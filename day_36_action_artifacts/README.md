# Build Artifacts: Uploading, Downloading, and Storing Build Artifacts

## Scope

Build artifacts are the durable outputs of a build process. They can include compiled binaries, packaged applications, frontend bundles, deployment manifests, libraries, container metadata, test reports, generated documentation, and other files that must survive the build environment long enough to be consumed by another stage.

Artifact handling has three distinct operational concerns:

- **Uploading** moves a completed build output from a build workspace into durable artifact storage.
- **Downloading** retrieves a previously published artifact for deployment, testing, debugging, release distribution, or another controlled consumer.
- **Storing** preserves artifact bytes and their metadata according to naming, immutability, integrity, access, retention, and lifecycle rules.

A useful artifact workflow is therefore more than copying a ZIP or TAR file. A reliable system maintains the relationship between an artifact, the source revision that produced it, the build that created it, its contents, its checksum, its storage object, its retention policy, and the consumers that retrieve it.

The implementations in this repository deliberately approach the subject from different engineering perspectives:

| Implementation | Technical perspective |
| --- | --- |
| Python | Complete local artifact lifecycle with packaging, manifests, checksums, safe extraction, storage, download verification, and retention cleanup |
| JavaScript | Node.js artifact pipeline using asynchronous filesystem operations, event-driven lifecycle notifications, metadata, checksums, immutable storage, and cleanup |
| C++ | Repository governance case study modeling artifact states, quality gates, integrity verification, deployment eligibility, and immutable lifecycle transitions |
| Java | Enterprise-oriented domain model using records, enums, policy interfaces, immutable collections, state transitions, validation, and retention services |
| PostgreSQL | Relational artifact repository with provenance, files, status checks, storage objects, download records, constraints, indexes, triggers, views, transactions, and retention queries |

The examples use build and release scenarios rather than generic file-copy demonstrations.

---

## Artifact lifecycle

A build artifact normally moves through several operational stages:

`build output → package → metadata → upload → storage → integrity verification → download → deployment/consumption → retention → expiration → cleanup`

The stages have different responsibilities.

Packaging turns many build-output files into a transferable unit. Metadata establishes provenance and describes the contents. Upload makes that unit durable. Storage gives the artifact a stable identity and retention policy. Download transfers the stored object to a consumer. Integrity verification determines whether the received bytes match the expected artifact. Retention determines how long the artifact remains available. Cleanup removes objects that are no longer required.

These stages should not be collapsed into one operation because successful transfer, successful verification, and deployment eligibility are different conditions.

---

## Artifact identity and provenance

An artifact needs an identity that distinguishes it from other builds. The examples associate artifacts with:

- repository name
- source commit
- build number
- pipeline name
- artifact name
- creation time
- archive format
- archive checksum
- individual file checksums
- retention period
- environment or release metadata

The source commit is especially important. A file named `release.tar.gz` is not sufficient provenance because the same filename may be produced by many different builds. A stable artifact identifier and source revision establish which build produced the stored content.

The Python manifest records the source commit in `commit_sha`, while the JavaScript implementation stores it in the generated manifest. The C++ and Java domain models treat the repository, commit, and build number as explicit artifact metadata. PostgreSQL stores those fields directly in the `artifacts` table and protects important provenance fields against mutation.

---

## Uploading build artifacts

Uploading should occur only after the build output has passed the checks that the pipeline considers necessary.

The Python implementation uses `ArtifactBuilder.package()` to collect build files, calculate individual SHA-256 values, create a compressed archive, calculate the archive checksum, and write a JSON manifest. `ArtifactRepository.upload()` verifies the archive checksum before copying it into the repository.

This creates an important boundary:

`build workspace → validated artifact package → artifact repository`

The build workspace is temporary. The artifact repository is durable.

The JavaScript implementation uses asynchronous filesystem APIs so file collection, metadata writing, and storage operations do not block the Node.js event loop unnecessarily. Its `ArtifactStore.upload()` checks the archive checksum before copying the artifact and deliberately rejects an existing object identifier rather than silently replacing it.

The C++ case study treats uploading as a state transition from `Staged` to `Uploaded`. The transition is rejected when a required quality check has failed.

The Java implementation separates publication policy from storage behavior. `ProductionArtifactPolicy` requires the configured quality checks before `ArtifactService.upload()` can transition an artifact from `CREATED` to `UPLOADED`.

The PostgreSQL implementation enforces upload-related conditions at the database layer. An artifact entering an active state must have files and must not have failed, cancelled, or pending status checks. This prevents an application bug from trivially bypassing important integrity rules.

---

## Artifact packaging

Packaging defines the unit that is uploaded and later downloaded.

The Python program uses `tarfile` to create a `.tar.gz` artifact. Its manifest describes every included file, including:

- relative path
- byte size
- SHA-256 checksum

The archive has its own SHA-256 checksum as well.

This creates two useful integrity levels:

`archive checksum → verifies the transferred artifact package`

`file checksum → verifies the extracted contents`

The JavaScript implementation delegates TAR/GZIP creation to the system `tar` command because Node.js's standard library does not provide a TAR writer. Node itself handles artifact metadata, hashing, storage, verification, and lifecycle behavior.

The SQL model does not package files itself. Instead, it records the package as an artifact and stores individual file metadata in `artifact_files`. This reflects the separation between a database that governs artifact metadata and an object store that contains the large binary payload.

---

## Checksums and integrity

A checksum provides a way to compare the bytes received by a consumer with the bytes expected from the artifact repository.

The Python implementation uses SHA-256 incrementally through `sha256_file()`. Reading the file in chunks avoids loading a large artifact into memory.

The JavaScript implementation uses Node's streaming `crypto.createHash()` approach. The file is processed as a stream and the digest is finalized when the stream ends.

The C++ program uses a deliberately small deterministic fingerprint because the C++17 standard library does not provide SHA-256. Its source code explicitly identifies this as a teaching substitute rather than a production cryptographic checksum. A production C++ artifact service should use an established cryptographic implementation or the checksum returned by its storage layer.

The Java implementation represents the expected archive checksum as immutable artifact metadata and rejects verification when the observed value differs.

The SQL schema requires a 64-character hexadecimal archive checksum and applies the same structural requirement to individual file checksums.

A checksum mismatch must be treated as a failed integrity event, not as a warning that can be ignored before deployment.

---

## Downloading artifacts

Downloading is a consumer-side operation. Typical consumers include deployment controllers, test environments, release jobs, packaging systems, and engineers investigating a previous build.

A successful download means that bytes were transferred. It does not automatically mean that the consumer has the correct artifact.

The Python `ArtifactRepository.download()` accepts an expected checksum and removes the downloaded file when verification fails. The program then safely extracts the verified archive and compares every extracted file with its manifest entry.

The JavaScript implementation follows the same separation. `download()` copies the object and verifies its checksum before returning the path to the consumer.

The Java service exposes deployment through `requestDeployment()`. The method permits consumption only after the artifact has entered a verified lifecycle state.

The SQL model records download attempts in `artifact_downloads`. A failed observed checksum therefore becomes an auditable event without modifying the immutable artifact itself.

---

## Safe artifact extraction

Archive extraction introduces a security issue that simple file copying does not have.

An archive can contain a path such as `../../sensitive-file` or an absolute path. If an extractor blindly writes archive members, an attacker-controlled archive can attempt path traversal outside the intended extraction directory.

The Python implementation explicitly rejects absolute paths and paths containing parent-directory traversal. It also rejects symbolic and hard links and confirms that the resolved extraction path remains inside the destination directory.

This check belongs at the extraction boundary. A valid checksum does not make an archive safe to extract. Integrity and content safety are separate properties.

---

## Immutable artifact storage

An artifact should normally be immutable after publication.

Changing the bytes associated with an existing artifact identifier creates provenance ambiguity. A deployment record saying that build 184 was deployed becomes unreliable if the object named by build 184 can later be replaced.

The JavaScript store therefore uses exclusive file creation and rejects an existing artifact identifier.

The C++ repository refuses invalid lifecycle transitions and treats an uploaded artifact as a distinct stored object.

The Java domain model keeps provenance fields immutable and does not expose setters for repository, commit, build number, file list, or checksum.

The PostgreSQL `prevent_artifact_mutation()` trigger rejects changes to archive checksum, source commit, build number, and archive format. The database can still change legitimate lifecycle metadata such as state, but the identity and provenance of the content remain protected.

Object storage systems can provide stronger immutability through object-lock or retention mechanisms. The database rules in this example demonstrate the governance layer rather than replacing storage-provider controls.

---

## Metadata and manifests

Artifact metadata answers questions that artifact bytes alone cannot answer efficiently.

A useful manifest can establish:

| Metadata | Purpose |
| --- | --- |
| Artifact ID | Stable identity for storage and retrieval |
| Repository | Identifies the source project |
| Commit SHA | Establishes source provenance |
| Build number | Identifies the CI/CD execution |
| Pipeline | Identifies how the artifact was produced |
| Created timestamp | Supports auditing and retention |
| Archive checksum | Verifies the complete downloaded object |
| File checksum | Verifies individual extracted files |
| File size | Detects unexpected content changes |
| Retention period | Defines lifecycle policy |
| Labels | Supports filtering and release classification |

The Python and JavaScript programs create JSON manifests. PostgreSQL stores equivalent information in normalized relational columns and uses JSONB for metadata that is useful for filtering but does not need to become a separate relational entity.

---

## Python implementation

The Python implementation is the most complete local end-to-end demonstration.

`ArtifactBuilder` handles build-output discovery and packaging. It refuses to publish an empty directory because an empty artifact is generally evidence of a broken build or an incorrectly configured output path.

`ArtifactManifest` records artifact provenance and per-file integrity information.

`ArtifactRepository` acts as a local object repository. It supports:

- upload
- manifest retrieval
- download
- artifact listing
- deletion
- retention cleanup

`safe_extract()` protects the extraction destination against archive path traversal.

`verify_extracted_files()` performs a second integrity check after extraction. This is useful when an artifact consumer needs confidence that the extracted files correspond to the manifest rather than merely trusting that the archive transferred successfully.

The demonstration uses a temporary directory, so it does not leave build artifacts on the host.

---

## JavaScript implementation

The Node.js implementation emphasizes asynchronous I/O and event-driven artifact processing.

`collectFiles()` recursively discovers build output and calculates per-file checksums.

`buildArtifact()` creates a compressed package and writes a manifest.

`ArtifactStore` provides repository operations and deliberately prevents overwriting an existing artifact identifier.

The `EventEmitter` demonstration shows how an artifact lifecycle can produce events such as `artifact:uploaded` and `artifact:verified`. In a larger CI/CD system, those events could trigger deployment orchestration, release notifications, artifact indexing, or audit processing.

The implementation also demonstrates why the JavaScript runtime can be useful for artifact automation: filesystem operations are asynchronous, while event-driven lifecycle notifications can connect independent stages without making the artifact store itself responsible for all downstream behavior.

---

## C++ repository governance case study

The C++ implementation models a release artifact as a governed domain object rather than focusing on archive syntax.

The central state machine is:

`Staged → Uploaded → Verified → Expired → Deleted`

An artifact cannot move directly from `Staged` to deployment. Upload requires all configured quality checks to pass. Verification requires the expected checksum. Download requires the artifact to be verified.

The case study models:

- repository provenance
- build number
- commit SHA
- artifact files
- file sizes
- file checksums
- quality checks
- retention
- storage state
- deployment eligibility

`ArtifactRepository` owns the lifecycle rules. This design keeps invalid transitions out of individual callers.

The program also demonstrates an important distinction between checksum verification and quality validation. A build can have valid bytes while still failing a security scan or dependency audit. Conversely, a build can pass all quality checks while a corrupted download fails checksum validation. These are separate gates.

The C++ implementation uses a deterministic non-cryptographic fingerprint solely because standard C++17 does not include SHA-256. It explicitly documents that limitation so the example does not accidentally present a non-cryptographic hash as production integrity protection.

---

## Java enterprise model

The Java implementation uses explicit domain types to make artifact policy visible in the design.

`ArtifactFile` represents an individual output and validates its path and size.

`BuildMetadata` represents provenance such as repository, commit, build number, and pipeline.

`ArtifactState` models legal lifecycle states.

`CheckType` represents publication quality gates.

`ArtifactPolicy` separates policy decisions from the storage service. `ProductionArtifactPolicy` requires all configured production checks before upload.

`ArtifactService` owns registration, upload, verification, deployment eligibility, retention, expiration, and deletion.

The state transition logic inside `Artifact.transitionTo()` prevents arbitrary state changes. For example, a deleted artifact cannot return to an active state, and a created artifact cannot be treated as verified without passing through upload and checksum verification.

Java records and immutable collections reduce accidental mutation of artifact metadata. This is particularly useful for provenance because changing a checksum or source revision after registration would undermine the relationship between the artifact and its build.

---

## PostgreSQL data model

The SQL implementation treats artifact management as a relational governance problem.

### Repositories

`repositories` identifies the source repository and its default branch. Artifact rows reference repositories through a foreign key.

### Artifacts

`artifacts` stores the primary artifact identity and provenance:

- repository
- artifact name
- build number
- commit
- pipeline
- lifecycle state
- archive format
- archive size
- archive checksum
- creation timestamp
- retention timestamp
- metadata

The uniqueness constraint on repository, build number, and artifact name prevents accidental duplicate build identities.

### Artifact files

`artifact_files` stores the manifest-level file information. A unique constraint prevents the same relative path from being represented twice within one artifact.

The path constraint rejects absolute paths and parent-directory traversal patterns.

### Status checks

`artifact_status_checks` represents quality gates such as unit tests, security scans, dependency audits, and package validation.

A failed or pending check can therefore be evaluated independently from the artifact bytes.

### Storage objects

`artifact_storage_objects` represents the physical storage location without storing the large object itself in PostgreSQL.

The model records:

- storage provider
- bucket
- object key
- upload time
- storage class
- encryption state
- object identifier metadata

This reflects a common architecture in which relational storage manages artifact metadata while object storage holds large binary objects.

### Download records

`artifact_downloads` provides an audit trail for artifact consumption and records whether checksum verification succeeded.

---

## Database-level integrity

Application validation is useful, but some artifact rules should also be enforced by the database.

The SQL schema uses:

- foreign keys to prevent orphaned metadata
- unique constraints to prevent duplicate artifact identities
- check constraints for valid states and formats
- checksum format constraints
- non-negative size constraints
- path-safety constraints
- indexes for repository and retention queries
- triggers for immutable provenance
- triggers for publication validation
- transactions for state changes involving storage metadata

The `artifact_upload_validation()` trigger prevents an artifact from becoming active without files and without a clean set of status checks.

The `prevent_artifact_mutation()` trigger prevents changes to source commit, build number, archive format, and archive checksum after publication.

Database enforcement does not remove the need for application-level validation. The two layers serve different purposes: application validation gives users immediate and contextual errors, while database constraints protect shared state even when multiple applications access the same data.

---

## Retention and lifecycle management

Artifact retention is a storage-management problem as well as a release-management problem.

Keeping every artifact indefinitely increases storage cost and makes artifact inventories harder to operate. Deleting artifacts too aggressively can make rollback, incident investigation, and reproducibility impossible.

The examples model retention with an explicit expiration time.

The Python repository computes expiration from creation time and retention days and supports `purge_expired()`.

The JavaScript store performs equivalent expiration evaluation.

The Java service refuses expiration before the retention period has elapsed.

The PostgreSQL model uses `retention_until` and a partial index over active artifacts. This allows retention-oriented queries to focus on rows that are candidates for expiration rather than scanning every historical state.

A production cleanup process should normally separate expiration from physical deletion when audit or recovery requirements demand it.

---

## Storage architecture

A practical artifact platform often separates responsibilities:

`CI runner`

produces build output in a temporary workspace.

`Artifact packaging`

creates a normalized archive and manifest.

`Artifact metadata service`

records provenance, lifecycle, checksums, ownership, and retention.

`Object storage`

stores the large immutable binary object.

`Deployment system`

downloads a specific artifact and verifies its identity before use.

`Retention service`

expires and eventually deletes objects according to policy.

This separation avoids placing large binary payloads directly into relational database rows while retaining strong queryability for metadata.

---

## Storage classes and cost

Object storage commonly provides multiple storage classes with different cost and retrieval characteristics.

Frequently consumed release artifacts may use standard storage.

Older artifacts that are still required but rarely accessed may use infrequent-access storage.

Long-term archival artifacts may use an archive class when slower retrieval is acceptable.

The PostgreSQL `storage_class` field models this distinction. The field does not itself move an object between storage tiers. A lifecycle service can use it as policy metadata when coordinating with the actual storage provider.

Storage-class selection should consider rollback frequency, incident response requirements, compliance retention, retrieval latency, and total cost rather than only raw storage price.

---

## Security considerations

Artifact storage should be treated as a security boundary.

### Integrity

Always verify artifact identity and checksums when integrity matters. A successful HTTP or object-storage download does not prove that the bytes are the intended build.

### Immutability

Prevent ordinary users and automation from replacing an artifact under an existing release identifier. Mutable artifacts weaken deployment provenance.

### Access control

Upload and download permissions should be separated where appropriate. A CI runner may have permission to publish artifacts without receiving broad access to unrelated production artifacts.

### Encryption

Artifacts can contain source code, configuration, generated credentials, debug information, or proprietary binaries. Storage encryption should be enabled where organizational policy requires it. The SQL model records `encryption_enabled` as part of storage metadata.

### Archive extraction

Downloaded archives must be treated as untrusted input. Path traversal, symbolic links, hard links, decompression bombs, excessive file counts, and unexpected executable content are separate concerns from checksum verification.

### Secrets

Build artifacts should not contain credentials merely because the build environment contained them. Secret injection should occur at deployment time when possible. Artifact publication should be preceded by appropriate secret scanning when the contents warrant it.

---

## Failure modes

Artifact systems fail in ways that are different from ordinary application file handling.

A build may produce no output. The Python implementation rejects an empty artifact.

A package may contain unexpected paths. The Python extractor rejects unsafe members.

An upload may be interrupted. The consumer should not treat a partial object as a valid release artifact.

A downloaded object may have the wrong checksum. The Python and JavaScript implementations reject it.

A build may pass compilation while failing security or dependency checks. The C++ and Java implementations represent quality checks independently from content integrity.

A stored object may outlive its intended retention period. The retention processes identify it for expiration.

A database row may be accidentally modified after publication. PostgreSQL triggers protect critical provenance fields.

A deleted artifact may still be referenced by storage metadata. Foreign keys and restrictive deletion behavior make such relationships visible rather than silently discarding them.

---

## Performance considerations

Large artifacts should be processed incrementally.

The Python checksum implementation reads fixed-size chunks rather than loading the complete archive into memory.

The JavaScript checksum implementation uses a file stream.

Object storage is generally more appropriate than relational database BLOB storage for large build outputs when the system needs scalable binary storage, lifecycle policies, and high-throughput downloads.

Metadata queries should use indexes that reflect actual access patterns. The SQL model indexes repository/build history, artifact files, status checks, download history, and retention candidates.

Artifact compression has a trade-off. Compression can reduce storage and network costs but consumes CPU during packaging and extraction. Already-compressed assets may gain little from additional compression.

Artifact granularity also affects performance. A single large release archive is convenient for deployment, while separate artifacts can allow consumers to retrieve only the component they need.

---

## Common mistakes

### Treating filenames as artifact identity

`release.zip` is not sufficient identity. The repository, build, commit, and immutable artifact identifier must distinguish one release from another.

### Trusting successful upload

An upload response confirms that the storage operation succeeded. It does not by itself prove that the object corresponds to the intended build.

### Replacing artifacts in place

Replacing build 184 with different bytes destroys provenance. New content should receive a new artifact identity.

### Ignoring retention

Without explicit lifecycle rules, artifact repositories grow continuously and historical objects become difficult to manage.

### Storing only the archive checksum

The archive checksum validates the transferred package. A manifest with individual file checksums can provide stronger post-extraction verification.

### Extracting archives without path validation

Checksum verification and path safety solve different problems. A trusted archive can still contain paths that are unsafe for a particular extraction location.

### Mixing deployment policy with storage operations

A storage service should know how to persist and retrieve artifacts. Deployment policy should determine whether a particular artifact is acceptable for a deployment target.

### Treating failed download verification as proof that the stored artifact is corrupt

A failed download may indicate transfer corruption, an incorrect expected checksum, or a faulty consumer. The immutable stored artifact should remain unchanged until its own integrity has been independently established as invalid.

---

## Practical relationships

Artifact uploading, downloading, and storing form one lifecycle, but they have different technical boundaries.

Uploading answers:

`How does a build output become a durable artifact?`

The important mechanisms are packaging, metadata creation, validation, checksum generation, and controlled publication.

Storing answers:

`How is the artifact preserved and governed after publication?`

The important mechanisms are immutable identity, object keys, metadata, retention, access control, encryption, storage class, and lifecycle state.

Downloading answers:

`How does a consumer safely obtain a specific artifact?`

The important mechanisms are artifact selection, authorization, transfer, checksum verification, safe extraction, and consumption audit.

The distinction matters because a system can succeed at one operation while failing another. An artifact can upload successfully but later fail download verification. A downloaded artifact can be intact but still fail deployment policy because its security scan failed. An artifact can be valid and deployable while remaining subject to retention expiration.

---

## Production considerations

A production artifact service should preserve enough information to answer:

- Which repository produced this artifact?
- Which source commit produced it?
- Which build generated it?
- Which pipeline published it?
- What exact checksum identifies the stored bytes?
- What files are inside the package?
- Which quality checks passed?
- Where is the object physically stored?
- Who or what downloaded it?
- Was the downloaded content verified?
- When does the retention period expire?
- What policy permits deletion?
- Can the artifact still be used for rollback?

The code examples implement these questions at different layers rather than attempting to turn every concern into one large function.

The resulting design treats a build artifact as an immutable, identifiable release object with provenance and lifecycle state, rather than as an anonymous file copied between directories.

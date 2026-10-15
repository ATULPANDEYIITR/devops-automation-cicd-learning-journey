# Artifact Management: Repositories, Versioning, and Immutability

## Purpose and scope

Artifact management is the controlled publication, storage, identification, verification, distribution, and retirement of software build outputs. An artifact may be a compiled library, container image, application package, model file, deployment bundle, database migration package, or signed release archive.

An artifact repository is not merely a directory containing downloadable files. It maintains the relationship between a payload, its version, its digest, its publisher, its source revision, and the policies governing its use.

This project models an artifact repository for an infrastructure inspection service. A release pipeline publishes candidate and stable builds, consumers retrieve specific versions, and deployment environments refer to approved releases through mutable channel pointers. The implementations distinguish three closely related mechanisms:

- **Artifact repositories** manage artifact identity, metadata, storage, discovery, and retrieval.
- **Versioning** identifies releases and establishes ordering and compatibility expectations.
- **Immutability** prevents a published version from silently changing its payload or provenance.

Content-addressed storage connects these mechanisms by identifying a payload through a cryptographic digest rather than relying solely on a filename or version label.

## Repository architecture

The logical architecture separates artifact identity from payload storage and deployment selection.

    Source repository and build pipeline
                    |
                    v
             Publisher identity
                    |
                    v
          Artifact publication request
                    |
                    v
       Metadata and version validation
                    |
                    v
        Content digest and verification
                    |
          +---------+---------+
          |                   |
          v                   v
    Immutable blob       Immutable manifest
          |                   |
          +---------+---------+
                    |
                    v
             Artifact catalog
                    |
           +--------+--------+
           |                 |
           v                 v
      Consumer retrieval   Release channel
                               |
                               v
                         Deployment target

The blob contains the payload. The manifest describes the published version and records its digest, size, media type, publisher, and source revision. The catalog makes versions discoverable. A release channel selects a version for an environment without changing the version itself.

A production implementation must make publication durable and atomic across its storage components. If blob storage succeeds but metadata publication fails, the system must recover or reconcile the orphaned blob. If a manifest is visible before its payload is durable, consumers may observe a release that cannot be retrieved. The local Python and in-memory JavaScript demonstrations illustrate these concerns but do not replace a transactional, durable repository service.

## Artifact identity and repository organization

An artifact is identified by more than its display name. A useful identity combines a repository or namespace, a package name, and a version. Its manifest binds that identity to the exact payload digest and publication provenance.

The implementations use names such as `telemetry-agent` and `bridge-inspection-engine`. Names are validated to avoid ambiguous identifiers and unsupported characters. Version identity is distinct from storage identity: two versions may contain identical bytes and therefore reference the same content-addressed blob.

A repository commonly needs the following metadata:

| Field | Purpose |
|---|---|
| Package name | Identifies the artifact family within a namespace |
| Version | Identifies a specific release of that family |
| SHA-256 digest | Identifies the expected payload bytes |
| Size and media type | Support transfer validation and consumer handling |
| Publisher | Identifies the human or service that published the release |
| Source revision | Connects the artifact to its source commit |
| Publication timestamp | Records when the repository accepted the version |
| Build metadata | Describes the pipeline, platform, or build environment |
| Lifecycle state | Determines whether the artifact can be distributed |
| Audit events | Record publication, promotion, quarantine, and revocation |

Metadata must be trustworthy enough for its intended purpose. A publisher string supplied by an unauthenticated client is not proof of identity. Production publication APIs should authenticate the caller and derive or validate publisher identity from the authenticated principal.

## Content-addressed storage and integrity

Content-addressed storage uses a digest of the artifact bytes as the storage identifier. With SHA-256, the repository calculates a 256-bit digest and represents it as 64 lowercase hexadecimal characters.

If the bytes are unchanged, the digest is unchanged. If the bytes change, the digest is expected to change. The digest provides an efficient way to detect accidental corruption and substitution, assuming the expected digest itself is trusted.

The Python implementation computes SHA-256 with `hashlib`. The JavaScript implementation uses Node.js `crypto`. The Java implementation uses `MessageDigest`. Each verifies retrieved bytes against the digest recorded in the manifest.

The C++ case study deliberately uses a simple demonstration fingerprint rather than a cryptographic implementation. It illustrates the registry's identity and integrity-checking control flow, but its fingerprint must not be treated as secure. A production C++ registry must use a vetted SHA-256 implementation and compare the computed digest against a trusted manifest.

Digest verification does not establish who published an artifact. An attacker able to replace both the payload and its trusted digest could produce a self-consistent but malicious artifact. Stronger systems combine digest verification with authenticated publication, signed manifests, trusted public keys, access control, and protected audit records.

### Deduplication

If two package versions have the same digest, they can reference the same immutable blob. This reduces storage use without merging their metadata or identities.

For example, version `1.0.0` and version `1.1.0` might contain identical binaries but different release notes or source provenance. Their manifest records remain distinct. The blob is shared only because the payload bytes are identical.

Deduplication requires careful lifecycle management. A blob must not be deleted while any live manifest references it. Garbage collection should identify unreferenced content, respect retention requirements, and coordinate with concurrent publication and deletion operations.

## Semantic versioning and release identity

The implementations use semantic version components consisting of major, minor, and patch numbers, with optional prerelease and build metadata.

- A **major** increment normally signals an incompatible public interface change.
- A **minor** increment normally introduces backward-compatible functionality.
- A **patch** increment normally provides a backward-compatible correction.
- A **prerelease** identifier marks a release candidate or another version that has not reached stable status.
- **Build metadata** records additional identification information but does not change semantic version precedence.

For example, `3.4.0-rc.1` is a release candidate for `3.4.0`. The stable version has higher precedence than the candidate. Build metadata such as `3.4.0+linux.amd64` does not change the precedence of `3.4.0`.

Version ordering must follow semantic-versioning rules rather than ordinary lexical string sorting. Lexical sorting can incorrectly order versions such as `2.10.0` and `2.9.0`. The Python, JavaScript, and Java implementations provide version-aware comparisons.

The SQL implementation stores version components in separate columns and records prerelease and build metadata independently. This supports indexing and filtering without depending on text sorting. Its uniqueness constraint prevents duplicate major, minor, patch, and prerelease identities within one package.

A production parser should enforce the complete semantic versioning specification, including all identifier restrictions and boundary conditions. The sample implementations cover common validation and ordering rules, but they are educational implementations rather than a substitute for a fully conformant versioning library.

## Immutability and publication policy

An immutable artifact version cannot be overwritten with different bytes after publication. If a release is defective, the publisher creates a new version or changes an explicitly mutable release channel according to repository policy.

Immutability protects reproducibility. A deployment referencing `3.4.0` should retrieve the same expected payload tomorrow as it retrieved today. If the content behind that version silently changes, incident investigation, rollback, build verification, and software supply-chain analysis become unreliable.

The Python repository makes repeated identical publication idempotent when the payload, publisher, source revision, media type, and metadata agree. It rejects conflicting publication under an existing version. The JavaScript implementation serializes publication requests through a promise queue to prevent simultaneous writes from racing to claim the same version in the in-memory model.

The C++ registry treats published manifests as stable records and rejects attempts to replace an existing release with different content. The Java registry uses immutable records and defensive copies of byte arrays to prevent callers from changing payload data through a retained reference.

The SQL implementation uses constraints and triggers to prevent changes to a version's identity, digest, publisher, source revision, and publication timestamp. Lifecycle changes remain possible because quarantining and revoking content are different from rewriting it.

Database triggers are only one part of an immutability policy. Production permissions should prevent ordinary application identities from disabling triggers, altering published manifests, or deleting audit evidence. Administrators and storage operators must be governed by separate controls.

## Python implementation: durable local repository model

The Python script implements a local repository with content-addressed blobs, JSON manifests, an index, semantic version parsing, retrieval, inventory export, and integrity checks.

`ArtifactRepository.publish()` validates the version and computes the SHA-256 digest before accepting the artifact. A new blob is written using exclusive file creation. The manifest is written through a temporary file followed by an atomic replacement, reducing the chance that a reader sees partially written JSON.

The repository index connects `name@version` identities to manifests and digests. Retrieval reads the manifest, locates the blob, checks its size, and recalculates the digest before returning the bytes.

The implementation also provides:

- Version discovery with semantic precedence ordering.
- Stable-version selection that excludes prereleases.
- Digest-based discovery for locating versions that share a payload.
- Inventory export for catalog review and reconciliation.
- Explicit exceptions for invalid metadata, missing artifacts, immutable-version conflicts, and integrity failures.
- Automated tests for publication, idempotency, version validation, missing versions, tampering, prerelease handling, and deduplication.

The local repository is intended to make the mechanisms executable and inspectable. Its index is a single JSON file, and it does not coordinate independent processes with a transactional database. Atomic file replacement does not make the multi-file publication sequence a fully atomic transaction. A production service should use durable transactional metadata, concurrency control, and storage reconciliation.

## JavaScript implementation: asynchronous publication and release channels

The JavaScript implementation models an event-driven repository service using Node.js. It emphasizes asynchronous publication, immutable in-memory records, event subscribers, release channel promotion, and audit events.

The private fields in `ArtifactRepository` prevent callers from directly replacing the internal maps. Publication copies the supplied byte buffer before calculating its digest, so mutation of the caller's original buffer cannot change the stored artifact.

The promise queue serializes publication operations. This is useful in a single Node.js process because multiple asynchronous callers may otherwise attempt to publish the same package version before either request completes. It does not coordinate multiple processes or machines; a shared database uniqueness constraint and transaction are needed for that.

The event mechanism separates repository operations from monitoring. A listener can record publication events or report release-channel changes. Listener failures are captured without undoing a publication that has already completed. In a production system, important audit records should be committed durably with the corresponding metadata operation rather than relying only on an in-memory callback.

Release channels are mutable pointers. Promoting a stable artifact to `production` updates the channel and records the prior target in the audit trail. The artifact manifest and digest remain unchanged. This separation permits controlled promotion and rollback without rewriting a published release.

The implementation is an in-memory model, so restarting the process discards its catalog, blobs, channels, and audit history. It demonstrates the behavior of the repository service rather than durable storage.

## C++ case study: infrastructure inspection releases

The C++ program models an artifact registry used by an infrastructure inspection platform. Build artifacts move from release-candidate publication to stable publication and then to a deployment channel.

`ArtifactRegistry` separates manifest records, blob storage, channel assignments, and audit events. Maps provide deterministic manifest lookup, while the blob map supports digest-based deduplication. The `versions()` method returns releases in version precedence order.

Publication validates package metadata and rejects a conflicting attempt to reuse an existing version. Retrieval verifies the expected size and stored fingerprint. Promotion changes the channel mapping and writes an audit event instead of modifying the published artifact.

The example demonstrates how a registry can distinguish immutable release records from mutable deployment selection. It also exposes the boundary between a domain model and production infrastructure.

The sample digest function is explicitly non-cryptographic. It is useful only for demonstrating the flow of digest generation and verification. A real registry must replace it with a cryptographic hash, persist metadata transactionally, coordinate concurrent writers, authenticate publishers, and retain audit evidence independently of ordinary application writes.

C++ is useful when artifact-management infrastructure needs predictable resource behavior or integration with native build and storage systems. The choice of language does not itself provide immutability. Correctness depends on digest verification, storage semantics, transaction boundaries, and access controls.

## Java implementation: enterprise lifecycle and governance

The Java program represents repository concepts as explicit domain types rather than loosely structured dictionaries. `ArtifactKey` combines a package name and parsed semantic version. `ArtifactManifest` binds that identity to the digest, payload size, media type, publisher, source revision, timestamp, and metadata.

Records provide concise immutable data carriers. Maps maintain manifest, blob, lifecycle-state, and promotion indexes. `ArtifactRegistry` exposes synchronized service methods so that operations within the same registry instance cannot interleave unsafely.

The lifecycle state distinguishes a published artifact from a quarantined or revoked artifact. Quarantine prevents distribution while preserving the manifest and evidence needed for investigation. Revocation is terminal in the example. A quarantined or revoked artifact cannot be silently changed back to published.

Release environments use an enum, reducing the risk of inconsistent values such as `prod`, `production`, and `Production`. A promotion stores the target artifact key and actor without rewriting artifact identity.

The registry uses defensive copying for payload arrays because Java arrays are mutable even when referenced by a record. Without copying, a caller could mutate data after publication and invalidate the digest relationship.

The synchronized methods provide process-local coordination only. Multi-instance deployments require shared transactional storage and appropriate database isolation or locking. A production audit trail should also have durable retention and access controls.

## SQL implementation: relational integrity and auditability

The PostgreSQL script represents repository governance as normalized relational data.

| Table | Responsibility |
|---|---|
| `repository` | Names and describes repository namespaces |
| `artifact_package` | Groups versions under a package identity |
| `artifact_blob` | Stores immutable digest, size, media type, and storage URI metadata |
| `publisher` | Records authenticated publisher identities |
| `source_revision` | Connects a release to a repository revision and branch |
| `artifact_version` | Records version identity, digest, provenance, and lifecycle state |
| `artifact_metadata` | Stores version-specific key-value metadata |
| `release_channel` | Maps an environment to its currently selected version |
| `artifact_audit_event` | Records publication, lifecycle changes, and promotions |

Foreign keys enforce the relationships between packages, repositories, blobs, publishers, source revisions, versions, and channels. Unique constraints prevent duplicate package names within a repository, duplicate source revisions within a repository, repeated metadata keys, and conflicting version identities.

The version table stores semantic version components separately. This supports version-aware queries and indexed release discovery. The uniqueness constraint includes the prerelease identifier so that a stable release and its release candidate can coexist.

The `prevent_artifact_version_rewrite()` trigger prevents changes to a published version's identifying and provenance fields. The `prevent_blob_rewrite()` trigger prevents updates to content-addressed blob metadata. These mechanisms enforce immutability at the database layer rather than relying exclusively on application code.

The channel validation trigger checks that the selected version belongs to the correct package and remains published. The `promote_artifact()` function performs a controlled channel update and inserts an audit event. The transaction makes the metadata changes part of a single database transaction.

The sample queries provide a release inventory, identify content reuse, resolve the production channel, inspect missing blob references, and review the audit trail. The demonstration quarantines a release candidate and attempts to promote it, capturing the expected rejection.

The `artifact_blob` table represents metadata about external payload storage. The database does not independently calculate a SHA-256 digest for an object in external storage. The application or storage integration must verify the actual bytes before publication and retrieval. A foreign key can guarantee that a referenced digest exists in the database, but it cannot prove that an external object has not been altered.

## Release channels and environment promotion

A release channel is a mutable name that resolves to an immutable artifact version. Examples include `development`, `staging`, and `production`.

A channel allows an operator to promote an existing version after validation. If a newly deployed version fails an operational check, the channel can be redirected to a previously published version. The rollback changes deployment selection, not the historical payload.

Channel mutation still requires governance. Production systems should restrict who can promote releases, record the reason for each promotion, and verify that the target artifact is published and approved for the intended environment.

A channel pointer should not be used as a substitute for a version identifier in a reproducible build record. A pipeline that records only `production` may retrieve a different version on a later run. For reproducibility, record the resolved version and digest used by the deployment.

## Lifecycle states and incident response

A release can remain immutable while its distribution eligibility changes.

- **Published:** The artifact is available for authorized consumers and eligible for promotion.
- **Quarantined:** Distribution and promotion are blocked while the release is investigated.
- **Revoked:** The release is no longer eligible for use under the repository's policy.

Quarantine is useful when a vulnerability, suspicious dependency, malformed package, or provenance discrepancy is discovered. Revocation is appropriate when policy requires the release to be permanently rejected.

Neither state should erase the original manifest or its audit evidence. Preserving the original identity makes it possible to determine which deployments consumed a release and to investigate the timeline of an incident.

The Java lifecycle model prevents a revoked version from being restored. The SQL trigger prevents a quarantined version from being changed directly back to published. Organizations may adopt more complex recovery policies, but recovery should create a new approved release or follow an explicitly authorized and audited exception process.

## Failure modes and operational controls

### Digest mismatch

A digest mismatch indicates that the retrieved bytes do not match the manifest. The consumer should reject the payload and record the failure. It should not silently recalculate the manifest digest and continue, because doing so would convert detection into acceptance of potentially substituted content.

### Version collision

A conflicting publication for an existing version must be rejected. Reusing a version for different content destroys the assumption that a version identifies a stable release. The publisher should create a new version and preserve the rejected attempt in operational logs where appropriate.

### Partial publication

A failure after writing the blob but before committing the manifest can leave unreferenced content. A failure that exposes metadata before the blob is durable can create a broken release. Production publication should use a clear commit protocol, idempotent retries, and reconciliation for orphaned objects.

### Concurrent publication

Two release workers may try to publish the same version simultaneously. Process-local locks do not coordinate separate service instances. A unique database constraint and transactional publication workflow are needed to ensure that only one version identity is accepted.

### Compromised publisher credentials

Immutability cannot prevent an authorized but compromised publisher from publishing malicious bytes under a new version. Strong publisher authentication, restricted publishing permissions, build provenance, signature verification, approval workflows, and independent audit records reduce this risk.

### Storage retention and deletion

Immutable artifacts consume storage as versions accumulate. Retention policy should distinguish production releases, release candidates, revoked artifacts, and artifacts subject to legal or operational retention. Garbage collection must not delete a blob while any retained manifest references it.

## Performance and production boundaries

Digest calculation requires reading the payload bytes, so publication and verification are generally linear in artifact size. Large artifacts benefit from streaming hash computation, resumable uploads, bounded buffering, and storage systems designed for large objects.

Content-addressed storage can reduce duplicate payload storage, but manifest lookup and release discovery still require indexes. A database index on package and version components supports common inventory queries. An index on the digest supports deduplication and reverse lookup. An audit index on artifact identity and event time supports incident investigations.

The examples use different persistence models to make their design trade-offs explicit. Python demonstrates a local filesystem repository and verification workflow. JavaScript models an asynchronous event-driven service. C++ presents a registry case study with explicit data structures and operations. Java models enterprise lifecycle policies through immutable domain records and service methods. PostgreSQL provides relational constraints, transactional channel promotion, and auditable state changes.

None of the in-memory or local demonstrations alone provides the durability, distributed concurrency control, authenticated access, cryptographic signing, and independent audit protection required by a production artifact repository. Those properties must be implemented and verified at the storage, service, deployment, and operational-policy layers.

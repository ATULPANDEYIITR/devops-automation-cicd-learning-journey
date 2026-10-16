# Nexus Repository: Repository Types, Artifact Publishing and Retrieval

## Scope

Nexus Repository is a repository manager for storing, organizing, distributing, and retrieving software components. It provides a controlled endpoint between developers, build systems, package clients, and upstream repositories.

This project models the central repository operations through five complementary implementations. The Python program provides a repository simulator with validation and executable assertions. The JavaScript program emphasizes asynchronous resolution, concurrent publication, and cache behavior. The C++ program presents a deterministic dependency-resolution case study. The Java program models repository governance using explicit domain types and defensive data handling. The PostgreSQL script represents repository metadata, access permissions, retrieval events, and integrity information relationally.

The four principal concerns are related but distinct:

- **Repository types** determine where artifacts originate, whether uploads are accepted, and how requests are resolved.
- **Artifact publishing** validates a package coordinate and its binary content before storing a release in an appropriate destination.
- **Artifact retrieval** resolves a requested coordinate, checks access permissions, and returns an existing artifact or obtains it through a configured proxy.
- **Repository governance** establishes permissions, immutability policies, integrity checks, and audit records around those operations.

The examples use internal software releases and external dependencies from a hypothetical enterprise platform.

## Repository types and their operational differences

| Repository type | Primary responsibility | Accepts direct publishing | Retrieves from an upstream |
|---|---|---|---|
| Hosted | Stores components published by an organization | Yes, when configured and authorized | No |
| Proxy | Caches components retrieved from an external repository | No | Yes |
| Group | Presents several compatible repositories through one endpoint | No | Delegates requests to its members |

### Hosted repositories

A hosted repository is the destination for internally produced packages. For example, `maven-releases` can hold the release `com.example.billing:billing-client:4.1.0`.

Publishing requires more than copying a file. The repository manager must validate the requested format, establish the artifact's canonical identity, verify the caller's permission, apply the redeployment policy, and record metadata about the resulting artifact.

A release repository commonly rejects replacement of an existing coordinate. If version `4.1.0` has already been published, publishing different bytes under the same release coordinate can cause builds to retrieve different software without any dependency declaration changing.

The Python, JavaScript, C++, and Java examples model immutable release behavior. The SQL schema represents uniqueness at the artifact-coordinate and repository levels.

### Proxy repositories

A proxy repository retrieves components from an upstream service and caches them locally. A Maven proxy might use Maven Central as its upstream. Subsequent requests for a cached component can be served locally rather than requiring another upstream request.

A cache miss and an upstream failure are not the same event. A miss means that the requested artifact is not present in the local cache. The upstream may return the artifact, return a not-found response, or fail because of a network or service problem.

The Python implementation includes an HTTPS retrieval adapter with a timeout and response-size limit. The JavaScript implementation supports an injectable fetch function for deterministic tests and an HTTPS network path for real retrieval. The C++ implementation uses a simulated upstream so its behavior is reproducible without network access. The Java implementation deliberately rejects uncached proxy requests because it has no HTTP transport adapter.

These differences are intentional. A repository metadata model can be tested independently from the transport implementation that communicates with an upstream server.

### Group repositories

A group repository provides one logical endpoint over several repositories. The `maven-public` group includes `maven-releases` and `maven-central-cache`.

A consumer can request an internal release through the group. If no suitable member contains the artifact, resolution can continue to the proxy member. The group is an access and resolution abstraction, not another binary-publishing destination.

Member order matters when multiple repositories contain the same coordinate. A production configuration should define repository precedence deliberately, particularly when internal package names could collide with public package names.

Group resolution also needs careful error handling. A missing artifact may justify trying another member, but an authorization failure or a serious upstream outage should not automatically be treated as an ordinary cache miss.

## Artifact coordinates and storage identity

A package client identifies an artifact through format-specific coordinates. The repository manager translates those coordinates into a canonical path or internal storage identity.

| Format | Example identity | Typical use |
|---|---|---|
| Maven | `com.example.billing:billing-client:4.1.0` | Java libraries, JARs, POM files, and related metadata |
| npm | `@example/payment-sdk@2.0.0` | JavaScript packages distributed as npm tarballs |
| PyPI | `payment_utils==0.8.2` | Python distributions such as wheels and source archives |
| Docker | `payments/api:4.1.0` | Container image manifests and associated layers |
| Raw | `reports/quality/2026-10.json` | Files that do not use a package-manager format |

Maven coordinates typically include a group identifier, artifact identifier, version, and extension. An optional classifier distinguishes related artifacts, such as a source archive and a compiled binary for the same version.

For npm, package names may be scoped. A scoped package's logical identity must not be confused with its encoded registry path. PyPI normalizes project names for lookup, while Docker registries use image names and tags or digests. Raw repositories rely on explicit paths rather than package-manager metadata.

These formats cannot be treated as interchangeable strings. The implementations use format-aware validation and path construction so that repository format errors and unsafe paths can be rejected before storage or retrieval.

Canonical paths in this project are educational representations. Real Nexus endpoints have format-specific layouts, metadata requirements, authentication behavior, and API conventions. The simulated paths are not intended to replace the official protocol implementation of any package manager.

## Publishing lifecycle

A safe publishing operation follows a consistent set of decisions.

The client first identifies the target repository and submits the package coordinates and binary content. The repository manager checks whether the repository is enabled, whether its format matches the package, and whether the caller has publishing permission. It then validates the coordinates, rejects empty content, calculates an integrity digest, and checks whether the coordinate already exists.

When the policy allows publication, the repository stores the artifact and records its provenance. When the policy prohibits redeployment, a duplicate coordinate is rejected without replacing the existing release.

The Python implementation represents artifacts as immutable data objects containing the coordinate, bytes, SHA-256 digest, publisher, publication time, and properties. The JavaScript implementation protects the coordinate and artifact record from ordinary reassignment and copies the incoming bytes before storage. The Java implementation uses records and defensive copies to reduce the risk of mutable data changing after validation.

In the SQL model, `artifact_versions` represents logical artifact coordinates, while `artifacts` records the repository-specific stored instance and its metadata. This separation permits a logical coordinate to exist independently of the repositories that store or cache it.

### Release immutability

Immutability prevents an already published release from silently changing under an unchanged version. It improves build reproducibility and makes incident investigations more reliable.

A repository may intentionally permit redeployment in a development or snapshot repository. That exception should be explicit. It should not become an accidental default for release repositories.

The code examples reject redeployment in their hosted release repositories. The SQL model enforces uniqueness for a repository and artifact coordinate. A production system also needs transactional write handling, storage-level consistency, and a well-defined policy for replacing or removing existing binaries.

### Checksums and content integrity

The SHA-256 digest identifies the bytes that were published or retrieved. Comparing a calculated digest with trusted metadata can detect unexpected changes in transit or storage.

A checksum does not establish that a package is trustworthy by itself. An attacker who can replace both the artifact and its checksum can defeat a comparison against untrusted metadata. Production pipelines should combine integrity verification with access controls, provenance records, and suitable signature or attestation verification where required.

The Python, JavaScript, and Java examples calculate SHA-256 through their standard libraries. The C++ program uses a small non-cryptographic fingerprint only to keep the case study self-contained; that value is explicitly unsuitable for validating production artifacts. The SQL script stores a digest value as metadata but does not calculate SHA-256 over a binary blob.

## Python implementation

The Python program provides an executable in-memory model of repository operations.

`RepositoryType`, `Format`, and `Permission` are enums, preventing repository type and authorization decisions from depending on loosely defined strings. `ArtifactCoordinate` validates format-specific identity rules and generates a storage key. `Artifact` stores the content and calculated SHA-256 digest with publication metadata.

`NexusModel` maintains repositories and an audit log. Its `publish` method enforces hosted-only publication, repository-format compatibility, authorization, non-empty content, and redeployment policy. Its retrieval method delegates to a recursive resolver that handles hosted storage, proxy retrieval, and group members.

The proxy adapter requires HTTPS, rejects credentials embedded in the upstream URL, uses a timeout, and limits the response size. These controls reduce some risks associated with remote retrieval, although a production proxy also needs redirect validation, network egress controls, response streaming, content-type handling, and format-aware metadata processing.

The test runner exercises Maven, npm, PyPI, and Docker artifacts. It checks checksum verification, group resolution, duplicate publication rejection, group publishing restrictions, missing-artifact handling, and authorization denial. The tests do not require an external server.

The in-memory repository state is lost when the process exits. It is intended for understanding policy and control flow, not for persistent storage or concurrent production use.

## JavaScript implementation

The Node.js implementation emphasizes asynchronous operations and concurrency.

The `NexusService` class separates coordinate validation, authorization, publishing, resolution, and upstream fetching. An injected fetch function allows tests to simulate an upstream repository without depending on network availability. The alternative network path uses the built-in `fetch` API, an HTTPS-only upstream, a timeout, and an origin check.

A group resolver attempts members in configured order. A proxy miss is fetched and cached locally. Subsequent requests can return the cached artifact, and the digest is recalculated before returning stored content.

Concurrent publishing illustrates an important distinction between an event-driven runtime and a repository consistency guarantee. JavaScript runs synchronous code on its event loop, but asynchronous work can overlap. The example uses a per-coordinate promise queue to serialize competing writers in one process. Two attempts to publish the same immutable coordinate therefore cannot both succeed.

This lock is local to the current process. It does not coordinate multiple Node.js instances, separate containers, or different repository servers. Production consistency must be enforced by a shared transactional store, the repository manager, or another distributed coordination mechanism.

The assertions check that an internal release resolves through the group, an external dependency is cached, a duplicate publication fails, publishing to a group is rejected, and an unauthorized caller cannot retrieve a private package.

## C++ case study

The C++ program models a build platform that retrieves internal releases and public dependencies through a common group endpoint.

`Coordinate` validates package identity and produces a format-aware storage key. `Repository` stores artifacts in an ordered map keyed by coordinates. `Principal` associates users with repository-specific permissions, and `RepositoryManager` centralizes publication, retrieval, deletion, and group resolution.

The case study first publishes a billing client into `maven-releases`. A build agent then retrieves that release through `maven-public`, demonstrating how an internal hosted repository can be exposed through a group. The program subsequently resolves `org.example:metrics-core:1.0.0` from a simulated upstream and records the cached copy in `maven-central-cache`.

The ordered member list expresses resolution precedence. A hosted miss is different from a proxy miss because the latter may trigger an upstream request. The example also rejects publication to a group and validates a raw path against traversal attempts.

The implementation uses `std::map` for deterministic coordinate lookup and `std::set` for visited repositories. Ordered-map lookup takes logarithmic time in the number of stored entries. Group resolution may inspect multiple members, so the number of repositories visited affects lookup latency.

The C++ program deliberately keeps upstream behavior deterministic. Its fingerprint is not cryptographic, and its exception handling is simplified for a compact case study. A production implementation should use SHA-256, distinguish missing artifacts from authorization failures and outages, and use an HTTP client with robust TLS verification and response handling.

## Java enterprise model

The Java program uses explicit domain types to make repository policy visible in the design.

`ArtifactCoordinate` is a record whose constructor validates the package identity before the value can be used. `Artifact` is also a record, but it defensively copies binary content on construction and access. This prevents a caller from modifying the stored byte array through a reference obtained from the record.

`Principal` maintains immutable permission sets. `Repository` encapsulates the repository's type, format, member configuration, and artifact store. `RepositoryService` acts as the service layer that validates operations and records audit events.

The service rejects publication into group and proxy repositories, enforces format compatibility, verifies artifact digests, and rejects duplicate immutable releases. The retrieval service resolves group members and returns stored artifacts only when authorization succeeds.

Synchronized service methods provide a simple single-instance concurrency boundary. They are not a substitute for database transactions or distributed coordination across several application instances. Holding a broad monitor during network I/O would also be undesirable; production code should keep critical sections narrow and separate transport calls from transactional state updates.

The Java proxy model explicitly reports that a network transport adapter is required on a cache miss. This keeps the domain service from pretending to retrieve a public dependency when it has no HTTP client implementation.

## PostgreSQL data model

The SQL script models repository metadata and operational evidence using relational tables.

### Repositories and permissions

`repositories` records the repository name, type, format, upstream URL, redeployment policy, deletion policy, and enabled state. Check constraints distinguish hosted, proxy, and group configuration. A proxy requires an HTTPS upstream URL, while non-proxy repositories cannot carry an upstream URL in this model.

`principals` represents users or service identities. `repository_permissions` associates a principal with a repository and stores separate read, publish, delete, and administrative privileges. This enables repository-specific access decisions rather than treating all authenticated users as equivalent.

The SQL constraints are necessary safeguards, but they do not implement a complete authorization service. Application or database procedures must still check the current principal and enforce the appropriate permission before allowing an operation.

### Coordinates and stored artifacts

`artifact_versions` stores logical package coordinates and canonical paths. A uniqueness constraint prevents duplicate logical coordinates within the modeled format and coordinate fields.

`artifacts` records the repository-specific instance, SHA-256 digest, size, origin, publisher, and verification timestamps. Its unique repository-coordinate constraint prevents the same logical coordinate from being inserted twice into one repository.

The distinction supports a common arrangement: one logical package version may be published internally and later appear in a cache or replicated repository. Each stored instance can have its own origin and verification metadata.

Large binaries are represented by size and digest metadata rather than stored directly in these tables. In production, the binary storage layer and the metadata database must remain consistent during upload, deletion, and cache population.

### Group membership and retrieval history

`repository_members` maps group repositories to their members and assigns an explicit priority. Foreign keys ensure that membership references existing repositories, while the self-membership constraint rejects direct cycles. The schema does not fully prevent multi-repository cycles, so a production service should validate the entire group graph when membership changes.

`artifact_retrievals` records successful cache hits, cache misses, not-found responses, denied requests, and other errors. This provides the data needed to investigate dependency resolution failures and measure cache behavior.

`repository_cache_metrics` aggregates retrieval outcomes by repository. Its counts support operational monitoring, but they are not a substitute for time-windowed metrics, latency measurements, or upstream availability monitoring.

### Integrity checks and audit events

`status_checks` stores results such as checksum verification, upstream availability, and release-policy validation. A window function selects the latest result for each artifact and check name.

`audit_events` records actions with their actor, repository, artifact coordinate, outcome, and structured event data. The indexed timestamps support incident investigation without requiring a full table scan for every repository-specific audit query.

The duplicate-publication example uses a savepoint and a PostgreSQL exception block to demonstrate database-level uniqueness enforcement. The transaction rolls back to the savepoint after the expected conflict and can continue without leaving a partial insertion.

The SQL script stores illustrative digest metadata. A real publishing service must calculate the digest from the uploaded bytes and ensure that the database record and binary storage operation commit consistently.

## Retrieval failures and operational behavior

Different failure types require different responses.

| Failure | Meaning | Appropriate operational response |
|---|---|---|
| Invalid coordinate | The requested package identity cannot be accepted | Reject the request before storage or network access |
| Authorization denied | The caller lacks permission for the requested repository operation | Return a controlled denial and record the event |
| Hosted artifact not found | The coordinate is absent from the selected hosted repository | Check the version, publishing destination, and repository configuration |
| Proxy upstream not found | The upstream does not contain the requested artifact | Inspect the coordinate and upstream metadata |
| Upstream unavailable | The upstream request failed due to a service or network problem | Preserve diagnostic details and apply bounded retry policies where appropriate |
| Checksum mismatch | Retrieved bytes differ from trusted integrity metadata | Reject the artifact and investigate storage, transport, or metadata integrity |
| Redeployment conflict | An immutable coordinate already exists | Publish a new release version or use an explicitly configured mutable repository |
| Group resolution failure | No eligible member returned the artifact | Inspect member order, formats, permissions, cache state, and upstream availability |

A repository manager should avoid converting every failure into a not-found result. Doing so hides outages and can cause a client to select a different source when it should instead stop the build.

## Performance and security considerations

Repository performance depends on cache-hit rate, artifact size, upstream latency, metadata lookup efficiency, and the number of repositories traversed by group resolution.

Frequently retrieved dependencies benefit from local proxy caching. Large artifacts should be streamed rather than loaded entirely into application memory. Pagination limits inventory requests, and database indexes should match the queries used to retrieve artifacts, review retrieval history, and inspect audit events.

Security requires more than checking a username. Repository permissions should be scoped by repository and operation. Release publication should use dedicated service identities, and credentials should not appear in upstream URLs or application logs. Upstream requests should use verified TLS connections, bounded timeouts, and controlled network destinations.

Artifact paths must be validated before being translated into storage keys. Package names and versions should not permit traversal outside the intended repository namespace. Checksums should be verified against trusted metadata, and publishing and deletion actions should be auditable.

A production deployment also needs backups, storage-capacity monitoring, retention rules, repository cleanup policies, and a recovery strategy for inconsistent binary and metadata state. The educational implementations focus on core repository semantics rather than reproducing every operational feature of a deployed Nexus Repository server.

## Practical interpretation

An internal release repository, an external dependency cache, and a group endpoint serve different responsibilities even when they expose related packages. Publishing establishes an artifact's identity and stored content. Retrieval resolves that identity through the configured repository topology. Permissions control who may perform each operation, while checksums and audit records help preserve integrity and traceability.

Keeping these responsibilities separate makes it easier to diagnose whether a failed build originates in package coordinates, publication policy, repository configuration, authorization, cache behavior, or upstream availability.

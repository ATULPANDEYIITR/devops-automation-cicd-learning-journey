# Docker Registry Governance and Image Publishing

## Purpose

This project models the lifecycle of container images from artifact preparation through publication, retrieval, and deployment eligibility. It distinguishes registry hosting, repository naming, image tags, immutable digests, access permissions, vulnerability scanning, signature verification, and build provenance.

The five implementations approach the same operational problem from different perspectives:

| File | Primary responsibility |
|---|---|
| Python | Simulate registry operations, permissions, publishing policies, and automated tests |
| JavaScript | Coordinate asynchronous publication and emit registry lifecycle events |
| C++17 | Evaluate publication eligibility and enforce registry governance rules |
| Java 17 | Model enterprise policy evaluation with immutable domain records and service boundaries |
| PostgreSQL | Persist registry metadata, authorization assignments, image evidence, policy decisions, and audit events |

The examples use synthetic registry names, credentials, manifests, and digests. They model the relevant workflows without connecting to a real registry or publishing actual container images.

## 1. Docker Registry Architecture

A Docker Registry stores and distributes container image content. Docker Hub is a hosted registry service. Private registries can be operated by an organization or provided through a cloud registry service.

A registry separates the logical name of an image from the content identified by its digest.

The main relationship is:

    Registry
      |
      +-- Repository
            |
            +-- Tag --------> Manifest
            |                   |
            |                   +-- Content digest
            |                   +-- Platform information
            |                   +-- Image layers and configuration
            |                   +-- Signature and provenance evidence
            |
            +-- Other tags ---> Other manifests or the same manifest

A repository groups related image artifacts. A tag is a human-readable reference that can point to a manifest. A digest identifies content by its cryptographic hash and is the stronger choice for verifying exactly which artifact is deployed.

A multi-platform image may use an image index that references different platform-specific manifests. The examples record platform metadata to make this distinction visible, but they do not implement the full OCI Distribution API or layer-transfer protocol.

### Registry and repository names

A registry hostname identifies the distribution service. A repository identifies an image collection within that registry.

Examples:

- `docker.io/library/nginx`
- `registry.example.com/commerce/orders-api`

A fully qualified image reference may also include a tag or digest:

- `registry.example.com/commerce/orders-api:v2.4.1`
- `registry.example.com/commerce/orders-api@sha256:...`

The examples validate simplified lowercase repository paths and standard tag characters. They deliberately do not attempt to implement every registry vendor's naming, authentication, or namespace rule.

## 2. Image Publishing Workflow

Publishing transfers a locally built image to a registry so other authorized systems can retrieve it.

    Build image
        |
        v
    Identify repository and tag
        |
        v
    Calculate or obtain manifest digest
        |
        v
    Authenticate publisher
        |
        v
    Evaluate publication policy
        |
        +---- Rejected: record failure
        |
        v
    Push manifest and image content
        |
        v
    Resolve published reference
        |
        v
    Deployment pulls approved image

A real publishing pipeline commonly performs the following operations:

1. Build an image from a reviewed source revision.
2. Tag the image with a meaningful release identifier.
3. Run tests and vulnerability scanning.
4. Verify signatures and build provenance where required.
5. Authenticate using a scoped, short-lived identity.
6. Push to the intended registry and repository.
7. Verify the resulting digest and deployment reference.
8. Record the result for auditing.

The implementations model publication checks and registry metadata. They do not build Docker images, upload layers, issue real registry tokens, or cryptographically verify external signatures.

### Tags and digests

Tags such as `latest`, `v2.4.1`, and `staging` are convenient labels. A tag can be reassigned unless the registry or its policy prevents reassignment.

A digest is content-addressed. If the image manifest changes, its digest changes as well. Deploying by digest avoids ambiguity about which manifest a mutable tag currently identifies.

Release-tag immutability is a governance rule rather than an intrinsic property of every registry tag. The examples prevent replacing a release tag with a different digest when the configured policy requires immutability. A real implementation should enforce this rule atomically in the registry or publishing service.

## 3. Access Control and Registry Visibility

Registry visibility and user permissions are separate controls.

| Role | Pull images | Publish images | Change governance |
|---|---:|---:|---:|
| Reader | Yes, subject to visibility | No | No |
| Publisher | Yes | Yes | No |
| Administrator | Yes | Yes | According to administrative policy |

A public repository may permit anonymous pulls while still requiring authentication to publish. A private repository requires an authorized identity for retrieval.

The examples use reader, publisher, and administrator roles. The Python and JavaScript versions use synthetic tokens for demonstration. The C++ implementation uses deterministic demo-token checks. The Java implementation compares configured token values using `MessageDigest.isEqual`.

These examples are not complete authentication systems. Production systems should use the registry's supported authentication mechanism, least-privilege credentials, protected secret storage, token rotation, audit trails, and narrowly scoped permissions.

Credentials must not be embedded in container images, committed to source control, or printed in logs.

## 4. Publication Policy and Security Evidence

A registry may accept an image only when required evidence is present and valid.

The modeled policy can require:

- An approved target registry.
- A publisher or administrator identity.
- A maximum manifest-size limit.
- A passing vulnerability scan.
- A verified image signature.
- Verified build provenance.
- Immutable release tags.

These conditions are independent. A valid publisher does not make an unsafe image acceptable, and a clean scan does not authorize an unprivileged reader to push.

### Vulnerability scanning

The scan state has three values:

| State | Meaning | Effect when a passing scan is mandatory |
|---|---|---|
| `PASS` | Required scan completed successfully | Eligible for this check |
| `FAIL` | Findings or policy failure block publication | Rejected |
| `UNKNOWN` | Evidence is missing or inconclusive | Rejected |

The PostgreSQL model records critical and high vulnerability counts and evaluates the latest scan result. It can also block images containing critical findings even if a scan record otherwise reports a passing status.

A production policy must define severity thresholds, exception handling, scan freshness, and how newly disclosed vulnerabilities affect previously published images.

### Signatures and provenance

A signature provides evidence that an artifact was signed by an expected identity. Provenance records how and from which source revision an artifact was built.

The examples represent verification outcomes as data. They do not implement signature cryptography, trusted-key discovery, provenance attestation formats, or verification against an external trust root.

In production, verification must validate the actual signature and attestation against an established trust policy. A Boolean flag supplied by an untrusted client is not sufficient security evidence.

## 5. Python: Repository Workflow Simulation

The Python script uses dataclasses and enums to define principals, image artifacts, publication policies, and check states.

The `Registry` class owns registered principals, published artifacts, and an audit log. Its `authenticate`, `push`, and `pull` methods implement the modeled workflow.

### Important mechanisms

- `Principal` combines a username, role, and hidden-from-representation demo token.
- `ImageArtifact` records repository, tag, digest, size, platform, and lifecycle state.
- `PublishPolicy` specifies allowed registries and publication constraints.
- `CheckState` distinguishes successful, failed, and unknown scan evidence.
- Custom exceptions separate validation, authentication, authorization, and release conflicts.
- `hashlib.sha256` derives a digest from the supplied demonstration manifest bytes.
- `secrets.compare_digest` compares token strings without ordinary early-exit string comparison.
- `unittest` exercises successful publishing, private pulls, role restrictions, scan failures, immutable tags, and invalid tags.

The `report` function aggregates the published image count, manifest-byte total, and audit-event count.

The artifact's size is the size of the supplied manifest bytes, not the compressed size of the complete image. A real registry must account for the actual uploaded content and its storage behavior.

## 6. JavaScript: Asynchronous and Event-Driven Publishing

The Node.js implementation uses `EventEmitter`, private class fields, `Map`, `Set`, `Promise`, and the standard `crypto` module.

The `Registry` class emits events when an image is published, pulled, or associated with an audit action. A caller can subscribe to these events without embedding notification logic in every registry operation.

### Event flow

    Publication request
          |
          v
    Validate principal and policy
          |
          v
    Check scan and signature evidence
          |
          v
    Store published reference
          |
          +---- emit "published"
          |
          +---- emit "audit"

The `publish` method is asynchronous and introduces a Promise boundary, allowing callers to coordinate publication with other asynchronous operations. It does not perform an actual network upload or concurrent remote verification.

Private fields protect internal maps from direct external mutation. Returned artifacts and policy objects are frozen to reduce accidental modification. The implementation also exposes copied audit events rather than its internal audit array.

The event-driven design makes it possible to connect successful publication to deployment orchestration, notifications, or inventory updates. Such integrations would require additional reliability controls, including durable event storage, retries, idempotency, and handling of duplicate events.

## 7. C++17: Registry Governance Engine

The C++ program emphasizes explicit eligibility evaluation and predictable control flow.

Its domain structures represent principals, artifacts, publication policies, review evidence, and eligibility results. The `Registry` class validates an artifact, checks publishing permissions, evaluates required security evidence, prevents prohibited release-tag reassignment, and records operations.

The `canPublish` method returns an `EligibilityResult` containing a Boolean decision and a list of reasons. This makes policy failures inspectable instead of collapsing them into a single success or failure message.

The program requires:

- An authorized publishing role.
- An approved registry.
- A valid repository, tag, digest, size, and platform.
- A passing scan when configured.
- Verified signature evidence when required.
- Verified build provenance.

The digest helper constructs a syntactically valid example digest from a supplied suffix. It is explicitly not a cryptographic hash implementation. Actual artifact digests must be computed with a cryptographically secure hash function over the correct content.

The deterministic demo-token check is also illustrative rather than suitable for production authentication.

The ordered `map` containers make registry reports deterministic and provide logarithmic lookup. A high-throughput registry service would need to evaluate its concurrency requirements and consider synchronization, persistence, and network-bound operations separately.

## 8. Java 17: Enterprise Domain and Policy Services

The Java implementation uses records for immutable domain data and interfaces for policy evaluation.

`Principal`, `ImageArtifact`, `ReviewEvidence`, `RegistryPolicy`, `AuditEvent`, and `Eligibility` express explicit data contracts. Constructors validate important invariants before the objects enter the service layer.

The `ImagePolicy` interface separates policy evaluation from registry storage. `DefaultImagePolicy` implements the publication checks, while `RegistryService` manages identity registration, publication, retrieval, audit events, and reporting.

This separation supports alternative policies without embedding all governance rules in the storage service.

### State and failure behavior

An artifact begins in the `BUILT` state. A successful publication creates a new immutable artifact value with the `PUBLISHED` state. A failed eligibility check raises a policy exception and leaves the image inventory unchanged.

The `evaluate` method returns structured reasons, making it suitable for displaying release-blocking conditions in a deployment interface or recording them for operational review.

The `publishedImages` method uses a stream to filter and sort published artifacts. `totalBytes` uses `mapToLong` for aggregation.

The service keeps data in memory. It does not provide durable transactions, distributed locking, database-backed authorization, or coordination between multiple registry service instances. A production implementation must address those concerns before treating eligibility decisions as authoritative.

## 9. PostgreSQL: Relational Registry Inventory

The SQL script creates the `registry_lab` schema and models registry metadata, authorization, artifacts, policy evidence, and publication outcomes.

### Relational structure

    registries
       |
       +-- registry_memberships ---- principals
       |
       +-- repositories
               |
               +-- image_manifests
               |       |
               |       +-- image_signatures
               |       +-- vulnerability_scans
               |       +-- build_provenance
               |
               +-- image_tags

    registry_policies
           |
           +-- publication_decisions
           |
           +-- publication_events

The tables preserve distinct responsibilities:

- `registries` identifies registry endpoints and visibility.
- `principals` stores identities without storing authentication tokens.
- `registry_memberships` assigns roles within individual registries.
- `repositories` identifies image collections.
- `image_manifests` records digests, sizes, media types, and platforms.
- `image_tags` maps human-readable tags to manifests.
- `image_signatures` records signature verification status.
- `vulnerability_scans` stores scan results and severity counts.
- `build_provenance` records source revisions and builder identity.
- `registry_policies` stores publication requirements.
- `publication_decisions` records eligibility and reasons.
- `publication_events` records successful or rejected operations.

Foreign keys preserve referential integrity. Unique constraints prevent duplicate registry hostnames, duplicate repository names within a registry, duplicate manifests within a repository, and duplicate tags within a repository. Check constraints reject invalid enum-like states, negative sizes, and malformed digest strings.

### Publication eligibility function

The `evaluate_publication` function checks whether a principal can publish a particular manifest to a repository under an active policy.

It evaluates:

1. Repository, policy, and manifest relationships.
2. Publisher or administrator membership.
3. Principal enabled status.
4. Maximum image size.
5. Latest vulnerability scan.
6. Critical vulnerability policy.
7. Verified signature evidence.
8. Verified build provenance.

The function returns an eligibility Boolean and an array of rejection reasons. Missing security evidence is treated as a failure when the corresponding policy requirement is enabled.

The function checks that the manifest belongs to the requested repository, preventing a caller from evaluating a manifest against an unrelated repository.

### Constraints and triggers

The `image_tags_immutable_guard` trigger prevents changing an immutable tag to a manifest with a different digest. It also prevents deleting immutable tags.

The trigger enforces the modeled rule within PostgreSQL. It does not prevent every possible race involving concurrent inserts, and it does not replace registry-side controls. Production deployment should use appropriate transaction isolation, database permissions, and atomic registry operations.

The SQL script uses `CREATE ... IF NOT EXISTS`, conflict-aware sample inserts, and a transaction to make initialization repeatable for the modeled dataset. The trigger is recreated explicitly. This is a learning schema rather than a versioned migration framework.

### Views, reporting, and CTEs

The `image_catalog` view combines tags, manifests, registry names, platform details, and the latest scan result.

The reporting queries demonstrate:

- Catalog retrieval.
- Policy eligibility and rejection reasons.
- Aggregated publication operations and manifest bytes.
- Latest scan state using `row_number()`.
- Reader authorization failure through the same eligibility function.

Indexes support event retrieval by repository and descending event time, tag lookup by manifest, and latest-scan lookup by manifest and timestamp.

The SQL script records decisions and events but does not implement a complete Docker Registry server. The modeled manifest sizes are metadata values, not a measurement of transferred image layers.

## 10. Docker Hub and Private Registry Operations

A typical command-line workflow uses the Docker client to build, tag, authenticate, push, and pull an image.

A registry-qualified tag identifies the destination repository. A successful push uploads the required image content and publishes the corresponding manifest. A pull retrieves the content associated with the selected reference.

Operational practices include:

- Use a dedicated repository for each independently managed image.
- Apply consistent tags for development, testing, and production.
- Prefer digest-pinned deployment references for release reproducibility.
- Keep publishing credentials separate from deployment credentials.
- Grant pull-only access to deployment identities when they do not need to publish.
- Enforce scanning and signature policies before release.
- Monitor failed authentication, denied pushes, and unexpected tag changes.
- Define retention and deletion policies appropriate to the registry.
- Test access and availability from the environments that build and deploy images.

Docker Hub and private registries can differ in namespace rules, authentication methods, access controls, retention features, rate limits, and policy capabilities. The common concepts in this project do not imply that every provider exposes identical enforcement mechanisms.

## 11. Failure Modes and Design Boundaries

| Failure | Modeled response | Operational implication |
|---|---|---|
| Invalid repository or tag | Validation rejection | Correct the image reference |
| Invalid credentials | Authentication rejection | Verify identity configuration and token scope |
| Reader attempts a push | Authorization rejection | Grant only the required publishing role |
| Registry is not approved | Policy rejection | Select an authorized destination |
| Scan fails or is unknown | Publication blocked | Resolve findings or obtain valid evidence |
| Signature is not verified | Publication blocked | Verify the artifact's trusted signer |
| Provenance is missing | Publication blocked where required | Validate build origin and source revision |
| Image exceeds configured size | Publication blocked | Review the artifact and policy limit |
| Immutable release tag is reassigned | Conflict rejection | Publish a new release tag |
| Manifest reference is absent | Pull failure | Verify publication and reference resolution |

The implementations are deliberately limited in several ways:

- Registry authentication and remote authorization are simulated.
- Signature and provenance evidence are represented as records or flags.
- Vulnerability scans are supplied as input rather than run against actual image layers.
- Image sizes represent manifest metadata in the examples.
- Registry content storage, layer deduplication, replication, and garbage collection are not implemented.
- No OCI Distribution API client or server is included.
- The in-memory implementations do not provide durable state across process restarts.
- The SQL schema does not independently enforce every publication decision at the remote registry.

These boundaries distinguish an executable governance model from a complete registry implementation. A real deployment must enforce access and integrity controls at the systems that actually authenticate clients, store artifacts, and serve image content.

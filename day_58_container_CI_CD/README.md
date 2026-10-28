# Container CI/CD: Build, Test, Scan and Publish Docker Images

## Scope

This project models a production-oriented container CI/CD workflow in five implementation environments:

| File | Primary perspective | Main responsibility |
|---|---|---|
| Python | Pipeline orchestration | Builds, tests, scans, fingerprints, and optionally publishes an image |
| JavaScript | Event-driven pipeline | Adds asynchronous command execution, event listeners, policy validation, and isolated test execution |
| C++17 | Governance engine | Evaluates image, test, security, registry, and publication conditions through explicit state transitions |
| Java 17 | Enterprise domain model | Separates pipeline state, policies, checks, image metadata, validation, and publication services |
| PostgreSQL | Persistent workflow model | Stores repositories, branches, commits, pipeline runs, checks, findings, publication records, and state history |

The implementations describe the same operational domain from different engineering perspectives rather than translating one program line by line into five languages.

## CI/CD Workflow

The core workflow is:

`source commit -> container build -> application tests -> image security scan -> image validation -> immutable digest -> registry publication`

A publication must not be treated as an independent Docker push. It is the final action in a controlled sequence.

The important distinction is between the stages:

- **Build** creates a container image from a source context and Dockerfile.
- **Test** validates application behavior using the generated image.
- **Scan** evaluates the image for security findings before distribution.
- **Validation** checks repository, tag, digest, registry, and credential requirements.
- **Publish** transfers an approved image to the container registry.
- **Digest tracking** identifies the resulting image independently of a mutable tag.

A failed prerequisite stops later stages.

## Container Image Identity

An image reference normally combines a registry, repository, and tag:

`registry.example.com/platform/payments-api:2026.10.28-9c1e7f2`

The tag is convenient for humans and deployment automation, but it should not be treated as the strongest identity of an image. Tags can be reassigned. A content digest provides immutable identification:

`registry.example.com/platform/payments-api@sha256:...`

The implementations therefore require a digest before publication.

The Python and JavaScript implementations calculate a local fingerprint for pipeline traceability when a registry digest is not yet available. The C++ and Java implementations explicitly document that their portable fingerprints are case-study representations and that a production registry should provide a real SHA-256 content digest.

## Build Stage

The build stage validates the Docker context and Dockerfile before invoking Docker.

The Python implementation uses `docker build --pull` and tags the resulting image. `--pull` requests fresh base-image metadata, which helps reduce the chance of building from an unexpectedly stale base image.

The JavaScript implementation performs filesystem validation asynchronously before starting the Docker build. It uses `spawn` with `shell: false`, avoiding shell interpretation of arguments supplied to the command runner.

The C++ and Java programs model the build as an explicit domain state transition. This makes the ordering requirement visible without requiring a Docker daemon for the executable case studies.

A valid transition is:

`CREATED -> BUILT`

A direct transition from `CREATED` to `PUBLISHED` is invalid.

## Testing Containers

Testing the built image rather than only the host checkout improves confidence that the artifact being distributed can execute its tests.

The Python example starts the image with:

`python -m unittest discover -s /app/tests`

The JavaScript example starts the container with Node's built-in test runner.

The JavaScript runtime also uses `--read-only` and `--cap-drop=ALL` for the test container. These settings reduce the privileges available to the test process and make accidental filesystem mutation less likely.

A real pipeline can use a more extensive test matrix covering unit tests, integration tests, API contracts, database migrations, and application startup behavior. The essential control is that test failure prevents the publication stage.

## Security Scanning

Image scanning is a separate CI/CD concern from application testing.

Application tests answer questions such as whether expected behavior works. Image scanning examines the assembled container artifact and its installed operating-system packages, libraries, and other components for known vulnerabilities.

The Python implementation invokes a Trivy-compatible scanner and treats high or critical findings as blocking.

The JavaScript implementation uses the scanner configured by `CONTAINER_SCANNER`, defaulting to `trivy`.

The C++ implementation represents security scanning as a policy check. A mutable `latest` tag is rejected, and a successful security check is required before publication.

The Java implementation separates image scanning into `ImageScanPolicy`, allowing security policy behavior to remain independent from the pipeline state machine.

The PostgreSQL model persists individual findings with severity and resolution state. Unresolved `high` and `critical` findings therefore remain queryable after the pipeline finishes.

## Image Tags and Immutability

The examples reject:

- `latest`
- `prod`
- `production`

as publication tags.

The reason is governance rather than syntax. A mutable tag can point to a different image at a later time. A release process that records only the tag cannot reliably prove which bytes were deployed.

A stronger publication record contains:

- repository
- tag
- registry
- immutable digest
- publication time
- source commit

A practical production tag can combine a release identifier and commit identifier, such as:

`2026.10.28-9c1e7f2`

The digest should still be retained as the authoritative image identity.

## Pipeline State Management

The Python implementation uses the `PipelineState` enum:

`CREATED -> BUILT -> TESTED -> SCANNED -> PUBLISHED`

Failures transition the pipeline to `FAILED`.

The Java and C++ implementations make invalid state transitions explicit failures. This prevents operations such as publishing an image before security scanning.

The PostgreSQL implementation uses a PostgreSQL enum for persistent pipeline state and records transitions in `pipeline_events`.

The database trigger captures:

- previous state
- new state
- pipeline identifier
- transition message
- timestamp

This creates an operational audit trail without requiring every application caller to implement its own history mechanism.

## Python Implementation

The Python file is a self-contained orchestration example.

### `ImageConfig`

`ImageConfig` is an immutable dataclass containing:

- image repository
- tag
- build context
- Dockerfile
- registry

Validation occurs before Docker commands are executed.

### `CommandRunner`

`CommandRunner` centralizes subprocess execution. It captures combined command output and raises `PipelineError` for non-zero exit codes.

This gives the pipeline a single failure boundary for Docker and scanner operations.

### `DockerPipeline`

The pipeline exposes separate operations:

- `build()`
- `test()`
- `scan()`
- `inspect_digest()`
- `publish()`
- `run()`

`run()` controls ordering and converts failures into a failed pipeline result.

The default execution path creates a temporary demonstration project, allowing the script to exercise its workflow without requiring a user-created application directory.

Publishing requires `--publish`, preventing an accidental registry push during the basic demonstration.

### Failure handling

The result contains:

- final state
- image reference
- fingerprint
- failure findings

A failed external command terminates the workflow and is surfaced through the result.

## JavaScript Implementation

The JavaScript file emphasizes asynchronous execution and event-driven state reporting.

### `CommandRunner`

Node's `child_process.spawn` is used instead of shell string execution.

Arguments are supplied as an array and `shell: false` is explicitly configured. This avoids unnecessary shell parsing and reduces command-injection risk.

### `ImagePolicy`

`ImagePolicy` validates:

- repository naming
- tag syntax
- registry syntax
- blocked mutable tags

The policy runs before pipeline execution.

### Events

The pipeline maintains a `Map` of event names to `Set` objects containing callbacks.

The `stateChanged` event reports transitions such as:

`created -> built -> tested -> scanned`

A failed event listener does not silently terminate the pipeline. Its error is recorded in the pipeline findings.

### Container test isolation

The test stage uses:

`--read-only`

and:

`--cap-drop=ALL`

This makes the example more restrictive than a basic `docker run` workflow.

## C++17 Governance Engine

The C++ implementation treats CI/CD as a governance decision system.

### Domain structures

The main domain objects are:

- `Image`
- `StatusCheck`
- `PipelineContext`
- `MergeEligibilityEngine`
- `ContainerPipeline`

`PipelineState` and `ReviewStatus` are strongly typed enums.

### State machine

The pipeline enforces expected predecessor states through `require()`.

For example, testing requires `Built`, and scanning requires `Tested`.

This prevents invalid workflow ordering.

### Eligibility engine

`MergeEligibilityEngine` checks:

- project identity
- source branch
- source commit
- image repository
- image tag
- unit tests
- security scan
- image digest
- registry reachability
- credentials when publication is requested

The eligibility logic is independent from the pipeline's execution methods. This separation makes policy changes easier to reason about.

### Performance characteristics

Status checks are stored in a vector because the example contains a small number of checks and prioritizes simple sequential evaluation.

Policy checks are linear in the number of stored checks.

For a production implementation with thousands of checks, an indexed structure such as `std::unordered_map` keyed by check name would reduce repeated scans.

## Java 17 Enterprise Model

The Java implementation uses explicit domain types and policy objects.

### Records

The following records represent immutable domain data:

- `Image`
- `StatusCheck`
- `PipelineRequest`

Records reduce accidental mutation of configuration and check information.

### Policy interface

`CheckPolicy` defines a common policy contract.

Two concrete policies are:

- `UnitTestPolicy`
- `ImageScanPolicy`
- `ImageMetadataPolicy`

This makes the validation rules composable.

### Pipeline service

`Pipeline` controls state transitions and owns the check results.

The sequence is:

`CREATED -> BUILT -> TESTED -> SCANNED -> PUBLISHED`

A policy failure moves the pipeline to `FAILED`.

### Merge eligibility

`MergeEligibilityService` evaluates the result of completed checks rather than directly executing Docker operations.

This distinction separates:

- artifact construction
- quality validation
- security policy
- publication authorization

That separation is useful in enterprise CI/CD systems where different teams may own different controls.

## PostgreSQL Data Model

The database models the persistent operational state.

The main relationship is:

`Repository -> Branch -> Commit -> Pipeline Run -> Checks -> Findings -> Publication`

Pipeline state history is stored separately through `pipeline_events`.

### Repositories

`repositories` stores the logical repository and its default branch and registry.

### Branches

`branches` associates branches with repositories and stores the current commit SHA.

A `protected` flag identifies branches that are subject to repository governance.

### Commits

`commits` stores the source revision associated with the pipeline.

This allows an image publication to be connected to a specific source revision.

### Pipeline runs

`pipeline_runs` stores:

- source branch
- commit
- pipeline state
- image repository
- image tag
- image digest
- execution timestamps

### Checks

`pipeline_checks` records named checks such as:

- `unit-tests`
- `security-scan`

Each check has an explicit `pending`, `passed`, or `failed` state.

### Findings

`image_findings` records individual vulnerabilities rather than storing only a single scan result.

Each finding contains:

- package
- severity
- fixed version
- description
- resolution state

This supports later reporting and remediation tracking.

### Publications

`registry_publications` records the immutable digest and registry associated with a successful publication.

A unique constraint on `pipeline_id` prevents a pipeline from receiving multiple publication records.

## Database Enforcement

Important publication requirements are enforced by PostgreSQL rather than relying exclusively on application code.

The `prevent_unsafe_pipeline_state` trigger prevents a pipeline from entering `published` state unless:

- an image digest exists
- unit tests passed
- the security scan passed
- no unresolved high or critical findings remain

This is important because database enforcement protects the workflow even if another application or administrative SQL session attempts an invalid state transition.

## Transactional Publication

`publish_pipeline()` evaluates eligibility and then changes the pipeline state and inserts the publication record.

The example executes the clean publication inside a transaction.

A second transaction attempts publication for a pipeline with a failed security scan. The publication is rejected and the transaction is rolled back.

This preserves the relationship between pipeline state and publication history.

## Relational Queries

The `pipeline_eligibility` view combines:

- pipeline state
- source repository
- source branch
- image metadata
- test result
- security result
- blocking vulnerability count

This converts multiple low-level records into an operational eligibility result.

The reporting queries then support:

- pipeline counts by repository and state
- unresolved blocking findings
- pipelines that cannot be published
- pipeline state transitions

## Failure Conditions

The implementations intentionally treat several conditions as blocking failures.

| Failure | Effect |
|---|---|
| Invalid repository name | Pipeline does not start |
| Invalid image tag | Pipeline does not start |
| Missing Dockerfile | Build fails |
| Docker build failure | Later stages do not execute |
| Application test failure | Scan and publication are blocked |
| Scanner failure | Publication is blocked |
| High or critical unresolved finding | Publication is blocked |
| Missing digest | Publication is blocked |
| Missing registry credentials | Publication is blocked |
| Registry unavailable | Publication is blocked |
| Mutable production-style tag | Policy rejects publication |

The objective is fail-closed behavior for release-critical controls.

## Security Controls

The examples use several complementary controls.

### Input validation

Repository and tag values are validated before external commands are executed.

### Shell avoidance

The JavaScript command runner uses direct process execution rather than concatenating shell commands.

### Scanner enforcement

The scanner is not silently skipped. A scanner failure is treated as a pipeline failure.

### Least privilege for test containers

The JavaScript test container uses a read-only filesystem and drops Linux capabilities.

### Immutable release identity

Publication requires a digest.

### Credential separation

Registry credentials are treated as an external prerequisite. They are not stored in source code or printed by the examples.

### Database enforcement

The PostgreSQL trigger prevents invalid publication state transitions even when the database is accessed outside the main application.

## Performance Considerations

Container builds are often the most expensive stage.

A production CI system should therefore use Docker layer caching where the security model and runner architecture permit it.

The examples use `--pull` to refresh base-image information, which can increase build work when base images change. This is a deliberate freshness trade-off.

Security scanning can also become expensive for large images. Keeping images small reduces scan scope, transfer size, startup time, and vulnerability surface.

Database indexes are limited to queries that naturally filter or group on:

- repository and pipeline state
- pipeline check status
- unresolved vulnerability severity

The PostgreSQL view aggregates pipeline checks and findings rather than repeatedly reconstructing eligibility logic in every reporting query.

## Operational Traceability

A useful container release should be traceable in both directions:

`source commit -> pipeline -> image tag -> image digest -> registry publication`

and:

`registry digest -> publication -> pipeline -> source commit`

The PostgreSQL schema supports this relationship through foreign keys and publication records.

The application implementations preserve the same conceptual chain through pipeline context and image metadata.

## Practical Pipeline Contract

A production-oriented container CI/CD contract represented by these artifacts is:

1. Identify the source commit.
2. Validate the build context and image metadata.
3. Build the image.
4. Execute tests using the built artifact.
5. Scan the artifact for security issues.
6. Reject mutable release tags.
7. Obtain and retain an immutable digest.
8. Verify registry access and credentials.
9. Publish only after every required check succeeds.
10. Persist the resulting state and publication identity.

This separates artifact creation from artifact approval and artifact publication.

## Limitations

The executable examples intentionally avoid pretending that a local case study is a complete production platform.

The Python and JavaScript programs invoke real Docker and scanner commands when pointed at an actual project, but their demonstration projects are intentionally small.

The C++ and Java programs model CI/CD governance without requiring Docker, making them suitable for studying state transitions and policy behavior independently of infrastructure.

The C++ and Java fingerprint calculations are not substitutes for a registry-provided cryptographic image digest.

The PostgreSQL model represents pipeline and registry state but does not itself execute Docker builds or security scanners. External CI workers are expected to write their results into the relational model.

A complete production platform would also need controlled secret management, runner isolation, artifact retention policies, registry access controls, cache governance, dependency policy, deployment environments, observability, and organizational approval rules.

# Dockerfile Optimization: Layers, Caching, and Smaller Images

## Purpose

This project models practical Dockerfile optimization decisions around three closely related objectives:

- reducing the size of the final container image
- preserving useful build-cache reuse
- reducing the amount of data sent as the Docker build context

The implementations use different perspectives rather than translating the same program between languages.

| File | Perspective | Main technical focus |
|---|---|---|
| Python | Build optimization simulator | Layer modeling, context reduction, cache reuse, validation |
| JavaScript | Event-driven policy model | Asynchronous policy evaluation, cache analysis, validation |
| C++17 | Governance engine | Policy enforcement, structured image evaluation, performance-oriented modeling |
| Java 17 | Enterprise governance model | Domain types, immutable records, policy services, CI publication gate |
| PostgreSQL | Relational governance system | Image stages, layers, cache metadata, policies, validation functions and reporting |

The central optimization principle is that Dockerfile structure affects both the final artifact and the amount of work Docker must repeat after a source change.

---

## Dockerfile Optimization Model

A Docker image can be viewed as a sequence of filesystem layers produced by build instructions.

A simplified dependency relationship is:

`Base image → dependency inputs → dependency installation → application source → runtime configuration`

The ordering is important.

If application source is copied before dependency metadata, a small source change can invalidate a later dependency-installation layer. When dependency metadata is copied first, source-only changes can preserve the expensive dependency layer.

The examples model this distinction explicitly.

### Layer optimization

A layer should contain work that has a sensible cache boundary.

For example, a Python service commonly benefits from separating:

- the runtime base
- dependency metadata such as `requirements.txt` or a lock file
- dependency installation
- application source
- runtime-only configuration

A Node.js service commonly uses the equivalent pattern with `package.json` and `package-lock.json`.

Layer optimization does not mean minimizing the number of Dockerfile instructions at any cost. Combining unrelated operations into a single instruction can make cache invalidation less precise and can reduce maintainability. The useful objective is to establish appropriate cache boundaries while avoiding unnecessary filesystem content.

---

## Build Cache Behavior

Docker's build cache associates build operations with their inputs. When an instruction and its relevant inputs remain unchanged, cached results can often be reused.

Consider these conceptual arrangements:

`COPY application .`

followed by

`RUN install dependencies`

This arrangement makes application changes relevant to the later dependency installation.

A more cache-friendly arrangement is:

`COPY dependency metadata`

then

`RUN install dependencies`

then

`COPY application source`

The dependency installation now depends primarily on dependency metadata rather than every source file.

The Python, JavaScript, C++, and Java implementations model stable dependency cache keys and distinguish them from frequently changing application-source keys.

### Cache invalidation

Cache reuse is not guaranteed merely because Dockerfile instructions look similar. Relevant build inputs include files copied into a layer, instruction arguments, base-image changes, build arguments, platform differences, and other build configuration.

A cache strategy therefore needs stable inputs rather than simply fewer instructions.

---

## Build Context and `.dockerignore`

The Docker build context is the set of files made available to the build process.

A repository can contain files that are unnecessary for an image build:

- `.git` metadata
- local virtual environments
- dependency caches
- test artifacts
- coverage reports
- editor configuration
- generated development files
- local credentials
- operating-system metadata

A `.dockerignore` file prevents selected content from becoming part of the build context.

The project models context reduction numerically. For example, an input repository may have a 420 MB context while only 125 MB is relevant to the build. Ignoring 295 MB produces an effective context of 125 MB.

The important distinction is that `.dockerignore` reduces build-context transfer and exposure. It does not remove files that were already explicitly copied into an image layer.

---

## Multi-Stage Builds

Multi-stage builds separate build-time requirements from runtime requirements.

A conceptual architecture is:

`builder stage → compiled or packaged artifact → runtime stage`

The builder may contain:

- compilers
- development headers
- package managers
- source code
- test dependencies
- build tooling

The runtime image should contain only what is necessary to execute the application.

The C++ and Java implementations treat build tooling as an explicit policy violation when it remains in the runtime image. The PostgreSQL model records build-only layers and runtime stages separately.

Multi-stage builds are particularly useful when build tools are large but runtime execution requires only their output.

---

## Python Implementation

The Python program defines `Layer`, `DockerfileModel`, and `BuildCache` objects.

`Layer` records:

- layer name
- approximate size
- cache key
- whether the operation is expensive

`DockerfileModel` calculates:

- modeled image size
- effective build context
- layer count

Validation rejects negative sizes, invalid context relationships, empty names, and missing cache keys.

The program compares a naive single-stage model with an optimized multi-stage model. It also calculates cache reuse against a set of previously available cache keys.

The simulation deliberately distinguishes measured quantities from real Docker behavior. The reported image sizes are models rather than actual registry or filesystem measurements.

The production-oriented checks cover stable dependency ordering, build-context reduction, runtime separation, cache cleanup, reproducibility, and secret exclusion.

---

## JavaScript Implementation

The JavaScript implementation uses Node.js standard-library functionality and an asynchronous policy evaluator.

`Layer` validates layer metadata before accepting it.

`DockerImage` calculates image and effective-context sizes through class properties. This makes the derived values unavailable for accidental mutation.

`CacheSimulator` uses a `Set` to provide efficient cache-key lookup.

The `evaluateBuildPolicy()` function uses `setImmediate()` to model a build-policy operation that participates in an event-driven Node.js workflow. A real implementation could replace this stage with asynchronous build metadata collection or CI-service API calls.

The program validates:

- context reduction
- absence of compiler layers in the modeled runtime
- dependency-before-source ordering

Assertions ensure that the expected optimization actually produces a smaller model rather than merely being called optimized.

---

## C++17 Implementation

The C++ implementation treats optimization as a governance problem.

`ImageModel` owns immutable-style image configuration through private state and exposes controlled queries for image size, context size, and layers.

`CacheIndex` uses `std::set` to model reusable cache keys.

`BuildPolicy` contains explicit limits for:

- runtime image size
- build context size
- stable dependency ordering
- runtime exclusion of build tooling

`MergeEligibilityStyleEngine` evaluates an image against these rules. The name emphasizes that the mechanism resembles a policy gate: an artifact is accepted only when all required conditions are satisfied.

The implementation compares a correctly ordered image against a poorly ordered image.

The correctly ordered version places the dependency layer before application source. The poorly ordered version places source before dependencies, which represents a less useful cache boundary.

The C++ program also models compiler tooling as a build-only resource. Retaining it in the runtime image can increase image size and attack surface.

The relevant operations are linear in the number of image layers for the modeled checks. Cache-key lookup is logarithmic with the chosen `std::set` structure.

---

## Java 17 Enterprise Model

The Java implementation models Docker optimization as a CI governance service.

The domain types distinguish:

- `LayerRole`
- `Violation`
- `ImageLayer`
- `BuildContext`
- `GovernancePolicy`
- `RepositoryImage`
- `GovernanceReport`

Java records provide compact immutable domain representations. Defensive copying of layer collections prevents callers from changing an image after policy validation has begun.

`ImagePolicy` is an interface so different enterprise policies can be introduced without coupling the build pipeline to one validation implementation.

`EnterpriseImagePolicy` evaluates:

- maximum runtime image size
- maximum build context size
- build-tool exclusion
- dependency ordering
- dependency cache-key stability

`BuildPipeline` converts policy evaluation into a CI-style report.

A publication gate is then applied to the optimized `billing-service` image. The same policy rejects the deliberately poorly optimized image.

This separation is useful in enterprise environments because optimization rules can be treated as governance rather than informal Dockerfile conventions.

---

## PostgreSQL Model

The SQL implementation treats container-build metadata as relational data.

### Core entities

`docker_images` stores repository, tag, and build-context information.

`image_stages` distinguishes builder and runtime stages.

`image_layers` records:

- layer order
- role
- approximate size
- cache key
- cache stability
- build-only status

`optimization_policies` stores organizational limits.

`optimization_violations` records policy failures as durable audit data.

The relationships are:

`docker_images → image_stages → image_layers`

and:

`optimization_policies → optimization_violations ← docker_images`

This structure allows one image to contain multiple stages while each stage contains an ordered sequence of layers.

---

## PostgreSQL Constraints

The schema uses database-level integrity enforcement rather than relying entirely on application validation.

Examples include:

- non-negative context sizes
- ignored context cannot exceed total context
- positive stage and layer ordering
- valid layer roles
- unique repository/tag combinations
- unique stage names within an image
- unique layer positions within a stage

The `set_updated_at()` trigger maintains modification timestamps.

The indexes target actual access patterns:

- runtime-stage lookup
- layer-role lookup
- cache-key lookup
- violation lookup by image

---

## SQL Validation Workflow

`calculate_image_size()` calculates the size of runtime layers rather than builder-only layers.

`validate_docker_image()` checks the selected policy against an image.

The function can report:

- excessive runtime image size
- excessive build context
- dependency layers placed after application layers
- build tooling retained in runtime
- unstable dependency cache keys

The validation results are inserted into `optimization_violations` inside a transaction.

This provides an auditable record of why an image failed the policy at the time it was evaluated.

The views provide operational reporting without requiring each query to reconstruct the layer relationships.

---

## Optimization Trade-offs

| Technique | Primary benefit | Important trade-off |
|---|---|---|
| `.dockerignore` | Smaller build context | Incorrect exclusions can remove required build inputs |
| Dependency-first copying | Better cache reuse | Requires deliberate Dockerfile ordering |
| Multi-stage builds | Smaller runtime image | Requires explicit artifact transfer between stages |
| Smaller base image | Reduced image footprint | Compatibility and debugging may become harder |
| Removing package caches | Smaller layers | Package installation must still remain reproducible |
| Layer separation | Precise cache boundaries | Excessive fragmentation can reduce clarity |
| Combining commands | Potentially fewer persisted artifacts | Can make cache invalidation less precise |
| BuildKit cache mounts | Faster repeated builds | Cache configuration becomes part of build infrastructure |
| Pinned dependencies | Reproducibility | Updating dependencies becomes an explicit maintenance task |

---

## Security Considerations

Image-size optimization is also related to security, but a smaller image is not automatically a secure image.

Build contexts should not contain secrets such as:

- private keys
- access tokens
- local credential files
- cloud credentials
- `.env` files containing sensitive values

A secret copied into an image layer can remain recoverable from image history or intermediate layers even if the visible filesystem is later changed.

Build secrets and appropriate BuildKit mechanisms should be used when a build genuinely needs secret material.

Build-only dependencies should normally remain outside the runtime image. Removing unnecessary compilers and development packages reduces both image size and the number of installed components that need security maintenance.

Base-image selection also requires verification of supported architecture, update policy, runtime compatibility, and vulnerability posture.

---

## Reproducibility

Optimization should not sacrifice reproducibility.

A useful build should make its important inputs explicit:

`Base image + dependency definition + lock information + source + build configuration → runtime artifact`

Lock files are particularly valuable for dependency layers because they create stable and auditable inputs.

Tags alone may not provide strong immutability guarantees. Production workflows can use immutable image references or digests where appropriate.

Optimization measurements should distinguish:

- local uncompressed layer size
- compressed registry size
- build context size
- transferred cache data
- total build time
- cache-hit behavior

A change that reduces image size but causes every dependency layer to rebuild may not improve the actual engineering workflow.

---

## Performance Evaluation

The implementations intentionally measure several different quantities instead of treating image size as the only optimization target.

The most useful metrics are:

| Metric | What it indicates |
|---|---|
| Runtime image size | Deployment storage and transfer cost |
| Effective build context | Amount of input sent to the build |
| Stable dependency layers | Potential reuse after source changes |
| Cache-hit rate | Amount of previously completed work reusable |
| Build-tooling size | Cost of retaining build dependencies |
| Layer count | Structural complexity, not a direct optimization target |

For real Docker builds, these modeled values should be validated against actual build output and cache statistics.

A smaller image is valuable, but an optimization is strongest when it simultaneously reduces unnecessary content, preserves useful cache boundaries, keeps builds reproducible, and avoids placing development tooling or secrets in the runtime artifact.

---

## Practical Dockerfile Structure

A maintainable optimized Dockerfile commonly follows this conceptual structure:

`minimal runtime/base selection`

`dependency metadata`

`dependency installation`

`application source`

`runtime configuration`

For compiled applications, the structure commonly becomes:

`builder base`

`dependency metadata`

`dependency installation`

`source`

`build artifact`

`minimal runtime base`

`copy artifact from builder`

The exact structure depends on the language, framework, package manager, native dependencies, and runtime requirements. The correct objective is not to minimize instructions mechanically. It is to establish useful cache boundaries and ensure the final image contains only the components required for execution.

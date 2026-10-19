# Docker Images: Layers, Caching, Tags, and Image Lifecycle

## Scope

A Docker image is a content-addressed package assembled from filesystem layers and image metadata. The four areas covered here are closely related but represent different mechanisms:

- **Image layers** describe how filesystem changes are stored as reusable immutable building blocks.
- **Caching** determines whether a build step can reuse a previously produced layer rather than executing the step again.
- **Tags** provide mutable human-readable references to image identities such as `payments-api:1.1.0` or `payments-api:production`.
- **Image lifecycle** covers creation, local use, publication, promotion through tags, retirement, and eventual removal of content that is no longer referenced.

The implementations deliberately approach these mechanisms from different technical perspectives rather than presenting the same example in five programming languages.

## Image Layers

A Docker image is represented by an ordered collection of layers. A typical build might conceptually produce:

`base image → dependency installation → application files → runtime configuration`

A layer records a filesystem change associated with a Dockerfile instruction. Layers are identified by content-derived digests rather than by ordinary sequential names.

The important distinction is between the instruction that created a layer and the layer's resulting content. A Dockerfile line such as `RUN npm ci --omit=dev` describes an operation, while the resulting layer contains the filesystem changes produced by that operation.

The Python model represents a layer with a digest, parent digest, instruction, size, and creation time. The parent relationship makes the ordered construction visible. The C++ implementation uses the same core idea in a repository-oriented engine but emphasizes deterministic identity and storage accounting.

The SQL implementation stores layers separately from image manifests. `image_layers` contains the reusable layer records, while `image_manifest_layers` associates those layers with an image and preserves their order through `layer_order`.

This separation is important because two images can share a layer. A base image or dependency layer does not need to be represented as an entirely independent copy for every image that uses it.

## Layer Sharing and Image Size

The apparent size of an image and the amount of unique storage required by a collection of images are different questions.

Suppose two images contain:

`base → dependencies → application-v1`

and

`base → dependencies → application-v2`

The two application layers differ, but the base and dependency layers can be shared.

The SQL query that groups `image_manifest_layers` by layer digest identifies layers referenced by multiple images. This exposes the storage-sharing relationship directly.

The Python program performs logical layer-size accounting. It does not attempt to reproduce Docker's exact compressed blob accounting because actual Docker storage depends on the engine's storage driver, compressed registry representation, local metadata, and other implementation details.

## Caching

Build caching is not simply a global "same Dockerfile means same result" mechanism. A build step depends on the state available to that step, including the relevant instruction and build inputs.

The Python implementation constructs a cache key from:

`parent layer + instruction + input fingerprint`

This makes cache invalidation visible.

If the application source changes only at a final `COPY` operation, earlier base and dependency layers remain reusable. If a dependency file changes, the dependency installation step must be reconsidered, and later layers normally cannot reuse results that depended on the previous dependency state.

The Python program explicitly contrasts these cases.

The JavaScript implementation uses asynchronous `setImmediate` scheduling and `EventEmitter` events to expose cache activity as an event-driven workflow. `cache-hit`, `layer-created`, `image-built`, `tag-moved`, and `pushed` events provide a useful operational view of what happens during a build.

The SQL implementation records cache keys, input fingerprints, resulting layers, and build-step outcomes. This makes cache behavior queryable rather than treating it as an invisible implementation detail.

## Cache-Friendly Dockerfile Ordering

Instruction ordering affects the practical value of caching.

A stable dependency installation step is generally more reusable when it appears before frequently changing application source:

`COPY dependency metadata → install dependencies → COPY application source`

A source change then invalidates the application layer without necessarily invalidating dependency installation.

The opposite ordering can cause frequent application changes to occur before an expensive dependency step, reducing the amount of work that can be reused.

The Python function `demonstrate_cache_ordering()` measures this effect in the model. It deliberately changes the application input and compares dependency-first and application-first instruction arrangements.

This is not a claim that every Dockerfile should have one universal ordering. Build inputs, security requirements, package managers, generated artifacts, secret handling, and application architecture can alter the optimal arrangement. The underlying principle is to isolate stable expensive operations from frequently changing inputs when that separation accurately represents the build.

## Tags

A tag is a mutable reference, not an immutable identity.

For example:

`payments-api:production`

may point to one image today and another image after a deployment.

The image digest remains the identity of the referenced image. The tag provides a convenient name that can be moved.

The Python implementation makes this distinction explicit through separate `images` and `tags` collections. The JavaScript implementation exposes tag movement through the `tag-moved` event. The Java implementation stores tags separately from image objects and permits `candidate` or `production` to be moved to another image.

The SQL schema uses `image_tags` as a separate table with a uniqueness rule on `(repository_id, tag)`. Updating that row changes the image associated with the tag without changing the underlying image identity.

This distinction matters for release operations. A deployment record that stores only `production` does not identify exactly which image was deployed if the tag later moves. Recording an immutable digest provides stronger traceability.

## Tag Promotion

A useful lifecycle is:

`build image → assign version tag → test candidate → promote tag → publish or deploy`

A version tag such as `1.1.0` can remain associated with a specific image while a mutable tag such as `production` moves as releases are promoted.

The Java implementation models this through `ImageRepository.moveTag()` and `publish()`. The SQL implementation performs tag operations through the `tag_image()` function and records lifecycle events.

The examples keep tagging distinct from caching. Caching answers whether a build operation can reuse existing work. Tagging answers which image identity a human-readable reference currently denotes.

## Image Lifecycle

The Python model represents a practical lifecycle:

- An image is created from a sequence of layers.
- Tags are attached to the image.
- A registry reference can identify a published image.
- Tags can be removed or moved.
- An unreferenced image can become eligible for retirement.
- Unreferenced layers can become garbage-collection candidates.

The Java implementation adds explicit `ImageState` values of `LOCAL`, `PUBLISHED`, and `RETIRED`. Its lifecycle service prevents retirement while an image is still referenced by a tag.

The SQL model records lifecycle events in `image_lifecycle_events`, allowing operations such as creation, tagging, publication, and retirement to be audited.

Actual Docker garbage collection is more complex than deleting rows from an application database. A Docker Engine also considers containers, image references, build cache, storage-driver behavior, and other resources. A registry has its own retention and garbage-collection model.

## Multi-Stage Builds

The Python implementation includes a multi-stage build model.

A builder stage may contain:

`compiler + source tree + build dependencies + generated artifacts`

while the final runtime stage can contain only the runtime base and the compiled artifact.

The important lifecycle property is that the build environment does not have to become part of the final runtime image merely because it was needed to construct the application.

This can reduce the final image footprint and reduce the number of build-time components present in the runtime environment.

The example does not claim that every build artifact should be handled identically. Runtime requirements determine what must cross the stage boundary.

## JavaScript Event-Driven Representation

The JavaScript implementation focuses on operational visibility.

`DockerImageStore` extends `EventEmitter`. A build can emit cache and layer events while asynchronous scheduling with `setImmediate()` demonstrates how an application could integrate image-processing operations into an event-driven Node.js workflow.

The implementation also validates repository names, instructions, layer sizes, image references, and tags.

The registry is intentionally represented as a small publication map rather than as a fake network implementation. Real image publication involves an OCI-compatible registry protocol, manifests, blobs, authentication, network transport, and registry-side storage.

## C++ Case Study

The C++ program models an image build engine combined with a release-governance boundary.

Its image side contains:

- `Layer` records with parent relationships and sizes.
- `ImageGovernanceEngine` storage for layers, image manifests, tags, and cache entries.
- Deterministic digest generation for the educational model.
- Build-context fingerprints that influence cache reuse.
- Image-size calculation from ordered layer collections.
- Tag resolution that distinguishes immutable image identity from mutable names.

The program then connects image production to a repository release scenario through `PullRequestBuild`, `ProtectedBranchPolicy`, and `ReviewDecision`.

That second part does not redefine Docker images. It demonstrates an operational relationship: a repository change may produce a new image, while organizational governance can decide whether the source change is eligible to enter a protected branch.

The merge gate requires the configured number of approvals, passing checks, the correct target branch, and no merge conflict. This is intentionally separate from Docker's layer and tag mechanisms.

## Java Enterprise Model

The Java implementation treats image management as a small enterprise domain.

`BuildInstruction`, `ImageLayer`, `Image`, `PullRequest`, `Review`, and `BranchPolicy` are explicit domain types. Records provide compact immutable representations for values that should not be modified after creation.

`ImageRepository` owns image and tag state. It also separates the build cache from image identity, preventing a cache key from being treated as an image reference.

`MergeEligibilityService` evaluates the repository-side release condition independently of image construction. This separation is useful in larger systems because build services, registry services, deployment services, and repository governance have different responsibilities.

The Java model also demonstrates stale-state concerns indirectly through explicit review states. An approval is represented as a stateful review decision rather than as an unqualified boolean attached permanently to a pull request.

## SQL Data Model

The PostgreSQL implementation models the domain relationally.

`repositories` stores image repositories.

`image_layers` stores individual layer records. A self-reference through `parent_layer_id` captures the parent relationship.

`images` stores image-level identities and lifecycle state.

`image_manifest_layers` associates images with ordered layers. The composite primary key and uniqueness constraints prevent duplicate layer positions or repeated layer references within one manifest.

`image_tags` represents mutable repository tags independently of images.

`registries` and `registry_publications` represent publication destinations.

`build_cache` records cache keys, input fingerprints, parent layers, and resulting layers.

`build_executions` and `build_steps` provide build-level history and expose whether individual steps were cache hits or misses.

`image_lifecycle_events` provides an audit trail for operational transitions.

## Database-Level Integrity

Several rules are enforced directly by PostgreSQL rather than relying exclusively on application code.

Layer sizes cannot be negative.

Layer digests must use the expected `sha256:` representation.

A repository name cannot be empty.

A tag is unique within a repository.

A layer cannot occupy two positions in the same image manifest because `(image_id, layer_id)` is unique.

An image cannot be marked `PUBLISHED` without a publication timestamp, and a retired image receives a retirement timestamp.

The `tag_image()` function refuses to assign a new tag to a retired image.

These constraints make invalid states harder to create even when multiple applications interact with the database.

## Cache Invalidation

Cache invalidation is the central relationship between build inputs and layers.

Consider:

`FROM base`

`RUN install dependencies`

`COPY source`

If the source changes, the source layer must change, while the earlier layers can potentially remain reusable.

If the dependency input changes, the dependency layer changes. Any later layer derived from that dependency state must then be rebuilt.

This is why the model includes the parent layer in its cache key. Treating an instruction string alone as the cache key would incorrectly suggest that a command always produces the same layer regardless of its preceding filesystem state.

## Tags Versus Digests

The distinction can be expressed compactly:

| Reference | Meaning | Mutable? |
| --- | --- | --- |
| `payments-api:1.1.0` | Human-readable tag | Yes |
| `payments-api:production` | Release-oriented tag | Yes |
| `sha256:...` | Content identity | No, as an identity |
| Layer digest | Content-addressed layer identity | No, as an identity |

A tag can move.

An image digest identifies a particular image manifest.

A layer digest identifies a particular layer.

Production systems should preserve immutable identifiers in deployment and audit records rather than depending only on mutable tags.

## Common Failure Modes

### Accidental cache invalidation

Copying frequently changing files before stable dependency metadata can cause expensive build steps to execute more often than necessary.

The Python cache-ordering example demonstrates this by comparing two build sequences.

### Treating tags as immutable

A tag such as `latest` or `production` can move. It should not be used as the sole long-term identity of a deployed artifact when exact reproducibility matters.

### Assuming every layer is independently useful

A later layer depends on the state produced by preceding layers. Reusing a layer without its correct parent context is not equivalent to reusing the complete image state.

### Confusing image size with unique storage

Two images can share large portions of their layer graph. Adding their individual logical sizes does not necessarily equal the amount of unique storage consumed.

### Retiring a tagged image

An image that is still referenced by a tag should not be treated as safely unreachable. The Python and Java models explicitly block retirement while a tag still resolves to the image.

### Ignoring build context

A Dockerfile instruction can be unchanged while its relevant inputs have changed. Cache reasoning therefore has to account for the state consumed by the build step.

## Performance Considerations

Layer reuse is most valuable when expensive operations are isolated behind stable inputs.

Large dependency installations are particularly important cache boundaries because repeating them can dominate build time.

Small frequently changing application layers can reduce the amount of data that needs to be rebuilt and transferred when the underlying base and dependencies remain unchanged.

Multi-stage builds can separate a large build environment from a smaller runtime image.

Indexes in the SQL implementation support common operational queries: parent-layer lookup, layer sharing, tag-to-image resolution, cache recency, and lifecycle history.

The actual performance of a Docker build also depends on the Docker Engine, BuildKit configuration, local storage, network access, registry latency, compression, and the build context.

## Security Considerations

Image layers can preserve files that were added in an earlier layer even if a later layer appears to remove them from the final filesystem view. Sensitive data should therefore not be introduced into image build history merely with the expectation that a later deletion will erase its presence from all underlying artifacts.

Secrets should be handled using appropriate build-time secret mechanisms rather than copied into ordinary image layers.

Base images should be pinned and maintained deliberately. A mutable tag can change what a future build receives, while an immutable digest provides stronger reproducibility.

Published images should be treated as release artifacts. Recording immutable image digests makes it possible to identify precisely which artifact was promoted.

Registry authentication, access control, signing or attestation mechanisms, and retention policies are operational controls outside the small local models in these examples.

## Debugging Considerations

When a build unexpectedly misses cache, inspect the first layer at which the expected reuse stops.

Useful questions include:

- Did the parent layer change?
- Did a dependency or lock file change?
- Did a `COPY` or `ADD` input change?
- Did the build context contain an unexpected modification?
- Was the instruction itself changed?
- Is the expected layer actually present in the local cache?
- Is the build using the expected builder and cache source?

The Python model makes the cache boundary explicit by printing hits and misses. The JavaScript implementation exposes cache decisions as events. The SQL implementation records cache outcomes so they can be analyzed after builds.

## Practical Relationship Between the Four Areas

The four mechanisms form a chain without being interchangeable:

`Dockerfile/build instructions`
→ produce
`image layers`
→ are reused through
`build caching`
→ are assembled into
`image identities`
→ are referenced by
`tags`
→ move through an
`image lifecycle`
→ may be published and eventually retired.

A cache hit does not create a new semantic image release by itself.

A tag does not create a new layer.

A new layer does not necessarily imply that every existing layer must be rebuilt.

Retiring a tag does not necessarily mean the underlying layer can immediately be deleted.

These distinctions are central to reasoning about Docker image construction and release operations.

## Implementation Mapping

| Implementation | Primary technical perspective |
| --- | --- |
| Python | Layer graph, cache keys, cache invalidation, tags, lifecycle, multi-stage builds, and Docker CLI inspection |
| JavaScript | Event-driven image construction, asynchronous build activity, cache events, tag movement, publication, and inspection |
| C++ | Dependency-free image engine case study with layer storage, deterministic model digests, cache reuse, size accounting, and release governance |
| Java | Enterprise domain model with immutable records, explicit lifecycle state, repository services, validation, review states, and merge eligibility |
| PostgreSQL | Relational representation of layers, manifests, tags, registries, cache records, builds, constraints, functions, indexes, transactions, and lifecycle audit data |

## Production Boundaries

These implementations are educational models of Docker image concepts, not replacements for Docker Engine, BuildKit, or an OCI registry.

The Python program can inspect a real local Docker installation when the Docker CLI and daemon are available, while most of its behavior is deliberately modeled so that layer and cache relationships remain visible.

The JavaScript, C++, and Java programs implement domain models rather than attempting to reproduce the Docker Engine.

The SQL schema is a relational representation of image-management information. It is not an implementation of the OCI Distribution Specification and does not perform registry blob transfer.

The models are therefore most useful for understanding the boundaries between immutable image content, reusable layers, cache decisions, mutable tags, and operational lifecycle state.

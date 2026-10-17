# Docker Fundamentals: Containers, Images, Registries, and Architecture

## Technical scope

Docker packages applications and their dependencies into images and runs those images as containers. Its architecture separates the client interface, daemon, image storage, registry communication, container execution, networking, and resource management.

The five implementations in this repository model these mechanisms from complementary perspectives. Python emphasizes a local deployment simulation and optional inspection of a real Docker installation. JavaScript demonstrates asynchronous registry operations and event-driven lifecycle notifications. C++ implements a repository and deployment case study with explicit resource allocation. Java separates enterprise deployment policy from the underlying container lifecycle. PostgreSQL represents image metadata, transfers, container state, port reservations, and resource constraints relationally.

These programs simulate Docker control-plane behavior. They do not replace the Docker Engine, create operating-system containers, or perform real image transfers unless a separately configured Docker CLI is used by the Python script for read-only inspection.

## Docker architecture

A typical Docker workflow involves several cooperating components.

| Component | Responsibility | Operational distinction |
|---|---|---|
| Docker CLI | Accepts commands such as `docker build`, `docker pull`, and `docker run` | It is a client, not the container runtime itself. |
| Docker daemon | Manages images, containers, networks, and volumes | The daemon coordinates requests and maintains Docker-managed resources. |
| Docker Engine API | Exposes daemon operations to clients | Clients can use the API directly or through compatible tooling. |
| Image store | Holds image manifests and layers available to the local engine | Image data is distinct from the writable state of a running container. |
| Registry | Stores and distributes image references and manifests | A registry is a remote distribution service, not the local execution environment. |
| Container runtime | Creates and supervises isolated processes through the operating system | Containers share the host kernel rather than booting an independent guest kernel by default. |
| Linux kernel facilities | Provide namespaces, control groups, filesystem isolation, and related mechanisms | These facilities enforce much of the process isolation and resource control. |

A simplified request path is:

`Docker CLI or API client -> Docker daemon -> image store and runtime -> operating system`

Image distribution follows a different path:

`Local image -> registry authentication -> registry push -> registry pull -> destination image store`

The separation matters when diagnosing failures. A registry authentication failure does not imply that an existing local image is corrupt. A daemon connectivity failure does not necessarily mean the Docker CLI is missing. A container startup failure may involve the image command, filesystem, environment, network, or host resources rather than image distribution.

## Images, layers, and containers

### Image structure

A Docker image is a versioned package containing a filesystem configuration, metadata, and a startup configuration. An image manifest describes the configuration and layers needed to construct the image filesystem.

A layer represents filesystem changes associated with image construction. Content-addressed layer identifiers allow identical layers to be reused. This reuse can reduce local storage and transfer requirements when images share compatible layers.

The Python and C++ programs model layers using a digest, an instruction description, and a size. Their image stores deduplicate layers by digest instead of charging the full layer size for every image that references it. The JavaScript and Java implementations preserve immutable image metadata and distinguish the image reference from the container created from it.

The simulated layer sizes are educational metadata. Real image sizes depend on filesystem contents, compression, manifest details, platform architecture, and the way a tool reports shared layers.

### Image tags and digests

An image reference commonly has the form `repository:tag`, such as `inventory-api:2.4.1`. A registry-qualified reference can include a hostname and namespace, such as `registry.example.com/operations/inventory-api:2.4.1`.

A tag is a human-readable reference that can be moved to another image. A digest identifies content by its cryptographic hash. Production deployment processes benefit from explicit version tags and digest verification because a tag alone does not guarantee immutable content.

The deployment-policy examples reject the `latest` tag in production scenarios. This is a policy choice, not a universal Docker restriction. Docker allows `latest`; organizations may prohibit it to make deployment selection and incident investigation more reproducible.

### Containers and writable state

A container is a running or stopped instance created from an image. It has a lifecycle, runtime configuration, and typically a writable layer associated with the image's read-only layers.

Creating a container does not necessarily start its application. Starting a container activates its configured process. Stopping a container ends that running process while preserving the container object and its associated writable state. Removing a container discards the container object and its writable layer, subject to the applicable storage and removal options.

An image is not automatically removed when a container is removed. The Python, C++, and Java programs explicitly test this distinction. Their lifecycle models reject removal of running containers, release port reservations when a container is removed, and retain the source image.

Containers are not equivalent to full virtual machines. They usually share the host operating-system kernel, although desktop Docker installations may use a Linux virtual machine to provide the required environment.

## Building images with Dockerfiles

A Dockerfile declares instructions used to build an image. A typical application build might contain:

- `FROM` selects the base image.
- `WORKDIR` establishes the working directory for subsequent instructions.
- `COPY` places application files into the build context's image.
- `RUN` executes build-time commands, such as installing pinned dependencies.
- `ENV` establishes image environment defaults.
- `EXPOSE` documents an intended container port but does not publish that port on the host.
- `USER` selects the identity used for subsequent runtime operations.
- `CMD` supplies the default command or arguments.
- `ENTRYPOINT` defines the primary executable or startup command.

Layer ordering affects cache reuse. Stable instructions, such as installing pinned dependencies from a lock file, are often placed before frequently changing application source. When an earlier build layer changes, later dependent layers may need rebuilding.

A production Dockerfile should avoid copying credentials into the image, limit the build context, use trusted base images, pin important dependencies, and run the application with the minimum privileges it requires. Multi-stage builds can separate compilation dependencies from the smaller runtime image.

The executable programs model completed image metadata rather than invoking a real Dockerfile build. Their layer sequences represent the resulting artifacts and support storage, tagging, and deployment exercises.

## Registries and image distribution

A registry distributes image manifests and layers. Examples include Docker Hub and privately operated registry services. A registry may enforce authentication, repository permissions, retention rules, vulnerability scanning, and organizational publishing policies.

The JavaScript registry exposes asynchronous `login`, `push`, and `pull` operations. `async` methods return promises, allowing callers to handle delayed operations without blocking the event loop. The Python, C++, and Java versions model the same distribution boundary synchronously to focus on image availability and authentication failures.

The simulated workflow distinguishes the following states:

- A local image exists in an image store.
- A push requires authorization when the registry policy demands it.
- A successful push publishes an image reference to the registry model.
- A pull retrieves an available registry image into another image store.
- A missing manifest or failed authentication produces an explicit error.

These models do not implement the Docker Registry HTTP API, TLS, token exchange, content negotiation, or layer streaming. Real registry clients must also verify certificate configuration, permissions, image provenance, and the integrity of the content being deployed.

Authentication tokens should not be embedded in Dockerfiles or application images. Production environments should use credential helpers, short-lived credentials where supported, and narrowly scoped registry permissions.

## Port publishing and container networking

A container port identifies a listening endpoint inside the container's network namespace. Publishing a port makes that endpoint accessible through a host-side port binding.

For example, a mapping from host port `18000` to container port `8000` directs traffic reaching the published host endpoint toward the container endpoint. Publishing is different from merely declaring a port in image metadata.

The Python, JavaScript, C++, and Java implementations represent mappings as host-port and container-port pairs. They reject conflicting host-port allocations and release allocations after container removal. The SQL implementation records port bindings separately and maintains reservations for running containers.

Real Docker networking includes bridge networks, user-defined networks, DNS-based service discovery, host networking, firewall rules, and platform-specific port-forwarding behavior. A host-port binding alone does not guarantee application reachability. The process must listen on the correct interface, network policy must permit traffic, and the host must have a suitable route.

Services that communicate on a user-defined Docker network can usually address one another by container or service name without publishing every internal port to the host. Public port publishing should be limited to the endpoints that genuinely require external access.

## Python implementation

The Python program is a standalone deployment simulator using only the standard library.

`ImageLayer` and `Image` use immutable dataclasses to represent image metadata. Validation rejects missing references, empty entrypoints, and negative layer sizes. `ImageStore` keeps image references and deduplicates layers by digest, illustrating the difference between logical image size and unique local layer storage.

`Registry` requires simulated authentication before accepting a push. A pull places the retrieved image into another image store, demonstrating that registry availability and local image availability are separate concerns.

`DockerDaemon` models container creation, startup, stopping, and removal. It validates names, port ranges, duplicate host-port bindings, and memory limits. Its configured memory calculation is a sum of limits for running containers, not a measurement of actual resident memory.

The sample scenario deploys an API and web service, catches an unauthenticated push, demonstrates a port conflict, and tests invalid lifecycle operations. The final function optionally uses the installed Docker CLI to inspect server information and list running containers. It performs no image pulls, workload starts, or destructive Docker operations.

Run the program with Python 3.10 or later:

`python docker_fundamentals.py`

## JavaScript implementation

The JavaScript program emphasizes event-driven operations and asynchronous registry interaction.

Image metadata is frozen after validation, preventing accidental modification of the modeled manifest and layer list. `LocalImageStore` uses maps to retrieve images by reference and deduplicate content-addressed layers.

`ImageRegistry` exposes asynchronous methods and throws structured errors with codes such as `UNAUTHORIZED`, `INVALID_TAG`, and `NOT_FOUND`. The `main` function awaits each registry operation, while a top-level rejection handler reports unexpected failures.

`DockerHost` extends Node.js `EventEmitter`. It publishes events when containers are created, started, stopped, or removed. Subscribers can observe changes without embedding reporting logic inside each lifecycle operation. This is useful in event-driven control planes, although the in-memory events in this example are neither durable nor delivered across processes.

The deployment policy checks for an explicit image version, a running container, and an acceptable memory limit. It demonstrates that successfully creating a container and satisfying organizational deployment requirements are separate outcomes.

Run with Node.js 18 or later:

`node docker_fundamentals.js`

## C++ case study

The C++ program models a small operations environment containing an inventory API and a web service.

`ImageLayer`, `Image`, and `ImageStore` separate layer metadata from image references. The store uses ordered maps for image lookup and layer deduplication. Its storage report calculates the total size of distinct layers, avoiding the incorrect assumption that every image independently consumes all of its layers.

`ImageRegistry` enforces authentication before publication. `DockerHost` owns container records and host-port reservations. It validates every requested port before reserving resources, preventing a failed container creation from leaving a partially allocated set of ports.

The `ContainerState` enumeration makes lifecycle states explicit. `start`, `stop`, and `remove` reject invalid transitions. The host refuses to remove a running container and releases port reservations only after successful removal.

The deployment eligibility function adds an independent policy layer. A container may be valid according to the lifecycle model but still fail deployment policy because it uses an unversioned tag, is not running, or has an insufficient memory limit.

Compile with a C++17-compatible compiler:

`g++ -std=c++17 -Wall -Wextra -pedantic docker_case_study.cpp -o docker_case_study`

Run the executable with `./docker_case_study` on Linux or the equivalent executable name on the target operating system.

## Java enterprise model

The Java implementation separates the image distribution layer, local image store, container lifecycle, host resource management, and deployment policy into domain-specific classes.

The `Image` record copies its layer list, entrypoint, and environment map into immutable representations. `PortBinding` validates port numbers at construction time, so invalid bindings cannot enter the model through the public record constructor.

`Container` owns its lifecycle state and event history. Callers cannot assign arbitrary states directly; they must use methods that enforce legal transitions. The `DockerHost` validates port reservations and memory limits before inserting a container into its managed collection.

`DeploymentPolicy` returns specific failure messages rather than a single Boolean alone. This supports operational reporting because a rejected deployment can identify whether the failure concerns image tagging, container state, memory limits, or published ports.

The configured memory total is calculated from running containers. It represents a simplified reservation model rather than actual kernel-enforced resource consumption. The model does not implement concurrent allocation locking, cgroup enforcement, or persistent event storage.

Compile and run with Java 17 or later:

`javac DockerGovernance.java`

`java DockerGovernance`

## PostgreSQL data model

The SQL script stores Docker-related control-plane metadata in the `docker_lab` schema.

| Relation | Purpose |
|---|---|
| `registries` | Identifies registry hosts, registry types, and authentication requirements. |
| `repositories` | Associates repositories with registries and their visibility policies. |
| `image_layers` | Stores content digests, layer instructions, and byte sizes. |
| `images` | Records tags, manifest digests, entrypoints, and environment defaults. |
| `image_layer_membership` | Maps ordered image layers to each image. |
| `image_transfers` | Records push and pull operations, including failures. |
| `hosts` | Represents Docker hosts and their configured memory capacity. |
| `containers` | Tracks image references, lifecycle state, memory limits, and commands. |
| `port_bindings` | Associates container ports with published host ports. |
| `host_port_reservations` | Reserves host ports for running containers. |

Foreign keys preserve the relationships between images, repositories, registries, layers, hosts, and containers. Unique constraints prevent duplicate image tags within a repository and duplicate layer positions within an image. Check constraints reject invalid sizes, unsupported states, malformed JSON types, and invalid port numbers.

The image-size views calculate logical image size from layer membership. A production storage report must distinguish logical image size from physical storage because a shared layer should be counted only once per host. Accurate physical usage also requires accounting for compressed content, build cache, writable layers, volumes, and filesystem behavior.

The running-host report compares configured memory limits with host capacity. A trigger rejects a running container when its memory reservation would exceed the host's configured capacity. This is a control-plane rule, not a replacement for operating-system resource enforcement.

Port reservations are created when a container enters the running state and released when it stops or is removed. The unique reservation key prevents two containers on the same host from reserving the same host port and protocol. The example trigger uses a simplified allocation model; production-grade concurrent deployments require carefully designed transaction locking and error handling.

The sample records include successful and failed registry transfers, versioned and `latest` image tags, multiple running containers, resource reporting, and intentional resource and port conflicts. The exception-handling blocks preserve the remainder of the demonstration after expected database errors.

Run the script in PostgreSQL using a client such as `psql`:

`psql -v ON_ERROR_STOP=1 -d your_database -f docker_fundamentals.sql`

The script drops and recreates its dedicated schema. Do not run it against a schema containing data that must be retained.

## Resource limits and runtime behavior

Container resource controls are enforced by the runtime and operating system, not by image metadata alone.

A memory limit constrains memory consumption according to the runtime and host platform's configuration. CPU quotas or shares affect scheduling and available CPU time. Process limits constrain the number of processes or related operating-system resources. Disk capacity and I/O controls have separate implications.

The examples calculate configured memory reservations for running containers. A sum of configured limits is not equivalent to actual memory use: some workloads consume far less than their limit, and certain runtime configurations allow aggregate limits to exceed physical memory. The sample deployment models intentionally use stricter reservation accounting to make capacity decisions explicit.

Production deployments should measure actual resource consumption, define limits based on workload characteristics, and observe restarts, exit codes, health checks, and application logs. A container being in the `running` state does not establish that its service is healthy or able to handle requests.

## Failure modes and operational diagnosis

Docker failures occur at different architectural boundaries.

| Symptom | Likely area to investigate | Technical distinction |
|---|---|---|
| Docker CLI cannot connect | Daemon availability, socket permissions, context, or endpoint configuration | Installing the CLI does not establish that a daemon is reachable. |
| Image pull is denied | Registry authentication, repository visibility, or permissions | A remote authorization failure is distinct from a missing local image. |
| Image reference cannot be resolved | Repository name, tag, registry hostname, or manifest availability | Image names are not interchangeable with container names. |
| Container exits immediately | Entrypoint, command arguments, configuration, or application failure | A successfully created container may fail as soon as its process starts. |
| Host port is unavailable | Existing listener, another binding, or host network configuration | The container port and host port are separate endpoints. |
| Container starts but service is unreachable | Listening interface, routing, DNS, firewall, or application readiness | A running process does not prove network accessibility. |
| Resource exhaustion occurs | Memory, CPU, process, disk, or I/O pressure | Configured limits and actual consumption require separate measurements. |
| A new image behaves differently from the previous release | Changed tag target, layers, configuration, or runtime environment | Mutable tags can select different content over time. |

The in-memory simulations cover selected validation and lifecycle failures. They do not model all real daemon errors, kernel failures, network races, image signature verification, or concurrent container operations.

## Security and production considerations

A secure container deployment requires controls beyond a valid image reference.

- **Image provenance:** Use trusted build processes, immutable digests where appropriate, and controlled promotion between environments. A successful registry pull establishes availability, not trustworthiness.
- **Least privilege:** Run application processes as non-root when possible, minimize Linux capabilities, and avoid privileged containers unless a narrowly defined requirement justifies them.
- **Secret handling:** Inject runtime secrets through appropriate secret-management mechanisms. Do not bake registry tokens, private keys, or production credentials into image layers.
- **Network exposure:** Publish only required service ports. Prefer controlled internal networks for service-to-service communication and restrict host exposure through network policy and firewall rules.
- **Resource control:** Define realistic memory and CPU limits, observe actual consumption, and test behavior under resource pressure.
- **Image construction:** Use minimal trusted base images, pinned dependencies, controlled build contexts, and multi-stage builds when they reduce the runtime attack surface.
- **Runtime observability:** Collect application logs, container events, exit codes, health information, and resource metrics. Lifecycle state alone is insufficient for diagnosing service health.
- **Host security:** Keep the Docker Engine and host operating system patched. Access to a privileged Docker daemon can provide substantial control over the host and should be restricted.
- **Registry governance:** Enforce repository access controls, secure transport, retention policies, and image verification appropriate to the deployment environment.

These controls complement the mechanisms demonstrated by the programs. The simulations provide a clear model of images, containers, registry distribution, networking, and resource reservations while leaving operating-system enforcement and real Docker Engine behavior to the actual deployment platform.

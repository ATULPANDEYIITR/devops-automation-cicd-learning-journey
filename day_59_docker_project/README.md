# Docker Project: Containerize a Multi-Service Application

## Project Scope

This project models a production-style multi-service order platform composed of five cooperating services:

| Service | Responsibility | Example Image | Host Port |
|---|---|---|---:|
| `frontend` | Presents the application interface and calls the API | `orders-frontend:1.0` | 3000 |
| `api` | Handles application requests and coordinates persistence and caching | `orders-api:1.0` | 8080 |
| `worker` | Processes asynchronous application work | `orders-worker:1.0` | none |
| `db` | Stores durable relational application data | `postgres:18` | 5432 |
| `redis` | Provides cache and transient work coordination | `redis:8` | 6379 |

The technical relationship is:

    frontend
        |
        v
       api ---------> db
        |             ^
        v             |
      redis <------ worker

The services share an application network. Service-to-service communication uses service names rather than host-specific addresses. The API and worker require healthy database and Redis services. The frontend requires a healthy API.

The project separates four concerns that are frequently confused in multi-service container deployments:

- service configuration defines what should exist;
- dependency management defines startup relationships;
- health state describes whether a running service is usable;
- orchestration determines whether the complete application can start, recover, and operate.

## Architecture

The application follows a layered container architecture.

    +----------------------+
    |      Frontend        |
    |     :3000            |
    +----------+-----------+
               |
               v
    +----------------------+
    |        API           |
    |       :8080          |
    +-----+-----------+----+
          |           |
          v           v
    +----------+   +----------+
    | PostgreSQL|   |  Redis   |
    |   :5432  |   |  :6379   |
    +----------+   +----------+
          ^
          |
    +-----+----------------+
    |       Worker         |
    | asynchronous jobs    |
    +----------------------+

The frontend does not access PostgreSQL directly. This keeps persistence behind the API boundary and prevents presentation-layer code from acquiring unnecessary database credentials.

The worker communicates with the database and Redis because it performs background processing independently of frontend requests.

## Docker Concepts Implemented

### Service Isolation

Each major responsibility is represented by an independently deployable service. A failure in one container does not require the remaining containers to be represented as one monolithic process.

The source implementations model the service identity, image, memory allocation, exposed host port, environment configuration, dependency relationships, and lifecycle state.

An image is represented using an explicit tag such as `postgres:18` or `orders-api:1.0`. The validators reject untagged image references because implicit image selection makes deployments less reproducible.

### Container Lifecycle

The lifecycle used by the implementations is:

    CREATED
       |
       v
    STARTING
       |
       v
    HEALTHY
       |
       +------> UNHEALTHY
       |
       v
    STOPPED

A stopped service can be restarted. Restart counts are tracked to distinguish an initial startup from recovery activity.

The lifecycle model is deliberately separate from dependency readiness. A container can be running while its application is not ready to serve traffic.

### Service Dependencies

The dependency graph is:

    db       redis
     \       /
      \     /
        api
         |
      frontend

and:

    db ------ worker
     \        /
      \      /
        redis

The API and worker use a healthy dependency condition for PostgreSQL and Redis. The frontend uses a healthy dependency condition for the API.

This is different from merely requiring that a dependency process has started. A started PostgreSQL container may still be initializing its database. A started API container may still be loading configuration or establishing database connections.

## Python Implementation

The Python implementation provides a deterministic orchestration simulator.

`Service` is a dataclass representing container-level configuration and lifecycle state. It validates:

- service naming;
- explicit image tags;
- valid ports;
- minimum memory allocation;
- environment variable names;
- dependency references.

`ComposeValidator` performs application-wide validation. It checks:

- missing dependencies;
- self-dependencies;
- duplicate host ports;
- dependency cycles.

A depth-first traversal detects cycles. A topological sort calculates dependency-safe startup order.

`ComposeRuntime` handles lifecycle behavior. It:

- validates the complete service graph;
- starts services in dependency order;
- enforces `service_started` and `service_healthy` conditions;
- connects running services to the application network;
- stops services;
- restarts failed services;
- records restart counts;
- reports health state.

The script also tests invalid image references, missing dependencies, and circular dependency graphs before executing the normal application scenario.

The network model intentionally prevents the frontend from directly reaching the database. The frontend can reach the API because both services belong to the application network, while the database is not treated as a frontend dependency.

## JavaScript Implementation

The JavaScript implementation uses an event-driven architecture rather than translating the Python class structure mechanically.

`EventEmitter` represents lifecycle notifications. The orchestrator emits events when services start, become healthy, stop, and restart.

`Map` is used for service lookup and dependency graph construction. `Set` represents network membership.

The asynchronous `start()` method uses a Promise to model the fact that container startup is not inherently synchronous. Dependency readiness is checked before the asynchronous startup operation completes.

The JavaScript policy layer validates:

- service names;
- explicitly tagged images;
- memory requirements;
- host port collisions;
- dependency existence;
- dependency conditions;
- circular dependencies.

The event stream makes operational state changes visible:

    service-started
          |
          v
    service-healthy
          |
          v
      application

Failure recovery is demonstrated by making Redis unhealthy and then restarting it.

## C++17 Implementation

The C++17 implementation presents the problem as a deployment engine.

`Service` stores strongly typed service configuration. `enum class` is used for lifecycle and dependency conditions, preventing arbitrary string values from representing states.

`DeploymentEngine` owns the service graph and network membership. It provides:

- configuration validation;
- cycle detection;
- topological startup ordering;
- dependency readiness checks;
- service startup;
- failure simulation;
- restart handling;
- network reachability checks.

The implementation uses `std::map`, `std::set`, `std::queue`, and `std::vector`.

Topological ordering is calculated with indegree tracking. If the resulting ordering contains fewer services than the configured graph, a cycle exists.

The C++ version also validates a security-oriented architectural rule: the frontend must not directly reach the database.

## Java 17 Implementation

The Java implementation models the application as an enterprise deployment service with explicit domain types.

Records represent immutable value concepts such as:

- `Dependency`;
- `EnvironmentVariable`.

`ServiceDefinition` encapsulates lifecycle state and service configuration.

`DeploymentPolicy` is an interface that separates deployment rules from deployment execution. `ProductionPolicy` implements validation rules for service names, image tags, memory requirements, host ports, dependency references, and dependency cycles.

`DeploymentNetwork` models service membership and reachability.

`DeploymentService` coordinates:

- configuration validation;
- dependency-safe startup;
- dependency health evaluation;
- lifecycle transitions;
- restart behavior;
- network state.

The separation between policy and execution is useful in enterprise systems because different environments can enforce different deployment rules without changing the basic lifecycle service.

## PostgreSQL Implementation

The PostgreSQL implementation models the Docker environment as relational operational data.

The `docker_demo` schema contains tables for:

- repositories;
- services;
- environment variables;
- service dependencies;
- containers;
- health checks;
- health observations;
- networks;
- network memberships;
- deployment policies;
- deployments;
- deployment-service state.

The relational structure represents the domain relationship:

    Repository
        |
        +---- Service
        |       |
        |       +---- Environment
        |       +---- Dependency
        |       +---- Container
        |       +---- Health Check
        |
        +---- Network
        |
        +---- Deployment Policy
                 |
                 +---- Deployment

Foreign keys enforce relationships. Check constraints prevent invalid ports, invalid memory limits, malformed service names, invalid environment variable names, and invalid health-check parameters.

A trigger prevents self-dependencies. Another trigger prevents duplicate host-port assignments within a repository.

The container transition trigger records startup and shutdown timestamps and requires a restart counter to increase when a stopped container returns to the running state.

## Health Checks

Health status is intentionally different from container status.

A container can exist and be running while its application is unavailable.

The database model stores:

- health-check definitions;
- execution intervals;
- timeout values;
- retry counts;
- individual health observations;
- response latency;
- failure reasons.

The latest health observation can be selected with PostgreSQL's `DISTINCT ON` feature.

A health record contains a failure reason whenever the observation is unhealthy. This prevents failure records from becoming ambiguous operational data.

## Configuration and Environment

Environment variables are represented explicitly rather than embedded into application source code.

Examples include:

| Variable | Service | Purpose |
|---|---|---|
| `DATABASE_HOST` | API | Database service discovery |
| `DATABASE_HOST` | Worker | Database service discovery |
| `REDIS_HOST` | API | Redis service discovery |
| `REDIS_HOST` | Worker | Redis service discovery |
| `API_BASE_URL` | Frontend | API service discovery |

The model treats environment names as uppercase identifiers.

Secrets are not hard-coded into production application source in the implementation model. The sample configuration uses development-oriented values only. Production deployment should provide credentials through an appropriate secret-management mechanism rather than committing credentials to source control.

## Networking

The application uses an isolated bridge-style network represented by `orders-network`.

Service discovery is based on logical service names:

    frontend -> api:8080
    api      -> db:5432
    api      -> redis:6379
    worker   -> db:5432
    worker   -> redis:6379

Host port publication and internal service connectivity are separate concepts.

For example, the API may be published on host port `8080`, while internal containers still communicate with the API through its service identity and container port.

The frontend does not need a direct database connection.

## Startup Ordering

Dependency ordering is calculated from the directed service graph.

A topological ordering produces a sequence in which dependencies occur before dependents:

    db
    redis
       |
       v
      api
       |
       v
    frontend

The worker can start after its database and Redis dependencies become healthy.

The ordering algorithm does not by itself prove that a dependency is operational. The runtime separately evaluates health conditions.

This distinction prevents a common deployment error where container creation order is incorrectly treated as application readiness.

## Failure and Recovery

The implementations simulate service failures.

A service may transition to `UNHEALTHY`. Dependent services can then be prevented from starting or considered unable to satisfy a health-based dependency condition.

Recovery uses a restart operation:

    healthy
       |
       v
    failure
       |
       v
    stopped
       |
       v
    starting
       |
       v
    healthy

Restart counters make recovery activity observable.

The PostgreSQL transaction demonstrates controlled failure simulation. Redis is temporarily marked unhealthy, a failed health observation is inserted, the resulting state is inspected, and the transaction is rolled back so the sample database remains usable.

## Validation Rules

The project applies validation at several layers.

| Layer | Examples |
|---|---|
| Service model | Names, image tags, memory, ports |
| Dependency graph | Missing dependencies, self-dependencies, cycles |
| Network | Membership and service reachability |
| Health | Latest health observation and failure reason |
| Database | Foreign keys, unique keys, checks, triggers |
| Deployment policy | Healthy-service count and memory capacity |

This layered approach prevents a single validation mechanism from becoming responsible for every failure class.

## Resource Constraints

Each service has a memory allocation.

The sample configuration requests:

| Service | Memory |
|---|---:|
| `db` | 512 MB |
| `redis` | 256 MB |
| `api` | 512 MB |
| `worker` | 384 MB |
| `frontend` | 256 MB |
| **Total** | **1920 MB** |

The production deployment policy allows `2048 MB`, so the configured application fits within the policy.

The SQL implementation calculates this value rather than relying only on a hard-coded result.

Memory limits are configuration constraints, not guarantees that an application will perform correctly. Real deployments also need CPU, disk, network, database connection, and application-specific capacity planning.

## Security Considerations

The architecture applies several basic security boundaries.

- The frontend has no direct database dependency.
- Database connectivity is mediated through the API and worker.
- Service-to-service communication occurs through a controlled application network.
- Environment variable names are validated.
- Image references require explicit tags.
- Host ports are validated and cannot collide within the repository.
- Dependency relationships are validated before startup.
- Database relationships use foreign keys.
- Deployment policy can reject configurations outside resource limits.

Image tags improve reproducibility, but a tag alone is not an immutable supply-chain guarantee. Production systems can strengthen this model with image digests, signed images, vulnerability scanning, restricted registries, least-privilege container users, read-only filesystems where appropriate, and controlled secret delivery.

## Performance Considerations

The dependency graph is small enough for straightforward graph traversal.

For `V` services and `E` dependency edges:

- dependency validation is approximately `O(V + E)`;
- topological ordering is `O(V + E)`;
- cycle detection is `O(V + E)`;
- service lookup is approximately `O(1)` in the Python dictionary, JavaScript Map, and hash-based structures where applicable.

The PostgreSQL schema uses indexes on repository membership, dependency targets, and health-observation history.

Health observations can grow rapidly in a real deployment. Production systems should establish retention, partitioning, aggregation, or archival policies appropriate to the observation volume.

## Important Distinctions

### Image

An image is the packaged artifact from which a container is created.

Example:

`orders-api:1.0`

### Container

A container is a runtime instance created from an image.

Multiple containers can originate from the same image.

### Service

A service describes a logical application component and its runtime configuration.

For this project, `api` is a service while an individual `api-1` instance would be a container.

### Network

A network provides controlled connectivity between services.

Network membership does not automatically imply that every application component should communicate directly with every other component. Application-level authorization and dependency design still matter.

### Health

Health expresses application readiness or operational condition.

A running container is not necessarily healthy.

### Dependency

A dependency expresses an operational relationship between services.

A health-based dependency is stricter than simply requiring that another service process has started.

## Edge Cases

The implementations explicitly handle:

- empty service configurations;
- duplicate service names;
- malformed service names;
- missing image tags;
- invalid host ports;
- duplicate host ports;
- insufficient memory allocations;
- missing dependencies;
- self-dependencies;
- dependency cycles;
- stopped services;
- unhealthy services;
- service restart counts;
- invalid environment variable names;
- invalid health observations;
- database referential-integrity violations.

A circular dependency is rejected instead of allowing startup to continue indefinitely.

## Practical Workflow

A realistic multi-service deployment workflow represented by these artifacts is:

    Define services
          |
          v
    Validate configuration
          |
          v
    Validate dependency graph
          |
          v
    Create network
          |
          v
    Start infrastructure services
          |
          v
    Wait for health
          |
          v
    Start application services
          |
          v
    Verify service reachability
          |
          v
    Monitor health
          |
          v
    Restart failed services
          |
          v
    Re-evaluate application readiness

The workflow separates configuration correctness from runtime readiness.

## File Responsibilities

| File | Main engineering perspective |
|---|---|
| Python | Service modeling, graph validation, lifecycle simulation, assertions |
| JavaScript | Event-driven orchestration, asynchronous startup, Maps, Sets, events |
| C++17 | Typed deployment engine, graph algorithms, explicit resource management |
| Java 17 | Enterprise domain modeling, policy interface, records, services, lifecycle rules |
| PostgreSQL | Relational topology, health data, deployment policy, constraints, triggers, transactions |

The implementations intentionally solve the same domain from different engineering perspectives rather than mechanically reproducing identical source structures.

## Limitations of the Model

This project models Docker concepts without requiring a Docker daemon. It does not create real images, containers, volumes, Docker networks, or container processes.

The lifecycle transitions are deterministic. Real container startup involves process execution, image retrieval, filesystem setup, networking, resource scheduling, application initialization, and external dependencies.

The health model represents health-check data but does not execute shell commands or HTTP requests.

The database model represents deployment state and policy. It does not replace an actual container orchestrator.

These limitations keep the learning artifacts focused on the architecture, state management, dependency graph, validation, persistence, and operational reasoning required for a multi-service Docker application.

# Docker Compose: Multi-Container Applications, Services, and Networks

## Overview

Docker Compose defines and manages applications made up of multiple containers through a declarative YAML configuration. A project can describe application services, container images, dependencies, networks, persistent storage, environment variables, health checks, and lifecycle policies in one configuration.

This project examines a realistic three-service application:

- **Database:** PostgreSQL stores application data.
- **API:** The application service communicates with PostgreSQL and exposes application functionality.
- **Web:** Nginx serves the public-facing interface and forwards requests to the API.

The implementation separates service configuration, network connectivity, dependency ordering, runtime health, deployment state, and failure handling. These mechanisms are related, but they address different operational concerns.

## Architecture

The application uses two networks.

- `frontend` connects the web service and API.
- `backend` connects the API and database. It is marked internal in the model.

The database is not attached directly to the frontend network.

Plain-text architecture:

    Client
      |
      v
    Web (nginx)
      |
      | frontend network
      v
    API (application)
      |
      | backend network
      v
    Database (postgres)

The API is the only service attached to both networks. This arrangement limits direct network reachability between the web tier and database tier.

An internal Docker network restricts external connectivity through that network. It does not replace authentication, database permissions, host security, or application-level authorization.

## Core Concepts

### Projects and services

A Compose project groups related services, networks, volumes, and other resources. Compose normally derives resource names from the project name, unless explicit names or external resources change the naming behavior.

A service describes how to create and run a workload. Its configuration can include:

- Image and build instructions.
- Container command and entrypoint.
- Environment variables.
- Published ports.
- Network attachments.
- Dependency conditions.
- Health checks.
- Restart policies.
- Volume mounts and configuration files.

A service is not identical to a container. A service can represent one or more container instances, particularly when scaling is used. Each container instance has its own runtime state.

### Images and containers

An image is the packaged filesystem and metadata used to create a container. A container is a running or stopped instance created from an image.

The sample services use PostgreSQL, a Python application image, and Nginx. The language implementations model these services without actually launching their containers.

Image tags such as `postgres:18` identify a major-version tag, not an immutable artifact. Production deployments should consider image digests, trusted registries, vulnerability scanning, controlled updates, and compatibility testing.

### Service names and DNS

On a user-defined Compose network, services can generally discover one another by service name. The API can connect to the database using `db` as its hostname rather than relying on a container IP address.

Container IP addresses can change when containers are recreated. Service-name discovery is more suitable for application configuration.

The database's internal port should be used for service-to-service connections. Publishing a database port to the host is not necessary merely because the API needs database access.

## Docker Compose Configuration

A representative configuration for the architecture follows. It is a deployment example, separate from the executable simulators and database model.

    name: orders-stack

    services:
      db:
        image: postgres:18
        environment:
          POSTGRES_DB: orders
          POSTGRES_USER: app
          POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD}
        volumes:
          - postgres-data:/var/lib/postgresql
        networks:
          - backend
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U app -d orders"]
          interval: 5s
          timeout: 3s
          retries: 10
          start_period: 10s
        restart: unless-stopped

      api:
        image: python:3.13-slim
        environment:
          DATABASE_HOST: db
          DATABASE_NAME: orders
        networks:
          - frontend
          - backend
        depends_on:
          db:
            condition: service_healthy
        healthcheck:
          test: ["CMD", "python", "-c",
                 "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
          interval: 10s
          timeout: 3s
          retries: 3
        restart: on-failure

      web:
        image: nginx:alpine
        ports:
          - "127.0.0.1:8080:80"
        networks:
          - frontend
        depends_on:
          api:
            condition: service_healthy
        restart: unless-stopped

    networks:
      frontend:
        driver: bridge
      backend:
        driver: bridge
        internal: true

    volumes:
      postgres-data:

This configuration assumes that the API image actually contains a working application listening on port 8000, exposes the specified health endpoint, and has the required database driver. A bare Python base image does not provide those application features by itself. Similarly, Nginx needs suitable proxy configuration if it is expected to forward requests to the API.

The PostgreSQL data directory shown is appropriate for current official PostgreSQL image layouts that use `/var/lib/postgresql` as the parent of version-specific data directories. Confirm the selected image version's storage layout before migrating existing data.

For a production deployment, replace the demonstration image references with tested application images, configure the Nginx routing rules, and supply credentials through an appropriate secret-management mechanism.

## Service Dependencies and Startup Ordering

`depends_on` expresses relationships between services. Its short syntax controls basic startup ordering. The long syntax can specify conditions such as:

- `service_started`: the dependency's container has started.
- `service_healthy`: the dependency has passed its configured health check.
- `service_completed_successfully`: the dependency completed successfully, useful for certain initialization jobs.

These conditions are not interchangeable.

A running PostgreSQL process may still be initializing, replaying recovery logs, or preparing to accept application connections. A health check provides a more useful readiness signal than container existence alone.

Compose waits for configured dependency conditions during applicable startup operations. It does not guarantee that a dependency remains healthy after the dependent service starts.

Applications must still handle connection failures, timeouts, reconnection, and interrupted requests. Health checks should test meaningful readiness without performing destructive operations.

The implementations compute a topological startup order. If `db` precedes `api`, and `api` precedes `web`, the resulting order is:

    db -> api -> web

Independent services can be started in different orders. A dependency cycle makes a valid topological order impossible and is rejected by the simulators.

## Networks and Isolation

### Bridge networks

Compose ordinarily creates bridge networks for services on a single Docker host. Containers attached to the same network can communicate through the network, subject to listener configuration and other network controls.

Network membership establishes potential reachability. It does not prove that an application is listening, that DNS resolution succeeds, or that authentication succeeds.

### Internal networks

An internal network is intended for communication isolated from external connectivity through that network. The `backend` network in this project reduces direct exposure of the database tier.

A service connected to both frontend and backend networks can still act as a communication path between tiers at the application level. Network segmentation is useful, but it is not a complete substitute for firewall controls, application authorization, or least-privilege credentials.

### Published ports

The `ports` setting maps a host port to a container port. It is different from `expose`, which documents an internal service port without publishing it on the host.

Binding the web port to `127.0.0.1` limits host-port access to the local machine. A public deployment normally requires a deliberate ingress and TLS configuration.

The database is not published in the example. The API reaches it over the backend network.

## Health Checks and Runtime State

Container state and application health describe different properties.

| State or signal | Meaning |
|---|---|
| Created | The workload has been defined or a container has been created, but it is not confirmed healthy. |
| Starting | Startup is in progress. |
| Healthy | The configured health check currently passes. |
| Unhealthy | The configured health check fails according to its policy. |
| Stopped | The workload is no longer running. |
| Failed | A modeled operation or process has failed. |

The source implementations use these states to simulate lifecycle transitions. The Python and C++ models use a single health-probe result per service. JavaScript models asynchronous probes and repeated attempts. Java represents service specifications separately from mutable runtime state.

These states are simplified application-level models, not an exact copy of Docker Engine's complete container-state machine. Real Docker containers expose more detailed lifecycle information, and health-check status is an additional field rather than a complete replacement for container state.

A health check should verify a useful application condition. A database check might use `pg_isready`; an API check might call a local readiness endpoint. A check that only tests whether a process exists can report success while dependencies or application initialization remain broken.

## Restart Policies and Recovery

Compose supports restart policies such as:

| Policy | Intended behavior |
|---|---|
| `no` | Do not automatically restart the container. |
| `on-failure` | Restart after an unsuccessful exit, subject to the configured restart limit when applicable. |
| `always` | Restart the container when it exits, subject to Docker's restart behavior. |
| `unless-stopped` | Restart it unless it has been explicitly stopped. |

A restart policy does not make a container healthy, repair invalid configuration, restore lost data, or guarantee that dependent services recover correctly.

The simulators store restart-policy values for configuration validation. They do not implement the Docker Engine's restart manager, backoff behavior, container recreation, or process supervision.

The JavaScript simulator adds asynchronous health-check attempts. A failed check produces a lifecycle error and triggers rollback of services started by that simulation operation. This rollback is an educational orchestration behavior, not an assertion that Compose always stops every previously started service after a startup failure.

## Persistent Data and Configuration

Containers are replaceable runtime instances. Important database data should not exist solely in a container's writable layer.

A named volume provides persistent storage managed by Docker. Removing a container does not ordinarily remove its named volume. Removing a project with volume deletion options can remove the associated data, so cleanup commands must be used carefully.

Environment variables are appropriate for non-secret configuration such as a database hostname. Passwords and tokens require stronger handling. Environment variables may be visible through process inspection, container metadata, diagnostics, or logs. Prefer supported Compose secrets or an external secret manager when suitable.

The Python and Java models reject empty values for environment-variable names that indicate credentials. The PostgreSQL model distinguishes secret metadata from ordinary configuration and deliberately avoids storing a sample password. These checks reduce accidental misconfiguration but do not provide encrypted secret storage.

## Python Implementation

The Python script models the Compose project using dataclasses, enums, dictionaries, sets, and explicit exceptions.

### Project validation

`ComposeProject.validate()` checks that:

- The project contains services.
- Each service has a valid image and network membership.
- Network references exist.
- Dependencies refer to valid services.
- Health checks exist for `service_healthy` dependencies.
- Credential-like environment variables are not empty.
- The dependency graph has no cycle.

The `Network`, `Dependency`, and `Service` dataclasses represent configuration. The `ServiceState` enum separates lifecycle states from arbitrary strings.

### Dependency algorithm

`startup_order()` implements Kahn's topological sorting algorithm. It calculates the number of prerequisites for each service, adds dependency-free services to a ready collection, and processes the graph until every service has been ordered.

For \(V\) services and \(E\) dependency edges, a conventional topological sort runs in \(O(V+E)\) time when queue operations are constant-time. This implementation sorts the ready collection to provide deterministic ordering, adding sorting overhead.

### Failure handling

`start()` checks dependency conditions before starting each service. A failed health probe raises `StartupError`; the simulator then marks services started by that operation as stopped in reverse order.

The example deliberately fails the database health check to show that dependent services cannot proceed.

The script also checks network reachability through shared network membership. It does not open sockets or create real Docker resources.

### Practical uses and limitations

This model is useful for validating dependency graphs, demonstrating lifecycle transitions, and testing configuration assumptions without Docker.

It does not parse Compose YAML, build images, create containers, apply port mappings, mount volumes, or query real health checks. The simulator should not be treated as proof that a deployment configuration is valid according to the Compose specification.

## JavaScript Implementation

The Node.js program provides an event-driven alternative.

### Event model

`ComposeProject` extends `EventEmitter`. Lifecycle transitions produce structured events containing a timestamp, service name, event type, and optional details.

Consumers can subscribe to the `lifecycle` event to build logs, metrics, or a monitoring display. The example prints these events as the application starts, becomes healthy, rolls back, and stops.

### Asynchronous health evaluation

Each service can define an asynchronous health-check function. The startup method awaits each check and supports a bounded number of attempts. A rejected health-check promise is recorded as an error rather than silently treated as success.

`maxAttempts` is validated before startup. The example uses a no-op delay function to keep the demonstration fast; production retry loops should use controlled backoff and cancellation.

### Configuration and data integrity

`ServiceDefinition` validates service names, images, network assignments, dependency conditions, restart policies, and secret-related environment variables. It uses `Set` for network membership and immutable copies of the service configuration.

The project uses `Map` for named resources, avoiding accidental confusion between a missing service and an existing service with a false-like value.

The `snapshot()` method returns plain objects representing current state. The `events` collection retains the emitted lifecycle records.

As with the other simulators, event timestamps and retries describe simulated activity, not measured Docker performance.

## C++17 Implementation

The C++ program emphasizes explicit types, standard-library containers, and deterministic graph evaluation.

### Domain model

The implementation uses:

- `Network` for network definitions.
- `Service` for image, network, dependency, and runtime information.
- `Dependency` for prerequisite relationships and readiness conditions.
- Enums for lifecycle states, restart policies, and dependency conditions.
- `ComposeEngine` to validate configuration and coordinate lifecycle transitions.

`std::map` stores services and networks by name. `std::set` represents network membership and provides deterministic ordering. `std::vector` stores dependencies and startup order.

### Graph validation

`startupOrder()` computes a topological ordering. If the number of ordered services differs from the number of defined services, the graph contains a cycle.

This method avoids starting services with unresolved prerequisites. It also makes the startup order inspectable before the simulated lifecycle begins.

### Error behavior

Configuration failures use `std::invalid_argument`, while runtime failures use `std::runtime_error`. The caller can distinguish configuration errors from the exceptions that arise during startup.

The sample creates an unhealthy database and confirms that the API and web services cannot successfully complete the modeled startup. It also checks a service's network references before running the lifecycle.

### Engineering trade-offs

The model favors transparent behavior over integration complexity. It uses synchronous probes and one simulated result per service. It does not provide threads, process management, network sockets, asynchronous scheduling, or Docker API access.

The use of ordered containers improves reproducibility but may have greater lookup and insertion costs than hash-based containers. For a small service graph, predictable output is a useful trade-off.

## Java 17 Implementation

The Java implementation models service configuration and mutable runtime state separately, using records and domain-oriented classes.

### Immutable configuration

`Network`, `Dependency`, and `ServiceSpec` are records. Their constructors validate input and copy collections so external modifications do not change the stored configuration.

`RuntimeService` holds mutable state and health-probe information. This separation prevents lifecycle transitions from accidentally rewriting the desired service definition.

`ComposeProject` coordinates validation, graph ordering, startup, rollback, network connectivity, and shutdown.

### Policy enforcement

The model explicitly checks whether a dependency requires a started service or a healthy service. A healthy dependency must declare a health check before the project can be validated.

The startup process checks prerequisite states before transitioning a service to `STARTING`. A failed probe moves the service to `UNHEALTHY` and causes the current startup operation to fail.

### Collections and complexity

`HashMap` holds dependency counts and graph adjacency data. A `TreeSet` selects ready services in deterministic alphabetical order. The final startup order is returned as an immutable list.

This design separates the graph algorithm from the domain rules that determine whether a service is eligible to start. That separation makes it easier to test configuration validity independently of runtime behavior.

The Java implementation does not connect to a Docker daemon, parse Compose files, execute containers, or implement the full Docker restart manager.

## PostgreSQL Data Model

The SQL script models configuration and deployment observations in a relational database. It is a reporting and validation layer, not a container runtime.

### Entity relationships

    projects
      |
      +-- networks
      |
      +-- services
      |     |
      |     +-- service_networks
      |     |
      |     +-- service_dependencies
      |     |
      |     +-- service_environment
      |
      +-- deployments
            |
            +-- deployment_service_status
            |
            +-- status_events

The model separates desired service configuration from deployment-specific observed states.

### Tables

| Table | Purpose |
|---|---|
| `projects` | Identifies each Compose project. |
| `networks` | Stores network names, drivers, and internal-network settings. |
| `services` | Stores image references, restart policies, and configured health-check information. |
| `service_networks` | Maps services to the networks they join. |
| `service_dependencies` | Records prerequisite services and readiness conditions. |
| `service_environment` | Stores non-secret configuration and optional secret metadata. |
| `deployments` | Records deployment versions and their overall states. |
| `deployment_service_status` | Stores observed state and health-check results for each service in a deployment. |
| `status_events` | Records structured lifecycle events and diagnostics. |

Primary keys identify records. Foreign keys enforce valid relationships. Unique constraints prevent duplicate service names within a project and duplicate network names within a project. Check constraints restrict names, network drivers, restart policies, and state values.

### Triggers and validation

The SQL includes triggers for several rules:

- Services must have network membership by the end of the transaction in which they are inserted or updated.
- A dependency requiring health must point to a service with a configured health check.
- A deployment's service observations must refer to services from the same project.
- Lifecycle events must refer to a service and deployment belonging to the same project.
- A deferred recursive graph check rejects dependency cycles introduced by inserted or updated dependency records.

The graph trigger runs at transaction completion, allowing multiple related dependency rows to be inserted within one transaction. Graph validation has costs that grow with the number of dependency relationships, so large systems may need additional safeguards or application-side validation.

The service-network constraint trigger checks network membership after changes to the service record. Applications that remove network memberships separately should validate the resulting service configuration before committing. A complete production implementation would also guard network-membership deletions and coordinate all configuration mutations through a transactionally validated workflow.

### Eligibility evaluation

`can_start_service()` evaluates whether the recorded prerequisites of a service have reached the required states in a particular deployment.

For `service_healthy`, the prerequisite must have an observed `healthy` state. For `service_started`, the prerequisite must exist in the deployment and must not remain in `created`.

`evaluate_project_deployment()` combines dependency eligibility, observed state, and the recorded health-check result. A service is marked eligible to serve only when it is healthy, its dependencies are satisfied, and its health-check result is true.

The sample creates two deployment records:

- Version 1 represents a successful deployment with healthy services.
- Version 2 represents a failed database health check with dependent services still in the created state.

The reporting queries make the difference visible without creating or modifying actual containers.

### Views, indexes, and reporting

`service_network_report` joins services to their network attachments. `latest_deployment_report` selects the newest recorded deployment version for each project.

The indexes support common access patterns:

- Looking up dependent services by prerequisite.
- Retrieving deployment versions by project and status.
- Filtering deployment observations by state.
- Reading lifecycle events in reverse chronological order.

Indexes consume storage and add write overhead. Their usefulness depends on table size, data distribution, and the actual query plan. For a small demonstration database, some indexes may not improve performance measurably.

### Transactions and failure handling

The schema and sample data are created inside a transaction. If a statement fails, PostgreSQL can roll back the transaction rather than leaving an incomplete initial dataset.

The `DO` block at the end emits a notice for a missing-network validation scenario. It is deliberately a non-destructive check, so the full sample script can complete successfully.

The database records simulated state observations. It does not automatically poll the Docker Engine or prove that a recorded healthy state still reflects a running container.

## Operational Workflows

### Inspect and validate a project

Use `docker compose config` to parse and resolve the Compose configuration. This can reveal invalid configuration structure and unresolved required variables.

Inspect the resulting configuration carefully because resolved environment values can contain sensitive information.

### Start the application

Use `docker compose up -d` to create and start the services in the background. Compose evaluates configured dependency conditions during startup.

Use `docker compose ps` to inspect service and container state. Use `docker compose logs --follow api` to examine application logs and `docker compose logs --follow db` to investigate database readiness or connection problems.

### Diagnose service connectivity

If the API cannot reach the database:

1. Confirm that both services are attached to the backend network.
2. Verify that the database hostname in the API configuration is `db`.
3. Check that PostgreSQL is listening on the expected container port.
4. Verify credentials and database permissions.
5. Inspect database logs and the API's connection errors.
6. Check health status and dependency conditions.

If the web service cannot reach the API, verify frontend network membership, API listener configuration, and the Nginx upstream address. A service being healthy does not establish that every endpoint or business operation is functioning correctly.

### Stop and remove resources

`docker compose stop` stops services without removing their containers. `docker compose down` stops and removes project containers and networks. Named volumes are normally retained unless volume-removal options are specified.

Avoid removing persistent database volumes unless their data is disposable or a verified backup exists.

## Failure Modes and Design Considerations

| Failure | Likely cause | Appropriate control |
|---|---|---|
| Invalid dependency | Missing service or circular graph | Validate configuration before deployment. |
| Database is not ready | Initialization or recovery is still running | Configure a meaningful health check and dependency condition. |
| API starts but cannot connect | Incorrect hostname, credentials, network, or port | Verify service DNS, network attachments, and application configuration. |
| Container repeatedly exits | Application error or invalid startup configuration | Inspect logs, exit status, and restart behavior. |
| Health check fails | Incorrect probe, failed dependency, or application malfunction | Test the probe independently and inspect service logs. |
| Database data disappears | Data stored only in a replaceable container layer | Use persistent volumes and verified backups. |
| Database is unnecessarily exposed | Host port publication or broad network connectivity | Remove unnecessary published ports and restrict network access. |
| Credentials appear in diagnostics | Secrets placed in exposed configuration or logs | Use secret-management controls and redact sensitive output. |
| A dependency becomes unavailable after startup | Runtime failure after initial readiness | Implement timeouts, retries, reconnection, and graceful degradation. |
| An image changes unexpectedly | Mutable image tag or uncontrolled update | Pin and test image versions or digests. |

## Security Considerations

Compose provides useful configuration and network boundaries, but secure deployment also requires controls beyond the YAML file.

- Use non-root application users where practical.
- Avoid unnecessary Linux capabilities and privileged containers.
- Use read-only filesystems when compatible with the application.
- Restrict published ports and database exposure.
- Store credentials using supported secrets or an external secret manager.
- Pin and scan images, and update them through a controlled process.
- Keep application and database permissions limited to required operations.
- Back up persistent data and test restoration.
- Avoid exposing environment dumps, secret values, or sensitive diagnostic output.
- Apply host-level and network-level controls appropriate to the deployment.

A network marked internal does not encrypt traffic, validate identities, or prevent a compromised application attached to that network from misusing its access.

## Performance Considerations

The dominant runtime costs in a real deployment usually come from application processing, database work, storage, network traffic, image downloads, and health-check configuration rather than the small dependency graph itself.

For orchestration:

- Keep dependency graphs accurate rather than unnecessarily restrictive.
- Avoid long startup delays caused by health checks that test unrelated services.
- Use bounded retries and suitable backoff for transient failures.
- Ensure health checks are inexpensive and do not create excessive database load.
- Avoid publishing ports that are not required.
- Measure resource usage and connection-pool behavior under representative load.

The graph algorithms in the simulators are designed for correctness and deterministic demonstration. The SQL model's recursive graph checks and status joins should be assessed with real query plans and representative data before use in a large configuration inventory.

## Scope and Limitations

The Python, JavaScript, C++17, and Java 17 programs simulate configuration validation and lifecycle decisions. They do not run containers, build images, manage volumes, create network interfaces, enforce host firewall rules, or replace the Docker Compose implementation.

The PostgreSQL schema stores configuration and observed deployment records. Its eligibility functions evaluate recorded data rather than querying live container health.

The Compose YAML example is a deployment-oriented reference and assumes a working API image and suitable Nginx configuration. The source implementations are independent, executable models that demonstrate how dependency graphs, network membership, readiness conditions, and failure handling can be represented and tested.

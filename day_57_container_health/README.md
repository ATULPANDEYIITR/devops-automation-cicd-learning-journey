# Container Health in DevOps Automation

## Scope

This project models container health as an operational control system rather than treating it as a single status value.

The implementation separates three concerns:

| Concern | Purpose | Typical mechanism |
|---|---|---|
| HEALTHCHECK | Determines whether the application responds correctly | Probe, interval, timeout, retries |
| Restart policy | Determines whether a failed container should be started again | `no`, `on-failure`, `always`, `unless-stopped` |
| Resource limits | Constrain infrastructure consumption | CPU and memory limits |

The central operational relationship is:

`Container process → Health probe → Health state → Recovery policy`

Resource enforcement operates alongside this workflow:

`Container → CPU / memory limits → Runtime enforcement`

A successful health check does not prove that a container has unlimited CPU or memory capacity. A restart policy does not itself determine whether an application is healthy. Resource limits do not replace application-level health checks.

## Operational Model

The project uses the following state concepts:

- `created`: the container exists but has not started.
- `running`: the container process is active.
- `restarting`: the runtime is performing recovery.
- `stopped`: the container is not running.
- `starting`: the application has not yet accumulated enough information to be considered healthy.
- `healthy`: the configured probe succeeds within the permitted timeout.
- `unhealthy`: the configured failure threshold has been reached.

The state and health values are deliberately separate.

A container can be `running` while `unhealthy`. This is important because a process can remain alive while its HTTP endpoint, database dependency, queue connection, or internal application subsystem is unavailable.

## HEALTHCHECK

A health check is an application-level observation mechanism.

The model uses four primary parameters:

| Parameter | Meaning |
|---|---|
| Interval | Time between probe attempts |
| Timeout | Maximum acceptable probe duration |
| Retries | Consecutive failures required to classify the service as unhealthy |
| Start period | Initial period during which startup failures are tolerated |

A successful check requires both a successful probe and a latency that does not exceed the configured timeout.

The Python implementation represents this with `HealthCheckConfig` and `HealthResult`. Its `record_health()` method maintains consecutive failures and applies the start-period rule.

The JavaScript implementation uses an asynchronous probe and `Promise.race()` so that a slow probe can be treated as a timeout. This reflects the event-driven nature of Node.js applications.

The C++ implementation makes health evaluation explicit through `HealthCheckConfig`, `HealthResult`, and `Container::applyHealthResult()`.

The Java implementation models the policy as an immutable `HealthCheckPolicy` record and validates its parameters at construction time.

The PostgreSQL implementation persists both the health policy and individual health-check results. The `record_health_result()` function evaluates the current result against historical failures and updates the container health state transactionally.

### Start-period behavior

Startup deserves separate handling because applications often require time to initialize.

A service that has not completed initialization should not immediately be classified as permanently unhealthy merely because its first probe fails.

The implementations therefore represent a `starting` state and use the configured start period before normal failure counting begins.

### Timeout behavior

A timeout is a failed health observation, not necessarily a process crash.

This distinction matters operationally:

`Slow application → failed health check → unhealthy state`

is different from:

`Process exit → container stopped → restart policy evaluation`

An automated system can react differently to each event.

## Restart Policies

Restart policies determine whether a container should be started again after failure.

| Policy | Behavior |
|---|---|
| `no` | Do not automatically restart |
| `on-failure` | Restart when the process exits with a non-zero exit code |
| `always` | Restart regardless of the exit code unless explicitly stopped according to runtime semantics |
| `unless-stopped` | Restart unless the container was intentionally stopped |

The implementations also introduce a bounded restart count. This is useful for automation because an endlessly failing service should not enter an uncontrolled restart loop.

A recovery decision can therefore be expressed as:

`Automatic restart = policy permits + failure condition matches + restart budget remains`

A manual stop is represented separately from an automated failure. The examples demonstrate that a manual stop prevents automatic recovery for policies that otherwise permit restarting.

### Restart loops

Repeated failure can produce:

`start → fail → restart → start → fail → restart`

Without a boundary, this can consume resources and hide the original failure.

The examples therefore maintain a restart count and maximum restart allowance.

A production implementation would normally complement this with exponential backoff, jitter, alerting, dependency isolation, and an operational policy for exhausted restart budgets.

## Resource Limits

Resource limits constrain container consumption independently of application health.

The examples use:

- CPU in millicores
- Memory in megabytes

A configuration such as `500` millicores represents a CPU allocation limit expressed in a runtime-neutral unit for the learning model.

Memory limits are particularly important because uncontrolled memory consumption can affect neighboring workloads on the same host.

The source files validate that CPU and memory limits are positive. The PostgreSQL model enforces the same rule with `CHECK` constraints.

The key distinction is:

`HEALTHCHECK → observes behavior`

`Resource limits → constrain consumption`

A service may be healthy while operating close to its memory limit. Conversely, a service can have generous resources while its health endpoint is failing because an external dependency is unavailable.

## Python Implementation

The Python program is a self-contained simulation of container runtime behavior.

### Domain types

The program uses:

- `Enum` values for health, state, and restart policy.
- `dataclass` structures for resource limits, health policies, and results.
- A `Container` class for lifecycle and policy behavior.
- `ContainerRuntime` as the runtime-level coordinator.

### Validation

Resource limits reject non-positive CPU and memory values.

Health-check configuration rejects:

- non-positive intervals
- non-positive timeouts
- timeouts longer than intervals
- zero or negative retry counts
- negative startup periods

The container also validates names, images, and restart limits.

### Recovery

The runtime evaluates a probe, records the result, changes health state, and invokes recovery when the container becomes unhealthy.

The implementation deliberately separates probe execution from policy evaluation so that the health mechanism is not itself responsible for deciding how the service should be restarted.

### Failure cases

The example covers:

- invalid resource limits
- invalid health-check configuration
- startup-period handling
- repeated health failures
- restart limits
- manual stops
- successful health recovery
- assertions for expected state

## JavaScript Implementation

The JavaScript file uses an event-driven architecture.

### Event model

`Container` extends Node.js `EventEmitter`.

Important events include:

- `started`
- `stopped`
- `healthy`
- `unhealthy`
- `restarting`

`ContainerOrchestrator` subscribes to unhealthy events and applies recovery behavior.

This creates a realistic automation flow:

`Probe → Event → Orchestrator → Restart decision`

### Asynchronous health checks

The health-check operation is asynchronous.

`Promise.race()` combines the probe operation with a timeout promise. A slow probe therefore becomes a failed observation rather than waiting indefinitely.

This is particularly useful in event-driven services where a blocked health probe could otherwise delay other work.

### Data structures

A `Map` stores containers by name. This provides direct lookup without scanning an array.

The implementation also uses immutable objects for enumerated configuration values and validates constructor arguments before allowing the container into the runtime.

### Backoff

The restart path calculates a bounded exponential delay value. The executable model does not sleep for that delay, which keeps testing deterministic, but it exposes the calculation that a production scheduler could use.

## C++17 Implementation

The C++ program treats container governance as a strongly typed runtime engine.

### Domain model

The implementation uses:

- scoped enums for states and policies
- structures for resource and health configuration
- a `Container` class for state transitions
- `GovernanceEngine` for container registration and health evaluation
- STL `map` for deterministic container lookup

The strong type separation reduces accidental mixing of health state, lifecycle state, and restart policy.

### State transition behavior

Health evaluation is rejected when the container is not running.

A valid health result resets the failure counter and produces `Healthy`.

A failed result increments the failure counter. Only after the configured threshold is reached does the container become `Unhealthy`.

Recovery then checks the restart policy and restart budget.

### Error handling

The program uses standard C++ exceptions for invalid configuration, unknown containers, invalid state transitions, and invalid resource settings.

The `main()` function provides a controlled failure boundary and returns a non-zero exit code when an unrecoverable configuration or runtime error occurs.

## Java 17 Implementation

The Java implementation represents an enterprise-oriented service model.

### Immutable configuration

`ResourceLimits`, `HealthCheckPolicy`, `HealthResult`, and `StatusCheck` use Java records where immutable value semantics are appropriate.

Constructor validation ensures invalid policies cannot be created.

### Explicit service layer

`ContainerService` handles lifecycle operations and recovery.

`RuntimePolicyEvaluator` evaluates whether an operationally healthy container also satisfies a set of independent status checks.

This separates:

`Container state`

from:

`Application health`

from:

`Operational policy`

That separation is useful in larger enterprise systems where multiple automation rules may contribute to a deployment or recovery decision.

### Policy conflicts

A container may be healthy while a separate operational check fails. The policy evaluator therefore checks both health state and all required status checks.

This prevents one successful health probe from being treated as proof that every operational condition is satisfied.

## PostgreSQL Implementation

The PostgreSQL model persists container governance data and applies important rules inside the database.

### Relational model

The core relationship is:

`Repositories → Services → Containers`

Container-specific operational data is associated with:

`Containers → Resource Limits`

`Containers → Health-Check Policies`

`Containers → Health-Check Results`

`Containers → Restart Events`

This makes historical operational behavior queryable rather than retaining only the latest status.

### Constraints

The schema uses:

- primary keys
- foreign keys
- unique constraints
- `CHECK` constraints
- PostgreSQL enum types
- indexes
- triggers
- stored functions

Examples include positive resource limits, valid retry counts, valid timeout relationships, and restart-count boundaries.

### Transactional health evaluation

`record_health_result()` locks the container row with `FOR UPDATE` before calculating the new health state.

This protects the state transition when multiple operational processes attempt to update the same container concurrently.

The health result and resulting state update occur in one database operation.

### Restart transaction

`restart_container()` locks the container, verifies restart eligibility, updates the lifecycle state, increments the restart count, records a restart event, and returns the container to the running state.

The operation can therefore be executed inside a transaction without leaving a partially recorded recovery event.

### Reporting

The `container_health_report` view combines repository, service, container, resource, and health policy information into an operational reporting surface.

The script also provides queries for:

- latest health results
- restart-budget usage
- unhealthy containers
- containers close to their restart limit
- restart eligibility under different exit codes

## Failure Handling

The project distinguishes several failure classes.

| Failure | Meaning | Primary response |
|---|---|---|
| Probe timeout | Application did not respond within policy | Count health failure |
| Repeated probe failure | Application is unhealthy | Mark unhealthy |
| Process exit with non-zero code | Runtime process failure | Apply restart policy |
| Restart budget exhausted | Automated recovery is bounded | Stop automatic restart |
| Invalid resource limit | Configuration error | Reject configuration |
| Invalid health policy | Configuration error | Reject policy |
| Manual stop | Intentional operator action | Suppress automatic restart |
| Missing database policy | Persistence/configuration failure | Reject health evaluation |

This separation is important for automation because different failure classes require different actions.

## Performance Considerations

Health checks create recurring workload.

If a deployment contains `N` containers and each container performs one probe every `I` seconds, the approximate probe rate is:

`N / I probes per second`

Short intervals improve detection speed but increase probe traffic and execution overhead.

Retry thresholds reduce sensitivity to isolated transient failures but increase detection time.

Database history can grow continuously. The PostgreSQL design therefore indexes health results by container and descending check time, which supports latest-result queries efficiently.

The JavaScript implementation uses a `Map` for container lookup, providing expected constant-time lookup by container name.

The C++ implementation uses `std::map`, which provides logarithmic lookup and deterministic ordering. This is appropriate for a governance-oriented registry where predictable ordering is useful. A very large runtime could instead use `std::unordered_map` when ordered traversal is not required.

## Security Considerations

Container health automation should not expose sensitive information through health endpoints or logs.

Health results should avoid returning:

- passwords
- access tokens
- private keys
- database credentials
- complete connection strings
- confidential request payloads

A health endpoint should generally report operational state rather than diagnostic secrets.

Resource limits also contribute to isolation by preventing one workload from consuming unbounded infrastructure capacity.

Restart automation must be bounded because an uncontrolled restart loop can become an availability problem itself.

Database functions should execute with carefully controlled privileges in production. Operational accounts should receive only the permissions required to record health results, evaluate policy, and perform authorized lifecycle operations.

## Production Design Boundaries

The project is intentionally a runtime-neutral learning model.

A real container platform may provide additional behavior such as:

- cgroup-based CPU enforcement
- cgroup-based memory enforcement
- image-pull failures
- process exit codes
- dependency health
- restart backoff
- orchestration-level scheduling
- replica management
- node failures
- graceful termination periods
- readiness and liveness distinctions
- centralized logging
- metrics and alerting

A health check should not be treated as a complete observability system.

Health answers whether a service currently satisfies a defined probe. Metrics provide quantitative operational information. Logs provide event context. Traces provide request-level execution context.

A mature DevOps system combines these signals instead of treating one health result as the entire operational picture.

## Relationship Between the Five Implementations

| File | Primary perspective | Main technical emphasis |
|---|---|---|
| Python | Runtime simulation | Classes, validation, health state, restart behavior |
| JavaScript | Event-driven automation | Async probes, events, promises, orchestration |
| C++17 | Governance engine | Strong types, STL, explicit runtime state |
| Java 17 | Enterprise domain model | Records, services, policy objects, explicit state transitions |
| PostgreSQL | Persistent operational model | Relational constraints, transactions, triggers, reporting |

The implementations intentionally model the same operational concepts from different engineering perspectives rather than mechanically translating one source file into another.

## Practical Workflow

A representative automated workflow is:

`Container created`
→ `Resource limits validated`
→ `Health policy loaded`
→ `Container started`
→ `Start period`
→ `HEALTHCHECK executed`
→ `Result recorded`
→ `Health state evaluated`
→ `Unhealthy threshold reached`
→ `Restart policy evaluated`
→ `Restart budget checked`
→ `Container restarted or left stopped`
→ `Health monitoring resumes`

For an intentional operator stop, the workflow changes:

`Container running`
→ `Manual stop`
→ `Stopped`
→ `Automatic restart suppressed`

This distinction prevents recovery automation from fighting an explicit operational decision.

## Limitations

The examples do not attempt to reproduce the complete behavior of a specific container engine.

Resource values are modeled as validated domain data. Actual CPU and memory enforcement belongs to the container runtime and operating system.

The health probes are deterministic demonstrations rather than real network or process probes.

The restart model includes bounded recovery logic but does not implement a full scheduler, distributed leader election, node placement, or production-grade backoff coordination.

The PostgreSQL model stores and evaluates operational state but does not itself control a container runtime.

These boundaries keep the four mechanisms distinct while still showing how they can participate in one DevOps automation workflow.

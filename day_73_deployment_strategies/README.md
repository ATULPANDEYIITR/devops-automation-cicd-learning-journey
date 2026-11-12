# Deployment Strategies: Recreate, Rolling and Blue-Green Deployments

## 1. Technical Scope

Deployment strategies define how a new application release replaces an existing release in an operational environment.

A deployment involves several coordinated activities:

- Selecting an application release.
- Preparing infrastructure.
- Provisioning application instances.
- Validating application health.
- Managing service availability.
- Allocating production traffic.
- Replacing or retiring previous instances.
- Recording deployment events.
- Recovering from unsuccessful releases.

Three deployment strategies are implemented:

| Strategy | Replacement mechanism | Infrastructure requirement | Availability characteristics |
|---|---|---|---|
| Recreate | Stops existing instances before starting replacements | Usually one environment | Application downtime can occur |
| Rolling | Replaces instances in controlled batches | Existing infrastructure with optional additional capacity | Maintains service availability when configured correctly |
| Blue-Green | Creates a separate environment and switches traffic | Capacity for two environments | Supports rapid traffic reversal |

The five implementations use different engineering perspectives:

| Deliverable | Engineering perspective |
|---|---|
| Python | Deployment simulation, lifecycle management and persistent execution history |
| JavaScript | Asynchronous orchestration, event-driven execution and traffic management |
| C++17 | Infrastructure governance, resource constraints and deployment eligibility |
| Java 17 | Enterprise domain modeling, immutable records, policies and state transitions |
| PostgreSQL | Relational deployment management, transactional workflow and operational reporting |

## 2. Deployment Architecture

A deployment system separates the desired application state from the actual infrastructure state.

The desired state identifies the release and configuration that should operate in an environment. The actual state describes the instances, their health, their versions and the traffic currently reaching them.

A deployment controller attempts to reconcile these states.

### 2.1 Core domain entities

| Entity | Responsibility |
|---|---|
| Application | Identifies the software service |
| Release | Identifies a specific application version and immutable artifact |
| Environment | Represents staging, production or another deployment target |
| Deployment | Records an execution attempting to introduce a release |
| Instance | Represents a running application instance |
| Deployment policy | Defines infrastructure and availability constraints |
| Health check | Records application and infrastructure validation |
| Traffic allocation | Describes the proportion of traffic assigned to a release |
| Deployment event | Records an operational event |
| Deployment batch | Tracks an individual stage of a rolling deployment |

### 2.2 Desired state and actual state

These concepts must remain separate.

**Desired state** includes:

- Target application version.
- Desired replica count.
- Deployment strategy.
- Deployment environment.
- Infrastructure capacity requirements.
- Availability policy.

**Actual state** includes:

- Currently running versions.
- Number of healthy instances.
- Number of unavailable instances.
- Available infrastructure capacity.
- Current traffic distribution.
- Deployment progress.

For example, a deployment may request four instances of version `2.0.0`, while the production environment currently runs four instances of version `1.0.0`.

The deployment is not complete merely because the requested release has been recorded. The infrastructure must reach the intended state, pass health validation and satisfy the traffic-switching conditions.

### 2.3 Deployment lifecycle

The general lifecycle is:

    Release Selection
          |
          v
    Policy Validation
          |
          v
    Infrastructure Preparation
          |
          v
    Instance Provisioning
          |
          v
    Application Health Validation
          |
          v
    Traffic Management
          |
          v
    Deployment Verification
          |
          v
    Successful Deployment
          |
          +------ Failure
                    |
                    v
                 Rollback

A deployment controller should maintain an explicit record of every state transition.

## 3. Recreate Deployment Strategy

### 3.1 Operating mechanism

Recreate deployment terminates the existing application instances before provisioning the replacement instances.

The sequence is:

    Existing Version: 1.0.0
              |
              v
       Stop Old Instances
              |
              v
       Release Infrastructure
              |
              v
       Provision Version 2.0.0
              |
              v
       Run Health Checks
              |
              v
       Activate New Version

The old and new application environments are not intended to serve production traffic simultaneously.

### 3.2 Availability characteristics

The primary disadvantage is downtime.

During the replacement interval, the application may have no healthy instances available to receive requests.

The actual downtime depends on:

- Instance termination time.
- Application startup time.
- Dependency initialization.
- Readiness checks.
- Traffic-router configuration.
- Recovery behavior.

Recreate deployment is appropriate when temporary service interruption is acceptable and infrastructure simplicity is important.

It is generally less suitable for services requiring continuous availability.

### 3.3 Python implementation

The Python implementation provides a `_recreate()` method.

It:

1. Preserves the previous instance collection.
2. Stops the existing instances.
3. Creates the requested number of replacements.
4. Starts the new instances.
5. Performs health validation.
6. Restores the original instance collection when an exception occurs.

The simulator uses an exception-based failure mechanism to demonstrate how a failed replacement can be handled.

Its local restoration behavior is a simulation of rollback. Real infrastructure requires explicit restoration of the previous release through the deployment controller.

### 3.4 Important failure conditions

| Failure | Consequence | Required response |
|---|---|---|
| Startup failure | New instances cannot start | Restore the previous release |
| Readiness failure | Application cannot safely receive traffic | Reject activation |
| Insufficient capacity | Requested instances cannot be provisioned | Reject deployment |
| Configuration error | Application initialization fails | Correct configuration before retrying |

## 4. Rolling Deployment Strategy

### 4.1 Operating mechanism

Rolling deployment replaces application instances incrementally.

Instead of terminating the entire existing environment, the deployment controller processes groups of instances called batches.

For example, consider four production instances:

| Stage | Version 1.0.0 | Version 2.0.0 |
|---|---:|---:|
| Initial | 4 | 0 |
| Batch 1 | 3 | 1 |
| Batch 2 | 2 | 2 |
| Batch 3 | 1 | 3 |
| Final | 0 | 4 |

Each batch must satisfy its health requirements before the deployment proceeds.

### 4.2 Batch management

The following configuration parameters influence rolling deployments:

| Parameter | Meaning |
|---|---|
| Desired replicas | Required final instance count |
| Batch size | Number of instances processed in a deployment batch |
| Maximum surge | Additional instances permitted above the desired capacity |
| Maximum unavailable | Maximum permitted unavailable instances |
| Minimum healthy percentage | Required proportion of healthy instances |

Maximum surge and maximum unavailable are different mechanisms.

Maximum surge controls additional temporary infrastructure capacity.

Maximum unavailable controls how many instances may be unavailable during replacement.

For a desired capacity of four instances:

- Maximum surge of one permits a temporary fifth instance.
- Maximum unavailable of one permits one instance to be unavailable during replacement.

These values must be evaluated against actual infrastructure capacity.

### 4.3 Availability constraints

A simplified capacity relationship is:

\[
N_{\text{running}} \leq N_{\text{desired}} + S
\]

Where:

- \(N_{\text{running}}\) is the number of allocated instances.
- \(N_{\text{desired}}\) is the desired instance count.
- \(S\) is the maximum surge.

A simplified minimum availability requirement is:

\[
N_{\text{healthy}} \geq
N_{\text{desired}} - U
\]

Where \(U\) represents the permitted number of unavailable instances.

These are simplified planning relationships. Actual deployment controllers must also consider batch scheduling, readiness, autoscaling, terminating instances and infrastructure-specific rollout behavior.

### 4.4 Python implementation

The `_rolling()` method maintains the original instance collection and processes replacements incrementally.

The implementation includes:

- Batch selection.
- Instance removal.
- Replacement provisioning.
- Capacity validation.
- Batch health checks.
- Final replica-count verification.
- Restoration following a failed batch.

The implementation demonstrates transactional simulation of instance state.

A production implementation must account for the fact that already terminated infrastructure cannot necessarily be restored by resetting an in-memory collection.

### 4.5 JavaScript implementation

The JavaScript implementation uses asynchronous provisioning.

The `rolling()` method processes replacement batches using `async` and `await`.

The `DeploymentEngine` extends `EventEmitter`, allowing monitoring systems to observe:

- Deployment initiation.
- Batch completion.
- Health-check outcomes.
- Deployment failure.
- Final deployment state.

This approach separates deployment execution from operational monitoring.

### 4.6 Rolling deployment failure scenarios

| Failure | Effect |
|---|---|
| One batch fails readiness | Further rollout should stop |
| Capacity is exceeded | Replacement cannot proceed |
| Too many instances become unavailable | Availability requirement is violated |
| Final replica count is incorrect | Deployment must not be marked successful |
| New version produces elevated errors | Rollout should be halted or reversed |

Rolling deployments reduce the scale of individual replacement operations, but they do not eliminate deployment risk.

A release may introduce a defect that affects every batch.

Progressive monitoring and rollback criteria remain necessary.

## 5. Blue-Green Deployment Strategy

### 5.1 Operating mechanism

Blue-green deployment maintains two separate application environments.

- Blue represents the currently active environment.
- Green represents the newly provisioned environment.

The new release is installed and validated in green while blue continues serving production traffic.

Once validation succeeds, traffic is switched to green.

    Production Traffic
           |
           v
       Traffic Router
           |
           v
       Blue Environment
          Version 1.0.0

    Prepare Green Environment
           |
           v
       Green Environment
          Version 2.0.0
           |
           v
       Readiness Validation
           |
           v
       Traffic Switch
           |
           v
       Green Becomes Active

The previous environment can be retained temporarily for recovery.

### 5.2 Traffic switching

Blue-green deployment separates environment preparation from production activation.

This separation provides an important operational advantage: the replacement environment can be validated before receiving production traffic.

A traffic router can perform the switch through:

- Load-balancer configuration.
- Reverse-proxy routing.
- Service-mesh routing.
- DNS-based traffic management.
- Platform-specific service routing.

DNS-based switching may be affected by caching and TTL behavior. It should not be assumed to provide instantaneous reversal.

### 5.3 Traffic allocation

A traffic allocation model can represent progressive traffic movement.

For example:

| Release | Traffic allocation |
|---|---:|
| Blue: 1.0.0 | 90% |
| Green: 2.0.0 | 10% |
| Total | 100% |

A subsequent shift may allocate 50% to each release, followed by 100% to green.

Partial traffic allocation is associated with progressive delivery and canary deployment techniques.

A blue-green deployment does not automatically become a canary deployment merely because both environments exist. The traffic policy determines how the release is exposed.

### 5.4 Python implementation

The `_blue_green()` method:

1. Preserves the active environment.
2. Checks the additional capacity requirement.
3. Provisions the complete replacement environment.
4. Validates the green instances.
5. Changes the simulated traffic version.
6. Retains the new environment after successful activation.
7. Restores the previous environment and traffic version after failure.

### 5.5 JavaScript implementation

The `TrafficRouter` uses a JavaScript `Map` to maintain release-specific traffic weights.

The `shiftTraffic()` method validates that the combined allocation equals 100%.

The deployment engine separately manages:

- Environment provisioning.
- Green environment validation.
- Traffic distribution.
- Active release state.
- Failed-switch recovery.

This separation makes traffic routing an independent responsibility rather than embedding it inside instance provisioning.

### 5.6 Java implementation

The `TrafficManager` provides synchronized traffic-allocation operations.

The `DeploymentPolicy` determines whether blue-green deployment is permitted and whether sufficient infrastructure capacity exists.

The `DeploymentService` validates the new environment before applying the traffic transition.

### 5.7 Important limitations

Blue-green deployment generally requires more temporary infrastructure than recreate or rolling deployment.

It also introduces operational complexity:

- Database compatibility.
- Session management.
- Background processing.
- External integrations.
- Message-consumer coordination.
- Cache consistency.
- Shared storage.
- Traffic-router synchronization.

A traffic reversal does not reverse database modifications.

Consequently, database changes should use backward-compatible migration patterns, such as expand-and-contract migrations.

## 6. Deployment Strategy Comparison

| Evaluation criterion | Recreate | Rolling | Blue-Green |
|---|---|---|---|
| Environment replacement | Complete replacement | Incremental replacement | Separate replacement environment |
| Additional capacity | Usually unnecessary | Optional | Usually substantial |
| Potential downtime | High | Low when configured correctly | Low when switching is properly implemented |
| Traffic switching | After replacement | Gradual through available instances | Explicit environment switch |
| Rollback mechanism | Redeploy previous release | Replace new instances with previous release | Route traffic back to previous environment |
| Operational complexity | Low | Medium | High |
| Infrastructure cost | Lower temporary requirement | Moderate | Higher temporary requirement |
| Best application fit | Applications accepting downtime | Continuously operating services | Services requiring controlled release activation |

No deployment strategy guarantees zero downtime.

Availability depends on application architecture, infrastructure, database compatibility, readiness checks, traffic management and failure-recovery design.

## 7. Health Checks and Deployment Validation

Health validation determines whether a newly provisioned instance is suitable for service.

Three commonly used health-check categories are:

| Check | Purpose |
|---|---|
| Liveness | Determines whether the application process is functioning |
| Readiness | Determines whether the instance can safely receive requests |
| Startup | Determines whether application initialization has completed |

These checks serve different purposes.

A running process is not necessarily ready to serve traffic.

For example, a payment service may have started successfully but may not yet have established its database connection.

### 7.1 Application-level validation

A deployment controller can evaluate:

- HTTP response codes.
- API readiness endpoints.
- Database connectivity.
- Dependency availability.
- Error percentages.
- Response latency.
- Queue processing status.
- Application-specific smoke tests.

A deployment should not be considered successful solely because infrastructure provisioning returned successfully.

### 7.2 Health thresholds

The implementations use a configurable health threshold.

The health ratio is:

\[
H =
\frac{N_{\text{healthy}}}
{N_{\text{total}}}
\times 100
\]

Where:

- \(H\) is the percentage of healthy instances.
- \(N_{\text{healthy}}\) is the healthy instance count.
- \(N_{\text{total}}\) is the evaluated instance count.

For a strict deployment policy, all replacement instances must be healthy before activation.

The threshold should reflect the application's actual availability requirements.

## 8. Deployment Policies and Governance

Deployment policies constrain the actions permitted by the deployment controller.

A policy can define:

- Maximum infrastructure capacity.
- Maximum surge.
- Maximum unavailable instances.
- Batch size.
- Minimum healthy percentage.
- Permitted deployment strategies.
- Production deployment restrictions.
- Health-check requirements.
- Manual approval requirements.
- Rollback authorization.

### 8.1 Policy enforcement

Policy evaluation must occur before infrastructure changes.

The implementations validate configuration and reject invalid requests.

Examples include:

| Policy violation | Expected response |
|---|---|
| Desired replicas exceed capacity | Reject deployment |
| Blue-green capacity is insufficient | Reject deployment |
| Recreate is prohibited | Reject deployment |
| Invalid traffic percentage | Reject traffic update |
| Health checks fail | Stop activation |
| Another deployment is running | Reject concurrent execution |

### 8.2 Concurrency management

Two simultaneous deployment operations targeting the same environment can produce inconsistent infrastructure state.

The JavaScript implementation uses an execution lock.

The Java implementation uses `ReentrantLock`.

The PostgreSQL implementation creates a partial unique index on active deployments for each environment.

These mechanisms illustrate three different approaches:

- Runtime execution control.
- Thread-level synchronization.
- Database-level uniqueness enforcement.

A distributed production deployment controller requires distributed coordination or equivalent concurrency control. An in-process lock cannot prevent another controller running on a separate machine from starting a conflicting deployment.

## 9. Rollback and Recovery

Rollback attempts to restore a previously operational release.

The mechanism depends on the deployment strategy.

| Strategy | Rollback mechanism |
|---|---|
| Recreate | Provision the previous version |
| Rolling | Replace updated instances with previous-version instances |
| Blue-Green | Route traffic back to the previous environment |

### 9.1 Rollback conditions

Rollback may be triggered by:

- Failed readiness checks.
- Elevated error rates.
- Increased response latency.
- Failed smoke tests.
- Dependency failures.
- Application crashes.
- Unexpected business-level behavior.

### 9.2 Recovery limitations

Application rollback and database rollback are not equivalent.

A previous application release may be incompatible with a newly modified database schema.

Production systems should therefore use migration patterns that support both old and new application versions during the deployment transition.

External side effects, such as processed payments, sent messages or completed transactions, cannot necessarily be reversed by restoring an earlier application version.

Rollback should be designed as a recovery workflow rather than treated as an automatic reversal of every system change.

## 10. Python Implementation Architecture

The Python script provides a self-contained deployment simulator.

### 10.1 Main classes

| Component | Responsibility |
|---|---|
| `DeploymentConfig` | Validates deployment parameters |
| `Instance` | Represents an application instance |
| `DeploymentRecord` | Stores execution details |
| `DeploymentManager` | Controls deployment lifecycle |
| `DeploymentError` | Represents general deployment failures |
| `HealthCheckError` | Represents health-validation failures |
| `CapacityError` | Represents infrastructure constraints |

### 10.2 Core methods

| Method | Purpose |
|---|---|
| `_recreate()` | Performs complete replacement |
| `_rolling()` | Replaces instances in batches |
| `_blue_green()` | Provisions and activates a separate environment |
| `_health_check()` | Evaluates instance health |
| `_capacity_check()` | Enforces infrastructure capacity |
| `rollback()` | Restores an earlier release |
| `save_history()` | Persists deployment records |

### 10.3 Persistent execution history

The script writes deployment history as JSON.

The history includes:

- Deployment identifiers.
- Application names.
- Release versions.
- Strategies.
- Deployment status.
- Start and completion timestamps.
- Previous versions.
- Failure messages.
- Infrastructure metrics.
- Operational events.

The file is written through a temporary file and replaced after completion.

This reduces the risk of partially written history files.

The JSON file is intended for local simulation. Production deployment records should be stored in a durable, access-controlled database or logging system.

## 11. JavaScript Implementation Architecture

The JavaScript implementation focuses on asynchronous orchestration and event-driven behavior.

### 11.1 Main components

| Component | Responsibility |
|---|---|
| `DeploymentPolicy` | Evaluates infrastructure constraints |
| `TrafficRouter` | Manages release-specific traffic weights |
| `DeploymentEngine` | Orchestrates deployment execution |
| `DeploymentError` | Provides structured deployment failures |

### 11.2 Event-driven monitoring

The `DeploymentEngine` extends Node.js `EventEmitter`.

Events are emitted when important operational conditions occur.

Examples include:

- `deployment-started`
- `health-check`
- `green-provisioning`
- `rolling-batch-completed`
- `traffic-shift-started`
- `deployment-failed`
- `rollback-completed`

Monitoring components can subscribe to these events without becoming directly responsible for provisioning.

### 11.3 Asynchronous execution

The `provision()` method returns a Promise.

The deployment methods use `async` and `await` to coordinate infrastructure operations.

This design is useful when deployment operations depend on external APIs, container platforms or infrastructure controllers.

The demonstration uses simulated provisioning and health checks. Real infrastructure operations require authenticated platform integrations and persistent execution coordination.

## 12. C++17 Implementation Architecture

The C++17 program models deployment governance and resource constraints using strongly typed domain objects.

### 12.1 Main structures

| Structure | Responsibility |
|---|---|
| `Instance` | Represents an infrastructure instance |
| `DeploymentPolicy` | Defines resource and availability limits |
| `DeploymentRequest` | Represents the desired deployment |
| `DeploymentResult` | Represents execution results |
| `DeploymentEngine` | Controls infrastructure transitions |

### 12.2 State and resource management

The implementation uses:

- `std::vector` for instance collections.
- `std::map` for traffic allocations.
- `std::mt19937` for reproducible failure simulation.
- `std::remove_if` for instance replacement.
- Exceptions for invalid deployment conditions.
- Copies of previous state for simulation-level recovery.

The implementation distinguishes deployment validation from execution.

A request is checked against policy constraints before infrastructure changes occur.

### 12.3 Performance considerations

For \(n\) instances, the program uses vector-based operations.

The main costs include:

- Instance traversal: \(O(n)\).
- Health evaluation: \(O(n)\).
- Batch selection: \(O(b)\), where \(b\) is the batch size.
- Instance removal: \(O(n)\).
- Traffic lookup and update: typically \(O(\log k)\), where \(k\) is the number of release allocations.

The implementation prioritizes clear state management and standard-library portability over specialized infrastructure optimizations.

## 13. Java 17 Enterprise Architecture

The Java implementation uses explicit domain types and service separation.

### 13.1 Domain modeling

Java records represent immutable data structures:

- `DeploymentRequest`
- `DeploymentEvent`
- `Instance`
- `DeploymentReport`

Enums represent deployment strategies, deployment states and instance states.

This reduces ambiguity in the domain model.

### 13.2 Service responsibilities

| Service | Responsibility |
|---|---|
| `DeploymentPolicy` | Authorizes deployment operations |
| `InfrastructureService` | Creates instances and checks capacity |
| `HealthService` | Evaluates application readiness |
| `TrafficManager` | Manages traffic allocations |
| `DeploymentService` | Coordinates deployment lifecycle |

### 13.3 Concurrency and state management

`ReentrantLock` prevents simultaneous deployments within the same service instance.

The `TrafficManager` uses synchronized operations to maintain consistent traffic allocations.

The deployment service captures the previous state before attempting a deployment.

On failure, the service restores its simulated infrastructure and traffic state.

These operations demonstrate enterprise-oriented state management. Distributed deployments require durable orchestration and cross-process coordination.

### 13.4 Policy separation

The deployment service does not independently decide every operational restriction.

Instead, the policy object determines whether the requested strategy is permitted and whether sufficient capacity exists.

This separation makes policy evaluation easier to test and maintain.

## 14. PostgreSQL Relational Architecture

The PostgreSQL script models the deployment lifecycle as a relational workflow.

### 14.1 Database relationships

The central relationships are:

    Applications
        |
        +---- Environments
        |         |
        |         +---- Deployment Policies
        |         |
        |         +---- Deployment Instances
        |         |
        |         +---- Traffic Allocations
        |         |
        |         +---- Deployments
        |                   |
        |                   +---- Deployment Batches
        |                   |
        |                   +---- Health Checks
        |                   |
        |                   +---- Deployment Events
        |
        +---- Releases
                  |
                  +---- Deployments

### 14.2 Table responsibilities

| Table | Stored information |
|---|---|
| `applications` | Application identity |
| `environments` | Deployment environments |
| `releases` | Version and artifact metadata |
| `deployment_policies` | Infrastructure and deployment restrictions |
| `deployments` | Deployment execution records |
| `deployment_instances` | Application infrastructure |
| `deployment_batches` | Rolling deployment progress |
| `deployment_health_checks` | Health-validation results |
| `traffic_allocations` | Release-specific traffic percentages |
| `deployment_events` | Operational audit events |

### 14.3 Integrity constraints

The schema uses primary keys, foreign keys, unique constraints and check constraints.

Examples include:

- Application names must be unique.
- Application versions must be unique within an application.
- Release artifact digests must have the expected hexadecimal format.
- Artifact URIs must use HTTPS.
- Deployment replica counts must be positive.
- Traffic percentages must remain between zero and 100.
- Rolling batch counts must remain within planned limits.
- Health percentages must remain within valid boundaries.

The deployment-release validation trigger checks that a release, environment and policy belong to the same application and environment.

### 14.4 State-transition trigger

The `validate_deployment_transition()` function restricts invalid deployment state changes.

A successful deployment cannot arbitrarily return to provisioning.

Terminal states are protected from ordinary transitions.

Completion timestamps are assigned when deployments reach terminal states.

The trigger demonstrates database-level workflow integrity.

### 14.5 Deployment eligibility

The `check_deployment_eligibility()` function evaluates:

- Policy activation.
- Requested capacity.
- Production deployment permissions.
- Strategy restrictions.
- Blue-green capacity.
- Health-check results.
- Concurrent deployments.
- Active traffic allocation.

It returns an eligibility result and a reason.

Eligibility is different from execution success.

A deployment can satisfy its policy requirements and still fail during infrastructure provisioning.

### 14.6 Transactional traffic switching

The `switch_deployment_traffic()` procedure validates the deployment and records a traffic allocation.

The procedure uses row-level locking through `FOR UPDATE`.

The traffic-switching operation and its associated records should be executed within an explicit transaction.

A failed operation should be rolled back so that partial database changes are not committed.

### 14.7 Reporting and indexes

The database provides reporting views for:

- Deployment summaries.
- Environment instance counts.
- Deployment success metrics.

Indexes support common operational queries.

The partial index on active deployments restricts unfinished deployments to one per environment.

The health-check index supports failure investigations.

These indexes improve selected query patterns but introduce additional write overhead. Their value should be evaluated against actual workload and query plans.

## 15. Failure Handling Across the Implementations

| Failure condition | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Invalid configuration | Validation exceptions | Type and range errors | Domain exceptions | Record and policy validation | Check constraints |
| Capacity exceeded | `CapacityError` | Policy rejection | Deployment exception | `CapacityException` | Eligibility function |
| Startup failure | Simulated exception | Promise rejection | Simulated failure | Service validation | Recorded operational result |
| Health failure | `HealthCheckError` | Health validation failure | Deployment exception | `HealthException` | Health-check records |
| Concurrent execution | Not distributed | Execution lock | Single-process execution | `ReentrantLock` | Unique partial index |
| Traffic inconsistency | Version restoration | Traffic snapshot restoration | Traffic map restoration | Synchronized traffic manager | Transactional procedure |
| Deployment failure | State restoration | Exception and recovery | Exception and recovery | Exception and recovery | Transaction rollback |

The implementations demonstrate failure handling within their respective execution models.

In a production environment, recovery must also account for external infrastructure operations that cannot be reversed by restoring local application state.

## 16. Security and Production Considerations

### 16.1 Artifact integrity

Release artifacts should be immutable and verified before deployment.

The PostgreSQL schema records a SHA-256-format artifact digest.

A production deployment controller should independently calculate or verify the digest against the downloaded artifact.

A digest stored in a database does not establish artifact authenticity by itself.

### 16.2 Access control

Deployment permissions should distinguish between:

- Release creators.
- Deployment operators.
- Production approvers.
- Infrastructure administrators.
- Audit personnel.

Production deployment permissions should follow least-privilege principles.

### 16.3 Secrets management

Credentials, API tokens and database passwords should not be embedded in deployment configurations, source files or deployment logs.

Sensitive values should be retrieved from an authorized secrets-management system.

### 16.4 Auditability

Deployment records should identify:

- Who initiated the deployment.
- Which application was affected.
- Which release was selected.
- Which environment was targeted.
- Which strategy was used.
- Whether validation succeeded.
- Whether traffic was switched.
- Whether rollback occurred.

Audit records should be protected against unauthorized modification.

### 16.5 Observability

Deployment monitoring should include:

- Deployment duration.
- Provisioning failures.
- Readiness failures.
- Application error rates.
- Request latency.
- Instance availability.
- Traffic distribution.
- Rollback frequency.
- Resource utilization.

Operational metrics should be evaluated against deployment-specific thresholds.

### 16.6 Database compatibility

The application deployment lifecycle must coordinate with database migrations.

Backward-compatible schema changes reduce the risk of a previous application version failing after rollback.

Expand-and-contract migration design provides a controlled method:

    Expand Schema
         |
         v
    Deploy Compatible Application
         |
         v
    Migrate Application Behavior
         |
         v
    Verify Compatibility
         |
         v
    Remove Obsolete Schema

Destructive schema changes should not be performed before the previous application version is no longer required.

## 17. Performance and Operational Trade-Offs

Deployment performance depends on more than the number of instances.

Relevant factors include:

- Artifact download time.
- Image extraction time.
- Instance startup time.
- Dependency initialization.
- Health-check duration.
- Batch scheduling.
- Infrastructure capacity.
- Traffic-router propagation.
- Database migration duration.

### 17.1 Recreate

The strategy has a relatively simple execution sequence.

Its major trade-off is the interval during which the old application is unavailable and the new environment is being established.

### 17.2 Rolling

The strategy reduces the number of instances changed in each operation.

Its execution time depends on the number of batches and the duration of each batch.

For \(N\) instances and batch size \(B\), the approximate batch count is:

\[
K = \left\lceil \frac{N}{B} \right\rceil
\]

Larger batches can reduce the number of deployment stages but increase the potential impact of a defective release.

### 17.3 Blue-Green

The strategy provides a separate environment for validation and traffic switching.

Its main cost is temporary infrastructure duplication.

The additional environment also requires coordinated management of external dependencies, persistent data and shared services.

## 18. Running the Implementations

### Python

Requirements:

- Python 3.10 or newer.
- Standard library only.

Save the first deliverable as `deployment.py`.

Run:

`python deployment.py`

The script executes assertions, demonstrates all three deployment strategies and writes `deployment_history.json` in the current working directory.

### JavaScript

Requirements:

- Node.js 18 or newer.
- Standard library only.

Save the second deliverable as `deployment.js`.

Run:

`node deployment.js`

The script executes deployment tests, emits operational events and writes `deployment-history.json`.

### C++17

Requirements:

- C++17-compatible compiler.

Save the third deliverable as `deployment.cpp`.

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic deployment.cpp -o deployment`

Run:

`./deployment`

The program demonstrates infrastructure validation, deployment execution, reporting and rollback.

### Java 17

Requirements:

- Java Development Kit 17.

Save the fourth deliverable as `DeploymentGovernance.java`.

Compile:

`javac DeploymentGovernance.java`

Run:

`java DeploymentGovernance`

The program executes the enterprise deployment workflow and validates rollback behavior.

### PostgreSQL

Requirements:

- PostgreSQL 15 or newer.
- Database-owner permissions for schema and object creation.

Save the fifth deliverable as `deployment.sql`.

Execute:

`psql -U postgres -d deployment_db -f deployment.sql`

The script creates the schema, relational objects, functions, triggers, policies, sample records and reporting queries.

It is intended for a development database. Running it again without cleaning up the existing schema is not a supported migration procedure.

## 19. Technical Limitations

The implementations are educational deployment models rather than complete integrations with production infrastructure platforms.

The following capabilities are simulated or represented through database records:

- Container creation.
- Virtual-machine provisioning.
- Real network traffic routing.
- External load-balancer updates.
- Distributed health probes.
- Persistent distributed deployment locks.
- Secrets retrieval.
- Actual application process termination.
- Real database migrations.
- External infrastructure rollback.

The Python, JavaScript, C++17 and Java 17 programs maintain local execution state.

Their rollback operations demonstrate logical state recovery, not guaranteed restoration of external infrastructure.

The PostgreSQL schema maintains deployment records and workflow integrity. It does not execute infrastructure operations or perform application health checks.

A production implementation requires an orchestration controller, infrastructure integration, durable state management, monitoring, access control and recovery procedures.

## 20. Key Technical Distinctions

The three deployment strategies solve the same general problem through different replacement mechanisms.

- **Recreate** replaces the existing application environment as a complete operation.
- **Rolling** replaces application instances incrementally.
- **Blue-Green** provisions a separate environment and controls activation through traffic switching.

The central engineering decision is not simply which strategy is fastest.

It is how the deployment system balances service availability, infrastructure capacity, release validation, operational complexity and recovery requirements.

The correct strategy depends on application architecture, infrastructure constraints, traffic characteristics, data compatibility and the acceptable impact of deployment failure.

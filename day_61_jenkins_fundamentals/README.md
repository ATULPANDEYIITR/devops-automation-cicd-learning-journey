# Jenkins Fundamentals: Controller, Agents, and Jobs

## Scope

This project models the core architecture of Jenkins through five executable implementations:

| File | Engineering perspective | Main focus |
|---|---|---|
| Python | Controller simulation | Jobs, queueing, agents, workspaces, builds |
| JavaScript | Event-driven orchestration | Events, asynchronous execution, executor capacity |
| C++17 | Governance engine | Label scheduling, executor accounting, failure handling |
| Java 17 | Enterprise domain model | Typed state transitions, policies, services |
| PostgreSQL | Relational workflow model | Persistent Jenkins entities, constraints, procedures, reporting |

The implementations describe the same architectural domain while using different engineering techniques.

The central relationship is:

`Controller → Jobs → Queue → Agent selection → Executor → Workspace → Build → Result`

A Jenkins controller manages configuration and orchestration. Agents provide execution capacity. Jobs define what should be executed. A build is a particular execution of a job, normally associated with a source revision.

## Jenkins Architecture

A conventional Jenkins installation separates orchestration from build execution.

```text
                         Jenkins Controller
                                |
              +-----------------+-----------------+
              |                 |                 |
            Jobs             Queue            Policies
              |                 |                 |
              +-----------------+-----------------+
                                |
                         Agent Selection
                                |
              +-----------------+-----------------+
              |                                   |
       Linux Python Agent                   Linux Java Agent
              |                                   |
        Executors                            Executors
              |                                   |
          Workspace                           Workspace
              |                                   |
            Build                              Build
```

The controller is responsible for coordinating work. It maintains job configuration, schedules builds, evaluates which agents can execute a build, tracks build history, and records results.

An agent is a worker environment connected to the controller. An agent may advertise labels such as `linux`, `python`, `java`, or `container`. Jobs can require labels so that incompatible workers are not selected.

An executor represents a unit of concurrent build capacity on an agent. An agent with two executors can normally execute two compatible builds concurrently, subject to other Jenkins configuration and resource constraints.

## Controller

The controller is the coordination layer.

The implementations model several controller responsibilities:

- Job registration
- Job configuration
- Build numbering
- Queue management
- Agent discovery
- Label matching
- Workspace allocation
- Build lifecycle tracking
- Build history
- Failure recording

The controller should not be treated as synonymous with the machine that performs every build command. The architecture separates scheduling from execution so that worker capacity can scale independently.

### Python implementation

The Python controller uses dictionaries for indexed job and agent lookup. `Build`, `Job`, and `Agent` are dataclasses, while enumerations represent job types, build states, and agent states.

`find_agent()` evaluates label compatibility and chooses a compatible worker with the smallest current workspace load.

`execute_build()` models the lifecycle:

`queued → running → success/failure`

The workspace is created beneath an isolated temporary root. A commit artifact is written and read back to validate that the simulated checkout produced the expected revision.

A commit message containing `FAIL` deliberately enters the failure path. This gives the execution model a deterministic failure condition without depending on external infrastructure.

### JavaScript implementation

The JavaScript version treats the controller as an `EventEmitter`. Queueing and completion generate events that can be consumed by operational observers.

This is useful for an event-driven systems perspective because build state changes can trigger independent logging or monitoring behavior.

The implementation uses:

- `Map` for jobs and agents
- `Set` for labels
- `Promise`-based filesystem operations
- asynchronous workspace creation
- event emission for queue and completion events
- `crypto.randomUUID()` for build identity

The `drainQueue()` method repeatedly selects work that has a compatible executor. If queued work has no eligible agent, the controller raises a scheduling failure instead of silently discarding the build.

### C++17 implementation

The C++ version emphasizes explicit resource ownership and executor accounting.

`JenkinsGovernanceEngine` owns jobs, agents, and the queue. `Agent` tracks active executor usage. Scheduling selects compatible agents and prefers the agent with fewer active executors.

The implementation uses:

- `std::map` for indexed domain objects
- `std::set` for labels
- `std::vector` for build history and logs
- `std::filesystem` for workspace management
- exceptions for invalid configuration and execution failures

An executor is acquired before a build begins and released after the build reaches a terminal state. This makes resource accounting explicit.

### Java 17 implementation

The Java version uses an enterprise-oriented domain model.

Records provide immutable value objects for `Commit` and `JobPolicy`. Enums represent controlled domain states. Interfaces isolate policy behavior from orchestration.

`Build.transition()` explicitly validates lifecycle transitions. A completed build cannot be moved back into a running state.

`BuildPolicy` separates policy validation from the controller. `EnterprisePolicy` evaluates production-level restrictions and required status-check conditions.

The controller therefore coordinates domain services rather than embedding every rule in one method.

## Agents

Agents provide execution capacity.

A job should not be sent to an arbitrary worker. Its requirements must be matched against agent capabilities.

Example:

| Job | Required labels | Compatible agent |
|---|---|---|
| Python service | `linux`, `python` | `linux-python` |
| Java service | `linux`, `java` | `linux-java` |
| Python service | `linux`, `python` | Offline Python agent: no |

The important distinction is between labels and executors.

A label answers:

`Can this agent execute this type of work?`

An executor answers:

`Does this agent currently have capacity to execute another build?`

An online Python agent with no available executor is temporarily unsuitable even though its labels are correct.

An offline agent may have the correct labels but must not receive a build.

## Jobs

A Jenkins job is a configured unit of automation.

The implementations distinguish two representative job types:

| Job type | Purpose in the project |
|---|---|
| Freestyle | Represents a configured build-oriented job |
| Pipeline | Represents a job whose workflow can express multiple execution stages |

The examples do not attempt to reproduce Jenkins Pipeline syntax. They model the architectural distinction between a configured job and the execution instance created from that configuration.

A job contains requirements such as:

- Enabled or disabled state
- Job type
- Required agent labels
- Build numbering
- Build history
- Policy requirements

A disabled job must not enter normal execution.

## Build Queue

The queue separates demand from execution capacity.

A job can request a build when no compatible executor is immediately available. The build remains queued until the controller can assign suitable capacity.

The queue therefore acts as a buffer between:

`Build request → available execution capacity`

A robust scheduler must avoid two errors:

1. Sending work to an incompatible agent.
2. Losing work merely because no executor is available at the current moment.

The Python and C++ implementations use explicit queue collections. JavaScript uses an array combined with asynchronous processing. PostgreSQL represents queued work as rows in `build_queue`.

The PostgreSQL queue also records priority and queue time, making it possible to produce operational reports.

## Executors

Executors control concurrency at the agent level.

Consider an agent configured with two executors:

```
Agent
├── Executor 1 → Build A
└── Executor 2 → Build B
```

A third compatible build cannot start on that agent until capacity becomes available.

The JavaScript implementation calculates load using:

`active builds / executor count`

The C++ implementation directly increments and decrements active executor counters.

The Java implementation stores active builds in a map keyed by build UUID.

The SQL model records agent capacity and running builds so that available capacity can be reported.

Executor capacity is not equivalent to unlimited machine capacity. CPU, memory, disk, network bandwidth, container limits, and external service limits can all become bottlenecks.

## Workspaces

A workspace is an isolated filesystem location used by a build.

The project creates paths conceptually similar to:

`agent/job-build-number`

For example:

`linux-python/python-service-1`

Isolation prevents unrelated builds from accidentally sharing the same simulated checkout directory.

Real Jenkins deployments require stronger workspace considerations when builds run concurrently. A build that writes generated files into another build's workspace can create nondeterministic failures.

The implementations therefore allocate a workspace per build.

The Python and C++ versions use filesystem APIs directly. JavaScript uses asynchronous Node.js filesystem functions. Java uses `java.nio.file`.

## Build Lifecycle

The project uses an explicit lifecycle:

```
QUEUED
   |
   v
RUNNING
  / \
 v   v
SUCCESS  FAILURE
```

An aborted build is also modeled as a terminal state where the language implementation supports it.

The distinction between state and result is important.

A queued build has not started. A running build has an assigned execution environment. A successful or failed build has completed execution.

The Java implementation enforces valid state transitions explicitly. This prevents invalid transitions such as:

`SUCCESS → RUNNING`

The other implementations also avoid silently treating a finished build as active.

## Source Commits

Each build is associated with a source commit.

The examples validate:

- Commit identity
- Minimum SHA length
- Non-empty commit messages
- Workspace checkout artifacts

The PostgreSQL model stores commits separately from builds and uses foreign keys to prevent builds from referencing nonexistent revisions.

This produces a normalized relationship:

`Commit 1 → many Builds`

A single revision can therefore be built more than once.

## Failure Handling

Failure is part of normal build operation.

The implementations include deterministic failure paths so that failure handling can be observed without external services.

Representative failure conditions include:

- Invalid commit identity
- Missing workspace artifact
- Checkout integrity mismatch
- Explicit build validation failure
- Disabled job
- Offline agent
- No compatible executor
- Invalid state transition
- Invalid job or agent configuration

A failed build is retained in history rather than removed.

This distinction matters operationally because failed builds are evidence about the state of the automation system.

## Python Design

The Python implementation emphasizes direct simulation and standard-library structures.

### Main domain types

| Type | Responsibility |
|---|---|
| `Commit` | Immutable source revision identity |
| `Build` | Individual build execution |
| `Job` | Job configuration and build history |
| `Agent` | Worker capabilities and capacity |
| `JenkinsController` | Scheduling and execution coordination |

The use of dataclasses keeps domain state explicit while avoiding unnecessary framework dependencies.

The `summary()` method produces structured operational information suitable for logging or later serialization.

Assertions in `run_examples()` verify expected success and failure behavior.

## JavaScript Design

The JavaScript implementation emphasizes event-driven execution.

The controller emits:

- `buildQueued`
- `buildFinished`

This separates operational observation from core scheduling.

Asynchronous filesystem operations use promises, making the implementation representative of Node.js service-side orchestration.

Validation errors, scheduling errors, and build execution errors are separate error classes. This allows callers to distinguish configuration failures from runtime failures.

The use of `crypto.randomUUID()` prevents build identifiers from depending solely on sequential numbers.

## C++17 Design

The C++ implementation treats agents as resource owners.

The key engineering decision is explicit executor acquisition:

`acquire() → execute → release()`

If an executor release is attempted without a corresponding acquisition, the model raises a logic error.

This makes resource accounting visible and testable.

`std::filesystem` is used to represent workspace creation rather than relying on shell commands. This reduces command-injection exposure and keeps filesystem operations inside the program's API.

The implementation also separates:

- domain state
- scheduling
- workspace creation
- checkout validation
- reporting

## Java 17 Design

The Java implementation uses explicit domain boundaries.

`JobPolicy` contains immutable policy configuration.

`BuildPolicy` defines a validation contract.

`EnterprisePolicy` implements the policy.

`JenkinsController` coordinates jobs, agents, queues, and builds.

This separation avoids embedding every business rule directly in the controller.

The `Build.transition()` method makes state transitions part of the domain model rather than relying on callers to assign enum values freely.

Streams are used for agent selection and reporting, while ordinary collections remain responsible for mutable operational state.

## PostgreSQL Design

The SQL implementation treats Jenkins state as relational data.

The core entities are:

```
Controller
    |
    +── Agents
    |     |
    |     +── Agent Labels
    |
    +── Jobs
          |
          +── Required Labels

Commit
    |
    +── Build Queue
    |
    +── Builds
            |
            +── Build Events
```

Foreign keys enforce relationships between these entities.

Check constraints validate:

- executor counts
- job names
- label names
- commit SHA format
- build numbers
- timestamp ordering
- terminal build requirements

The database therefore protects important invariants even when application code is not trusted.

## Database Functions and Triggers

`next_build_number()` calculates the next build number for a job.

`enqueue_build()` validates that a job exists and is enabled before placing work in the queue.

`create_build_from_queue()` performs queue-to-build conversion while locking the queue row.

The `validate_build_assignment` trigger checks that an assigned agent is online and satisfies all required labels.

The timestamp trigger prevents impossible build histories such as a build finishing before it starts.

These checks demonstrate an important database principle: critical integrity rules should not depend exclusively on application-level validation.

## Reporting

The PostgreSQL view `build_execution_report` combines:

- Job
- Job type
- Build number
- Commit
- Agent
- Build status
- Timing
- Failure reason

The queries then provide:

- Build retrieval
- Success/failure aggregation
- Agent compatibility validation
- Queue state
- Average execution duration
- Executor capacity
- Failure reporting

This makes the database useful for both transactional storage and operational analysis.

## State and Failure Distinctions

The implementations distinguish several different causes of non-success.

| Condition | Meaning |
|---|---|
| Disabled job | Work should not be scheduled |
| Queued build | Work is waiting for execution |
| Offline agent | Worker cannot accept execution |
| No compatible agent | Label requirements cannot be satisfied |
| No free executor | Compatible worker exists but is busy |
| Running build | Execution has started |
| Failed build | Execution reached a failure result |
| Aborted build | Execution was deliberately terminated |

These conditions should not be collapsed into a single generic "error" state because they require different operational responses.

## Performance Considerations

The examples intentionally use in-memory collections for the language implementations so that the architecture remains self-contained.

Agent selection scans compatible agents. With `A` agents and `L` required labels, a straightforward selection is approximately `O(A × L)`.

Build history lookup in the language implementations is collection-based. A production controller would use persistent indexed storage and more sophisticated scheduling structures.

The PostgreSQL model adds indexes for common access patterns:

- Agent status by controller
- Agent labels
- Job state
- Queue priority
- Build status
- Build event history

Indexes should correspond to actual query patterns. Excessive indexing increases write cost and storage consumption.

## Security Considerations

Build systems execute code and therefore represent a high-value security boundary.

The implementations avoid shell execution and construct filesystem paths from controlled names.

Important real-world controls include:

- Least-privilege agent identities
- Isolation between builds
- Restricted filesystem access
- Secret masking and controlled secret injection
- Authentication and authorization for controller administration
- Signed or trusted build artifacts where required
- Network restrictions for agents
- Protection of controller credentials
- Controlled plugin installation
- Audit logging
- Separation of production deployment credentials from ordinary build workers

An agent executing untrusted source code should not automatically receive unrestricted credentials or administrator privileges.

## Operational Failure Modes

Common Jenkins-style failure scenarios include:

| Failure | Primary diagnostic area |
|---|---|
| Build remains queued | Agent labels, executor capacity, node availability |
| Agent disconnected | Agent connectivity and worker environment |
| Workspace corruption | Concurrent builds and cleanup |
| Build fails during checkout | Source configuration and credentials |
| Build starts on unexpected worker | Label configuration |
| Builds become slow | Executor contention or external dependencies |
| Repeated build failures | Source changes, environment, dependencies |
| Controller overload | Queue size, scheduling, persistence, plugins |
| Disk exhaustion | Workspace and artifact retention |
| Credentials unavailable | Credential configuration and permissions |

A useful diagnostic process begins by distinguishing scheduling failure from build execution failure.

If a build has never started, investigating application test output is premature. Queue and agent state should be inspected first.

## Relationship Between Controller, Agents, Jobs, and Builds

The architecture can be expressed as:

```
Job definition
     |
     v
Build request
     |
     v
Controller queue
     |
     v
Label and capacity evaluation
     |
     v
Compatible agent
     |
     v
Available executor
     |
     v
Isolated workspace
     |
     v
Build execution
     |
     +----> Success
     |
     +----> Failure
```

This separation is the central architectural idea represented by all five implementations.

A controller is not merely a build script runner. A job is not the same thing as a build. An agent is not the same thing as an executor. Queueing is not failure. A failed build is not equivalent to a scheduling failure.

Keeping those distinctions explicit makes Jenkins automation easier to reason about, test, monitor, and operate.

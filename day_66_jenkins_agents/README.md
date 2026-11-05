# Jenkins Agents: Static Agents, Dynamic Agents, and Distributed Builds

## 1. Introduction

Jenkins uses a controller-agent architecture to distribute software build, test, packaging, and deployment workloads across multiple execution environments.

The Jenkins controller manages jobs, scheduling, configuration, build queues, and execution coordination. Agents provide the computing resources on which pipeline steps and build tasks execute.

A Jenkins agent can run on a physical server, virtual machine, container, Kubernetes pod, or cloud instance.

The main architectural distinction is between:

- **Static agents:** Long-lived agents registered with Jenkins and maintained as persistent infrastructure.
- **Dynamic agents:** Agents provisioned when workload capacity is needed and removed when their work is complete.
- **Distributed builds:** Build workloads executed across multiple agents according to labels, available executors, scheduling policies, and infrastructure capacity.

The five implementations model these concepts using executable programs and a relational database.

## 2. Jenkins Controller-Agent Architecture

The controller coordinates execution but should not perform every resource-intensive build itself.

A distributed architecture separates scheduling responsibilities from execution resources.

```text
                  Jenkins Controller
                          |
              -------------------------
              |           |           |
           Queue       Scheduler    Policies
              |           |
              |      Agent Selection
              |           |
       -----------------------------
       |             |             |
   Static Agent  Static Agent  Dynamic Provider
       |             |             |
   Linux Build   Windows Build   Cloud Agent
       |             |             |
       -----------------------------
                    |
              Build Results
                    |
              Controller
```

### Controller responsibilities

- Accept build requests.
- Maintain the build queue.
- Evaluate agent availability.
- Match build requirements against agent labels.
- Assign builds to available executors.
- Monitor build execution.
- Record execution results.
- Coordinate dynamic infrastructure.
- Apply scheduling and capacity policies.

### Agent responsibilities

- Connect to the Jenkins controller.
- Advertise execution labels and capabilities.
- Accept assigned workloads.
- Execute build and pipeline operations.
- Return console output and execution results.
- Report connection and execution status.

The controller and agent communicate through Jenkins-supported remoting and agent connection mechanisms.

Agents should run with appropriately restricted permissions rather than automatically receiving unrestricted controller-level access.

## 3. Static Jenkins Agents

A static agent is a persistent execution resource that remains registered with Jenkins independently of individual build requests.

Typical implementations include:

- Dedicated Linux build servers.
- Windows build machines.
- Persistent virtual machines.
- On-premises development infrastructure.
- Long-running container hosts.

### Lifecycle

```
Provision Infrastructure
         |
Install Agent Runtime
         |
Configure Connection
         |
Register with Jenkins
         |
       ONLINE
         |
Receive Build
         |
       BUSY
         |
Execute Build
         |
Return Result
         |
       ONLINE
         |
Optional Maintenance
```

### Characteristics

| Property            | Static agent                         |
| ------------------- | ------------------------------------ |
| Lifetime            | Long-lived                           |
| Provisioning        | Usually performed before scheduling  |
| Availability        | Persistent when healthy              |
| Startup overhead    | Generally low                        |
| Infrastructure cost | Can continue during idle periods     |
| Capacity            | Usually predetermined                |
| Maintenance         | Administratively managed             |
| Best suited for     | Predictable and continuous workloads |

### Executor management

An executor represents an execution slot on an agent.

An agent with four executors can potentially execute four independent builds concurrently, provided its CPU, memory, disk, and other resources can support the workload.

The number of executors should reflect actual hardware capacity.

Excessive executor allocation can cause:

- CPU contention.
- Memory exhaustion.
- Disk contention.
- Longer execution times.
- Unreliable test results.
- Resource exhaustion.

An agent should not be considered available merely because it is connected. Its executor capacity and operational state must also be evaluated.

### Implementation

The Python, C++, JavaScript, and Java programs register persistent agents with explicit labels and executor limits.

The PostgreSQL implementation stores static agents in the `agents` table with `agent_type = 'STATIC'`.

Static agents are preferred in the scheduling policies when they can execute the requested workload.

## 4. Dynamic Jenkins Agents

A dynamic agent is created when additional execution capacity is required.

The Jenkins infrastructure requests a new execution environment from an external provisioning system.

Possible provisioning environments include:

- Cloud virtual machines.
- Kubernetes pods.
- Ephemeral containers.
- Automatically created virtual machines.
- Temporary build workers.

### Dynamic agent lifecycle

```
Build Enters Queue
       |
No Compatible Capacity
       |
Provisioning Request
       |
Cloud or Container Platform
       |
Agent Starts
       |
Agent Connects to Jenkins
       |
Build Executes
       |
Build Completes
       |
Agent Becomes Idle
       |
Agent Terminated
```

### Provisioning workflow

1. Jenkins receives a build request.
2. The scheduler identifies the required labels.
3. Existing agents are evaluated.
4. If no compatible executor is available, dynamic provisioning is considered.
5. The infrastructure provider creates an execution environment.
6. The agent connects to the controller.
7. The scheduler assigns the build.
8. The build executes.
9. The agent is terminated according to its lifecycle policy.

The controller must account for provisioning time. A cloud instance being created does not mean it is immediately ready to execute a build.

A production provisioning system should distinguish:

- Provisioning requested.
- Infrastructure created.
- Agent process started.
- Agent connected.
- Agent ready.
- Agent executing work.
- Agent disconnected.
- Agent terminated.

### Characteristics

| Property                 | Dynamic agent                        |
| ------------------------ | ------------------------------------ |
| Lifetime                 | Temporary                            |
| Provisioning             | On demand                            |
| Startup overhead         | Depends on infrastructure            |
| Capacity                 | Can scale within configured limits   |
| Idle cost                | Reduced through termination          |
| Configuration            | Automated                            |
| Best suited for          | Variable or burst workloads          |
| Main operational concern | Provisioning and startup reliability |

### Benefits

- Reduces idle infrastructure consumption.
- Supports workload-based scaling.
- Provides isolated execution environments.
- Supports temporary build environments.
- Allows different operating systems and toolchains to be provisioned when required.

### Limitations

- Provisioning failures can delay builds.
- Cloud quotas restrict capacity.
- Startup latency affects short jobs.
- Temporary storage may disappear after termination.
- Configuration drift can create inconsistent environments.
- Poor cleanup policies can leave unnecessary infrastructure running.

### Implementation

The Python implementation uses a dynamic-agent limit and idle-timeout cleanup.

The JavaScript implementation introduces an asynchronous `DynamicAgentProvider`, which provisions agents through a Promise-based interface.

The C++ implementation models cloud-agent provisioning through scheduler-managed dynamic capacity.

The Java implementation separates provisioning responsibilities through the `AgentProvisioner` interface.

The PostgreSQL implementation records dynamic-agent infrastructure using:

- `agent_type`
- `cloud_instance_id`
- `provisioned_at`
- `last_used_at`
- `terminated_at`
- `provisioning_events`

## 5. Static vs Dynamic Agents

The two approaches solve different infrastructure problems.

| Comparison                | Static                 | Dynamic                 |
| ------------------------- | ---------------------- | ----------------------- |
| Infrastructure lifetime   | Persistent             | Temporary               |
| Creation                  | Preconfigured          | On demand               |
| Startup latency           | Usually low            | Depends on provisioning |
| Capacity expansion        | Administrative         | Automated               |
| Idle resource consumption | Potentially high       | Can be reduced          |
| Maintenance               | Scheduled              | Often automated         |
| Workload suitability      | Predictable workloads  | Variable workloads      |
| Environment               | Persistent             | Often isolated          |
| Cleanup                   | Maintenance procedures | Lifecycle automation    |

### Selection considerations

Static agents are useful when:

- Build workloads are continuous.
- Specialized hardware is required.
- Toolchains are expensive to initialize.
- Infrastructure is already available.
- Stable network access is necessary.

Dynamic agents are useful when:

- Build volume changes significantly.
- Temporary isolation is required.
- Different execution environments are needed.
- Cloud capacity is available.
- Idle infrastructure costs need to be controlled.

A mixed infrastructure is often appropriate.

Persistent agents can handle regular workloads while dynamic agents provide additional capacity during periods of increased demand.

## 6. Distributed Builds

Distributed builds allow Jenkins to execute multiple jobs across multiple agents.

A controller schedules work based on the requirements of each build and the capabilities of available agents.

### Build distribution example

| Build             | Required labels       | Compatible agent       |
| ----------------- | --------------------- | ---------------------- |
| Python tests      | `linux`, `python`     | Linux agent            |
| Docker packaging  | `linux`, `docker`     | Linux Docker agent     |
| .NET integration  | `windows`, `dotnet`   | Windows agent          |
| Security scanning | `linux`, `security`   | Security-enabled agent |
| Deployment        | `linux`, `deployment` | Deployment agent       |

### Label-based scheduling

Labels describe agent capabilities.

Examples:

- `linux`
- `windows`
- `python`
- `java`
- `docker`
- `security`
- `deployment`

A build can require multiple labels.

An agent is compatible only when it satisfies all required labels.

For example:

A build requiring `linux` and `docker` must not be assigned to a Windows agent that only provides `windows` and `dotnet`.

Labels describe capabilities, not guaranteed resource availability.

A compatible agent must also have:

- An online connection.
- Available executor capacity.
- Sufficient remaining build capacity.
- The required permissions.
- A suitable execution environment.

### Scheduling workflow

```
Build Submission
       |
Validate Requirements
       |
Add to Build Queue
       |
Find Compatible Agents
       |
Check Executor Availability
       |
   Agent Available?
      /       \
    Yes        No
     |          |
 Assign      Provision
     |          |
 Execute    Wait or Retry
     |          |
 Return Result
     |
 Update State
```

### Scheduling decisions

The implementations demonstrate a policy that prefers static agents when both static and dynamic agents can execute the same workload.

This reduces unnecessary infrastructure provisioning.

A more advanced scheduling policy can consider:

- Build priority.
- Queue waiting time.
- Estimated execution duration.
- Agent utilization.
- Infrastructure cost.
- Operating-system requirements.
- Geographic location.
- Resource availability.
- Agent reliability.

The scheduler should avoid assigning a build to an agent merely because its labels match.

## 7. Build States and Execution Attempts

A build progresses through defined states.

| State     | Meaning                          |
| --------- | -------------------------------- |
| QUEUED    | Waiting for an eligible executor |
| RUNNING   | Assigned and executing           |
| SUCCESS   | Completed successfully           |
| FAILED    | Execution failed                 |
| CANCELLED | Execution was cancelled          |

A typical transition is:

```
QUEUED
   |
RUNNING
   |
   +---------- SUCCESS
   |
   +---------- FAILED
   |
   +---------- QUEUED (Retry)
   |
   +---------- CANCELLED
```

Retries should be controlled by explicit policies.

A failed build should not be retried indefinitely because the failure might be caused by:

- Invalid source code.
- Missing dependencies.
- Authentication errors.
- Incorrect configuration.
- Persistent infrastructure failure.

A retry limit helps prevent repeated resource consumption.

An execution attempt should be recorded separately from the overall build request. This preserves the history of failed attempts even when a later attempt succeeds.

The PostgreSQL `build_attempts` table implements this distinction.

## 8. Python Implementation

The Python file implements a controller-oriented simulation.

### Main components

| Component           | Responsibility                            |
| ------------------- | ----------------------------------------- |
| `AgentType`         | Identifies static and dynamic agents      |
| `AgentStatus`       | Tracks infrastructure state               |
| `BuildStatus`       | Tracks build execution state              |
| `Build`             | Represents a submitted workload           |
| `Agent`             | Stores capabilities and executor capacity |
| `JenkinsController` | Coordinates scheduling and execution      |

### Scheduling mechanism

The controller maintains:

- An agent dictionary.
- A build dictionary.
- A queue of build identifiers.
- Infrastructure metrics.

The `_find_agent()` method filters agents according to availability and label compatibility.

Static agents receive scheduling preference.

If no suitable agent exists, `_provision_dynamic_agent()` attempts to create one within the configured capacity limit.

### Failure handling

The implementation validates:

- Duplicate agent registrations.
- Duplicate build identifiers.
- Invalid labels and executor counts.
- Invalid build durations.
- Agent availability.
- Invalid build transitions.
- Dynamic-agent capacity.
- Agent termination conditions.

The `cancel_build()` method handles queued and running build cancellation.

The `cleanup_idle_dynamic_agents()` method removes dynamic agents after their idle timeout.

### Complexity

Let:

- A = number of registered agents.
- Q = number of queued builds.
- L = number of required labels.

A straightforward scheduling pass performs approximately O(Q × A × L) work, excluding sorting overhead.

Agent selection sorts compatible candidates, adding a sorting cost of O(A log A) in the worst case for each build.

For larger systems, indexed label lookup and priority queues can reduce unnecessary candidate evaluation.

## 9. JavaScript Implementation

The JavaScript file uses an event-driven architecture.

It is designed around asynchronous provisioning and build execution.

### Main components

| Component              | Responsibility                            |
| ---------------------- | ----------------------------------------- |
| `Build`                | Represents a build request                |
| `Agent`                | Tracks agent capabilities and state       |
| `DynamicAgentProvider` | Simulates asynchronous provisioning       |
| `JenkinsController`    | Coordinates scheduling                    |
| `EventEmitter`         | Publishes infrastructure and build events |

### Asynchronous provisioning

Dynamic provisioning uses Promises and asynchronous functions.

This reflects the fact that cloud infrastructure creation requires time.

Provisioning can fail because of:

- Capacity exhaustion.
- Infrastructure errors.
- Provider failures.
- Temporary service unavailability.

The controller records provisioning failures and retains affected builds in its queue.

### Event-driven monitoring

The implementation emits events including:

- `build:queued`
- `build:started`
- `build:success`
- `build:failed`
- `build:retry`
- `agent:registered`
- `agent:provisioned`
- `agent:provisioning-failed`
- `agent:terminated`

This allows monitoring and reporting systems to subscribe to execution events without directly modifying scheduling logic.

### Timeout handling

Build execution uses a timeout mechanism.

A build that exceeds its configured execution limit is marked as failed or retried according to its retry policy.

The example models execution with timers. A production implementation should use cancellation signals so that timeout and cancellation requests actually terminate the underlying process or container.

The demonstration uses sequential scheduling to keep the state transitions easy to inspect. A production distributed scheduler should dispatch independent builds concurrently while enforcing executor and provisioning limits.

## 10. C++17 Implementation

The C++17 program implements a domain-oriented scheduling engine.

### Main data structures

| Structure          | Purpose                             |
| ------------------ | ----------------------------------- |
| `Build`            | Build request and execution state   |
| `Agent`            | Agent capabilities and capacity     |
| `JenkinsScheduler` | Scheduling and lifecycle management |
| `map`              | Agent and build registries          |
| `vector`           | Pending queue                       |
| `set`              | Labels and active build identifiers |

### Design decisions

The implementation uses ordered maps to provide predictable lookup and reporting behavior.

Sets provide efficient label membership and assignment tracking.

The scheduler:

1. Validates build requests.
2. Searches compatible agents.
3. Prefers static agents.
4. Provisions dynamic agents when capacity permits.
5. Assigns available executors.
6. Records execution outcomes.
7. Validates build-agent relationships.

### Invariant validation

The `validateInvariants()` method checks that:

- Active builds do not exceed executor capacity.
- Every active assignment references a running build.
- Each running build identifies the correct assigned agent.

These checks help identify state inconsistencies before they become difficult to debug.

The implementation also rejects attempts to terminate static agents through the dynamic-agent termination operation.

## 11. Java 17 Implementation

The Java implementation uses an enterprise-oriented domain model.

### Domain types

The implementation defines:

- Immutable `BuildRequest` records.
- Mutable `BuildExecution` entities.
- An `Agent` domain object.
- An `AgentProvisioner` interface.
- A `CloudProvisioner` implementation.
- A `SchedulingPolicy` object.
- A `JenkinsController` service.

### Separation of responsibilities

`BuildRequest` stores immutable workload requirements.

`BuildExecution` manages the lifecycle of an individual build.

`Agent` manages executor allocation and release.

`AgentProvisioner` separates infrastructure provisioning from scheduling.

`SchedulingPolicy` defines candidate-selection behavior.

`JenkinsController` coordinates the services.

This separation allows infrastructure provisioning to be replaced without redesigning the scheduling domain.

### State transition enforcement

The `BuildExecution` class prevents invalid transitions.

For example, a completed build cannot be started again directly.

A failed attempt can return to the queued state only when the configured retry limit permits it.

### Enterprise considerations

The model demonstrates:

- Immutable request data.
- Explicit domain types.
- Policy-driven scheduling.
- Infrastructure abstraction.
- Custom exceptions.
- Assignment consistency checks.
- Agent lifecycle enforcement.
- Queue capacity restrictions.

A production implementation would also require persistent execution state, distributed locking, authenticated agent connections, structured audit records, and reliable recovery after controller restarts.

## 12. PostgreSQL Database Architecture

The SQL implementation models Jenkins infrastructure as a relational system.

### Entity relationships

```
CONTROLLERS
    |
    +--------------------+
    |                    |
  AGENTS              BUILDS
    |                    |
    |                    +---- BUILD_REQUIRED_LABELS
    |
    +---- AGENT_LABELS
    |
    +---- BUILD_ATTEMPTS
                |
                +---- BUILDS

CONTROLLERS
    |
    +---- SCHEDULING_POLICIES
    |
    +---- PROVISIONING_EVENTS
```

### Database tables

| Table                   | Purpose                            |
| ----------------------- | ---------------------------------- |
| `controllers`           | Controller configuration           |
| `agents`                | Static and dynamic agent inventory |
| `agent_labels`          | Agent execution capabilities       |
| `builds`                | Build requests and current states  |
| `build_required_labels` | Required build capabilities        |
| `build_attempts`        | Individual execution attempts      |
| `provisioning_events`   | Infrastructure lifecycle history   |
| `scheduling_policies`   | Scheduling and capacity rules      |

### Data integrity

Primary keys identify individual records.

Foreign keys preserve relationships between controllers, agents, builds, and execution attempts.

Unique constraints prevent duplicate agent names within a controller and duplicate build attempt numbers within a build.

Check constraints enforce:

- Positive executor counts.
- Valid retry limits.
- Valid execution durations.
- Consistent agent types.
- Valid terminal states.

Partial indexes improve access to active execution attempts and queued workloads.

### Agent eligibility

The `is_agent_eligible()` function evaluates whether an agent can execute a particular build.

It considers:

- Agent status.
- Available executor capacity.
- Remaining build capacity.
- Required labels.

The `find_eligible_agents()` function returns compatible agents in scheduling order, preferring static agents.

### Build assignment

The `assign_build()` procedure performs a controlled assignment.

It locks the build and agent rows to reduce concurrent allocation conflicts.

It validates agent eligibility before:

1. Creating an execution-attempt record.
2. Changing the build state to `RUNNING`.
3. Recording the assigned agent.
4. Updating agent state.

The procedure executes within the caller's transaction.

### Build completion

The `complete_build()` procedure records the execution result.

It updates the attempt record and the overall build state.

If a failed attempt is eligible for retry, the build returns to `QUEUED`.

Otherwise, it enters the `FAILED` state.

### Reporting views

`agent_capacity` provides executor utilization information.

`queued_build_details` provides queue age, workload requirements, and estimated execution time.

The reporting queries compare static and dynamic agent performance, inspect provisioning failures, and evaluate queue conditions.

## 13. Distributed Build Scheduling Strategies

Different scheduling strategies produce different infrastructure behavior.

| Strategy        | Mechanism                              | Trade-off                                |
| --------------- | -------------------------------------- | ---------------------------------------- |
| First available | Assign the first eligible agent        | Simple but may create uneven utilization |
| Least loaded    | Prefer agents with fewer active builds | Improves load distribution               |
| Static first    | Prefer persistent agents               | Reduces provisioning overhead            |
| Dynamic first   | Prefer temporary capacity              | Can reduce persistent-agent usage        |
| Priority-based  | Schedule critical jobs earlier         | Lower-priority jobs may wait             |
| Resource-aware  | Consider CPU and memory                | Requires reliable resource monitoring    |
| Cost-aware      | Consider infrastructure cost           | May increase waiting time                |

A production scheduler can combine these approaches.

For example, it can prefer a static agent for ordinary workloads while provisioning dynamic agents for high-priority builds when static capacity is exhausted.

## 14. Security Considerations

Jenkins agents execute repository-controlled and pipeline-controlled operations. They must be treated as security-sensitive infrastructure.

### Agent communication

- Use authenticated agent connections.
- Protect agent connection credentials.
- Avoid exposing controller communication endpoints unnecessarily.
- Use encrypted communication.
- Rotate credentials according to organizational policy.
- Restrict network access.

### Execution isolation

- Use separate execution identities.
- Avoid unrestricted administrator privileges.
- Isolate untrusted workloads.
- Restrict filesystem access.
- Control access to Docker sockets.
- Separate production deployment credentials from ordinary build credentials.
- Remove temporary credentials after execution.

### Dynamic infrastructure

Dynamic agents should use:

- Short-lived credentials.
- Restricted cloud permissions.
- Resource quotas.
- Network segmentation.
- Controlled image registries.
- Ephemeral workspaces.
- Automated termination.

### Pipeline security

Build scripts should not receive credentials that are unnecessary for their execution.

Secrets should be injected through controlled credential mechanisms rather than embedded in source code, environment files, or build logs.

A build running on a shared agent must not be able to access another build's sensitive workspace or credentials.

### Database security

The PostgreSQL example stores a field for a connection-secret hash rather than the original secret.

Production deployments should also enforce:

- Role-based database permissions.
- Restricted schema access.
- Encrypted connections.
- Credential rotation.
- Audit logging.
- Least-privilege procedure execution.

## 15. Performance and Scalability

Distributed execution increases available capacity, but it does not automatically guarantee shorter build times.

Important performance factors include:

| Factor                   | Effect                                      |
| ------------------------ | ------------------------------------------- |
| Number of agents         | Determines available distributed capacity   |
| Executor count           | Controls concurrent work per agent          |
| Provisioning latency     | Delays dynamically created capacity         |
| Build duration           | Determines resource occupancy               |
| Queue length             | Indicates demand relative to capacity       |
| Network latency          | Affects communication and artifact transfer |
| Workspace initialization | Adds startup overhead                       |
| Artifact storage         | Influences transfer time                    |
| Resource contention      | Can reduce execution throughput             |

### Throughput

A simplified upper-bound estimate is:

\\[ \text{Throughput} \approx \frac{\text{Available Executors}} {\text{Average Build Duration}} \\]

For example, 10 executors with an average build duration of 60 seconds have an approximate theoretical capacity of:

\\[ \frac{10}{60}=0.1667 \\]

builds per second, or approximately 10 builds per minute.

This estimate assumes continuous demand and ignores scheduling, provisioning, network, and resource-contention overhead.

### Dynamic scaling

Dynamic scaling should account for:

- Queue growth.
- Provisioning delay.
- Cloud quotas.
- Maximum agent count.
- Idle timeout.
- Build duration.
- Cost constraints.

Provisioning too many agents can increase infrastructure costs.

Provisioning too few agents can create long queue times.

## 16. Failure Handling and Recovery

| Failure                 | Possible cause                      | Appropriate handling                                      |
| ----------------------- | ----------------------------------- | --------------------------------------------------------- |
| Agent offline           | Network or machine failure          | Stop new assignments and investigate running workloads    |
| Provisioning failure    | Cloud quota or API error            | Retain queued work and retry with limits                  |
| Executor exhaustion     | Too many active builds              | Wait for capacity or provision additional agents          |
| Build timeout           | Hung process or resource contention | Terminate execution and record failure                    |
| Agent disconnection     | Remoting connection failure         | Recover or reassign according to execution safety         |
| Dynamic cleanup failure | Cloud API error                     | Record event and retry termination                        |
| Invalid label           | Incorrect pipeline configuration    | Reject or report the request                              |
| Controller restart      | Infrastructure interruption         | Recover queue and execution state from persistent storage |

A disconnected agent must not automatically cause a build to be considered successful.

The controller needs reliable evidence of execution completion.

Reassignment also requires care because a disconnected agent might still be executing the original workload.

Production systems should use execution identifiers, heartbeat monitoring, leases, and recovery procedures to prevent duplicate or conflicting operations.

## 17. Important Implementation Limitations

The implementations are educational models of Jenkins scheduling and infrastructure behavior rather than complete replacements for Jenkins.

| Implementation | Main limitation                                                       |
| -------------- | --------------------------------------------------------------------- |
| Python         | Uses an in-memory scheduler and simulated execution                   |
| JavaScript     | Uses timers and simulated asynchronous provisioning                   |
| C++17          | Uses synchronous execution-state transitions                          |
| Java 17        | Uses an in-memory enterprise domain model                             |
| PostgreSQL     | Models database workflows but does not provision cloud infrastructure |

The PostgreSQL implementation also assumes that scheduling operations are coordinated through its procedures and transaction boundaries. A production deployment must ensure that every assignment path follows the same concurrency rules.

The code does not implement Jenkins remoting, Kubernetes pod creation, cloud-provider APIs, pipeline execution, artifact storage, or actual operating-system process isolation.

These capabilities belong to the operational infrastructure surrounding the scheduling model.

## 18. Practical Learning Outcomes

The implementations demonstrate the technical differences between:

- Persistent and temporary execution infrastructure.
- Agent registration and dynamic provisioning.
- Agent availability and executor availability.
- Label compatibility and actual scheduling eligibility.
- Build requests and execution attempts.
- Build state and agent lifecycle state.
- Scheduling policy and infrastructure capacity.
- Controller coordination and agent execution.

The central architectural relationship is:

The Jenkins controller manages and distributes workloads, static agents provide persistent execution capacity, dynamic agents provide temporary execution capacity, and distributed scheduling coordinates their use according to workload requirements and available resources.

# Jenkins Pipeline: Declarative and Scripted Pipelines

## 1. Scope

Jenkins Pipeline defines an automated workflow for building, testing, packaging, and delivering software. A pipeline describes the execution process as stages and steps, with rules for agent allocation, conditions, retries, credentials, parallel work, and post-build behavior.

Jenkins Pipeline has two principal implementation styles:

| Style | Main characteristic | Typical use |
|---|---|---|
| Declarative Pipeline | Structured syntax with defined sections and validation rules | Standardized CI/CD workflows |
| Scripted Pipeline | Imperative Groovy programming using Pipeline steps | Dynamic workflows and complex control flow |

Both styles use Jenkins Pipeline infrastructure and can invoke Jenkins steps. They differ in how the workflow is expressed and controlled.

The five source files model these concepts with executable local implementations. They simulate pipeline behavior and state transitions; they do not communicate with a Jenkins controller, provision actual Jenkins agents, or execute real deployment commands.

## 2. Jenkins Pipeline Architecture

A Jenkins Pipeline normally involves a controller, one or more agents, a pipeline definition, and the resources used by its execution.

| Component | Responsibility |
|---|---|
| Jenkins controller | Schedules builds, coordinates pipeline execution, manages configuration, and records build information |
| Agent | Provides an execution environment for pipeline work |
| Executor | Represents a unit of execution capacity on an agent |
| Pipeline definition | Describes the stages, steps, conditions, and workflow |
| Stage | Groups related activities, such as compilation or testing |
| Step | Performs an individual operation inside a stage |
| Workspace | Provides the working directory for a build on an agent |
| Artifact | Represents a build output that can be retained or transferred |
| Credentials | Provides controlled access to passwords, tokens, keys, or certificates |
| Build result | Records whether the pipeline succeeded, failed, or became unstable |

A conceptual execution path is:

Repository event or manual trigger  
→ Jenkins controller  
→ Pipeline definition  
→ Agent allocation  
→ Stage execution  
→ Step execution  
→ Artifact publication  
→ Deployment or delivery  
→ Post-build processing

The controller coordinates execution, while agents perform the work. A pipeline can use different agents for different stages. For example, compilation may use a container-capable Linux agent while deployment uses a restricted deployment agent.

Agent labels are scheduling requirements. A label such as `linux-docker` describes an execution capability; it does not identify a particular machine unless the Jenkins configuration maps that label to an agent.

## 3. Declarative Pipeline

Declarative Pipeline provides a structured way to define the workflow. A conventional Jenkins Declarative Pipeline uses a `pipeline` block containing sections such as `agent`, `stages`, and `post`.

Its structure supports consistent review and enforcement of pipeline conventions.

### 3.1 Main directives

| Directive | Purpose |
|---|---|
| `pipeline` | Defines the pipeline |
| `agent` | Selects where the pipeline or a stage executes |
| `stages` | Contains the ordered stage definitions |
| `stage` | Names a logical unit of pipeline work |
| `steps` | Contains executable Jenkins steps |
| `environment` | Defines environment variables |
| `parameters` | Declares build parameters |
| `options` | Configures pipeline-level behavior |
| `when` | Determines whether a stage should execute |
| `post` | Defines actions associated with build outcomes |
| `tools` | Selects configured tools where supported |
| `input` | Requests manual interaction at a pipeline point |

A Declarative Pipeline separates workflow structure from the operations inside each stage. Its syntax also permits stage-level agents and stage-specific conditions.

### 3.2 Stage execution

A stage may contain several steps. For example, a build stage can execute compilation, while a test stage runs unit tests.

A stage is not equivalent to an individual shell command. It is a named workflow boundary that groups steps and makes the build easier to inspect.

A conventional delivery pipeline may contain:

| Stage | Responsibility |
|---|---|
| Checkout | Obtain the required source revision |
| Build | Compile or assemble the application |
| Unit Tests | Verify isolated application behavior |
| Integration Tests | Verify interactions between components |
| Package | Produce a distributable artifact |
| Deploy | Transfer or activate the approved artifact |

The stages may have dependencies even when the source definition is written in a simple sequential form. Parallel stages can execute independent work concurrently.

### 3.3 Conditions and parameters

The `when` directive controls whether a stage is executed. Conditions can depend on branch names, parameters, environment values, or other supported expressions.

A production deployment stage might be restricted to the main branch and require a separate approval decision.

A skipped stage is not necessarily a failed stage. Its absence from execution can be an intentional result of a condition. The source implementations represent this separately from success and failure.

Build parameters allow a workflow to receive controlled input. They should be validated before use. Parameters must not be used as a substitute for secure credential management.

### 3.4 Post-build behavior

Declarative Pipeline supports post conditions for actions that should occur after normal stage execution.

Common conditions include:

| Condition | Meaning |
|---|---|
| `always` | Run the action regardless of the build result |
| `success` | Run when the pipeline succeeds |
| `failure` | Run when the pipeline fails |
| `unstable` | Run when the result is unstable |
| `changed` | Run when the result differs from the previous build |

Post actions may publish reports, archive results, clean up resources, or send notifications. Their own failures should be observable and should not hide the original stage failure.

The Python and JavaScript implementations support the `always`, `success`, `failure`, and `unstable` conditions. The SQL model records build outcomes but does not execute post-build actions.

## 4. Scripted Pipeline

Scripted Pipeline uses Groovy control flow and Jenkins Pipeline steps to construct an execution process. It is more directly expressed as a program.

Its execution commonly uses `node` and `stage` blocks. The `node` step allocates an agent and provides a workspace. The `stage` step identifies a logical section of the build.

Scripted Pipeline can use standard programming constructs such as:

- Conditional statements.
- Loops and iteration.
- Variables and collections.
- Functions and closures.
- Exception handling.
- Dynamic stage selection.
- Parallel execution.
- Custom orchestration logic.

This flexibility is useful when the workflow depends on dynamically generated tasks or complex decisions.

### 4.1 Imperative execution

A scripted workflow can determine at runtime which stages to invoke. It can use ordinary control flow to select deployment targets, process a list of components, or construct parallel branches.

The Python implementation represents this model with `ScriptedPipeline` and `ScriptedRuntime`. The runtime exposes `node`, `stage`, and `parallel` operations. Its parallel operation uses a bounded thread pool and waits for all branches to complete.

The JavaScript and Java implementations provide similar imperative execution interfaces. The C++ implementation constructs a scripted-style pipeline through imperative stage registration.

### 4.2 Exception handling

Scripted workflows can use exception handling to control error behavior. A failed stage may be caught and handled, or the failure may be allowed to propagate and stop later operations.

Failure handling should preserve the original error and make the final build result accurate. A workflow should not silently convert a critical failure into success.

Scripted exception handling can be useful for optional work, recovery operations, and cleanup. It should not be used to bypass required validation.

## 5. Declarative and Scripted Pipeline Differences

| Area | Declarative Pipeline | Scripted Pipeline |
|---|---|---|
| Expression | Structured pipeline syntax | Imperative Groovy |
| Organization | Defined sections and directives | Program flow and Pipeline steps |
| Validation | Declarative syntax and model validation | General programming and runtime behavior |
| Control flow | Supported conditions and structured constructs | Full Groovy control flow |
| Dynamic workflow construction | More constrained | More flexible |
| Maintenance | Usually easier to standardize across teams | Depends more heavily on code organization |
| Typical application | Standard CI/CD workflows | Complex or dynamically generated workflows |

Declarative and Scripted Pipeline are not separate execution platforms. Both use Jenkins Pipeline capabilities. Declarative Pipeline can also contain permitted scripted sections, while Scripted Pipeline can use shared code and structured conventions.

The choice should reflect workflow complexity, governance requirements, maintainability, and the need for dynamic behavior.

## 6. Pipeline Scheduling and Agent Allocation

Jenkins uses agent labels and available executors to determine where work can execute.

A pipeline may request a general agent or a specialized one. Stage-level agent selection allows different environments to be used within the same build.

For example:

- Compilation may require a Linux environment with a compiler.
- Container packaging may require a Docker-capable agent.
- Windows packaging may require a Windows agent.
- Production deployment may require a restricted agent with approved network access.

Agent availability affects queue time and pipeline throughput. More executors do not automatically improve performance if the workload is constrained by memory, CPU, storage, network capacity, or shared services.

The C++ implementation models agent labels and executes independent dependency layers concurrently. The Java and JavaScript implementations use bounded worker execution. The SQL schema stores agent labels, online state, and executor counts.

## 7. Dependencies and Parallel Execution

A pipeline is often represented as a directed acyclic graph.

A dependency indicates that a stage must wait for another stage to complete successfully. Independent stages can run concurrently.

A typical dependency structure is:

Checkout  
→ Compile  
→ Unit Tests  
→ Package  
→ Deploy

An alternative structure executes independent checks in parallel:

Compile  
→ Unit Tests ─────────┐  
                       ├→ Package → Deploy  
Compile                │  
→ Integration Tests ──┘

A stage should not run when a required dependency has failed or has been skipped. The implementations represent dependency failures and skipped stages explicitly.

The JavaScript and Java implementations validate dependency references and detect cycles before execution. The C++ implementation uses graph validation and executes ready stages concurrently. The Python scripted implementation demonstrates parallel branches using a thread pool.

A valid dependency graph should not contain cycles. If Stage A depends on Stage B and Stage B depends on Stage A, neither stage can become ready.

Parallel execution can reduce elapsed build time, but it increases resource demand and requires care with shared workspace files, artifacts, environment values, and test infrastructure.

## 8. Failure, Retry, and Build Results

A pipeline stage can succeed, fail, become skipped, or be marked unstable.

| State | Meaning |
|---|---|
| Success | The stage completed successfully |
| Failed | The stage failed and requires attention |
| Skipped | The stage was not executed |
| Unstable | The stage or build completed with a non-success condition that does not necessarily stop all processing |

The exact effect of a stage result depends on pipeline logic and Jenkins steps. In the local implementations, required stage failures produce a failed build, while configured optional failures produce an unstable build.

### 8.1 Retries

Retries allow selected transient failures to be attempted again. Examples include temporary network failures or short-lived service unavailability.

Retries should be limited. Repeating a deterministic compilation error or invalid test assertion does not normally correct the underlying problem.

A retry policy should consider:

- Maximum retry count.
- Whether the operation is safe to repeat.
- Whether the failure is transient.
- The total time budget.
- The possibility of duplicate side effects.

The source implementations model retry counts and retain the number of attempts in their execution records. The PostgreSQL model stores attempts as separate stage-run records.

### 8.2 Timeouts

Jenkins Pipeline provides timeout behavior to limit how long selected workflow sections may execute. Timeout configuration prevents indefinitely waiting for an unavailable service or stalled operation.

The database model records a timeout budget for each stage. The local Python, JavaScript, C++, and Java examples focus on scheduling, dependencies, retries, and result states rather than forcibly terminating operating-system processes. Their simulated execution should not be interpreted as Jenkins timeout enforcement.

### 8.3 Build status

A build result is an aggregate outcome of its stages and pipeline logic.

A failed required stage normally prevents dependent stages from executing. Independent stages may still finish when the orchestration model permits it.

A skipped stage is not automatically a failure. It may represent a branch condition or a dependency that was not satisfied.

## 9. Credentials and Security

CI/CD pipelines often interact with source repositories, artifact registries, cloud platforms, deployment targets, and external services. These operations may require sensitive credentials.

Jenkins credentials management provides a mechanism for storing and referencing sensitive values. Pipeline code should refer to credential identifiers and use supported binding mechanisms rather than embedding secrets in source files.

Security controls include:

- Keep tokens and passwords out of source code.
- Use credential identifiers instead of literal secrets.
- Restrict credentials to the required job or stage.
- Use limited-scope service identities.
- Avoid printing credential values to build logs.
- Rotate credentials according to organizational policy.
- Restrict agent network access and operating-system permissions.
- Review shared-library code and third-party pipeline dependencies.
- Avoid exposing secrets through artifacts, environment dumps, or exception messages.

Log masking is a defensive measure, not a guarantee that secrets cannot leak. A pipeline should avoid creating sensitive log content in the first place.

The Python, JavaScript, and Java programs model credential lookup and redaction. The SQL schema stores credential metadata and stage bindings only. It deliberately excludes secret values.

## 10. Artifacts and Build Reproducibility

A pipeline commonly creates artifacts that are consumed by later stages or delivered to another environment.

An artifact should be associated with its originating build and source revision. Useful metadata includes:

| Field | Purpose |
|---|---|
| Artifact name | Identifies the output |
| Build number | Identifies the producing build |
| Commit SHA | Identifies the source revision |
| Checksum | Supports integrity verification |
| Storage URI | Identifies the artifact location |
| Creation time | Records when it was produced |

The examples register artifacts after compilation and packaging. The SQL model associates artifacts with builds and stage runs and requires a SHA-256 checksum.

A reliable deployment should promote a previously produced artifact rather than silently rebuilding different content during deployment. This improves traceability between testing and production delivery.

## 11. Python Implementation

The Python file models pipeline behavior through structured objects and runtime classes.

### Main components

| Component | Responsibility |
|---|---|
| `StageSpec` | Defines a stage, its agent, condition, retry count, and failure policy |
| `PipelineContext` | Holds parameters, environment values, credentials, artifacts, and logs |
| `StageResult` | Stores the outcome and attempt count of a stage |
| `DeclarativePipeline` | Executes a structured stage sequence and post actions |
| `ScriptedRuntime` | Provides imperative stage, node, and parallel operations |
| `ScriptedPipeline` | Runs a program that controls stage invocation |
| `PipelineResult` | Reports the pipeline outcome and produced artifacts |

The declarative example runs checkout, compilation, tests, packaging, and a conditional production deployment.

The scripted example uses a node scope, imperative stage calls, and parallel testing. It omits production deployment for a feature branch.

Credential values are redacted from log messages. The `bind_credential` context manager provides a scoped access pattern for the simulated credential.

The implementation uses Python's standard library. Its thread pool demonstrates local parallel execution without claiming to reproduce Jenkins agent scheduling.

## 12. JavaScript Implementation

The JavaScript file uses asynchronous programming and event-driven execution.

### Main components

| Component | Responsibility |
|---|---|
| `PipelineEngine` | Validates and executes declarative and scripted workflows |
| `CredentialStore` | Provides credential lookup and log redaction |
| `validateGraph` | Checks stage names, dependencies, and cycles |
| `mapLimit` | Limits concurrent stage execution |
| `executeStage` | Handles stage conditions, asynchronous actions, and retries |
| `runDeclarative` | Executes a dependency graph |
| `runScripted` | Exposes imperative stage, parallel, and node operations |

The event emitter reports stage starts, completions, failures, retries, and build completion.

Declarative execution waits until all dependencies of a stage have reached a terminal state. A stage is skipped if its dependencies did not succeed. Independent ready stages are processed using a concurrency limit.

Scripted execution uses asynchronous functions and `Promise.all` for parallel branches. This represents a different implementation approach from the graph-based scheduler.

The program runs with Node.js and uses only built-in modules.

## 13. C++17 Implementation

The C++ program models a pipeline as a dependency graph and uses the standard library for concurrent execution.

### Main components

| Component | Responsibility |
|---|---|
| `Pipeline` | Stores stage definitions and executes the workflow |
| `StageSpec` | Holds dependencies, agent, retries, condition, and action |
| `PipelineContext` | Stores branch information and artifact metadata |
| `StageResult` | Records state, attempt count, and failure message |
| `BuildReport` | Collects the final build state and stage results |

The dependency validation uses topological processing. Independent ready stages are launched through `std::async`.

The stage executor applies retry limits and distinguishes required failure from optional failure. A dependent stage is skipped if any dependency did not succeed.

The declarative example builds a payments application and includes a transient integration-test failure that succeeds on retry.

The scripted example constructs stages imperatively using a collection of quality checks. This illustrates how an imperative program can build a workflow dynamically.

The implementation uses no external libraries. Its concurrency is appropriate for the small demonstration graph; a large-scale scheduler would normally use a controlled worker pool and more detailed resource accounting.

## 14. Java 17 Implementation

The Java implementation uses enterprise-oriented domain types and a bounded executor service.

### Main components

| Component | Responsibility |
|---|---|
| `PipelineKind` | Identifies the pipeline style |
| `StageSpec` | Immutable stage definition |
| `PipelineDefinition` | Immutable declarative pipeline definition |
| `PipelineContext` | Holds parameters, credentials, artifacts, and logs |
| `PipelineEngine` | Validates and executes pipelines |
| `ScriptRuntime` | Exposes imperative stage and parallel operations |
| `StageRun` | Captures the outcome of a stage execution |
| `PipelineResult` | Captures the final pipeline result |

The Java implementation uses records for immutable domain data, interfaces for stage actions, predicates for conditions, and collections for workflow state.

Declarative stages are validated before execution. Their dependencies are processed in readiness layers, and independent stages use `CompletableFuture` with a bounded executor.

The scripted runtime provides explicit stage and parallel operations. Stage errors propagate through the runtime so that the final result can be marked as failed.

Credential access is scoped through an operation callback. Secret values are redacted from recorded logs.

## 15. PostgreSQL Implementation

The SQL file stores pipeline configuration and execution history as relational data.

### Main tables

| Table | Purpose |
|---|---|
| `pipelines` | Stores Declarative and Scripted pipeline definitions |
| `pipeline_stages` | Stores stage configuration, retry limits, agent labels, and approval requirements |
| `stage_dependencies` | Defines the directed stage dependency graph |
| `agents` | Stores agent labels and availability |
| `users` | Identifies requesters and reviewers |
| `builds` | Stores build number, source branch, commit, parameters, and result |
| `stage_runs` | Stores each stage attempt |
| `step_runs` | Stores step-level execution records |
| `artifacts` | Stores build outputs, checksums, and storage locations |
| `credential_catalog` | Stores credential metadata without secret material |
| `credential_bindings` | Maps credential references to pipeline stages |
| `approval_requests` | Stores manual deployment decisions |
| `pipeline_events` | Records workflow events |

### 15.1 Integrity enforcement

Primary keys and foreign keys protect entity relationships. Unique constraints prevent duplicate pipeline names, stage names within a pipeline, build numbers within a pipeline, and attempt numbers for a stage in a build.

Check constraints validate positive retry counts, positive timeout budgets, valid source commit formats, JSON object parameters, and checksum formats.

Triggers enforce legal build and stage state transitions. They also validate stage dependencies and require an approved request before a protected deployment stage can start.

Approval updates must move from pending to a final decision. A requester cannot approve their own deployment request, and the reviewer must be active.

### 15.2 Workflow functions

| Function | Responsibility |
|---|---|
| `start_build` | Moves a queued build into execution |
| `set_stage_state` | Requests a stage state transition |
| `finalize_build` | Validates required stage completion and derives the build state |
| `deployment_eligible` | Evaluates whether an approved deployment stage can start |

The `finalize_build` function checks the latest attempt for every required stage. It does not mark a build successful while required work remains queued or running.

### 15.3 Reporting

The views provide the latest stage attempt and a build-level summary. Additional queries retrieve build activity, dependency relationships, unsuccessful stages, artifacts, approvals, credential references, agent matches, and execution duration statistics.

Indexes support common access patterns, including recent builds, build state, stage attempts, dependency lookups, approval state, event history, and JSON parameter filtering.

The sample records demonstrate a successful build, a failed test build, a build waiting for production deployment, and a scripted nightly workflow.

## 16. Relationship Between the Implementations

| Technical concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Declarative workflow | Structured stage list | Validated dependency graph | Stage graph | Immutable definition | Pipeline and stage records |
| Scripted workflow | Runtime API | Async imperative API | Imperative stage construction | Script runtime | Pipeline kind and sample definition |
| Agent selection | Agent label | Agent label | Agent label | Agent label | Agent records and stage labels |
| Conditional execution | Callable condition | Predicate function | Condition callback | Predicate | Stage policy fields |
| Parallel execution | Thread pool | Promise concurrency | `std::async` | `CompletableFuture` | Stored execution attempts |
| Retry tracking | Attempt count | Attempt count | Attempt count | Attempt count | `stage_runs` |
| Credential handling | Scoped access and masking | Credential store | Context model | Scoped callback | Credential references |
| Artifact tracking | In-memory set | Artifact map | Artifact map | Concurrent map | Artifact table |
| Result processing | Build result object | Build state | Build report | Pipeline result | State functions and views |

Each implementation models the same underlying pipeline concepts while using language-specific mechanisms.

## 17. Execution

The examples use standard language runtimes and do not require third-party packages.

| File | Execution |
|---|---|
| Python | Run with Python 3 |
| JavaScript | Run with Node.js |
| C++17 | Compile with a C++17-compatible compiler |
| Java 17 | Compile and run `JenkinsPipelineDemo` |
| PostgreSQL | Execute the SQL file in a PostgreSQL session |

The SQL script drops and recreates the `jenkins_lab` schema. It is intended for a dedicated learning database and should not be run against a schema containing production data.

## 18. Limitations of the Local Models

The programs reproduce selected workflow concepts rather than the complete Jenkins implementation.

They do not implement Jenkins controller persistence, Pipeline Groovy CPS execution, plugin loading, shared-library resolution, actual node provisioning, workspace allocation, durable task monitoring, real credential providers, or actual shell and deployment steps.

The Python and C++ implementations use local threads for parallel work. The JavaScript and Java examples use their language runtimes' asynchronous execution facilities. None of these is a substitute for Jenkins executor scheduling.

The PostgreSQL schema stores execution records and applies selected state-transition rules. It is not a replacement for Jenkins build storage or controller state.

These boundaries are important when comparing a language-level pipeline simulation with a real Jenkins installation. A real deployment requires Jenkins configuration, appropriate agents, controlled credentials, job permissions, plugin compatibility, and operational monitoring.

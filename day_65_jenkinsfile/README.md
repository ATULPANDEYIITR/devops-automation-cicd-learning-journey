# Jenkinsfile: Pipeline Stages, Steps, Environment, and Post Actions

## 1. Jenkinsfile Fundamentals

A Jenkinsfile is a text-based pipeline definition used by Jenkins to describe how software should be built, tested, packaged, and deployed.

It is normally stored in the application's source-code repository. Jenkins reads the file and executes its declared workflow through a Pipeline job.

A Jenkinsfile provides:

- A repeatable build and deployment process.
- An ordered collection of pipeline stages.
- Individual execution steps within each stage.
- Environment variables shared across execution.
- Conditional execution.
- Failure handling.
- Post-build actions.
- Execution visibility and reporting.

The Pipeline as Code approach keeps CI/CD configuration under source control alongside application code.

### Declarative and Scripted Pipeline

Jenkins supports two principal pipeline styles.

| Feature | Declarative Pipeline | Scripted Pipeline |
|---|---|---|
| Structure | Defined using `pipeline` | Defined using Groovy statements |
| Entry point | `pipeline {}` | Typically `node {}` |
| Stage definition | `stages {}` | `stage()` |
| Execution steps | `steps {}` | Groovy execution statements |
| Environment | `environment {}` | Groovy variables and environment APIs |
| Post-processing | `post {}` | Explicit control flow and post-processing |
| Validation | Declarative syntax validation | Primarily Groovy compilation and runtime validation |
| Complexity | Structured and predictable | More flexible and programmatic |

Declarative Pipeline is appropriate for most standard CI/CD workflows. Scripted Pipeline is useful when execution requires more complex Groovy logic.

The implementations in this project model the core declarative concepts.

## 2. Declarative Pipeline Structure

A typical Declarative Jenkinsfile contains several major sections.

| Section | Purpose |
|---|---|
| `pipeline` | Defines the pipeline configuration |
| `agent` | Specifies where execution takes place |
| `environment` | Defines environment variables |
| `options` | Configures execution behavior |
| `parameters` | Defines user-provided build inputs |
| `triggers` | Defines automatic build triggers |
| `tools` | Selects configured build tools |
| `stages` | Contains the ordered workflow |
| `stage` | Represents a logical execution phase |
| `steps` | Contains executable operations |
| `when` | Controls conditional stage execution |
| `post` | Defines actions based on the final build result |

A conceptual workflow is:

    Jenkinsfile
        |
        v
    Pipeline Configuration
        |
        v
    Agent Allocation
        |
        v
    Environment Initialization
        |
        v
    Stage Execution
        |
        +---- Checkout
        |
        +---- Dependencies
        |
        +---- Build
        |
        +---- Test
        |
        +---- Security Checks
        |
        +---- Deployment
        |
        v
    Final Build Status
        |
        v
    Post Actions
        |
        +---- Always
        +---- Success
        +---- Failure
        +---- Unstable
        +---- Cleanup

A stage is a logical grouping of work. A step is an individual operation executed within that stage.

## 3. Pipeline Stages

A stage represents a major phase of the software delivery process.

Typical stages include:

| Stage | Responsibility |
|---|---|
| Checkout | Retrieve application source code |
| Dependencies | Install or resolve required packages |
| Build | Compile or package the application |
| Test | Execute automated tests |
| Security Scan | Identify vulnerabilities and policy violations |
| Package | Prepare distributable artifacts |
| Deploy | Release the application to an environment |
| Verification | Check the deployed application |

Stages provide a meaningful view of pipeline execution.

For example, a failed Test stage prevents subsequent deployment stages from executing under the normal sequential failure behavior.

### Stage execution states

| State | Meaning |
|---|---|
| PENDING | Stage has not started |
| RUNNING | Stage is executing |
| SUCCESS | All required steps completed |
| FAILURE | An execution step failed |
| SKIPPED | Execution conditions were not satisfied or an earlier failure prevented execution |

The Python, JavaScript, C++17, and Java implementations represent these states explicitly.

### Conditional stages

A Declarative Pipeline can use `when` to decide whether a stage should execute.

Common conditions include:

- `branch`: Executes for a specified branch.
- `environment`: Checks an environment variable.
- `expression`: Evaluates a Groovy expression.
- `changeset`: Checks whether matching files changed.
- `buildingTag`: Checks whether the build is associated with a Git tag.
- `triggeredBy`: Checks the build trigger.

A deployment stage might execute only when the source branch is `main`.

Conditions control execution eligibility. They do not replace authorization or deployment security controls.

## 4. Pipeline Steps

Steps are executable operations inside a stage.

A step can invoke a Jenkins operation, execute a shell command, run a test, publish an artifact, or interact with an external system.

### Common built-in steps

| Step | Purpose |
|---|---|
| `sh` | Execute a Unix shell command |
| `bat` | Execute a Windows batch command |
| `powershell` | Execute a PowerShell command |
| `echo` | Write a message to the build log |
| `checkout` | Retrieve source code |
| `dir` | Execute operations within a directory |
| `fileExists` | Check whether a file exists |
| `readFile` | Read a workspace file |
| `writeFile` | Write a workspace file |
| `archiveArtifacts` | Preserve build artifacts |
| `junit` | Publish JUnit-compatible test reports |
| `timeout` | Limit execution time |
| `retry` | Retry a block of operations |
| `withCredentials` | Expose credentials within a controlled scope |

Some steps are supplied by Jenkins plugins rather than the Pipeline core.

The availability of individual steps depends on the installed Jenkins plugins and configured execution environment.

### Shell execution

The `sh` step executes commands on Unix-like agents.

The `bat` step executes Windows batch commands.

The `powershell` step executes PowerShell commands.

Command execution should use controlled inputs. Untrusted branch names, parameters, or environment values must not be concatenated directly into executable shell commands.

### Step failure handling

A failed step normally fails its containing stage and the pipeline.

Declarative Pipeline provides mechanisms for controlled failure handling:

- `catchError`
- `warnError`
- `returnStatus`
- `retry`
- `timeout`

These mechanisms should be used selectively.

For example, a test failure should generally prevent production deployment. A noncritical reporting failure may be handled without changing the main build result.

## 5. Environment Variables

Environment variables provide configuration to pipeline execution.

They allow the same pipeline definition to operate across different applications, branches, and deployment environments.

### Global environment

Variables defined inside the pipeline-level `environment` section are available throughout the pipeline.

Common examples include:

| Variable | Example purpose |
|---|---|
| `APPLICATION_NAME` | Application identifier |
| `BUILD_NUMBER` | Jenkins build sequence |
| `GIT_BRANCH` | Source branch |
| `BUILD_ID` | Build identifier |
| `WORKSPACE` | Jenkins workspace directory |
| `DEPLOY_TARGET` | Deployment environment |
| `CI` | Continuous integration indicator |

Jenkins also exposes built-in environment variables through its execution environment.

### Stage-level environment

A stage can define its own environment variables.

Stage-level variables provide scoped configuration and can override inherited global values within that stage.

Example configuration:

- Global `DEPLOY_TARGET`: `development`
- Deployment-stage `DEPLOY_TARGET`: `staging`

The deployment stage uses `staging`, while other stages retain the global value.

The Python, JavaScript, C++17, and Java implementations demonstrate environment inheritance and stage-level overrides.

### Environment precedence

For the simplified execution model used in these implementations:

    Global Environment
            |
            v
    Stage Environment Overrides
            |
            v
    Effective Stage Environment
            |
            v
    Step Execution

Jenkins also supports environment contributions from build parameters, plugins, credentials bindings, and other execution contexts. Their effective behavior depends on scope and configuration.

### Secret management

Passwords, API keys, access tokens, and deployment credentials should not be committed to a Jenkinsfile.

Jenkins Credentials and `withCredentials` provide controlled access to stored credentials.

Important security practices include:

- Store credentials in Jenkins Credentials or an approved secret manager.
- Use credential identifiers instead of literal secret values.
- Restrict credential access to appropriate jobs and folders.
- Avoid printing credentials in console output.
- Limit the scope in which credentials are exposed.
- Rotate compromised credentials.
- Avoid passing secrets as command-line arguments when safer alternatives exist.

The PostgreSQL model stores secret references rather than actual secret values.

## 6. Post Actions

The `post` section defines operations that execute according to the final pipeline or stage result.

Post actions are useful for notifications, report publication, artifact archival, and cleanup.

### Post conditions

| Condition | Execution behavior |
|---|---|
| `always` | Executes regardless of the build result |
| `success` | Executes when the build succeeds |
| `failure` | Executes when the build fails |
| `unstable` | Executes when the build is unstable |
| `changed` | Executes when the result differs from the previous build |
| `fixed` | Executes when the build changes from unsuccessful to successful |
| `regression` | Executes when the build changes from successful to unsuccessful |
| `aborted` | Executes when the build is aborted |
| `cleanup` | Executes after other post conditions |

These conditions have different purposes.

For example:

- `always` is suitable for general completion logging.
- `success` is suitable for successful artifact publication.
- `failure` is suitable for failure notifications.
- `unstable` is suitable for test-quality warnings.
- `cleanup` is suitable for removing temporary resources.

A representative post-processing sequence is:

    Pipeline Execution
          |
          v
    Determine Final Result
          |
          +---- SUCCESS
          |       |
          |       v
          |   Success Actions
          |
          +---- FAILURE
          |       |
          |       v
          |   Failure Actions
          |
          +---- UNSTABLE
          |       |
          |       v
          |   Unstable Actions
          |
          v
    Always Actions
          |
          v
    Cleanup

The actual ordering of Declarative Pipeline post conditions is defined by Jenkins. A custom execution simulator should not be assumed to reproduce every Jenkins internal lifecycle detail.

A failure in a post action can affect the final build result. Post-processing should therefore be designed with clear failure policies.

## 7. Pipeline Failure and Recovery

A production pipeline must handle failures at several levels.

| Failure | Possible response |
|---|---|
| Git checkout failure | Stop execution and report source retrieval failure |
| Dependency installation failure | Stop build execution |
| Compilation failure | Prevent packaging and deployment |
| Unit test failure | Mark build as failed |
| Security scan failure | Enforce the configured security policy |
| Deployment failure | Stop release and initiate the defined recovery process |
| Notification failure | Record notification failure and apply notification-specific policy |
| Cleanup failure | Record the cleanup error and investigate remaining resources |

### Retry behavior

The `retry` step can repeat an operation when a transient failure occurs.

Retries are appropriate for operations such as temporary network access or service availability.

Retries are not appropriate for every failure.

A deterministic compilation error will normally remain unsuccessful after retrying.

### Timeout behavior

The `timeout` step limits the duration of an execution block.

Timeouts protect agents and pipeline resources from operations that do not terminate.

A useful timeout strategy includes:

- Short limits for simple validation.
- Moderate limits for compilation and tests.
- Longer limits for deployment and integration testing.
- Separate limits for individual stages and the overall pipeline.

### Unstable builds

An unstable result indicates that execution completed but one or more quality conditions were not satisfied.

For example, a pipeline may complete while reporting test failures or quality violations.

An unstable build is not equivalent to a successful build.

Production release policies should explicitly determine whether unstable results are permitted.

## 8. Python Implementation

File: `jenkins_pipeline.py`

The Python implementation creates a reusable pipeline simulation engine.

### Main classes

| Class | Responsibility |
|---|---|
| `JenkinsPipeline` | Coordinates pipeline execution |
| `Stage` | Represents a pipeline stage |
| `Step` | Represents an executable operation |
| `PostActions` | Groups result-dependent callbacks |
| `PipelineReport` | Stores final execution information |

### Execution behavior

The implementation:

1. Validates pipeline and stage configuration.
2. Executes stages sequentially.
3. Combines global and stage-specific environment values.
4. Evaluates stage conditions.
5. Executes steps.
6. Records execution history.
7. Stops normal execution after a mandatory step fails.
8. Marks remaining stages as skipped.
9. Executes applicable post actions.
10. Generates a structured JSON-compatible report.

### Important design decisions

The implementation uses:

- Dataclasses for pipeline configuration.
- Enums for execution states.
- Dictionaries for environment configuration.
- Lists for stages and execution history.
- Callable objects for steps and conditions.
- Exceptions for failure propagation.
- `time.perf_counter()` for duration measurements.
- Assertions to verify expected outcomes.

The timeout implementation detects an operation that exceeds its configured duration after the synchronous action returns. It cannot forcibly interrupt an arbitrary Python function. A production timeout implementation should use an interruptible subprocess, process isolation, or an external execution supervisor.

### Running the program

Execute `python jenkins_pipeline.py`.

The program demonstrates a successful inventory-service build and a separate failed-test scenario.

The failed-test scenario verifies that deployment is skipped.

## 9. JavaScript Implementation

File: `jenkins_pipeline.js`

The JavaScript implementation uses an event-driven execution model.

It is designed around asynchronous application workflows.

### Main classes

| Class | Responsibility |
|---|---|
| `JenkinsPipeline` | Executes the pipeline and publishes events |
| `PipelineStage` | Stores stage configuration and state |
| `PipelineStep` | Represents an asynchronous operation |
| `PipelineConfigurationError` | Identifies invalid pipeline configuration |
| `PipelineExecutionError` | Represents execution failures |

### Event-driven execution

The implementation extends Node.js `EventEmitter`.

Execution events include:

- `PIPELINE_STARTED`
- `STAGE_STARTED`
- `STAGE_SUCCESS`
- `STAGE_SKIPPED`
- `STEP_STARTED`
- `STEP_SUCCESS`
- `STEP_FAILURE`
- `PIPELINE_FAILURE`
- `PIPELINE_COMPLETED`

Consumers can subscribe to these events to display execution progress or integrate reporting systems.

### Dependency validation

Stages can declare explicit dependencies.

For example:

    Checkout
       |
       v
    Install
       |
       v
    Build
       |
       v
    Test
       |
       v
    Deploy

The implementation validates the dependency graph before execution.

A circular dependency is rejected.

A stage cannot execute successfully if its required predecessor did not succeed.

### Asynchronous execution and timeouts

The implementation uses:

- `async` and `await`.
- Promises.
- `AbortController`.
- `Promise.race()`.
- Node.js event handling.
- A `Map` for artifact storage.
- A JSON execution report.

The timeout mechanism requests cancellation using `AbortController`. An operation must cooperate with the supplied abort signal to stop its underlying work. Racing a promise against a timeout does not automatically terminate an arbitrary external process.

The report is saved to `pipeline-report.json`.

### Running the program

Execute `node jenkins_pipeline.js`.

Node.js standard-library modules provide the event, cryptographic, and file-system capabilities without requiring third-party packages.

## 10. C++17 Implementation

File: `jenkins_pipeline.cpp`

The C++ implementation models pipeline execution using explicit domain structures and a stateful execution engine.

### Main components

| Component | Responsibility |
|---|---|
| `JenkinsPipeline` | Pipeline coordination |
| `Stage` | Stage definition and execution state |
| `Step` | Executable stage operation |
| `ExecutionContext` | Environment and artifact state |
| `PostAction` | Result-dependent post-processing |
| `HistoryEntry` | Execution event information |
| `BuildStatus` | Pipeline-level status |
| `StageStatus` | Stage-level status |

### Engineering decisions

The implementation uses:

- `std::vector` for ordered stages and steps.
- `std::map` for deterministic environment and artifact storage.
- `std::set` for dependency validation.
- `std::unordered_map` for efficient stage lookup.
- `std::function` for executable callbacks.
- `std::chrono` for execution duration.
- Exceptions for execution failures.
- Strongly typed enums for status representation.

### Dependency graph

The dependency validator uses depth-first search.

Its complexity is:

- Time: \(O(V + E)\)
- Space: \(O(V)\)

Where:

- \(V\) represents the number of stages.
- \(E\) represents the number of dependency relationships.

Cycle detection occurs before execution.

### Execution behavior

The pipeline combines environment values, evaluates stage conditions, checks predecessor states, executes steps, records events, and processes post actions.

The implementation uses sequential execution to keep state transitions deterministic.

A production parallel execution engine would require synchronization, resource management, concurrency limits, and additional dependency-state handling.

### Compilation

Compile using:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic jenkins_pipeline.cpp -o jenkins_pipeline`

Run:

`./jenkins_pipeline`

On Windows:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic jenkins_pipeline.cpp -o jenkins_pipeline.exe`

`.\jenkins_pipeline.exe`

## 11. Java 17 Implementation

File: `JenkinsPipelineEnterprise.java`

The Java implementation represents an enterprise pipeline configuration with explicit domain types, immutable configuration objects, and service-oriented execution.

### Main components

| Component | Responsibility |
|---|---|
| `JenkinsPipeline` | Enterprise pipeline orchestration |
| `PipelineStage` | Immutable stage configuration with mutable execution state |
| `PipelineStep` | Executable operation |
| `PipelineContext` | Controlled environment and artifact access |
| `PipelinePolicy` | Configuration-level governance |
| `PostActionDefinition` | Typed post-action configuration |
| `ExecutionEvent` | Structured execution history |
| `PipelineReport` | Final execution report |

### Records

Java 17 records represent immutable data structures.

The implementation uses records for:

- Execution events.
- Step results.
- Stage reports.
- Pipeline reports.
- Post-action definitions.

These structures reduce boilerplate and make reporting data easier to handle.

### Interfaces

Functional interfaces represent operations that can be executed.

`PipelineAction` defines a step operation.

`PostAction` defines a post-build operation.

This separates pipeline orchestration from individual execution logic.

### Policy validation

`PipelinePolicy` checks configuration before execution.

The example requires test execution and explicitly controls production deployment.

A production system should also evaluate deployment approvals, environment permissions, credential access, artifact provenance, and security scan results.

### State transitions

The pipeline uses explicit states rather than relying on loosely structured strings.

Terminal states cannot be reused as active execution states.

The dependency graph is validated before any stage executes.

### Compilation and execution

Compile:

`javac --release 17 JenkinsPipelineEnterprise.java`

Run:

`java JenkinsPipelineEnterprise`

No third-party dependencies are required.

## 12. PostgreSQL Implementation

File: `jenkins_pipeline.sql`

The PostgreSQL implementation models pipeline configuration and execution history as relational data.

### Relational domain model

    projects
       |
       v
    pipelines
       |
       +---- pipeline_environment
       |
       +---- pipeline_stages
       |          |
       |          +---- stage_dependencies
       |          |
       |          +---- pipeline_steps
       |
       +---- post_actions
       |
       +---- builds
                  |
                  +---- stage_executions
                  |          |
                  |          +---- step_executions
                  |
                  +---- build_artifacts
                  |
                  +---- execution_events

### Database entities

| Table | Purpose |
|---|---|
| `projects` | Repository and project information |
| `pipelines` | Jenkins pipeline definitions |
| `pipeline_environment` | Global and stage-level environment configuration |
| `pipeline_stages` | Ordered stage definitions |
| `stage_dependencies` | Relationships between stages |
| `pipeline_steps` | Executable step definitions |
| `post_actions` | Conditional post-build operations |
| `builds` | Individual pipeline executions |
| `stage_executions` | Stage execution records |
| `step_executions` | Individual step execution records |
| `build_artifacts` | Published build artifacts |
| `execution_events` | Structured execution history |

### Integrity constraints

The database uses:

- Primary keys to identify records.
- Foreign keys to enforce relationships.
- Unique constraints to prevent duplicate stage and step ordering.
- Check constraints to validate status-independent configuration values.
- Triggers to reject invalid build transitions.
- Triggers to validate stage dependency relationships.
- Transactions to maintain consistent build completion.

### Recursive CTE

The stage dependency validation function uses a recursive common table expression.

It traverses existing dependency relationships and rejects a newly introduced dependency if it creates a cycle.

This prevents invalid execution graphs from entering the configuration.

### Build completion

The `complete_build()` function:

1. Locks the running build.
2. Verifies that it is eligible for completion.
3. Records the final status.
4. Sets the completion timestamp.
5. Calculates execution duration.
6. Records the completion event.

The function executes within the caller's transaction.

### Eligibility evaluation

The `evaluate_build_eligibility()` function evaluates:

- Whether the pipeline is enabled.
- Whether the build completed successfully.
- Whether pending stages remain.
- Whether failed stages remain.

It returns an eligibility result and a list of failed conditions.

This is a simplified database-level eligibility model. It does not replace Jenkins' actual pipeline execution engine.

### Reporting

The database provides queries for:

- Pipeline configuration retrieval.
- Build history.
- Stage-level execution details.
- Failed build identification.
- Average build duration.
- Stage failure frequency.
- Build success percentages.
- Environment configuration validation.
- Secret-reference inspection.
- Build eligibility.

### Security considerations

The SQL schema deliberately separates secret references from secret values.

Database permissions should restrict access to environment configuration and execution records.

Production deployments should use separate database roles for pipeline configuration, build execution, and reporting.

## 13. Jenkinsfile Execution Semantics

Understanding the relationship between stages, steps, environment variables, and post actions is essential.

| Mechanism | Controls | Does not independently provide |
|---|---|---|
| Pipeline | Overall execution structure | Application correctness |
| Stage | Logical execution phase | Automatic security approval |
| Step | Individual operation | Guaranteed successful execution |
| Environment | Runtime configuration | Secure secret storage by itself |
| Condition | Whether a stage executes | Authorization by itself |
| Post action | Result-dependent processing | Guaranteed external notification delivery |

A pipeline can be syntactically valid and still fail at runtime.

Examples include:

- An unavailable Jenkins agent.
- A missing tool installation.
- An invalid shell command.
- A failed test.
- A missing credential.
- An unavailable deployment endpoint.
- An incompatible plugin.
- A deployment permission error.

Pipeline configuration validation and execution validation are separate responsibilities.

## 14. Reliability and Performance Considerations

### Execution efficiency

Pipeline execution time can be reduced through:

- Dependency caching.
- Incremental builds.
- Parallel testing.
- Reusing build artifacts.
- Avoiding unnecessary workspace operations.
- Running only relevant test suites.
- Separating independent validation stages.

Declarative Pipeline supports parallel execution through the `parallel` and `matrix` constructs.

Parallel execution should be introduced only when dependencies and shared resources are properly managed.

### Resource management

Jenkins agents have finite resources.

Pipeline design should account for:

- CPU availability.
- Memory usage.
- Disk space.
- Network bandwidth.
- Concurrent build limits.
- Workspace cleanup.
- Container lifecycle.
- External service limits.

### Artifact management

Build artifacts should be associated with their originating build.

Useful artifact metadata includes:

- Artifact name.
- Build identifier.
- Commit SHA.
- Checksum.
- Storage location.
- Creation timestamp.
- Artifact size.

Checksums help verify artifact integrity.

Artifact retention policies should balance auditability and storage costs.

### Observability

Useful pipeline metrics include:

| Metric | Purpose |
|---|---|
| Build success rate | Measures execution reliability |
| Average build duration | Identifies slow pipelines |
| Stage failure rate | Identifies problematic phases |
| Deployment frequency | Measures release activity |
| Recovery time | Measures restoration efficiency |
| Queue duration | Identifies agent capacity constraints |
| Retry frequency | Identifies unstable dependencies |

Structured execution events provide a basis for monitoring and troubleshooting.

## 15. Security and Production Governance

A production Jenkinsfile should be designed with security boundaries.

### Source control

- Protect the Jenkinsfile through repository review.
- Restrict modifications to trusted contributors.
- Review changes to deployment logic.
- Avoid embedding sensitive values.
- Audit changes to shared pipeline libraries.

### Agent security

- Use dedicated agents for sensitive workloads.
- Avoid running untrusted pull-request code on privileged agents.
- Restrict agent network access.
- Apply operating-system security updates.
- Isolate build workspaces where appropriate.

### Credentials

- Use Jenkins Credentials.
- Apply least-privilege permissions.
- Avoid exposing credentials in logs.
- Restrict credential scope.
- Rotate credentials periodically.

### Deployment governance

Production deployments should enforce:

- Authorized deployment identities.
- Environment-specific permissions.
- Artifact integrity checks.
- Required test results.
- Security validation.
- Change approval where required.
- Deployment audit records.
- Recovery procedures.

### Pipeline configuration versus execution simulation

The four source implementations are independent execution models for learning pipeline behavior.

They demonstrate concepts associated with Jenkinsfiles but are not Jenkins plugins, Jenkins agents, or complete replacements for the Jenkins Pipeline execution engine.

The PostgreSQL implementation stores pipeline definitions and execution records. It does not directly execute Jenkins steps.

This distinction is important when translating a conceptual pipeline model into a production Jenkins environment.

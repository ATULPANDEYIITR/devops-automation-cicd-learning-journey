# Jenkins Freestyle Jobs: Jobs, Parameters, Triggers, and Workspace

## Scope

This project models a Jenkins Freestyle job as a configurable build workflow. The implementation separates four operational concerns:

| Concern | Role |
|---|---|
| Job | Defines the reusable build configuration and lifecycle |
| Parameters | Supply validated values to a build |
| Triggers | Determine which configured events can start a build |
| Workspace | Provides an isolated filesystem area for build execution and artifacts |

The implementations use the same domain scenario while deliberately using different engineering approaches in Python, JavaScript, C++17, Java 17, and PostgreSQL.

A typical workflow is:

Repository or external event
→ configured trigger
→ Freestyle job
→ parameter resolution
→ workspace allocation
→ ordered build steps
→ validation
→ artifact creation
→ build result
→ build history

## Jenkins Freestyle Job Model

A Freestyle job is a configurable Jenkins job type in which build behavior is assembled from job configuration such as parameters, triggers, build steps, and post-build behavior.

The job itself is persistent configuration. A build is an execution instance of that configuration.

The distinction matters:

- The job has a stable name and configuration.
- A build has a unique build number within the job.
- Parameters belong to the job definition but receive concrete values during a build.
- Triggers determine when a build may start.
- The workspace is execution state associated with a particular build.
- Build history records the result of previous executions.

The implementations use `release-application` as the representative Freestyle job.

## Parameters

The job defines two parameters:

| Parameter | Type | Default | Allowed values |
|---|---|---|---|
| `ENVIRONMENT` | choice | `staging` | `development`, `staging`, `production` |
| `VERSION` | string | `1.0.0` | Non-empty value |

Parameter resolution follows this sequence:

1. Confirm that every supplied parameter exists in the job configuration.
2. Use the supplied value when present.
3. Otherwise use the configured default.
4. Reject missing required values.
5. Validate choice parameters against their allowed values.
6. Store the resolved values with the build.

This prevents arbitrary parameter names from silently entering a build and makes the build record reproducible.

The release policy also rejects a `dev-` version when the target environment is `production`. This is a workflow validation rule rather than a generic parameter-type constraint.

## Triggers

The job supports three configured non-manual trigger categories:

| Trigger | Meaning in the model |
|---|---|
| `SCM` | A source-control event can initiate the build |
| `TIMER` | A scheduled execution can initiate the build |
| `UPSTREAM` | Another job can initiate the build |
| `MANUAL` | Explicit execution is always permitted by the model |

The trigger configuration is checked before execution. A trigger that is not configured for the job is rejected.

This distinction separates the event that starts execution from the build steps that execute after the job has started.

A trigger is not itself a build step. It is an entry condition for creating a build execution.

## Workspace Management

Each build receives a distinct workspace path:

`<workspace-root>/<job-name>/build-<build-number>`

For example:

`/var/lib/jenkins/workspace/release-application/build-3`

The Python, JavaScript, C++17, and Java implementations create build-specific directories. The PostgreSQL implementation stores the workspace path as build metadata because a database does not itself perform the filesystem operations.

The build workspace is used for:

- generated manifests
- temporary build state
- packaged artifacts
- build-specific files

Separating build directories prevents one simulated build from overwriting another build's files.

A production Jenkins installation can use workspace cleanup and Jenkins-managed workspace allocation. The model focuses on the state relationship rather than implementing Jenkins agents or filesystem locking.

## Build Lifecycle

The model treats a build as an execution record with a number, parameters, trigger, workspace, status, timestamps, and log.

The principal state values are:

| State | Meaning |
|---|---|
| `SUCCESS` | All configured build steps completed |
| `FAILURE` | A build step or validation rule failed |
| `ABORTED` | Execution was stopped before normal completion |

The source implementations primarily exercise `SUCCESS` and `FAILURE`.

A successful staging build uses:

`ENVIRONMENT=staging`

`VERSION=1.4.0`

A deliberately invalid production build uses:

`ENVIRONMENT=production`

`VERSION=dev-2.0.0`

The second execution fails because the release policy does not permit a development version for production.

A valid production build uses:

`ENVIRONMENT=production`

`VERSION=2.0.0`

and succeeds.

## Build Steps

The build is represented as an ordered sequence of operations:

1. Validate release parameters.
2. Create workspace metadata.
3. Create a versioned artifact.

The ordering is significant. Validation happens before packaging so an invalid production version cannot reach the artifact stage.

The Python implementation represents build steps as callable functions. JavaScript uses asynchronous functions. C++17 uses function pointers with a common signature. Java uses the `BuildStep` interface. PostgreSQL represents the configured steps relationally with explicit order.

## Python Implementation

The Python program models the job as a `FreestyleJob` dataclass-based object.

Important mechanisms include:

- `Enum` values for job, build, and trigger states.
- `ParameterDefinition` for parameter validation.
- `Build` for immutable-style build metadata plus execution logging.
- dictionaries for parameter definitions and resolved values.
- sets for configured triggers.
- callable builder functions for build stages.
- `pathlib.Path` for workspace operations.
- temporary directories for isolated execution.
- assertions for expected success and failure states.
- JSON serialization for build-history persistence.

The `run` method performs configuration validation, parameter resolution, workspace creation, ordered builder execution, exception handling, and build-history recording.

The implementation demonstrates a direct simulation of a job controller without depending on a Jenkins server.

## JavaScript Implementation

The JavaScript implementation emphasizes asynchronous filesystem operations and event-oriented processing.

`Map` stores parameter definitions and `Set` stores configured triggers. `ParameterDefinition` encapsulates validation, while `FreestyleJob` coordinates execution.

The Node.js standard library provides:

- `fs/promises` for asynchronous filesystem operations.
- `os` for temporary workspace allocation.
- `path` for platform-independent path construction.

Build steps are asynchronous functions. The job executes them sequentially with `await`, which models a build pipeline where a later step must not run until its predecessor completes.

The history is serialized to JSON after execution.

The JavaScript implementation also uses explicit error propagation through `JobError` and sets the process exit status when an unrecoverable error reaches the program boundary.

## C++17 Implementation

The C++17 program treats the job as a strongly typed execution engine.

The model uses:

- scoped enumerations for state and trigger categories.
- `struct` types for parameter definitions and builds.
- `std::map` for deterministic parameter storage.
- `std::set` for configured triggers and allowed choice values.
- `std::vector` for ordered build steps and build history.
- `std::filesystem` for workspace creation and cleanup.
- function pointers as a compact build-step strategy.
- exceptions for configuration and execution failures.

The build engine validates unknown parameters before execution and creates an isolated directory for every build.

C++ makes resource and filesystem operations explicit. The program removes its temporary workspace after the demonstration finishes.

The design is intentionally procedural around a typed domain object rather than reproducing the object patterns used by the Java implementation.

## Java 17 Implementation

The Java implementation models the job as an enterprise-oriented service object with explicit domain types.

It uses:

- records for immutable parameter and build representations.
- enums for job, build, and trigger states.
- an interface for build-step behavior.
- `EnumSet` for trigger configuration.
- immutable copies of collections at domain boundaries.
- `HashMap` for parameter lookup.
- Java streams for deterministic reporting.
- custom exceptions for domain validation failures.
- `Path` and `Files` for workspace management.

The `BuildStep` interface allows individual operations to be composed without coupling the job controller to a specific implementation.

Three concrete steps represent manifest creation, release-policy validation, and artifact creation.

The design makes the distinction between configuration, execution, and policy explicit.

## PostgreSQL Implementation

The PostgreSQL implementation treats the Freestyle job as persistent relational state.

The schema contains:

- `jobs`
- `job_parameters`
- `parameter_choices`
- `job_triggers`
- `build_steps`
- `builds`
- `build_parameters`
- `build_step_results`

The principal relationships are:

`jobs`
→ `job_parameters`

`job_parameters`
→ `parameter_choices`

`jobs`
→ `job_triggers`

`jobs`
→ `build_steps`

`jobs`
→ `builds`

`builds`
→ `build_parameters`

`builds`
→ `build_step_results`

Foreign keys enforce these relationships.

Unique constraints prevent duplicate parameter names within a job, duplicate trigger configurations, duplicate build numbers, and duplicate build-step orders.

Check constraints enforce valid names, positive build numbers, and valid timestamp ordering.

## PostgreSQL Validation and Transactions

The `validate_choice_parameter` trigger function checks that a value assigned to a choice parameter belongs to its configured choices.

This moves an important rule into the database rather than relying exclusively on application code.

The `start_build` function:

- locks the selected job.
- verifies that the job is enabled.
- verifies configured non-manual triggers.
- calculates the next build number.
- creates the build record.
- resolves defaults.
- validates required parameters.
- stores build parameter values.

The build examples execute inside transactions.

A build is initially represented as `ABORTED` while execution is incomplete. The final update changes it to `SUCCESS` or `FAILURE` and records `finished_at`.

This gives the relational model an explicit incomplete-execution state rather than pretending that every inserted build succeeded.

## Reporting Queries

The SQL script contains queries for several operational questions.

Configured job and trigger retrieval shows which events can start each job.

Parameter retrieval shows the exact values captured by each build.

Status aggregation counts successful and failed executions.

`v_latest_build` exposes the most recent build for every job.

The failure query identifies jobs whose latest build failed.

Duration reporting calculates execution duration from `started_at` and `finished_at`.

The final eligibility-style query combines job state and latest build state to identify whether a job's latest execution is operationally usable.

## State and Failure Handling

The implementations distinguish configuration failures from build failures.

Configuration failures include:

- duplicate parameter definitions.
- unknown parameters.
- unsupported parameter values.
- unconfigured triggers.
- disabled jobs.
- invalid required values.

Build failures include:

- release-policy violations.
- workspace or file-creation failures.
- exceptions raised by build steps.

A failure is recorded against the build rather than silently converting the job into a successful execution.

This distinction is important because a valid job configuration can produce a failed build, while an invalid request may be rejected before a build can be created.

## Security Considerations

Parameterized job execution can become dangerous when parameter values are inserted directly into shell commands. The implementations avoid executing arbitrary shell commands and treat parameter values as data.

The model therefore avoids command injection in the demonstration itself.

A production Freestyle job should apply additional controls:

- restrict who can configure jobs.
- restrict who can trigger sensitive production jobs.
- validate parameter values using allowlists where possible.
- avoid interpolating untrusted values into shell commands.
- protect credentials using Jenkins credential facilities rather than job parameters.
- isolate workspaces between jobs and agents.
- control artifact permissions.
- restrict administrative bypass capabilities.
- retain sufficient build history for auditing.
- clean temporary workspaces containing sensitive material.

The PostgreSQL model uses database constraints and triggers to reduce dependence on application-only validation.

## Performance Considerations

Parameter lookup uses keyed structures in the application implementations, giving efficient lookup for normal job configuration sizes.

Build steps are stored in ordered collections because execution order is part of the workflow semantics.

The SQL schema indexes:

- builds by job and start time.
- builds by status.
- build parameter values.

The `(job_id, started_at DESC)` index supports recent-build and history queries efficiently.

The database does not create indexes for every column. Indexes have maintenance cost during writes, so they are concentrated on relationships and reporting patterns represented by the queries.

Workspace creation is filesystem-bound rather than CPU-bound. Large artifact generation would require different storage and retention strategies in a production environment.

## Edge Cases

The implementations explicitly address several edge cases:

| Edge case | Handling |
|---|---|
| Disabled job | Execution rejected |
| Unknown parameter | Execution rejected |
| Missing required parameter | Validation failure |
| Invalid choice value | Validation failure |
| Unconfigured trigger | Execution rejected |
| Development version in production | Build failure |
| Duplicate parameter | Configuration rejected |
| Workspace creation failure | Build failure |
| Invalid build completion state | Database constraint |
| Duplicate build number | Database uniqueness constraint |

These cases distinguish predictable configuration errors from runtime build failures.

## Domain Relationships

The complete model can be viewed as:

`Job`

→ `Parameters`

→ `Triggers`

→ `Build Steps`

→ `Build`

→ `Resolved Parameters`

→ `Workspace`

→ `Step Results`

→ `Build Status`

The important boundary is between configuration and execution.

A job configuration can remain unchanged while many builds are created from it. Each build receives its own parameters, workspace, status, and execution history.

## File Responsibilities

| File | Responsibility |
|---|---|
| Python | Stateful Freestyle job simulation with dataclasses, validation, filesystem handling, and assertions |
| JavaScript | Asynchronous Node.js workflow with Maps, Sets, Promises, and JSON history |
| C++17 | Strongly typed build engine using STL containers, filesystem APIs, and exception handling |
| Java 17 | Enterprise-style domain model using records, interfaces, immutable collections, policies, and service-like build steps |
| PostgreSQL | Persistent relational model with constraints, triggers, functions, procedures, transactions, views, and reporting queries |

## Execution Characteristics

The Python program creates a temporary workspace and runs three builds.

The JavaScript program uses a temporary Node.js directory and performs asynchronous build operations.

The C++17 program uses `std::filesystem` and removes its temporary workspace after execution.

The Java program creates a temporary workspace and retains the path in the final report for inspection.

The PostgreSQL script creates the `jenkins_demo` schema, inserts representative job configuration and build records, executes transactional build workflows, and runs reporting queries.

No external runtime service is required by the Python, JavaScript, C++17, or Java demonstrations. The SQL deliverable requires PostgreSQL.

## Practical Workflow

A realistic parameterized Freestyle workflow represented by these artifacts is:

`SCM event`
→ `configured job trigger`
→ `parameter resolution`
→ `workspace allocation`
→ `release validation`
→ `build step execution`
→ `artifact creation`
→ `SUCCESS or FAILURE`
→ `build history`

The trigger answers whether execution should start.

The parameters define the values for that execution.

The workspace provides build-local filesystem state.

The build steps perform the configured work.

The status records the outcome.

The history makes previous executions observable and reportable.

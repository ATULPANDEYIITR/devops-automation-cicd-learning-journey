# GitHub Actions Job Dependencies and Conditional Execution

## Scope

This project models one of the central workflow-design mechanisms in GitHub Actions: the relationship between job dependencies, dependency results, and conditional execution.

The controlling concept is the job dependency expressed through `needs`. A workflow can contain independent jobs that run without waiting for one another, dependent jobs that form a directed execution graph, fan-out validation branches, and fan-in jobs that wait for several prerequisites. Conditional expressions then determine whether an otherwise ordered job is eligible to execute.

The implementations deliberately separate three concerns:

- **Dependency ordering** determines which jobs must finish before another job can be evaluated.
- **Dependency results** determine whether the normal success-based execution path remains available.
- **Conditional execution** determines whether a job should run when its prerequisites and workflow context have been evaluated.

This distinction is important because declaring a dependency is not equivalent to saying that the dependent job must always execute. A dependency creates an ordering relationship, while the condition defines the policy applied after that relationship has been satisfied.

The repository scenario used throughout the implementations is a CI/CD workflow containing build, validation, packaging, deployment, diagnostics, and matrix-style testing paths.

## Core Dependency Model

A workflow can be represented as a directed graph.

A job such as `unit-tests` that declares `build` as a dependency has an edge:

`build -> unit-tests`

The edge means that the test job cannot be evaluated before the build job reaches a terminal result.

A larger workflow can look conceptually like:

`build -> unit-tests -> integration-tests -> package -> deploy`

At the same time, independent validation can form a fan-out:

`build -> lint`

`build -> unit-tests`

`build -> security`

The package job then creates a fan-in:

`lint + unit-tests + security -> package`

This graph structure is more useful than thinking of a workflow as a simple sequential script. Independent jobs can be evaluated separately, while downstream jobs wait only for the dependencies explicitly declared for them.

The Python, C++, JavaScript, Java, and SQL implementations all model this distinction, but they do so using different mechanisms appropriate to each language.

## Job Dependencies

A dependency establishes an execution relationship between jobs.

In a GitHub Actions workflow, a job can declare dependencies using `needs`. A dependent job waits for the jobs named by `needs` before GitHub evaluates the normal execution path for that job.

For example, the conceptual relationship represented by:

`build -> unit-tests`

means that the test job should not start before the build has completed.

Multiple dependencies represent a fan-in relationship. A packaging job depending on `lint`, `unit-tests`, and `security` does not merely wait for one prerequisite. It has three explicit prerequisites.

This is useful when a release artifact should only be assembled after independent validation paths have completed.

The Python implementation represents dependencies with `Job.needs`. The workflow executor waits until every dependency has a recorded result before evaluating the dependent job.

The JavaScript implementation uses asynchronous job execution. Jobs that become ready at the same stage are executed through `Promise.all`, demonstrating how independent branches can be modeled as concurrent asynchronous work.

The C++ implementation stores the dependency graph in `DependencyGraph` and uses topological ordering to establish a valid execution sequence.

The Java implementation uses `JobDefinition.needs` and constructs an execution order with Kahn's topological sorting algorithm.

The SQL implementation represents dependency edges explicitly in `job_dependencies`. This makes the workflow graph queryable rather than embedding it only in application logic.

## Dependency Graph Validation

A workflow dependency graph must be structurally valid before execution.

Two important invalid states are missing dependencies and dependency cycles.

A missing dependency occurs when a job references a job that does not exist. For example, a workflow containing `deploy -> release-candidate` is invalid if `release-candidate` is not defined.

A cycle is more serious because no job in the cycle can become ready. A graph such as:

`build -> tests`

`tests -> build`

has no valid starting point.

The Python implementation detects cycles through depth-first graph traversal and also implements Kahn's algorithm separately for topological ordering.

The JavaScript implementation performs the same graph validation using `Set` objects for its visiting and visited states.

The C++ and Java implementations explicitly validate the graph before execution. This keeps malformed workflow definitions separate from runtime job failures.

The SQL schema uses foreign keys to prevent references to nonexistent job rows and a check constraint to prevent a job from depending directly on itself. Relational foreign keys cannot by themselves detect arbitrary multi-row cycles, so application-level graph validation remains necessary for complete cycle detection.

## Default Dependency Behavior

A useful mental model is:

`needs` establishes the dependency relationship.

The normal dependent-job path requires successful dependencies.

If a required dependency fails, a downstream job normally does not behave like an independent job that simply starts anyway. The failure propagates into the dependency-based eligibility decision.

The Python example `demonstrate_failure_propagation` makes this visible. `security-scan` fails, while an independent `documentation` job can still succeed. A `release` job depending on both is not eligible because one of its prerequisites failed.

This is different from saying that the entire workflow must immediately stop. Independent branches can have their own outcomes, and explicitly designed diagnostic or cleanup jobs can use different conditions.

## Conditional Execution

Conditional execution adds policy on top of dependency ordering.

A condition can consider workflow context, dependency results, event information, branch information, or other state exposed to the workflow.

The important architectural distinction is:

`needs` answers **when the dependency relationship has been satisfied sufficiently for evaluation**.

The condition answers **whether this job should execute**.

A production deployment may therefore depend on a successful package while also requiring the workflow to represent a production branch and an enabled release policy.

The Python implementation models this with a callable condition receiving job results and workflow environment.

The JavaScript implementation uses asynchronous condition functions receiving dependency results and workflow context.

The C++ case study represents conditions as `std::function` objects. The deployment condition checks the branch, event type, release flag, and package result.

The Java implementation represents conditions with `BiPredicate<Map<String, JobResult>, WorkflowEvent>`, keeping workflow policy explicit instead of burying it inside print statements.

The SQL model stores condition expressions and their evaluated outcomes as records so that policy evaluation can be audited.

## Failure, Skipping, and Explicit Failure-Tolerant Paths

A failed dependency and a skipped dependent job are different states.

A failure means the job actually executed and produced an unsuccessful result.

A skipped job means its execution was intentionally not performed because its eligibility conditions were not satisfied.

This distinction matters for debugging. If `security` fails and `package` is skipped, the root problem is the security job. The package job is not necessarily itself broken. It was prevented from executing because its dependency policy was not satisfied.

The Python workflow records `FAILURE` and `SKIPPED` independently.

The JavaScript workflow uses separate `JobStatus` values and preserves the dependency results that caused the downstream condition to evaluate to false.

The Java and C++ programs use explicit enumerations for these states rather than representing them with arbitrary strings.

Some workflow jobs should be able to execute after another job fails. Diagnostics, cleanup, artifact collection, and failure notifications are examples where unconditional or failure-tolerant conditions can be appropriate.

The implementations demonstrate this with diagnostic jobs.

This mechanism should be used deliberately. A diagnostic job that runs after a failure is fundamentally different from a deployment job that ignores failed validation.

## Fan-Out and Fan-In

A well-designed CI workflow often uses parallel validation.

After `build`, independent checks may include:

`lint`

`unit-tests`

`security`

None of these jobs necessarily needs the other validation jobs.

The package stage can then depend on all three.

This produces:

`build -> lint`

`build -> unit-tests`

`build -> security`

followed by:

`lint + unit-tests + security -> package`

This structure avoids artificial serialization. Making `security` depend on `unit-tests` when there is no technical reason for that relationship unnecessarily reduces parallelism.

The JavaScript implementation demonstrates this particularly clearly because ready jobs are evaluated through asynchronous execution.

The C++ and Java implementations represent the same topology through explicit graph structures.

The SQL implementation can inspect fan-in relationships using aggregation over `job_dependencies`.

## Matrix-Style Dependencies

CI workflows frequently test several runtime, operating-system, or configuration combinations.

A matrix can produce independent job executions such as:

`test-node-18`

`test-node-20`

`test-node-22`

`test-node-16`

The individual executions can finish independently, while a release policy can require every required matrix entry to pass.

The Python implementation models this with `MatrixJob` objects and evaluates the complete matrix with `all`.

The JavaScript implementation creates matrix-like entries and uses `every` to determine whether the aggregate release gate is open.

The C++ implementation uses `std::all_of`.

The Java implementation uses `Stream.allMatch`.

These examples demonstrate a useful distinction between individual job execution and aggregate eligibility. A matrix entry is one execution result; the release gate is a policy applied across the result set.

## Outputs and Data Dependencies

Ordering is not the only reason to use dependencies.

A downstream job may need an artifact or value produced by an upstream job.

The Python `build` job produces an `artifact` output. The unit-test job retrieves that output through its dependency context.

The JavaScript build job produces an artifact and a build identifier. The unit-test job validates that the artifact exists before continuing.

The Java implementation represents outputs as an immutable map inside `JobResult`.

The SQL implementation stores job outputs in `job_outputs`, allowing output records to be queried independently of job status.

This creates two different kinds of dependency:

- **Control dependency:** the downstream job waits for the upstream job.
- **Data dependency:** the downstream job needs information produced by the upstream job.

A workflow can have a control dependency without requiring an output, but a job that consumes an upstream artifact generally has both.

## Python Implementation

The Python program provides the most complete executable simulation.

`Workflow` owns the job definitions and execution results. `Job` stores the dependency list, optional condition, action, and failure policy. `JobResult` separates execution status, conclusion, outputs, and messages.

The `validate` method checks missing dependencies and cycles.

The `_run_job` method first collects dependency results, evaluates the default or explicit condition, and only then invokes the job action.

This is important because a job should not execute before its dependency state has been resolved.

The program also demonstrates:

- linear dependency chains;
- parallel dependency branches;
- failure propagation;
- explicit failure-tolerant diagnostic execution;
- environment-dependent conditions;
- matrix aggregation;
- topological sorting;
- invalid dependency detection;
- artifact output propagation;
- production-style release eligibility.

The `topological_order` function uses Kahn's algorithm with `O(V + E)` time complexity, where `V` represents jobs and `E` represents dependency edges.

## JavaScript Implementation

The JavaScript implementation emphasizes asynchronous execution.

`ActionsWorkflow` maintains jobs and completed results. Jobs that have all their prerequisites recorded are collected as ready work.

Ready jobs are executed through `Promise.all`, which represents concurrent CI branches more naturally than a purely sequential implementation.

`JobResult` is immutable with respect to its output map, preventing accidental mutation of stored job results.

Conditions receive:

- the completed result map;
- dependency-specific results;
- workflow context;
- the current job.

This makes conditions composable and keeps event-driven execution separate from policy evaluation.

The JavaScript file also models matrix-style validation, failure propagation, conditional production deployment, diagnostic execution, and topological graph analysis.

The asynchronous structure is especially useful for understanding why independent jobs should not be modeled as an unnecessarily long serial chain.

## C++ Case Study

The C++ program implements a repository release-engineering scenario.

The `DependencyGraph` class owns job definitions and validates graph structure. It implements topological ordering so that jobs are processed only after their prerequisites.

`RepositoryGovernanceEngine` adds workflow-event context to dependency execution.

The scenario contains:

`checkout -> build`

followed by independent:

`lint`

`unit-tests`

`security-scan`

and then:

`lint + unit-tests + security-scan -> package -> production-deploy`

The deployment condition checks whether the workflow represents a main-branch push and whether release execution is enabled.

The C++ program uses standard library containers such as `map`, `vector`, `queue`, and `set`. `std::function` is used for job conditions and actions because the workflow engine needs policy and execution behavior that can vary between jobs.

The program also demonstrates a diagnostic path that can run even after deployment is unsuccessful. This makes the distinction between normal dependency propagation and intentionally failure-tolerant work explicit.

## Java Implementation

The Java program models the workflow as an enterprise domain rather than as a collection of procedural examples.

`JobDefinition` contains a job name, dependency list, condition, action, and failure policy.

`WorkflowEvent` represents contextual information such as event type, branch, and release eligibility.

`JobResult` is an immutable record containing status, message, and outputs.

The workflow validates the dependency graph before execution and constructs an execution order using Kahn's algorithm.

The production policy is represented by a `BiPredicate`, allowing deployment eligibility to be expressed separately from the mechanics that execute deployment.

The example distinguishes pull-request validation from production deployment. Validation jobs can execute on the pull-request path, while deployment requires a main-branch push and an enabled release policy.

This is a useful enterprise design because dependency structure, execution behavior, event context, and policy are separate abstractions.

## SQL Data Model

The PostgreSQL script treats workflow execution as relational data.

`repositories` stores repository identity and its default branch.

`workflow_runs` represents a particular execution of a workflow and records the event type, branch, and release flag.

`workflow_jobs` stores the individual jobs and their statuses.

`job_dependencies` stores directed dependency edges. A row means that the child job requires the referenced parent job.

`job_outputs` stores data produced by jobs.

`workflow_job_attempts` records individual execution attempts.

`conditional_rules` records conditions and their evaluated results.

The schema uses foreign keys to preserve referential integrity. A job dependency cannot reference a nonexistent job, and a job cannot directly depend on itself.

Indexes are placed on dependency lookup, workflow status, output lookup, and job-attempt status because those access patterns are important when inspecting workflow execution.

## SQL Dependency Analysis

The script contains queries that calculate dependency readiness.

A job with no dependencies is immediately eligible under the default dependency rule.

A job with dependencies is eligible under the default rule only when every required dependency has status `success`.

The blocked-job query identifies the specific dependency responsible for preventing downstream execution.

The fan-in query identifies jobs that have multiple prerequisites and exposes the dependency set as an array.

The recursive common table expression expands the upstream dependency tree of `deploy`. This is useful when diagnosing why a high-level job cannot execute. Instead of inspecting only the immediate dependency, the query can expose the complete chain.

## Transactional State

Workflow state should not be updated carelessly when an execution attempt and its resulting job status must remain consistent.

The SQL script demonstrates a transaction that updates the package job and records its execution attempt together.

The transaction ensures that both database changes commit as one unit.

If an application fails between those operations, a rollback prevents a partial workflow history from being persisted.

The database therefore acts as an integrity boundary while the workflow engine remains responsible for higher-level graph and policy logic.

## Conditions Versus Dependencies

A common design mistake is treating every condition as a replacement for `needs`.

These mechanisms solve different problems.

A dependency expresses a structural relationship:

`package` needs `unit-tests`.

A condition expresses a decision:

`deploy` may execute only when the branch is `main` and release execution is enabled.

A workflow can therefore have:

`unit-tests -> package -> deploy`

where `needs` establishes the order, while the deployment condition adds branch and release-policy requirements.

Removing a dependency simply because a condition mentions the upstream job can change the workflow's execution graph and may permit the dependent job to be evaluated before the required upstream work has completed.

## Conditional Diagnostics

Failure diagnostics illustrate why explicit conditions are valuable.

Suppose:

`build -> deploy`

and the build fails.

A normal deployment path should not proceed.

A diagnostic path can deliberately depend on the deployment stage while using a failure-tolerant condition. The diagnostic job can inspect the deployment state and record information even though deployment did not succeed.

This creates two policies:

`deploy`: success-dependent execution.

`diagnostics`: terminal-state-dependent execution.

The distinction prevents failure handling from being confused with successful release execution.

## Debugging Unexpectedly Skipped Jobs

When a downstream job is skipped, debugging should begin with its declared dependencies rather than with the skipped job's action.

The relevant questions are:

- Which jobs appear in its dependency set?
- Did every dependency reach a terminal state?
- Which dependencies succeeded?
- Which dependency failed or was skipped?
- Does the job have an explicit condition?
- Does the condition depend on branch, event, environment, or another result?
- Is the condition intentionally failure-tolerant?
- Is the workflow graph missing a required dependency?
- Is a job output being consumed without being produced?

The SQL recursive dependency query is particularly useful for tracing an entire upstream chain.

The Python, C++, and Java graph validators are useful for detecting malformed dependency structures before execution.

## Common Design Failures

### Unnecessary Serialization

Making every job depend on the previous job creates a long serial pipeline even when tasks are independent.

For example, forcing `security` to wait for `unit-tests` adds latency if security analysis only needs the build artifact.

Independent validation should share the minimum necessary prerequisite.

### Missing Data Dependencies

A job may depend on `build` for ordering but still fail because the expected artifact was never produced.

The dependency graph guarantees ordering, not the correctness of every output.

Consumers should validate required outputs explicitly.

### Overly Broad Failure-Tolerant Conditions

Allowing a deployment to ignore failed dependencies can create a release path that bypasses the very validation the workflow was designed to enforce.

Failure-tolerant execution is better suited to diagnostics, cleanup, reporting, or other tasks whose purpose is to operate after failure.

### Hidden Policy

If branch, release, or environment requirements are buried inside arbitrary action code, the workflow becomes harder to reason about.

Conditions should express important execution policy explicitly.

### Cyclic Dependencies

A dependency cycle prevents the graph from reaching a valid starting state.

Graph validation should happen before executing real work.

## Performance Considerations

Dependency resolution is fundamentally a graph problem.

For `V` jobs and `E` dependency edges, topological sorting can be performed in `O(V + E)` time.

The practical execution time of a CI workflow is different because actual jobs consume compute time. Parallel independent jobs can reduce elapsed workflow time even when the total amount of work remains unchanged.

Fan-out therefore improves latency when the runner capacity and job workloads permit concurrent execution.

Excessive fan-in can increase the critical path because a downstream job must wait for every prerequisite.

The most effective dependency graph is usually the smallest graph that accurately represents real technical prerequisites.

## Security Considerations

Dependency conditions can control high-impact operations such as deployment.

Production deployment should not be made failure-tolerant merely to keep a workflow moving.

Conditions that use branch, event, environment, or release flags should be evaluated carefully because those values influence execution authority.

Sensitive credentials should not be exposed through ordinary job outputs or diagnostic messages.

A workflow should also avoid creating an implicit release path where an informational job failure is ignored accidentally or where a required validation job is omitted from the deployment dependency graph.

The database model reinforces structural integrity but does not replace repository-level security controls or GitHub Actions permission configuration.

## Production Considerations

A production workflow benefits from clear dependency boundaries.

Build jobs should produce artifacts.

Validation jobs should consume the appropriate build state.

Independent checks should remain independent unless there is a real technical dependency.

Aggregation jobs should depend on every validation result that is genuinely release-blocking.

Deployment should depend on the release candidate and apply explicit environment or event policy.

Diagnostics should be designed separately from release eligibility so that failures can still be investigated without weakening the deployment gate.

This separation makes the workflow easier to reason about, debug, optimize, and audit.

## Implementation Relationship

The five executable implementations approach the same dependency model from different technical perspectives.

| Implementation | Primary perspective |
| --- | --- |
| Python | Full executable workflow simulator with validation, conditions, outputs, and graph algorithms |
| JavaScript | Asynchronous event-driven workflow execution and concurrent dependency branches |
| C++ | Repository release-engineering engine with explicit graph and policy objects |
| Java | Enterprise domain model using records, interfaces, predicates, collections, and explicit state |
| PostgreSQL | Relational representation of workflow runs, jobs, dependency edges, outputs, attempts, and policy evaluation |

The implementations are intentionally not translations of one another. Each uses language-specific mechanisms to expose a different aspect of dependency-oriented workflow design.

The common architectural principle remains the same: define the dependency graph explicitly, evaluate dependency results separately from policy conditions, and make failure-tolerant execution an intentional decision rather than an accidental consequence of workflow structure.

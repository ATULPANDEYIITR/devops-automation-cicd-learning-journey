# GitHub Actions Basics: Workflow Files, Events, Jobs, and Steps

## Purpose

This repository presents GitHub Actions as an execution model built from four closely connected mechanisms: workflow files, events, jobs, and steps.

A workflow file defines automation in the repository. An event determines when that workflow is eligible to start. Jobs divide the workflow into execution units, usually associated with separate runners. Steps are the ordered operations performed inside each job.

The three implementations approach the same subject from different technical perspectives:

- The Python program builds an executable workflow simulator with event matching, dependency graphs, matrix expansion, conditions, outputs, validation, failure handling, and security-oriented checks.
- The JavaScript program models workflow execution as an event-driven system using Node.js `EventEmitter`, asynchronous functions, action registration, matrix expansion, job dependencies, and conditional deployment.
- The C++ program treats a repository CI pipeline as a dependency-graph case study and uses C++17 data structures and algorithms to validate and execute jobs.

The examples use repository-development scenarios such as linting, testing, building, pull-request validation, and deployment.

## GitHub Actions Mental Model

A useful conceptual flow is:

`repository event -> workflow trigger -> jobs -> steps -> job result -> dependent jobs`

The layers have different responsibilities.

A **workflow file** describes automation. It normally lives in `.github/workflows/` and uses YAML.

An **event** is something that can cause a workflow run, such as a push, pull request activity, manual dispatch, or scheduled execution.

A **job** is a collection of steps executed on a runner. Jobs are separate execution units. If two jobs both need the repository source, each job should explicitly establish the required workspace state rather than assuming that another job's filesystem is available.

A **step** is an individual operation inside a job. A step can run a shell command or invoke a reusable action.

This separation matters because changing one layer does not automatically change the responsibilities of the others. Adding a `push` trigger does not define what the workflow does. Adding a second step does not create a second runner. Adding a second job does create another execution unit.

## Workflow Files

A GitHub Actions workflow is normally represented by YAML under `.github/workflows/`.

A minimal conceptual workflow contains a workflow name, an event trigger, and one or more jobs. A compact example is represented here in inline form rather than a nested Markdown code fence:

`name: Continuous Integration`

`on:`

`  push:`

`    branches: [main]`

`jobs:`

`  test:`

`    runs-on: ubuntu-latest`

`    steps:`

`      - name: Run tests`

`        run: python -m pytest`

The important structural relationship is:

`name -> on -> jobs -> job -> steps`

The `jobs` mapping uses identifiers such as `test`, `build`, or `deploy`. These identifiers are used when another job declares `needs`.

The `runs-on` value identifies the runner environment for the job. A GitHub-hosted runner label such as `ubuntu-latest` describes the requested runner environment. The exact software installed on a hosted runner can change over time, so production workflows should not assume that every tool version remains permanently identical.

The `steps` sequence is ordered. This ordering is significant when one step prepares state used by a later step.

A workflow file is declarative. It describes desired automation rather than implementing a conventional top-to-bottom application program.

## Events

Events control when a workflow run can begin.

Common development-oriented events include:

- `push` runs in response to pushes that match its configuration.
- `pull_request` runs for selected pull-request activity.
- `workflow_dispatch` allows a workflow to be started manually.
- `schedule` can start workflows according to a schedule.
- `workflow_call` allows one workflow to be invoked by another reusable workflow.

The event is not the same thing as a job. A `pull_request` event can trigger a workflow, after which several jobs may run.

Event configuration can include filters. Branch filters are particularly important because a repository may want different automation behavior for `main`, development branches, or selected release branches.

The Python implementation represents an event with `Event`, including the event name, branch, actor, and payload. Its `event_matches` function separates trigger evaluation from execution.

The JavaScript implementation uses `RepositoryEvent` and Node.js `EventEmitter`. This reflects JavaScript's event-driven programming model: listeners subscribe to an event and receive its payload when the event is emitted.

The C++ implementation uses `RepositoryEvent` as a value object and evaluates it through `event_matches`. This makes the event-to-workflow relationship explicit without coupling the event representation to the job implementation.

### Event payloads

An event can carry contextual information. For a pull request, useful information can include the pull-request number, action, branch context, and actor.

A workflow can use event context to decide whether a job should execute, but untrusted event values require care when they are placed into shell commands. A pull-request title, branch name, issue body, or other user-controlled text should not be blindly interpolated into executable shell source.

## Jobs

A job groups related steps and assigns them to a runner.

For example, a CI workflow may have independent jobs for:

`lint`

`test`

`build`

`deploy`

These are not merely headings. Each job represents an execution boundary.

The Python simulator models jobs with the `Job` dataclass. It records the runner, steps, dependencies, environment, matrix configuration, status, and outputs.

The JavaScript implementation uses `WorkflowJob`, where the constructor captures the job identifier, runner, dependencies, steps, conditions, matrix, and environment.

The C++ implementation uses a `Job` structure containing `needs`, `steps`, a condition function, matrix dimensions, environment values, outputs, and status.

### Job isolation

Separate jobs should not be treated as if they share one continuous shell session.

For example, if a `test` job downloads dependencies and creates a temporary file, a later `build` job should not rely on that file still existing. The build job should recreate the required state or receive data through an explicit transfer mechanism such as an artifact.

The Python demonstration makes this boundary visible by giving each job its own temporary workspace.

The JavaScript implementation similarly creates a new workspace object for each job execution.

The C++ case study models the job boundary through a separate `JobContext`.

## Steps

Steps are the operations within a job.

A common sequence is conceptually:

`checkout -> setup runtime -> install dependencies -> lint -> test -> build`

The exact sequence depends on the repository.

The key distinction is that these operations are steps of one job when they need to share the same runner environment and workspace.

A checkout step establishes repository content. A setup step establishes a runtime or toolchain. A test step consumes source and dependencies. A build step consumes the validated source.

The Python `Step` class can contain either a callable or a shell command. Its execution method applies conditions and step-specific environment values before invoking the implementation.

The JavaScript `WorkflowStep` class demonstrates a more JavaScript-specific design. It supports either a function or an action-like `uses` reference and executes asynchronously.

The C++ `Step` structure stores a `std::function` so the case-study engine can execute different operations through the same abstraction.

### `run` and `uses`

A `run` step executes a command or command-like operation.

A `uses` step invokes an action. Actions package reusable automation. A common example is a repository checkout action.

The JavaScript implementation registers an action named `actions/checkout` and dispatches it through an action registry. This does not contact GitHub; it models the architectural distinction between an inline command and reusable action invocation.

## Job Dependencies

Jobs can depend on other jobs through `needs`.

A workflow might express:

`build needs test`

and:

`deploy needs build`

The resulting dependency graph is:

`test -> build -> deploy`

If linting must also succeed before a build, the graph can be:

`lint -> build`

`test -> build`

`build -> deploy`

This is different from putting all operations into one long list of steps. The graph defines relationships between execution units.

The Python implementation uses a depth-first traversal to calculate a dependency-safe order and detect cycles.

The JavaScript implementation uses a depth-first topological traversal and throws an error when it encounters a cycle.

The C++ implementation uses Kahn's topological sorting algorithm. It calculates indegrees and maintains a queue of jobs that currently have no unmet dependencies. If the resulting ordering does not contain every job, the workflow contains a cycle.

A cycle such as:

`build needs test`

`test needs build`

cannot produce a valid execution order. Neither job can become ready first.

## Conditions

A job or step can have conditions that determine whether it runs.

A practical deployment rule might be conceptually:

`event.name == "push" && event.branch == "main"`

This allows pull-request validation to use the same workflow while preventing the deployment job from executing merely because a pull request was opened.

The Python implementation attaches a callable condition to jobs and evaluates it using `WorkflowContext`.

The JavaScript implementation uses asynchronous condition functions. This fits naturally with JavaScript's ability to compose asynchronous workflow decisions.

The C++ implementation stores a `std::function<bool(const RepositoryEvent&)>`, allowing a job to evaluate the event without embedding event-specific logic directly into the workflow engine.

Conditions should be designed around explicit repository requirements. A deployment condition should not rely only on the existence of a branch string if the actual release process requires additional gates.

## Environment Variables and Context

GitHub Actions exposes workflow and runner context through environment variables and expression contexts.

The implementations model several useful values:

- Event name
- Branch or reference name
- Actor
- Runner operating system
- CI indicator
- Matrix values
- Job-specific environment values

The Python program constructs an execution environment containing values such as `GITHUB_EVENT_NAME`, `GITHUB_REF_NAME`, and `GITHUB_ACTOR`.

The JavaScript implementation creates an environment object and merges workflow-level, job-level, and matrix values.

The C++ case study uses `std::map<std::string, std::string>` for the job context.

Environment scope matters. A value needed by one job should not be assumed to exist in another job unless it is explicitly recreated or transferred.

Sensitive values should be stored through appropriate secret mechanisms rather than committed to workflow source.

## Matrix Jobs

A matrix lets one logical job definition execute against several combinations of configuration values.

For example:

`node: [20, 22]`

and:

`database: [postgres, sqlite]`

produces four combinations:

`Node 20 + PostgreSQL`

`Node 20 + SQLite`

`Node 22 + PostgreSQL`

`Node 22 + SQLite`

The matrix is therefore a Cartesian product.

The Python `expand_matrix` function constructs these combinations directly.

The JavaScript implementation uses `reduce` and `flatMap` to expand the dimensions into concrete variants.

The C++ implementation uses vectors and maps to generate combinations iteratively.

Matrix jobs are useful for compatibility testing because one workflow definition can validate several supported environments.

The trade-off is execution cost. A matrix with many dimensions can multiply the number of runner executions rapidly. Matrix design should therefore reflect meaningful compatibility requirements rather than every theoretically possible combination.

## Job Outputs

A job can expose selected information as outputs for later workflow logic.

The Python simulator's `ExecutionContext.set_output` stores output values on the job.

The JavaScript workflow stores outputs in the `WorkflowJob` instance and exposes them through the engine's output map.

The C++ case study records an artifact name and source branch in `JobContext::outputs`.

Outputs should represent deliberate interfaces between workflow components. They are not a substitute for sharing arbitrary filesystem state between jobs.

For larger generated files, workflow artifacts are conceptually different from small string outputs. An output communicates a value; an artifact transfers a file or collection of files.

## Failure Handling

A normal step failure can stop the current job.

If a job fails, jobs that require it through `needs` normally cannot proceed as successful downstream work.

The Python simulator demonstrates this by returning `JobStatus.FAILURE` and preventing dependent jobs from executing.

The JavaScript implementation distinguishes ordinary failure from `continueOnError`. A step configured with `continueOnError` can fail while allowing subsequent steps in the same job to continue.

The C++ case study demonstrates dependency failure propagation: when the test job fails, the build job is skipped because its required dependency did not succeed.

This distinction is important:

`step failure -> may fail job`

`job failure -> can prevent dependent jobs`

`continue-on-error -> changes how a selected failure affects subsequent execution`

A workflow should use non-blocking failures deliberately. Making critical validation non-blocking can allow a workflow to appear successful even when an important check failed.

## Pull Request CI Scenario

A pull-request workflow commonly validates proposed changes before they are incorporated into a protected branch.

A useful structure is:

`pull_request -> lint`

`pull_request -> test`

`lint + test -> build`

The Python implementation has a dedicated `demonstrate_pull_request_ci` function that models linting and testing as separate jobs and makes the build depend on both.

The JavaScript implementation uses a `pull_request` event containing a pull-request number, action, title, and draft state. The same workflow definition can then be executed against a different event type.

The C++ implementation uses `RepositoryEvent` with `action = "opened"` for a pull request and executes the validation graph without treating the pull request itself as a deployment.

This demonstrates the difference between an event and the jobs that the event causes to run.

## Workflow Validation

Workflow configuration is itself a source of failure.

Common structural problems include:

- Missing workflow triggers.
- No jobs.
- A job without `runs-on`.
- A job without steps.
- A dependency referring to a nonexistent job.
- Cyclic dependencies.
- Empty matrix dimensions.
- Steps that define neither a command nor an action.

The Python `validate_workflow_structure` function checks a simplified dictionary representation of workflow YAML and validates job dependencies through the same graph logic used during execution.

The JavaScript `WorkflowEngine.validateWorkflow` performs analogous structural checks.

The C++ `WorkflowEngine::validate` verifies workflow metadata, jobs, runners, steps, dependency references, and graph validity.

These validators are educational models rather than complete replacements for GitHub's workflow syntax and validation rules.

## Security Considerations

CI configuration is executable infrastructure. A workflow can access source code, credentials, deployment systems, package registries, cloud resources, and other services depending on its permissions.

A few security principles are directly relevant to workflow design.

### Least privilege

Workflow permissions should be limited to what the workflow requires.

A read-only testing job generally should not receive write access to repository contents.

The Python security demonstration flags unnecessarily broad modeled permissions.

### Untrusted event data

Pull requests from external contributors can contain user-controlled values. These values must not be treated as trusted shell source.

For example, embedding an untrusted pull-request title directly into a shell command can create command-injection risk.

The Python implementation explicitly checks for a modeled unsafe interpolation pattern and documents the concern.

The JavaScript implementation uses `execFile` for its real Node.js subprocess demonstration rather than constructing a shell command from user-controlled strings.

### Secrets

Secrets should not be committed directly into workflow files or source code.

A workflow should expose a secret only to the job and steps that actually require it.

Logs should also be designed so credentials are not intentionally printed.

### Third-party actions

Reusable actions execute code with the permissions available to the workflow. Production repositories should evaluate the actions they depend on and consider version-pinning strategies where appropriate.

The educational JavaScript action registry demonstrates the abstraction without downloading external action code.

## Runner and Workspace Behavior

A runner executes a job.

Within a job, successive steps normally share the job's execution context. This makes sequences such as:

`checkout -> install -> test`

possible without repeating checkout between every step.

Separate jobs should be considered separate execution environments.

The Python program creates temporary workspaces to make this boundary concrete.

The JavaScript program creates a new workspace object for every job execution.

The C++ program represents the environment through `JobContext`, which is created when a concrete job variant executes.

This is why a later job should not rely on an untransferred file produced by an earlier job.

## Python Implementation

The Python program is an executable simulator rather than a static description.

Its `Event` class represents repository events. `Workflow` stores trigger configuration and jobs. `Job` represents a runner-bound execution unit, while `Step` models ordered work.

The `event_matches` function demonstrates trigger filtering.

`topological_order` detects invalid job dependency cycles and determines a dependency-safe execution sequence.

`expand_matrix` demonstrates Cartesian-product matrix execution.

`execute_job` handles step ordering, step conditions, environment construction, failures, and `continue_on_error`.

The program also creates an actual temporary Python project and executes deterministic test assertions. It attempts `pytest` when available and falls back to direct assertions so the example remains executable without an external package.

The workflow validator demonstrates how configuration errors can be detected before execution.

The pull-request CI example separates linting and tests from the build job, demonstrating a realistic dependency graph.

The security example focuses on workflow-specific risks such as excessive permissions and unsafe event-data interpolation.

## JavaScript Implementation

The JavaScript implementation uses Node.js capabilities that are particularly suited to event-driven automation.

`RepositoryEvent` extends `EventEmitter`. Repository events can therefore be emitted and consumed by listeners.

`WorkflowStep` models asynchronous step execution. It supports either a function or a reusable action reference.

`WorkflowJob` represents the job boundary and implements matrix expansion through JavaScript collection operations.

`WorkflowEngine` performs workflow validation, topological ordering, dependency evaluation, matrix execution, conditions, environment construction, and output collection.

The action registry demonstrates the architectural distinction between `run`-style work and `uses`-style reusable operations without requiring an external npm dependency.

The real subprocess demonstration uses Node's `execFile`, showing how a JavaScript workflow tool can invoke another executable while avoiding unnecessary shell parsing.

The same workflow definition is executed against a pull-request event and a push-to-main event. The deployment condition makes their behavior different without duplicating the workflow definition.

## C++ Case Study

The C++ program models a repository's continuous integration and delivery pipeline as a directed acyclic graph.

The case-study workflow contains:

`lint`

`test`

`build`

`deploy`

The `build` job depends on both `lint` and `test`. The `deploy` job depends on `build` and additionally checks that the event is a push to `main`.

The test job has a compiler matrix containing `gcc-13` and `clang-18`. Matrix expansion produces separate concrete test executions.

`DependencyGraph` implements Kahn's topological sorting algorithm. Its indegree representation makes the relationship between prerequisites and ready jobs explicit.

The workflow engine validates dependency references and detects cycles before execution.

`JobContext` represents the information available during a concrete job execution, including event data, runner information, environment values, matrix values, and outputs.

The failure case study deliberately makes a regression test fail. The dependent build job is then skipped because its required test dependency failed.

The invalid-workflow case deliberately creates:

`first needs second`

and:

`second needs first`

The dependency graph rejects the cycle rather than attempting to execute an impossible workflow.

This case study is useful for understanding that GitHub Actions jobs form a dependency graph rather than simply a single sequential program.

## Workflow, Event, Job, and Step Distinctions

| Mechanism | Primary responsibility | Example in the implementations |
|---|---|---|
| Workflow file | Defines automation structure and triggers | `Workflow`, workflow objects, validation |
| Event | Determines whether a workflow run starts | `push`, `pull_request` |
| Job | Defines an execution unit and runner | `test`, `build`, `deploy` |
| Step | Performs ordered work within a job | checkout, lint, test, build |
| `needs` | Defines job dependency relationships | `build` depends on `lint` and `test` |
| Matrix | Creates multiple job variants | multiple compiler or runtime values |
| Condition | Controls whether eligible work runs | deployment only for a main push |
| Output | Communicates selected values from a job | artifact and quality metadata |

Keeping these boundaries clear prevents several common workflow-design errors.

## Common Mistakes

### Treating jobs as sequential steps

Jobs are execution units, not simply larger versions of steps. If job ordering matters, express the dependency explicitly with `needs`.

### Assuming job workspaces persist

A file created in one job should not be assumed to exist in another. Use explicit artifacts or another appropriate transfer mechanism when data must cross job boundaries.

### Putting every operation into one job

A single job can become difficult to understand and can prevent useful parallelism. Separating independent validation jobs can make the workflow graph clearer.

### Creating unnecessary matrix combinations

Matrix expansion multiplies executions. A matrix should represent supported compatibility requirements rather than combinations with no practical value.

### Making important checks non-blocking

`continue-on-error` changes failure behavior. It should be used for intentionally non-blocking diagnostics, not to hide failures in required validation.

### Forgetting event filters

A workflow triggered by every push may run much more often than intended. Branch and event configuration should match the repository's actual automation requirements.

### Embedding untrusted data into shell commands

Event payloads can contain user-controlled values. Treating those values as shell source can introduce command-injection vulnerabilities.

### Giving workflows excessive permissions

A testing workflow normally should not receive write permissions that it does not need. Permissions should follow least privilege.

## Performance Considerations

Job-level parallelism can reduce total workflow duration when jobs do not depend on one another.

For example, linting and testing can often begin independently:

`lint`

`test`

and the build can wait for both:

`lint + test -> build`

The dependency graph therefore influences not only correctness but also potential parallel execution.

Matrices can increase throughput by running variants independently, but they also increase runner consumption and workflow duration when the platform must execute many variants.

Caching can reduce repeated dependency installation in appropriate workflows, but cache keys must correspond to the dependencies that actually determine the cached content.

Large workflows benefit from clear dependency boundaries. Excessive serialization through unnecessary `needs` declarations can remove parallelism.

## Debugging Considerations

When a workflow fails, debugging should identify the layer at which the failure occurred.

An event problem means the workflow did not trigger as intended.

A workflow-configuration problem means the workflow could not be parsed or validated.

A job problem means the runner-bound execution unit failed or was skipped.

A step problem means a particular command or action failed.

A dependency problem means a job was prevented from running because required upstream work did not succeed.

The implementations expose these distinctions through explicit statuses such as `success`, `failure`, and `skipped`.

Useful debugging information includes the event type, branch, actor, job identifier, matrix values, runner, step name, command output, and dependency status.

## Production Design Considerations

A production workflow should have a clear relationship between repository events and automation purpose.

Pull-request workflows generally focus on validation of proposed changes.

Push workflows can validate committed changes and may also perform release-related operations when their conditions and permissions allow it.

Deployment jobs should have explicit gating conditions rather than relying on accidental job order.

Critical validation should remain blocking.

Sensitive operations should receive narrowly scoped credentials and permissions.

Reusable actions and external dependencies should be managed deliberately because workflow execution is part of the repository's operational supply chain.

The workflow should also be maintainable. Job identifiers should describe the responsibility of the job, step names should make logs understandable, and dependency relationships should represent real requirements.

## Practical Architecture

A maintainable CI workflow can be viewed as several layers:

`Event configuration`

determines which repository activities can start the workflow.

`Validation jobs`

perform independent quality checks such as linting and tests.

`Build job`

depends on successful validation and creates the application artifact.

`Release or deployment job`

depends on the build and applies additional event or branch conditions.

This structure keeps event selection, execution responsibilities, and dependency rules distinct.

The implementations intentionally preserve those boundaries:

- Python emphasizes simulation and validation.
- JavaScript emphasizes asynchronous and event-driven execution.
- C++ emphasizes graph algorithms and a typed repository-governance case study.

## Limitations of the Demonstrations

These programs model GitHub Actions concepts; they are not replacements for the GitHub Actions service.

The Python workflow validator does not implement the complete GitHub Actions YAML schema.

The JavaScript action registry simulates reusable actions instead of downloading and executing real action repositories.

The C++ case study models runner and workflow behavior rather than communicating with GitHub's APIs.

The examples therefore focus on the execution relationships that are important for understanding workflow files, events, jobs, and steps while keeping the implementations self-contained.

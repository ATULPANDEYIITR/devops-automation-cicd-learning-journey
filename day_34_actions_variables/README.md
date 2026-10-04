# Actions Variables: Environment Variables, Contexts, and Expressions

## Scope

This repository studies the variable and expression model used by GitHub Actions workflows, with particular attention to three mechanisms that are easy to confuse:

- **Environment variables** provide process-level values to commands running on a job step.
- **Contexts** expose structured workflow metadata and configuration through expressions such as `${{ github.ref_name }}` and `${{ vars.SERVICE_NAME }}`.
- **Expressions** evaluate workflow decisions and interpolate values before or around step execution.

The three mechanisms interact, but they are not interchangeable. A reliable workflow design depends on understanding where a value originates, when it is evaluated, which scope can see it, and whether it becomes part of the child process environment.

## Core distinction

An environment variable is fundamentally a key-value entry supplied to a process. A shell command can consume it through shell syntax such as `$DEPLOY_ENVIRONMENT` on Unix-like runners.

A context is structured workflow data. The expression `${{ github.ref_name }}` accesses metadata about the workflow execution. `${{ vars.DEPLOY_ENVIRONMENT }}` accesses a configuration variable through the `vars` context. Context data is not automatically equivalent to a shell environment variable.

An expression is the evaluation mechanism. Expressions can compare values, select behavior, interpolate strings, and access context properties.

A useful conceptual pipeline is:

`workflow configuration → context resolution → expression evaluation → effective environment → process execution`

The exact evaluation timing depends on the workflow field and context involved, so a workflow should not be designed around the assumption that every value behaves like a shell variable.

## Environment variables

The Python implementation models environment scopes with `VariableScopes`. It keeps workflow-level, job-level, and step-level mappings separate before constructing an effective process environment.

The modeled precedence is:

`runner environment < workflow environment < job environment < step environment`

This makes an override visible rather than hiding it in a single dictionary. For example, a workflow can define `LOG_LEVEL=info`, a job can redefine it as `debug`, and a particular step can redefine it as `trace`. The effective value seen by that step is `trace`.

The JavaScript implementation provides the same conceptual separation through the `EnvironmentScopes` class. Its `effectiveEnvironment()` method merges the layers from broadest to most specific.

The C++ case study makes the same decision explicit in `VariableScopes::effectiveEnvironment()`. This is useful in systems where configuration precedence must be auditable because a deployment decision can depend on the final value rather than merely on the location where a variable was originally declared.

Environment variables are especially useful for process configuration:

- command behavior such as `LOG_LEVEL`,
- service ports,
- deployment regions,
- runtime modes,
- flags passed to a program,
- configuration values that a child process must read.

They are less suitable as a substitute for structured workflow metadata. Repository names, branch names, event types, matrix values, step outputs, and job results belong naturally to contexts.

## Configuration variables and the `vars` context

The `vars` context represents configuration variables that can be defined at supported repository, organization, or environment scopes.

The implementations intentionally keep configuration variables separate from ordinary environment mappings.

For example:

`${{ vars.SERVICE_NAME }}`

means that the workflow expression system is looking up the configuration variable named `SERVICE_NAME`.

It does not mean that a shell process automatically has an environment variable called `SERVICE_NAME`.

If a command needs a process environment variable, a workflow can map the configuration value into an appropriate `env` entry. The conceptual relationship is:

`vars.SERVICE_NAME → expression resolution → env.SERVICE_NAME → child process`

This distinction prevents a common debugging error in which a value is visible through one context but expected to exist in the shell environment without an explicit mapping.

## GitHub context

The Python simulator models GitHub metadata through a dictionary containing values such as:

- repository,
- ref,
- ref name,
- event name,
- commit SHA,
- actor.

The JavaScript implementation stores equivalent information in its `github` object.

The C++ implementation uses the strongly typed `GithubContext` structure.

These values describe the workflow execution rather than the environment of the application being executed.

For example:

`${{ github.ref_name }}`

can identify the branch associated with the workflow execution.

A deployment condition can therefore distinguish a push to `main` from a push to a feature branch without requiring the shell to discover the branch independently.

The case studies use conditions such as:

`${{ github.ref_name == 'main' }}`

and:

`${{ startsWith(github.ref, 'refs/heads/') }}`

to show that repository metadata can participate directly in workflow decisions.

## Expression evaluation

The Python implementation contains a deliberately restricted expression evaluator rather than executing arbitrary Python code. It supports context lookup, literals, comparisons, boolean operators, and selected functions.

Supported functions include:

`startsWith()`

`endsWith()`

`contains()`

`format()`

`success()`

`failure()`

`cancelled()`

`always()`

The JavaScript implementation follows a similar design but uses JavaScript-specific string and object mechanisms.

The C++ implementation uses explicit parsing and strongly typed structures. It does not invoke an interpreter or execute arbitrary code from an expression. This is important for a governance component because workflow expressions should not become an accidental command-execution interface.

An expression such as:

`${{ github.ref_name == 'main' && vars.DEPLOY_ENVIRONMENT == 'production' }}`

can be interpreted as a policy:

- the workflow must be associated with `main`;
- the configured deployment environment must be `production`;
- only when both conditions are true should the deployment path be permitted.

The expression makes the decision. The command that performs deployment remains a separate operation.

## Expression evaluation and shell expansion are different stages

One of the most important distinctions demonstrated by the implementations is the difference between Actions expressions and shell expansion.

Consider a command conceptually containing:

`${{ vars.SERVICE }}`

and:

`$SERVICE`

The first is an Actions expression. It is resolved by the workflow expression mechanism.

The second is shell syntax. It is interpreted by the shell running the command and depends on the process environment.

The Python implementation explicitly demonstrates this boundary by resolving `${{ ... }}` before executing a local command while separately constructing the environment supplied to the process.

The JavaScript implementation demonstrates the same boundary with `execFileSync()`. The workflow model resolves Actions expressions first and then starts a child shell with the resulting environment.

This distinction is particularly important when debugging a step that prints an unexpected empty value. The correct question is whether the value failed to enter the Actions context, failed to be mapped into `env`, or failed during shell expansion.

## Matrix context

The `matrix` context represents the dimensions of a matrix job.

The Python implementation evaluates combinations such as:

`python=3.11, database=postgres`

`python=3.12, database=postgres`

`python=3.13, database=sqlite`

The JavaScript implementation uses Node.js objects to process equivalent combinations.

The C++ implementation uses `MatrixContext`, whose `values` map represents the current matrix combination.

A matrix value is fundamentally different from a static environment variable because the workflow can create multiple job instances from the matrix definition. Each instance receives its own matrix context.

A useful expression is:

`${{ matrix.database }}`

while an environment variable would instead be something such as:

`DATABASE=postgres`

The former identifies workflow expansion data. The latter supplies a process configuration value.

## Step outputs

Step outputs provide a controlled data path from one step to a later step.

The Python implementation represents a step with `StepResult` and stores output values such as:

`version=2026.10.04`

`artifact=platform-2026.10.04`

A later expression can access:

`${{ steps.metadata.outputs.version }}`

The JavaScript implementation uses a `Map` of step objects and exposes output data through the `steps` context.

The C++ case study stores output values inside `StepState::outputs`.

This mechanism is preferable to relying on an incidental shell environment when a value is logically produced by one workflow step and consumed by another. It gives the value a clear producer and consumer relationship.

The lifecycle is conceptually:

`build step → output creation → steps context → downstream expression`

The output is associated with the step identifier, not with a generic process-wide environment.

## Job outputs and the `needs` context

Data that must cross a job boundary is modeled through job outputs and the `needs` context.

The Python implementation creates a `needs` structure containing a completed `build` job with:

`result=success`

`image=registry.example.com/payment-api:2026.10.04`

`version=2026.10.04`

A dependent job can evaluate:

`${{ needs.build.result }}`

or:

`${{ needs.build.outputs.image }}`

The JavaScript workflow model stores completed jobs and constructs the corresponding `needs` context.

The C++ implementation uses `JobState` and `NeedsContext` to represent the same dependency relationship.

This distinction matters because a job does not simply inherit the previous job's shell environment. Job-to-job communication must use an explicit workflow data path.

## Conditional execution

Expressions are particularly valuable when deciding whether a step should run.

The JavaScript implementation contains an event-driven example in which a step is enabled only when:

`github.event_name == 'pull_request'`

The Python implementation demonstrates conditions based on branch and deployment configuration.

The C++ governance engine evaluates a deployment policy:

`github.ref_name == 'main' && vars.DEPLOY_ENVIRONMENT == 'production'`

This separates policy evaluation from process execution.

A robust workflow should make the condition explicit rather than hiding deployment rules inside a shell script. The workflow configuration then documents the circumstances under which the deployment operation is allowed to execute.

## Failure handling

Several classes of failure are demonstrated.

### Missing context values

The implementations deliberately attempt lookups such as:

`${{ vars.MISSING }}`

and:

`${{ github.unknown }}`

A production workflow should treat missing required values as configuration errors rather than silently substituting an unrelated value.

### Invalid expressions

Unsupported function names and incorrect argument counts are rejected by the local expression engines.

This demonstrates a useful design principle: configuration expressions should fail clearly when their syntax or semantics are invalid.

### Incorrect variable assumptions

A variable may exist in `vars` but not in `env`. A context value may exist but not be appropriate for the current workflow field. A shell variable may be absent even though the corresponding expression resolved successfully.

These are different failure modes and should be diagnosed separately.

## Validation

The Python implementation validates environment variable names against a restricted uppercase convention and checks for NUL and line-break characters.

The JavaScript implementation performs equivalent validation using a regular expression and string checks.

The C++ implementation uses `std::regex` and explicit character checks.

The validation is deliberately stricter than what every environment implementation necessarily requires. Its purpose is to demonstrate a production-oriented configuration boundary where variable names and values are validated before being used by a workflow execution system.

Validation is especially useful when variables originate outside a tightly controlled workflow file, such as repository configuration, external automation, generated configuration, or administrative input.

## Security considerations

Environment variables are not automatically secret.

A value should not be treated as sensitive merely because it is stored in an environment variable. Conversely, placing a secret in `env` does not make unsafe logging acceptable.

Sensitive values should not be exposed through:

- command-line arguments,
- shell tracing,
- generated artifacts,
- diagnostic output,
- cache keys,
- URLs,
- build logs,
- untrusted pull request output.

The Python implementation includes `mask_sensitive_values()`. The JavaScript implementation demonstrates replacement of known secret values before logging. The C++ implementation provides `maskSecrets()`.

These functions are simplified educational models. They are not replacements for the runner's own secret-handling and log-masking mechanisms.

A particularly important security boundary occurs when workflow expressions contain attacker-controlled data. Pull request titles, branch names, commit messages, issue content, and other event data should not be inserted into shell commands without appropriate handling.

The safest design is to keep data and executable syntax separate. When a value needs to reach a command, pass it as an environment value or another structured input rather than constructing executable shell syntax from untrusted text.

## Context availability and timing

Not every context is available in every workflow field.

A workflow author should distinguish:

- data available when a workflow is planned,
- data available while a job is evaluated,
- data created by an earlier step,
- data created by a completed job,
- values supplied to the child process.

This explains why contexts such as `matrix`, `steps`, and `needs` have different roles.

`matrix` describes the current matrix expansion.

`steps` exposes information produced by earlier steps in the same job.

`needs` exposes results and outputs from prerequisite jobs.

`github` describes workflow-event metadata.

`vars` supplies configuration values.

`env` represents the environment available through the workflow's environment mappings.

These contexts should be selected based on the relationship represented by the value rather than convenience.

## Python implementation

The Python program is an executable teaching model centered on a reusable `ActionsSimulator`.

Its `VariableScopes` class separates workflow, job, step, configuration, and runner values.

Its expression engine provides safe evaluation of a focused subset of Actions-style expressions without using Python's `eval()`. This is an intentional design decision because arbitrary expression evaluation would turn configuration text into executable host-language code.

The Python program demonstrates:

- context lookup,
- environment precedence,
- expression interpolation,
- boolean conditions,
- matrix values,
- step outputs,
- job dependency data,
- validation,
- shell expansion boundaries,
- security-sensitive logging,
- missing-context failures,
- a complete release workflow simulation.

The release simulation builds an artifact, stores output metadata, evaluates a production deployment condition, and supplies the artifact to a deployment step through an explicit environment mapping.

## JavaScript implementation

The JavaScript file provides a complementary event-driven model.

`EnvironmentScopes` represents layered process configuration.

`ActionsWorkflow` manages:

- workflow metadata,
- configuration variables,
- environment scopes,
- steps,
- step outputs,
- completed jobs,
- job outputs,
- event listeners.

The event mechanism is intentionally relevant to Node.js. A completed step emits a `step.completed` event, and a skipped step emits `step.skipped`. This models the event-oriented style common in JavaScript applications without pretending that Node.js events are themselves part of GitHub Actions semantics.

The program also uses `execFileSync()` to show a meaningful process boundary. Actions expressions are resolved by the workflow model, and the resulting environment is supplied to a child shell.

The JavaScript expression evaluator demonstrates context lookup, comparisons, boolean operations, string functions, matrix data, step outputs, job outputs, validation, and security-oriented log handling.

## C++ governance case study

The C++ program presents the topic as a release-governance engine for a hypothetical payments API.

The system separates:

- `GithubContext` for repository and event metadata,
- `RunnerContext` for runner characteristics,
- `MatrixContext` for matrix dimensions,
- `StepState` for step results and outputs,
- `JobState` for job results and outputs,
- `NeedsContext` for job dependencies,
- `VariableScopes` for environment and configuration layers,
- `ContextStore` for expression-accessible state,
- `GovernanceEngine` for policy resolution.

The architecture is deliberately different from the Python and JavaScript implementations. It uses C++ structures and explicit ownership of state rather than reproducing the other programs' object models.

The final release scenario uses a build step output as the artifact identifier and evaluates a deployment policy against the GitHub branch and configured deployment environment.

The resulting decision is separate from execution:

`policy evaluation → permitted or blocked → deployment operation`

This separation is useful for real CI/CD governance because policy logic can be inspected independently from the command that performs the deployment.

## Practical workflow architecture

A maintainable Actions configuration can treat values according to their role.

**Repository or deployment configuration**

Use configuration variables for values such as a service identifier, deployment tier, or registry location when the value is workflow configuration rather than a transient process setting.

**Process configuration**

Use environment variables for values that a command or application actually needs in its execution environment.

**Workflow metadata**

Use contexts such as `github` for repository, event, branch, actor, and commit information.

**Parallel test dimensions**

Use `matrix` for values that define independent job combinations.

**Step-to-step communication**

Use step outputs when a step produces structured information that later steps must consume.

**Job-to-job communication**

Use job outputs through `needs` when a dependent job needs a value produced by another job.

This classification makes workflow data flow explicit.

## Common mistakes

### Assuming `vars` automatically becomes `env`

A configuration variable accessed as `${{ vars.SERVICE_NAME }}` does not mean that `$SERVICE_NAME` is automatically available to a shell process. If the process needs an environment variable, the workflow should explicitly provide the appropriate environment mapping.

### Treating every value as a string

Expressions can produce booleans and other scalar values. Converting everything to text too early can make conditions ambiguous.

The Python and JavaScript models preserve scalar results when an expression occupies an entire value.

### Confusing `steps` with `needs`

`steps` describes step-level state within a job.

`needs` describes completed prerequisite jobs.

A value generated by a previous job is not conceptually a step-local value in the dependent job.

### Embedding untrusted values into shell syntax

A branch name or event-derived value should not be treated as trusted executable syntax merely because it came from a GitHub context.

Keep data in variables and pass it to commands as data whenever possible.

### Hiding policy inside scripts

If a production deployment is permitted only on `main`, making that rule visible as an expression is easier to inspect than burying it in a shell script.

### Assuming the runner environment is identical everywhere

Runner operating systems, available commands, path conventions, shells, and preinstalled software can differ. The C++ model therefore keeps runner characteristics separate from workflow configuration.

## Debugging model

When a variable has an unexpected value, inspect the data path rather than immediately changing the command.

Determine:

`source → context → expression → environment mapping → shell/process`

For a configuration value, verify the `vars` lookup.

For repository metadata, inspect the relevant `github` property.

For a matrix value, inspect `matrix`.

For a step-produced value, inspect `steps.<id>.outputs`.

For a job-produced value, inspect `needs.<job>.outputs`.

For a shell value, inspect the final `env` mapping supplied to the process.

This model prevents a common debugging failure where a problem in one layer is incorrectly fixed in another.

## Performance considerations

Expression evaluation is normally small compared with compilation, testing, packaging, and deployment work. The important performance issue is not raw expression cost but unnecessary data processing and process creation.

The examples keep expression evaluation in memory and avoid external dependencies.

For a larger workflow-management system, expression parsing could be tokenized once and cached rather than reparsed repeatedly. Context data can also be represented using immutable snapshots when multiple evaluation operations must observe the same workflow state.

Matrix expansion can produce many job combinations. The operational cost therefore comes primarily from the number of generated jobs and their workload, not from looking up a matrix property such as `matrix.database`.

## Design relationships

The central relationship among the three concepts is:

`context data → expression evaluation → environment/process execution`

A context gives an expression access to structured workflow information.

An expression can transform or compare that information.

An environment mapping can expose a resolved value to a child process.

The process then executes independently of the expression engine.

This separation is important because a shell command should not need to understand the internal structure of `github`, `matrix`, `steps`, or `needs`. The workflow layer resolves those concepts before or around process execution and supplies the process with the concrete configuration it requires.

## Limitations of the implementations

The three programs are educational models, not replacements for the GitHub Actions runner.

They intentionally do not implement the complete Actions expression grammar, every available context, every workflow field, every shell behavior, every runner command, or every platform-specific rule.

The expression evaluators cover a focused subset needed to demonstrate the relationships among environment variables, contexts, and expressions.

The local command execution examples also cannot reproduce every behavior of hosted or self-hosted runners.

The value of the implementations is the explicit modeling of scope, data flow, evaluation, precedence, dependency outputs, validation, and security boundaries.

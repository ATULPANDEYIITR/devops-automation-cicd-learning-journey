# GitHub Actions Reusable Workflows and Composite Actions

## Technical scope

GitHub Actions supports two complementary mechanisms for reducing duplication in repository automation: reusable workflows and composite actions. Both allow teams to centralize automation logic, but they operate at different levels of the execution model.

A reusable workflow is a workflow that another workflow invokes as a job. It can define multiple jobs, dependencies, runner selection, permissions, environments, and workflow-level outputs. Its public interface is normally declared through the `workflow_call` event.

A composite action packages a sequence of steps into a single action. A caller invokes it from a job's `steps` list. The composite action can validate inputs, run commands, call other actions, and expose outputs to later steps. It does not independently create a workflow-level job graph.

This repository models both mechanisms using executable Python, JavaScript, C++, Java, and PostgreSQL implementations. The programs simulate contracts, dependency execution, output propagation, deployment checks, and failure handling without requiring a GitHub repository or performing a real deployment.

## The execution model

The distinction between the two reuse mechanisms determines where responsibilities belong.

| Property | Reusable workflow | Composite action |
| --- | --- | --- |
| Invocation location | A job's `uses` property | A step's `uses` property |
| Main purpose | Reuse an automation workflow or job sequence | Reuse a sequence of steps |
| Job graph | Can define multiple jobs and `needs` dependencies | Executes inside the caller's job |
| Runner selection | Defined by jobs in the reusable workflow | Inherits the execution context of its calling job |
| Interface | `on.workflow_call.inputs`, secrets, and outputs | `inputs`, action steps, and declared outputs |
| Workflow-level permissions | Defined for the workflow and its jobs within applicable permission limits | Does not establish a separate workflow-level permission boundary |
| Typical use | Shared CI pipelines, release orchestration, deployment workflows | Packaging, metadata generation, validation, deployment commands |
| Failure propagation | Job and workflow results reflect job failures and dependencies | A failed action step normally fails the containing job unless configured otherwise |

These mechanisms can be composed. An application workflow can invoke a reusable release workflow, which runs validation and release jobs. A release job can invoke a composite action that prepares artifact metadata and validates deployment inputs.

The reusable workflow owns the job-level process. The composite action owns a repeatable sequence of steps within one job.

## Repository layout and callable interfaces

A reusable workflow normally resides under `.github/workflows/` and must declare `workflow_call` to be callable by another workflow.

A representative workflow interface is:

    name: Shared Release

    on:
      workflow_call:
        inputs:
          release-version:
            description: Semantic release version
            required: true
            type: string
          target-environment:
            description: Deployment destination
            required: false
            default: staging
            type: string
        secrets:
          DEPLOY_TOKEN:
            required: true
        outputs:
          artifact-name:
            description: Prepared artifact
            value: ${{ jobs.release.outputs.artifact-name }}

The corresponding caller invokes the workflow at job level:

    jobs:
      release:
        uses: acme/shared-automation/.github/workflows/release.yml@v2.1.0
        with:
          release-version: 3.2.0
          target-environment: staging
        secrets:
          DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}

The called workflow must expose any job output through the workflow's declared outputs. Outputs are not automatically available merely because a step produced a value.

A composite action normally resides in a directory containing `action.yml`. Its metadata identifies the action as composite and defines its inputs and steps.

    name: Deploy Service
    description: Validate release metadata and prepare deployment

    inputs:
      release-version:
        description: Semantic release version
        required: true
      target-environment:
        description: Deployment destination
        required: true

    outputs:
      artifact-name:
        description: Prepared artifact
        value: ${{ steps.package.outputs.artifact-name }}

    runs:
      using: composite
      steps:
        - name: Validate release metadata
          shell: bash
          env:
            RELEASE_VERSION: ${{ inputs.release-version }}
          run: |
            [[ "$RELEASE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]

        - name: Prepare artifact metadata
          id: package
          shell: bash
          env:
            RELEASE_VERSION: ${{ inputs.release-version }}
          run: |
            printf 'artifact-name=service-%s.tar\n' "$RELEASE_VERSION" \
              >> "$GITHUB_OUTPUT"

The action declares the output in its metadata and maps it to a step output. A caller can then read the action output in a later step using the action step's identifier.

These examples illustrate the interfaces rather than a complete deployment configuration. A production implementation must also define the actual packaging and deployment operations, permissions, environment controls, and required validation.

## Workflow inputs, secrets, and outputs

### Inputs

Inputs form a contract between a caller and a reusable component. A workflow can declare string, Boolean, and numeric inputs. Composite action metadata supports input declarations and defaults, but values received through action inputs must be validated when they influence commands or deployment decisions.

The Python `InputSpec` and JavaScript `InputContract` implementations resolve supplied values against declared inputs. They reject unknown input names, missing required values, and values outside an explicitly permitted set.

The C++ and Java implementations apply similar validation before action execution. These checks illustrate an important contract-design principle: callers should not be able to silently change behavior by supplying misspelled or unsupported parameters.

Defaults must be deliberate. A staging default can be appropriate for a release target, while a missing release version should prevent execution. Required inputs and defaults should be defined consistently with the intended GitHub Actions interface.

### Secrets

Reusable workflows can receive explicitly declared secrets or receive secrets through `secrets: inherit` when the caller and called workflow satisfy the applicable repository and organization access rules. Explicit secret mapping makes the intended credential interface easier to audit.

A composite action can access secrets that its calling workflow deliberately exposes through the action's inputs or environment. Secret access should be restricted to the steps that require it.

The sample implementations keep credentials in separate execution-context structures, validate their presence, and avoid printing secret values. Their credentials are demonstration values, not usable deployment credentials.

Log redaction is a defensive measure, not a complete secret-protection mechanism. Production code should avoid placing credentials in command-line arguments, output files, exception messages, artifact metadata, or untrusted expressions. GitHub's secret masking should not be treated as a substitute for minimizing exposure.

### Outputs

Action outputs and workflow outputs belong to different interfaces.

A composite action obtains a step output through mechanisms such as `$GITHUB_OUTPUT` and exposes it through `action.yml`. A reusable workflow maps job outputs to the workflow-level outputs declared under `workflow_call`.

A caller can consume an action output in a subsequent step or a reusable-workflow output in a dependent job. The distinction matters when designing shared release interfaces: the action may produce an artifact identifier, while the workflow may expose that identifier after its release job completes.

## Python implementation

The Python program implements a local execution engine rather than parsing or running GitHub Actions YAML.

`WorkflowContract` defines the reusable workflow's public inputs and required secrets. Its validation process rejects undeclared inputs and missing credentials before jobs execute.

`CompositeAction` represents step-level reuse. It resolves its own input contract, executes its steps in sequence, collects action outputs, and raises an execution error when a required output is absent.

`ReusableWorkflow` represents job-level reuse. Each `Job` has a name, dependencies, an execution status, and an error field. The workflow validates dependency references and detects cycles before execution.

The scheduler repeatedly selects jobs whose dependencies have succeeded. When a dependency fails or is skipped, dependent jobs are skipped. A stalled scheduler raises an error rather than waiting indefinitely.

The demonstration uses a release workflow containing test, release, and audit jobs. The release job invokes a composite action that validates the commit identifier, checks the release version, and evaluates deployment authorization. The audit job requires artifact metadata from the release job.

The `unittest` suite checks successful staging execution, blocked production deployment, invalid versions, unknown inputs, missing secrets, invalid revisions, cyclic dependencies, and secret leakage into logs. Execute the program with `python actions_reuse.py --test` to run the tests.

The manifest validator checks selected structural rules, including workflow-call input definitions and invalid combinations of reusable workflow invocation properties. It is intentionally not a complete YAML parser or a replacement for GitHub's workflow validation.

## JavaScript implementation

The JavaScript program emphasizes asynchronous execution, event-driven observability, and explicit state transitions.

`EventBus` publishes job success and failure events to registered listeners. This separates workflow execution from monitoring code that records outcomes.

`ReusableWorkflow` schedules jobs according to their dependencies. It tracks pending, running, succeeded, failed, and cancelled states. A dependent job is cancelled when its prerequisite fails. The distinction between failure and cancellation helps the execution report identify the original failure and its downstream consequences.

`CompositeAction.execute()` processes an action's steps sequentially with `await`. It maintains a local output object and returns the outputs to the calling job after all mandatory steps complete. An optional step can be marked `continueOnError`, but mandatory release validation does not use that behavior.

The release workflow computes a deterministic audit reference from artifact metadata using SHA-256. This is a demonstration of event correlation, not a signature or proof of artifact authenticity.

The input contract rejects unknown keys, checks required values, and constrains the deployment destination to staging or production. The program asserts that a staging release succeeds and that a production release without the required approval signal fails before the audit job runs.

A significant JavaScript design consideration is that asynchronous operations must be awaited. Failure to await an action can allow a job to report success before the action finishes. Production workflow orchestration should also distinguish cancellation initiated by a user from cancellation caused by failed dependencies.

## C++ case study

The C++ program models a repository automation engine used by an organization that centralizes release procedures for multiple services.

`InputDefinition` describes the callable input contract. `InputValidator` checks unknown inputs, required values, and allowed deployment targets before the composite action executes.

`ExecutionContext` contains workflow inputs, secrets, environment values, outputs, and diagnostic messages. Its logging method redacts configured secret values. It does not attempt to guarantee that arbitrary command output or transformed credentials can never leak.

`CompositeAction` receives a collection of `CompositeStep` functions. The deployment sequence validates the source revision, checks the semantic release version, constructs artifact metadata, and authorizes the deployment destination.

`WorkflowEngine` stores job definitions and their dependency relationships. Its graph validation rejects missing dependencies and cyclic execution graphs. During execution, the scheduler starts jobs only when all dependencies have succeeded.

The case study contains test, release, and audit jobs. The audit operation depends on the release artifact output. When production authorization fails, the release job is marked failed and the audit job is skipped.

The implementation uses maps for named inputs and outputs, sets for dependency scheduling, vectors for ordered steps and logs, and function pointers for job operations. These structures provide a clear separation between the workflow graph and the operations executed by each job.

The implementation demonstrates in-memory orchestration, not the complete GitHub Actions runtime. It does not interpret expressions, parse YAML, allocate runners, create artifacts, or contact external deployment services.

## Java enterprise model

The Java program organizes automation around explicit domain types and immutable interface definitions.

`InputDefinition` and `InputContract` represent declared workflow and action inputs. Contract construction rejects duplicate definitions, and invocation rejects undeclared parameters.

`ExecutionContext` keeps inputs, secrets, environment values, outputs, and logs separate. It exposes named access methods that fail explicitly when a required value is missing. This prevents accidental use of absent values as valid deployment configuration.

`CompositeAction` executes named steps and verifies that all declared outputs were produced. The implementation returns action outputs to the reusable workflow's execution context so the audit job can consume release metadata.

`JobDefinition` expresses the dependency graph. `ReusableWorkflow` validates job names, dependency references, and cycles before accepting an invocation. During execution, it records each job's state and associates failures with the job that produced them.

The deployment action validates the revision format, enforces a numeric semantic-version pattern, checks the deployment destination, and creates a SHA-256 audit reference. The release workflow cannot reach a successful audit state when the release job fails.

The Java model illustrates a service-oriented design in which interface validation, execution context, action behavior, scheduling, and reporting have separate responsibilities. Its records, collections, enums, and exception types make domain contracts more explicit than an implementation based entirely on loosely structured maps.

The model is deliberately self-contained. A production implementation would need stronger secret isolation, durable execution records, concurrency control, cancellation handling, permission enforcement, and integration with GitHub's actual workflow runtime.

## PostgreSQL data model

The SQL script records workflow definitions, composite actions, interfaces, invocations, job dependencies, and execution results in relational tables.

| Table | Responsibility |
| --- | --- |
| `repositories` | Identifies the repositories that own reusable automation and call it |
| `workflow_definitions` | Stores caller and reusable workflow metadata, version references, and immutable revisions |
| `composite_actions` | Stores step-level action definitions and their version references |
| `workflow_inputs` | Declares callable workflow input names, types, defaults, and required status |
| `action_inputs` | Declares the inputs accepted by composite actions |
| `workflow_outputs` and `action_outputs` | Describe the outputs exposed by each reuse interface |
| `workflow_jobs` | Represents jobs and distinguishes ordinary jobs from reusable workflow calls |
| `job_dependencies` | Records the `needs` relationship between jobs |
| `workflow_action_calls` | Connects a job's action invocation to a reusable composite action |
| `workflow_invocations` | Records which caller invoked which reusable workflow and the execution result |
| `invocation_input_values` | Records the non-secret input values supplied to an invocation |
| `invocation_secret_grants` | Records secret grant names and grant modes without storing secret values |
| `job_executions` | Stores per-invocation job states and failure details |
| `execution_outputs` | Records named outputs produced by a job execution |
| `workflow_status_checks` | Stores the results of individual automation checks |

Foreign keys maintain referential integrity between repositories, workflows, actions, jobs, and invocations. Unique constraints prevent duplicate input definitions, output definitions, job names within a workflow, and action-call names within a job.

The `job_dependencies` trigger verifies that both jobs belong to the same workflow. This is a database-level rule because a job dependency must not cross unrelated workflow definitions. The trigger does not detect every possible dependency cycle; a complete cycle check belongs in the workflow validation layer or a dedicated database routine.

Indexes support common queries over workflow jobs, dependency edges, invocation states, job execution states, and status-check conclusions. They are not substitutes for execution scheduling or workflow validation.

The sample inserts demonstrate a shared release workflow, an application caller, a composite deployment action, workflow inputs, action outputs, and representative successful and failed invocations.

The reporting queries inspect immutable workflow references, input contracts, the relationship between workflow jobs and composite actions, job dependency edges, invocation outcomes, and aggregate success rates.

The SQL model intentionally does not store secret values. It records secret grants by name and mode. In a production system, actual credentials should remain in a dedicated secrets-management mechanism.

The database is an operational model of automation metadata. It is not a GitHub Actions server and does not execute YAML, expressions, shell commands, or jobs on runners.

## Versioning and security

Reusable workflows and composite actions are executable dependencies. A caller that references a moving branch can receive different automation behavior without changing its own workflow file.

A version tag improves readability and release management, but a tag can be moved by an authorized repository maintainer. A full commit SHA provides an immutable reference to the selected revision. The examples record both a human-readable reference and an optional full revision so a governance process can audit how dependencies are pinned.

Input validation must occur at the point where values influence execution. A release version should match the expected format, and a deployment target should be restricted to approved values. Shell commands should use carefully quoted arguments and explicit environment variables instead of interpolating untrusted strings directly into command text.

Secrets should be passed only to the components that need them. The `secrets: inherit` option is convenient when appropriate, but it broadens the credential interface compared with explicit mappings. Permissions should follow least privilege, particularly when shared workflows can access deployment environments or repository write permissions.

A shared workflow can centralize security controls, but centralization alone does not establish a security boundary. The caller, reusable workflow, composite action, runner, token permissions, environment approvals, and referenced dependencies must all be evaluated.

## Common implementation failures

### Calling a workflow at the wrong level

A reusable workflow is referenced in a job's `uses` property. A composite action is referenced in a step's `uses` property. A reusable workflow call job does not define its own `runs-on` or a normal `steps` list; runner selection and steps belong to jobs inside the called workflow.

### Confusing action outputs with workflow outputs

A value written to `$GITHUB_OUTPUT` belongs to a step. The action must expose the value through its output mapping before a caller can consume it. Workflow outputs require an additional mapping from a job output to the reusable workflow's declared output.

### Omitting shell declarations

Composite action `run` steps should explicitly declare `shell`. A workflow that executes successfully on a local machine can still fail in GitHub Actions if its shell assumptions, runner environment, or command dependencies differ.

### Depending on undeclared inputs or secrets

A called workflow should declare the inputs and secrets it expects. A composite action should declare its own inputs. Passing a value to a caller does not automatically make that value available through every nested interface.

### Allowing dependent jobs to run after a failed prerequisite

A job that consumes an artifact must not proceed as though the artifact exists when the release job fails. The `needs` graph and the workflow's failure-handling rules must agree about which jobs can run after a failure.

### Treating validation as deployment authorization

A valid version string, a valid commit identifier, and a present credential do not independently authorize a production deployment. Real deployment authorization can also depend on protected environments, required reviewers, token permissions, repository policies, and the deployment service itself.

## Performance and operational considerations

Reusable workflows reduce duplicated configuration but introduce dependency and interface management. Changes to a shared workflow can affect many caller repositories, so interface changes should be versioned and tested against representative callers.

Composite actions reduce repeated step definitions and help standardize packaging, validation, and command execution. They do not eliminate the cost of the commands they invoke, nor do they provide separate job-level parallelism.

Job dependencies constrain concurrency. Independent jobs can run concurrently in GitHub Actions when their dependencies and runner capacity permit. Jobs with explicit `needs` relationships must wait for their prerequisites. The Python, JavaScript, C++, and Java simulators execute their schedulable jobs sequentially, so their runtime behavior is not a performance benchmark for GitHub's distributed runners.

The SQL reporting indexes target common administrative queries. As invocation history grows, operational systems may require retention policies, partitioning, archival, and carefully designed aggregate reporting. The schema records execution metadata rather than full runner logs or artifact contents.

## Scope and limitations

The programs implement educational workflow models rather than complete interpreters for GitHub Actions. They do not reproduce every GitHub expression, event filter, matrix expansion, runner command, environment protection rule, cancellation condition, concurrency group, artifact transfer mechanism, or permission calculation.

The manifest validator checks selected structural invariants but does not validate arbitrary YAML or guarantee that a workflow is accepted by GitHub. The execution simulators use simplified dependency scheduling and explicit approval signals. Their local policy checks are not equivalent to GitHub environment protection or organizational access controls.

The PostgreSQL schema enforces selected metadata and referential-integrity rules. It does not enforce every GitHub Actions interface rule, prove that workflow outputs map to valid job outputs, execute dependency graphs, or guarantee that a referenced external action is safe.

These distinctions are important when transferring the models to production: reusable workflows define job-level reuse, composite actions define step-level reuse, and the real GitHub Actions runtime remains responsible for interpreting and executing the workflow configuration.

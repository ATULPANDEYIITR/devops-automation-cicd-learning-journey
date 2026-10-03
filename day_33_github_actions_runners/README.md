# GitHub Actions Runners: Hosted Runners, Self-Hosted Runners, and Runner Architecture

## Topic Scope

GitHub Actions runners are the execution layer behind GitHub Actions workflows. A workflow defines jobs and steps, but those steps need a machine or execution environment on which they can run. A runner provides that execution environment.

The three central areas covered by the accompanying implementations are:

- **Hosted runners**: execution environments managed by GitHub, including their image-oriented and typically ephemeral execution model.
- **Self-hosted runners**: execution agents operated by an organization or repository owner, where infrastructure, operating-system maintenance, networking, software, credentials, and lifecycle become operational responsibilities.
- **Runner architecture**: the relationship among workflow jobs, scheduling constraints, runner labels, operating-system and CPU architecture, installed tools, runner state, queues, execution, reporting, capacity, and security boundaries.

These concepts are related but are not interchangeable. A hosted runner describes who operates the execution infrastructure. A self-hosted runner describes an organization-managed execution model. Runner architecture describes how workloads are matched to and executed by available agents.

## Core Architecture

A simplified execution path is:

`Workflow -> Job -> Scheduling constraints -> Eligible runner -> Job execution -> Logs/results -> Completion`

The workflow is the declarative source of the automation. Its jobs contain execution requirements. The scheduling layer determines which available runner satisfies those requirements. The selected runner obtains and executes the workload, then reports the execution result.

A runner therefore has two important identities:

- It is an **execution agent** capable of running operating-system processes.
- It is a **scheduling target** described by properties such as labels, operating system, architecture, and available software.

The distinction matters because a workflow does not merely need "a machine." It needs a machine with the required capabilities and an acceptable trust boundary.

## Hosted Runners

GitHub-hosted runners provide managed execution environments. The infrastructure lifecycle is handled by GitHub rather than by the repository owner.

A hosted runner is particularly useful when a workflow needs conventional operating-system environments without requiring the organization to maintain physical or virtual machines.

The Python implementation models a hosted runner with a `RunnerKind.HOSTED` classification and an image containing tools such as Git, Python, Node.js, and Docker. Its `RunnerImage.ephemeral` value represents the intended temporary nature of the environment.

The JavaScript implementation models a hosted runner as `hosted-linux-x64`. It has labels for Linux, x64, and Docker and declares an ephemeral execution environment. The scheduler can therefore route ordinary Linux workloads to it without giving the workflow access to an organization-specific internal runner.

The C++ case study represents the same architectural distinction with `RunnerKind::Hosted` and an `ubuntu-latest` image. The program uses this distinction to explain responsibility rather than merely treating hosted and self-hosted machines as different names.

Hosted execution reduces infrastructure-management work, but workflow security still matters. Secrets, permissions, artifacts, dependencies, and commands executed by the workflow remain security-sensitive.

## Self-Hosted Runners

A self-hosted runner is infrastructure controlled by the organization or repository owner. The runner machine, virtual machine, container environment, network placement, installed software, patch level, service account, and lifecycle require deliberate management.

The Python model uses an `internal-builder-01` runner with an `internal` label and an `internal-sdk` tool. This represents a common reason to use specialized infrastructure: a workflow may require software or network access that is specific to an organization's environment.

The JavaScript model separates an `internal-sdk` runner from the general hosted Linux runner. This makes routing capability-specific rather than simply selecting the first available machine.

The C++ case study uses `internal-linux-builder` as a trusted self-hosted runner. The job requesting `internal-sdk` is routed to this runner because the runner advertises both the relevant labels and the required tool.

Self-hosted infrastructure introduces operational responsibilities that do not disappear because the machine is called a runner. Important responsibilities include:

- operating-system patching
- runner software maintenance
- service-account permissions
- network segmentation
- credential handling
- workspace cleanup
- disk and CPU capacity
- monitoring and availability
- hardware lifecycle
- isolation between workloads

A self-hosted runner that can access sensitive internal systems should be treated as part of that security boundary.

## Runner Labels and Routing

Labels provide a capability-oriented way to select runners.

Examples represented by the implementations include:

`linux`, `windows`, `x64`, `arm64`, `docker`, `gpu`, `internal`, and `self-hosted`.

A job can require a set of labels. The scheduler checks whether the runner's label set contains the complete required set.

For example, a job requiring:

`self-hosted + linux + x64 + gpu`

cannot be routed to a runner that has only:

`self-hosted + linux + x64`

even if that runner is otherwise idle.

The Python `Runner.can_run()` method performs this subset check and separately verifies required tools.

The JavaScript `Runner.supports()` method applies the same idea using JavaScript `Set` objects. Its routing model returns diagnostics explaining why a runner was rejected, which is useful when debugging scheduling failures.

The C++ implementation performs equivalent capability checks in `Runner::supports()`, but adds an explicit trusted-runner requirement for the case study. This demonstrates an important distinction: labels describe routing capabilities, while trust and authorization should not be reduced to labels alone.

## Operating System and CPU Architecture

Operating-system and CPU architecture are separate execution constraints.

A workflow may require Linux but not Windows. Another workload may depend on x64 binaries, while an ARM64 workload needs an ARM64-compatible environment.

The examples model:

- Linux x64
- Linux ARM64
- Windows x64
- macOS ARM64
- GPU-enabled Linux x64

The Python matrix demonstration maps requested platform characteristics to compatible fleet entries.

The JavaScript runner model stores `operatingSystem` and `architecture` as explicit properties in addition to labels.

The C++ configuration validator detects contradictions such as an `arm64` label on an x64 image. This is useful because an incorrectly labeled runner can cause routing to succeed even though execution later fails.

A good runner inventory therefore keeps labels and actual machine properties consistent.

## Tool Availability

A runner's labels are not sufficient to describe every executable dependency.

The implementations also model installed tools.

Examples include:

- `python`
- `node`
- `docker`
- `cuda`
- `internal-sdk`

A job can require a label and a tool. The scheduler first verifies runner availability and labels, then checks whether the runner's execution image or machine contains the required tools.

This distinction is important because a Linux runner without Docker is not equivalent to a Linux runner configured for container builds.

The Python implementation represents tools with a `frozenset` on `RunnerImage`.

The JavaScript implementation uses a `Set` stored in `Runner.tools`.

The C++ implementation stores tools in `std::set`.

These data structures provide efficient membership checks and make capability matching explicit.

## Runner State and Lifecycle

A runner is not permanently available.

The examples use four states:

- `offline`
- `idle`
- `busy`
- `draining`

An **idle** runner can accept an eligible job.

A **busy** runner is executing a job and should not receive another job that requires exclusive execution on that runner.

An **offline** runner is unavailable.

A **draining** runner is still represented in the fleet but should not accept new work. Draining is useful before maintenance because it separates the decision to stop accepting new workloads from the later operation of shutting down or modifying the host.

The Python implementation explicitly tests that a draining runner rejects a new job.

The JavaScript implementation raises an error if an operator attempts to drain a busy runner in its simplified lifecycle model.

The C++ implementation exposes `drainRunner()`, `restoreRunner()`, and `takeOffline()` to model operational transitions.

Real runner infrastructure has additional lifecycle details, but these states provide a useful architecture-level model.

## Queueing and Scheduling

When no eligible runner is available, a job cannot simply be assigned to an incompatible machine.

The Python scheduler leaves an unroutable job in its queue.

The JavaScript scheduler emits a `job:waiting` event when a queued job has no compatible idle runner.

The C++ engine retains an unroutable job in the queue and prints diagnostics for each registered runner.

This behavior illustrates the difference between:

`no runner exists`

and:

`a runner exists but is currently unsuitable`.

A job may be waiting because:

- every compatible runner is busy
- compatible infrastructure is offline
- a required label is absent
- a required tool is absent
- the required architecture is unavailable
- the job requires a trusted environment that is not available

A queueing problem is therefore not necessarily solved by adding arbitrary runner capacity. Capacity must match the workload's constraints.

## Concurrent Capacity

Runner capacity is multidimensional.

Suppose a system has many Linux x64 runners but only one GPU runner. Ordinary Linux jobs can execute concurrently across the general fleet, while GPU jobs can still form a queue.

A simple capacity approximation is:

`wall-clock time ≈ total runner-minutes / concurrent compatible runners`

The C++ program demonstrates this relationship with thirty jobs, five-minute average execution time, and six concurrent compatible runners.

This is only an approximation. Real systems also depend on:

- job duration variability
- queueing
- runner startup time
- image provisioning
- specialized hardware
- workflow dependencies
- caching
- artifact transfer
- external service latency
- unavailable runners

The important architectural point is that **compatible concurrency**, rather than raw machine count, determines useful capacity.

## Ephemeral and Persistent Execution

An ephemeral execution environment is intended to provide a fresh environment for a workload rather than retaining state for the next workload.

The Python implementation uses `tempfile.TemporaryDirectory()` to demonstrate temporary workspace lifecycle. The directory is removed when its context ends.

The JavaScript runner contains `resetEphemeralState()`, which clears runner-level job state after an ephemeral job.

The C++ model distinguishes images with `ephemeral = true` from persistent self-hosted infrastructure with `ephemeral = false`.

Ephemeral execution can reduce accidental state leakage between workloads. Persistent machines can be useful when specialized software, hardware, or network access makes recreation expensive, but they require deliberate cleanup and stronger operational controls.

Persistent state can include:

- source workspaces
- generated files
- package caches
- credentials accidentally written to disk
- tool configuration
- logs
- temporary build outputs

The lifecycle decision should therefore be based on workload and security requirements rather than convenience alone.

## Hosted and Self-Hosted Responsibility Boundary

| Area | Hosted runner | Self-hosted runner |
|---|---|---|
| Host infrastructure | Managed by GitHub | Managed by organization/repository owner |
| Operating-system maintenance | Provider responsibility for the hosted environment | Organization responsibility |
| Custom internal software | Limited to available environment and workflow installation | Can be preinstalled and maintained by the organization |
| Specialized hardware | Depends on available hosted offerings | Organization can provide its own hardware |
| Internal network placement | Controlled by hosted infrastructure constraints | Organization controls network placement |
| Workspace persistence | Commonly designed around ephemeral environments | Can be persistent unless deliberately isolated |
| Patching responsibility | Primarily provider-side for hosted infrastructure | Organization-side |
| Trust boundary | Still requires secure workflow and credential handling | Host becomes a major organizational security boundary |
| Capacity model | Depends on available hosted capacity and service configuration | Organization must provision and operate capacity |

The table describes operational responsibilities rather than declaring one model universally preferable.

## Python Implementation

The Python program is a simulation and laboratory rather than a GitHub API client.

Its main architectural components are:

### `RunnerImage`

`RunnerImage` describes the operating system, architecture, installed tools, image name, and ephemeral characteristic of an execution environment.

Its `supports()` method checks tool requirements.

### `WorkflowJob`

`WorkflowJob` represents a unit of workflow execution. It contains labels, required tools, duration, execution state, and the runner assigned to it.

### `Runner`

`Runner` models a runner's identity, kind, labels, image, lifecycle state, group, trust classification, and current workload.

The `can_run()` method performs the core eligibility checks.

### `RunnerRegistry`

`RunnerRegistry` stores the available runners and implements deterministic routing. It records diagnostics for incompatible runners so scheduling failures can be inspected rather than silently ignored.

### `RunnerPool`

`RunnerPool` provides queueing and execution behavior. It changes the job and runner states while a job runs and records completed jobs.

The program also demonstrates real local process execution through Python's `subprocess` module. This is intentionally limited to executing the current Python interpreter with a harmless command. It illustrates the operating-system process boundary without requiring external services.

## JavaScript Implementation

The JavaScript implementation focuses on event-driven runner orchestration.

`RunnerScheduler` extends Node.js `EventEmitter`, allowing runner and job state changes to produce events such as:

`runner:registered`

`job:queued`

`job:started`

`job:succeeded`

`job:failed`

`runner:idle`

This is appropriate for JavaScript because runner orchestration is naturally modeled as an asynchronous sequence of events.

The scheduler also uses Promises and `Promise.all()` to model concurrent jobs. Multiple eligible runners can execute different jobs at the same time rather than forcing every job through one serial execution path.

The implementation deliberately separates:

- runner capability checks
- job creation
- registration
- routing
- queueing
- asynchronous execution
- event notification
- lifecycle transitions

The `demonstrateFailedRouting()` function creates a Linux ARM64 GPU job while the fleet contains no compatible ARM64 GPU runner. The job therefore has no valid execution target, demonstrating a realistic source of queueing.

## C++ Repository Governance Case Study

The C++ implementation models a repository governance and merge-execution environment in which different workflow jobs require different classes of runner infrastructure.

The fleet contains:

- `hosted-ubuntu-x64`: general hosted Linux execution
- `internal-linux-builder`: trusted self-hosted infrastructure with an internal SDK
- `gpu-linux-builder`: trusted self-hosted infrastructure with CUDA

The `RunnerGovernanceEngine` owns runner registration, configuration validation, job submission, routing, execution, lifecycle transitions, and execution history.

### Configuration validation

The engine rejects inconsistent configurations.

For example, a runner advertising `arm64` while its image declares `x64` is rejected. This prevents a metadata problem from becoming a runtime architecture failure.

The engine also requires self-hosted runners to carry the `self-hosted` label in this model.

### Routing

`RunnerGovernanceEngine::route()` evaluates each runner and records diagnostic reasons.

A runner can be rejected because it is:

- offline
- busy
- draining
- missing a required label
- missing a required tool
- insufficiently trusted for the workload

The first compatible runner is selected in this deterministic case study.

### Execution

`executeNext()` changes the job to `Running`, marks the selected runner as `Busy`, simulates execution, records success or failure, then returns the runner to `Idle`.

A deliberate failing job demonstrates that a failed workload does not necessarily mean the runner itself has failed. The runner can return to an idle state after the workload reports failure.

### Draining

`drainRunner()` prevents new work from being assigned while leaving the runner represented in the fleet.

This is an operational mechanism rather than a job result.

### Offline state

`takeOffline()` represents removal of a runner from active scheduling. The implementation prevents abrupt shutdown of a busy runner in order to make lifecycle handling explicit.

### Security classification

The case study includes `trusted` as a property of infrastructure. This is intentionally separate from labels.

A label can help a scheduler find a machine with a capability. It should not by itself be treated as proof that the machine is authorized to receive sensitive workloads.

## Security Considerations

A runner executes workflow code. That fact defines a significant security boundary.

For hosted environments, workflows should still be treated as executable code with access to whatever permissions, tokens, secrets, artifacts, or external systems are made available to them.

For self-hosted environments, the consequences can be broader because the runner host may have persistent filesystem state or network access to organizational resources.

Important controls include:

- least-privilege service accounts
- minimal workflow permissions
- restricted network access
- careful secret exposure
- operating-system patching
- runner software updates
- workspace cleanup
- isolation of untrusted workloads
- separation of privileged deployment infrastructure
- monitoring of unusual runner behavior

A production deployment runner should not automatically be treated as equivalent to an ordinary test runner simply because both can execute GitHub Actions jobs.

## Common Failure Modes

### Job remains queued

Possible causes include:

- no runner has the required labels
- all matching runners are busy
- all matching runners are offline
- a specialized architecture is unavailable
- a required tool is absent
- a runner has been placed into a draining state

The implementations expose diagnostics for these conditions.

### Job reaches a runner but a command fails

This is different from a scheduling failure. The runner was eligible, but the workload itself failed.

The C++ case study demonstrates this distinction with an intentionally failing job. The runner returns to the idle state after the job finishes.

### Incorrect labels

A mislabeled runner can create false scheduling compatibility. The Python and C++ validation examples show why actual machine properties should agree with advertised labels.

### Specialized capacity bottleneck

A fleet can have many general runners but still experience long waits for jobs requiring GPU, ARM64, internal software, or another specialized capability.

Adding general runners does not necessarily increase capacity for that constrained class of workload.

### Persistent-state contamination

A self-hosted runner can retain files, configuration, credentials, or build artifacts if cleanup is incomplete. This is one reason ephemeral environments can be valuable for workloads that do not need persistent machine state.

## Performance Considerations

Runner performance is affected by both machine capacity and orchestration constraints.

Important variables include:

- CPU count
- memory
- disk throughput
- network bandwidth
- container startup time
- image provisioning
- package installation
- cache effectiveness
- specialized hardware
- concurrent runner count
- workload duration

A faster individual runner can reduce execution time for one job, while additional compatible runners can reduce queue latency across independent jobs.

The distinction is important:

`execution speed` concerns how quickly one job runs.

`concurrency` concerns how many independent jobs can run simultaneously.

A fleet design should measure both.

## Debugging Runner Selection

When a job does not execute where expected, debugging should begin with the scheduling constraints rather than assuming the runner software is broken.

Inspect:

- requested labels
- runner labels
- operating-system requirements
- CPU architecture
- required tools
- runner online state
- runner busy state
- draining state
- runner group
- trust requirements
- available specialized capacity

The JavaScript scheduler's diagnostic output and the Python registry's routing diagnostics are designed specifically to expose these mismatches.

A useful diagnostic statement is more precise than "runner unavailable." A message such as `gpu-linux-builder: missing required label: arm64` directly identifies the routing mismatch.

## Production Design Considerations

Hosted runners are useful when managed execution environments meet the workflow's operating-system, software, security, and capacity requirements.

Self-hosted runners become relevant when the workload needs organizational control over infrastructure, specialized hardware, internal software, private network access, or other capabilities not provided by the standard hosted environment.

For self-hosted fleets, production design should treat runner management as infrastructure engineering rather than simply installing an agent on a convenient machine.

The fleet should have clear ownership for:

- registration and removal
- patching
- capacity planning
- monitoring
- network controls
- credential management
- workspace cleanup
- disaster recovery
- maintenance windows
- specialized hardware
- workload isolation

The most important architectural relationship is:

**A workflow defines what should execute; runner constraints determine where it can execute; runner infrastructure determines the environment and trust boundary in which it executes.**

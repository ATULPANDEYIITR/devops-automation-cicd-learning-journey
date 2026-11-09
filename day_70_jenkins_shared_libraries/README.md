# Jenkins Shared Libraries: Reusable Enterprise Pipeline Code

## 1. Introduction

Jenkins Shared Libraries provide a mechanism for organizing, distributing, maintaining, and reusing pipeline functionality across multiple Jenkins projects.

Enterprise environments commonly maintain several repositories, applications, deployment environments, and development teams. Without shared pipeline code, each application may implement its own checkout, build, testing, packaging, security scanning, and deployment operations.

This creates duplicated logic and inconsistent engineering practices.

Jenkins Shared Libraries address this problem by moving reusable pipeline functionality into centrally maintained repositories. Individual application pipelines can then consume these capabilities rather than independently implementing every operation.

A shared library establishes a common pipeline engineering model while allowing individual applications to retain their own configuration and execution requirements.

## 2. Architecture of Jenkins Shared Libraries

A conventional Jenkins Shared Library repository uses three primary directories.

| Directory | Purpose | Typical contents |
|---|---|---|
| `vars/` | Exposes globally accessible pipeline steps | Reusable Groovy scripts |
| `src/` | Contains reusable classes and supporting logic | Services, domain objects, utility classes |
| `resources/` | Stores non-executable supporting files | Configuration files, templates, deployment policies |

A fourth directory, `test/`, is commonly used for automated library tests.

### 2.1 The `vars/` directory

The `vars/` directory exposes functions that application pipelines can invoke directly.

Examples include:

- `standardPipeline.groovy`
- `buildApplication.groovy`
- `runQualityChecks.groovy`
- `deployArtifact.groovy`
- `notifyTeam.groovy`

A file named `buildApplication.groovy` typically exposes a corresponding pipeline step named `buildApplication`.

These scripts provide the user-facing interface of the shared library.

A well-designed step should have:

- Clearly defined parameters.
- Input validation.
- Consistent error handling.
- Predictable output.
- Documented side effects.
- Minimal dependence on global pipeline state.

### 2.2 The `src/` directory

The `src/` directory contains reusable Groovy classes.

A possible organization is:

| Package | Responsibility |
|---|---|
| `com.company.ci.build` | Build configuration and build operations |
| `com.company.ci.testing` | Test execution and quality evaluation |
| `com.company.ci.security` | Security scanning and policy evaluation |
| `com.company.ci.deployment` | Deployment operations |
| `com.company.ci.notifications` | Notification services |
| `com.company.ci.configuration` | Configuration validation |

Unlike global pipeline steps, classes in `src/` provide structured application logic.

This separation makes shared pipeline functionality easier to test, maintain, and extend.

### 2.3 The `resources/` directory

The `resources/` directory stores files required by pipeline operations.

Examples include:

- Build templates.
- Deployment configuration.
- Security policy definitions.
- Environment-specific templates.
- Configuration schemas.
- Standard notification templates.

Resource files allow teams to maintain supporting configuration separately from executable pipeline logic.

## 3. Shared Library Loading and Version Management

A Jenkins controller must be configured to recognize a shared library before application pipelines can use it.

A library configuration normally specifies:

- Library name.
- Source control repository.
- Default version.
- Retrieval method.
- Credential configuration where required.
- Version override permissions.
- Whether the library is implicitly loaded.

A pipeline can then reference the configured library.

### 3.1 Library versions

A shared library should be versioned independently from the applications that consume it.

Semantic versioning provides a useful release convention.

| Version component | Meaning | Example |
|---|---|---|
| Major | Incompatible interface or behavior changes | `3.0.0` |
| Minor | Backward-compatible functionality | `2.2.0` |
| Patch | Backward-compatible corrections | `2.1.1` |

Version pinning provides reproducibility.

An application consuming `enterprise-ci@2.1.0` should continue using that release until its pipeline configuration is deliberately updated.

A moving branch reference such as `main` can introduce unexpected behavior because the library implementation may change without corresponding changes in the application repository.

For production workloads, immutable release tags or commit identifiers provide stronger reproducibility than moving branch references.

### 3.2 Release lifecycle

A controlled library release can follow this lifecycle:

`DRAFT → TESTED → APPROVED → PUBLISHED → DEPRECATED`

The release process should include:

1. Development of shared pipeline functionality.
2. Unit and integration testing.
3. Compatibility evaluation.
4. Security review.
5. Approval by authorized maintainers.
6. Version creation.
7. Publication.
8. Controlled adoption by consuming repositories.
9. Deprecation of obsolete releases.

An approved release should not have its underlying source silently replaced.

Release identity, version, and commit reference should remain traceable.

## 4. Reusable Pipeline Operations

Shared libraries should expose operations that represent stable, meaningful engineering capabilities.

Typical operations include:

| Operation | Responsibility |
|---|---|
| `checkoutSource` | Retrieves application source |
| `validateConfiguration` | Validates pipeline parameters |
| `buildApplication` | Executes the application build |
| `runUnitTests` | Executes unit tests |
| `runQualityChecks` | Evaluates quality requirements |
| `securityScan` | Performs security validation |
| `packageArtifact` | Produces deployment artifacts |
| `publishArtifact` | Publishes build outputs |
| `deployArtifact` | Performs environment deployment |
| `sendNotification` | Reports execution results |

A shared library should not force every application into an identical pipeline.

Reusable operations should be configurable through validated parameters while preserving centrally enforced policies.

### 4.1 Pipeline composition

An enterprise application pipeline may use the following sequence:

`Source Checkout`

`↓`

`Configuration Validation`

`↓`

`Build`

`↓`

`Unit and Integration Tests`

`↓`

`Code Quality and Security Checks`

`↓`

`Artifact Packaging`

`↓`

`Artifact Publication`

`↓`

`Deployment Approval`

`↓`

`Deployment`

`↓`

`Post-deployment Verification`

Individual applications can reuse the same stages while supplying application-specific build configuration and deployment settings.

### 4.2 Parameter validation

Pipeline parameters should be validated before execution.

Examples include:

- Application identifier.
- Repository URL.
- Source branch.
- Build tool.
- Runtime version.
- Target environment.
- Artifact name.
- Deployment configuration.

Validation should reject missing values, invalid environment names, unsupported repository protocols, and malformed configuration.

A pipeline should fail early when its configuration is invalid rather than proceeding with incomplete information.

## 5. Python Implementation: Pipeline Simulation

The Python implementation models a reusable pipeline execution environment.

It is a standalone simulation of shared library behavior rather than a Jenkins controller integration.

### 5.1 Domain model

The implementation uses several domain types.

| Type | Responsibility |
|---|---|
| `LibraryVersion` | Represents a versioned shared library release |
| `SharedLibraryRegistry` | Registers and resolves releases |
| `PipelineContext` | Maintains execution configuration and state |
| `PipelineSteps` | Provides reusable pipeline operations |
| `PipelineEngine` | Coordinates pipeline execution |
| `StageResult` | Records individual stage outcomes |

Dataclasses provide structured execution records.

Enums represent pipeline, stage, and environment states.

### 5.2 Library registry

The registry uses a dictionary indexed by library name and version.

The resolution process verifies:

- Library existence.
- Semantic version validity.
- Test status.
- Approval status.

Unknown or unapproved releases are rejected.

This prevents an application from silently resolving an arbitrary release.

### 5.3 Stage execution

The engine executes six stages:

| Stage | Operation |
|---|---|
| Configuration | Validates pipeline configuration |
| Checkout | Validates and records repository information |
| Build | Produces an artifact identifier |
| Test | Executes simulated test validation |
| Package | Records the packaged artifact |
| Deploy | Evaluates deployment requirements |

Each stage receives an independent execution result.

The implementation records:

- Stage name.
- Stage state.
- Execution attempts.
- Duration.
- Error information.

A failed stage causes the pipeline to enter the `FAILED` state.

### 5.4 Retry behavior

The retry mechanism executes an operation a configurable number of times.

A failed attempt does not immediately terminate the operation when additional attempts remain.

The delay increases between attempts.

Retries should only be used for operations where repeating execution is safe.

For example, retrying a temporary network request may be reasonable. Repeating a financial transaction or a non-idempotent production operation without an idempotency mechanism may create duplicate effects.

### 5.5 Credentials

The Python implementation models credential access through a scoped operation.

Credential values are removed from the in-memory execution context after the operation.

A real Jenkins implementation should use Jenkins Credentials and `withCredentials` rather than storing production secrets in pipeline configuration.

Secrets must not be printed, serialized into reports, or included in exception messages.

### 5.6 Execution reports

The Python implementation produces a JSON report.

The report contains library identity, build information, execution state, timestamps, and stage results.

A temporary file is used before replacing the destination report.

This reduces the likelihood of leaving a partially written report after a failed write.

The script also validates successful staging execution and rejection of an unapproved production deployment.

## 6. JavaScript Implementation: Event-Driven Pipeline Model

The JavaScript implementation provides a complementary event-driven execution architecture.

It uses Node.js standard-library functionality without third-party dependencies.

### 6.1 Main components

| Component | Responsibility |
|---|---|
| `SharedLibrary` | Represents an immutable library release |
| `LibraryRegistry` | Maintains registered releases |
| `PipelinePolicy` | Evaluates environment restrictions |
| `PipelineContext` | Stores execution information |
| `PipelineSteps` | Provides reusable asynchronous operations |
| `PipelineEngine` | Coordinates execution and events |

The implementation uses private class fields for registry and credential state.

Maps provide efficient release lookup, while Sets represent permitted environments.

### 6.2 Event-driven execution

The pipeline engine extends Node.js `EventEmitter`.

It publishes events such as:

- `pipelineStarted`
- `stageStarted`
- `stageFinished`
- `retry`
- `pipelineFailed`
- `pipelineFinished`

This design separates pipeline execution from reporting and monitoring.

For example, an external monitoring component can listen for stage completion events without modifying the stage implementation.

### 6.3 Asynchronous operations

The pipeline uses `async` and `await` to model operations that may involve network access, artifact repositories, or deployment services.

The execution engine processes stages sequentially because later stages depend on earlier outputs.

Independent operations could be executed concurrently where dependencies and resource constraints permit.

### 6.4 Concurrency and state management

The engine prevents duplicate execution of the same pipeline context.

A context moves through the following states:

`CREATED → RUNNING → SUCCESS`

or:

`CREATED → RUNNING → FAILED`

The execution guard prevents a second invocation from starting while the original execution is active.

For a distributed Jenkins environment, this local guard would need to be complemented by controller-level scheduling, locking, and resource coordination.

### 6.5 Reporting

The implementation generates structured JSON reports containing:

- Run identifier.
- Application information.
- Library version.
- Branch.
- Environment.
- Stage execution results.
- Failure information.

The report is written to a temporary file before being renamed to its final destination.

## 7. C++17 Implementation: Enterprise Pipeline Execution Engine

The C++ implementation focuses on strongly typed domain modeling, release validation, and controlled pipeline execution.

It does not attempt to reproduce Jenkins controller functionality. Instead, it models the operational rules that a reusable pipeline execution service should enforce.

### 7.1 Domain types

The implementation uses enums for:

- Release states.
- Pipeline states.
- Stage states.
- Deployment environments.

The `LibraryRelease` structure stores library identity, version, commit, and release state.

`PipelineDefinition` represents application-specific execution configuration.

`PipelineContext` maintains the execution state and stage history.

### 7.2 Library registry

The registry uses an ordered map indexed by library name and version.

The registry supports:

- Release registration.
- Duplicate detection.
- Release resolution.
- Approval validation.

Its lookup complexity is \(O(\log n)\), where \(n\) is the number of registered releases.

This provides predictable lookup performance for an ordered release catalog.

### 7.3 Repository policy

`RepositoryPolicy` evaluates the pipeline definition before execution.

It validates:

- Required application information.
- Repository protocol.
- Branch information.
- Positive build number.
- Permitted environments.
- Production approval.

This separates governance decisions from the actual pipeline operations.

### 7.4 Reusable pipeline steps

The `SharedPipelineSteps` class provides independent operations:

- Checkout.
- Build.
- Test.
- Package.
- Deploy.

The pipeline engine coordinates these operations through `executeStage`.

Each completed or failed operation produces a `StageResult`.

Exceptions are used to propagate execution failures to the orchestration layer.

### 7.5 Failure handling

The implementation rejects:

- Invalid release versions.
- Missing releases.
- Unapproved library releases.
- Invalid repository definitions.
- Unauthorized production deployment.
- Missing build artifacts.
- Failed pipeline operations.

The production scenario demonstrates that successful compilation and testing do not automatically authorize production deployment.

## 8. Java 17 Implementation: Enterprise Pipeline Governance

The Java implementation emphasizes enterprise-oriented domain modeling and separation of responsibilities.

### 8.1 Immutable domain objects

Java records represent:

- `LibraryRelease`
- `StageResult`
- `PipelineConfiguration`

Records provide concise immutable data structures with generated accessors and value-based equality.

Their compact constructors enforce validation at object creation.

This prevents invalid domain objects from entering the execution workflow through ordinary construction.

### 8.2 Interfaces and service separation

The implementation defines two important interfaces.

`PipelineStep<T>` represents an executable operation.

`DeploymentService` represents the deployment boundary.

The `SimulatedDeploymentService` provides a concrete implementation.

This separation makes it possible to replace the simulated service with an implementation that communicates with an actual deployment platform.

### 8.3 Approval policy

`ApprovalPolicy` evaluates whether a pipeline can execute in a particular environment.

The policy uses an immutable set of allowed environments.

Production deployments require an explicit approval decision.

The policy is independent of the pipeline stage implementation.

This separation allows different organizations to apply different environment restrictions without changing reusable build and test operations.

### 8.4 Credential handling

`CredentialStore` demonstrates scoped access to registered credentials.

A credential is retrieved only for the duration of an operation.

The implementation deliberately excludes credentials from reports.

In an actual Jenkins environment, the Jenkins Credentials system should be used for secret storage and controlled binding.

### 8.5 Pipeline execution

`PipelineExecution` coordinates:

1. Policy evaluation.
2. Source checkout.
3. Application build.
4. Automated testing.
5. Artifact packaging.
6. Deployment.

Each operation is executed through a common stage handler.

The handler records status, duration, and failure information.

The implementation uses immutable copies when exposing execution results to other components.

This prevents external callers from directly modifying the internal stage history.

## 9. PostgreSQL Implementation: Shared Pipeline Governance Database

The PostgreSQL implementation provides a relational model for tracking shared library releases and enterprise pipeline executions.

It distinguishes reusable library definitions from application-specific pipeline configurations and individual execution records.

### 9.1 Relational architecture

The primary relationships are:

`Repositories`

`↓`

`Branches`

`↓`

`Pipeline Definitions`

`↓`

`Pipeline Runs`

`↓`

`Pipeline Stages`

`↓`

`Test Results and Execution Events`

A separate release-management relationship is maintained:

`Shared Libraries`

`↓`

`Library Releases`

`↓`

`Library Modules`

`↓`

`Reusable Steps`

Release approvals and deployment approvals are recorded independently.

### 9.2 Main tables

| Table | Responsibility |
|---|---|
| `repositories` | Maintains source repository information |
| `branches` | Maintains repository branch metadata |
| `shared_libraries` | Identifies reusable libraries |
| `library_releases` | Tracks versioned releases |
| `library_modules` | Records library directory components |
| `reusable_steps` | Documents reusable pipeline operations |
| `library_approvals` | Records library release decisions |
| `pipeline_definitions` | Stores application pipeline configuration |
| `environment_policies` | Stores environment-level requirements |
| `pipeline_runs` | Records individual executions |
| `pipeline_stages` | Records stage-level outcomes |
| `pipeline_test_results` | Stores automated test results |
| `deployment_approvals` | Records deployment authorization |
| `pipeline_events` | Maintains execution audit history |

### 9.3 Database integrity

Primary keys identify individual records.

Foreign keys maintain relationships between repositories, branches, library releases, pipelines, and execution records.

Unique constraints prevent duplicate library versions and duplicate build numbers within a pipeline.

Check constraints validate:

- Semantic version formatting.
- Commit identifiers.
- Build numbers.
- Test result arithmetic.
- Stage sequence numbers.
- Execution timestamps.

These constraints prevent many invalid states from entering the database.

### 9.4 Release governance trigger

The release governance trigger protects approved release identity.

Once a library release is approved, its library association, version, and commit hash cannot be modified.

An approved release can subsequently be deprecated.

It cannot silently return to an earlier release state.

### 9.5 Pipeline state transitions

The pipeline state trigger prevents terminal execution states from being changed.

A completed pipeline cannot be changed from `SUCCESS` to `RUNNING` or from `FAILED` to `SUCCESS`.

Execution timestamps are populated when appropriate.

An additional trigger records status transitions in the audit event table.

### 9.6 Eligibility evaluation

The `evaluate_pipeline_eligibility` function evaluates several independent conditions:

- Shared library approval.
- Automated test results.
- Environment-specific requirements.
- Deployment approval.
- Successful pipeline completion.

The function returns an eligibility decision together with individual policy results and failure reasons.

This distinction is important because a successful library release does not necessarily mean that an application deployment is authorized.

Likewise, an approved deployment request does not establish that its automated tests passed.

### 9.7 Transaction processing

The `start_pipeline_run` procedure uses a row-level lock while validating and starting a pipeline execution.

This reduces the possibility of conflicting concurrent transitions for the same execution record.

The sample transaction demonstrates savepoint-based rollback for an optional audit operation.

Production deployment systems should also use suitable transaction isolation, idempotency controls, and external operation reconciliation.

### 9.8 Database reporting

The SQL script provides:

- Library release reports.
- Reusable step inventories.
- Pipeline execution reports.
- Success and failure aggregations.
- Failed-stage analysis.
- Release eligibility evaluation.
- Invalid configuration detection.
- Incomplete stage detection.
- Execution event history.

Indexes support frequent release, execution, stage, and audit lookups.

## 10. Jenkins Shared Library Design Patterns

### 10.1 Centralized pipeline logic

Common pipeline behavior should be implemented centrally.

For example, multiple application repositories may use the same security scanning step.

A security policy correction can then be delivered through a controlled library release rather than requiring each application to independently reproduce the change.

### 10.2 Configuration-driven pipelines

A reusable library should accept configuration rather than hardcode application-specific values.

A typical configuration may describe:

| Configuration | Example |
|---|---|
| Application | `payment-service` |
| Build tool | Maven |
| Runtime | Java 17 |
| Environment | Staging |
| Artifact | `payment-service.jar` |
| Test requirement | All mandatory tests pass |
| Deployment policy | Approval required for production |

Configuration values should be validated and separated from secret material.

### 10.3 Separation of responsibilities

A maintainable shared library separates pipeline interfaces, business logic, configuration, and supporting resources.

| Component | Responsibility |
|---|---|
| Pipeline entry point | Coordinates reusable operations |
| Shared pipeline steps | Exposes reusable functionality |
| Service classes | Implements complex operational logic |
| Configuration | Defines execution parameters |
| Resources | Stores templates and policy files |
| Tests | Validates expected behavior |

This architecture prevents pipeline entry points from becoming large collections of duplicated implementation details.

## 11. Reliability, Security, and Performance

### 11.1 Reliability

Shared pipeline operations should define clear failure behavior.

Important controls include:

- Explicit stage timeouts.
- Bounded retry attempts.
- Failure propagation.
- Pipeline cancellation handling.
- Artifact verification.
- Deployment health checks.
- Consistent execution reporting.

Retry behavior must account for idempotency.

A deployment operation should not be repeated blindly after an uncertain network failure.

### 11.2 Security

Shared libraries have significant influence over every pipeline that consumes them.

Their source code should receive the same security attention as other privileged infrastructure components.

Important controls include:

- Restricting write permissions to library repositories.
- Protecting release branches and tags.
- Reviewing library changes.
- Pinning production library versions.
- Restricting credential access.
- Avoiding secret exposure in console logs.
- Validating external inputs.
- Restricting privileged pipeline operations.
- Maintaining release audit history.

Jenkins Script Security and sandbox configuration should be evaluated according to the operations performed by each library.

Trusted shared libraries require particularly strict access controls because their code can execute with elevated Jenkins capabilities.

### 11.3 Performance

Shared library performance affects every consuming pipeline.

Relevant considerations include:

- Avoiding unnecessary source retrieval.
- Reducing repeated initialization.
- Limiting expensive network requests.
- Reusing safe configuration data.
- Avoiding excessive shared-library dependencies.
- Keeping pipeline stages independent where possible.
- Using appropriate concurrency limits.
- Avoiding unnecessary serialization of large execution objects.

Library caching and loading behavior should be considered when designing large shared libraries.

### 11.4 Observability

A reusable pipeline should expose enough information to identify failures without exposing confidential data.

Useful operational measurements include:

| Measurement | Purpose |
|---|---|
| Pipeline duration | Identifies slow execution |
| Stage duration | Locates performance bottlenecks |
| Failure rate | Identifies unstable operations |
| Retry frequency | Detects unreliable dependencies |
| Deployment success rate | Measures deployment reliability |
| Library adoption | Tracks release usage |
| Version distribution | Identifies outdated consumers |
| Test failure rate | Measures quality-gate stability |

Consistent structured events make it easier to correlate application execution with shared library versions.

## 12. Important Engineering Distinctions

Several related concepts should remain separate.

| Concept | Meaning |
|---|---|
| Jenkins Pipeline | Defines the workflow executed by Jenkins |
| Shared Library | Provides reusable pipeline code |
| Library release | Identifies a specific library version |
| Pipeline configuration | Defines application-specific execution parameters |
| Pipeline stage | Represents one execution phase |
| Build artifact | Represents the output of a build |
| Credentials | Provide controlled access to protected information |
| Release approval | Authorizes a shared library release |
| Deployment approval | Authorizes a particular deployment |
| Execution policy | Defines the conditions required for an operation |

A shared library does not automatically guarantee that a pipeline is secure, reproducible, or authorized.

Those properties depend on release management, configuration validation, access control, testing, and execution governance.

## 13. Limitations of the Implementations

The five implementations are executable domain models and demonstrations of reusable pipeline engineering principles.

They do not communicate with a live Jenkins controller.

| Implementation | Main limitation |
|---|---|
| Python | Simulates pipeline execution without Jenkins APIs |
| JavaScript | Models asynchronous execution without distributed workers |
| C++17 | Models execution and policy decisions without Jenkins integration |
| Java 17 | Models enterprise services without a Jenkins controller |
| PostgreSQL | Tracks releases and executions but does not execute Jenkins jobs |

The examples simulate checkout, build, test, packaging, and deployment operations.

They do not perform actual source retrieval, compilation of application projects, artifact publication, or infrastructure deployment.

The PostgreSQL database models execution and release governance. It is not a replacement for Jenkins build scheduling or its internal execution engine.

These boundaries allow the implementations to focus on reusable pipeline architecture, release management, validation, state transitions, and governance.

## 14. Execution and Validation

### Python

Requires Python 3.10 or later.

Run the script using:

`python main.py`

The program registers a library release, executes a staging pipeline, creates a JSON report, and validates production approval enforcement.

### JavaScript

Requires Node.js 18 or later.

Run the file using:

`node main.js`

The program demonstrates asynchronous execution, event emission, retry behavior, release validation, and report generation.

### C++17

Compile using:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic main.cpp -o pipeline`

Run using:

`./pipeline`

The program executes a staging pipeline and evaluates an unauthorized production deployment.

### Java 17

Compile using:

`javac Main.java`

Run using:

`java Main`

The program demonstrates immutable domain records, service interfaces, environment policies, stage execution, and validation.

### PostgreSQL

Execute the SQL script against a PostgreSQL 15 or later database.

The script creates the `jenkins_shared` schema, domain types, tables, constraints, indexes, functions, procedures, triggers, views, and sample records.

The script uses a transaction for schema and sample-data initialization.

### Expected execution characteristics

| Validation | Expected behavior |
|---|---|
| Approved library resolution | Accepted |
| Unknown library version | Rejected |
| Invalid semantic version | Rejected |
| Successful staging pipeline | Accepted |
| Failed test stage | Pipeline failure |
| Production without approval | Rejected |
| Missing deployment artifact | Rejected |
| Duplicate library release | Rejected |
| Modification of approved release identity | Rejected |
| Repeated execution of a terminal pipeline | Rejected |

## 15. Technical Learning Outcomes

The implementations demonstrate the following engineering concepts:

- Designing reusable pipeline interfaces.
- Organizing shared functionality into modules.
- Managing immutable library releases.
- Resolving explicitly versioned dependencies.
- Separating pipeline configuration from execution logic.
- Implementing reusable build and deployment operations.
- Managing execution state transitions.
- Applying environment-specific policies.
- Handling failures and bounded retries.
- Protecting credentials.
- Recording structured execution history.
- Maintaining relational integrity.
- Evaluating release and deployment eligibility.
- Designing enterprise pipeline governance.

The central architectural principle is separation between reusable pipeline functionality, application-specific configuration, library release management, and deployment authorization.

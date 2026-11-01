# Jenkins Installation, Configuration, and Plugins

## Scope

This learning artifact models a controlled Jenkins installation from controller prerequisites through plugin management and repository-oriented build governance.

The implementation treats Jenkins installation as an operational workflow rather than a single package-installation command:

`Host prerequisites → Controller configuration → Security baseline → Plugin dependencies → Credentials → Jobs → Build execution`

The five source files use the same domain theme from different engineering perspectives. Python models the installation workflow directly, JavaScript emphasizes asynchronous plugin processing and event-driven operations, C++17 implements a merge-governance engine, Java 17 models enterprise policy services, and PostgreSQL provides the persistent relational model.

## Technical Domain

Jenkins is a continuous integration and continuous delivery automation server. A Jenkins controller coordinates jobs, plugins, credentials, agents or executors, configuration, and build execution.

Installation has several distinct concerns:

| Concern | Purpose |
|---|---|
| Java runtime | Provides the runtime required by the Jenkins controller |
| Controller configuration | Defines ports, URL, executors, and security defaults |
| Plugins | Extend Jenkins capabilities |
| Plugin dependencies | Ensure required supporting plugins are installed |
| Credentials | Allow jobs to access protected systems without embedding secrets |
| Jobs | Define repeatable automation workflows |
| Build execution | Runs stages such as checkout, testing, and packaging |
| Audit data | Records operational changes without exposing secrets |

The source implementations deliberately separate these concerns.

## Installation Model

The installation workflow begins with prerequisite validation.

The model requires Java 17 or newer, a valid non-privileged HTTP port, and a bounded executor count. Security settings are also validated before the controller becomes installed.

The security baseline represented in the implementations disables anonymous read access and public user signup while requiring CSRF protection.

A controller therefore moves through explicit states:

`NEW → VALIDATED → INSTALLED`

An invalid prerequisite prevents the transition.

This makes configuration state explicit instead of allowing later operations to run against a partially initialized controller.

## Controller Configuration

The controller configuration includes:

- Controller name
- Jenkins version
- Java major version
- HTTP port
- Executor count
- Controller URL
- CSRF protection
- Anonymous-read policy
- User-signup policy

The implementations use `8080` as the demonstration HTTP port and Java 21 as the controller runtime.

The port validation prevents values outside the valid TCP port range used by the model. The executor validation prevents accidental configuration of an empty or excessively large controller execution pool.

In an actual production installation, executor sizing should account for workload type, available CPU and memory, controller responsibilities, and the use of external agents. The examples keep the controller configuration intentionally bounded.

## Security Configuration

The configuration model treats security controls as mandatory installation conditions rather than optional preferences.

The following conditions are enforced:

- CSRF protection must be enabled.
- Anonymous read access must be disabled.
- Public signup must be disabled.
- Controller URLs must have a valid HTTP or HTTPS form.
- Credentials are represented by references rather than plaintext configuration output.
- Plugin installation requires an approval state.
- Plugin compatibility is checked against the controller Java runtime.

The configuration export in the Python and JavaScript implementations deliberately omits credential secrets. The JavaScript implementation stores a SHA-256 fingerprint for operational identification rather than retaining the secret in the exported object.

The PostgreSQL model stores only a `secret_fingerprint` field. It does not create a table column intended for plaintext credential material.

## Plugin Installation

Plugins are modeled as versioned components with:

- Plugin name
- Plugin version
- Minimum Java version
- Security approval state
- Dependencies

The example dependency graph is:

`pipeline-model-definition`
`├── workflow-job`
`│   └── workflow-api`
`└── credentials`

The Git plugin is also installed because the example job obtains source code from a Git repository.

Plugin installation is not treated as an unordered list. Dependencies must be resolved before dependent plugins become installed.

### Dependency Validation

Python uses recursive dependency resolution with `visiting` and `installed` sets.

The `visiting` set detects cycles while the `installed` set prevents duplicate work. This provides graph traversal with a practical cycle-detection mechanism.

JavaScript uses the same graph concept while making the installation operation asynchronous. Each resolved plugin is processed through a Promise-based operation.

C++17 separates plugin registration, dependency resolution, and installation inside `PluginManager`.

Java 17 places dependency traversal inside `JenkinsController`, using `ArrayDeque` for the active dependency path and `HashSet` for visited nodes.

PostgreSQL represents plugin dependencies with the `plugin_dependencies` table and verifies dependencies through a trigger before a controller-plugin relationship is inserted.

## Plugin Compatibility

A plugin can be syntactically valid yet operationally unsuitable for the controller.

The model checks the plugin's minimum Java requirement against the configured controller runtime.

For example, a plugin requiring Java 21 cannot be installed on a controller configured with Java 17.

The same compatibility concept is represented at several layers:

| Implementation | Compatibility mechanism |
|---|---|
| Python | Plugin dependency validation |
| JavaScript | `PluginCatalog.resolve()` |
| C++17 | `PluginManager::resolve()` |
| Java 17 | `resolvePlugin()` |
| PostgreSQL | Controller/plugin installation trigger |

This separation is important because dependency presence and runtime compatibility are different conditions.

## Plugin Security Approval

Plugin availability is not treated as sufficient evidence for installation.

Each plugin has an approval state in the implementations. A plugin that is not security-approved is rejected before installation.

This models an operational plugin-governance decision:

`Plugin requested → Plugin exists → Runtime compatible → Dependencies available → Security approved → Install`

Plugin versions should be deliberately managed in real Jenkins environments. Blindly installing arbitrary versions can create compatibility, security, or operational risks.

## Credentials

Credentials provide access to protected resources such as source repositories.

The examples use a `git-readonly` credential reference.

The job stores the credential identifier rather than the credential value:

`Job → credential_id → credential store`

This is preferable to embedding secrets directly in job configuration.

The Python implementation uses a `CredentialReference` dataclass and redacts the secret during export.

The JavaScript implementation stores a cryptographic fingerprint and excludes the original secret from configuration output.

The PostgreSQL schema stores a fingerprint rather than a secret.

Credential ownership is also represented so that operational responsibility can be identified.

## Jenkins Jobs

The example job is `orders-service-main`.

It connects:

`Jenkins controller → Job → Repository → Branch → Credentials`

The job requires the following plugins:

- `git`
- `credentials`
- `pipeline-model-definition`

Job creation validates that all required plugins are installed.

The repository URL is also validated. The Python implementation accepts HTTPS, SSH, and Git-style URLs, while the JavaScript model deliberately restricts its example job configuration to HTTPS.

These are implementation-specific policy choices rather than universal Jenkins requirements.

## Build Workflow

The example build follows a compact pipeline:

`Checkout → Dependency Validation → Test → Package`

A successful execution reaches the package stage.

A test failure stops later stages.

The Python implementation returns a structured `BuildResult` containing:

- Job name
- Build number
- Final status
- Stage results
- Diagnostics

The JavaScript implementation represents build execution as asynchronous operations and emits a `build.started` event.

This demonstrates two useful operational distinctions:

- A job configuration describes what should execute.
- A build result records what actually happened for a particular execution.

## Failure Handling

The implementations include explicit failure conditions.

Examples include:

- Unsupported Java version
- Invalid HTTP port
- Invalid executor count
- Disabled CSRF protection
- Anonymous access enabled
- Public signup enabled
- Invalid controller URL
- Duplicate plugins
- Unknown plugins
- Missing plugin dependencies
- Circular plugin dependencies
- Plugin runtime incompatibility
- Unapproved plugins
- Invalid credential identifiers
- Missing credentials
- Invalid repository URLs
- Missing required plugins
- Failed automated tests

Explicit failure handling prevents invalid state from silently propagating into later operations.

## Python Implementation

The Python file uses dataclasses, enums, dictionaries, sets, recursive dependency resolution, custom exceptions, assertions, and JSON serialization.

`JenkinsInstallation` acts as the main domain service.

The class controls:

- Prerequisite validation
- Installation state
- Plugin registration
- Plugin dependency resolution
- Credential registration
- Job registration
- Build execution
- Safe configuration export
- Health reporting

The plugin graph uses a recursive depth-first traversal. A `visiting` set detects cycles, while an `installed` set records resolved plugins.

The script also executes validation tests when run directly. These tests verify successful and failed builds, secret redaction, unsupported Java versions, and invalid repository URLs.

The Python implementation is therefore executable without external dependencies.

## JavaScript Implementation

The JavaScript file uses Node.js standard-library functionality.

`EventEmitter` is used to model operational events such as:

- Audit events
- Build start events

`PluginCatalog` manages plugin registration, dependency resolution, and asynchronous installation.

The asynchronous installation operation uses Promises and allows the controller to model plugin installation as an operation that can complete independently of the caller's synchronous execution flow.

The credential implementation uses Node's `crypto` module to generate a SHA-256 fingerprint.

The fingerprint provides a stable non-secret representation that can be logged or exported without copying the credential value into the configuration report.

The build workflow uses asynchronous stage execution and records individual stage outcomes.

## C++17 Implementation

The C++17 implementation focuses on repository governance and merge eligibility.

The controller and plugin manager model installation state, plugin dependencies, Java compatibility, and security approval.

The second major component is `MergeEligibilityEngine`.

It evaluates:

- Target branch
- Pull Request state
- Draft status
- Merge conflicts
- Resolved conversations
- Eligible approvals
- Stale approvals
- Required status checks

This creates a separate governance perspective around the Jenkins-managed repository workflow.

The example demonstrates stale approvals explicitly. When a new commit invalidates one approval, the Pull Request no longer satisfies the two-approval policy.

The implementation uses STL containers such as `map`, `set`, and `vector`. Dependency resolution uses recursive traversal, while merge evaluation uses set-based reviewer counting and map-based status-check lookup.

## Java 17 Implementation

The Java implementation models enterprise configuration and governance through explicit domain types.

Java records represent immutable values such as:

- `ControllerConfig`
- `Plugin`
- `CredentialRef`
- `Review`
- `StatusCheck`
- `BranchProtection`
- `PullRequest`
- `MergeDecision`

The `PolicyRule` interface separates individual merge rules from the service that executes them.

`MergeEligibilityService` applies multiple policy rules and collects all failures instead of stopping after the first one.

This produces a useful operational result such as:

`Required approvals not satisfied`

and

`Required status check is not passing`

in the same evaluation.

The explicit policy-rule design makes branch governance extensible without embedding every rule into one large conditional statement.

## PostgreSQL Implementation

The PostgreSQL script provides the persistent relational representation.

The main entities are:

`controllers`
`→ plugins`
`→ plugin_dependencies`
`→ controller_plugins`
`→ repositories`
`→ branches`
`→ commits`
`→ pull_requests`
`→ reviewers`
`→ pull_request_reviews`
`→ review_comments`
`→ status_checks`
`→ branch_protection_policies`
`→ required_status_checks`
`→ credentials`
`→ jobs`
`→ job_required_plugins`
`→ merge_evaluations`
`→ audit_events`

Foreign keys enforce relationships between these entities.

Check constraints enforce basic validity.

Indexes support common lookup patterns such as Pull Requests by repository and state, reviews by Pull Request, status checks by Pull Request, and recent audit events.

## PostgreSQL Triggers

The controller installation trigger verifies security conditions when a controller enters the installed state.

The plugin installation trigger verifies:

- Controller existence
- Plugin approval
- Java compatibility
- Controller installed state
- Dependency installation

The plugin audit trigger records successful controller-plugin installation events.

These database-level checks prevent applications from bypassing important configuration rules through direct SQL operations.

## PostgreSQL Merge Evaluation

The `evaluate_pull_request()` function calculates merge eligibility using current database state.

It checks:

- Pull Request state
- Target branch
- Draft state
- Merge conflicts
- Conversation resolution
- Valid non-stale approvals
- Required status checks
- Unresolved review comments

The function returns:

| Result | Meaning |
|---|---|
| `eligible` | All represented policy conditions are satisfied |
| `blocked` | At least one merge condition has failed |

The reasons are returned as a PostgreSQL text array, making the result suitable for reporting or subsequent persistence in `merge_evaluations`.

## Pull Requests, Reviews, Approvals, and Branch Protection

These concepts are represented as distinct layers.

A Pull Request is the change-proposal workflow:

`source branch → target branch → commits → proposed change`

Code Review evaluates the proposed change through reviewer decisions and review comments.

Approvals represent explicit reviewer decisions. An approval is not automatically equivalent to merge permission because eligibility can depend on reviewer identity, stale status, required approval count, and other policy rules.

Branch Protection represents repository-level enforcement.

The relationship is:

`Pull Request`
`↓`
`Code Review`
`↓`
`Approval Decisions`
`↓`
`Branch Protection`
`↓`
`Merge Eligibility`

This distinction prevents a review approval from being treated as a complete repository governance policy.

## Branch Protection Model

The example `main` branch requires:

- Two eligible approvals
- Passing build check
- Passing unit-test check
- Passing security-scan check
- Resolved review conversations
- No direct pushes
- No force pushes
- No branch deletion
- Linear history
- No administrator bypass

The database stores these requirements independently from Pull Request records.

This is important because the same Pull Request can be evaluated under different branch policies.

## Stale Approvals

An approval can become stale when the Pull Request changes after the review decision.

The C++ and Java implementations explicitly represent stale approvals.

The PostgreSQL model stores `stale` on `pull_request_reviews`.

A stale approval is excluded from the valid approval count.

The resulting rule is:

`valid approval = approved + eligible + not stale`

This prevents an earlier review decision from automatically satisfying a policy after significant changes to the proposed code.

## Review Comments and Conversations

Review comments are separate records connected to reviews.

Each comment contains:

- File path
- Line number
- Comment body
- Resolution state
- Creation time

A Pull Request can therefore have approved reviews while still being blocked because review conversations remain unresolved.

This captures an important distinction:

`Approval decision ≠ resolved review discussion`

The branch protection policy can require both.

## Status Checks

Status checks represent automated validation associated with a Pull Request.

The example uses:

- `build`
- `unit-tests`
- `security-scan`

A required check passes only when its current state is `passing`.

A missing required check is also treated as a failure.

This avoids assuming that absence of a check means success.

## Operational Configuration Flow

A controlled Jenkins setup can be represented as:

`Java runtime`
`    ↓`
`Controller configuration`
`    ↓`
`Security validation`
`    ↓`
`Jenkins installation`
`    ↓`
`Plugin catalog`
`    ↓`
`Dependency resolution`
`    ↓`
`Approved plugin installation`
`    ↓`
`Credential references`
`    ↓`
`Job configuration`
`    ↓`
`Build execution`
`    ↓`
`Repository governance`
`    ↓`
`Merge eligibility`

Each stage has its own validation conditions.

## Configuration Failure Modes

| Failure | Detection layer | Result |
|---|---|---|
| Unsupported Java | Controller validation | Installation blocked |
| Invalid port | Controller validation | Installation blocked |
| Unsafe security defaults | Controller validation | Installation blocked |
| Missing plugin | Plugin resolver | Plugin installation blocked |
| Circular dependency | Dependency resolver | Plugin installation blocked |
| Unsupported plugin runtime | Compatibility check | Plugin installation blocked |
| Unapproved plugin | Security policy | Plugin installation blocked |
| Missing credential | Job validation | Job creation blocked |
| Failed test | Build execution | Later stages skipped |
| Stale approval | Governance engine | Merge blocked |
| Missing status check | Branch policy | Merge blocked |
| Unresolved review comment | Review policy | Merge blocked |
| Merge conflict | Pull Request evaluation | Merge blocked |

## Performance Considerations

Plugin dependency resolution is graph traversal. With `V` plugins and `E` dependency relationships, the dependency traversal is approximately `O(V + E)` when visited nodes are tracked.

The database uses indexes for recurring relationship lookups.

Merge eligibility also benefits from indexed Pull Request, review, and status-check relationships.

The examples do not attempt to model Jenkins controller scaling, distributed build agents, queue scheduling, artifact storage, or large-scale build-history retention. Those concerns require infrastructure-specific configuration beyond this learning artifact.

## Security Considerations

The implementations enforce several practical controls:

- CSRF protection
- No anonymous read access
- No public signup
- Credential references rather than plaintext job secrets
- Secret redaction during export
- Plugin security approval
- Java compatibility validation
- HTTPS repository validation in the JavaScript example
- Explicit repository branch policies
- Required status checks
- Required reviewer approvals
- Stale approval handling
- Audit records

Credential fingerprints are not substitutes for a real secret-management system. They are used here to demonstrate how an application can identify a credential without exporting the credential value.

## Configuration and Governance Boundaries

Jenkins controller configuration, plugin installation, job configuration, repository review, and branch protection should not be treated as one mechanism.

| Layer | Primary responsibility |
|---|---|
| Controller configuration | Runtime and Jenkins service behavior |
| Plugin management | Jenkins capability extension |
| Job configuration | Automation workflow |
| Pull Request | Proposed repository change |
| Code Review | Human evaluation of proposed changes |
| Approval | Reviewer decision |
| Branch Protection | Repository-level merge enforcement |
| Merge Eligibility | Current combined decision |

A successful Jenkins installation does not imply that a repository Pull Request is eligible for merge.

Likewise, a Pull Request approval does not imply that every branch-protection requirement has been satisfied.

## Practical Learning Outcomes

The implementations provide concrete practice with:

- Jenkins controller configuration
- Runtime prerequisite validation
- Security baseline enforcement
- Plugin dependency graphs
- Plugin compatibility validation
- Credential-reference design
- Build-state management
- Asynchronous Node.js processing
- Event-driven operational logging
- C++ dependency and policy engines
- Java enterprise domain modeling
- PostgreSQL relational integrity
- Database triggers
- PostgreSQL functions
- Branch protection policy evaluation
- Review and approval state
- Stale approval handling
- Status-check enforcement
- Merge-eligibility reporting

The common domain is intentionally divided across the five implementations so that each language exposes different engineering decisions rather than providing five mechanically translated versions of the same program.

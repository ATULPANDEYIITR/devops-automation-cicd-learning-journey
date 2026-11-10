# CI/CD Architecture: Pipelines, Runners, Artifacts, and Environments

## 1. Technical Scope

Continuous Integration and Continuous Delivery/Deployment (CI/CD) describe the automated processes that transform source-code changes into tested, versioned, and deployable software.

A CI/CD architecture coordinates several independent components:

- Source-code repositories and branches.
- Pull Requests and proposed changes.
- Code review and approval workflows.
- Repository-level merge restrictions.
- Pipeline definitions and execution stages.
- Runners and execution environments.
- Build outputs and artifact storage.
- Deployment environments.
- Release authorization and deployment monitoring.

The implementations model these components through executable domain logic, event-driven execution, runner scheduling, governance evaluation, and relational database operations.

The central architectural distinction is that source-code management, pipeline execution, artifact production, and deployment are separate processes connected through identifiable revisions and controlled transitions.

## 2. CI/CD Architecture

### 2.1 Continuous Integration

Continuous Integration (CI) automates the validation of changes introduced into a shared repository.

A typical CI workflow includes:

- Detecting a commit or Pull Request event.
- Retrieving the relevant repository revision.
- Preparing an isolated execution environment.
- Installing dependencies.
- Performing formatting and static analysis.
- Running unit and integration tests.
- Performing security checks.
- Building the application.
- Publishing build artifacts.
- Reporting pipeline results.

The purpose of CI is to detect defects before changes enter an important integration branch.

A successful CI execution establishes that a particular revision passed a defined set of automated checks. It does not independently authorize a repository merge or production deployment.

### 2.2 Continuous Delivery

Continuous Delivery maintains software in a deployable state.

After successful integration and artifact production, the release workflow can:

- Deploy to a development environment.
- Promote the same artifact to staging.
- Execute integration and acceptance tests.
- Request release authorization.
- Promote the approved artifact to production.

Production deployment can remain a controlled manual decision.

### 2.3 Continuous Deployment

Continuous Deployment extends Continuous Delivery by automatically releasing qualifying changes to production.

The distinction is the production-release decision:

| Property | Continuous Integration | Continuous Delivery | Continuous Deployment |
|---|---|---|---|
| Automated validation | Yes | Yes | Yes |
| Automated builds | Yes | Yes | Yes |
| Artifact production | Common | Yes | Yes |
| Staging deployment | Optional | Common | Common |
| Production authorization | Not applicable | May be manual | Automated policy |
| Production release | Separate process | Controlled release | Automatic qualifying release |

A successful pipeline is not equivalent to a successful deployment. Each stage has independent execution and failure conditions.

## 3. Pipeline Architecture

### 3.1 Pipeline Definition

A pipeline definition specifies the operations required to validate, build, package, and deploy software.

A pipeline generally contains:

- Trigger definitions.
- Workflow stages.
- Jobs.
- Execution dependencies.
- Runner requirements.
- Environment variables.
- Secrets references.
- Timeout limits.
- Retry policies.
- Artifact retention rules.
- Deployment conditions.

A pipeline definition is configuration. A pipeline run is one execution of that configuration against a particular source revision.

The distinction matters because a pipeline definition can be reused across hundreds of commits while each execution has its own state, duration, logs, artifacts, and result.

### 3.2 Pipeline Stages

A representative application pipeline follows this structure:

| Stage | Operations | Expected result |
|---|---|---|
| Validation | Formatting, linting, static analysis | Validated source |
| Testing | Unit and integration tests | Test results |
| Security | Dependency and security scanning | Security findings |
| Build | Compilation and packaging | Build output |
| Artifact publication | Checksum calculation and storage | Immutable artifact |
| Development | Automated deployment | Development release |
| Staging | Integration and acceptance testing | Release candidate |
| Production | Authorized deployment | Production release |

Stages express logical execution boundaries.

Jobs within one stage may execute concurrently when their dependencies permit it. A subsequent stage normally waits for its required predecessor jobs to finish successfully.

A failed required job should prevent dependent stages from progressing.

### 3.3 Directed Acyclic Graphs

Modern pipeline systems frequently represent job dependencies using a directed acyclic graph (DAG).

For example:

Validation
    |
    +------------------+
    |                  |
Unit Tests       Security Scan
    |                  |
    +--------+---------+
             |
           Build
             |
       Artifact Publish
             |
           Staging
             |
      Release Approval
             |
         Production

A DAG provides more scheduling flexibility than a strictly sequential pipeline.

Independent jobs can run concurrently. Jobs with dependencies must wait until their prerequisites complete.

The implementations use stage-based execution and dependency-aware domain structures to represent these execution relationships.

### 3.4 Pipeline Triggers

Common pipeline triggers include:

| Trigger | Purpose |
|---|---|
| Push | Validate a new commit |
| Pull Request | Validate proposed repository changes |
| Manual | Execute an explicitly requested workflow |
| Schedule | Perform recurring validation |
| Release | Execute release-specific workflows |
| Tag | Build or publish a versioned release |

A trigger should identify the repository, commit, branch, and workflow configuration that caused execution.

This information provides traceability between source changes and build results.

## 4. Runners and Execution Infrastructure

### 4.1 Runner Architecture

A runner is an execution worker responsible for running pipeline jobs.

The pipeline scheduler selects a suitable runner according to:

- Availability.
- Capacity.
- Operating system.
- Runtime requirements.
- Architecture.
- Installed tools.
- Execution labels.
- Security restrictions.

A runner is not the pipeline itself. The pipeline describes the work, while the runner executes assigned jobs.

### 4.2 Runner Types

| Runner type | Characteristics | Typical use |
|---|---|---|
| Hosted runner | Managed execution infrastructure | General-purpose CI |
| Self-hosted runner | Organization-managed infrastructure | Private network access |
| Container runner | Isolated container execution | Reproducible application builds |
| Virtual-machine runner | VM-based isolation | OS-specific builds |
| Ephemeral runner | Created for individual workloads | Sensitive workloads |
| Specialized runner | Dedicated hardware or software | GPU, mobile, or cross-platform builds |

### 4.3 Runner Scheduling

Runner selection is a resource-allocation problem.

A job requesting `linux`, `python`, and `docker` labels cannot be assigned to a runner that provides only `linux` and `python`.

The Python, JavaScript, and C++ implementations model:

- Runner registration.
- Execution labels.
- Capacity.
- Active job counts.
- Job dispatch.
- Job completion.
- Failure handling.

The scheduling strategy prefers compatible runners with lower current utilization.

A runner with no available capacity must not receive additional jobs.

### 4.4 Runner Security

Runners execute repository-controlled operations and should be treated as potentially exposed execution environments.

Important controls include:

- Separate execution identities.
- Short-lived credentials.
- Restricted network access.
- Isolated workspaces.
- Container or virtual-machine boundaries.
- Restricted access to deployment secrets.
- Clean-up after execution.
- Resource limits.
- Runner heartbeat monitoring.
- Controlled registration and deregistration.

Untrusted Pull Request code should not automatically receive production credentials.

Self-hosted runners require particular care because malicious build instructions can access the host environment if isolation is insufficient.

## 5. Build Artifacts

### 5.1 Artifact Definition

An artifact is a versioned output produced by a build or pipeline.

Examples include:

- Executable binaries.
- Application packages.
- Container images.
- Static web assets.
- Deployment bundles.
- Database migration packages.
- Signed release archives.

An artifact is different from a commit.

A commit identifies a source-code revision. An artifact identifies a produced build output.

The same commit may produce multiple artifacts under different build configurations.

### 5.2 Artifact Lifecycle

The artifact lifecycle is:

Source Revision
      |
      v
Build Execution
      |
      v
Artifact Creation
      |
      v
Checksum Calculation
      |
      v
Artifact Storage
      |
      v
Integrity Verification
      |
      v
Environment Promotion
      |
      v
Deployment

### 5.3 Artifact Integrity

Artifact integrity establishes that the stored or retrieved output matches the expected content.

The implementations use SHA-256 checksums to identify artifact content.

A digest can support:

- Content verification.
- Duplicate detection.
- Artifact traceability.
- Release identification.
- Integrity checks during retrieval.

An artifact registry should preserve metadata such as:

| Attribute | Purpose |
|---|---|
| Artifact identifier | Internal record identity |
| Artifact name | Human-readable identification |
| Commit SHA | Source revision |
| Pipeline run | Producing execution |
| SHA-256 digest | Content integrity |
| Storage URI | Artifact location |
| Size | Storage and transfer management |
| Creation time | Traceability |
| Retention policy | Lifecycle management |

### 5.4 Immutable Artifacts

An immutable artifact cannot be silently replaced after publication.

This property is important for reliable environment promotion.

For example, a tested application package should be promoted from staging to production without rebuilding it from potentially different source or dependency states.

The release workflow should preserve:

- Artifact identity.
- Artifact digest.
- Source commit.
- Build execution.
- Verification results.
- Deployment history.

### 5.5 Artifact Storage

Artifact storage can use:

- Private object storage.
- Container registries.
- Package registries.
- Build-system artifact repositories.

Access should be restricted through service identities and narrowly scoped permissions.

Artifact retention must balance reproducibility, audit requirements, storage costs, and security.

## 6. Deployment Environments

### 6.1 Environment Separation

A deployment environment is an independently managed application execution target.

The implementations distinguish three common environments.

| Environment | Purpose | Typical controls |
|---|---|---|
| Development | Early application validation | Frequent deployment |
| Staging | Release candidate verification | Production-like configuration |
| Production | Live application operation | Strict authorization and monitoring |

Environment separation reduces the risk of exposing unfinished changes to production users.

### 6.2 Development Environment

Development environments support rapid validation.

Typical characteristics:

- Frequent deployments.
- Developer-oriented configuration.
- Test data.
- Short feedback cycles.
- Limited operational guarantees.

### 6.3 Staging Environment

Staging evaluates the release candidate under conditions that approximate production.

Typical checks include:

- Integration tests.
- Database migration validation.
- API compatibility.
- Configuration verification.
- Performance testing.
- Security testing.
- Deployment smoke tests.

Staging should use the same artifact intended for production whenever the release architecture supports artifact promotion.

### 6.4 Production Environment

Production hosts the live application.

Production deployment may require:

- Authorized release approval.
- Verified artifact identity.
- Successful pipeline execution.
- Environment-specific credentials.
- Database migration safeguards.
- Health checks.
- Rollback capability.
- Monitoring and audit records.

The JavaScript and Java deployment services explicitly distinguish staging deployment from authorized production deployment.

The SQL implementation represents environment approvals and deployment history through separate relational entities.

### 6.5 Promotion and Rollback

Promotion transfers an already produced artifact between environments.

Rollback restores a previously deployed version when a new deployment causes an unacceptable failure.

A reliable rollback strategy requires retained artifacts and deployment metadata.

Rollback is not necessarily equivalent to reversing a database migration. Database schema changes can introduce irreversible data transformations and require independent recovery procedures.

## 7. Pull Requests

### 7.1 Purpose and Lifecycle

A Pull Request (PR) is a repository-level proposal to integrate changes from a source branch into a target branch.

It provides a structured development workflow.

A typical lifecycle is:

Feature Branch
      |
      v
Commit Changes
      |
      v
Create Draft PR
      |
      v
Open PR
      |
      v
Request Reviewers
      |
      v
Run CI Pipeline
      |
      v
Evaluate Review and Checks
      |
      v
Merge or Close

A PR is not a commit and is not a branch.

It represents a proposed change set and records the discussion and decisions associated with that proposal.

### 7.2 Source Branch and Target Branch

The source branch contains the proposed changes.

The target branch is the branch into which those changes are intended to be integrated.

For example:

- Source: `feature/payment-validation`
- Target: `main`

The source branch may contain commits that are absent from the target branch.

The target branch may also advance while the PR remains open.

Consequently, a PR must distinguish between its recorded proposed changes and the current state of both branches.

### 7.3 Changesets and Commits

A changeset represents the proposed differences between the source and target revisions.

Commits are individual repository history objects.

A PR may contain multiple commits. Its effective changeset is determined by comparing the relevant source and target revisions.

A new source commit changes the proposed revision.

A new target commit changes the integration context.

These are separate events and should not be treated as interchangeable.

### 7.4 Draft Pull Requests

A draft PR indicates that proposed changes are not yet ready for normal integration.

Draft workflows support:

- Early technical feedback.
- Preliminary CI execution.
- Architecture discussion.
- Reviewer awareness.
- Incremental development.

A draft should not automatically qualify for merging merely because some checks have succeeded.

### 7.5 Synchronizing the Base Branch

Synchronizing the base branch updates the source branch's integration context with newer target-branch changes.

This can be achieved through merging or rebasing, depending on repository conventions.

Synchronization may introduce:

- New commits.
- New merge conflicts.
- Changes in the resulting changeset.
- New test failures.
- Stale review decisions.

A successful CI result from an earlier revision should not automatically authorize a newer revision.

### 7.6 Merge Conflicts

A merge conflict occurs when changes cannot be integrated automatically.

Common causes include:

- Competing edits to the same lines.
- File deletion versus modification.
- Conflicting structural changes.
- Incompatible branch history.

Conflict resolution requires updating the proposed source revision and rerunning relevant validation.

### 7.7 Merge Strategies

| Strategy | Behavior | Trade-off |
|---|---|---|
| Merge commit | Preserves branch integration history | May introduce merge commits |
| Squash | Combines proposed changes into one commit | Individual source commits are not retained as separate target commits |
| Rebase | Reapplies commits on a newer base | Rewrites commit identities |

The repository must configure permitted strategies consistently with its history requirements.

### 7.8 Closing and Reopening

Closing a PR without merging ends the current proposal.

Reopening a closed PR restores the proposal workflow, subject to repository-specific rules.

A merged PR is a completed integration record and should not be reopened as an ordinary unmerged proposal.

## 8. Code Review

### 8.1 Purpose

Code Review is the technical evaluation of proposed changes by qualified reviewers.

It evaluates correctness, maintainability, security, reliability, and compliance with engineering standards.

A PR provides the collaboration workflow. Code Review evaluates the actual proposed implementation.

These are related but distinct mechanisms.

### 8.2 Review Criteria

| Criterion | Review question |
|---|---|
| Correctness | Does the implementation meet its requirements? |
| Security | Can the changes introduce vulnerabilities? |
| Reliability | How does the implementation behave during failure? |
| Performance | Are computational and resource costs acceptable? |
| Maintainability | Is the implementation understandable and manageable? |
| Compatibility | Are existing interfaces and consumers preserved? |
| Testing | Are meaningful normal and failure conditions covered? |
| Scope | Does the change remain within its intended objective? |

### 8.3 Inline Comments

Inline comments identify specific locations within a proposed changeset.

A useful comment should identify:

- The relevant file.
- The relevant line or code range.
- The technical concern.
- Its potential effect.
- The required clarification or correction.

Comments should be actionable rather than merely expressing disagreement.

### 8.4 Review States

| Review state | Meaning |
|---|---|
| Approved | Reviewer accepts the evaluated revision |
| Changes requested | Reviewer identifies blocking concerns |
| Commented | Reviewer provides feedback without approval |
| Dismissed | An earlier review decision is no longer active |

The latest review from an individual reviewer is generally more relevant than an older review from the same person.

### 8.5 Review Discussions

Review discussions provide a record of technical questions and responses.

A discussion may remain unresolved even after a reviewer submits an approval.

The repository can independently require all review conversations to be resolved before merging.

Resolution should indicate that the discussion has been addressed, not merely that a comment has been hidden.

### 8.6 Reviewer Responsibilities

Reviewers should:

- Understand the change objective.
- Examine the actual changeset.
- Evaluate relevant failure cases.
- Identify security and reliability risks.
- Distinguish blocking defects from optional improvements.
- Provide specific technical feedback.
- Re-evaluate revised code when necessary.

Review quality depends on technical relevance, appropriate scope, and the revision being evaluated.

### 8.7 Review Failure Modes

Common review failures include:

- Approving without examining the implementation.
- Reviewing an outdated commit.
- Ignoring security-sensitive changes.
- Treating automated test success as complete technical validation.
- Leaving blocking discussions unresolved.
- Providing vague or non-actionable feedback.
- Allowing conflicts of interest in approval decisions.

## 9. Approvals

### 9.1 Approval Semantics

An approval represents a reviewer's decision that a particular proposed revision is acceptable from the reviewer's perspective.

It is not equivalent to a general statement that the repository is ready for integration.

Approval is a recorded review decision with an associated reviewer, commit SHA, and submission time.

### 9.2 Eligible Reviewers

Reviewer eligibility is determined by repository membership, assigned permissions, account status, and applicable governance rules.

Typical eligible roles include:

- Reviewer.
- Maintainer.
- Security reviewer.
- Repository administrator, where permitted.

The implementations reject inactive reviewers and prevent authors from approving their own PRs.

### 9.3 Required Approvals

A branch policy may require two or more independent approvals.

For example:

Required approvals = 2

Alice: Approved
Bob: Approved

Approval count = 2

The PR satisfies the numerical approval requirement if both decisions remain valid for the evaluated revision.

### 9.4 Stale Approvals

An approval can become stale when new commits are introduced after review.

A review against commit `bbbbbbb` should not automatically authorize a newer commit `ccccccc`.

The implementations support invalidating earlier approvals when a new proposed commit is added.

### 9.5 Dismissed Approvals

A dismissed approval is excluded from the effective approval count.

Dismissal may occur when:

- New commits invalidate previous decisions.
- A review is withdrawn.
- A governance rule requires dismissal.
- A review is determined to be inappropriate.

Dismissal should be auditable.

### 9.6 Approval Versus Merge Eligibility

Approval is one input to merge eligibility.

It does not independently establish that a PR can be merged.

For example:

| Condition | Result |
|---|---|
| Two valid approvals | Satisfied |
| Required tests successful | Satisfied |
| Security check failed | Blocked |
| One discussion unresolved | Blocked |
| Target branch changed | Requires synchronization |

A PR with sufficient approvals can remain ineligible for merging.

## 10. Branch Protection

### 10.1 Purpose

Branch Protection is a repository-level governance mechanism that enforces conditions before changes are integrated into important branches.

It operates at a different level from PR collaboration and Code Review.

A PR describes the proposed integration. Reviews provide technical evaluation. Approvals record review decisions. Branch Protection enforces repository conditions.

### 10.2 Protected Branches

Common protected branches include:

- `main`
- `master`
- `production`
- `release/*`

Protection rules can vary by branch.

A production branch may require more approvals and stricter deployment validation than a development branch.

### 10.3 Required Status Checks

Required status checks are automated conditions that must succeed before merging.

Examples:

- Unit tests.
- Integration tests.
- Build validation.
- Security scans.
- Static analysis.
- Dependency checks.

Checks must refer to the revision being evaluated.

A successful check for an older commit is not sufficient evidence that the current revision has passed validation.

### 10.4 Direct-Push Restrictions

Direct-push restrictions prevent developers from bypassing the intended integration workflow.

Protected changes must enter through an authorized merge process.

This supports consistent review, validation, and auditability.

### 10.5 Force-Push Restrictions

Force pushes can rewrite branch history.

They may remove or replace commits and disrupt integration records.

Protected branches commonly prohibit force pushes to preserve history integrity.

### 10.6 Branch Deletion Restrictions

Important branches should not be deleted without authorization.

Deletion restrictions protect:

- Release references.
- Production integration history.
- Shared development workflows.
- Active Pull Requests.

### 10.7 Linear History

A linear-history requirement prevents merge commits from introducing additional branch-history structure.

It commonly aligns with squash or rebase-based integration policies.

It is a repository-history constraint, not a review decision.

### 10.8 Administrator Enforcement and Bypass

Some repository platforms allow administrators to bypass selected protection conditions.

Others provide options to enforce the same restrictions for administrators.

Bypass permissions should be:

- Explicitly configured.
- Restricted to authorized identities.
- Recorded in audit logs.
- Used only under defined operational conditions.

The database implementation represents bypass capability and administrative enforcement as separate policy attributes.

### 10.9 Merge Restrictions

A branch can restrict permitted merge strategies.

For example:

- Squash enabled.
- Merge commits enabled.
- Rebase disabled.
- Direct pushes prohibited.
- Force pushes prohibited.
- Two approvals required.
- Three status checks required.

The merge operation must evaluate these conditions before changing the target branch.

## 11. Relationship Between Repository Governance and CI/CD

The repository workflow and pipeline architecture are connected but are not interchangeable.

| Component | Primary responsibility |
|---|---|
| Pull Request | Propose and coordinate changes |
| Code Review | Evaluate implementation quality |
| Approval | Record a review decision |
| Branch Protection | Enforce repository integration rules |
| Pipeline Definition | Describe automated execution |
| Pipeline Run | Execute the configured workflow |
| Runner | Execute an assigned job |
| Status Check | Report an automated validation result |
| Artifact Registry | Preserve build outputs |
| Deployment Environment | Host a particular application release |
| Deployment Policy | Control release authorization |

The complete relationship is:

Repository
    |
    +-- Branches
    |     |
    |     +-- Commits
    |
    +-- Pull Request
    |     |
    |     +-- Proposed Changes
    |     |
    |     +-- Code Review
    |     |     |
    |     |     +-- Inline Comments
    |     |     +-- Review Discussions
    |     |     +-- Review Decisions
    |     |
    |     +-- Approval Evaluation
    |     |
    |     +-- CI Status Checks
    |     |
    |     +-- Branch Protection
    |           |
    |           +-- Merge Eligibility
    |
    +-- Merge
          |
          +-- Integration Commit
          |
          +-- CI/CD Pipeline
                |
                +-- Runner Scheduling
                |
                +-- Validation
                |
                +-- Testing
                |
                +-- Security
                |
                +-- Build
                |
                +-- Artifact Registry
                      |
                      +-- Development
                      |
                      +-- Staging
                      |
                      +-- Release Authorization
                      |
                      +-- Production

The merge decision and the production deployment decision remain independent.

A successfully merged PR may still fail its post-merge pipeline.

A successful pipeline may produce an artifact that cannot be deployed because an environment approval is missing.

A deployment may also fail after all repository and pipeline conditions have been satisfied.

## 12. Python Implementation

### 12.1 Architectural Approach

The Python implementation uses a domain-oriented simulation.

Dataclasses represent repository entities, while enumerations provide controlled lifecycle states.

The `Repository` class coordinates:

- Branch registration.
- Pull Request creation.
- Reviewer registration.
- Branch protection.
- Merge eligibility.
- Merge operations.
- Runner registration.
- Artifact publication.
- Deployment authorization.

### 12.2 Governance Evaluation

The `merge_eligibility()` method evaluates several independent conditions.

These include:

- PR lifecycle state.
- Target branch synchronization.
- Proposed commit membership.
- Current reviewer decisions.
- Required approval count.
- Current revision status checks.
- Unresolved conversations.

The result is a `MergeDecision` containing an eligibility flag and blocking reasons.

### 12.3 Pipeline and Artifact Handling

The runner model evaluates labels and capacity before assigning jobs.

The artifact model calculates a SHA-256 digest and enforces a maximum artifact size.

The deployment method verifies the pipeline state and artifact-to-commit association before authorizing environment promotion.

The demonstration includes executable assertions covering approval, stale reviews, conversations, self-approval, and production authorization.

### 12.4 Engineering Decisions

Python is appropriate for workflow simulation because dataclasses, dictionaries, sets, and exceptions make it straightforward to express domain state and validation.

The implementation uses in-memory state, so it does not provide durable storage, distributed locking, or actual Git operations.

The generated merge identifier is illustrative rather than a real Git object.

## 13. JavaScript Implementation

### 13.1 Event-Driven Architecture

The JavaScript implementation uses Node.js event-driven capabilities.

`RunnerPool` extends `EventEmitter` and publishes lifecycle events:

- `job:queued`
- `job:started`
- `job:succeeded`
- `job:failed`
- `job:cancelled`

These events separate job execution from monitoring and workflow coordination.

### 13.2 Asynchronous Pipeline Execution

The `Pipeline` class uses asynchronous functions and `Promise.all()` to execute independent jobs within a stage.

Subsequent stages wait until their predecessor stage completes.

A failed job causes the pipeline to fail rather than incorrectly proceeding to dependent stages.

### 13.3 Filesystem Artifact Storage

The artifact implementation uses Node.js filesystem capabilities.

Artifact filenames are derived from content digests rather than untrusted input names.

This reduces path traversal risk.

Published artifacts are stored with restricted file permissions and can be verified against their SHA-256 digest.

### 13.4 Deployment Concurrency

The deployment service supports an optional expected-current-digest condition.

This is an optimistic concurrency check.

It prevents an outdated deployment request from silently replacing an environment that has changed since the request was prepared.

### 13.5 Engineering Decisions

JavaScript provides a useful perspective for event-driven pipeline systems.

Its asynchronous execution model supports parallel job processing and independent lifecycle event handling.

The implementation uses local filesystem storage and in-memory state, so it is a working reference architecture rather than a distributed production runner service.

## 14. C++17 Implementation

### 14.1 Domain and Governance Engine

The C++17 implementation emphasizes explicit domain modeling and deterministic policy evaluation.

The primary components are:

- `Branch`
- `Commit`
- `PullRequest`
- `Reviewer`
- `Review`
- `StatusCheck`
- `Conversation`
- `BranchProtection`
- `GovernanceEngine`

The governance engine evaluates merge conditions before updating the target branch.

### 14.2 STL Data Structures

The implementation uses:

| Structure | Purpose |
|---|---|
| `vector` | Ordered commits, reviews, checks, and jobs |
| `unordered_map` | Repository entity lookup |
| `map` | Deterministic runner ordering |
| `set` | Reviewer roles and required checks |
| `optional` | Missing branch heads and merge identifiers |
| `reference_wrapper` | Runner scheduling candidates |

The use of sets makes membership checks straightforward, while maps provide structured identity-based access.

### 14.3 Runner Scheduling

The `RunnerScheduler` selects an available compatible runner.

It compares:

- Required labels.
- Current job count.
- Runner capacity.
- Runner availability.

Job completion releases allocated capacity.

The implementation prevents invalid transitions such as completing an unassigned job.

### 14.4 Artifact and Deployment Modeling

The artifact registry associates build output metadata with a source commit.

The deployment service requires a successful pipeline and matching artifact revision.

Production deployment requires explicit authorization.

The C++ digest calculation is intentionally a demonstration fingerprint based on `std::hash`; it is not a cryptographic integrity mechanism. Production implementations should use a standard cryptographic SHA-256 library or a trusted artifact service.

## 15. Java 17 Implementation

### 15.1 Enterprise Domain Model

The Java implementation uses explicit domain types and service boundaries.

Records represent immutable values such as:

- Commit.
- Reviewer.
- Review comments.
- Status checks.
- Branch protection.
- Runner configuration.
- Job definitions.
- Artifacts.
- Deployments.

Mutable classes represent entities whose lifecycle changes during execution.

### 15.2 Service Separation

The architecture separates responsibilities:

| Component | Responsibility |
|---|---|
| `Repository` | Repository and merge governance |
| `PullRequest` | Proposal lifecycle and review state |
| `RunnerScheduler` | Runner allocation |
| `Pipeline` | Stage and job orchestration |
| `ArtifactRegistry` | Artifact identity and integrity |
| `DeploymentService` | Environment promotion |

This reduces coupling between repository governance and operational deployment.

### 15.3 Parallel Execution

`ExecutorService` manages worker threads.

`CompletableFuture` coordinates independent jobs.

The implementation executes jobs within a stage concurrently and waits for all required jobs before continuing.

Runner capacity is separately tracked to prevent the scheduler from exceeding configured resource limits.

### 15.4 State and Failure Handling

The implementation uses:

- Custom exceptions.
- Explicit enumerations.
- Immutable collection views.
- Synchronized domain operations.
- Validation at construction boundaries.
- Separate job and pipeline states.

These mechanisms make invalid operations easier to detect and isolate.

The implementation does not provide persistent distributed coordination or a real container execution backend.

## 16. PostgreSQL Implementation

### 16.1 Relational Architecture

The SQL implementation models repository governance and CI/CD execution in a dedicated `cicd` schema.

Its main relational structure is:

| Table group | Main entities |
|---|---|
| Identity | Users, repository members |
| Repository | Repositories, branches |
| Version history | Commits, commit parents, branch commits |
| Pull Requests | Pull Requests, proposed commits, review requests |
| Code Review | Reviews, review comments |
| CI validation | Status checks |
| Governance | Protection policies, required checks, bypass audit |
| Merge | Merge decisions |
| Pipeline | Definitions, stages, runs, jobs |
| Infrastructure | Runners, runner labels, job dependencies |
| Build outputs | Artifacts |
| Release | Environments, approvals, deployments |
| Auditing | Audit events |

### 16.2 Referential Integrity

Primary keys identify records.

Foreign keys preserve relationships between entities.

Unique constraints prevent duplicate repository branches, membership assignments, review requests, and artifact digests.

Check constraints reject invalid states such as:

- Negative approval requirements.
- Nonpositive runner capacities.
- Invalid commit identifiers.
- Negative artifact sizes.
- Invalid job attempts.
- Incorrect deployment state combinations.

### 16.3 Review Validation

The review trigger verifies:

- The PR is open.
- The reviewer is not the author.
- The review references the current PR head.
- The reviewer is an active repository member.
- The repository role permits review.

This places important integrity checks close to the data being modified.

### 16.4 Stale Approval Handling

The stale-approval trigger invalidates previous approvals when a new PR commit is attached and the target branch policy requires dismissal.

The merge evaluation function also requires approval decisions to match the current source head.

This prevents earlier review decisions from being incorrectly reused for newer revisions.

### 16.5 Merge Eligibility

`evaluate_merge_eligibility()` evaluates:

- PR state.
- Branch synchronization.
- Proposed commits.
- Latest reviewer decisions.
- Eligible reviewer roles.
- Approval count.
- Required status checks.
- Current commit identity.
- Unresolved conversations.

It returns a structured decision containing the eligibility result, approval count, required approval count, and blocking reasons.

`merge_pull_request()` performs the database-side integration operation in a transaction.

### 16.6 Pipeline and Runner Management

The relational pipeline model separates:

- Pipeline definitions.
- Stages.
- Runs.
- Jobs.
- Runner infrastructure.
- Runner labels.
- Job dependencies.

`assign_pipeline_job()` uses row locking and `SKIP LOCKED` to reduce contention when multiple workers request available jobs.

The runner-capacity trigger updates active job counts when a job enters or exits the running state.

### 16.7 Artifact and Environment Management

Artifact records contain:

- Producing pipeline.
- Source commit.
- Artifact name.
- Storage URI.
- SHA-256 digest.
- Size.
- Immutability flag.

Deployment records reference artifacts and pipeline runs.

Environment approvals are represented independently from PR approvals because repository integration approval and production release authorization serve different purposes.

### 16.8 Reporting and Analysis

The SQL implementation includes queries for:

- PR retrieval.
- Latest review decisions.
- Merge eligibility.
- Pipeline performance.
- Runner capacity.
- Artifact inventory.
- Deployment history.
- Stale approvals.
- Missing status checks.
- Unresolved conversations.
- Production approval eligibility.
- Pipeline failures.
- Audit records.

CTEs and views consolidate frequently used reporting logic.

## 17. Failure Modes and Operational Controls

| Failure | Potential effect | Required control |
|---|---|---|
| Runner unavailable | Job remains queued | Capacity monitoring and retry |
| Runner exhaustion | Pipeline delay | Scheduling and concurrency limits |
| Job failure | Pipeline cannot progress | Failure reporting and controlled retry |
| Dependency installation failure | Build interruption | Reproducible dependency management |
| Test failure | Defective change may be introduced | Required status checks |
| Security scan failure | Vulnerable release candidate | Security policy enforcement |
| Stale approval | Outdated review decision | Revision-based approval validation |
| Merge conflict | Integration blocked | Branch synchronization |
| Artifact corruption | Invalid deployment input | Checksum verification |
| Artifact mismatch | Wrong revision deployed | Commit and digest verification |
| Missing environment approval | Unauthorized release | Environment authorization |
| Deployment failure | Service disruption | Health checks and rollback |
| Database migration failure | Application inconsistency | Migration validation and recovery |
| Credential exposure | Infrastructure compromise | Short-lived credentials and isolation |
| Concurrent deployment | Release state inconsistency | Optimistic concurrency or locking |

Failure handling should preserve the distinction between an unsuccessful job, an unsuccessful pipeline, a failed deployment, and a rejected repository merge.

## 18. Security Architecture

A secure CI/CD architecture requires controls across the entire software delivery lifecycle.

### Source and Repository Security

- Restrict repository administration.
- Protect important branches.
- Require eligible independent reviews.
- Prevent unauthorized direct pushes.
- Enforce appropriate status checks.
- Record exceptional policy bypasses.

### Pipeline Security

- Treat build configuration as executable code.
- Restrict permissions assigned to pipeline jobs.
- Validate third-party dependencies.
- Separate trusted and untrusted execution contexts.
- Avoid exposing production secrets to untrusted changes.
- Use isolated runners.

### Artifact Security

- Verify artifact checksums.
- Restrict registry write permissions.
- Preserve immutable release identifiers.
- Record source commit and build provenance.
- Enforce retention policies.
- Prevent unauthorized artifact replacement.

### Deployment Security

- Use environment-specific identities.
- Require appropriate production authorization.
- Apply least-privilege access.
- Record deployment activity.
- Monitor deployed application health.
- Maintain controlled rollback procedures.

## 19. Performance and Scalability

CI/CD performance depends on pipeline design, runner availability, dependency management, build duration, artifact transfer, and deployment orchestration.

Important optimization areas include:

| Area | Optimization |
|---|---|
| Pipeline scheduling | Run independent jobs concurrently |
| Runner utilization | Match labels and capacity efficiently |
| Dependencies | Cache safely and use reproducible versions |
| Builds | Reuse validated intermediate outputs |
| Artifacts | Use content-addressed storage |
| Pipeline history | Index repository, commit, and execution identifiers |
| Database queries | Index frequently filtered relationships |
| Review retrieval | Retrieve the latest decision per reviewer |
| Audit records | Partition large historical datasets |
| Deployments | Use controlled promotion and concurrency checks |

Parallel execution should be applied only when dependencies permit it.

Excessive parallelism can increase infrastructure costs and reduce throughput when runners or external services become saturated.

## 20. Performance Characteristics

The principal implementation choices have the following approximate computational characteristics.

| Operation | Expected complexity |
|---|---|
| Python dictionary lookup | Average O(1) |
| Python set membership | Average O(1) |
| JavaScript Map lookup | Average sublinear, typically O(1) |
| C++ unordered-map lookup | Average O(1) |
| Java HashMap lookup | Average O(1) |
| Latest review selection | O(R) with hash-based grouping |
| Review sorting | O(R log R) |
| Required check evaluation | O(C) with indexed or hashed lookup |
| Runner selection | O(N log N) in the demonstrated sorting approach |
| Artifact digest calculation | O(B), where B is artifact size |
| Pipeline execution | Depends on job duration and available parallelism |

Where:

- `R` represents review records.
- `C` represents required checks.
- `N` represents available runners.
- `B` represents artifact size.

The PostgreSQL implementation uses indexes on frequently queried relationships, including PR reviews, status checks, pipeline execution history, runner queues, and deployment history.

## 21. Architectural Limitations

The implementations are executable reference models, not complete distributed CI/CD platforms.

| Area | Limitation |
|---|---|
| Git operations | Merge identifiers do not construct actual Git objects |
| Repository hosting | External repository synchronization is not implemented |
| Distributed runners | Execution is locally simulated |
| Container orchestration | No real container runtime is provisioned |
| Pipeline configuration | No YAML workflow parser is included |
| Secrets management | No external secrets manager is connected |
| Artifact storage | Local filesystem or relational metadata is used |
| Production deployment | No external deployment API is invoked |
| Monitoring | Operational telemetry integration is not implemented |
| Distributed locking | No cross-process repository lock service is provided |

The PostgreSQL merge procedure demonstrates database-level state transitions. A production repository service must coordinate those transitions with actual Git reference updates.

Likewise, database transactions cannot atomically include external runner processes, object storage operations, and deployment APIs.

Production systems should use idempotent operations, event delivery, durable execution records, and reconciliation mechanisms to manage failures across these boundaries.

## 22. Execution Requirements

| Deliverable | Runtime | Dependencies |
|---|---|---|
| Python | Python 3.10+ | Standard library |
| JavaScript | Node.js 18+ | Node.js standard library |
| C++17 | C++17 compiler | C++ standard library |
| Java | Java 17 | Java standard library |
| PostgreSQL | PostgreSQL 15+ | `pgcrypto` extension |

The SQL script uses the PostgreSQL `pgcrypto` extension for digest operations. Enable the extension in the database before executing the script if it is not already available.

The C++ program uses `std::hash` only for demonstration identifiers. The JavaScript, Python, and Java implementations use SHA-256 for artifact identification.

The five implementations use different engineering approaches while maintaining consistent domain distinctions:

- Python emphasizes workflow simulation and validation.
- JavaScript emphasizes event-driven execution and asynchronous orchestration.
- C++17 emphasizes explicit state and resource management.
- Java 17 emphasizes enterprise domain types and service boundaries.
- PostgreSQL emphasizes relational integrity, policy evaluation, transactional operations, and reporting.

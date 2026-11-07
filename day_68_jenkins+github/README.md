# Jenkins + GitHub Integration

## Technical Scope

This project models automated repository integration between GitHub and Jenkins. It covers webhook-based triggering, Source Code Management (SCM) polling, Pull Request automation, code review, approval decisions, status checks, branch protection, and merge eligibility.

The implementations use five complementary approaches:

| Deliverable | Engineering perspective |
|---|---|
| Python | Repository workflow simulation and governance |
| JavaScript | Event-driven webhook processing and asynchronous build dispatch |
| C++17 | Repository governance and merge-eligibility engine |
| Java 17 | Enterprise domain model and policy-based workflow services |
| PostgreSQL | Relational repository, CI/CD, and governance database |

The implementations model the same general engineering domain but use different programming approaches. The Python implementation emphasizes workflow simulation, JavaScript emphasizes event handling, C++ emphasizes policy evaluation, Java emphasizes enterprise domain modeling, and PostgreSQL emphasizes persistent workflow state and integrity.

---

## 1. Jenkins and GitHub Integration Architecture

GitHub manages repository source code, branches, commits, Pull Requests, and review discussions. Jenkins automates build, test, security analysis, and deployment activities.

The integration connects repository events to automated Jenkins jobs.

### Main components

| Component | Responsibility |
|---|---|
| GitHub repository | Stores source code and development history |
| Git branch | Maintains an independent line of development |
| Git commit | Identifies a specific repository revision |
| GitHub webhook | Notifies an external service about repository events |
| Jenkins controller | Coordinates jobs, builds, and pipeline execution |
| Jenkins agent | Executes pipeline stages |
| Jenkinsfile | Defines pipeline stages and execution conditions |
| SCM polling | Periodically checks repository revisions |
| Pull Request | Proposes changes between branches |
| Status checks | Communicate automated validation results |
| Branch protection | Enforces repository-level merge restrictions |

### Integration architecture

    Developer
       |
       v
    GitHub Repository
       |
       +--------------------------+
       |                          |
       v                          v
    GitHub Webhook             SCM Polling
       |                          |
       v                          v
    Webhook Receiver          Jenkins SCM Check
       |                          |
       +------------+-------------+
                    |
                    v
              Jenkins Controller
                    |
                    v
                Jenkins Job
                    |
                    v
               Jenkins Agent
                    |
          +---------+---------+
          |         |         |
          v         v         v
        Build      Tests    Security
          |         |         |
          +---------+---------+
                    |
                    v
             Status Checks
                    |
                    v
             GitHub Pull Request
                    |
                    v
              Code Review
                    |
                    v
                Approval
                    |
                    v
             Branch Protection
                    |
                    v
              Merge Decision
                    |
                    v
              Target Branch

The architecture separates event delivery, build execution, review decisions, and repository governance. A successful Jenkins build does not automatically authorize a merge.

---

## 2. GitHub Webhooks

### Definition

A webhook is an HTTP notification sent by GitHub to a configured external endpoint when a repository event occurs.

Instead of continuously asking GitHub whether something changed, an integration receives notifications when relevant events happen.

This is an event-driven integration mechanism.

### Important webhook events

| GitHub event | Typical action | Jenkins integration |
|---|---|---|
| `push` | Commit pushed | Trigger branch build |
| `pull_request` | PR opened or synchronized | Trigger PR validation |
| `pull_request` | PR reopened | Revalidate proposed changes |
| `pull_request_review` | Review submitted | Update review workflow |
| `check_suite` | Check suite completed | Update CI state |
| `check_run` | Check execution changed | Publish check results |
| `ping` | Webhook configuration tested | Verify connectivity |

Not every event should start a Jenkins build. Review submissions, discussion changes, and webhook configuration events can be processed without starting another pipeline.

### Webhook processing

A typical webhook request contains:

- An event identifier.
- An event name.
- A delivery identifier.
- A JSON payload.
- A cryptographic signature.

GitHub provides the `X-GitHub-Event` header to identify the event and `X-GitHub-Delivery` to identify the delivery.

The `X-Hub-Signature-256` header contains an HMAC-SHA256 signature.

The receiver should:

1. Read the original request body.
2. Calculate HMAC-SHA256 using the configured webhook secret.
3. Compare the calculated and supplied signatures securely.
4. Validate the event type.
5. Validate the payload.
6. Check whether the delivery has already been processed.
7. Queue the appropriate Jenkins job.
8. Record processing results.

The signature must be calculated over the original raw request body. Parsing and serializing JSON before verification can change the bytes and invalidate the signature.

### Webhook authentication

The JavaScript implementation uses Node.js `crypto.createHmac()` and `crypto.timingSafeEqual()`.

The Python implementation uses `hmac.new()`, SHA-256, and `hmac.compare_digest()`.

These mechanisms protect the webhook receiver against unauthorized requests and ordinary timing-based signature comparisons.

A production deployment should also use:

- HTTPS.
- Secret storage outside source control.
- Request size limits.
- Network restrictions where appropriate.
- Durable delivery records.
- Rate limiting.
- Monitoring and alerting.

Webhook signature verification authenticates possession of the configured secret. It does not replace authorization checks for individual repository operations.

### Duplicate delivery handling

GitHub can retry webhook deliveries. Consequently, an integration must not assume that every HTTP delivery represents a new repository event.

The delivery identifier provides an idempotency key.

The implementations demonstrate delivery deduplication using:

- Python dictionaries.
- JavaScript Maps.
- Java sets.
- PostgreSQL primary keys.

The PostgreSQL implementation uses `ON CONFLICT DO NOTHING` to prevent the same delivery identifier from being registered twice.

In a production system, delivery registration and event queuing should be coordinated through durable storage or a transactional outbox. An in-memory registry alone is not sufficient because it loses its state when the process restarts.

---

## 3. SCM Polling

### Definition

SCM polling is a mechanism through which Jenkins periodically checks a source code repository for changes.

The Jenkins job compares the currently observed repository revision with the previously observed revision.

If a relevant revision changes, Jenkins schedules a build.

### Workflow

    Jenkins Scheduler
           |
           v
      SCM Repository
           |
           v
      Read Branch HEAD
           |
           v
      Compare Commit SHA
           |
       +---+---+
       |       |
     Same    Changed
       |       |
       v       v
      Skip    Queue Build

### Polling example

Assume the following observations:

| Poll | Branch | Observed SHA | Result |
|---|---|---|---|
| 1 | main | `aaaa...` | Initial observation |
| 2 | main | `aaaa...` | No change |
| 3 | main | `bbbb...` | Change detected |
| 4 | main | `bbbb...` | No change |
| 5 | main | `cccc...` | Change detected |

The Python and JavaScript implementations maintain the previous SHA for each repository and branch.

The Java implementation uses a synchronized polling service. The PostgreSQL implementation records each observation with a timestamp and a Boolean indicating whether a change was detected.

### Webhooks versus SCM polling

| Characteristic | Webhooks | SCM polling |
|---|---|---|
| Operating model | Event-driven | Periodic checking |
| Notification | GitHub sends notification | Jenkins checks GitHub |
| Typical latency | Low | Depends on polling interval |
| Repository requests | Event-triggered | Repeated checks |
| Delivery failure | Requires retry handling | Next poll may detect changes |
| Duplicate handling | Delivery deduplication | Revision comparison |
| Network direction | GitHub to receiver | Jenkins to repository |
| Infrastructure | Requires reachable webhook endpoint | Requires SCM connectivity |

Webhooks generally reduce unnecessary repository checks and provide faster event delivery.

SCM polling remains useful where inbound webhook connectivity is unavailable, restricted, or unsuitable.

Both approaches can coexist, but duplicate builds should be controlled through idempotency and build-queue policies.

### Polling performance

Polling every few seconds across hundreds of repositories can generate unnecessary API requests.

A practical configuration considers:

- Repository count.
- Number of monitored branches.
- Polling interval.
- GitHub API limits.
- Repository activity.
- Jenkins controller capacity.

Jenkins SCM polling should not be confused with Jenkins periodically running a build regardless of whether source code changed.

---

## 4. Jenkins Pipeline Automation

### Pipeline execution

A Jenkins pipeline defines the sequence of activities required to validate and produce software.

A typical repository pipeline contains:

| Stage | Responsibility |
|---|---|
| Checkout | Obtain the requested source revision |
| Dependency installation | Resolve required dependencies |
| Build | Compile or package the application |
| Unit tests | Validate individual components |
| Integration tests | Validate interactions between components |
| Security scan | Identify security weaknesses |
| Artifact generation | Produce deployable output |
| Publication | Store or publish the validated artifact |

### Jenkinsfile

A repository-managed Jenkins pipeline is commonly defined through a `Jenkinsfile`.

The Jenkinsfile is version-controlled with the application. This allows pipeline changes to be reviewed alongside source changes.

Important pipeline concepts include:

- Pipeline: the complete automated workflow.
- Stage: a logical group of activities.
- Step: an individual operation.
- Agent: an execution environment.
- Workspace: the directory used by a build.
- Environment: configuration available during execution.
- Artifact: output produced by a build.
- Post condition: actions performed after a pipeline or stage.

### Build isolation

A Jenkins controller coordinates builds, while Jenkins agents execute work.

Separating these responsibilities allows multiple builds to execute concurrently.

Agents should have controlled permissions and should not automatically receive unrestricted access to production credentials.

### Build state management

The implementations model these states:

| State | Meaning |
|---|---|
| QUEUED | Waiting for execution |
| RUNNING | Pipeline is executing |
| SUCCESS | Pipeline completed successfully |
| FAILURE | Pipeline failed |
| ABORTED | Execution was intentionally stopped |

A build should not transition directly from a completed state back to running.

The Java and C++ implementations explicitly model build-state transitions. The JavaScript implementation uses asynchronous execution and event notifications.

### Status check publication

Jenkins results can be communicated to GitHub through status checks or check runs.

For Pull Request validation, the result must correspond to the exact commit being evaluated.

For example:

- Unit tests pass for commit A.
- A developer pushes commit B.
- Commit A's successful test result does not establish that commit B passed the tests.

The implementations therefore associate status checks with commit SHAs.

This prevents stale successful results from incorrectly satisfying the current merge policy.

---

## 5. Pull Requests

### Definition

A Pull Request is a GitHub collaboration mechanism through which proposed changes from one branch are submitted for consideration in another branch.

A Pull Request is not itself a branch and does not independently modify the target branch when created.

It provides a review and integration workflow around changes that already exist in Git branches.

### Source and target branches

| Element | Responsibility |
|---|---|
| Source branch | Contains the proposed changes |
| Target branch | Receives the changes if merged |
| Source SHA | Identifies the current source revision |
| Target SHA | Identifies the target revision |
| Changeset | Represents the proposed differences |
| Commits | Record individual source history changes |

Example:

    main
      |
      +--- A --- B --- C
                   \
                    feature/payment-validation
                       |
                       D
                       |
                       E

The Pull Request proposes integrating the changes represented by D and E into main.

The source branch continues to maintain its own revision history. The target branch retains its existing state until a successful merge operation changes it.

### Pull Request lifecycle

    Feature Branch Created
             |
             v
       Commits Added
             |
             v
       Pull Request Opened
             |
             v
       Automated CI Build
             |
             v
         Code Review
             |
             v
       Review Decisions
             |
             v
       Required Checks
             |
             v
       Branch Protection
             |
        +----+----+
        |         |
      Blocked   Eligible
        |         |
        v         v
      Changes    Merge
      Required     |
                  v
             Target Updated

### Pull Request states

| State | Meaning |
|---|---|
| Draft | Work is not ready for normal review or merging |
| Open | Proposed changes are under consideration |
| Closed | PR was closed without merging |
| Merged | Proposed changes were integrated |

A closed Pull Request can be reopened when repository conditions permit.

A merged Pull Request is a completed integration record and should not be treated as an ordinary open PR.

### Synchronizing the target branch

The target branch can change while a Pull Request is under review.

Suppose the original target revision is A and the source branch contains D.

Another developer merges E into the target branch.

The source branch may now be behind the target branch. Synchronization updates the proposed integration state and can expose conflicts.

A source branch can be synchronized by merging the latest target branch or rebasing the source commits, depending on repository policy.

Synchronization may require CI to run again.

### Merge conflicts

A merge conflict occurs when Git cannot automatically combine changes.

Conflicts can arise when:

- Different branches modify the same lines.
- File changes overlap.
- One branch deletes a file modified by another.
- File renames interact with other modifications.

A conflict must be resolved before the merge can proceed.

### Merge strategies

| Strategy | Behavior |
|---|---|
| Merge commit | Combines histories and creates a merge commit |
| Squash | Combines the proposed changes into one commit |
| Rebase and merge | Replays source commits onto the target history |

The appropriate strategy depends on the repository's history and governance requirements.

Linear-history policies generally restrict merge commits.

### Pull Request automation

The implementations initiate builds for relevant events such as:

- PR opened.
- PR reopened.
- New commits pushed to the source branch.
- Draft PR marked ready for review.

Draft PRs can still participate in selected CI workflows, but the example policies deliberately skip normal build dispatch for draft PRs.

---

## 6. Code Review

### Definition

Code Review is the technical evaluation of proposed source changes by other developers.

A Pull Request provides the collaboration container. Code Review is the activity conducted within that container.

Code Review is not equivalent to branch protection or merge authorization.

### Review mechanics

Reviewers examine:

- Source-code correctness.
- Security weaknesses.
- Performance.
- Maintainability.
- Error handling.
- Test quality.
- Compatibility.
- Architectural consistency.
- Compliance with repository conventions.

### Inline comments

Inline comments refer to particular files and lines in the proposed changes.

Example:

    File: src/payment.py
    Line: 45

    Reviewer:
    Validate the transaction amount before
    submitting the payment request.

A review conversation can contain multiple messages and responses.

Discussions should be resolved only after the issue has been addressed or an acceptable resolution has been agreed upon.

### Review states

| Review state | Meaning |
|---|---|
| APPROVED | Reviewer accepts the proposed changes |
| CHANGES_REQUESTED | Reviewer identifies changes that must be addressed |
| COMMENTED | Reviewer provides feedback without an approval decision |
| DISMISSED | An existing review decision is dismissed |

A comment-only review is not an approval.

A dismissed approval must not continue to count as an active approval decision.

### Review quality

Effective reviews should:

- Focus on the proposed changes.
- Identify concrete defects.
- Explain why a change is problematic.
- Distinguish critical defects from style preferences.
- Avoid unnecessary changes outside the PR scope.
- Verify that requested corrections are implemented.
- Reassess changes after new commits are pushed.

The implementations model review comments independently from review decisions.

This distinction allows an approval decision and an unresolved discussion to coexist. A repository can require both approval and resolution of review conversations.

---

## 7. Approval Governance

### Definition

An approval represents an explicit reviewer decision that the proposed changes satisfy the reviewer's acceptance criteria.

An approval is a review outcome, not an automatic merge authorization.

### Reviewer eligibility

A repository can restrict approval eligibility based on:

- Repository membership.
- Repository role.
- Active account status.
- Code ownership.
- Organization policy.
- Required reviewer assignments.

A user who cannot satisfy repository reviewer requirements should not be counted toward the approval threshold.

### Required approvals

Consider a branch protection policy requiring two approvals.

| Reviewer | Decision | Counted |
|---|---|---|
| Alice | APPROVED | Yes |
| Bob | APPROVED | Yes |
| Charlie | COMMENTED | No |

The approval count is two.

A Pull Request requiring three approvals would remain blocked.

### Latest review decision

An important governance rule is that a reviewer's latest decision can replace an earlier decision.

Example:

| Sequence | Reviewer | Decision |
|---|---|---|
| 1 | Alice | APPROVED |
| 2 | Alice | CHANGES_REQUESTED |
| 3 | Alice | APPROVED |

The final active decision is approval.

The Python, C++, and Java implementations retain review history and evaluate the latest decision per eligible reviewer.

### Stale approvals

An approval is associated with a particular commit revision.

Suppose Alice approves commit A. The developer subsequently pushes commit B.

If the repository dismisses stale approvals, Alice's approval of A cannot satisfy the requirement for B.

This prevents previously reviewed code from being treated as reviewed after its contents change.

The database stores `reviewed_commit_sha` separately from the current Pull Request `source_sha`.

### Approval and merge eligibility

Approval requirements are part of repository governance.

The approval service determines which review decisions are valid. The merge eligibility service evaluates whether those decisions satisfy the configured policy.

An approval alone does not establish:

- Successful unit tests.
- Successful integration tests.
- Successful security checks.
- Resolved review discussions.
- Absence of merge conflicts.
- Synchronization with the target branch.

All required conditions must be satisfied independently.

---

## 8. Branch Protection

### Definition

Branch Protection is a repository-level governance mechanism that restricts operations on selected branches.

Its purpose is to protect important branches from unauthorized, unreviewed, or insufficiently validated changes.

A Pull Request does not itself enforce these restrictions. Branch protection provides the enforcement conditions.

### Protected branch example

The `main` branch in the implementations has the following policy:

| Requirement | Configuration |
|---|---|
| Required approvals | 2 |
| Required checks | Unit tests, integration tests, security scan |
| Code owner approval | Required |
| Conversation resolution | Required |
| Up-to-date source | Required |
| Direct pushes | Restricted |
| Force pushes | Restricted |
| Branch deletion | Restricted |
| Stale approvals | Dismissed |
| Administrator bypass | Disabled |

### Required status checks

A required status check must report success for the current source commit.

A successful status check for an older commit cannot automatically satisfy a new commit's requirement.

The PostgreSQL implementation stores the SHA against which each check ran.

The merge evaluation function compares that SHA against the current PR source SHA.

### Direct-push restrictions

A protected branch can prohibit direct pushes.

Developers must use the repository's approved integration workflow rather than pushing arbitrary commits directly to the protected branch.

### Force-push restrictions

A force push can rewrite branch history.

Restricting force pushes reduces the risk of accidentally removing commits or disrupting shared development history.

### Branch deletion restrictions

A protected branch can prohibit deletion.

This is particularly important for default and release branches.

### Conversation resolution

A repository can require all review discussions to be resolved before merging.

This is a repository-level merge condition, separate from whether reviewers approved the changes.

### Linear history

A linear-history requirement restricts merge methods that introduce merge commits.

The PostgreSQL schema stores this policy, while the C++ and Java domain models represent it explicitly.

An actual merge service must validate the selected Git merge strategy against this policy before performing the merge.

### Administrator behavior and bypass

Some GitHub governance configurations permit administrators or authorized actors to bypass selected restrictions.

Such bypasses must be explicit, controlled, and auditable.

The examples include an administrator bypass policy flag. Normal merge execution does not automatically assume administrator privileges.

### Important distinction

| Mechanism | Purpose |
|---|---|
| Pull Request | Proposes changes |
| Code Review | Evaluates proposed changes |
| Approval | Records a review decision |
| Branch Protection | Enforces repository-level conditions |
| Merge Eligibility | Determines whether all applicable conditions are satisfied |
| Merge | Integrates the changes into the target branch |

These mechanisms work together but are not interchangeable.

---

## 9. Merge Eligibility

### Definition

Merge eligibility is the final evaluation of whether a Pull Request satisfies the repository's applicable integration requirements.

It combines independent policy results.

### Evaluation sequence

    Pull Request Open?
           |
           v
       Not Draft?
           |
           v
      No Merge Conflict?
           |
           v
     Target Synchronized?
           |
           v
     Required Approvals?
           |
           v
     Code Owner Approval?
           |
           v
     Required CI Checks?
           |
           v
    Current Commit Validated?
           |
           v
    Discussions Resolved?
           |
           v
       Merge Eligible

If any required condition fails, the merge is blocked.

### Example evaluation

Assume a Pull Request has:

| Condition | Result |
|---|---|
| PR open | Pass |
| Draft status | Pass |
| Merge conflicts | None |
| Target synchronization | Pass |
| Alice approval | Pass |
| Bob approval | Pass |
| Code owner approval | Pass |
| Unit tests | Pass |
| Integration tests | Pass |
| Security scan | Pass |
| Review discussions | Resolved |

The Pull Request is eligible for merging.

If the developer pushes another commit after these results are recorded, the current status checks and approval decisions must be reevaluated.

### Failure conditions

The implementations cover:

- Missing approvals.
- Ineligible reviewers.
- Stale approvals.
- Missing status checks.
- Failed status checks.
- Pending status checks.
- Stale status checks.
- Unresolved conversations.
- Draft Pull Requests.
- Closed Pull Requests.
- Merge conflicts.
- Unsynchronized branches.
- Duplicate webhook deliveries.
- Invalid commit identifiers.
- Invalid branch names.
- Duplicate build requests.

The merge decision returns explicit blocking reasons rather than a generic failure message.

---

## 10. Python Implementation

The Python script implements a repository workflow simulator using standard-library features.

### Architecture

| Component | Responsibility |
|---|---|
| `Repository` | Maintains repository state |
| `Branch` | Stores branch information |
| `Commit` | Validates commit identity |
| `PullRequest` | Tracks proposed changes |
| `Review` | Records review decisions |
| `StatusCheck` | Stores Jenkins validation results |
| `BranchProtection` | Defines repository restrictions |
| `WebhookVerifier` | Validates HMAC signatures |
| `EventDeduplicator` | Rejects repeated deliveries |
| `SCMPoller` | Detects new revisions |
| `JenkinsBuildManager` | Queues and executes builds |
| `MergeEligibilityService` | Evaluates merge policy |
| `RepositoryWorkflow` | Coordinates repository operations |

### Important design decisions

Dataclasses represent repository objects and immutable configuration.

Enums restrict workflow values to recognized states.

Dictionaries provide efficient lookup for branches, commits, Pull Requests, and status checks.

Sets maintain eligible reviewer and code owner membership.

The merge eligibility service separates policy evaluation from the actual merge operation.

The test suite uses Python's `unittest` module.

### Execution

Save the script as `jenkins_github.py`.

Run:

`python jenkins_github.py`

The program executes a sample push event, Jenkins build, Pull Request review, status checks, merge evaluation, and automated tests.

### Limitations

The Python program simulates repository operations rather than making authenticated GitHub API requests.

Its delivery registry and build history are in memory. A production service should use durable storage and a persistent job queue.

The simulated merge operation updates domain state. It does not execute Git commands or verify an actual merge in a repository.

---

## 11. JavaScript Implementation

The JavaScript file uses Node.js event-driven programming.

Its architecture emphasizes asynchronous operations and webhook processing.

### Main components

| Component | Responsibility |
|---|---|
| `WebhookAuthenticator` | Verifies GitHub webhook signatures |
| `DeliveryRegistry` | Tracks duplicate deliveries |
| `GitHubEventRouter` | Routes incoming event types |
| `JenkinsDispatcher` | Queues builds and publishes events |
| `SCMMonitor` | Detects repository changes |
| `PullRequest` | Tracks PR state |
| `BranchProtectionPolicy` | Defines policy configuration |
| `MergePolicyEngine` | Evaluates merge conditions |
| HTTP server | Receives GitHub webhook requests |

### Event-driven architecture

The implementation extends Node.js `EventEmitter`.

Build events include:

- `build:queued`
- `build:started`
- `build:success`
- `build:failure`

This approach separates event producers from event consumers.

For example, the Jenkins dispatcher emits a build failure event without needing to know which monitoring or notification component consumes it.

### Asynchronous processing

The `execute()` method is asynchronous and accepts a pipeline function.

This allows pipeline operations to be composed with Promises.

The implementation uses `async` and `await` to manage execution flow and exception handling.

### Starting the webhook server

Save the file as `jenkins_github.js`.

Set the environment variables:

- `GITHUB_WEBHOOK_SECRET`: webhook secret containing at least 16 characters.
- `PORT`: HTTP listener port.
- `START_SERVER`: set to `true` to start the HTTP server.

Run:

`node jenkins_github.js`

The receiver listens at:

`POST /github-webhook`

The sender must supply valid GitHub webhook headers.

### Security characteristics

The HTTP receiver:

- Verifies the raw-body HMAC.
- Uses timing-safe comparison.
- Rejects oversized payloads.
- Validates event headers.
- Deduplicates deliveries.
- Separates request processing from build execution.

The example uses an in-memory build queue. A production implementation should use a durable queue, retry policies, bounded concurrency, and persistent idempotency records.

### Limitations

The pipeline stages are simulated asynchronous operations.

The example does not directly authenticate to Jenkins or GitHub REST APIs. A production adapter should use restricted service credentials and validated endpoint configuration.

---

## 12. C++17 Implementation

The C++ program implements a repository governance and merge-eligibility engine.

Its main purpose is to demonstrate explicit domain modeling and deterministic policy evaluation.

### Architecture

| Component | Responsibility |
|---|---|
| `Repository` | Stores repository entities |
| `Branch` | Represents branch state |
| `Commit` | Represents revision history |
| `PullRequest` | Stores proposed changes |
| `Review` | Records reviewer decisions |
| `StatusCheck` | Represents automated checks |
| `ReviewComment` | Tracks review conversations |
| `BranchProtectionPolicy` | Defines branch restrictions |
| `MergeEligibilityEngine` | Evaluates merge requirements |
| `JenkinsBuildEngine` | Manages build state |
| `SCMPoller` | Detects revision changes |
| `RepositoryGovernanceService` | Coordinates merging |

### Data structures

The implementation uses:

- `map` for ordered branch and Pull Request storage.
- `unordered_map` for commit lookup.
- `unordered_set` for reviewer membership.
- `set` for unique approvals.
- `vector` for commits, reviews, comments, and build history.
- `optional` for optional build identifiers.

### Complexity considerations

| Operation | Main data structure | Expected complexity |
|---|---|---|
| Branch lookup | `map` | O(log n) |
| Commit lookup | `unordered_map` | Average O(1) |
| Reviewer membership | `set` | O(log n) |
| Build duplicate lookup | `unordered_set` | Average O(1) |
| Latest review calculation | `map` | O(r log r) |
| Required check evaluation | `map` lookup | O(c log c) |

Here, `r` represents the number of review decisions and `c` represents the number of required checks.

### Engineering decisions

The merge eligibility engine does not directly modify repository state.

It returns a `MergeDecision` containing eligibility and explicit blockers.

The governance service performs the merge only after eligibility succeeds.

This separation prevents policy evaluation from becoming mixed with repository state transitions.

### Compilation

Save the file as `jenkins_github.cpp`.

Compile:

`g++ -std=c++17 -Wall -Wextra -pedantic -O2 jenkins_github.cpp -o jenkins_github`

Run:

`./jenkins_github`

On Windows:

`g++ -std=c++17 -Wall -Wextra -pedantic -O2 jenkins_github.cpp -o jenkins_github.exe`

`.\jenkins_github.exe`

### Limitations

The C++ implementation models merge behavior and build orchestration. It does not connect to a live Git repository, execute a Jenkins pipeline, or communicate with GitHub.

Its in-memory collections are suitable for simulation and learning, not persistent production governance.

---

## 13. Java 17 Implementation

The Java program uses an enterprise-oriented domain model.

It separates immutable data records, mutable workflow entities, policy configuration, and application services.

### Architecture

| Component | Responsibility |
|---|---|
| `Commit` | Immutable commit representation |
| `Review` | Immutable review decision |
| `StatusCheck` | Immutable CI result |
| `Branch` | Controlled branch state |
| `PullRequest` | PR lifecycle and proposed changes |
| `Repository` | Repository state and membership |
| `BranchProtectionPolicy` | Immutable policy configuration |
| `MergeEligibilityService` | Policy evaluation |
| `MergeService` | Authorized merge transition |
| `JenkinsService` | Build orchestration |
| `SCMPollingService` | Revision comparison |
| `WebhookProcessor` | Delivery processing |

### Java 17 capabilities

**Records**

Records provide immutable representations for commits, reviews, status checks, and build records.

**Enums**

Enums restrict review states, Pull Request states, check results, and build states.

**Collections**

Maps maintain repository entities and policy configurations.

Sets maintain reviewer membership and prevent duplicate delivery processing.

Lists preserve review and comment history.

**Streams**

Streams support filtering, aggregation, and latest review decision selection.

**Custom exceptions**

Domain and authorization exceptions distinguish invalid operations from access restrictions.

**Immutable structures**

`List.copyOf()`, `Set.copyOf()`, and unmodifiable collection views help prevent uncontrolled modification of exposed collections.

### Enterprise design decisions

The implementation separates:

- Repository membership.
- Reviewer eligibility.
- Code owner membership.
- Review decisions.
- Status check results.
- Branch protection.
- Merge authorization.

This allows repository governance policies to evolve without changing the underlying Pull Request representation.

The merge service rechecks eligibility before updating the target branch.

### Compilation

Save the file as `JenkinsGitHubEnterprise.java`.

Compile:

`javac JenkinsGitHubEnterprise.java`

Run:

`java JenkinsGitHubEnterprise`

### Limitations

The example uses in-memory collections and simulated build execution.

It does not implement distributed locking, persistence, real Git operations, or external identity verification.

A production deployment would require transaction management, persistent repositories, service authentication, and concurrency controls.

---

## 14. PostgreSQL Database Architecture

The PostgreSQL script models repository and CI/CD operations as a relational database.

It uses normalized entities and foreign-key relationships to maintain data integrity.

### Entity relationships

    repositories
        |
        +---- branches
        |       |
        |       +---- commits
        |       |
        |       +---- branch_protection_policies
        |                    |
        |                    +---- required_status_checks
        |
        +---- repository_members
        |          |
        |          +---- users
        |
        +---- pull_requests
                   |
                   +---- pull_request_commits
                   |
                   +---- review_requests
                   |
                   +---- reviews
                   |
                   +---- review_comments
                   |
                   +---- status_checks
                   |
                   +---- jenkins_builds
                   |
                   +---- merge_audit

    repositories
        |
        +---- jenkins_jobs
        |          |
        |          +---- jenkins_builds
        |
        +---- webhook_deliveries
        |
        +---- scm_poll_observations

### Main tables

| Table | Purpose |
|---|---|
| `repositories` | Repository identity and ownership |
| `users` | GitHub user identities |
| `repository_members` | Repository roles and reviewer eligibility |
| `branches` | Branch names and current revisions |
| `commits` | Commit history |
| `pull_requests` | Proposed changes and PR lifecycle |
| `pull_request_commits` | Commits belonging to a PR |
| `review_requests` | Requested reviewers |
| `reviews` | Review decisions |
| `review_comments` | Inline comments and discussion resolution |
| `status_checks` | Jenkins validation results |
| `jenkins_jobs` | Jenkins job configuration |
| `jenkins_builds` | Build execution history |
| `webhook_deliveries` | Incoming event records |
| `scm_poll_observations` | SCM polling history |
| `branch_protection_policies` | Protected branch rules |
| `required_status_checks` | Required CI check names |
| `merge_audit` | Completed merge history |

### Constraints

The database uses:

- Primary keys for entity identification.
- Foreign keys for relational integrity.
- Unique constraints for repository and branch identity.
- Check constraints for SHA formats and valid values.
- Enum types for controlled workflow states.
- Partial indexes for unresolved review conversations.
- Composite indexes for PR status and review retrieval.

### Trigger-based validation

The Pull Request branch trigger verifies that source and target branches belong to the same repository.

The review trigger checks whether the reviewer is eligible and active.

The discussion-resolution trigger records the time at which a comment is resolved.

These mechanisms protect database integrity independently of application-level validation.

### Views

`latest_review_decisions` identifies the latest decision made by each reviewer for each PR.

`current_pr_status_checks` provides the latest check results associated with the current PR source commit.

`pull_request_merge_report` combines PR state with merge eligibility results.

### Functions

`evaluate_merge_eligibility()` evaluates approval requirements, status checks, discussion resolution, branch synchronization, and other restrictions.

`register_webhook_delivery()` uses an idempotent insert to prevent duplicate delivery registration.

`record_scm_poll()` compares an observed remote SHA against the stored branch revision.

`create_jenkins_build()` allocates a build number and records a queued build.

### Procedures

`merge_pull_request()` performs the final database-side merge transition.

It:

1. Locks the Pull Request.
2. Validates the proposed merge SHA.
3. Checks current merge eligibility.
4. Records the merge commit.
5. Updates the target branch revision.
6. Marks the PR as merged.
7. Records the merge audit entry.

The procedure executes within the caller's database transaction.

### Transactional integrity

The merge operation uses a transaction and a row-level lock.

This reduces the possibility of concurrent operations independently merging the same Pull Request.

The database does not perform the actual Git merge. The application must execute and validate the real Git operation before committing the corresponding database transition in a production architecture.

### Performance

The script includes indexes for:

- Repository branch lookup.
- Repository commit history.
- Pull Request state retrieval.
- Target branch PR lookup.
- Latest review decisions.
- Current status checks.
- Unresolved discussions.
- Jenkins build history.
- Webhook processing state.
- SCM observation history.

These indexes support common repository and CI/CD queries.

Additional indexing should be based on actual query plans and workload measurements.

---

## 15. End-to-End Jenkins and GitHub Workflow

Consider a payment-service repository with a protected `main` branch.

A developer creates `feature/payment-validation`.

The workflow proceeds as follows.

### Development

The developer modifies the payment validation logic and commits the changes.

GitHub records the new commit in the feature branch.

The target branch remains unchanged.

### Webhook delivery

GitHub sends a push event.

The webhook receiver authenticates the request, checks the delivery identifier, and routes the event to the appropriate Jenkins job.

### Jenkins execution

Jenkins checks out the exact commit and executes:

- Dependency installation.
- Build.
- Unit tests.
- Integration tests.
- Security scanning.

The resulting status checks are associated with the tested commit.

### Pull Request creation

The developer opens a Pull Request targeting `main`.

The PR references the source and target branches and their revisions.

The proposed changes become available for review.

### Code review

Alice and Bob review the changes.

Alice approves the implementation as a code owner.

Bob provides an independent approval.

An inline discussion is resolved after the developer addresses the requested correction.

### Automated validation

Jenkins reports successful unit tests, integration tests, and security scanning.

The status results correspond to the current source commit.

### Merge eligibility

The merge eligibility service verifies:

- PR state.
- Draft status.
- Merge conflict state.
- Branch synchronization.
- Required approval count.
- Code owner approval.
- Required CI checks.
- Current commit association.
- Review discussion resolution.

If all conditions pass, the Pull Request becomes eligible for merging.

### Merge

The authorized merge operation integrates the changes into `main`.

The target branch revision changes.

A merge audit record is retained.

A subsequent push event can trigger another Jenkins pipeline for the updated target branch.

---

## 16. Security and Reliability Considerations

### Webhook security

- Use HTTPS for webhook communication.
- Keep webhook secrets outside source control.
- Verify the original request body.
- Use constant-time signature comparison.
- Reject malformed payloads.
- Restrict request sizes.
- Persist delivery identifiers.
- Avoid logging webhook secrets or sensitive payload fields.

### Jenkins security

- Use dedicated service accounts.
- Apply least-privilege permissions.
- Restrict credential access.
- Isolate build agents.
- Avoid executing untrusted repository scripts with production credentials.
- Protect Jenkins controller access.
- Separate development and production deployment credentials.

Pull Request builds from untrusted contributors require particular care because the pipeline may execute repository-controlled code.

### GitHub security

- Restrict repository administration.
- Configure protected branches.
- Require appropriate reviewer approvals.
- Require status checks.
- Restrict force pushes.
- Control bypass permissions.
- Review organization-level repository policies.

### Reliability

A production integration should address:

- Duplicate webhook deliveries.
- Delayed webhook deliveries.
- Failed build agents.
- Jenkins controller restarts.
- Interrupted builds.
- API rate limits.
- Repository synchronization failures.
- Database transaction failures.
- Concurrent merge requests.
- Stale approval decisions.
- Stale status checks.
- Retry and recovery behavior.

### Idempotency

An operation is idempotent when repeating it does not produce an unintended additional effect.

Webhook delivery registration and build scheduling should use stable event identifiers or appropriate repository-and-commit keys.

However, two distinct events involving the same commit do not necessarily represent the same business operation. Deduplication rules should reflect the desired CI behavior.

### Observability

Useful operational metrics include:

| Metric | Purpose |
|---|---|
| Webhook delivery success rate | Measures event receiver reliability |
| Duplicate delivery count | Measures repeated notifications |
| Webhook processing latency | Measures event handling performance |
| Jenkins build duration | Measures pipeline execution time |
| Build failure rate | Measures CI reliability |
| SCM polling frequency | Measures repository checking activity |
| Queue waiting time | Measures Jenkins capacity |
| PR review duration | Measures review workflow latency |
| Merge blocker count | Identifies governance bottlenecks |

---

## 17. Implementation Comparison

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Webhook validation | Yes | Yes | Simulated | Simulated | Delivery registration |
| Delivery deduplication | Yes | Yes | Build deduplication | Yes | Primary key |
| SCM polling | Yes | Yes | Yes | Yes | Yes |
| Jenkins build queue | Yes | Yes | Yes | Yes | Yes |
| PR lifecycle | Yes | Yes | Yes | Yes | Yes |
| Code review | Yes | Yes | Yes | Yes | Yes |
| Approval evaluation | Yes | Yes | Yes | Yes | Yes |
| Status checks | Yes | Yes | Yes | Yes | Yes |
| Branch protection | Yes | Yes | Yes | Yes | Yes |
| Merge eligibility | Yes | Yes | Yes | Yes | Yes |
| Persistent state | No | No | No | No | Yes |
| Real Jenkins API integration | No | No | No | No | No |
| Real Git merge execution | No | No | No | No | No |

The implementations are educational domain models rather than a complete production integration deployment. Their responsibilities are deliberately separated so that real GitHub API clients, Jenkins integrations, execution agents, and persistent services can be introduced without confusing event delivery, code review, approval, and repository enforcement.

---

## 18. Practical Engineering Distinctions

The following distinctions are central to correct Jenkins and GitHub integration.

| Concept | What it establishes | What it does not establish |
|---|---|---|
| Webhook | A repository event notification was received | A Jenkins build succeeded |
| SCM polling | A repository revision changed | A PR is approved |
| Jenkins build | An automated pipeline executed | The target branch can be modified |
| Pull Request | Changes were proposed for integration | Changes were merged |
| Code Review | Proposed changes were evaluated | Repository restrictions were satisfied |
| Approval | A reviewer accepted a revision | All CI checks passed |
| Status check | An automated validation reported a result | All governance requirements passed |
| Branch protection | Repository-level restrictions apply | A merge is automatically successful |
| Merge eligibility | Current configured conditions are satisfied | The underlying Git operation cannot fail |
| Merge | Changes were integrated into the target branch | Future commits are automatically validated |

A reliable integration treats these as separate operations connected through explicit events, revision identifiers, state transitions, and repository policies.

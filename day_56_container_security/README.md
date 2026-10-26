# Container Security in Repository Governance

## Scope

This project models container security as a repository-governance problem rather than as an isolated Docker configuration exercise.

The central security controls are:

- running containers as non-root users
- detecting vulnerable packages
- preventing secrets from being embedded in container artifacts
- requiring automated container security checks
- connecting those checks to Pull Request merge eligibility
- requiring eligible code reviews and approvals
- enforcing repository-level branch protection

The four repository concepts remain distinct:

| Area | Role |
|---|---|
| Pull Requests | Propose and track a change from a source branch into a target branch |
| Code Review | Evaluates the proposed changes through reviews and discussions |
| Approvals | Records explicit reviewer decisions that satisfy approval requirements |
| Branch Protection | Enforces repository-level conditions before a protected branch can accept the change |

The relationship is:

`Pull Request → Code Review → Approval → Status Checks → Branch Protection → Merge Eligibility`

Container security supplies part of the status-check and merge-eligibility decision.

## Security Model

A container image is considered unsafe when one or more of the following conditions is present:

| Finding | Security consequence |
|---|---|
| Root container user | A container compromise can begin with unnecessarily broad process privileges |
| Detected secret | Credentials may become available to anyone able to access the image or build artifact |
| High vulnerability | A known significant package weakness remains in the image |
| Critical vulnerability | A severe known weakness remains and should block the protected merge |
| Missing security check | The repository cannot prove that the required security control executed successfully |

The implementations intentionally treat the container user, secrets, and vulnerability findings as separate security dimensions.

A non-root user does not make an image safe by itself. An image can run as UID `10001` and still contain a critical vulnerable package or an embedded database password.

## Pull Request Lifecycle

The Pull Request model represents the change-management workflow.

A source branch contains proposed commits. The Pull Request identifies the source branch, target branch, author, and current head commit.

The lifecycle represented by the implementations is:

`Draft → Open → Review → Approval + Checks → Merge`

A Pull Request can also move to `Closed` without merging or be reopened while it remains under repository workflow control.

The implementations explicitly validate:

- Pull Request state
- draft status
- source and target branches
- current head commit
- base-branch synchronization
- merge conflicts
- review conversations
- stale approvals
- required status checks
- container-security findings

Base-branch synchronization matters because the reviewed change may become invalid after the target branch advances. A repository can therefore require the source branch to be current before accepting the change.

When a Pull Request receives new commits, approvals tied to the previous commit are treated as stale. This prevents an approval for one code state from silently authorizing a different code state.

## Code Review

Code review evaluates the proposed change itself.

The model distinguishes review states:

| Review state | Meaning |
|---|---|
| `commented` | Reviewer provided feedback without approving the change |
| `approved` | Reviewer accepts the reviewed commit for approval purposes |
| `changes_requested` | Reviewer requires changes before acceptance |
| `dismissed` | Previously recorded review is no longer an active approval |

Review comments are attached to reviews and can identify files and lines. Conversations provide a separate representation for discussion threads that must be resolved.

Review quality is represented by several controls:

- the reviewer must belong to an eligible repository role
- the author cannot approve their own Pull Request
- an approval must correspond to the current Pull Request commit
- dismissed reviews do not satisfy approval requirements
- unresolved conversations can block merging
- new commits can invalidate existing approvals

This distinction is important because reviewing a change and approving a change are different actions.

A reviewer can identify a vulnerability without approving the Pull Request. A security reviewer can approve the change only after the relevant security conditions have been satisfied.

## Approvals

Approval is a specific decision, not a synonym for code review.

The policy requires two eligible approvals in the supplied scenarios.

An eligible approval must satisfy all of these conditions:

- the reviewer exists
- the reviewer belongs to an allowed repository role
- the reviewer is not the Pull Request author
- the review state is `approved`
- the approval references the current Pull Request commit
- the review has not been dismissed

The Python, C++17, JavaScript, and Java 17 implementations deduplicate approvals by reviewer.

The PostgreSQL implementation uses `COUNT(DISTINCT reviewer_id)` so repeated approvals from the same reviewer do not artificially increase the approval count.

Stale approvals are explicitly modeled. When the reviewed commit changes, an earlier approval must not automatically authorize the new code.

This is particularly important for container security. A reviewer may approve an image running as a non-root UID, while a later commit could change the Dockerfile and introduce a root process or a vulnerable package.

## Branch Protection

Branch protection is repository-level enforcement.

The protected `main` branch in the supplied scenarios requires:

- a Pull Request
- two eligible approvals
- successful container build validation
- successful container vulnerability scanning
- successful container secret scanning
- resolved review conversations
- no merge conflict
- synchronized base state
- current approvals
- restrictions on direct pushes
- restrictions on force pushes
- restrictions on branch deletion
- linear-history enforcement where configured
- no administrator bypass in the example policy

Branch protection therefore does not perform code review itself.

It establishes the conditions under which the repository permits a reviewed change to become part of the protected branch.

The distinction is:

`Code Review = evaluation`

`Approval = reviewer decision`

`Branch Protection = repository enforcement`

## Container Security Controls

### Non-root Containers

The implementations treat `root`, UID `0`, and an empty container user as insecure.

A production image should declare an explicit unprivileged identity, such as UID `10001`, rather than relying on the runtime default.

The model does not assume that a numeric UID automatically provides complete isolation. Container privileges also depend on runtime configuration, Linux capabilities, mounted filesystems, namespaces, seccomp configuration, and orchestration policy.

The repository gate focuses on the image-level control that can be deterministically evaluated from the supplied image metadata.

### Vulnerabilities

The vulnerability model records:

- package name
- severity
- fixed version where available

High and critical vulnerabilities block merge eligibility in the supplied scenarios.

A medium vulnerability is recorded but does not automatically block the example merge.

This represents a policy decision rather than a universal security rule. Different repositories may choose different thresholds based on exploitability, exposure, compensating controls, asset criticality, and remediation deadlines.

The C++ implementation validates that high and critical findings include remediation metadata.

### Secrets

Secrets are represented separately from vulnerabilities because they have a different failure mode.

A vulnerability is a weakness in software.

A secret exposure is a credential-disclosure problem.

The Python and JavaScript implementations include lightweight scanners for patterns resembling:

- passwords
- API keys
- secret assignments
- private keys
- cloud secret credentials

A production implementation should avoid relying only on regular expressions. Secret detection should also use repository-specific rules, entropy analysis where appropriate, secret-store integration, and post-exposure credential rotation.

The database model stores only the secret name and detection source. It does not store the actual secret value.

## Python Implementation

The Python file implements an executable repository-security simulation.

Its primary domain types are:

- `Repository`
- `Branch`
- `PullRequest`
- `Commit`
- `Review`
- `StatusCheck`
- `ContainerImage`
- `Vulnerability`
- `BranchProtection`

Python `dataclass` objects provide explicit domain state.

Enums represent Pull Request, review, and status-check states.

`MergeEligibilityEngine` combines repository policy, review state, approvals, checks, conversations, branch synchronization, and container findings.

`SecretScanner` provides a standard-library-only secret-pattern check.

The scenario evaluates the same Pull Request against:

1. a non-root image with no secrets and a medium vulnerability
2. a root image containing a database password and high/critical vulnerabilities

The first decision is eligible. The second is blocked.

Assertions provide executable regression checks for both security decisions.

## JavaScript Implementation

The JavaScript file uses a Node.js standard-library design.

It uses:

- `Map` for users and status checks
- `Set` for policy requirements
- classes for domain objects
- Promises for asynchronous workflow processing
- `EventEmitter` for workflow events
- Node's `crypto` module for deterministic commit identifiers
- regular expressions for lightweight secret detection

`ContainerSecurityWorkflow` emits events for:

`workflow.started`

`container.scan.completed`

`merge.evaluated`

This makes the model suitable for event-driven repository automation.

The JavaScript implementation intentionally separates scanning from policy evaluation. The scanner produces findings, while `MergePolicyEngine` decides whether those findings prevent a merge.

## C++17 Implementation

The C++17 program implements a repository governance engine as a deterministic case study.

Its core domain objects are:

- `Repository`
- `BranchProtection`
- `PullRequest`
- `Review`
- `StatusCheck`
- `ContainerImage`
- `Vulnerability`

STL containers such as `std::map`, `std::set`, and `std::vector` provide indexed state and deduplication.

`GovernanceEngine` calculates merge eligibility.

The implementation validates:

- protected target branch existence
- Pull Request state
- draft state
- merge conflicts
- branch synchronization
- unresolved conversations
- stale approvals
- reviewer eligibility
- current-commit approval
- required checks
- root container execution
- embedded secrets
- high and critical vulnerabilities

The program separates image validation from governance evaluation. This makes it possible to reject malformed security metadata before applying merge policy.

## Java 17 Implementation

The Java implementation uses an enterprise-oriented domain model.

Java records represent immutable value-oriented objects such as:

- `User`
- `Review`
- `StatusCheck`
- `Vulnerability`
- `BranchProtectionPolicy`
- `MergeDecision`

Interfaces represent policy behavior through `SecurityPolicy`.

`NonRootAndVulnerabilityPolicy` evaluates container security independently from the repository governance service.

`MergeEligibilityService` combines the security policy with repository membership, approvals, status checks, review state, and branch protection.

The service model makes policy composition explicit:

`SecurityPolicy → MergeEligibilityService → MergeDecision`

The Pull Request object also exposes explicit state mutation for workflow conditions such as draft status, synchronization, stale approvals, conflicts, and open conversations.

## PostgreSQL Implementation

The PostgreSQL script persists the complete governance model.

The schema includes:

| Table | Purpose |
|---|---|
| `repositories` | Repository identity |
| `users` | Repository participants |
| `repository_members` | Roles and reviewer eligibility |
| `branches` | Source and protected target branches |
| `commits` | Reviewed changesets |
| `commit_files` | Files belonging to commits |
| `pull_requests` | Proposed changes |
| `reviews` | Review decisions |
| `review_comments` | Inline review feedback |
| `conversations` | Review discussions and resolution state |
| `status_checks` | Automated validation results |
| `branch_protection_policies` | Protected-branch rules |
| `required_status_checks` | Required automated checks |
| `container_images` | Container artifacts associated with Pull Requests |
| `container_secrets` | Detected secret names and detection sources |
| `vulnerabilities` | Package-level vulnerability findings |

Database constraints enforce important invariants.

Examples include:

- unique repository names
- unique branch names within a repository
- unique commit SHAs within a repository
- positive Pull Request numbers
- non-empty container users
- valid workflow enum states
- unique image vulnerabilities by package
- unique detected secrets per image

The `validate_review_reviewer` trigger prevents an author from approving their own Pull Request and checks repository reviewer eligibility.

The `invalidate_approvals_after_head_change` trigger marks approvals stale when the Pull Request head commit changes.

The `prevent_protected_branch_removal` trigger prevents deletion of a protected branch.

## Merge Eligibility in PostgreSQL

The `merge_eligibility` function evaluates repository policy in the database.

Its checks include:

- Pull Request existence
- protected target policy
- open Pull Request state
- draft status
- merge conflicts
- base synchronization
- stale approvals
- required approval count
- unresolved conversations
- required status checks
- container user
- detected secrets
- high and critical vulnerabilities

The function returns structured reasons instead of a single unexplained boolean.

For example, a decision can identify that a Pull Request has insufficient approvals while also reporting a failed security condition.

This supports auditability and operational debugging.

## Workflow State Model

The complete domain can be represented as:

`Repository`

`└── Branches`

`    ├── Source Branch`

`    └── Protected Target Branch`

`        └── Pull Request`

`            ├── Commits`

`            ├── Reviews`

`            │   └── Review Comments`

`            ├── Conversations`

`            ├── Status Checks`

`            │   ├── Container Build`

`            │   ├── Vulnerability Scan`

`            │   └── Secret Scan`

`            └── Container Image`

`                ├── Non-root Identity`

`                ├── Secrets`

`                └── Vulnerabilities`

The final decision is:

`Pull Request State`
`+ Review State`
`+ Approval State`
`+ Automated Checks`
`+ Container Security`
`+ Branch Protection`
`= Merge Eligibility`

## Failure Modes

The implementations intentionally cover several failure conditions.

| Failure | Result |
|---|---|
| Pull Request is draft | Merge blocked |
| Pull Request is closed | Merge blocked |
| Merge conflict exists | Merge blocked |
| Base branch is not synchronized | Merge blocked |
| Approval belongs to author | Approval rejected or excluded |
| Reviewer is not eligible | Approval excluded |
| Approval references old commit | Approval excluded |
| Approval is stale | Merge blocked |
| Required check missing | Merge blocked |
| Required check failed | Merge blocked |
| Conversation unresolved | Merge blocked |
| Container runs as root | Merge blocked |
| Secret detected | Merge blocked |
| High vulnerability present | Merge blocked |
| Critical vulnerability present | Merge blocked |
| Protected branch deletion attempted | Database operation rejected |

## Performance Considerations

The in-memory implementations use hash-based collections for frequent membership and lookup operations.

Examples include:

- Python dictionaries and sets
- JavaScript `Map` and `Set`
- C++ `std::map` and `std::set`
- Java `HashMap` and `HashSet`

Approval counting is deduplicated by reviewer.

The PostgreSQL schema adds indexes for access patterns that occur during eligibility evaluation:

- Pull Requests by target branch and state
- reviews by Pull Request and state
- status checks by Pull Request and name
- vulnerabilities by image and severity
- unresolved conversations by Pull Request

The database does not indiscriminately index every column. Indexes are concentrated on relationships used by policy evaluation and reporting.

## Security Design Decisions

The model follows several security principles.

### Least Privilege

Container processes should run under an explicit unprivileged identity.

Repository permissions should distinguish developers, reviewers, security reviewers, and administrators.

### Separation of Duties

The Pull Request author cannot satisfy the approval requirement for their own change.

Security review can be assigned to users with a security role.

### Immutable Review Context

Approvals are associated with a commit.

When the reviewed commit changes, previous approvals are treated as stale.

### No Secret Persistence

The PostgreSQL model stores secret identifiers and detection metadata rather than secret values.

Actual credentials should reside in a dedicated secret-management system rather than source files or container images.

### Automated Enforcement

Security scans are represented as required status checks.

A reviewer approval alone is insufficient when automated security conditions fail.

### Protected Branches

The protected branch prevents direct modification outside the governed Pull Request workflow.

Force-push and deletion restrictions reduce the ability to rewrite or remove the protected history.

## Practical Governance Scenario

Consider a developer submitting a Dockerfile change.

The Pull Request contains a new image.

The repository pipeline performs:

`Build Image`

`→ Scan Packages`

`→ Scan Secrets`

`→ Validate Container User`

`→ Run Tests`

`→ Request Review`

`→ Collect Approvals`

`→ Evaluate Branch Protection`

`→ Merge`

If the image runs as root, the security check fails even when two reviewers approve the code.

If a database password is found in the image, the merge is blocked even if all application tests pass.

If a new commit changes the Dockerfile after approval, the previous approval becomes stale and the Pull Request requires re-evaluation.

This creates a meaningful separation between human review and automated security enforcement.

## Limitations

The project models repository and container policy without integrating with a live Git hosting service or container runtime.

The secret scanner is intentionally lightweight and pattern-based. It does not provide comprehensive credential discovery.

The vulnerability model stores package findings but does not implement a live vulnerability database.

The non-root check validates the declared image user but does not evaluate runtime Linux capabilities, privileged mode, host mounts, namespace configuration, seccomp policies, or orchestrator-level security settings.

The branch protection model represents policy decisions in an executable form but does not attempt to reproduce every feature of a specific Git hosting platform.

These limitations keep the examples deterministic while preserving the important relationships between repository governance and container security.

## File Responsibilities

| File | Primary responsibility |
|---|---|
| Python | Repository workflow simulation with container-security validation and secret scanning |
| JavaScript | Event-driven security workflow and policy evaluation |
| C++17 | Deterministic repository governance and merge-eligibility engine |
| Java 17 | Enterprise domain model with explicit security and governance policy objects |
| PostgreSQL | Persistent relational model, constraints, triggers, reporting, and merge-eligibility function |
| README.md | Technical description of the security and repository-governance model |

## Key Distinctions

A Pull Request is the **proposal mechanism**.

Code Review is the **evaluation mechanism**.

An Approval is the **review decision**.

Branch Protection is the **repository enforcement mechanism**.

Container security supplies technical evidence to that enforcement process.

The important security boundary is therefore not a single Dockerfile rule. It is the complete chain:

`Proposed Change`
`→ Human Review`
`→ Explicit Approval`
`→ Automated Container Validation`
`→ Protected Branch Policy`
`→ Merge Decision`

A secure repository should prevent a change from reaching a protected branch when the required security evidence is absent, stale, failed, or explicitly unsafe.

# Pull Requests, Code Review, Approvals, and Branch Protection

## 1. Topic Introduction

A pull request is a structured proposal to integrate changes from one branch into another branch. It provides a place to inspect the proposed difference, discuss implementation details, run automated checks, record approvals, resolve review conversations, and apply repository policies before integration.

The central workflow modeled by the three implementations is:

`feature branch → pull request → diff → code review → automated checks → branch-protection policy → merge`

A pull request is not itself a Git commit or a Git branch. It is a collaboration and workflow object built around a comparison between a source branch and a target branch.

For example, a typical development flow may contain:

- `main` as the protected production-oriented branch.
- `feature/payment-validation` as the development branch.
- A pull request from `feature/payment-validation` into `main`.
- One or more reviewers.
- Required automated checks.
- A rule requiring one or more approvals.
- A rule preventing direct changes to `main`.
- A merge operation only after the configured requirements are satisfied.

The Python implementation models this workflow with a policy engine. The JavaScript implementation emphasizes executable application-level behavior and asynchronous CI simulation. The C++ implementation develops an industry-style payment-service case study with explicit data structures, classes, validation, policy evaluation, auditing, and tests.

---

## 2. Git and Pull-Request Terminology

### Repository

A repository contains project files and version history.

A repository may contain many branches representing different lines of development.

### Commit

A commit records a version of the repository state together with metadata such as:

- author
- commit message
- parent history
- changed content
- commit identifier

The educational implementations create simplified deterministic identifiers. These identifiers are not intended to reproduce Git's actual object-storage algorithm.

### Branch

A branch is a movable reference to a commit.

A common repository layout is:

- `main`
- `develop`
- `feature/...`
- `fix/...`
- `release/...`

A feature branch allows development to occur independently from the protected integration branch.

### Base branch

The base branch is the target of the proposed integration.

For example:

`feature/payment-validation → main`

Here, `main` is the base branch.

### Head branch

The head branch contains the proposed changes.

In the same example, `feature/payment-validation` is the head branch.

### Pull request

A pull request connects the source and target branches and records the proposed integration.

It normally provides information such as:

- title
- description
- changed files
- commits
- review comments
- reviewers
- review states
- status checks
- mergeability
- merge history

### Diff

A diff describes how the proposed version differs from the base version.

A reviewer generally examines the diff rather than blindly reviewing the entire repository.

---

## 3. Why Pull Requests Exist

A pull request provides a controlled point between development and integration.

Without a review workflow, a developer could make a change directly to an important branch. With a protected-branch workflow, the change can instead pass through several controls:

1. The developer creates a branch.
2. The developer commits changes.
3. The developer opens a pull request.
4. Reviewers inspect the diff.
5. Reviewers comment on specific lines.
6. Automated checks run.
7. Reviewers approve or request changes.
8. Review conversations are resolved.
9. Required branch-policy conditions are evaluated.
10. The change is merged.

This creates separation between writing code and accepting code.

---

## 4. Code Review

Code review is a technical examination of proposed changes by another person or group.

A useful review considers more than whether the code appears to work.

Important review dimensions include:

- correctness
- readability
- maintainability
- test coverage
- error handling
- security
- performance
- API compatibility
- data validation
- architectural consistency
- observability
- operational consequences

A reviewer may identify:

- a logic error
- an unhandled exception
- an insecure credential
- an insufficient test
- an unnecessary dependency
- a performance problem
- an unclear interface
- a backward-compatibility problem

The Python implementation represents a review with the `Review` class. The JavaScript implementation uses the `Review` class and `ReviewState` values. The C++ implementation uses the same conceptual model through `Review` and `ReviewState`.

---

## 5. Review States

The implementations model four useful review states:

- `approved`
- `changes_requested`
- `commented`
- `dismissed`

### Approved

An approval indicates that the reviewer accepts the reviewed state under the applicable review process.

An approval should not automatically be interpreted as a permanent statement that every future version of the pull request is acceptable.

This distinction becomes important when new commits are added.

### Changes requested

A reviewer can indicate that the pull request should not proceed until specified issues are addressed.

A branch-protection policy can treat a current change request as a merge blocker.

### Commented

A reviewer can leave feedback without formally approving or rejecting the proposed integration.

### Dismissed

A review may no longer be treated as an active approval or change request after it is dismissed under the repository's workflow.

---

## 6. Approval Versus Review

Approval and review are related but distinct concepts.

A review is an event or recorded assessment by a reviewer.

An approval is a particular review state.

A repository may require:

- one approval
- two approvals
- approval from a particular team
- approval from a code owner
- approval from reviewers other than the author

Therefore, a rule such as "two reviews are required" is not necessarily equivalent to "two independent approvals are required."

The Python policy engine explicitly counts current approvals and excludes the pull-request author from the independent approval count.

---

## 7. Why Approval Can Become Stale

Consider this sequence:

1. Alice opens a pull request.
2. Bob reviews commit `A`.
3. Bob approves commit `A`.
4. Alice changes the implementation.
5. The pull request now points to commit `B`.

The code Bob reviewed was commit `A`, while the current pull request contains commit `B`.

If the repository policy dismisses stale approvals, Bob's earlier approval does not satisfy the current approval requirement.

The Python example `demonstrate_stale_approval()` and the JavaScript and C++ stale-approval examples model this behavior.

The important principle is:

`approval is associated with a reviewed state, not automatically with every future state of the branch`

This matters because even a small subsequent commit can modify:

- business logic
- security behavior
- tests
- dependencies
- configuration
- database operations

---

## 8. Review Comments

Line-level review comments provide precise feedback.

A review comment can contain:

- reviewer
- filename
- line number
- message
- resolution state

The implementations model comments such as:

`Please validate negative amounts.`

A comment can be unresolved while the reviewer and author discuss the issue. A branch policy may require all review conversations to be resolved before merging.

Resolution should not be treated as proof that the underlying implementation is correct. It indicates that the review conversation has reached the workflow's required state.

---

## 9. Branch Protection

Branch protection is a collection of rules applied to important branches.

The educational policy model includes:

- protected branch name
- minimum approvals
- required status checks
- code-owner review
- stale-approval behavior
- conversation resolution
- branch freshness
- force-push policy
- branch deletion policy
- signed-commit requirement
- linear-history requirement
- direct-push policy

A protected `main` branch can therefore require a pull request instead of accepting unrestricted direct changes.

The exact available controls depend on the repository platform, repository configuration, permissions, and plan or organizational settings.

---

## 10. Direct Push Versus Pull Request

A direct push has a simpler path:

`developer → main`

A protected workflow is closer to:

`developer → feature branch → pull request → review/checks → main`

The second workflow creates explicit checkpoints.

Preventing direct pushes to a protected branch helps ensure that important changes pass through the required workflow.

The C++ policy contains `allowDirectPush`, while the Python and JavaScript models expose the same conceptual setting.

---

## 11. Required Status Checks

Automated checks provide machine-based validation.

Typical checks can include:

- unit tests
- integration tests
- build
- lint
- formatting
- type checking
- static analysis
- security scanning
- dependency scanning
- deployment validation

The examples use:

- `unit-tests`
- `lint` in Python and JavaScript
- `static-analysis` in C++

The policy engine checks the status for the current pull-request commit.

This is important.

A passing test result for commit `A` should not automatically be treated as proof that commit `B` passes.

The model therefore associates a `StatusCheck` with a commit identifier.

---

## 12. Why Review and CI Are Different

Human review and automated checks solve different problems.

A CI test can verify:

`calculateTotal(100, 10) == 110`

A reviewer can ask:

- Should negative values be rejected?
- Is the exception appropriate?
- Does the API need documentation?
- Is the behavior compatible with existing callers?
- Is the implementation maintainable?

Neither process completely replaces the other.

A mature workflow uses both automated verification and human review where appropriate.

---

## 13. Python Implementation

The Python script builds a complete educational policy engine.

### Repository model

The main classes are:

- `Commit`
- `Branch`
- `Repository`

The repository stores branches and commits.

A branch points to a commit through its `head`.

### Pull-request model

The main pull-request structure contains:

- number
- title
- author
- base branch
- head branch
- base commit
- head commit
- draft state
- review records
- review comments
- status checks
- code-owner approvals

### Review model

`ReviewState` provides explicit states rather than using arbitrary strings throughout the program.

This reduces accidental inconsistencies such as using both `approved` and `approve` to represent the same concept.

### Policy engine

`PullRequestPolicyEngine` separates policy evaluation from pull-request data.

This is an important design decision.

Instead of placing all merge logic inside `PullRequest`, the policy engine evaluates a pull request against a separate `BranchProtectionPolicy`.

That separation makes the system easier to:

- test
- extend
- audit
- reason about
- reuse

### Policy evaluation

The Python engine evaluates conditions such as:

- pull request is open
- pull request is not a draft
- correct protected branch is targeted
- branch is current
- no active change request exists
- enough independent approvals exist
- code-owner approval exists when required
- conversations are resolved
- required status checks passed

The engine returns a `PolicyResult` containing:

- `allowed`
- blocking reasons

This is preferable to returning only `True` or `False`, because developers need to understand why a merge is blocked.

---

## 14. Python Diff Demonstration

The Python implementation uses `difflib.unified_diff()` to demonstrate a textual unified diff.

The purpose is educational.

A real Git diff contains significantly more behavior, including:

- rename detection
- binary-file handling
- file modes
- commit metadata
- context handling
- merge diffs
- submodules
- special Git object behavior

The important concept is that a pull-request review normally focuses on the difference between the proposed and base versions.

---

## 15. Python Status Checks

The Python program simulates:

- unit tests
- lint

The simulated unit test fails if the source contains `INTENTIONALLY_BROKEN`.

The lint example rejects tab characters in Python source.

These checks are deliberately simple so the policy behavior remains visible.

The educational principle is more important than the individual check implementation:

`check result + commit identifier`

A check must correspond to the version that is being evaluated.

---

## 16. Python Security Example

The Python script includes a deliberately limited secret scanner.

It searches for patterns resembling:

- access keys
- private keys
- hard-coded passwords

The scanner demonstrates the idea of a security check but is not a complete secret-detection system.

Regular expressions can produce:

- false positives
- false negatives
- missed encoded secrets
- missed secrets split across files
- secrets stored under unexpected variable names

A production security process should therefore not rely on this small scanner alone.

---

## 17. Python Testing

The Python implementation includes `unittest` tests for:

- successful merge
- missing approval
- failed status check
- unresolved review conversation
- draft pull request
- stale approval
- author approval

These tests demonstrate an important software-engineering principle:

`policy logic should itself be tested`

A branch-protection implementation that is difficult to test is difficult to trust.

---

## 18. JavaScript Implementation

The JavaScript implementation models the same conceptual workflow but emphasizes JavaScript-specific execution patterns.

It includes:

- classes
- `Map`
- `Set`
- arrays
- object spread
- default parameters
- `Promise`
- `async` and `await`
- error handling
- executable assertions

### Repository representation

`Repository` uses a JavaScript `Map` for branch storage.

A `Map` is useful when the application needs explicit key-value semantics rather than relying on object-property behavior.

### Reviewer storage

Approval calculations use `Set`.

A set is appropriate because a reviewer should normally count once, even if multiple approval records could otherwise produce duplicate names.

The conceptual operation is:

`reviewers → unique reviewer set`

---

## 19. JavaScript Asynchronous CI

The JavaScript implementation includes `runAsynchronousCheck()`.

It returns a `Promise` and uses `setTimeout()` to simulate CI jobs completing independently.

The example uses `Promise.all()`:

`Promise.all([...checks])`

This demonstrates a realistic application-level property of CI systems: multiple checks can execute independently and the pull request can wait for all required results.

If three jobs require approximately:

- 100 ms
- 50 ms
- 75 ms

parallel execution can finish when the slowest job finishes rather than requiring their delays to be added sequentially.

In the simulation this means approximately:

`max(100, 50, 75) = 100 ms`

rather than:

`100 + 50 + 75 = 225 ms`

Actual CI systems involve scheduling, queueing, worker availability, caching, dependencies, and network overhead, so this is only a conceptual model.

---

## 20. JavaScript Policy Engine

The JavaScript `PullRequestPolicyEngine` mirrors the core policy architecture.

It provides:

- current approval calculation
- current change-request detection
- required-check validation
- final policy evaluation

The implementation demonstrates that application code can treat repository policy as data plus deterministic evaluation logic.

This approach is useful for:

- internal developer portals
- repository-management automation
- compliance systems
- merge gates
- engineering dashboards
- audit systems

---

## 21. JavaScript Error Handling

The JavaScript program uses explicit errors for invalid operations such as:

- creating an existing branch
- referencing an unknown branch

The main asynchronous function catches fatal errors:

`main().catch(...)`

This prevents an unhandled rejection from silently ending the program without a clear diagnostic.

---

## 22. C++ Industry-Style Case Study

The C++ program models a payment-service repository.

The scenario is intentionally more structured than an isolated syntax demonstration.

The system contains:

- repository
- commits
- branches
- pull requests
- reviews
- review comments
- status checks
- code-owner rules
- security findings
- branch-protection policy
- policy evaluation
- audit logging structures
- merge strategies
- policy tests

The scenario follows a feature called payment validation.

The proposed implementation rejects negative amounts and negative taxes.

---

## 23. C++ Repository Architecture

The `Repository` class owns the repository's commits and branches.

Important operations include:

- `addCommit()`
- `createBranch()`
- `createInitialBranch()`
- `updateBranch()`
- `getCommit()`
- `getBranch()`

The branch stores a commit identifier rather than a full duplicated commit object.

This mirrors an important systems concept:

`branch → commit reference`

rather than:

`branch → independent copy of entire repository state`

---

## 24. C++ Pull Request Architecture

`PullRequest` stores the state needed to evaluate the proposed integration.

Important fields include:

- `number`
- `title`
- `author`
- `baseBranch`
- `headBranch`
- `baseCommitId`
- `headCommit`
- `draft`
- `merged`
- `closed`
- `branchIsUpToDate`
- `reviews`
- `comments`
- `statusChecks`
- `codeOwnerApprovals`

The object represents the workflow state rather than only the changed source files.

---

## 25. C++ Policy Engine

The `PullRequestPolicyEngine` is the central component of the case study.

It checks:

1. Whether the pull request is already merged.
2. Whether it is closed.
3. Whether it is still a draft.
4. Whether it targets the protected branch.
5. Whether the head branch is current.
6. Whether a change request is active.
7. Whether enough independent approvals exist.
8. Whether code-owner review is required and present.
9. Whether review conversations are resolved.
10. Whether required CI checks passed.
11. Whether a signed commit is required and present.

The result contains all blocking reasons.

This is a better operational interface than a single boolean because a developer needs actionable feedback.

For example, a result can identify:

- missing approval
- failed CI
- unresolved conversation

at the same time.

---

## 26. Data Structures Used in C++

The C++ case study deliberately uses several standard-library structures.

### `std::vector`

Used for ordered collections such as:

- reviews
- comments
- status checks
- security findings

### `std::set`

Used where unique sorted values are useful, such as:

- reviewers
- code owners
- approval identities

### `std::unordered_map`

Used for efficient lookup of:

- commits
- branches
- status-check names

### `std::map`

Used for deterministic filename ordering in commit file storage.

The choice of container should follow the required access pattern rather than habit.

---

## 27. Complexity Considerations

Suppose:

- `R` = number of review records
- `C` = number of comments
- `S` = number of status checks
- `F` = number of files

A straightforward review scan is approximately `O(R)`.

Unresolved-comment detection is approximately `O(C)`.

Status-check lookup can be close to `O(S)` when rebuilding the lookup structure during each evaluation.

Using a hash map for status checks can reduce individual name lookup toward average `O(1)` after indexing.

Code-owner evaluation in the simplified implementation is approximately:

`O(F × K)`

where `K` is the number of ownership rules.

Real repository platforms use substantially more sophisticated infrastructure, indexing, caching, and pattern matching.

---

## 28. Code Ownership

Code ownership connects paths to reviewers or teams responsible for particular areas.

Example conceptual rules include:

`payment.cpp → security-team`

`*.md → documentation-team`

If a pull request changes `payment.cpp`, the policy may require an eligible security reviewer.

This is useful in large organizations because no single reviewer can understand every part of a large codebase.

Code ownership can provide domain-specific review responsibility for:

- security-sensitive code
- infrastructure
- databases
- APIs
- authentication
- billing
- compliance-sensitive components

---

## 29. Branch Freshness

A pull request can become outdated when the base branch changes after the pull request was opened.

Example:

1. `main` points to commit `A`.
2. Alice creates a pull request against `A`.
3. Another change merges into `main`.
4. `main` now points to `B`.
5. Alice's pull request still references the older base.

A policy may require Alice's branch to be updated before merging.

The purpose is to ensure that the proposed change is evaluated against a sufficiently current base.

An important distinction is that "up to date" and "conflict-free" are related but not identical concepts. A workflow can require the branch to incorporate the latest base and can separately require the resulting state to be mergeable.

---

## 30. Merge Conflicts

A pull request can satisfy:

- approval requirements
- review requirements
- status checks

and still have a merge conflict.

A merge conflict means the changes cannot be integrated automatically under the selected integration strategy.

Conflicts often occur when two changes modify overlapping regions or when one change removes or restructures content another change depends on.

Resolving a conflict creates another version of the proposed change, which may affect the review state and may require new validation.

---

## 31. Draft Pull Requests

A draft pull request is useful when the author wants to share work before declaring it ready for integration.

Draft work can be used for:

- early architectural feedback
- incomplete implementation discussion
- exploratory work
- incremental development
- review of an approach before completion

The examples deliberately block a draft PR from merging under the configured policy.

The exact behavior of draft pull requests depends on the platform workflow and repository configuration.

---

## 32. Changes Requested

A reviewer can request changes instead of approving.

The policy engine treats a current change request as a blocker.

After the author changes the code, the review state and approval status may need to be reconsidered because the code under review has changed.

This demonstrates why review is stateful rather than simply a permanent checkbox.

---

## 33. Conversation Resolution

An unresolved conversation can indicate that an issue raised during review has not been addressed or explicitly closed.

A repository can require conversations to be resolved before merging.

This creates a workflow condition:

`unresolved comments = merge blocked`

The policy does not attempt to determine whether the underlying technical issue is objectively solved. It enforces the repository's defined workflow state.

---

## 34. Merge Strategies

The examples describe three common integration strategies.

### Merge commit

A merge commit preserves the branch relationship and records an explicit merge operation.

Advantages can include:

- preserving branch topology
- explicit integration history

Trade-offs can include:

- more complex history
- additional merge commits

### Squash

Squashing combines the pull request's changes into a consolidated commit.

Advantages can include:

- compact main-branch history
- easier high-level browsing

Trade-offs can include:

- individual development commits may not remain as separate commits on the target branch

### Rebase

Rebasing replays commits onto another base.

Advantages can include:

- linear history
- clean commit sequence

Trade-offs can include:

- rewritten commit identifiers
- history-rewriting implications
- greater care required when working with shared branches

The appropriate strategy depends on repository history requirements and team workflow.

---

## 35. Security Considerations

Pull-request workflows can reduce risk but do not automatically make code secure.

Important security concerns include:

### Secrets

Credentials should not be committed to source control.

Examples include:

- API keys
- database passwords
- private keys
- cloud credentials
- authentication tokens

If a secret is accidentally committed, deleting it from the latest file version may not remove it from repository history. Credential rotation is therefore important.

### Untrusted pull-request code

Automated workflows must be designed carefully when they execute code from untrusted branches.

Potential concerns include:

- access to secrets
- privileged tokens
- deployment credentials
- write permissions
- malicious build scripts

CI permissions should follow least privilege.

### Review bypass

Branch protection should prevent unauthorized ways of bypassing required review or status checks.

### Force pushes

Force pushing can rewrite history and complicate review traceability. Restricting force pushes on protected branches reduces this risk.

### Signed commits

Where identity and commit authenticity requirements justify it, signed commits can provide an additional verification signal.

Signed commits do not replace code review or security testing.

---

## 36. Common Mistakes

### Mistake 1: Treating approval as permanent

An approval may relate to a particular version of a pull request.

A later change can invalidate the context of the approval.

### Mistake 2: Counting the author's approval

Many review policies require independent review.

The educational implementations explicitly exclude the author from the independent approval count.

### Mistake 3: Ignoring CI status

A pull request can have excellent human review and still fail automated verification.

### Mistake 4: Checking only whether a check exists

A status check should be evaluated for the relevant commit.

A passing result from an older commit should not automatically validate a newer commit.

### Mistake 5: Treating branch protection as a substitute for review

Branch protection enforces workflow rules. It does not determine whether an implementation is technically correct.

### Mistake 6: Using only one security control

Secret scanning, static analysis, tests, review, access control, dependency controls, and runtime security address different risk categories.

### Mistake 7: Allowing excessive branch permissions

A protection policy is weakened if users can simply bypass it through unrestricted direct pushes or administrative permissions.

### Mistake 8: Ignoring merge conflicts

Passing checks and approvals do not necessarily mean that a branch can be integrated without resolving conflicts.

---

## 37. Edge Cases

### Empty or insignificant changes

A pull request may contain very little effective change. Automated policy should still evaluate the actual state.

### Binary files

Text diff tools do not fully explain many binary changes.

### Renames

A rename is more nuanced than treating one file as deleted and another as newly created.

### New commits after approval

New commits can invalidate review assumptions.

### Failed checks after approval

Human approval does not override required automated checks.

### Closed pull requests

A closed pull request should normally not be treated as mergeable.

### Draft pull requests

Draft status can intentionally prevent merge readiness.

### Multiple approvals from one reviewer

A policy should count eligible reviewers rather than blindly counting approval records.

### Concurrent changes

Two pull requests may both appear valid independently but interact in ways that require integration ordering or conflict resolution.

---

## 38. Limitations of the Educational Implementations

The implementations are intentionally self-contained and do not reproduce every behavior of a production Git hosting platform.

They simplify:

- Git object storage
- commit hashing
- branch ancestry
- merge-base calculation
- three-way merging
- rename detection
- binary diffs
- repository permissions
- organization membership
- CODEOWNERS syntax
- CI infrastructure
- webhook delivery
- review dismissal rules
- platform-specific branch-protection APIs
- deployment environments

The Python and JavaScript implementations use simplified commit identifiers.

The C++ implementation uses simplified repository state and merge evaluation rather than implementing a full Git engine.

These limitations keep the examples focused on the conceptual relationship between pull requests, review, approvals, automated checks, and branch policy.

---

## 39. Python, JavaScript, and C++ Comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Primary role | Policy engine and educational workflow | Application and asynchronous workflow model | Industry-style system case study |
| Main strength in this topic | Clear modeling and testing | Async CI and application behavior | Explicit architecture and data structures |
| Review representation | Classes and enums | Classes and objects | Classes and enums |
| Status checks | Simulated unit test and lint | Simulated asynchronous CI | Simulated unit test and static analysis |
| Security example | Regex-based secret scanner | Regex-based secret scanner | Regex-based secret scanner |
| Testing | `unittest` | Assertion-based test runner | Custom test runner |
| Collections | `dict`, `set`, lists | `Map`, `Set`, arrays | `map`, `set`, `unordered_map`, `vector` |
| Policy architecture | Dedicated policy engine | Dedicated policy engine | Dedicated policy engine |
| Async demonstration | Limited | `Promise` and `async`/`await` | Not central to the case study |

The three implementations are deliberately complementary.

---

## 40. Design Principles Demonstrated

### Separation of data and policy

A pull request stores state.

A policy determines whether that state is acceptable for merge.

Separating the two makes policy easier to test and modify.

### Deterministic policy evaluation

The same pull-request state and policy should produce the same result.

This makes the workflow auditable.

### Explicit failure reasons

Returning only "false" is operationally weak.

Returning specific blocking reasons helps developers fix the correct issue.

### Commit-specific validation

Approvals and automated checks should be associated with the version they evaluate.

### Least privilege

Protected branches and restricted permissions reduce unnecessary write capability.

### Defense in depth

No single control should be treated as sufficient for all risks.

---

## 41. Production Considerations

A production implementation of a pull-request governance system would typically need to address:

- authentication
- authorization
- repository permissions
- team membership
- audit trails
- webhook processing
- idempotency
- concurrent updates
- race conditions
- status synchronization
- branch ancestry
- merge-base computation
- conflict detection
- CI provider integration
- retry handling
- API rate limits
- caching
- persistence
- observability
- failure recovery
- security event logging

The critical design question is not simply "is the PR approved?"

A production merge decision can be modeled conceptually as:

`mergeable = workflow state ∧ review policy ∧ status policy ∧ branch state ∧ permission policy`

Each component must be evaluated against the correct current repository state.

---

## 42. Auditability

A controlled merge process should make it possible to determine:

- who opened the pull request
- what branch was targeted
- what commit was reviewed
- who approved it
- when approval occurred
- what checks passed
- which commit those checks evaluated
- whether conversations were unresolved
- what policy was applied
- who performed the merge

The C++ implementation includes an `AuditLog` structure to demonstrate this architectural concern, even though the example does not build a complete persistent audit subsystem.

Auditability becomes particularly important for regulated, security-sensitive, or high-impact systems.

---

## 43. Practical Pull-Request Review Sequence

A technically disciplined review can follow this sequence:

1. Understand the purpose of the pull request.
2. Check the scope of the change.
3. Inspect the diff.
4. Identify correctness risks.
5. Examine error handling.
6. Examine tests.
7. Check security-sensitive behavior.
8. Consider performance implications.
9. Consider compatibility and API effects.
10. Leave precise review comments.
11. Approve when the applicable review requirements are satisfied.
12. Re-review important changes added after the original approval.
13. Confirm required automated checks.
14. Confirm branch-policy requirements.
15. Merge using the repository's approved strategy.

This sequence is a workflow model, not a substitute for repository-specific policy.

---

## 44. Conceptual Merge Gate

The examples can be reduced to a logical model:

`eligible = open AND not draft`

`review_ok = sufficient_current_approvals AND no_current_change_request`

`checks_ok = every_required_check_passed_for_current_commit`

`conversation_ok = all_required_conversations_resolved`

`branch_ok = branch_is_current AND targets_protected_branch`

Then:

`merge_allowed = eligible AND review_ok AND checks_ok AND conversation_ok AND branch_ok`

Additional repository policies can add conditions such as:

- code-owner approval
- signed commit
- linear history
- deployment environment approval
- security scan
- dependency policy

The value of such a model is that each condition can be independently tested.

---

## 45. Key Distinctions

### Git versus pull request

Git provides distributed version control.

A pull request is a collaboration and integration workflow built around repository changes.

### Review versus approval

A review is an evaluation.

An approval is a particular review outcome.

### Approval versus merge permission

Approval alone does not necessarily grant merge permission.

Other branch-protection conditions can still block the merge.

### CI versus code review

CI provides automated validation.

Code review provides human examination.

### Branch protection versus security

Branch protection can enforce workflow controls, but security requires broader controls.

### Up-to-date branch versus conflict-free branch

A branch can be behind the target branch, and it can also have content conflicts. These are related but distinct conditions.

### Draft versus approved

A draft state can indicate that the author does not yet consider the pull request ready for integration, even if a reviewer has already commented or approved.

---

## 46. Implementation Correspondence

The Python implementation demonstrates:

- repository modeling
- branch modeling
- pull-request state
- review states
- approval counting
- stale approvals
- status checks
- code ownership
- security scanning
- branch policy
- automated policy tests

The JavaScript implementation demonstrates:

- object-oriented modeling
- `Map` and `Set`
- pull-request policy
- asynchronous CI jobs
- `Promise.all()`
- review state management
- security scanning
- executable assertions
- failure handling

The C++ implementation demonstrates:

- explicit domain classes
- strongly typed enumerations
- repository state
- policy evaluation
- code ownership
- status checks
- security findings
- merge-strategy modeling
- audit-log architecture
- complexity-aware data structures
- C++17 testing patterns
- explicit exception handling

Together, the implementations show the same domain from three programming perspectives without requiring an external service or package.

---

## 47. Practical Relevance

Pull-request workflows are used to control how software changes move from individual development branches into shared branches.

The same principles appear in:

- enterprise software development
- open-source projects
- internal engineering platforms
- infrastructure repositories
- security-sensitive systems
- data platforms
- web applications
- backend services
- mobile applications
- DevOps workflows

The central engineering principle is controlled integration: proposed changes should be inspectable, testable, attributable, and subject to the repository's defined acceptance rules before entering an important shared branch.

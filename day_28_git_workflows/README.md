# Git Workflows: Feature Branches, GitHub Flow, and Trunk-Based Development

## Topic Introduction

Git workflows define how source-code changes move from individual development into shared integration, review, testing, release, deployment, and recovery.

Git itself provides the version-control mechanisms. A workflow adds engineering conventions around those mechanisms.

This study covers three closely related approaches:

- Feature branch workflows
- GitHub Flow
- Trunk-based development

The implementations use three different languages to demonstrate the same engineering subject from different technical perspectives:

- Python provides a broad educational model with data classes, validation, graph traversal, policy objects, testing, and optional real Git execution in an isolated temporary repository.
- JavaScript demonstrates workflow automation concepts together with asynchronous CI behavior, promises, event-oriented execution, and executable workflow simulation.
- C++ presents a more structured industry-style case study using classes, strong data modeling, containers, validation, exception handling, algorithms, and a simulated e-commerce repository workflow.

The three approaches are not mutually exclusive. A real engineering organization may use short-lived feature branches, pull requests, protected `main`, automated CI, feature flags, and frequent integration at the same time.

---

## Fundamental Git Concepts

### Repository

A repository contains Git-managed project data and its version history.

A repository normally contains:

- commits
- references
- branches
- tags
- configuration
- objects representing project history

A local Git repository is distributed. Developers generally have their own complete or partially cloned copy of the repository history.

### Working Tree

The working tree is the collection of project files currently checked out on disk.

A developer typically moves changes through several states:

1. Working tree
2. Staging area
3. Commit
4. Remote repository

The staging area allows the developer to select exactly which changes belong to the next commit.

### Commit

A commit records a snapshot and references its parent commit or commits.

A simplified commit contains:

- an identifier
- author information
- a message
- parent commit references
- a reference to project content

A commit is therefore not simply a text description of a change. It is part of a directed history graph.

### Branch

A branch is a movable reference to a commit.

A useful conceptual model is:

`branch name -> commit`

When a new commit is created on the branch, the branch reference moves to the new commit.

Branches provide convenient names for lines of development, but they do not inherently represent independent repositories.

### Remote

A remote is a named reference to another repository location.

The conventional name `origin` is commonly used for the repository from which a project was cloned.

Typical commands include:

- `git remote -v`
- `git fetch origin`
- `git push origin main`

### Fetch

`git fetch` downloads information from a remote without directly changing the checked-out working tree.

It is useful when a developer wants to inspect remote changes before deciding how to integrate them.

### Pull

`git pull` normally combines fetching remote information with an integration operation.

Teams frequently prefer an explicit sequence such as `git fetch` followed by an intentional merge or rebase because the separate operations make the resulting history easier to reason about.

### Merge

A merge combines two lines of development.

If one branch contains commits that another branch does not contain, Git can sometimes move the target reference directly. This is a fast-forward.

When two histories have diverged, a merge can create a merge commit that records the combination of the two lines.

### Rebase

Rebase replays commits onto a different base.

For example, conceptually:

`A -- B -- C    main`

`      \`

`       D -- E  feature`

can become:

`A -- B -- C -- D' -- E'`

The apostrophes represent newly created commits. Rebase therefore changes commit identities.

This makes rebase powerful for organizing local history, but it requires care when commits are already shared with other developers.

### Pull Request

A pull request is a collaboration mechanism provided by Git hosting platforms.

A pull request normally identifies:

- source branch
- target branch
- proposed changes
- review comments
- automated checks
- approvals
- integration status

A pull request is not a Git object. It is a hosting-platform collaboration abstraction built around Git references and commits.

---

## The Commit Graph

Git history is naturally a graph.

A linear history can be represented as:

`A -> B -> C`

A branch can introduce another line:

`A -> B -> C`

`     \`

`      D -> E`

The Python and C++ implementations model commits as objects with parent references.

The Python `CommitGraph` class stores commits in a dictionary and branches in another dictionary. Its `ancestors()` method traverses parent relationships.

The C++ `RepositoryGraph` class uses standard-library containers to represent the same concept with stronger type structure.

The JavaScript `CommitGraph` uses `Map` and `Set` to demonstrate equivalent graph operations in an application-oriented runtime.

This graph model is important when understanding:

- merge bases
- branch divergence
- rebasing
- merge conflicts
- history inspection
- recovery
- release points

---

# Feature Branch Workflows

## Definition

A feature branch workflow isolates a logical change from the shared integration branch.

A typical lifecycle is:

1. Update the shared branch.
2. Create a short-lived feature branch.
3. Make a small logical change.
4. Commit the change.
5. Push the branch.
6. Open a pull request.
7. Run automated checks.
8. Review the change.
9. Resolve feedback.
10. Integrate the branch.
11. Remove the temporary branch.

A common naming convention is:

`feature/user-login`

Other useful prefixes include:

- `bugfix/`
- `hotfix/`
- `chore/`
- `docs/`
- `refactor/`
- `test/`

Branch naming conventions are team policy rather than fundamental Git requirements.

## Why Feature Branches Exist

Feature branches provide isolation.

Without isolation, several developers making unrelated changes directly in the same branch can make it difficult to identify:

- which changes belong together
- which change caused a failure
- which change requires review
- which change should be reverted

A branch can provide a natural boundary for a logical unit of work.

## Short-Lived Versus Long-Lived Branches

A short-lived branch generally diverges from the shared branch for a limited period.

A long-lived branch accumulates more divergence.

As divergence grows:

- conflicts can become more difficult
- assumptions about the current codebase become stale
- integration becomes larger
- testing becomes more expensive
- review becomes harder

This does not mean every feature must be completed in one commit. A feature can contain multiple small commits while still being integrated frequently.

---

# GitHub Flow

## Definition

GitHub Flow is a lightweight, main-centered workflow commonly organized around:

1. A continuously maintained primary branch.
2. A short-lived branch for a change.
3. A pull request.
4. Automated validation.
5. Review.
6. Integration.
7. Deployment or release.

The conceptual flow is:

`main -> feature branch -> pull request -> checks -> review -> merge -> deployment`

The JavaScript implementation models a `PullRequest` class containing:

- pull-request number
- source branch
- target branch
- title
- approvals
- check status
- merge state
- review comments

The C++ implementation incorporates the same concept into an industry-style workflow engine.

## GitHub Versus GitHub Flow

GitHub is a hosting and collaboration platform.

GitHub Flow is a workflow pattern.

Using GitHub does not automatically mean a project follows GitHub Flow.

A repository may use:

- release branches
- trunk-based development
- pull requests
- direct integration
- different merge policies

while still being hosted on GitHub.

---

# Trunk-Based Development

## Definition

Trunk-based development emphasizes frequent integration into one shared trunk, commonly called `main` or `trunk`.

Two broad patterns are possible.

### Direct Integration

Developers integrate small changes directly into the trunk under the organization's controls.

### Very Short-Lived Branches

Developers use branches for small changes, validate them, integrate them quickly, and remove them.

The important property is frequent integration rather than the complete absence of branches.

## Supporting Practices

Trunk-based development commonly benefits from:

- fast CI
- reliable automated tests
- small changes
- frequent synchronization
- feature flags
- automated deployment
- rapid feedback
- strong recovery procedures

Trunk-based development does not inherently mean:

- no code review
- no tests
- no security checks
- no branch protection
- direct deployment of every untested commit

Those are separate engineering decisions.

---

# Feature Flags

Feature flags separate code integration from feature exposure.

For example, application code can contain a new capability while the flag remains disabled.

Conceptually:

`new-search = false`

means the new implementation may exist without being exposed to users.

The Python, JavaScript, and C++ implementations all demonstrate feature-flag behavior.

## Benefits

Feature flags can support:

- gradual rollout
- controlled activation
- emergency disabling
- integration of incomplete capabilities
- deployment independently of user exposure

## Risks

Feature flags create operational and technical complexity.

Long-lived flags can cause:

- additional conditional branches
- configuration confusion
- incomplete testing combinations
- obsolete code
- difficult debugging

Production feature flags should therefore have:

- an owner
- clear naming
- access controls where necessary
- monitoring
- testing
- lifecycle management
- removal criteria

---

# Pull Requests and Quality Gates

A pull request can act as a controlled integration boundary.

A mature workflow may require:

- automated tests
- linting
- static analysis
- security checks
- build validation
- dependency checks
- required reviews

The Python `QualityGate` class models these requirements.

The JavaScript `QualityGate` class demonstrates the same idea in a dynamic runtime.

The C++ `QualityGate` class demonstrates strongly typed validation.

A simplified rule is:

`mergeable = tests_passed AND lint_passed AND security_passed AND approvals >= required`

This is intentionally simplified. Production systems may have many more conditions.

---

# Branch Protection

A protected primary branch can prevent unauthorized or unsafe changes.

Typical controls can include:

- required pull requests
- required approvals
- required status checks
- restrictions on direct pushes
- restrictions on force pushes
- required signed commits
- required linear history
- restrictions on branch deletion
- administrator bypass policies

Branch protection is not a property of Git itself. It is normally implemented by the hosting platform or repository management system.

---

# Merge, Rebase, and Squash

## Merge

Merge preserves the fact that two histories were integrated.

Advantages include:

- explicit branch topology
- preservation of the original commit structure
- clear representation of parallel development

A non-fast-forward merge can create a merge commit.

## Rebase

Rebase replays commits onto a different base.

Advantages can include:

- a linear-looking history
- easier reading of local development history
- reduced unnecessary merge commits

The major technical consequence is that rebased commits receive new identities.

A developer should be cautious when rebasing commits that others already depend on.

## Squash

Squashing combines multiple commits into a smaller integration history.

For example, a branch might contain:

- `Add search input`
- `Fix search validation`
- `Fix search test`
- `Correct typo`

A project may choose to integrate these as one logical commit.

Squashing can make the primary branch easier to read, but it removes the individual branch commits from the integrated history.

---

# Merge Conflicts

A conflict occurs when Git cannot safely determine how competing changes should be combined automatically.

A simplified three-way model uses:

- base
- ours
- theirs

Suppose:

Base:

`timeout=30`

Ours:

`timeout=60`

Theirs:

`timeout=120`

Both sides changed the same base content differently.

The Python, JavaScript, and C++ implementations contain simplified conflict detection to demonstrate this principle.

Real Git performs more sophisticated line-oriented and tree-level processing.

## Conflict Resolution

A real conflict-resolution process generally involves:

1. Inspecting repository status.
2. Identifying affected files.
3. Understanding the base and competing changes.
4. Editing the files.
5. Running tests.
6. Staging the resolved files.
7. Continuing the merge or rebase.

Useful commands include:

- `git status`
- `git diff`
- `git add <file>`
- `git merge --continue`
- `git rebase --continue`
- `git merge --abort`
- `git rebase --abort`

The correct resolution is determined by intended application behavior, not by automatically selecting "ours" or "theirs".

---

# Python Implementation

The Python script is designed as a comprehensive study program rather than a minimal command reference.

## Core Classes

### `Commit`

Represents a commit with:

- commit ID
- message
- author
- parents
- changed files

### `Branch`

Represents a branch reference and records whether the simulated branch is protected.

### `PullRequest`

Models:

- source branch
- target branch
- approvals
- CI state
- merge state

### `CommitGraph`

Models Git's graph structure.

It implements:

- repository initialization
- commit creation
- branch creation
- ancestor traversal
- common-ancestor discovery
- graph inspection

### `FeatureFlagService`

Demonstrates the separation between code integration and runtime activation.

### `QualityGate`

Models CI and review requirements.

### `BranchPolicy`

Represents workflow rules such as:

- maximum branch age
- pull-request requirements
- CI requirements
- branch cleanup
- linear-history requirements

### `DeliveryMetrics`

Models operational measurements such as:

- deployment frequency
- lead time
- change failure rate
- recovery time

## Real Git Demonstration

The Python script has an optional `--real-git-demo` mode.

It creates a temporary repository and executes real Git commands in that isolated directory.

The demonstration:

1. Initializes a repository.
2. Creates `main`.
3. Configures a temporary identity.
4. Creates an initial commit.
5. Creates a feature branch.
6. Creates a feature commit.
7. Displays the graph.
8. Merges the feature branch.
9. Displays the final graph.
10. Checks repository status.

The temporary-directory design prevents the demonstration from modifying the user's ordinary project repository.

Run the normal study program with:

`python git_workflows.py`

Run only the tests with:

`python git_workflows.py --tests-only`

Run the isolated real Git demonstration with:

`python git_workflows.py --real-git-demo`

The real Git demonstration requires the `git` executable to be available on the system.

---

# JavaScript Implementation

The JavaScript file focuses on application-level modeling and asynchronous automation.

## JavaScript-Specific Concepts

JavaScript is particularly useful for demonstrating CI orchestration because asynchronous operations are common in automation systems.

The implementation demonstrates:

- classes
- `Map`
- `Set`
- arrays
- promises
- `async` functions
- `await`
- error handling
- `Promise.all`
- `Promise.allSettled`
- command-line execution
- reusable validation functions

## Asynchronous CI

The `runCICheck()` function simulates a CI check using a promise.

Several checks can run concurrently:

- unit tests
- linting
- security scanning

`Promise.all()` waits for all operations to succeed but rejects when one rejects.

`Promise.allSettled()` collects the result of every operation.

This distinction matters in CI orchestration.

A CI system may need to know:

- which checks passed
- which checks failed
- whether independent checks completed
- whether cleanup is necessary
- whether retry is appropriate

A production CI orchestrator may add cancellation, retry policies, timeouts, artifact storage, logging, and dependency ordering.

---

# C++ Case Study

## Problem Being Solved

The C++ program models a workflow system for an e-commerce organization.

The modeled organization has:

- a protected `main` branch
- feature branches
- pull requests
- required approvals
- automated quality checks
- feature flags
- releases
- production hotfixes
- database migration stages
- monorepo change-impact analysis
- operational delivery metrics

The purpose is to demonstrate how Git workflow concepts interact with real software engineering controls.

## System Architecture

The major components are:

### `Commit`

Stores:

- commit ID
- message
- author
- parent IDs
- changed files

### `Branch`

Stores:

- branch name
- current head
- protection state

### `RepositoryGraph`

Provides:

- repository initialization
- commit creation
- branch creation
- branch lookup
- ancestor traversal
- common-ancestor discovery
- graph printing

### `PullRequest`

Models:

- source branch
- target branch
- title
- approvals
- CI status
- merge status

### `QualityGate`

Validates:

- tests
- lint
- security scanning
- approval count

### `FeatureFlagService`

Stores named boolean feature states and provides default handling for missing flags.

### `WorkflowEngine`

Coordinates:

- pull-request creation
- required approval configuration
- mergeability
- integration

### `Release`

Associates a release version with a commit.

### `Hotfix`

Models an urgent production correction associated with a source release commit.

### `DeliveryMetrics`

Validates operational measurements.

---

# C++ Case Study Workflow

The case study starts by creating an e-commerce repository.

The simulated repository contains:

- `services/catalog/catalog.cpp`
- `services/payments/payment.cpp`

A feature branch named:

`feature/payment-validation`

is created from `main`.

Two commits are then created:

1. `Add payment input validation`
2. `Add payment validation tests`

This demonstrates small logical commits on a feature branch.

A pull request is created from the feature branch into `main`.

The quality gate initially requires:

- tests passed
- lint passed
- security scan passed
- two approvals

Only one approval is initially present, so the gate blocks integration.

After the second approval is added, the gate passes.

The pull request is then merged through the workflow engine.

---

# Monorepo Change Impact

The C++ case study includes path-based service analysis.

For example:

`services/payments/payment.cpp`

belongs to the payments service.

`services/catalog/catalog.cpp`

belongs to the catalog service.

The `affectedServices()` function extracts service names from changed paths.

This is a simplified model of path-based CI.

A real monorepo often requires dependency-aware analysis because one component can affect another without directly changing files inside that component.

Possible production mechanisms include:

- dependency graphs
- build graphs
- path ownership
- cached builds
- selective test execution
- service-level deployment boundaries

---

# Releases and Tags

The C++ `Release` class associates a version with a commit.

For example:

`v2.4.0`

can identify a specific release point.

Tags are useful because they provide stable names for release commits.

A release workflow should establish:

- which commit is released
- how the version is named
- which checks must pass
- where the artifact is stored
- which deployment environment receives it
- how deployment is verified
- how recovery is performed

Git tags themselves do not implement deployment.

---

# Hotfixes

A hotfix is an urgent correction for an already released or production system.

The exact branch strategy depends on the release architecture.

A main-centered project may create a hotfix from an appropriate production point, validate it, integrate it, and deploy it.

A project with release branches may need the same fix to reach multiple active lines.

The important technical concern is preventing the fix from disappearing from the next release.

A production hotfix process should account for:

- source commit
- validation
- deployment
- monitoring
- release identification
- propagation to active development branches
- recovery if the fix introduces a regression

---

# Database Migration Considerations

Source-code history and database state are different systems.

A database migration can therefore create compatibility problems even when Git integration is clean.

The C++ case study demonstrates an expand-and-contract sequence:

1. Expand the schema.
2. Deploy backward-compatible application code.
3. Migrate data.
4. Switch application behavior.
5. Remove obsolete schema later.

This approach can reduce deployment coupling between application code and persistent data.

A Git workflow cannot by itself make a database migration safe.

A rollback strategy must consider:

- application binaries
- source versions
- database schema
- migrated data
- backward compatibility
- irreversible data transformations

---

# Important Distinctions

## Git Versus GitHub

Git is a distributed version-control system.

GitHub is a hosting and collaboration platform.

Git provides mechanisms such as:

- commits
- branches
- merges
- rebases
- tags
- remotes

A hosting platform can provide:

- pull requests
- branch protection
- review interfaces
- CI integration
- deployment integrations
- repository permissions

## Feature Branch Workflow Versus GitHub Flow

Feature branch workflow is a broader pattern based on isolating work in branches.

GitHub Flow is a particular lightweight main-centered workflow built around pull requests and frequent integration.

A project can use feature branches without following every convention associated with GitHub Flow.

## GitHub Flow Versus Trunk-Based Development

Both can use:

- `main`
- short-lived branches
- pull requests
- automated testing
- feature flags
- continuous deployment

The main conceptual difference concerns integration frequency and branch lifetime.

GitHub Flow commonly emphasizes a main-centered PR lifecycle.

Trunk-based development emphasizes frequent integration into the shared trunk and minimizing divergence.

These practices can overlap substantially.

---

# Edge Cases

## Empty Branch Names

An empty branch name is invalid.

The Python, JavaScript, and C++ validators reject it.

## Duplicate Branches

Creating a branch that already exists should fail rather than silently replace the existing reference.

## Unknown Source Branch

A branch cannot be safely created from a branch that does not exist in the modeled repository.

## Pull Request Against Itself

A pull request where source and target are identical is rejected in the C++ and JavaScript workflow models.

## Insufficient Approvals

A pull request can have passing tests and still remain blocked because the required number of approvals has not been reached.

## Failed CI

Passing review does not automatically make a pull request mergeable when required CI checks are failing.

## Missing Feature Flag

The implementations return a configurable default when a feature flag is not present.

The default in the examples is generally `false`.

## Invalid Metrics

Negative deployment frequency, negative lead time, negative recovery time, or a failure rate outside the interval from `0` through `1` is rejected.

## Merge Conflicts

A conflict requires human understanding when the automated merge mechanism cannot safely determine the intended result.

---

# Exceptions and Failure Handling

The Python implementation uses exceptions such as:

- `ValueError`
- `RuntimeError`

The JavaScript implementation uses:

- `Error`
- `TypeError`
- `RangeError`

The C++ implementation uses standard exceptions such as:

- `std::invalid_argument`
- `std::out_of_range`
- `std::runtime_error`

The important principle is that invalid workflow state should not silently produce an apparently successful result.

Examples include:

- nonexistent branch
- duplicate branch
- empty commit message
- invalid approval count
- invalid feature flag name
- failed quality gate
- invalid release information

---

# Debugging Git Workflow State

When a workflow behaves unexpectedly, inspecting repository state should come before making additional changes.

Useful commands include:

`git status`

Shows current state, branch information, staged changes, and unresolved operations.

`git branch --show-current`

Shows the current branch.

`git log --oneline --decorate --graph --all`

Displays recent history and branch references.

`git remote -v`

Displays configured remotes.

`git fetch --prune`

Updates remote information and removes stale remote-tracking references.

`git diff`

Shows unstaged changes.

`git diff --staged`

Shows staged changes.

`git reflog`

Shows local movement of references.

## Reflog

Reflog is particularly useful for investigating local history after operations such as:

- reset
- rebase
- branch movement
- certain merge operations

It can help identify previous commit positions that are no longer referenced by a branch name.

Recovery depends on the repository state and object availability.

---

# Rebase Safety

Suppose the history is:

`A -- B -- C    main`

`     \`

`      D -- E  feature`

After rebasing the feature onto `C`, the conceptual result is:

`A -- B -- C -- D' -- E'`

The replayed commits are new objects.

This means a rebase is not merely a visual rearrangement.

When a branch has already been shared, rebasing can require a force update of the remote branch.

A commonly safer command is:

`git push --force-with-lease`

The `--force-with-lease` form provides protection against overwriting remote movement that the local repository has not observed.

It does not eliminate all risks associated with history rewriting.

---

# Common Mistakes

## Long-Lived Feature Branches

Long-lived branches can accumulate divergence and increase integration complexity.

## Large Pull Requests

Large changes can be difficult to review and can make failures harder to isolate.

## Skipping CI

Skipping automated validation increases the probability that incorrect changes reach shared branches.

## Directly Modifying Protected Code

Direct changes can bypass review and automated controls.

## Rewriting Shared History

Rebase and other history-rewriting operations can invalidate references used by other developers.

## Committing Secrets

Secrets committed to Git can remain in repository history.

Credential rotation is important after exposure.

## Stale Branches

Old branches can make active work harder to identify and maintain.

## No Recovery Procedure

A deployment system should have a defined response to failed releases.

## Feature Flag Accumulation

Unused flags increase code and configuration complexity.

## Treating Commands as Magic

Git commands should be selected based on repository state and the intended result.

---

# Performance Considerations

Git workflow performance should be evaluated at multiple levels.

## Local Git Operations

Repository size can affect:

- clone time
- fetch time
- object traversal
- history inspection
- certain merge and rebase operations

Large generated artifacts and binaries can create unnecessary repository growth.

## CI Performance

Important measurements include:

- checkout time
- dependency installation
- compilation
- test execution
- static analysis
- security scanning
- artifact creation
- deployment

Fast feedback is valuable because developers otherwise remain blocked while waiting for validation.

## Parallel CI

Independent checks can run concurrently.

The JavaScript implementation demonstrates this with promises.

A real pipeline can parallelize independent work such as:

- linting
- unit tests
- static analysis

while preserving ordering for dependent tasks.

## Monorepo Optimization

Large repositories may benefit from:

- path-based builds
- dependency graphs
- build caching
- selective testing
- incremental compilation
- artifact reuse

Path-based filtering alone can be insufficient when components have dependencies on each other.

---

# Security Considerations

Git workflows are part of software supply-chain security.

Important controls include:

- protected primary branches
- required reviews
- required CI checks
- restricted administrative permissions
- protected deployment environments
- secure credential handling
- dependency validation
- CI workflow review
- artifact integrity
- audit logging

## Secrets

Do not commit:

- passwords
- API tokens
- private keys
- database credentials
- cloud credentials

If a secret is accidentally committed, removing it from the newest file version is not enough.

Historical repository objects may still contain the value.

The exposed credential should generally be revoked or rotated.

## CI Security

CI workflows can possess powerful permissions.

A malicious or compromised pull request can become dangerous if untrusted code is given access to sensitive credentials.

Workflow design should distinguish between:

- trusted code
- untrusted pull-request code
- secrets
- deployment credentials
- privileged operations

---

# Implementation Considerations

## Python

Python provides:

- rapid modeling
- readable classes
- dictionaries and sets
- convenient testing
- easy subprocess execution

Its dynamic typing makes it concise, but invalid data must be validated carefully.

The Python implementation uses data classes for structured domain objects and explicit validation methods for workflow rules.

## JavaScript

JavaScript provides:

- dynamic object modeling
- `Map`
- `Set`
- promises
- asynchronous execution
- event-oriented application patterns

It is especially suitable for demonstrating CI orchestration behavior where multiple tasks execute asynchronously.

The JavaScript implementation uses `Promise.all()` and `Promise.allSettled()` to illustrate two different coordination strategies.

## C++

C++ provides:

- strong static typing
- deterministic resource behavior
- standard containers
- explicit class design
- efficient graph traversal
- low-level control

The C++ case study uses:

- `std::map`
- `std::set`
- `std::unordered_set`
- `std::unordered_map`
- `std::vector`
- `std::optional`
- exception handling
- classes
- enumerations

This makes the C++ version useful for studying how a workflow model can become a structured system component.

---

# Complexity Considerations

The repository graph implementation uses graph traversal for ancestor discovery.

For a graph with:

- `V` reachable commits
- `E` parent edges

a standard traversal has approximately:

`O(V + E)`

time complexity.

Because ordinary commits normally have one parent and merge commits usually have a small number of parents, `E` is generally proportional to the number of commits in the traversed history.

The implementations use sets to avoid repeatedly processing the same commit.

## Branch Lookup

Map-based branch lookup is typically logarithmic in the number of branches in the C++ `std::map` implementation.

JavaScript's `Map` and Python dictionaries provide average-case constant-time lookup under normal hash-table assumptions.

These complexity characteristics matter when workflow tooling grows from a small project to a large repository platform.

---

# Advanced Workflow Design

A mature software delivery workflow can be represented as a control chain:

`Developer change`

then

`Local validation`

then

`Pull request or controlled integration`

then

`Automated quality gates`

then

`Review where required`

then

`Protected integration`

then

`Build artifact`

then

`Deployment`

then

`Monitoring`

then

`Recovery or continued operation`

Each stage answers a different engineering question.

## Local Validation

Can the developer detect obvious errors before sharing the change?

## CI

Does the shared automation confirm that required checks pass?

## Review

Has another authorized person inspected the proposed change when review is required?

## Branch Protection

Can unauthorized changes bypass the integration controls?

## Deployment

Can a validated artifact be delivered reproducibly?

## Monitoring

Can the organization detect unexpected behavior?

## Recovery

Can the organization restore service or correct the release when problems occur?

---

# Workflow Policy Design

A workflow policy can specify:

- maximum branch age
- pull-request requirement
- required CI
- approval requirements
- branch protection
- history rules
- branch cleanup
- release procedures
- hotfix procedures

Policy should be treated as an engineering control rather than as a collection of commands.

The Python and JavaScript implementations model policy objects with validation.

The important idea is that workflow rules should be explicit enough to be understood and, where practical, automated.

---

# Measuring Workflow Performance

Operational measurements can include:

## Deployment Frequency

How often deployments occur during a defined measurement period.

## Lead Time

The elapsed time between an appropriate starting point for a change and its delivery.

The precise definition must be consistent within the measurement system.

## Change Failure Rate

The proportion of delivered changes associated with a defined failure condition.

## Recovery Time

The elapsed time needed to restore normal operation after a failure.

These measurements should always be interpreted with:

- population
- measurement period
- definitions
- data collection method
- exclusions
- environmental context

A single measurement does not describe every characteristic of a development organization.

---

# Database and Deployment Coordination

Database changes require special care because source code can be replaced while persistent data remains.

A backward-compatible deployment sequence can use:

1. Expand.
2. Deploy compatibility code.
3. Migrate data.
4. Switch behavior.
5. Contract.

The principle is to avoid requiring application and database state to change incompatibly at exactly the same moment.

This is particularly relevant to trunk-based development because frequent integration increases the need for application versions to coexist safely during deployment transitions.

---

# Production Considerations

A production-ready Git workflow should define:

- branch permissions
- review requirements
- CI requirements
- artifact creation
- release identification
- deployment controls
- secret management
- monitoring
- rollback or roll-forward procedures
- hotfix handling
- database migration procedures
- audit requirements

A branch strategy alone does not provide production safety.

The workflow must be integrated with the broader software delivery architecture.

---

# Practical Command Sequence

A common short-lived branch sequence can look like:

`git switch main`

`git pull --ff-only origin main`

`git switch -c feature/account-validation`

`git add <files>`

`git commit -m "Add account validation"`

`git push -u origin feature/account-validation`

The developer then opens the pull request through the hosting platform.

After integration:

`git switch main`

`git pull --ff-only origin main`

`git branch --delete feature/account-validation`

The exact integration strategy depends on repository policy.

---

# Git Command Roles

| Command | Primary purpose |
|---|---|
| `git status` | Inspect current repository state |
| `git switch` | Change branches or create a branch |
| `git add` | Stage changes |
| `git commit` | Record a snapshot |
| `git fetch` | Download remote history information |
| `git pull` | Fetch and integrate remote changes |
| `git push` | Publish local references and commits |
| `git merge` | Combine histories |
| `git rebase` | Replay commits onto a different base |
| `git log` | Inspect commit history |
| `git diff` | Inspect content differences |
| `git reflog` | Inspect local reference movement |
| `git tag` | Create named references for releases |
| `git branch` | Inspect and manage branches |

---

# Practical Learning Exercises

1. Create a feature branch from an updated `main`.
2. Make two small logical commits.
3. Open a pull request and identify its required checks.
4. Create a three-way merge conflict.
5. Resolve the conflict based on intended application behavior.
6. Compare merge and rebase histories.
7. Introduce a feature flag for incomplete functionality.
8. Design a branch-age policy.
9. Design CI stages for a pull request.
10. Define required review rules.
11. Design a production hotfix procedure.
12. Explain how a database migration affects deployment order.
13. Use `git reflog` to investigate a mistaken reset.
14. Measure branch lifetime.
15. Measure CI feedback time.
16. Identify which checks can execute concurrently.
17. Identify which checks require earlier build artifacts.
18. Design a monorepo path-impact mechanism.
19. Define a release-tagging policy.
20. Define how a failed production deployment is recovered.

---

# Implementation Mapping

| Concept | Python | JavaScript | C++ |
|---|---|---|---|
| Commit model | `Commit` | `Commit` | `Commit` |
| Branch model | `Branch` | `Branch` | `Branch` |
| Commit graph | `CommitGraph` | `CommitGraph` | `RepositoryGraph` |
| Branch validation | `BranchNameValidator` | `BranchNameValidator` | `BranchNameValidator` |
| Pull requests | `PullRequest` | `PullRequest` | `PullRequest` |
| Quality gates | `QualityGate` | `QualityGate` | `QualityGate` |
| Feature flags | `FeatureFlagService` | `FeatureFlagService` | `FeatureFlagService` |
| Workflow policy | `BranchPolicy` | `BranchPolicy` | Workflow engine |
| Release modeling | Release concepts | `Release` | `Release` |
| Hotfix modeling | Hotfix concepts | `Hotfix` | `Hotfix` |
| CI simulation | Pipeline model | Async promises | Workflow model |
| Graph traversal | Ancestor traversal | Ancestor traversal | Ancestor traversal |
| Testing | `unittest` | Custom assertions | Custom test utility |
| Real Git execution | Optional temporary repository | Not required | Not required |

---

# Technical Takeaways

A Git workflow has several independent dimensions.

Branch structure determines how changes diverge.

Integration policy determines how changes become shared.

Pull requests provide a review mechanism.

CI provides automated validation.

Branch protection controls permissions around sensitive integration points.

Feature flags can separate code integration from runtime exposure.

Release processes identify what is delivered.

Deployment automation determines how validated artifacts reach environments.

Monitoring determines how the organization detects unexpected behavior.

Recovery procedures determine how failures are handled.

These mechanisms should be designed together rather than treated as independent Git commands.

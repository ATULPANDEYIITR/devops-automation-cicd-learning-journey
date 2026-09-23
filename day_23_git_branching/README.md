# Git Branching: Branches, checkout, switch, merge

## Introduction

Git branching is the mechanism used to maintain multiple lines of development within the same repository. A branch allows work to progress independently from another branch while preserving a connected commit history.

The central idea is simple: a Git branch is a movable reference to a commit. It is not a complete copy of the repository.

The three implementations in this repository approach the subject from different directions:

- The Python implementation builds a detailed repository model and demonstrates branching mechanics, commit graphs, fast-forward merges, three-way merges, conflicts, detached HEAD, branch deletion, and validation.
- The JavaScript implementation models the same concepts while emphasizing objects, functional operations, asynchronous pre-merge checks, and application-level workflow behavior.
- The C++ implementation develops an industry-style service-development case study using classes, maps, queues, sets, validation, merge algorithms, and explicit error handling.

The implementations simulate Git's concepts rather than executing the Git command-line program.

---

## Fundamental Git concepts

### Repository

A Git repository contains the information needed to track the history of a project.

The repository includes commits, references such as branches, and other internal Git objects and metadata.

A repository may exist locally on a developer's computer and can also be connected to remote repositories.

### Commit

A commit records a version of the project's tracked content together with metadata and parent relationships.

A normal commit has one parent:

`A -> B -> C`

Here, B is based on A, and C is based on B.

A merge commit can have two or more parents:

`A -> B`
and
`A -> C`

followed by a merge commit whose parents are B and C.

The parent relationship creates the commit graph that allows Git to determine ancestry.

### Branch

A branch is a named reference to a commit.

Suppose a repository contains:

`main -> C`

The branch named `main` points to commit C.

If a new branch is created at C:

`main -> C`

`feature -> C`

Both names point to the same commit.

When a new commit D is created while `feature` is checked out:

`main -> C`

`feature -> D`

Only the feature branch moves.

This is why branch creation is lightweight.

### HEAD

`HEAD` identifies the current checkout position.

When a normal branch is checked out, HEAD points to that branch:

`HEAD -> main -> C`

If `main` receives a new commit D:

`HEAD -> main -> D`

HEAD therefore follows the branch reference.

### Working tree

The working tree is the set of files currently checked out for editing.

It is the version of the project that the developer is actively working with.

### Staging area

The staging area records changes selected for the next commit.

A simplified workflow is:

`working tree -> staging area -> commit`

The commands normally associated with these stages are:

`git add`

followed by:

`git commit`

The branching topic is closely connected to this workflow because commits are the points that branches reference.

---

## Creating branches

A traditional branch creation command is:

`git branch feature`

This creates the branch but does not switch to it.

If the current commit is C, the result is:

`main -> C`

`feature -> C`

To create and switch to a branch using the modern branch-oriented command:

`git switch -c feature`

This performs two operations:

1. Create the branch.
2. Make that branch the current branch.

The older equivalent is:

`git checkout -b feature`

The Python, JavaScript, and C++ implementations model branch creation by creating a new branch reference at the current commit.

---

## Switching branches

The modern command for switching an existing branch is:

`git switch main`

For example:

`git switch feature/login`

This moves HEAD from the current branch to `feature/login` and updates the working tree to the commit referenced by that branch.

The older multi-purpose command is:

`git checkout feature/login`

Both commands can switch branches.

The distinction is primarily about command design and clarity. `git switch` is specifically intended for branch switching, while `git checkout` historically performs several different operations.

---

## `checkout` and `switch`

### Existing branch

Modern form:

`git switch main`

Older form:

`git checkout main`

### Create and switch

Modern form:

`git switch -c feature/login`

Older form:

`git checkout -b feature/login`

### Detached HEAD

Modern form:

`git switch --detach <commit>`

Older form:

`git checkout <commit>`

The JavaScript implementation explicitly models both concepts through `switchBranch()` and `checkout()`.

The Python implementation similarly distinguishes the branch-oriented `switch()` behavior from the more general `checkout()` behavior.

---

## Branch divergence

Branches diverge when each branch receives commits that the other branch does not contain.

For example:

`A -- B -- C    main`

and:

`       \-- D -- E    feature`

The branches share A and B but then develop independently.

The main branch contains C.

The feature branch contains D and E.

Neither C nor E is automatically present in the other branch.

This divergence is what makes merging necessary.

The Python, JavaScript, and C++ implementations construct this situation explicitly.

---

## Fast-forward merge

A fast-forward merge occurs when the current branch is an ancestor of the branch being merged.

Suppose the history is:

`A -- B -- C    feature`

and:

`A -- B        main`

If `main` merges `feature`, no separate merge commit is required.

Git can simply move the `main` reference from B to C:

`A -- B -- C    main, feature`

This is called a fast-forward because the branch pointer moves forward through existing history.

The Python implementation demonstrates this with the `merge()` method.

The JavaScript implementation detects the same condition through `isAncestor()`.

The C++ case study also tests fast-forward behavior as part of its self-tests.

---

## Three-way merge

A three-way merge is required when the two branches have diverged.

Suppose the history is:

`       C -- D    main`

`A -- B`

`       E -- F    feature`

The common ancestor is B.

The merge operation considers:

- the common ancestor B
- the current branch tip D
- the target branch tip F

Git determines what changed from B to D and what changed from B to F.

It then attempts to combine those changes.

This is different from simply comparing the final versions of D and F because the common ancestor establishes what each side actually changed.

The Python implementation contains an explicit `find_merge_base()` method and uses the base, current commit, and target commit during merge processing.

The JavaScript implementation implements the same three-way reasoning.

The C++ implementation uses ancestor traversal and a merge-base search to model the same architectural mechanism.

---

## Merge commits

If a merge cannot be represented as a fast-forward, Git can create a merge commit.

A merge commit normally has two parents.

For example:

`A -- B -- C`

with another branch:

`     \-- D -- E`

can result in:

`A -- B -- C -- M`

`     \-- D -- E --/`

M has C and E as parents.

The merge commit records the integration point between the two histories.

The Python and JavaScript repository models store multiple parents in a commit.

The C++ `Commit` structure contains a `vector<string>` for parents, allowing ordinary commits and merge commits to be represented using the same data structure.

---

## Merge conflicts

A merge conflict occurs when Git cannot determine a single correct result from the changes made on both sides.

Consider a base file containing:

`mode=development`

The feature branch changes it to:

`mode=feature`

The main branch changes it to:

`mode=production`

Both branches changed the same content differently.

Git cannot infer whether the final version should contain the feature value, production value, or some combination.

A conflict therefore requires a human or an explicitly designed resolution process.

The Python implementation represents an unresolved conflict using markers conceptually similar to:

`<<<<<<< CURRENT`

`=======`

`>>>>>>> TARGET`

The JavaScript and C++ implementations model the same situation.

---

## Conflict resolution

A conflict-resolution workflow normally involves:

1. Inspecting the conflict.
2. Determining the intended final content.
3. Editing the affected file.
4. Staging the resolved file.
5. Completing the merge commit.
6. Testing the result.

The exact commands commonly involved include:

`git status`

`git add <file>`

`git commit`

The Python implementation permits explicit resolutions through the `conflict_resolutions` argument.

The JavaScript implementation accepts a resolution object.

The C++ implementation accepts a map of resolved file contents.

These approaches represent the same conceptual operation while allowing each language to demonstrate its own data structures.

---

## Aborting a merge

When a merge is in progress and the developer decides not to continue, Git provides:

`git merge --abort`

This attempts to return the working state to what it was before the merge began.

The educational implementations focus on the mechanics of conflict detection and resolution rather than reproducing every internal state transition required for a complete `git merge --abort` implementation.

---

## Detached HEAD

Normally, HEAD points to a branch:

`HEAD -> main -> C`

A detached HEAD occurs when HEAD points directly to a commit:

`HEAD -> C`

There is no branch name between HEAD and the commit.

This is useful for inspecting historical versions or temporarily testing an older state.

For example:

`git switch --detach <commit>`

or:

`git checkout <commit>`

If meaningful work is created while HEAD is detached, it should be preserved by creating a branch pointing to that work before the reference becomes difficult to locate.

The Python, JavaScript, and C++ implementations explicitly represent detached HEAD using a separate commit reference rather than a branch name.

---

## Branch deletion

A completed branch can be removed with:

`git branch -d feature`

The lowercase `-d` form performs a safety check intended to prevent accidental deletion of an unmerged branch.

Forced deletion uses:

`git branch -D feature`

The forced form should be used intentionally because the branch reference may be the easiest way to locate commits that have not been integrated elsewhere.

Deleting a branch does not mean that all of its commits are immediately destroyed. Git stores objects independently of branch names, and unreachable objects can remain until Git's maintenance and garbage-collection mechanisms remove them.

The Python, JavaScript, and C++ implementations distinguish safe deletion from forced deletion.

---

## Python implementation

The Python implementation provides the most detailed educational repository simulation.

### `Commit`

The `Commit` data class contains:

- `commit_id`
- `message`
- `parents`
- `files`

The `parents` list is important because it allows both normal commits and merge commits to be represented.

### `Repository`

The `Repository` class models:

- commits
- branches
- HEAD
- detached HEAD
- working tree
- staging area

The `branches` dictionary maps branch names to commit IDs.

This directly represents the idea that a branch is a reference rather than a duplicate project directory.

### Branch operations

The implementation provides:

`create_branch()`

`checkout()`

`switch()`

`delete_branch()`

`force_delete_branch()`

The `switch()` method supports the conceptual equivalent of:

`git switch <branch>`

and:

`git switch -c <branch>`

### Commit operations

The Python implementation includes:

`edit_file()`

`add()`

`add_all()`

`commit()`

`commit_all()`

This provides a simplified representation of the working tree, staging area, and commit process.

### History analysis

The methods:

`ancestors()`

`is_ancestor()`

and:

`find_merge_base()`

are used to reason about the commit graph.

The implementation uses graph traversal rather than treating history as a simple linear list.

### Merge implementation

The Python `merge()` method distinguishes:

- already up-to-date
- fast-forward
- merge commit
- conflict

For a divergent history it identifies a common ancestor and compares the three snapshots.

This is the core technical mechanism of the Python implementation.

---

## JavaScript implementation

The JavaScript implementation uses classes, maps, sets, objects, promises, and asynchronous functions.

### `GitRepository`

The `GitRepository` class models repository state in an object-oriented way.

The following properties represent major Git concepts:

- `commits`
- `branches`
- `headBranch`
- `detachedHead`
- `workingTree`
- `stagingArea`

JavaScript's `Map` is used for commit and branch references.

### Object-oriented design

The `Commit` class encapsulates commit-specific information.

The `GitRepository` class encapsulates repository operations.

This separation mirrors a useful application-level design principle: domain objects should represent domain concepts, while the repository object manages relationships among them.

### Functional processing

The branch reporting example uses methods such as:

`map()`

and:

`sort()`

to transform repository state into branch reports.

This demonstrates how JavaScript's functional array methods can be applied to repository metadata.

### Asynchronous validation

The implementation includes asynchronous pre-merge checks using:

`Promise`

`Promise.all()`

and:

`async/await`

The checks represent independent operations such as:

- unit tests
- linting
- build validation
- security validation

In a real development platform, these operations can be performed by a CI system.

`Promise.all()` demonstrates the conceptual benefit of running independent checks concurrently rather than waiting for each unrelated check sequentially.

---

## C++ case study

The C++ program models an industry-style development environment for a web service.

The fictional service contains:

- a health function
- version information
- environment information
- authentication logic
- configuration data

The repository simulation is built around C++ classes and standard-library containers.

### `Commit`

The C++ `Commit` structure contains:

- commit ID
- commit message
- parent commit IDs
- file snapshots

The use of `vector<string>` for parents allows the same representation to handle ordinary commits and merge commits.

### `Repository`

The `Repository` class manages:

- commits
- branches
- HEAD
- detached HEAD
- working tree
- staging area

The branch table is represented using:

`map<string, string>`

This maps a branch name to a commit ID.

### Graph traversal

The program uses:

`set<string>`

and:

`queue<string>`

for ancestor discovery.

The `ancestors()` method performs breadth-first traversal through parent relationships.

The `findMergeBase()` method uses ancestor information to locate a common ancestor.

This demonstrates that Git history is fundamentally a directed acyclic graph rather than merely a list of versions.

### Merge processing

The C++ implementation checks for:

1. Identical branch tips.
2. Target already contained in current history.
3. Fast-forward possibility.
4. Three-way merge.
5. Conflicting file changes.
6. Explicit conflict resolution.
7. Merge commit creation.

The implementation is deliberately structured so that these decisions are visible in the program.

### Release validation

The `ReleaseValidator` class performs simple pre-integration checks.

It verifies that required files exist and that the service implementation contains the expected health functionality.

This models the principle that a branch should be validated before integration.

---

## Important distinctions

### Branch versus commit

A commit is a historical object.

A branch is a movable name pointing to a commit.

For example:

`main -> C`

means that the branch `main` currently references commit C.

If another commit is created on main:

`main -> D`

The old commit C still exists in the history.

### Branch versus working directory

Creating a branch does not mean creating a second complete directory containing another independent copy of the project.

Git changes the branch reference and working-tree state when switching branches.

### HEAD versus branch

HEAD usually points to the current branch.

For example:

`HEAD -> main -> C`

Detached HEAD changes this relationship:

`HEAD -> C`

### Checkout versus switch

`git checkout` is an older general-purpose command that can perform several operations.

`git switch` is focused specifically on branch switching.

For new branch-oriented workflows, `git switch` makes the intent clearer.

### Fast-forward versus merge commit

A fast-forward merge moves an existing branch reference.

A non-fast-forward merge can create a new commit with multiple parents.

The difference is determined by the relationship between the branch histories.

---

## Edge cases

### Switching with local changes

Switching branches while local modifications exist can cause problems if those changes would be overwritten or cannot be cleanly carried across.

A developer should inspect:

`git status`

before switching branches.

### Same branch merged into itself

A branch that is already identical to the current branch does not require a new merge commit.

### Already-contained branch

If the branch being merged is already an ancestor of the current branch, there is nothing new to integrate.

### Divergent branches

If both branches contain unique commits, Git must perform a non-fast-forward merge or another integration strategy.

### Same content changed independently

Two branches may modify the same file but produce identical final content. Such a case does not necessarily require a conflict because Git can determine that both sides reached the same result.

### File creation

If one branch creates a file and another branch does not modify the relevant base state, the new file can normally be incorporated automatically.

### File deletion

Deletion is also part of merge reasoning. A deletion can conflict with modifications made to the same file on another branch.

---

## Common mistakes

### Creating a branch from the wrong point

A branch begins at the commit that was checked out when it was created.

Before creating a branch, inspect the current branch and history.

Useful commands include:

`git status`

`git branch`

`git log --oneline --graph --decorate --all`

### Forgetting which branch is active

Always check the current branch before making important changes.

`git status`

usually shows the current branch.

### Merging without testing

A merge that completes without a conflict can still introduce incorrect application behavior.

Compilation, automated tests, static analysis, and other validation should be used where appropriate.

### Treating branches as security boundaries

Branches are not access-control boundaries.

Repository permissions and security controls are separate concerns.

### Assuming deletion removes all history

Deleting a branch removes the branch reference. It does not immediately mean that every commit formerly reachable through that branch has been physically removed.

### Ignoring conflicts

A conflict should be resolved deliberately. Accepting one side without understanding the application behavior can produce incorrect results.

---

## Limitations of the implementations

The three programs are educational simulations rather than replacements for Git.

They do not reproduce the complete Git object database, index format, reference storage, reflog behavior, pack files, object compression, remote protocols, authentication, hooks, merge strategies, rename detection, sparse checkout, submodules, worktrees, or Git's full conflict-resolution engine.

The merge-base implementations are simplified graph algorithms. Production Git uses optimized algorithms designed for very large histories.

The file models also represent content as strings rather than reproducing Git's binary object model.

The purpose of the implementations is to make the important branching relationships and algorithms explicit.

---

## Performance considerations

Branch creation is inexpensive because a branch is fundamentally a reference to an existing commit.

The main performance concerns in large repositories are usually associated with repository size, history complexity, working-tree size, large binary files, generated artifacts, object storage, and operations that must inspect significant portions of the commit graph.

The Python implementation uses sets and queues for graph traversal.

The JavaScript implementation uses `Map`, `Set`, arrays, and asynchronous promises.

The C++ implementation uses standard-library containers and graph traversal structures.

The complexity of a simplified ancestor traversal is approximately proportional to the number of commits and parent relationships visited.

For a graph containing V reachable commits and E parent relationships, a breadth-first history traversal has a typical graph-processing complexity of O(V + E).

The actual performance of Git itself depends on implementation details, repository structure, commit-graph data, object storage, caching, and other optimizations not reproduced here.

---

## Security considerations

Branching does not provide security isolation.

A secret such as an API key or password should not be committed to a repository simply because the branch is private or temporary.

Once sensitive data is committed, it can become part of repository history.

Deleting the file in a later commit does not automatically make the historical content disappear.

If a credential is exposed through a Git commit, the credential should be revoked or rotated. Depending on the situation, repository history may also need to be rewritten and affected copies or clones considered.

Branch permissions, repository permissions, protected branches, code review controls, and deployment permissions are separate mechanisms from the branch data structure itself.

---

## Production implementation considerations

A production branching workflow usually requires more than local branch creation and merging.

Important operational concerns can include:

- protected branches
- pull requests
- automated testing
- code review
- continuous integration
- release management
- deployment controls
- branch naming conventions
- commit quality
- dependency validation
- security scanning
- secret management
- audit requirements
- rollback procedures

The exact workflow varies between organizations and teams.

A small project may use a main branch plus short-lived feature branches.

Another organization may use release branches.

Another may use a trunk-based workflow with very short-lived branches.

The important technical principle is that the branch model should match the project's integration, testing, release, and collaboration requirements.

---

## Practical command reference

| Command | Purpose |
|---|---|
| `git branch` | List local branches |
| `git branch feature` | Create a branch |
| `git switch main` | Switch to an existing branch |
| `git switch -c feature` | Create and switch to a branch |
| `git checkout main` | Older multi-purpose branch switching command |
| `git checkout -b feature` | Older create-and-switch command |
| `git merge feature` | Merge a branch into the current branch |
| `git branch -d feature` | Safely delete a merged branch |
| `git branch -D feature` | Force-delete a branch |
| `git status` | Inspect current branch and working-tree state |
| `git log --oneline --graph --decorate --all` | Inspect the commit graph |
| `git merge --abort` | Abort an in-progress merge when supported by the current merge state |

---

## Python, JavaScript, and C++ comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Repository model | Detailed educational simulation | Object-oriented application model | Industry-style systems case study |
| Branch representation | Dictionary | `Map` | `map` |
| Commit representation | `dataclass` | Class | Struct |
| Graph traversal | Sets and lists | Sets and arrays | Sets and queues |
| Merge conflicts | Explicit resolution dictionary | Resolution object | Resolution map |
| Detached HEAD | Explicit repository state | Explicit repository state | Explicit repository state |
| Validation | Functions and assertions | Promise-based checks | Dedicated validator class |
| Asynchronous behavior | Not central | Demonstrated with promises | Not required for the case study |
| Systems-level design | Moderate | Application-oriented | Strong emphasis |
| Memory-level control | Python-managed | JavaScript runtime | C++ value and container semantics |

Python is particularly suitable for making the branching algorithm readable.

JavaScript is useful for demonstrating how repository concepts can become part of application interfaces, asynchronous workflows, and CI-style checks.

C++ makes the data structures and graph-oriented implementation decisions more explicit and provides a useful model for systems-oriented software.

---

## Architectural relationships

The central relationship can be represented conceptually as:

`Repository -> Commits`

`Repository -> Branch references`

`HEAD -> Current branch or commit`

`Branch -> Commit`

`Commit -> Parent commit or commits`

`Working tree -> Current files`

`Staging area -> Proposed next commit`

A branch therefore does not contain a separate copy of every previous branch state.

It identifies one point in the commit graph.

The commit itself identifies its parents, allowing Git to reconstruct ancestry.

---

## Example development history

A typical feature-development sequence can look like:

`main -> A`

Create a branch:

`main -> A`

`feature -> A`

Develop the feature:

`main -> A`

`feature -> B -> C`

Continue independent work on main:

`main -> A -> D`

`feature -> B -> C`

Merge:

`main -> A -> D -> M`

`feature -> B -> C ----/`

The merge commit M records both development lines.

If main had no independent commit after A, the merge could instead be a fast-forward:

`main -> A -> B -> C`

with no new merge commit.

---

## Testing principles

A branch is a development mechanism, not evidence that the code is correct.

A practical integration process should validate:

- syntax
- compilation
- unit behavior
- integration behavior
- expected edge cases
- security-sensitive behavior
- configuration
- deployment assumptions

The JavaScript implementation models concurrent pre-merge checks with promises.

The C++ implementation models release validation before integration.

The Python implementation includes assertions that verify branch creation, switching, fast-forward merging, and branch-pointer movement.

---

## Relationship between branching and collaboration

Branching allows several developers to work on different lines of development without immediately changing the same branch.

For example:

`feature/authentication`

may contain authentication work while:

`feature/reporting`

contains reporting work.

Both can originate from:

`main`

Each branch can have its own commits.

Eventually the changes can be integrated into the shared development line.

The branch names themselves are references. The actual history is represented by commits and their parent relationships.

---

## Core mental model

The most useful mental model is:

`Commit = snapshot plus parent relationship`

`Branch = movable name pointing to a commit`

`HEAD = current checkout position`

`Working tree = files currently being edited`

`Staging area = selected content for the next commit`

`Merge = operation that combines histories`

`Fast-forward = move a branch reference forward`

`Three-way merge = compare base, current, and target`

`Conflict = Git cannot determine the intended combined result`

Once these relationships are understood, commands such as `branch`, `checkout`, `switch`, and `merge` become operations on a commit graph rather than unrelated command-line instructions.

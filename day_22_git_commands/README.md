# Git commands: init, clone, status, add, commit, push, pull

## Introduction

Git is a distributed version control system used to record changes to files, preserve project history, and synchronize work between developers and repositories.

The commands covered in this document form a fundamental Git workflow:

- `git init`
- `git clone`
- `git status`
- `git add`
- `git commit`
- `git push`
- `git pull`

These commands are related but perform different operations. Understanding the separation between the working tree, staging area, local repository, and remote repository is more important than memorizing command syntax.

The central workflow is:

`working tree → git add → staging area → git commit → local repository → git push → remote repository`

Remote changes commonly travel in the opposite direction through:

`git pull`

A disciplined Git workflow depends on understanding exactly where a change exists at each stage.

## Fundamental Git terminology

### Working tree

The working tree is the collection of project files currently available in the local project directory.

For example, a project may contain:

`README.md`

`src/main.py`

`config.json`

If a tracked file is edited, the working tree contains the newer version while the latest commit may still contain the older version.

### Repository

A Git repository contains Git's internal history and metadata.

For a normal repository, Git stores this information in the `.git` directory.

The repository records commits, references, configuration, object data, and other information required to manage project history.

### Untracked file

An untracked file exists in the working tree but has not been included in Git's tracked content.

For example, after creating:

`notes.txt`

`git status` may report it as untracked.

Git does not automatically commit every file that happens to exist in the project directory.

### Tracked file

A tracked file is known to Git because it has been included in repository history or has otherwise been staged for tracking.

A tracked file can be clean, modified, or staged.

### Staging area

The staging area is also called the index.

It contains the version of files selected for the next commit.

This is one of the most important Git concepts.

The command:

`git add app.py`

does not create a commit.

It places the current contents of `app.py` into the staging area.

### Commit

A commit records a snapshot of staged content in the local repository.

The command:

`git commit -m "Add application configuration"`

creates a local historical record.

A successful commit does not automatically publish the commit to GitHub or another remote server.

### Remote repository

A remote repository is another Git repository used for synchronization and collaboration.

A hosted repository on a Git service is a common example.

The conventional remote name is:

`origin`

The name is only a local label. A remote can technically have another name.

### Branch

A branch is a movable reference to a line of development.

A common default branch name is:

`main`

Older repositories may use:

`master`

Projects can also use other branch names.

The exact branch name should always be checked instead of assumed.

### HEAD

`HEAD` normally identifies the current checkout position.

When working on a branch, `HEAD` normally points to that branch's current commit.

Understanding `HEAD` becomes particularly important when studying branches, detached HEAD states, merges, and rebases.

## The Git state model

A useful conceptual model is:

### Working tree

Contains the files being edited.

### Staging area

Contains selected file contents for the next commit.

### Local repository

Contains committed history.

### Remote repository

Contains history published to another repository.

The transition commands are:

| Command | Main purpose |
| --- | --- |
| `git init` | Create a new repository |
| `git clone` | Copy an existing repository |
| `git status` | Inspect repository state |
| `git add` | Stage content |
| `git commit` | Record staged content locally |
| `git push` | Send local commits to a remote |
| `git pull` | Obtain and integrate remote changes |

## `git init`

### Purpose

`git init` creates a new Git repository in an existing directory.

Basic form:

`git init`

A typical sequence is:

`mkdir project`

`cd project`

`git init`

After initialization, Git creates the repository metadata structure.

### What `git init` does

It creates a repository.

It does not automatically:

- create a meaningful project commit
- upload files
- create a GitHub repository
- stage all existing files
- push files to a remote

If the directory already contains project files, those files remain in the working tree.

They can then be inspected with:

`git status`

### Initial state

A newly initialized repository can have no commits.

This distinction is important.

A repository can exist while its history is empty.

A typical initial workflow is:

`git init`

`git status`

`git add .`

`git commit -m "Initial project"`

## `git clone`

### Purpose

`git clone` creates a new local copy of an existing repository.

Basic form:

`git clone <repository-url>`

For example:

`git clone https://example.com/project.git`

A clone normally creates:

- a working directory
- a `.git` repository
- a remote configuration
- local knowledge of the remote history

The default remote is commonly named:

`origin`

### Difference between `init` and `clone`

| `git init` | `git clone` |
| --- | --- |
| Starts a repository in an existing directory | Copies an existing repository |
| Usually begins with no commits | Receives existing repository history |
| Does not require an existing remote repository | Normally starts from an existing repository |
| Useful for a new local project | Useful for obtaining an existing project |

A simple distinction is:

`init = start here`

`clone = copy that repository here`

## `git status`

### Purpose

`git status` shows the state of the working tree and staging area.

Basic form:

`git status`

A compact form is:

`git status --short`

It can identify:

- untracked files
- modified files
- staged files
- files with both staged and unstaged changes
- branch information
- synchronization information

### Why status is important

Git does not require the developer to guess what will be committed.

`git status` provides a direct inspection mechanism.

A disciplined workflow frequently uses:

`git status`

before:

`git add`

and again before:

`git commit`

### Short status notation

A simplified interpretation is:

`?? file.txt`

The file is untracked.

` M file.txt`

The tracked file has working-tree modifications that are not staged.

`M  file.txt`

The modification is staged.

`MM file.txt`

The file contains staged changes and additional unstaged changes.

`A  file.txt`

A new file is staged.

The exact output can contain additional states for renames, deletions, conflicts, and other conditions.

## `git add`

### Purpose

`git add` places selected working-tree content into the staging area.

Basic form:

`git add file.txt`

Multiple files can be staged:

`git add file1.txt file2.txt`

A directory can also be staged:

`git add .`

### Important distinction

`git add` does not create a commit.

The sequence is:

`git add app.py`

then:

`git commit -m "Update application"`

The first command selects content.

The second records that selected content.

### Why staging exists

The staging area provides control over what belongs in the next commit.

Suppose a developer changes:

- `README.md`
- `src/main.py`
- `temporary-notes.txt`

The developer can stage only:

`git add README.md src/main.py`

This creates a commit containing the intended project changes without automatically including every modification in the working tree.

### Staging is a snapshot

An important behavior is that staging captures the contents at the time `git add` runs.

Consider:

`git add notes.txt`

Then modify `notes.txt` again.

The staging area can contain the earlier version while the working tree contains the newer version.

Running:

`git status`

can expose this difference.

This behavior is demonstrated explicitly in both the Python and C++ implementations.

## `git commit`

### Purpose

`git commit` records staged content in local repository history.

Basic form:

`git commit -m "Create project structure"`

The commit message should describe the logical change.

### Commit contents

A commit contains information associated with a snapshot and its history, including:

- snapshot information
- author information
- committer information
- commit message
- parent commit references
- an object identifier

A commit is part of local repository history.

### Commit versus push

These operations are separate:

`git commit`

records a change locally.

`git push`

transfers commits to a remote.

Therefore:

`git commit`

does not mean:

"the change is now on GitHub."

The change is local until it is successfully transferred to a remote.

### Commit messages

A useful commit message is specific.

Weak:

`git commit -m "changes"`

Better:

`git commit -m "Add incident severity validation"`

The purpose is to make repository history understandable to developers reviewing the project later.

## `git push`

### Purpose

`git push` sends local commits to a remote repository.

Basic form:

`git push`

If the upstream branch has not yet been configured, a common first push is:

`git push -u origin main`

The exact branch name depends on the repository.

### Remote and branch

In:

`git push origin main`

`origin` is the remote name.

`main` is the branch being pushed.

The relationship can be viewed conceptually as:

`local main → origin/main`

The `-u` option establishes an upstream relationship so that later synchronization can often use:

`git push`

without explicitly specifying the remote and branch.

### What push does not mean

A push does not:

- automatically modify unrelated local files
- automatically create a commit
- automatically resolve every collaboration conflict
- guarantee that application code is correct
- replace code review or automated testing

It transfers compatible Git history to the remote.

## `git pull`

### Purpose

`git pull` obtains remote changes and integrates them into the current local branch.

Basic form:

`git pull`

Conceptually, a traditional pull can be understood as:

`git fetch + integration`

The integration strategy can involve merging or rebasing depending on configuration and command options.

### Fast-forward pull

The simplest case occurs when the local branch is behind the remote and has no divergent local commits.

The local branch can move forward to the remote commit.

This is called a fast-forward.

### Divergent history

Suppose:

Local history:

`A → B → C`

Remote history:

`A → B → D`

The histories have diverged.

Git cannot simply move one branch pointer forward without deciding how the two histories should be integrated.

Depending on the chosen workflow, integration may involve:

- merge
- rebase
- conflict resolution

The appropriate choice depends on the project's collaboration policy and history requirements.

The C++ case study deliberately does not pretend that divergent histories can always be resolved automatically.

## The complete basic workflow

### Starting a new local project

A typical sequence is:

`mkdir project`

`cd project`

`git init`

Create project files.

Then:

`git status`

Stage the desired files:

`git add .`

Inspect again:

`git status`

Create a commit:

`git commit -m "Initial project"`

Configure a remote:

`git remote add origin <remote-url>`

Publish the branch:

`git push -u origin main`

### Working with an existing project

A typical sequence is:

`git clone <repository-url>`

`cd project`

Then:

`git status`

Make changes.

Then:

`git status`

Stage selected changes:

`git add <files>`

Inspect:

`git status`

Commit:

`git commit -m "Describe the change"`

Publish:

`git push`

### Synchronizing before continuing work

A common workflow is:

`git pull`

`git status`

edit files

`git add <files>`

`git commit -m "Describe the change"`

`git push`

The exact synchronization policy should follow the repository's established development workflow.

## Python implementation

The Python implementation provides an executable laboratory around the actual Git command-line program.

It uses:

- `subprocess`
- `pathlib`
- `tempfile`
- `dataclasses`
- standard exception handling

### Why Python is useful here

Python can invoke external processes through `subprocess`.

The helper function `git()` constructs commands such as:

`git status`

`git add README.md`

`git commit -m "Create initial project files"`

This demonstrates that Git itself is a command-line program and that automation tools can execute Git workflows programmatically.

### Temporary repositories

The Python program creates temporary directories.

This is an important safety and design decision.

Instead of operating on the user's normal repository, the program creates isolated demonstrations.

This allows commands such as:

`git init`

`git clone`

`git push`

and:

`git pull`

to be demonstrated without modifying an unrelated project.

### Repository-local identity

The Python program configures:

`user.name`

and:

`user.email`

at the repository level.

This prevents the educational demonstration from changing the user's global Git configuration.

### Python demonstration sequence

The Python script demonstrates:

1. Git installation verification.
2. Git's working-tree/staging/repository model.
3. `git init`.
4. `git status`.
5. `git add`.
6. `git commit`.
7. Creation of a local bare remote.
8. `git push`.
9. `git clone`.
10. `git pull`.
11. Staging behavior.
12. Push and synchronization concepts.
13. Common Git errors.
14. Production-oriented workflow considerations.

### Python error handling

The custom `GitCommandError` exception converts failed Git commands into explicit Python errors.

This is useful for automation because a script should not silently assume that:

`git push`

or:

`git commit`

succeeded.

A subprocess exit code is important when automating Git.

## JavaScript implementation

The JavaScript implementation uses Node.js standard-library functionality.

Important modules include:

`child_process`

and:

`fs`

The program also uses:

`os`

and:

`path`

### Executing Git commands

Node.js uses `execFileSync()` to invoke Git.

Passing the Git executable and its arguments separately is preferable to constructing one large shell command string.

For example, the program conceptually executes:

`git status --short`

as an executable plus an argument list.

### Why JavaScript is useful for this topic

JavaScript and Node.js are widely used in application tooling, build systems, web projects, automation, and development infrastructure.

A Node.js program can therefore integrate Git operations into:

- project automation
- build scripts
- release workflows
- repository utilities
- developer tooling
- continuous integration tasks

### JavaScript implementation stages

The JavaScript program demonstrates:

- Git installation verification
- `git init`
- `git status`
- `git add`
- `git commit`
- local remote creation
- `git push`
- `git clone`
- `git pull`
- staging snapshots
- edge cases
- command reference
- advanced Git concepts

The JavaScript version complements the Python implementation by emphasizing Node.js process execution and filesystem integration.

## C++ case study

The C++ program implements a detailed in-memory simulation of a software development environment.

The modeled system is an internal project named:

`Incident Analytics`

The case study models:

- repositories
- files
- working-tree state
- staging
- commits
- commit parents
- snapshots
- remote repositories
- branches
- push
- pull
- clone
- fast-forward synchronization
- non-fast-forward rejection

The program does not modify a real Git repository. Instead, it models the underlying concepts directly.

This provides a useful systems-level perspective on what the commands represent.

## C++ architecture

### `FileRecord`

`FileRecord` represents a project file.

It stores:

- path
- working-tree contents
- committed contents
- staged contents
- state

The state can be:

- `Untracked`
- `Clean`
- `Modified`
- `Staged`

This explicitly models the distinction that `git status` exposes.

### `Commit`

The `Commit` structure contains:

- commit ID
- message
- author
- parent identifiers
- snapshot

A snapshot is represented as a mapping from file paths to file contents.

The model is simplified compared with Git's actual content-addressed object database, but it is sufficient for demonstrating commit semantics.

### `RemoteRepository`

`RemoteRepository` represents a remote Git repository.

It stores:

- remote name
- commits
- branch name
- remote HEAD

This allows the local `Repository` class to simulate push and pull operations.

### `Repository`

The `Repository` class provides operations corresponding to the main Git concepts.

Important methods include:

`init()`

`createFile()`

`modifyFile()`

`status()`

`add()`

`commit()`

`log()`

`addRemote()`

`push()`

`pull()`

`cloneFrom()`

These methods form a simplified repository engine.

## C++ `init` model

The `init()` method creates the conceptual initial repository state.

The repository begins without a commit.

This represents an important Git condition:

A repository can exist even though its history contains zero commits.

## C++ `status` model

The `status()` method reports:

- repository name
- branch
- HEAD
- file states
- staging contents

This is analogous to the information a developer investigates through:

`git status`

The C++ version makes the states explicit through the `FileState` enumeration.

## C++ `add` model

The `add()` method copies the current working-tree contents into the staged representation.

This is intentionally implemented as a snapshot operation.

If a file is changed after being staged, the staged version remains different from the newer working-tree version.

This demonstrates why `git add` is not simply a flag saying "always include this file."

It stages specific content.

## C++ `commit` model

The `commit()` method:

1. validates the message.
2. validates the author.
3. checks that something is staged.
4. records the parent commit.
5. creates a commit identifier.
6. builds a snapshot.
7. stores the commit.
8. advances HEAD.
9. updates committed file state.
10. clears the staging area.

The implementation therefore models the essential conceptual effect of a Git commit.

## Commit parents

Each commit except the initial commit has a parent.

A simple history can therefore be represented as:

`A → B → C`

where:

- `A` is the initial commit
- `B` has `A` as its parent
- `C` has `B` as its parent

Branches and merges can create more complex ancestry.

The case study primarily models linear history and uses parent traversal for ancestry checks.

## Push model

The simulated `push()` method transfers compatible local history to the remote repository.

It checks for a remote.

It checks for a local commit.

It checks whether an existing remote tip is compatible with the local history.

If the update can be represented as a fast-forward, the simulated remote is updated.

If the histories are incompatible, the simulation rejects the push.

This models the important safety principle behind non-fast-forward rejection.

## Clone model

The C++ `cloneFrom()` method creates a new repository containing:

- remote history
- current branch
- remote HEAD
- working-tree files
- committed contents

This models the conceptual result of:

`git clone`

The cloned repository also retains a relationship with the remote.

## Pull model

The C++ implementation demonstrates a fast-forward pull.

If the remote has a newer commit and the local history can be advanced without divergence, the local repository adopts the remote history.

The simulation deliberately rejects a more complicated divergent pull rather than performing an artificial automatic merge.

This distinction is important because real conflict resolution depends on the actual content and project intent.

## Non-fast-forward behavior

A non-fast-forward condition can occur when two developers start from the same commit and independently create commits.

For example:

`A → B`

Developer A creates:

`A → B → C`

Developer B creates:

`A → B → D`

If Developer A pushes `C`, the remote may become:

`A → B → C`

Developer B's local history is still:

`A → B → D`

Developer B cannot safely replace the remote branch with `D` without integrating the divergent history.

A push rejection protects the remote history.

The C++ program explicitly demonstrates this condition.

## Edge cases

### Empty repository

After `git init`, there may be no commit.

Consequently, operations that require a commit must account for this state.

### Nothing to commit

If nothing is staged,:

`git commit`

cannot create a new snapshot.

The correct response is to inspect:

`git status`

and determine whether changes need to be staged.

### Untracked files

An untracked file exists in the working tree but is not part of repository history.

It can be intentionally staged with:

`git add file.txt`

### Modified but unstaged files

A tracked file can contain working-tree changes that are not yet staged.

Running:

`git commit`

does not automatically stage those changes.

### Staged plus unstaged changes

A file can have a staged version and a newer working-tree version simultaneously.

This is one of the most important subtle behaviors for beginners to understand.

### Non-fast-forward push

A push can be rejected when remote history is not contained in the local history.

This protects against silently replacing remote work.

### Missing remote

A local repository may not have a configured remote.

Commands such as:

`git push`

then require appropriate remote configuration.

### Wrong branch name

A command such as:

`git push origin main`

fails if the local repository does not actually have the expected branch or if the repository has not reached the appropriate initial state.

Checking the branch with:

`git branch --show-current`

reduces this type of error.

## Common mistakes

### Mistaking `add` for commit

Incorrect mental model:

`git add` saves the project permanently.

Correct model:

`git add` stages content for a future commit.

### Mistaking commit for push

Incorrect mental model:

`git commit` uploads the change.

Correct model:

`git commit` records the change locally.

`git push` publishes local commits to the configured remote.

### Using `git add .` without checking status

`git add .` can stage many changes.

A safer workflow for sensitive or complex projects is often:

`git status`

then stage intentionally:

`git add <specific files>`

then:

`git status`

### Ignoring status

Git provides detailed state information.

Failing to inspect it can lead to:

- unintended files in a commit
- missing staged changes
- accidental inclusion of generated files
- misunderstanding of synchronization state

### Assuming the branch is always `main`

Modern repositories commonly use `main`, but branch names are configurable.

The actual branch should be checked.

### Treating push rejection as data loss

A non-fast-forward rejection is normally a protective mechanism.

It means the remote and local histories require synchronization or integration.

### Committing secrets

Never treat Git history as a secure password store.

Secrets can remain in historical commits even after they are removed from the latest version.

## Important distinctions

### `init` versus `clone`

`init` creates a repository.

`clone` copies an existing repository.

### `status` versus `log`

`status` focuses on the current state of the working tree and staging area.

`log` focuses on historical commits.

### `add` versus `commit`

`add` stages content.

`commit` records staged content.

### `commit` versus `push`

`commit` affects local history.

`push` transfers local history to a remote.

### `pull` versus `push`

`pull` obtains remote changes and integrates them locally.

`push` transfers compatible local commits to the remote.

### `pull` versus `fetch`

`fetch` obtains remote information without automatically integrating it into the current branch.

`pull` combines fetching with an integration step.

## Advanced concepts

### Remote-tracking branches

A local repository can maintain references such as:

`origin/main`

This does not necessarily mean that the remote repository is currently being queried.

It represents the local repository's known state of that remote branch from synchronization operations.

### Upstream branches

An upstream relationship associates a local branch with a remote branch.

For example:

`main → origin/main`

After an upstream is configured, commands such as:

`git push`

and:

`git pull`

can often operate without explicitly specifying the remote and branch.

### Fast-forward

Suppose:

`A → B`

and the remote advances to:

`A → B → C`

If the local branch is still at `B`, it can advance directly to `C`.

No divergent local history needs to be combined.

### Merge

A merge combines histories that have diverged.

A simplified structure can look like:

`A → B → C`

and:

`A → B → D`

A merge can create a new commit with both lines of history as parents.

The exact graph depends on the operation and repository state.

### Rebase

A rebase replays commits on a different base and changes their ancestry.

Rebase can create a cleaner linear history in appropriate workflows, but it rewrites commit identities.

Published history should not be rewritten casually because other developers may already depend on the existing commits.

### Commit identifiers

Git commits have object identifiers.

The identifier is derived from repository object information and commit metadata.

Modern Git repositories can use different object hash formats, including SHA-1 and SHA-256 repository formats.

The C++ program intentionally uses a non-cryptographic educational identifier instead of attempting to implement Git's actual object database.

## Performance considerations

The Git commands themselves operate on potentially large repositories and histories.

Performance depends on factors such as:

- repository size
- number of files
- number of objects
- number of changed files
- history structure
- remote size
- network speed
- object compression
- filesystem performance
- repository configuration

### Status performance

`git status` may need to examine filesystem state and repository metadata.

Very large working trees can make status operations more expensive.

### Add performance

The cost of staging depends on the number and size of changed files and the work needed to determine their content state.

### Commit performance

A commit records a snapshot relationship and object metadata.

The practical cost depends on the amount of changed content and repository structure.

### Push performance

Push can require:

- object discovery
- negotiation
- object transfer
- compression
- network communication
- remote-side processing

Large binary files can make repository synchronization expensive.

### Pull performance

Pull includes remote synchronization and local integration.

Large histories or substantial changes can increase both network and local processing costs.

## Security considerations

### Secrets

Never commit:

- passwords
- API tokens
- private keys
- authentication credentials
- confidential configuration
- production secrets

A `.gitignore` file can prevent intended tracking, but it does not repair a secret that has already entered repository history.

### History persistence

Deleting a secret from the latest version does not necessarily remove it from previous commits.

This is why accidental secret publication must be treated as a security incident rather than merely a file-editing problem.

### Remote authentication

Git hosting can authenticate users through mechanisms such as:

- SSH
- HTTPS authentication
- credential helpers
- access tokens
- provider-specific authentication mechanisms

Authentication is distinct from Git's local commit mechanism.

A user can create a local commit without having permission to push it to a remote repository.

### Branch protection

Hosted repositories can apply additional controls such as:

- required reviews
- automated checks
- restrictions on direct pushes
- required status checks

These controls are generally provided by the hosting platform rather than by `git commit` itself.

## Implementation considerations

The Python program demonstrates actual Git commands in isolated temporary repositories.

This is useful for learning command behavior directly.

The JavaScript program demonstrates how Node.js can automate Git commands using process execution.

The C++ program takes a different approach. It models the underlying repository concepts directly in memory.

The three approaches therefore provide complementary perspectives:

| Language | Main demonstration |
| --- | --- |
| Python | Direct Git CLI automation |
| JavaScript | Node.js process and filesystem automation |
| C++ | Internal repository-state and workflow modeling |

## Why the three implementations differ

The implementations should not be identical merely because the same commands are involved.

### Python

Python is concise and well suited to scripting and automation.

The Python program therefore interacts directly with the real Git executable.

### JavaScript

Node.js is widely used for application tooling and development automation.

The JavaScript program demonstrates how a Node application can execute Git commands and manage temporary project files.

### C++

C++ provides explicit data structures and state management.

The C++ implementation uses classes, enumerations, maps, sets, vectors, optional values, exceptions, and algorithms to represent a simplified repository engine.

This makes it possible to study the conceptual mechanics behind Git without depending on the actual Git executable.

## Testing considerations

A Git automation program should verify command success.

For example, a script should not assume that:

`git commit`

succeeded merely because the command was attempted.

It should inspect:

- process exit code
- standard output
- standard error
- resulting repository state

After important operations,:

`git status`

can provide an additional state check.

For automated systems, failures should normally stop the workflow or be handled explicitly rather than silently ignored.

## Production workflow

A practical workflow for an existing project can be expressed as:

`git pull`

`git status`

Make changes.

`git status`

`git add <specific files>`

`git status`

`git commit -m "Describe the logical change"`

`git push`

For a new local project:

`git init`

`git status`

`git add .`

`git commit -m "Initial project"`

`git remote add origin <remote-url>`

`git push -u origin main`

The exact branch and remote URL depend on the repository.

## Practical applications

These commands are relevant to:

- software development
- data science projects
- machine learning projects
- documentation repositories
- infrastructure code
- configuration management
- research code
- web applications
- mobile applications
- C++ systems
- Python applications
- JavaScript applications
- collaborative engineering
- automated build systems
- continuous integration
- deployment workflows

The commands form the foundation for larger Git workflows involving branches, pull requests, code review, automated testing, release management, and deployment.

## Example mental model

A concise mental model is:

`git init`

Create a repository.

`git clone`

Copy an existing repository.

`git status`

Ask Git what state the project is in.

`git add`

Choose which current file contents belong in the next commit.

`git commit`

Record the staged snapshot locally.

`git push`

Send local commits to a remote.

`git pull`

Bring remote changes into the local repository and integrate them according to the configured strategy.

The critical distinction is:

`add ≠ commit ≠ push`

and:

`pull ≠ push`

These commands operate at different points in the version-control lifecycle.

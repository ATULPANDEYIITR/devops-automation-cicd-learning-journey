# Git Fundamentals: Repository, Working Tree, and Staging Area

## Introduction

Git is a distributed version control system designed to record changes to a collection of files. Its power comes from separating several related concepts that are often confused by beginners: the working tree, the staging area, the current commit, branches, and the repository's internal object database.

This project studies those concepts through three implementations:

- `Python`: a detailed educational model that focuses on the flow of file content between the working tree, staging area, and committed state.
- `JavaScript`: an implementation using classes, maps, sets, functional transformations, asynchronous process execution, filesystem operations, and a miniature object database.
- `C++`: an industry-style case study that models a controlled document publishing repository with commits, branches, HEAD, object storage, validation, status, diffs, and complexity analysis.

The central model is:

    Working tree
         |
         | git add
         v
    Staging area / index
         |
         | git commit
         v
    Repository history

Understanding this flow is more important than memorizing individual Git commands. Most common Git operations become easier to reason about once the source and destination of a change are clear.

## Fundamental concepts

### Git

Git is a distributed version control system. A local Git repository contains the information required to maintain project history without requiring a network connection for ordinary local operations.

Git records versions as objects and connects those versions through commit history. Developers can create branches, compare states, restore content, inspect history, and synchronize repositories with remote repositories.

### Repository

A repository is the Git-controlled project history and metadata. In a typical working directory, the local repository is represented by the hidden `.git` directory.

The working files are not themselves equivalent to the entire repository. A repository contains information about commits, references, objects, the index, configuration, and other metadata.

A useful distinction is:

- Working tree: files being edited.
- Repository: Git's stored version history and metadata.
- Index: the staging area used to prepare the next commit.

### Working tree

The working tree is the directory containing the files that a developer currently works on.

For example, a project might contain:

- `README.md`
- `src/app.py`
- `tests/test_app.py`
- `.gitignore`

Opening `src/app.py` in an editor and changing its contents changes the working tree.

The change does not automatically become part of the next commit.

### Staging area

The staging area is commonly called the index.

It represents the content that Git has selected for the next commit.

The command `git add` updates the index using the current contents of the selected working-tree paths.

This distinction is essential:

`git add` does not mean "permanently save this change."

It means, conceptually:

"Put this current version of the selected path into the proposed next snapshot."

A later `git commit` records the staged snapshot.

### Commit

A commit is a recorded snapshot of the project state together with metadata and references to parent commits.

A normal commit has one parent, except for the initial commit. A merge commit can have multiple parents.

A commit is therefore more than a timestamped copy of one file. It represents a project tree and metadata within a connected history.

### Branch

A branch is a movable reference to a commit.

This is an important distinction from the beginner assumption that a branch is a completely separate copy of the project directory.

When a new branch is created, the branch reference initially points to an existing commit. New commits can move that reference forward.

For example:

    main -> A -> B
                 ^
                 |
              feature

If `feature` is created while `main` points to commit `B`, both references initially point to the same commit.

If a new feature commit `C` is created on `feature`:

    main    -> B
               \
    feature -> C

The commit objects and file data can be shared. The branch references themselves are separate.

### HEAD

`HEAD` identifies the current checkout position.

In an ordinary branch checkout, `HEAD` points to the current branch, and that branch points to a commit.

Conceptually:

    HEAD -> main -> commit

When the developer switches to another branch:

    HEAD -> feature -> commit

This relationship explains why the current branch changes when the user runs `git switch`.

### Tracked and untracked files

A tracked file is a path that Git already knows about through the index and/or repository history.

An untracked file exists in the working tree but has not been incorporated into the Git tracking state.

For example, after creating a new file:

    report.txt

`git status` can show it as untracked.

After:

    git add report.txt

the file becomes staged for the next commit.

After:

    git commit -m "Add report"

the file becomes part of committed history.

## The three-area model

The most useful beginner model is to think about three local states:

1. The current commit.
2. The staging area.
3. The working tree.

The current commit represents the last recorded snapshot at the current branch position.

The staging area represents what is proposed for the next commit.

The working tree contains what currently exists on disk.

The common flow is:

    working tree
        |
        | git add
        v
    staging area
        |
        | git commit
        v
    new commit

Changes can exist at either boundary.

For example:

    Commit:   version 1
    Stage:    version 2
    Working:  version 3

This is a valid state.

The developer can therefore have:

- a change already staged for the next commit, and
- another change made after staging that is still unstaged.

This is one of Git's most important characteristics.

## Why the staging area exists

Without a staging area, the system would have to treat all working-tree changes as one indivisible group.

The staging area permits selective commits.

Suppose a developer makes three changes:

- fixes a calculation,
- changes documentation,
- adds temporary debugging output.

The developer can stage only the calculation fix and commit it separately.

The remaining working-tree changes can stay uncommitted.

This creates cleaner history and reduces the chance of mixing unrelated changes into one commit.

Interactive staging can make this even more precise. Commands such as `git add -p` allow individual portions of a file's changes to be selected.

## `git status`

`git status` provides a high-level view of the relationship between the current commit, staging area, and working tree.

Common states include:

- untracked
- modified but unstaged
- modified and staged
- staged and additionally modified
- deleted
- clean

A clean working tree means there are no relevant changes between the working tree, index, and current commit.

A simplified conceptual example is:

    Commit = A
    Stage  = A
    Working = A

The project is clean.

After editing:

    Commit = A
    Stage  = A
    Working = B

The file is modified but unstaged.

After staging:

    Commit = A
    Stage  = B
    Working = B

The modification is staged.

After editing again:

    Commit = A
    Stage  = B
    Working = C

There are now two boundaries containing differences.

## `git add`

The command:

    git add <path>

updates the staging area from the working tree.

It is useful to think of the operation as:

    working-tree content
            |
            v
       staging area

The working file is not removed from the working tree.

The index receives the selected version.

This means a developer can edit a file, stage it, edit it again, and have different content in the staging area and working tree.

The Python and JavaScript implementations explicitly model this behavior.

## `git diff`

The ordinary command:

    git diff

is conceptually concerned with the difference between the working tree and staging area.

If the index contains:

    version 2

and the working tree contains:

    version 3

the difference shown by `git diff` concerns version 2 versus version 3.

This is useful for answering:

"What have I changed since I last staged?"

## `git diff --cached`

The command:

    git diff --cached

compares the staging area with the current commit.

It answers:

"What am I currently preparing to commit?"

For example:

    Commit = version 1
    Stage  = version 2
    Working = version 3

Then:

    git diff

shows the difference between version 2 and version 3.

    git diff --cached

shows the difference between version 1 and version 2.

These two commands are therefore not interchangeable.

## `git commit`

The command:

    git commit -m "Update application"

creates a new commit from staged content.

The conceptual flow is:

    index
      |
      | commit
      v
    new commit

A commit does not simply record whatever happens to be visible in the working directory at that instant. The staging area determines the content represented by the new snapshot.

This is why reviewing the staged changes before committing is useful.

## File lifecycle

A common lifecycle is:

    untracked
       |
       | git add
       v
    staged
       |
       | git commit
       v
    tracked and committed
       |
       | edit
       v
    modified
       |
       | git add
       v
    staged modification
       |
       | git commit
       v
    clean committed state

The Python and JavaScript implementations reproduce this lifecycle with in-memory state.

The C++ case study implements it as part of a document management system.

## Deleting files

Deletion introduces another important distinction.

If a tracked file is removed from the working tree, Git can detect that the path has disappeared.

The deletion can then be staged and committed.

The staging area can therefore represent not only file content but also the absence of a previously existing path.

This is part of the reason the index should be thought of as a proposed snapshot rather than merely a list of "files to commit."

## The object model

Git uses a content-addressed object database.

Important Git object categories include:

- blob
- tree
- commit
- annotated tag

### Blob

A blob represents file content.

A blob does not primarily represent a filename. Names and directory structure are represented through trees.

### Tree

A tree represents directory structure and references objects associated with paths.

Conceptually:

    tree
      |
      +-- README.md -> blob
      |
      +-- src       -> tree
                         |
                         +-- app.py -> blob

### Commit

A commit points to a tree representing the project state and records metadata such as its parents and commit message.

Conceptually:

    commit
      |
      +-- tree
      |
      +-- parent
      |
      +-- metadata

A commit can therefore be understood as a node in a history graph.

## Content addressing

A content-addressed system derives an identifier from the content being stored.

The Python implementation demonstrates hashing with SHA-1.

The JavaScript implementation constructs Git-like object identifiers from an object type and content.

The C++ program includes an educational hash only to demonstrate the architecture without requiring an external cryptography library.

The C++ hash is explicitly not a cryptographic implementation of Git's hashing mechanism.

Real Git repositories may use SHA-1 or SHA-256 depending on repository format and configuration.

A tiny content change normally changes the resulting cryptographic hash substantially.

This property supports object identification and integrity-oriented storage.

## Commit history

Commits form a directed graph.

A simple history might look like:

    A -> B -> C

where:

- `A` is the first commit,
- `B` has `A` as its parent,
- `C` has `B` as its parent.

A branch can point to `C`.

A second branch can be created at `B`:

    A -> B -> C
         \
          D

If development on both branches continues, histories diverge.

A merge can create a commit with two parents:

    A -> B -> C
         \     /
          D -- 
             \
              M

The exact graph depends on the development history.

## Python implementation

The Python script provides an in-memory `GitLearningModel`.

It maintains three dictionaries:

- `committed`
- `staged`
- `working`

These correspond to the conceptual states discussed earlier.

The `status()` method compares all three.

The `git_add()` method copies working-tree content into the staging area.

The `git_restore_staged()` method models moving staged content toward the current committed state.

The `git_restore_worktree()` method models restoring working-tree content from staged or committed content.

The `commit()` method creates a simplified committed snapshot from the staging area.

The implementation intentionally focuses on content flow rather than attempting to reproduce Git's entire storage format.

### Python status detection

The Python implementation explicitly distinguishes:

    clean

from:

    modified

from:

    modified and staged

and:

    staged and additionally modified

This makes the relationship between the three areas directly observable.

### Python diff model

Two comparison functions are provided:

    diff_commit_to_stage()

and:

    diff_stage_to_working()

The first corresponds conceptually to:

    git diff --cached

The second corresponds conceptually to:

    git diff

### Python object database

`MiniObjectDatabase` demonstrates the idea of storing:

- blob objects,
- tree objects,
- commit objects.

It uses SHA-1 for educational object identification.

The object database is deliberately smaller than Git itself. It demonstrates the architecture rather than implementing Git's complete on-disk format, compression, indexing, locking, pack files, references, and protocol behavior.

### Python real Git demonstration

The script checks whether Git is installed and, if available, creates a temporary repository.

It then demonstrates:

- `git init`
- Git configuration
- creating files
- `git status`
- `git add`
- `git diff --cached`
- `git commit`
- modifying a file
- `git diff`
- another `git add`
- history inspection
- `git rev-parse`

The repository is created in a temporary directory and removed automatically after the demonstration.

This keeps the practical demonstration separate from a user's existing project.

## JavaScript implementation

The JavaScript file models the same Git concepts using JavaScript-specific structures and runtime capabilities.

The central class is:

    GitThreeAreaModel

It uses JavaScript `Map` objects to represent file snapshots.

This makes it possible to demonstrate:

- object-oriented design,
- maps,
- sets,
- iteration,
- validation,
- exceptions,
- functional classification,
- asynchronous operations.

### JavaScript status classification

The function:

    classifyFile()

takes the relevant state of a file and returns a status classification.

This separates status logic from storage and demonstrates a functional approach to state classification.

### JavaScript object database

`MiniObjectDatabase` stores objects in a `Map`.

The implementation calculates object identifiers using Node.js's built-in `crypto` module.

The demonstration uses:

    blob

    tree

    commit

objects.

It illustrates the relationship between content, object identifiers, and stored object types.

### JavaScript branches

`BranchState` stores branch names and commit identifiers.

The current branch is stored separately as `headBranch`.

This creates the conceptual structure:

    HEAD -> branch -> commit

Creating a branch stores the current commit identifier under another branch name.

Advancing the feature branch changes only that branch's reference.

### JavaScript asynchronous Git execution

Node.js provides access to the operating system through its standard library.

The script uses asynchronous process execution to invoke real Git commands.

This demonstrates an application-level automation pattern:

    JavaScript application
           |
           | execute Git process
           v
        Git CLI
           |
           v
      repository

The code creates a temporary repository and removes it after the demonstration.

This is a useful pattern for tooling that needs to automate Git operations while still allowing Git itself to handle repository semantics.

## C++ case study

The C++ implementation presents a non-trivial scenario: a controlled document publishing repository.

The modeled organization maintains policy documents and needs to:

- create documents,
- edit documents,
- stage selected changes,
- review differences,
- commit stable snapshots,
- create branches,
- switch branches,
- inspect history,
- handle invalid operations,
- model object storage.

The architecture is intentionally modular.

### `FileMap`

`FileMap` is an alias for:

    std::map<std::string, std::string>

The key represents a path.

The value represents file content.

Three important snapshots are maintained:

- `workingTree_`
- `index_`
- the current commit tree

### `Commit`

The `Commit` structure stores:

- commit identifier,
- commit message,
- parent identifiers,
- tree snapshot.

This represents the relationship between a snapshot and its history.

### `CommitStore`

`CommitStore` maintains commits by identifier.

It creates an identifier from educational content derived from:

- commit message,
- parent references,
- file paths,
- file content.

The implementation does not claim to reproduce Git's actual commit serialization.

### `BranchManager`

`BranchManager` maintains:

- branch names,
- commit references,
- current branch.

This provides a direct model of branch references.

### `ObjectDatabase`

The C++ object database demonstrates the architecture of content-addressed objects.

It supports:

    Blob
    Tree
    Commit

The database calculates an educational identifier and stores the resulting object.

The implementation is intentionally not a replacement for Git's real object database.

### `VersionControlEngine`

`VersionControlEngine` combines the major components.

Its methods include:

- `createFile`
- `editFile`
- `deleteFile`
- `add`
- `addAll`
- `unstage`
- `restoreWorkingFile`
- `commit`
- `createBranch`
- `switchBranch`
- `printStatus`
- `printDiffs`
- `printHistory`

The class therefore models a small version-control system instead of presenting isolated syntax examples.

## C++ case study workflow

The document repository begins with:

    README.md
    policy.txt

The files are staged and committed.

The policy is then modified and staged.

Afterward, the README is changed but not staged.

The resulting state contains:

    policy.txt
        staged change

    README.md
        unstaged change

The program then commits only the staged policy modification.

This demonstrates the primary purpose of the staging area: selecting the exact content that should become part of the next commit.

The README modification remains in the working tree.

It can later be staged and committed independently.

## Important distinctions

### Working tree vs staging area

The working tree is what is currently being edited.

The staging area is what has been selected for the next commit.

### Staging area vs commit

The staging area is temporary preparation.

A commit records a snapshot into repository history.

### `git diff` vs `git diff --cached`

`git diff` compares:

    working tree
    vs
    staging area

`git diff --cached` compares:

    staging area
    vs
    current commit

### Branch vs commit

A branch is a reference to a commit.

A commit is a historical snapshot.

A branch can move forward as new commits are created.

### HEAD vs branch

In an ordinary branch checkout:

    HEAD -> branch -> commit

`HEAD` identifies the current checkout position.

### `.gitignore` vs security

`.gitignore` helps prevent selected untracked files from being included accidentally.

It is not a security boundary.

If a secret has already been committed, adding its filename to `.gitignore` does not erase the secret from historical commits.

## Common mistakes

### Treating `git add` as permanent saving

`git add` updates the index.

It does not create a commit.

The staged content becomes part of repository history only when it is committed.

### Assuming all edits are automatically committed

Working-tree edits are not automatically part of the next commit.

Only staged content is prepared for that commit.

### Running `git add .` without reviewing the result

Broad staging commands can include files that were not intended to be part of the next commit.

Reviewing:

    git status

and:

    git diff --cached

helps verify the staged set.

### Confusing the two diff commands

`git diff` and `git diff --cached` compare different boundaries.

Remember:

    git diff
    working tree -> staging area comparison

    git diff --cached
    staging area -> current commit comparison

### Assuming `.gitignore` removes tracked files

If a file is already tracked, adding it to `.gitignore` does not automatically stop Git from tracking it.

The tracking state must be changed explicitly.

### Using restore operations without understanding their direction

Restore-related commands can change working-tree or index state.

Some forms can discard uncommitted work.

The important question before using a potentially destructive command is:

"What state will replace what state?"

### Committing secrets

Credentials should not be placed into Git history.

Examples include:

- passwords,
- API tokens,
- private keys,
- database credentials,
- cloud access credentials.

If sensitive information is committed, simply deleting it from the current version does not necessarily remove it from historical objects.

## Edge cases

### Stage and edit again

A file can have three different states:

    Commit = A
    Stage = B
    Working = C

This is valid.

It means one change has already been selected for the next commit and another change was made afterward.

### Edit and return to the original content

If a file is edited from A to B and then returned exactly to A, Git may have no content difference to report at that boundary.

Git compares state, not the sequence of keystrokes that produced the state.

### Stage and then undo the working-tree edit

Suppose:

    Commit = A
    Stage = B
    Working = B

After editing the working tree back to A:

    Commit = A
    Stage = B
    Working = A

The staged change remains.

The working-tree content and staged content are independent states.

### Empty commit

If there is no staged difference from the current commit, a normal commit operation has nothing new to record.

The C++ case study explicitly detects this condition.

### Untracked files

An untracked file can exist in the working tree without appearing in repository history.

It becomes part of the proposed next snapshot only after it is staged.

## Performance considerations

Git is designed to handle large histories efficiently, but repository design affects performance.

### Repository size

Large repositories consume more storage and may require more time for operations involving history, object traversal, transfer, or working-tree inspection.

### Binary files

Frequently changing large binary files can be expensive for ordinary Git workflows because source-oriented version control is especially effective when changes can be represented efficiently across versions.

Large binary assets may require different repository strategies depending on the workload.

### Object reuse

Content-addressed storage permits identical content to map to the same object identity.

This can reduce redundant storage.

### Packing

Git can pack objects together and use compression and indexing techniques.

Packing is one of the mechanisms that allows Git repositories to remain practical even when they contain substantial history.

### Commit granularity

Focused commits are useful for:

- reviewing history,
- identifying the change associated with a bug,
- reverting a particular logical change,
- understanding project evolution.

Commit size is therefore both a technical and organizational design consideration.

### Data structures

The C++ implementation uses ordered maps and sets.

For `N` paths, operations involving ordered traversal are generally associated with logarithmic lookup and approximately `O(N log N)` behavior for operations that collect and compare ordered sets of paths.

An `unordered_map` can provide average constant-time lookup, but it does not naturally provide sorted iteration and has different memory and worst-case behavior.

The educational implementation favors clarity and deterministic ordering.

## Security considerations

Git provides integrity-oriented mechanisms, but repository security is broader than hashing.

### Secrets

Sensitive values should not be committed.

A secret in Git history can remain accessible through older commits even after the latest version no longer contains it.

### `.gitignore`

A `.gitignore` file can reduce accidental inclusion of local secret files.

It should not be treated as a security control.

### Repository permissions

Local Git commands and remote repository authorization are separate concerns.

Having a local clone does not by itself determine who is authorized to access a remote repository.

### Commit signing

Signed commits can provide cryptographic evidence associated with a signer and commit.

Signing does not establish that the code is safe, correct, or free of malicious behavior.

### Object identifiers

Content-addressed identifiers help detect changes to the underlying represented object.

They do not grant authorization.

## Implementation considerations

### Python

Python is useful for teaching Git concepts because dictionaries and classes make the three-area state easy to model.

The script also demonstrates subprocess execution against a temporary repository, allowing conceptual code and real Git behavior to be compared.

### JavaScript

JavaScript is useful for application and automation scenarios.

The implementation demonstrates:

- `Map`,
- `Set`,
- classes,
- functional classification,
- asynchronous process execution,
- Node.js filesystem APIs,
- Node.js cryptographic APIs.

This is relevant to developer tooling, build systems, automation, and web-oriented development environments.

### C++

C++ demonstrates how the concepts can be expressed in a strongly typed systems-oriented architecture.

The case study uses:

- classes,
- structures,
- maps,
- sets,
- vectors,
- optionals,
- exceptions,
- deterministic output,
- modular functions,
- explicit ownership through ordinary standard-library objects.

The implementation also makes architectural trade-offs visible.

## Practical applications

The concepts demonstrated here appear in many real development workflows.

### Individual development

A developer can maintain experimental changes in the working tree while selecting only stable changes for the next commit.

### Team development

Branches allow independent lines of development to exist within one repository history.

### Code review

A focused commit and its staged changes can provide a clearer unit for review.

### Debugging

Commit history can help identify when a change entered a project.

### Release management

Branches and commits can represent different development and release states.

### Automation

The JavaScript implementation demonstrates how another program can invoke Git commands and inspect their output.

This pattern can be used in build tooling, repository management utilities, deployment systems, and developer productivity software.

### Document management

The C++ case study demonstrates that version-control concepts apply beyond source code.

The same fundamental model can be applied to controlled documents, configuration files, research artifacts, policies, and other text-oriented project assets.

## Production considerations

A real production-grade version-control system requires significantly more than the educational implementations in this project.

Important concerns include:

- durable filesystem storage,
- locking,
- concurrent processes,
- object compression,
- pack files,
- indexes,
- references,
- reflogs,
- configuration,
- merge algorithms,
- rename detection,
- binary handling,
- filesystem performance,
- crash recovery,
- corruption detection,
- repository protocols,
- remote synchronization,
- authentication,
- authorization,
- cryptographic signing,
- compatibility with existing repository formats.

The three implementations intentionally avoid pretending to reproduce all of Git.

Their purpose is to make the fundamental state transitions and architecture understandable.

## Core command reference

| Command | Purpose |
| --- | --- |
| `git init` | Create a new repository |
| `git status` | Inspect repository state |
| `git add <path>` | Stage the current contents of a path |
| `git add .` | Stage applicable changes under the current directory |
| `git diff` | Inspect unstaged changes |
| `git diff --cached` | Inspect staged changes |
| `git commit -m "message"` | Create a commit from staged content |
| `git log --oneline` | Inspect compact history |
| `git branch` | List branches |
| `git branch <name>` | Create a branch |
| `git switch <name>` | Switch branches |
| `git restore --staged <path>` | Unstage a path while normally retaining the working-tree edit |
| `git restore <path>` | Restore working-tree content from the index |
| `git show <commit>` | Inspect a commit |
| `git rev-parse HEAD` | Resolve `HEAD` to a commit identifier |
| `git rev-parse --show-toplevel` | Locate the repository root |

## Relationship between the three implementations

The implementations share the same conceptual model but use different programming techniques.

| Concept | Python | JavaScript | C++ |
| --- | --- | --- | --- |
| Working tree | Dictionary | `Map` | `std::map` |
| Staging area | Dictionary | `Map` | `std::map` |
| Commit snapshot | Dictionary | `Map` | `FileMap` |
| Status calculation | Class methods | Class methods and function | Engine methods |
| Object storage | `MiniObjectDatabase` | `MiniObjectDatabase` | `ObjectDatabase` |
| Branches | `BranchModel` | `BranchState` | `BranchManager` |
| Commits | Dataclass | `CommitGraph` | `Commit` and `CommitStore` |
| Real Git execution | Python subprocess | Node.js child process | Not required |
| Error handling | Exceptions | Exceptions and rejected promises | C++ exceptions |
| Testing | Assertions | Assertions | Explicit `require` checks |

The Python implementation emphasizes conceptual clarity.

The JavaScript implementation emphasizes application-level programming and asynchronous interaction with Git.

The C++ implementation emphasizes architecture, data structures, type safety, and a realistic technical case study.

## Conceptual model to retain

The most important relationships are:

    Working tree
        |
        | git add
        v
    Staging area / index
        |
        | git commit
        v
    Commit
        |
        v
    Repository history

For comparisons:

    git diff
        Working tree <-> Index

    git diff --cached
        Index <-> Current commit

For branches:

    HEAD -> current branch -> current commit

For commit history:

    commit -> parent commit -> parent commit

For object storage:

    file content -> blob
    directory structure -> tree
    snapshot metadata + tree + parents -> commit

These relationships explain a large part of Git's everyday behavior and provide the foundation for understanding more advanced operations such as branching, merging, rebasing, reset, restore, remote synchronization, and history inspection.
```

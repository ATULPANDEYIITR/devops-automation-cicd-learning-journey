# Git Advanced: Rebase, Cherry-pick, Stash, and Reflog

## 1. Topic Introduction

Advanced Git work requires more than creating commits and pushing branches. Developers frequently need to reorganize local history, transfer a specific fix between branches, temporarily preserve unfinished work, or recover a commit after a destructive history operation.

This study focuses on four important Git mechanisms:

- `rebase`
- `cherry-pick`
- `stash`
- `reflog`

The three implementations approach the subject from different technical perspectives:

- **Python** provides a broad executable tutorial with progressively developed demonstrations.
- **JavaScript** demonstrates Git automation from Node.js using process execution, structured error handling, and repository-state inspection.
- **C++** presents an industry-style release-engineering case study with classes, modular operations, validation, recovery analysis, and production considerations.

All three implementations create temporary repositories so that their demonstrations do not depend on an existing project history.

---

## 2. Git Concepts Required Before Advanced Operations

Git is a distributed version-control system based around commits, references, and repository objects.

Four concepts are particularly important.

### 2.1 Working tree

The working tree is the set of files currently checked out on disk.

A developer can modify these files without immediately creating a Git commit.

### 2.2 Index

The index, commonly called the staging area, contains the proposed contents for the next commit.

For example:

`git add app.py`

moves the selected changes into the index.

### 2.3 Commit

A commit represents a snapshot of tracked project content together with metadata such as:

- parent commit references
- author
- committer
- timestamp
- commit message

A commit receives an identifier derived from its content and associated metadata.

### 2.4 Reference

A reference is a name that points to a commit.

Examples include:

- `main`
- `feature/login`
- `HEAD`
- tags

A branch is therefore better understood as a movable reference than as an independent copy of the project.

---

## 3. Why Commit Parents Matter

Git history is represented through parent relationships.

A simple history may look like:

`A -> B -> C`

where:

- `B` has parent `A`
- `C` has parent `B`

Branches can diverge:

`A -> B -> C`

and:

`A -> B -> D`

The two branches share history through `B`, but their later commits differ.

Advanced commands such as rebase and cherry-pick operate on these relationships and on the changes represented by commits.

---

# 4. Rebase

## 4.1 Definition

`git rebase` replays commits from one line of development onto another base.

Suppose the history is:

`A -> M1`

and a feature branch contains:

`A -> F1 -> F2`

A rebase of the feature branch onto `M1` conceptually produces:

`A -> M1 -> F1' -> F2'`

The commits `F1'` and `F2'` are newly created commits.

The original feature commits are not modified in place.

---

## 4.2 Why Commit IDs Change

A Git commit includes its parent information.

If a commit originally has:

`F1 parent = A`

and is replayed after `M1`, the resulting commit has:

`F1' parent = M1`

Because the parent relationship is different, the commit identity changes.

This is the fundamental reason rebase is a history-rewriting operation.

---

## 4.3 Basic Rebase Command

The common form is:

`git rebase main`

When executed while on a feature branch, Git attempts to replay the feature commits on top of `main`.

A typical workflow is:

`git switch feature`

`git fetch origin`

`git rebase origin/main`

The Python and JavaScript implementations create divergent histories and execute an actual rebase.

The C++ implementation uses the same operation as part of a release-engineering workflow.

---

## 4.4 Linear History

Rebase is often used when a team wants a feature branch to appear as though its work was developed from the latest base.

Before:

`A -> M1`

`A -> F1 -> F2`

After rebasing:

`A -> M1 -> F1' -> F2'`

The resulting history can be easier to read because the feature commits form a linear sequence after the updated base.

This does not mean that rebase is inherently superior to merge. The appropriate approach depends on the project's history policy and collaboration model.

---

## 4.5 Rebase Versus Merge

### Rebase

Rebase:

- replays commits
- creates new commit objects
- changes commit ancestry
- can produce a linear history
- rewrites the rebased commits

### Merge

Merge:

- combines histories
- normally preserves the existing commits
- can create a merge commit
- preserves the fact that two development lines existed

Conceptually:

Rebase:

`A -> M -> F1' -> F2'`

Merge:

`A -> M`
` \`
`  F1 -> F2`
`       \`
`        Merge`

The choice is a workflow decision rather than a universal technical rule.

---

## 4.6 Interactive Rebase

Interactive rebase allows developers to manipulate a sequence of commits.

Example:

`git rebase -i HEAD~4`

Common actions include:

| Action | Meaning |
|---|---|
| `pick` | Keep the commit |
| `reword` | Keep the changes but edit the message |
| `edit` | Stop and manually modify the commit |
| `squash` | Combine with the previous commit and edit the combined message |
| `fixup` | Combine with the previous commit while discarding the selected message |
| `drop` | Remove the commit |

Interactive rebase is useful for organizing local commits before sharing them.

For example, a developer might have:

`Add login`

`Fix typo`

`Fix validation`

`Improve login`

These can potentially be reorganized into a smaller, coherent sequence before publication.

---

## 4.7 Rebase Conflicts

Rebase does not guarantee that every patch can be applied automatically.

A conflict can occur when the original patch no longer applies cleanly to the new base.

Useful commands are:

`git status`

`git rebase --show-current-patch`

After resolving a conflict:

`git add <resolved-file>`

`git rebase --continue`

To abandon the entire operation:

`git rebase --abort`

To skip the current patch:

`git rebase --skip`

Conflict resolution is a semantic task. Git can identify conflicting content, but it cannot reliably determine the correct business behavior in every situation.

---

## 4.8 Public History and Rebase

Rebase changes commit identities.

If other developers have already based work on those commits, rewriting them can require coordination.

A common distinction is:

- **Private/local commits:** frequently suitable for cleanup through rebase.
- **Shared/public commits:** rewriting requires greater care and explicit team policy.

When rewritten history must be pushed to a remote, a safer force-push form is:

`git push --force-with-lease`

`--force-with-lease` checks whether the remote reference still has the expected state, reducing the risk of overwriting someone else's newly pushed work.

---

# 5. Cherry-pick

## 5.1 Definition

`git cherry-pick` applies the change introduced by a selected commit to the current branch.

It is selective.

Suppose:

`main: A -> M1`

and:

`feature: A -> F1`

Cherry-picking `F1` onto `main` produces conceptually:

`main: A -> M1 -> F1'`

while the original feature branch remains:

`feature: A -> F1`

The target receives a new commit.

---

## 5.2 Typical Use Case

Cherry-pick is particularly useful when a specific fix needs to move to a release or maintenance branch without merging an entire development branch.

For example:

- a bug is fixed on `main`
- the release branch needs only that bug fix
- unrelated development should remain excluded

The release engineer can select the fix commit and cherry-pick it.

---

## 5.3 Basic Command

`git cherry-pick <commit>`

Multiple commits can be selected:

`git cherry-pick <commit-a> <commit-b>`

A contiguous range can be expressed with revision notation:

`git cherry-pick <oldest>^..<newest>`

The exact commit set should be reviewed carefully.

---

## 5.4 Commit Dependencies

Cherry-picking a commit does not automatically bring every earlier commit that the selected commit depends on.

Suppose:

`A -> B -> C`

and `C` depends on functionality introduced by `B`.

Cherry-picking only `C` may technically succeed while producing an incomplete application because the target branch lacks the required changes from `B`.

This is an important distinction:

**A successful cherry-pick means Git applied the patch successfully. It does not necessarily mean the resulting software behavior is correct.**

Testing and review remain necessary.

---

## 5.5 Cherry-pick Conflicts

If the selected patch conflicts with the target:

`git status`

After resolving the conflict:

`git add <resolved-files>`

`git cherry-pick --continue`

To abandon:

`git cherry-pick --abort`

If the selected commit becomes unnecessary or empty:

`git cherry-pick --skip`

---

# 6. Rebase Versus Cherry-pick

| Property | Rebase | Cherry-pick |
|---|---|---|
| Main purpose | Move/replay a sequence of commits | Selectively apply particular commits |
| Typical scope | Branch history | Individual or selected commits |
| Creates new commits | Yes | Yes |
| Rewrites ancestry | Yes | Only creates target-side commits |
| Selectivity | Sequence-oriented | Commit-oriented |
| Common use | Updating feature branch | Backporting or transferring fixes |
| Conflict possible | Yes | Yes |
| Changes existing shared history | Potentially | Normally no, unless combined with other operations |

A useful conceptual distinction is:

**Rebase changes where a sequence of development commits is based.**

**Cherry-pick selects particular changes and applies them elsewhere.**

---

# 7. Stash

## 7.1 Definition

A stash temporarily stores unfinished changes.

A common situation is:

1. A developer is modifying a feature.
2. An urgent issue requires switching branches.
3. The current work is incomplete.
4. The developer needs a clean working tree.

A stash can preserve the unfinished work temporarily.

---

## 7.2 Basic Stash

`git stash push -m "WIP: feature work"`

After the operation, the working tree can become clean.

The stash can be inspected with:

`git stash list`

---

## 7.3 Apply Versus Pop

### Apply

`git stash apply stash@{0}`

Restores the changes while keeping the stash entry.

### Pop

`git stash pop stash@{0}`

Restores the changes and normally removes the stash entry if application succeeds.

A cautious workflow can use `apply` first, inspect the result, and remove the stash later when appropriate.

---

## 7.4 Inspecting a Stash

Statistics:

`git stash show --stat stash@{0}`

Detailed patch:

`git stash show --patch stash@{0}`

The Python and JavaScript implementations demonstrate both forms.

---

## 7.5 Untracked Files

A normal stash operation primarily concerns tracked working-tree changes.

To include untracked files:

`git stash push -u -m "WIP"`

The `-u` option means untracked files are included.

Ignored files can be included with:

`git stash push -a`

This should be used deliberately because ignored directories may contain:

- build artifacts
- caches
- generated files
- large binaries
- local environment data

---

## 7.6 Stash Branch

A stash can be moved into a dedicated branch:

`git stash branch recovered-work stash@{0}`

This creates a branch from the commit that was current when the stash was created and attempts to reapply the stash there.

This is useful when unfinished work no longer belongs naturally on the branch where it was originally created.

---

## 7.7 Stash Limitations

A stash is not a substitute for durable version history.

Important work is generally easier to reason about when represented by:

- a branch
- a commit
- a remote copy when appropriate

A long-lived stash collection can become difficult to understand because stash entries are temporary working states rather than a clean project history.

---

# 8. Reflog

## 8.1 Definition

The reflog records local movements of references.

Typical operations recorded by reflog include:

- commits
- branch switching
- resets
- rebases
- checkouts
- reference movement

The primary command is:

`git reflog`

---

## 8.2 Reflog Versus Log

This distinction is fundamental.

### Git log

`git log`

primarily answers:

**Which commits are reachable through this history?**

### Git reflog

`git reflog`

primarily answers:

**Where has this local reference pointed recently?**

This makes reflog particularly useful for recovery.

---

## 8.3 Recovery After Reset

Suppose the history is:

`A -> B -> C`

and the developer executes:

`git reset --hard HEAD~1`

The branch now points to:

`A -> B`

The previous position containing `C` may no longer be reachable from the branch's normal history.

The reflog can reveal the previous position.

Example:

`git reflog`

After identifying the desired commit, a cautious recovery method is:

`git switch -c recovery <commit>`

This creates a new branch without immediately moving the existing branch.

After verifying the recovered history, the developer can decide what permanent action is appropriate.

---

## 8.4 Reflog After Rebase

Rebase can rewrite branch history.

If the resulting history is not what was intended, reflog may show earlier reference positions.

A developer can inspect:

`git reflog`

and then investigate a candidate with:

`git show <commit>`

This makes reflog an important local safety mechanism when experimenting with history rewriting.

---

## 8.5 Reflog Is Not a Backup

Reflog is primarily local.

A different clone does not automatically receive the same reflog entries.

Reflog entries can also expire according to Git's maintenance and configuration behavior.

Therefore:

**Reflog is a recovery aid, not a replacement for backups or remote repository copies.**

---

# 9. Python Implementation

The Python implementation is the most comprehensive instructional implementation.

It demonstrates:

- Git availability validation
- temporary repository creation
- local Git configuration
- file manipulation
- commit creation
- branch creation
- history visualization
- rebase
- merge-base inspection
- branch comparison
- cherry-pick
- stash
- untracked-file stashing
- stash inspection
- stash branch
- reflog
- reset and recovery analysis
- error handling
- production considerations
- security considerations
- command reference

The script uses Python's `subprocess` module to execute actual Git commands.

This is useful because the educational examples demonstrate Git behavior itself rather than simulating Git with Python data structures.

---

## 9.1 Python Process Execution

The central abstraction is a function that executes:

`git ...`

inside a selected repository.

The implementation captures:

- standard output
- standard error
- return code

A failed Git command raises a dedicated `GitError`.

This is preferable to assuming that every Git command succeeds.

---

## 9.2 Python Repository Isolation

The script creates a temporary directory using Python's temporary-file facilities.

This has two educational benefits:

1. The examples can be reproduced.
2. An existing user repository is not modified.

The temporary repository is removed after execution.

---

## 9.3 Python Rebase Demonstration

The Python implementation creates:

- `main`
- `feature/profile`

The histories diverge.

The script then executes:

`git rebase main`

and compares the feature tip before and after rebase.

This demonstrates that the branch tip can change even when the logical feature changes remain similar.

---

## 9.4 Python Cherry-pick Demonstration

A focused fix is committed on a feature branch.

The script then switches to `main` and cherry-picks the selected commit.

The original source branch remains intact.

This demonstrates selective transfer rather than branch-history combination.

---

## 9.5 Python Stash Demonstration

The Python script creates unfinished changes and executes:

`git stash push -m "WIP: unfinished application change"`

It then demonstrates:

- stash listing
- statistics
- patch inspection
- applying a stash
- including untracked files
- stash branch creation

---

## 9.6 Python Reflog Demonstration

The script deliberately creates a commit, performs a reset, and examines:

`git reflog`

This shows how reflog can preserve evidence of previous reference positions after a branch has moved backward.

---

# 10. JavaScript Implementation

The JavaScript implementation approaches Git as an automation target.

It uses Node.js process APIs to execute Git commands.

This demonstrates how application-level automation can interact with Git while checking command outcomes.

---

## 10.1 Node.js Process Handling

The implementation uses `child_process.spawnSync()`.

The arguments are passed as separate process arguments rather than being assembled into a shell command for normal Git operations.

The program records:

- stdout
- stderr
- exit status

A custom `GitCommandError` represents unexpected failures.

---

## 10.2 Why Error Handling Matters

Git operations can fail for legitimate reasons.

Examples include:

- conflicts
- missing branches
- invalid commit references
- incomplete operations
- dirty working trees
- rejected updates

Automation must not treat a Git invocation as successful merely because the process was launched.

The JavaScript implementation explicitly checks exit status.

---

## 10.3 JavaScript Rebase

The Node.js implementation:

1. creates a feature branch
2. creates feature commits
3. adds a new main-branch commit
4. switches to the feature branch
5. executes rebase
6. compares the feature tip before and after rebase
7. displays the resulting graph

This demonstrates rebase as an automated workflow rather than only as an interactive command.

---

## 10.4 JavaScript Cherry-pick

The implementation creates a focused change on a feature branch and then applies that change to the main branch.

It also documents the important states:

- normal cherry-pick
- conflict
- continue
- skip
- abort

This distinction is essential for robust automation.

---

## 10.5 JavaScript Stash

The Node.js implementation demonstrates:

`git stash push -u`

and compares:

- `apply`
- `pop`
- stash inspection
- untracked-file handling
- stash branch creation

This models the type of Git automation that might be useful in release tooling or developer workflow utilities.

---

## 10.6 JavaScript Security

Passing arguments separately is important when building automation.

A dangerous approach would be to concatenate untrusted input into a shell command.

For example, an application should not blindly construct shell text from an arbitrary branch name or user-provided message.

Production systems should use a process API that safely separates:

- executable
- arguments
- working directory

---

# 11. C++ Release-Engineering Case Study

The C++ implementation models a more structured operational scenario.

## 11.1 Problem

A release engineering team needs to manage:

1. a main development branch
2. feature development
3. selective fixes
4. unfinished developer work
5. recovery after accidental history movement

The case study models these requirements through a `ReleaseRepository` class.

---

## 11.2 Architecture

The basic structure is:

`main program`

`-> ReleaseRepository`

`-> Git command execution`

`-> temporary Git repository`

The `ReleaseRepository` class exposes operations such as:

- `status()`
- `graph()`
- `switchBranch()`
- `createBranch()`
- `commit()`
- `rebaseOnto()`
- `cherryPick()`
- `stash()`
- `stashList()`
- `reflog()`
- `resetHard()`

This separates repository-level operations from the main scenario.

---

## 11.3 Rebase in the Release Workflow

The C++ case study creates a reporting feature.

The main branch receives a separate service improvement.

The reporting branch is rebased onto main.

The result models the common situation where a feature must be updated against the latest base before integration.

---

## 11.4 Cherry-pick in the Release Workflow

A critical input-validation fix is created separately.

The release line needs the fix without importing unrelated feature work.

Cherry-pick is used to selectively transfer the fix.

This corresponds to a common maintenance or release-management scenario.

---

## 11.5 Stash in the Release Workflow

The developer has unfinished changes.

An urgent release operation requires a clean working tree.

The unfinished work is stashed, the repository becomes clean, and the stash remains available for later restoration.

The case study also includes untracked files using the equivalent of:

`git stash push -u`

---

## 11.6 Reflog Recovery

The case study deliberately performs a hard reset after creating a commit.

The normal branch history no longer shows the removed tip.

The program then inspects reflog.

The intended lesson is not that every lost commit is permanently recoverable, but that Git's local reference history can provide a valuable recovery path after accidental operations.

---

# 12. Detailed Comparison

| Mechanism | Main Purpose | Changes Existing Commit Objects? | Creates New Commits? | Typical Scope |
|---|---|---:|---:|---|
| Rebase | Replay commits on a new base | No, but rewrites branch history around recreated commits | Yes | Sequence of commits |
| Cherry-pick | Transfer selected changes | No | Yes | One or more selected commits |
| Stash | Temporarily preserve unfinished work | No | Internally records stash state | Working-tree changes |
| Reflog | Track local reference movement | No | No new project commit required | Reference history |

---

# 13. Important Distinctions

## Rebase Is Not a Merge

Rebase does not combine two histories by creating a merge relationship.

Instead, it replays commits onto another base.

## Cherry-pick Is Not Branch Movement

Cherry-pick does not move the source branch.

It applies the selected change to the current branch and creates a new target-side commit.

## Stash Is Not a Commit Workflow

A stash is temporary working storage.

It should not automatically replace a meaningful branch and commit history.

## Reflog Is Not Git Log

Git log presents reachable commit history.

Reflog records local movements of references.

---

# 14. Edge Cases

## 14.1 Rebase with Local Changes

Git may refuse to rebase if local changes could be overwritten.

A developer may need to:

- commit the work
- stash the work
- otherwise arrange a clean working state

The exact choice depends on the work and workflow.

---

## 14.2 Rebase Conflict

A replayed patch may conflict with changes in the new base.

Required actions can include:

`git status`

Resolve the file.

`git add <file>`

Then:

`git rebase --continue`

Or abandon:

`git rebase --abort`

---

## 14.3 Cherry-pick Conflict

Cherry-pick can also conflict.

The state must be resolved using:

`git cherry-pick --continue`

or abandoned using:

`git cherry-pick --abort`

---

## 14.4 Empty Cherry-pick

A target branch may already contain an equivalent change.

Git can therefore produce an empty cherry-pick.

Depending on the situation:

`git cherry-pick --skip`

can move past the unnecessary operation.

---

## 14.5 Stash Conflict

A stash can conflict when reapplied if the working tree has changed substantially since the stash was created.

A successful stash creation does not guarantee conflict-free restoration.

---

## 14.6 Reflog Expiration

Reflog entries are not permanent.

Repository maintenance and configuration influence how long entries remain available.

This is why important history should not depend exclusively on reflog recovery.

---

# 15. Common Mistakes

## Mistake 1: Rebasing shared history casually

Rebase changes commit identities.

If other developers already use those commits, rewriting them can disrupt collaboration.

## Mistake 2: Force pushing without understanding the remote state

Unconditional force pushing can overwrite remote work.

`--force-with-lease` provides a safer mechanism for many intentional history rewrites.

## Mistake 3: Cherry-picking a dependent commit alone

A patch can apply successfully but still depend on functionality missing from the target branch.

## Mistake 4: Keeping important work only in stash

A forgotten stash is harder to maintain than a well-named branch with meaningful commits.

## Mistake 5: Assuming reflog is a permanent backup

Reflog is local and subject to expiration.

## Mistake 6: Treating Git success as application correctness

Git can successfully perform a history operation while the resulting software still contains a logical error.

Testing and review remain separate responsibilities.

## Mistake 7: Ignoring conflicts in automation

A release script should stop and request human resolution when semantic source conflicts cannot safely be resolved automatically.

---

# 16. Best Practices

## Rebase

- Rebase local work according to project policy.
- Keep commits focused.
- Resolve conflicts carefully.
- Understand that rebased commits receive new identities.
- Avoid rewriting shared history without coordination.
- Use `--force-with-lease` when an intentional rewrite must be published.

## Cherry-pick

- Prefer cohesive commits.
- Understand commit dependencies before selecting a patch.
- Use it for genuinely selective transfers.
- Test the target branch after applying the patch.
- Handle conflicts explicitly.

## Stash

- Give stashes descriptive messages.
- Keep stash lifetime reasonably short.
- Use `-u` deliberately when untracked files matter.
- Avoid using stash as long-term project history.
- Inspect a stash before applying it when the target branch has changed substantially.

## Reflog

- Inspect reflog after accidental resets or rebases.
- Verify recovery candidates with `git show`.
- Create a recovery branch before modifying an existing branch when practical.
- Do not treat reflog as a backup strategy.

---

# 17. Performance Considerations

## Rebase

If `N` commits are replayed, the conceptual amount of work grows with the number of commits and the size and complexity of their patches.

A simplified model is:

`O(N + P)`

where `P` represents the patch-processing workload.

Large binary changes and conflict-heavy histories can increase practical cost.

## Cherry-pick

For `K` selected commits, the conceptual work depends on:

`O(K + P_selected)`

where `P_selected` represents the patches being applied.

The primary difficulty is often dependency correctness rather than raw execution time.

## Stash

Stash cost depends on the amount of changed data.

Including ignored files can greatly increase the amount of data involved, particularly when ignored directories contain generated artifacts.

## Reflog

Reflog operations concern retained reference-history records.

The practical cost depends on repository metadata and the number of entries being inspected.

---

# 18. Security Considerations

Git history can contain sensitive information.

Deleting a secret in a later commit does not necessarily remove the earlier secret from repository history.

If a secret is committed:

1. Rotate or revoke the secret.
2. Determine where the repository history has been copied.
3. Assess exposure.
4. Rewrite sensitive history when appropriate.
5. Coordinate cleanup of affected repository copies.

The four mechanisms in this study do not themselves constitute a secret-removal strategy.

### Automation Security

When Git is controlled by an application:

- do not concatenate untrusted values into shell commands
- validate branch and revision names
- capture process exit codes
- inspect stderr
- avoid automatically resolving arbitrary conflicts
- restrict credentials used by automation
- use least-privilege repository access

The JavaScript implementation demonstrates separate process arguments for normal Git execution.

The C++ case study uses internally controlled values for its educational command construction. A production implementation should use a safer argument-based subprocess API when arbitrary external input is accepted.

---

# 19. Production Considerations

A production Git automation system should verify repository state before destructive operations.

Useful checks include:

`git status --porcelain`

`git branch --show-current`

`git rev-parse HEAD`

`git log --oneline`

Before rebasing, cherry-picking, resetting, or force-pushing, the system should establish:

- which repository is being modified
- which branch is active
- which commit is expected
- whether uncommitted changes exist
- whether another operation is already in progress
- whether remote state has changed

A production tool should also log operations and preserve sufficient diagnostics to understand failures.

---

# 20. Conflict Management

Conflicts are one of the most important practical aspects of advanced Git.

## Rebase Conflict State

Use:

`git status`

Resolve:

`git add <resolved-files>`

Continue:

`git rebase --continue`

Abort:

`git rebase --abort`

## Cherry-pick Conflict State

Use:

`git status`

Resolve:

`git add <resolved-files>`

Continue:

`git cherry-pick --continue`

Abort:

`git cherry-pick --abort`

The critical principle is that Git's conflict markers identify incompatible content, but a developer must determine the correct intended behavior.

---

# 21. Recovery Model

A useful mental model for Git recovery is:

1. Identify the operation that changed the reference.
2. Inspect reflog.
3. Locate candidate commits.
4. Verify candidates with `git show`.
5. Create a recovery branch when practical.
6. Validate the recovered content.
7. Only then decide whether an existing branch should be moved.

For example:

`git reflog`

then:

`git show <candidate>`

then:

`git switch -c recovery <candidate>`

This sequence reduces the risk of compounding an accidental history operation with another destructive operation.

---

# 22. Language-Specific Learning

## Python

Python is particularly useful for demonstrating:

- subprocess automation
- structured error handling
- temporary repositories
- reusable Git helper functions
- automated demonstrations
- validation and study workflows

The Python implementation is intentionally tutorial-oriented and contains the broadest conceptual coverage.

## JavaScript

Node.js is useful when Git functionality needs to interact with:

- developer tools
- web applications
- build systems
- release automation
- event-driven application logic
- CI/CD utilities

The JavaScript implementation focuses on process control, command-result handling, and automation safety.

## C++

C++ is useful for demonstrating:

- explicit architecture
- classes
- deterministic resource handling
- standard-library filesystem operations
- structured exception handling
- systems-oriented automation
- performance-conscious design

The C++ implementation therefore treats Git as an external release-engineering subsystem and wraps common operations in a dedicated repository class.

---

# 23. Practical Command Reference

## History

`git log --graph --oneline --decorate --all`

`git show <commit>`

`git diff <base>...<branch>`

`git merge-base <branch-a> <branch-b>`

## Rebase

`git rebase <base>`

`git rebase -i HEAD~N`

`git rebase --continue`

`git rebase --skip`

`git rebase --abort`

`git rebase --show-current-patch`

## Cherry-pick

`git cherry-pick <commit>`

`git cherry-pick <commit-a> <commit-b>`

`git cherry-pick <oldest>^..<newest>`

`git cherry-pick --continue`

`git cherry-pick --skip`

`git cherry-pick --abort`

## Stash

`git stash push -m "message"`

`git stash push -u -m "message"`

`git stash list`

`git stash show --stat stash@{0}`

`git stash show --patch stash@{0}`

`git stash apply stash@{0}`

`git stash pop stash@{0}`

`git stash drop stash@{0}`

`git stash branch <branch> stash@{0}`

## Reflog

`git reflog`

`git reflog show <branch>`

`git show <commit>`

`git switch -c recovery <commit>`

`git reset --hard <commit>`

## Publishing an Intentional Rewrite

`git push --force-with-lease`

---

# 24. Conceptual Decision Guide

When the requirement is to **update a feature branch onto a new base**, rebase is the relevant mechanism.

When the requirement is to **transfer one particular fix**, cherry-pick is the relevant mechanism.

When the requirement is to **temporarily put unfinished changes aside**, stash is the relevant mechanism.

When the requirement is to **investigate where a local reference previously pointed**, reflog is the relevant mechanism.

These mechanisms solve different problems and can also appear together in a single workflow.

For example:

1. A developer stashes unfinished work.
2. The developer updates a feature branch with rebase.
3. A release engineer cherry-picks a specific fix.
4. An accidental reset is later investigated through reflog.

The commands are different because the underlying repository-state problems are different.

---

# 25. Core Technical Principles

The four mechanisms can be remembered through their fundamental operations:

**Rebase:** replay a sequence of commits on a different base.

**Cherry-pick:** apply a selected commit's change to another location.

**Stash:** temporarily preserve unfinished working changes.

**Reflog:** record local movements of references for inspection and recovery.

Understanding Git in terms of commits, parents, branches, references, working-tree state, and patches makes these commands predictable rather than merely memorized.

The Python, JavaScript, and C++ implementations demonstrate these mechanisms through actual repositories, real Git commands, error states, recovery analysis, and production-oriented design considerations.

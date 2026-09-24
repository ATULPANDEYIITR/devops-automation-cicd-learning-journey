# Git conflicts: conflict detection, resolution, and merge strategies

## Topic introduction

A Git conflict occurs when Git cannot safely combine changes from divergent histories using its merge rules. The important idea is that a conflict is not simply caused by two people editing the same file. Git can often merge independent edits automatically. A conflict occurs when the available information is insufficient to determine a single safe result.

This topic requires understanding three related objects:

- the **merge base**, which represents the common starting point of the divergent histories
- **ours**, which normally represents the current branch being merged into
- **theirs**, which normally represents the branch or commit being integrated

A three-way merge compares those three states rather than comparing only the two branch tips.

The implementations in this repository model those concepts progressively:

- Python provides a broad educational merge engine, commit graph model, validation routines, resolution policies, rerere modeling, and optional real-Git integration.
- JavaScript demonstrates the same central mechanics with JavaScript data structures, dynamic programming for line comparison, validation, caching, and optional execution of real Git commands.
- C++ develops an industry-style deployment-configuration case study with typed data structures, a merge engine, validation, a resolution cache, a commit graph, tests, and explicit complexity considerations.

## Fundamental concepts

### Repository history

Git stores project history as commits. A commit identifies a snapshot of the project and points to one or more parent commits.

A normal commit has one parent:

`A -> B -> C`

A merge commit normally has two parents:

`A -> B ----> M`
`     \      /`
`      C ---`

The merge commit records that two lines of development have been combined.

### Branches

A branch is essentially a movable reference to a commit. When two branches point to descendants of a common ancestor, their histories may have diverged.

For example:

`A -> B -> C`  
` \-> D -> E`

The common ancestor `A` is a candidate merge base.

### Merge base

The merge base is the commit Git uses as the reference point for a three-way merge.

Conceptually:

`base -> ours`

and

`base -> theirs`

Git compares what each side changed relative to the base.

This distinction is important because the same final text on two branches does not necessarily have the same meaning as an unchanged file. The base provides the information required to determine which side actually changed.

### Ours and theirs

The terms have operational meanings rather than universal semantic meanings.

During a normal merge:

- **ours** generally refers to the current branch, represented by `HEAD`
- **theirs** generally refers to the incoming branch being merged

During a rebase, terminology can be confusing because commits are replayed and the apparent roles of current and incoming changes can differ from what a user expects from an ordinary merge.

For this reason, a resolution should be based on the intended final state rather than blindly choosing a side.

## The three-way merge model

Consider a file with this base state:

`timeout=30`

Suppose the current branch changes it to:

`timeout=60`

and the incoming branch changes it to:

`timeout=120`

Git sees:

- base: `30`
- ours: `60`
- theirs: `120`

Both sides changed the base differently. Git therefore needs human or configured merge logic to determine the final value.

By contrast, suppose the incoming branch changes only another file while the current branch changes `timeout`.

Git can normally combine the two changes automatically.

The central rule used by the Python, JavaScript, and C++ educational implementations is:

1. If ours and theirs are identical, the result is that common state.
2. If ours equals the base, accept theirs.
3. If theirs equals the base, accept ours.
4. If both sides changed differently, classify the situation as a conflict.

Real Git has substantially more sophisticated content-merging behavior than this simplified file-level model.

## Conflict detection

Conflict detection takes place after Git has identified the relevant merge base and compared the divergent trees.

A conflict can arise from different forms of change.

### Content conflict

Both branches modify a common base state differently.

Example:

Base:

`workers=4`

Ours:

`workers=8`

Theirs:

`workers=16`

There is no universally correct textual result.

### Add/add conflict

The file did not exist in the merge base, but both branches create the same path with different contents.

Example:

Base:

`<absent>`

Ours:

`service.conf` containing one configuration

Theirs:

`service.conf` containing another configuration

Git cannot simply choose one without considering the intended result.

### Modify/delete conflict

One branch modifies a file while the other deletes it.

The result requires a decision about whether the file should survive and, if so, which content should be retained.

### Delete/modify conflict

The same underlying situation is observed from the opposite branch perspective: one side deletes the file while the other modifies it.

The Python and C++ implementations explicitly classify these cases.

### Rename-related conflicts

Git can detect renames by comparing deleted and added paths and evaluating content similarity. A rename is therefore not best understood as an immutable special object that always survives unchanged. Rename detection is an inference made from tree changes.

A rename can become complicated when:

- both branches rename the same file differently
- a renamed file is also modified
- one branch deletes a file while another renames it
- both branches modify the same renamed file
- directory restructuring creates multiple plausible rename relationships

The exact behavior depends on Git's merge machinery, similarity detection, and repository history.

## Conflict markers

A traditional textual conflict can appear in a working-tree file using markers resembling:

`<<<<<<< HEAD`

followed by the current branch's content, then:

`=======`

followed by incoming content, and finally:

`>>>>>>> incoming`

These markers identify competing regions.

The Python, JavaScript, and C++ programs generate an educational representation of these markers.

Conflict markers are not a valid final representation for most source files. Leaving them unresolved can cause:

- syntax errors
- configuration failures
- invalid data
- incorrect business behavior
- accidental deployment of the wrong implementation

Searching for conflict-marker strings is useful as a safeguard, but it is not sufficient validation. A program can contain no markers and still be incorrect.

## Python implementation

The Python implementation begins with a simplified representation of a Git file tree.

`FileSnapshot` represents either an existing file or an absent file. `Commit` represents a commit containing a tree, parents, and a message. `Conflict` stores the merge base state and both divergent states.

The central function is `three_way_merge()`.

It constructs the union of all paths from:

- the base tree
- the current branch tree
- the incoming branch tree

Each path is then evaluated using the three-way rules.

This makes the algorithm suitable for learning the conceptual mechanism without requiring a Git repository.

### Python conflict classification

`detect_file_conflict()` distinguishes:

- `content`
- `add/add`
- `delete/modify`
- `modify/delete`

The implementation also demonstrates why file existence is part of merge state. A deletion is not merely an empty string. A deleted path and an empty file are different states.

### Python resolution policies

`ResolutionPolicy` defines:

- `OURS`
- `THEIRS`
- `MANUAL`

The manual option accepts an explicit final file value.

Choosing ours or theirs is a mechanical operation. It does not mean that the selected branch is semantically correct. A production resolution should be based on the intended application behavior.

### Python validation

The Python program provides two useful validation examples.

`validate_no_conflict_markers()` searches the resulting tree for unresolved markers.

`validate_python_syntax()` uses Python's compiler to check syntax without executing the source.

This illustrates an important distinction:

**conflict resolution and correctness validation are separate tasks.**

A clean merge can still introduce a logical defect.

### Python commit graph

`RepositoryGraph` models parent relationships and calculates a merge base.

The example creates:

- an initial commit
- a main-branch descendant
- a feature-branch descendant

Both descendants point back to the initial commit, making that commit the common base.

Real Git handles much more complicated graphs, including multiple merge bases and histories involving previous merges.

### Python rerere model

The `ConflictResolutionCache` class models the concept behind Git's rerere facility.

A conflict can be represented by a key derived from:

- path
- base content
- ours content
- theirs content

A previously recorded resolution can then be retrieved when an equivalent conflict appears again.

This is useful for repetitive integration work where the same conflict occurs repeatedly.

## JavaScript implementation

The JavaScript implementation uses classes and plain objects to model the same conceptual structures while emphasizing JavaScript-specific mechanisms.

`FileSnapshot`, `Conflict`, and `MergeResult` provide an object-oriented representation of merge state.

JavaScript's `Set` is used to construct the union of file paths.

### JavaScript line comparison

The JavaScript implementation includes a dynamic-programming longest-common-subsequence approach for identifying broad changed ranges.

This illustrates an important difference between:

- file-level conflict detection
- line-level difference analysis
- actual production merge algorithms

The educational algorithm is intentionally smaller than Git's merge machinery.

For two sequences with lengths `n` and `m`, the basic LCS dynamic-programming approach uses approximately:

- time: `O(nm)`
- memory: `O(nm)`

Optimized diff implementations can reduce memory or use different algorithms depending on requirements.

### JavaScript validation

The JavaScript implementation validates JSON with `JSON.parse()`.

This demonstrates a useful post-merge principle: validation should use the parser or compiler appropriate to the file type whenever practical.

For example:

- JSON should be parsed as JSON
- JavaScript should be syntax checked
- YAML should be parsed with an appropriate YAML parser
- SQL should be tested against a database-compatible parser or test environment
- application configuration should be validated against business constraints

### JavaScript real-Git integration

The optional real-Git demonstration uses `child_process.spawnSync()` with `shell: false`.

It can create a temporary repository, make divergent commits, perform a merge, inspect the resulting conflict, and abort the merge.

Using an argument array instead of constructing a shell command string reduces command-injection risk when arguments originate from external input.

The real-Git demonstration is disabled unless `RUN_REAL_GIT_DEMO=1` is supplied.

## C++ case study

The C++ program models a realistic deployment-configuration workflow.

The scenario contains a production configuration with:

- worker count
- timeout
- operating mode

Two branches then change the configuration independently.

One branch changes the timeout to `60`.

The other changes the worker count and timeout.

The merge engine detects the conflict.

The application then performs a semantic resolution by selecting:

`workers=8`

and:

`timeout=90`

The resulting configuration is parsed and validated.

This demonstrates why a conflict resolution should not be treated as simply selecting an entire branch. The correct final configuration may combine information from both sides and introduce a reviewed value.

### C++ data structures

The case study uses:

- `std::map` for deterministic file-tree representation
- `std::set` for path unions
- `std::vector` for collections and parent lists
- `std::optional` to distinguish a missing file from a present file
- `std::queue` for commit-graph traversal
- `std::map` for the resolution cache

`std::optional<std::string>` is especially useful because it explicitly represents the distinction between:

- file exists with empty content
- file does not exist

### Configuration validation

The `Configuration` class parses key-value configuration and validates:

- presence of required values
- integer conversion
- worker limits
- timeout limits

This adds a domain-level validation layer after merge resolution.

A Git merge engine cannot know whether `workers=8` or `workers=16` is appropriate for a particular production system. That decision belongs to the application and its engineering policies.

### Resolution cache

`ResolutionCache` models repeated conflict resolution.

The cache stores a resolution using the conflict's path and three states as the identifying material.

A production implementation must consider normalization, conflict shape, repository state, and invalidation behavior more carefully.

## Merge strategies

A merge strategy is the mechanism Git uses to combine histories or trees. Strategy selection and conflict-resolution options should not be treated as interchangeable concepts.

### Fast-forward

A fast-forward is possible when the current branch tip is an ancestor of the incoming commit.

Example:

`A -> B -> C`

If the current branch points to `B` and the incoming branch points to `C`, Git can move the current branch reference from `B` to `C`.

No merge commit is required.

A fast-forward therefore does not represent divergent history being reconciled through a merge commit.

### Three-way merge

A three-way merge uses:

- merge base
- current branch
- incoming branch

It can create a merge commit when histories have diverged.

This is the central model demonstrated by all three implementations.

### Ours and theirs

Ours and theirs are useful terms for describing side selection, but their exact meaning depends on the Git operation and the options being used.

A command that chooses one side of a conflicted file is not necessarily equivalent to a merge strategy that constructs an entire tree from one side.

This distinction is important because Git has both:

- merge strategies
- strategy options and conflict-resolution options

They operate at different levels.

### Recursive and ort merge machinery

Modern Git uses the `ort` merge strategy for ordinary two-head merges. Older documentation and historical explanations often discuss the recursive strategy.

The internal algorithms can perform considerably more sophisticated operations than the simplified file-level algorithm in these examples.

The educational implementations should therefore be understood as conceptual models, not replacements for Git's actual merge engine.

## Merge versus rebase

A merge combines divergent histories and can create a commit with multiple parents.

A rebase instead replays commits onto a different base and creates new commit objects.

Conceptually:

Original:

`A -> B -> C`

Feature:

`     \-> D -> E`

After rebasing the feature onto `C`, Git creates new commits conceptually represented as:

`A -> B -> C -> D' -> E'`

`D'` and `E'` are not the same commit objects as `D` and `E`.

This changes commit identities because commit metadata and parent relationships are part of commit identity.

### Merge advantages and trade-offs

A merge:

- preserves the topology of the divergent histories
- records that two lines of development were combined
- can produce an explicit merge commit
- avoids rewriting already-published feature commits

The resulting history can be more complex to read when many short-lived branches are merged.

### Rebase advantages and trade-offs

A rebase:

- creates a more linear history
- replays changes onto a new base
- creates new commit identities
- can require resolving conflicts during commit replay

Rewriting commits that other people already depend on can require coordination.

The choice is therefore a repository workflow decision rather than a universal technical rule.

## Conflict resolution workflow

A practical merge workflow can be represented as:

1. Identify the current repository state.
2. Identify whether the operation is a merge, rebase, cherry-pick, or another integration operation.
3. Inspect the conflict list.
4. Inspect the base and both divergent versions when necessary.
5. Understand the intended application behavior.
6. Edit the conflicted file or use an appropriate resolution mechanism.
7. Remove all unintended conflict markers.
8. Stage the resolved files.
9. Continue or complete the integration operation.
10. Run syntax checks, unit tests, integration tests, and relevant application validation.
11. Review the resulting diff.
12. Verify that no unrelated changes were introduced.

Useful diagnostic commands include:

`git status`

`git diff`

`git diff --cc`

`git diff --name-only --diff-filter=U`

`git ls-files -u`

The unmerged index information exposed by `git ls-files -u` is particularly useful for understanding that a conflicted path can have multiple index stages representing different versions.

## Edge cases

### Both sides make the same change

If both sides independently change a file from:

`mode=standard`

to:

`mode=fast`

the result is identical on both sides.

There is no need for a semantic choice between competing results.

### One side changes while the other does not

If the base contains:

`timeout=30`

and ours contains:

`timeout=60`

while theirs still contains:

`timeout=30`

the change can normally be accepted automatically.

### Both sides delete the same file

If both sides delete a file that existed in the base, there is no conflict because both sides agree on the final absence of the file.

### One side creates an empty file

An empty file is different from a deleted file.

A present file with `""` as content must not be treated as equivalent to an absent path.

### Binary files

Binary files cannot generally be resolved using ordinary line-based textual merging.

Resolution often requires selecting a complete version or regenerating the binary artifact from source.

### Generated files

Generated files can create noisy conflicts.

Where possible, generated artifacts should be regenerated from authoritative source rather than manually combining generated output.

### Lock files

Package manager lock files can have highly structured content. Manual editing can be error-prone because the file often represents a dependency graph rather than a simple list.

The appropriate validation mechanism should be used after resolution.

### Submodules

Submodules introduce another layer of commit references. A conflict may concern which submodule commit should be selected rather than ordinary file contents.

### Criss-cross histories

A complex history can contain more than one plausible merge base. Merge-base selection becomes more subtle than the simplified graph algorithm shown in these implementations.

### Directory renames

Directory-level restructuring can interact with file renames and modifications. Rename detection and directory restructuring are substantially more complicated than comparing two path strings.

## Common mistakes

### Editing only the visible conflict text

A conflict can involve surrounding code whose logic also needs review.

Removing markers is not equivalent to resolving the problem.

### Always choosing ours

Choosing ours mechanically can discard legitimate incoming functionality.

### Always choosing theirs

Choosing theirs mechanically can discard required local changes.

### Treating a clean merge as proof of correctness

Git can merge syntactically compatible changes that are semantically incompatible.

For example, two branches may independently alter values that remain valid individually but violate a cross-component invariant when combined.

### Forgetting deleted files

Deletion is a meaningful change and must be reviewed just like modification.

### Resolving without inspecting the base

The base explains what each branch actually changed.

Looking only at ours and theirs can make it harder to determine the intent of each modification.

### Skipping tests

A conflict resolution modifies source code or configuration. Tests are therefore part of the resolution process, not an optional cosmetic step.

### Continuing the operation prematurely

Files should be reviewed and staged deliberately before using the relevant continuation command.

### Confusing merge and rebase terminology

The meaning of ours and theirs can appear counterintuitive during rebase operations. The operation being performed should be identified before selecting a side.

## Conflict-resolution validation

A robust resolution can be checked at several levels.

### Structural validation

Check that:

- all intended files exist
- unwanted files were not deleted
- paths are correct
- configuration structure is valid

### Syntax validation

Compile or parse affected files.

The Python implementation demonstrates this with Python's `compile()` function.

The JavaScript implementation demonstrates JSON parsing.

The C++ implementation demonstrates parsing and validating a deployment configuration.

### Unit testing

Tests should target the affected behavior directly.

### Integration testing

If the conflict joins components that interact with each other, integration tests are required because individual components may remain valid while their combination is not.

### Review of the resulting diff

The final diff should be inspected to verify that the resolution contains exactly the intended changes.

### Search for unresolved markers

Searching for:

`<<<<<<<`

`=======`

`>>>>>>>`

is a useful final safeguard.

It should not be the only validation method.

## Performance considerations

A real repository may contain thousands or millions of paths and very large files.

The simplified file-level merge algorithm in the implementations is approximately proportional to the number of unique paths, excluding the cost of content comparisons.

The Python implementation uses sets and dictionaries for path lookup.

The JavaScript implementation uses `Set` and objects.

The C++ implementation uses ordered `std::map` and `std::set`.

Ordered C++ containers provide deterministic traversal but generally have `O(log n)` lookup and insertion complexity. Hash-based structures can provide expected `O(1)` lookup in many workloads.

Line-based comparison can be significantly more expensive than comparing whole-file identities. The JavaScript LCS demonstration has `O(nm)` time and `O(nm)` memory in the basic formulation.

Production merge engines use specialized algorithms and optimizations because repository histories and file sizes can be large.

## Security considerations

Git conflict handling can become a security concern when the merged result changes:

- authentication logic
- authorization checks
- input validation
- cryptographic code
- dependency versions
- deployment configuration
- access-control policy
- infrastructure definitions

A conflict resolution that removes a security check can be syntactically valid and still introduce a serious vulnerability.

External command execution also deserves care.

The JavaScript real-Git example uses `spawnSync()` with argument arrays and does not construct shell command strings from untrusted input.

The Python implementation uses `subprocess.run()` with a list of arguments and does not invoke a shell.

The C++ case study does not invoke external commands and therefore keeps the demonstration within the standard library.

## Implementation considerations

### Separate mechanics from policy

The merge engine determines whether changes can be combined mechanically.

The application or engineering team determines whether the resulting state is desirable.

These are different responsibilities.

### Preserve the base

The merge base should remain available during conflict analysis because it provides evidence about what each side changed.

### Keep resolution explicit

A manual resolution should represent an intentional final state.

### Validate after resolution

The merge operation itself does not understand every business invariant.

Validation should therefore be layered after the textual or structural merge.

### Prefer authoritative sources

For generated files, derived configuration, and compiled artifacts, resolving the source and regenerating the derived output can be safer than manually merging generated content.

### Use automation for repeated conflicts carefully

Conflict reuse can save time, but automatic reuse should be followed by validation. A conflict that looks similar can occur in a context where the previous resolution is no longer correct.

## Python, JavaScript, and C++ comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Primary purpose | Comprehensive conceptual model | Application-oriented model | Industry-style typed case study |
| File representation | Dataclass-based | Classes | Structs and classes |
| Path collection | `set` | `Set` | `std::set` |
| Merge result | Dataclass | Class | Struct |
| Commit graph | Dictionary and graph class | `Map` and graph class | `std::map` and queue |
| Validation | Python compiler and marker checks | JSON parser and marker checks | Configuration parser and domain validation |
| Conflict cache | Dictionary | `Map` | `std::map` |
| External Git | Optional subprocess integration | Optional child-process integration | Not required |
| Type system | Dynamic with type annotations | Dynamic | Static |
| Case-study emphasis | Merge mechanics | Runtime and application behavior | Typed architecture and validation |

Python is particularly effective for expressing the merge model concisely and building an educational simulator.

JavaScript is useful for demonstrating how conflict concepts can be integrated into application-side tooling and runtime-oriented workflows.

C++ makes the data model and resource-oriented architecture explicit and demonstrates how a merge subsystem could be incorporated into a strongly typed engineering application.

## Real-world applications

Git conflict knowledge is relevant to:

- software development teams
- release engineering
- DevOps workflows
- infrastructure-as-code repositories
- configuration management
- documentation maintenance
- dependency management
- monorepos
- open-source collaboration
- continuous integration systems
- deployment automation
- code review systems

The underlying principle is broader than Git: whenever two independently evolved states must be reconciled, the system needs a mechanism for identifying compatible changes and surfacing ambiguous changes.

## Important distinctions

### Conflict versus error

A conflict is an integration ambiguity.

A compile error is a language-level problem.

A test failure is a behavioral problem.

A deployment failure is an operational problem.

A conflict can lead to any of the others, but they are not the same event.

### Merge conflict versus merge commit

A merge conflict is a problem encountered while constructing a merge result.

A merge commit is a commit that records a completed merge between histories.

A merge can be clean and still produce a merge commit.

### Conflict markers versus Git index state

Conflict markers are a working-tree representation for many textual conflicts.

The Git index also records unmerged stages.

Therefore, checking only file text does not completely describe Git's internal conflict state.

### Mechanical resolution versus semantic resolution

Mechanical resolution selects or combines content according to merge rules.

Semantic resolution considers what the application is supposed to do.

The C++ deployment example intentionally demonstrates semantic resolution by constructing a valid final configuration rather than simply selecting one complete branch.

## Testing strategy

The three implementations include tests for important cases.

The test suite covers:

- clean one-sided changes
- identical changes
- content conflicts
- add/add conflicts
- modify/delete conflicts
- resolution caching

These tests illustrate a useful property of merge systems: conflict detection should be tested independently of conflict resolution.

A merge engine should be able to identify the conflict consistently even when different applications choose different final resolutions.

## Limitations of the educational implementations

The Python, JavaScript, and C++ implementations intentionally simplify several parts of Git.

They do not implement the complete Git object database.

They do not reproduce every Git diff algorithm.

They do not reproduce all rename and directory-rename heuristics.

They do not implement the full Git index format.

They do not reproduce every merge strategy or strategy option.

They do not model every form of binary-file handling.

They do not reproduce all multiple-merge-base cases.

They should therefore be treated as conceptual and engineering demonstrations rather than replacements for Git itself.

The optional real-Git demonstrations are included precisely to connect the simplified model to actual Git behavior.

## Production considerations

A production integration workflow should consider:

- repository branching conventions
- protected branches
- code review
- automated testing
- static analysis
- formatting
- dependency validation
- security testing
- configuration validation
- deployment checks
- rollback procedures
- auditability
- merge frequency
- conflict frequency
- ownership of sensitive files

Frequent conflicts can indicate architectural or workflow issues such as excessive coupling, long-lived branches, frequently edited shared configuration, or poorly separated ownership boundaries.

The presence of conflicts does not by itself identify a specific root cause. Conflict frequency should be analyzed together with repository structure, team workflow, and the nature of the changes.

## Practical command reference

`git status`

Shows the repository state and identifies an ongoing conflicted operation.

`git diff`

Displays working-tree differences.

`git diff --cc`

Displays combined differences for conflicted files.

`git diff --name-only --diff-filter=U`

Lists paths that are currently unmerged.

`git ls-files -u`

Displays unmerged index entries and their stages.

`git add <file>`

Stages a resolved file.

`git merge --continue`

Continues a merge after conflicts have been resolved and staged.

`git merge --abort`

Attempts to return to the state before the current merge.

`git rebase --continue`

Continues a rebase after resolving and staging a conflict.

`git rebase --abort`

Attempts to return to the state before the current rebase.

## Relationship between the three implementations

The implementations deliberately use different emphases.

The Python program is the most complete conceptual simulator. It contains the merge model, conflict classification, commit graph, strategy descriptions, validation, rerere modeling, rename similarity discussion, tests, and optional real-Git repository creation.

The JavaScript program focuses on runtime-oriented implementation. It demonstrates classes, `Set`, `Map`, dynamic programming, JSON validation, conflict caching, and safe child-process invocation.

The C++ program turns the merge concepts into a typed engineering case study. Its deployment configuration service demonstrates how merge mechanics can be separated from application-specific semantic validation and resolution policy.

Across all three languages, the essential model remains:

`merge base + ours + theirs -> merged result or conflict`

The critical engineering step after a conflict is not merely removing markers. It is establishing that the resulting state is structurally valid, syntactically valid, behaviorally correct, secure, and appropriate for the intended operational context.

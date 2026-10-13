# Code Quality Engineering: Linters, Formatters, and Static Analysis

## Purpose

Code quality engineering establishes repeatable rules for evaluating source code before it becomes part of a shared codebase. Linters, formatters, and static analyzers address different aspects of that process. They complement automated tests, code review, approval policies, and protected branches without replacing any of them.

This repository models code quality as a set of observable checks and enforceable repository policies. The implementations cover Python source inspection, JavaScript quality-gate evaluation, a C++ repository governance engine, a Java enterprise policy model, and a PostgreSQL relational representation of pull requests and their quality evidence.

The central engineering principle is that a quality decision should be explainable. A failed check should identify the affected source or rule, and a merge decision should identify every unmet policy condition.

## Code Quality Mechanisms

### Linters

A linter examines source code for violations of coding rules. Depending on the language and configuration, it can detect unused imports, suspicious expressions, inconsistent naming, risky exception handling, unreachable code, and other maintainability problems.

A lint finding generally identifies a rule, a severity, and a source location. A warning may indicate a maintainability concern, while an error may represent a policy violation that prevents a quality gate from passing.

Lint rules require careful configuration. An overly permissive configuration allows defects to remain undetected. An overly restrictive configuration can create enough false positives that developers stop paying attention to the results.

The Python implementation uses an explicit rule catalog with stable identifiers such as `CQ008` for syntax errors and `CQ014` for mutable default arguments. The JavaScript implementation applies corresponding language-specific rules, including strict equality, prohibited `debugger` statements, and risky use of `eval`.

These custom implementations illustrate rule processing. They are intentionally not full replacements for established parsers and production linting tools. In particular, simple text-based checks can mistake code inside comments or string literals for executable code. Scope-aware rules also require more sophisticated parsing and symbol resolution.

### Formatters

A formatter transforms source code into a consistent representation. Formatting rules can cover indentation, whitespace, line breaks, quote conventions, and expression layout.

The main objective is to remove unnecessary stylistic variation from code review. If a formatter consistently handles layout, reviewers can focus on logic, correctness, security, and architecture rather than manually correcting whitespace.

The Python formatter normalizes line endings, removes trailing whitespace, and ensures a final newline. The JavaScript formatter applies the same narrow transformations through JavaScript string operations.

These implementations are deliberately conservative. They do not rewrite syntax or claim to implement the complete formatting rules of Black, Ruff, Prettier, or another production formatter.

A formatter check and a formatter write operation are distinct operations. A write operation changes a file. A check operation compares the existing source against its formatted representation and reports a difference without modifying the source.

### Static Analysis

Static analysis examines source code or its structure without requiring the complete application to execute normally. It can identify potential defects, suspicious data flows, unsafe operations, complexity problems, and violations of architectural rules.

Static analysis varies in depth. A lexical rule may inspect one line. An abstract syntax tree provides structural information about functions, imports, expressions, and control flow. More advanced analysis can track values between statements or across functions.

The Python analyzer uses the standard library's `ast` module to inspect functions, imported names, parameter counts, mutable defaults, and approximate cyclomatic complexity. It also validates syntax and produces structured findings.

The JavaScript implementation deliberately separates lightweight source checks from repository-level policy evaluation. This reflects an important distinction: a file can pass linting while its pull request remains ineligible for merge because tests failed or required reviews are incomplete.

## How the Mechanisms Relate

| Mechanism | Primary question | Typical output | What it does not establish |
|---|---|---|---|
| Formatter | Is the source represented consistently? | Reformatted source or a formatting difference | Correct business behavior |
| Linter | Does the source violate configured coding rules? | Rule identifiers and source locations | Full runtime correctness |
| Static analyzer | Does the source contain patterns associated with defects or policy violations? | Potential defects, structural findings, risk indicators | That every reported path is reachable or defective |
| Automated tests | Does the program behave as expected for the tested inputs? | Pass, fail, assertions, and execution traces | Correctness for all possible inputs |
| Code review | Are the proposed changes technically acceptable? | Comments, requested changes, approval decisions | Automatic enforcement of every repository policy |
| Branch protection | Are repository-level merge conditions satisfied? | Merge restrictions and policy failures | That every accepted change is defect-free |

A production quality pipeline normally combines these mechanisms. Formatting and linting can run quickly on every proposed change. Static analysis and tests can run in parallel where appropriate. Their results become status checks that repository policy can require before merging.

## Repository Workflow

The implementations use the following conceptual workflow:

- A developer creates a source branch and opens a pull request against a target branch.
- The proposed changes are inspected by formatting, linting, static analysis, and automated tests.
- Reviewers inspect the changeset, discuss defects, and record review decisions.
- Required checks and eligible approvals are evaluated against the current source revision.
- Branch protection determines whether the proposed change satisfies repository-level merge conditions.
- A merge is allowed only when the applicable conditions are satisfied.

The checks must correspond to the commit being merged. A passing test result for an earlier commit does not establish that newly pushed code passes the same test suite. The same concern applies to approvals when repository policy dismisses stale approvals.

## Python Implementation

The Python program, `code_quality.py`, combines a lightweight rule engine, a formatting demonstration, syntax validation, recursive file scanning, JSON reporting, and regression tests.

### Rule representation

Each finding is represented by a `Finding` object containing a rule identifier, severity, message, file path, line number, and column number. This structure makes results suitable for both console output and machine-readable reports.

The `QualityReport` class aggregates findings and computes counts by severity and rule. Its JSON representation can be consumed by a local development workflow or a continuous integration step.

### Source inspection

`PythonQualityAnalyzer.analyze_text()` begins with source-level checks for excessive line length, trailing whitespace, tabs used for indentation, and several risky patterns. It then parses the source using `ast.parse()`.

The syntax parser provides a reliable boundary between syntactically valid Python and source that cannot be analyzed structurally. When parsing fails, the analyzer reports a syntax finding instead of attempting AST-based rules against an invalid tree.

The AST analysis detects:

- Imported names that do not appear to be used.
- Wildcard imports that obscure the names introduced into a module.
- Functions with more parameters than the configured limit.
- Functions whose source spans exceed the configured length.
- Functions whose approximate cyclomatic complexity exceeds the configured limit.
- Mutable list, dictionary, or set literals used as function defaults.

The unused-import rule is intentionally conservative in scope. It does not implement full name binding or determine whether an imported symbol is re-exported through a public module interface. Production linting should use a tool with appropriate semantic analysis for those cases.

### Complexity measurement

The `complexity_of()` function starts a function at complexity one and increases the score for branches, exception handlers, Boolean operators, and conditional expressions.

Cyclomatic complexity approximates the number of independent paths through a function. It can help identify code that deserves closer inspection, but it is not a direct measurement of maintainability or defect probability.

The implementation excludes nested function bodies from the enclosing function's score. Without that boundary, a nested helper's branches could incorrectly inflate the score of its parent.

### Repository scanning and exit codes

`scan_repository()` recursively discovers Python files while excluding common generated directories and virtual environments. It handles file-reading errors and syntax failures as reportable conditions.

The command-line interface supports a target directory, configurable line length, optional JSON output, a warning-sensitive failure policy, and self-tests.

The exit-code contract is suitable for automation:

- `0` indicates that the configured failure policy was satisfied.
- `1` indicates blocking findings or a failed self-test.
- `2` indicates a scan configuration or operational failure.

The built-in tests verify syntax detection, mutable-default detection, formatter idempotence, complexity calculation, configuration validation, and directory exclusions.

### Limitations

The formatter performs only narrow text transformations. It does not wrap expressions or restructure syntax. The lint rules that rely on regular expressions can produce false positives when a pattern appears in a comment or string literal. The AST-based rules also use simplified name analysis.

These constraints are explicit so the implementation can be used as a learning model without being mistaken for a complete production linting system.

## JavaScript Implementation

The JavaScript program, `code-quality.js`, models quality checks as inputs to a pull-request decision rather than treating the presence of source findings as the entire governance process.

### Lightweight source analysis

`lintSource()` normalizes line endings and produces a `QualityReport`. Its rule set checks final newlines, line length, trailing whitespace, `debugger` statements, optional console logging restrictions, loose equality, `eval`, and empty catch blocks.

The rule for loose equality illustrates a common static-analysis concern. Expressions such as `value == 1` can apply implicit type conversion, which may produce behavior that is not immediately apparent from the source. Strict equality is generally easier to reason about when coercion is not intended.

The `eval` rule identifies a different concern. Dynamic evaluation complicates code review and can create injection risks when untrusted input reaches the evaluated expression.

These checks are line-oriented examples. They are not a complete JavaScript parser and should not be used as the sole security control for a production application.

### Event-driven workflow

`PullRequestQualityWorkflow` records immutable event snapshots for inspections and quality-gate evaluations. The event history gives the model an auditable sequence of actions without coupling policy evaluation to a particular user interface.

Its `evaluatePullRequest()` method evaluates evidence such as test status, lint status, formatting status, static-analysis status, unresolved discussions, approvals, stale approvals, and merge conflicts.

The evidence is deliberately separate from the source linter. A lint finding is a file-level observation. A failed lint status is a pipeline result. A merge blocker is a repository-policy decision.

The distinction allows a quality pipeline to evolve independently from the repository's review requirements.

### Asynchronous file inspection

`inspectFile()` reads source with Node.js file-system promises. The `await` expression allows the method to suspend while file I/O completes, and its caller receives a promise representing the inspection operation.

The program resolves a supplied file path before reading it and handles operational errors at the entry point. A production service accepting paths from untrusted users would also need an explicit allowed-root policy to prevent access to unintended files.

The built-in tests check lint rules, formatter idempotence, quality-gate outcomes, and event recording. Run them with `node code-quality.js --self-test`.

## C++ Case Study: Repository Governance Engine

The C++ program models a release repository where changes can be merged into a protected `main` branch only after satisfying code quality, review, and branch governance rules.

### Domain model

`PullRequest` stores the proposed changeset's identifying information, source revision, branch relationship, current state, and quality evidence.

`Reviewer` captures whether a reviewer is active, authorized to review code, the author, or an automated identity. `Review` records the decision and the exact commit that was reviewed.

`BranchPolicy` represents repository governance. It defines required quality checks, the number of approvals, synchronization requirements, linear-history restrictions, and restrictions on direct pushes, force pushes, and deletion.

`Repository` owns these records and provides operations for registering reviewers, creating pull requests, submitting reviews, updating quality evidence, and evaluating merge eligibility.

### Merge eligibility

`Repository::evaluate()` evaluates the proposed merge and returns a `GateResult`. Rather than stopping after the first failure, the engine collects blockers for conditions such as failed static analysis, unresolved review discussions, insufficient approvals, stale approvals, conflicts, draft status, and a source branch that is not synchronized with the base.

The result also records the number of valid approvals and passing quality checks. These values make a blocked decision easier to explain and diagnose.

The example requires linear history. Under that policy, a merge-commit strategy is rejected, while squash and rebase strategies remain candidates if all other requirements pass.

The strategy restriction does not make squash or rebase universally preferable. Teams must choose policies appropriate to their release and audit requirements.

### Reviewer eligibility and stale decisions

The engine excludes inactive reviewers, bots, unauthorized reviewers, and the pull request author from approval counts. A review must identify the commit it evaluates.

When a new source commit is pushed, the configured policy dismisses approvals tied to an earlier commit. Reviewers must then reassess the changed source.

The model stores one current review decision per reviewer. A production implementation may need a richer history of review submissions, dismissals, and review-thread resolution events.

### Branch restrictions and limitations

Direct-push, force-push, and branch-deletion checks are represented separately from pull-request merge eligibility. This separation is intentional: restrictions on how a branch may be modified are not the same as the conditions for accepting a proposed change.

The example models administrator bypass as a policy option, but does not implement a real authentication or authorization system. A production implementation must identify the authenticated actor, apply the actual hosting platform's rules, and record any authorized bypass in an audit trail.

The C++ program compiles with C++17 and uses standard-library containers. Repository lookup uses `std::map`, giving logarithmic lookup and insertion in the number of stored requests or reviewers. The engine evaluates a request by examining its current reviews and policy requirements, so evaluation cost grows with the number of recorded reviews and configured checks.

## Java Implementation: Enterprise Governance Service

The Java program provides a complementary domain model built around explicit records, enumerated states, immutable policy configuration, and a service responsible for merge eligibility.

### Domain types

`Reviewer`, `ReviewDecision`, `StatusCheck`, and `BranchProtectionPolicy` are Java records. Their compact constructors validate essential fields and make the value objects concise.

`ReviewState`, `CheckStatus`, and `MergeMethod` are enums. These types prevent arbitrary strings from being used wherever the model expects a recognized decision, check state, or merge strategy.

The branch policy stores a set of required check names. Its constructor creates an unmodifiable copy so that a caller cannot change the effective policy through a mutable set passed to the constructor.

### Pull-request state

The `PullRequest` class stores its current source commit, branch synchronization state, merge-conflict state, review decisions, and status-check results.

Its methods validate state transitions. A closed pull request cannot receive a new review or check result. A new source commit invalidates checks attached to older commits and can dismiss stale approvals.

Status-check evidence includes both a check name and a commit SHA. A passing result is accepted only when it belongs to the current source commit. This prevents an old successful pipeline run from satisfying a current quality requirement.

### Governance service

`GovernanceService` registers reviewers, opens pull requests, evaluates policy, and performs the modeled merge operation.

The evaluation service distinguishes several failure classes:

- The pull request may be closed, a draft, or affected by merge conflicts.
- The source branch may not be synchronized with the target branch.
- Required review conversations may remain unresolved.
- The current approval count may be insufficient.
- Required quality checks may be missing, failing, pending, or stale.
- A selected merge method may violate the configured linear-history policy.

The method returns an immutable `GateResult` with all identified blockers and applicable policy warnings.

### Enterprise implications

Explicit domain types make policy logic easier to test than a collection of unrelated conditional print statements. Centralizing merge eligibility also prevents separate callers from accidentally applying different rules to the same pull request.

The example still uses an in-memory model. A deployed governance service would need persistent storage, concurrent-update protection, authenticated identities, transaction boundaries, authorization checks, audit records, and integration with the source-control provider.

## PostgreSQL Data Model

The SQL script stores repository governance information relationally. It uses PostgreSQL identity columns, foreign keys, check constraints, partial indexes, views, and common table expressions.

### Repositories, branches, and policies

`repositories` identifies a repository and its default branch. `repository_members` represents repository-level reviewer eligibility. `branches` identifies branch names and current head commits.

`branch_protection_policies` stores governance requirements for a protected branch. Quality requirements, review requirements, branch synchronization, linear history, direct-push restrictions, force-push restrictions, deletion restrictions, administrator bypass, and stale-approval behavior are represented as separate fields.

This structure avoids treating all policy conditions as one undifferentiated quality score.

### Pull requests and commits

`pull_requests` stores the source and target relationship, current source revision, lifecycle state, draft status, synchronization state, conflict status, and merge method.

`commits` and `changed_files` model the changeset associated with a proposed change. Their foreign keys preserve the relationship between a pull request, its commits, and the files modified by those commits.

The sample uses stable identifiers to make the demonstration rerunnable. In a production application, source-control identifiers would normally be reconciled with the hosting provider's records.

### Reviews and discussions

`reviews` records reviewer decisions and the commit SHA against which the review was submitted. This permits the database to distinguish a current approval from an approval that predates a source change.

`review_comments` stores file paths, optional line numbers, comment sides, resolution states, and timestamps. Its resolution constraint prevents a record from being marked unresolved while also carrying a resolution timestamp, or marked resolved without one.

Inline comments and overall review decisions are related but distinct. Resolving a comment does not automatically imply approval, and approval does not prove that every discussion is resolved.

### Status checks

`status_checks` stores a named pipeline result, its source commit, its state, and its completion timestamp.

The schema enforces valid check states and consistent completion timestamps. Pending checks have no completion timestamp, while completed, failed, or cancelled checks require one.

The model retains multiple results over time. This is important because a newer result may supersede an earlier result for the same check name.

### Indexing and query behavior

The script creates indexes for repository lifecycle filtering, review-state lookups, reviewer history, unresolved comments, recent status checks, and commit history.

The partial index on unresolved comments is designed for queries that repeatedly locate open discussions without scanning resolved comments through that index.

`current_valid_approvals` joins reviews to repository membership and excludes authors, inactive reviewers, bots, unauthorized reviewers, and stale approvals when the branch policy requires dismissal.

`pull_request_quality_status` uses common table expressions to aggregate approvals, unresolved comments, and passing required checks. It compares check results with the pull request's current head SHA so that stale results do not satisfy the quality gate.

The final eligibility query produces a blocker array. A single pull request can therefore expose multiple independent reasons for being blocked, which is more useful operationally than returning only a Boolean result.

### Transactional behavior and enforcement boundaries

The script runs the schema and sample-data setup in a transaction. If an unhandled SQL error occurs while the script is executed with `ON_ERROR_STOP`, PostgreSQL can roll back the transaction instead of leaving a partially initialized sample.

Database constraints protect data integrity, but the schema alone does not provide a complete Git hosting authorization system. For example, the current source SHA in a pull request must be maintained consistently with its commit records, and branch protection must be enforced by the actual merge operation. Production implementations should use transactional procedures or application services to enforce cross-table invariants and prevent concurrent updates from bypassing the policy.

The views are intended for reporting and evaluation. They do not make it impossible for another database client with sufficient privileges to write an inconsistent governance state. Access control, controlled write paths, and the source-control platform's own branch protection remain necessary.

## Interpreting Quality Findings

A useful quality policy distinguishes findings that indicate a possible defect from evidence that a merge requirement failed.

An unused import may be a low-severity maintainability issue. A syntax error prevents the source from being parsed. A failed security-oriented static-analysis rule may warrant a blocking status check, depending on its severity and the repository's policy.

The same principle applies to formatting. A formatting difference can be corrected automatically, while a failing formatting status means the required formatting gate has not passed. The distinction allows automated remediation without confusing the transformation itself with the repository decision.

The examples also illustrate why a clean quality report is not proof of defect-free code. Custom rules have limited coverage, static analysis can produce false positives and false negatives, tests cover only the behaviors they exercise, and code review depends on the scope and quality of human inspection.

## Operational and Security Considerations

Quality tools should run against the same source revision that is proposed for merging. A pipeline must not report success by combining a passing test run from one commit with approvals for a different commit when policy requires current evidence.

Quality rules should be version-controlled with the repository. Changes to lint configuration, formatting configuration, static-analysis rules, or required checks can alter merge eligibility and should therefore be reviewed as code changes.

Automated findings should include stable rule identifiers and precise source locations where possible. This supports suppression review, trend analysis, and consistent treatment across local development and continuous integration.

Suppressions should be narrow and justified. Broadly disabling a rule can hide unrelated defects. Security-related rules should receive particular scrutiny when a suppression changes the set of code paths that are examined.

Finally, branch protection must be enforced by the system that performs the merge. A local quality script can report that a change appears acceptable, but it cannot independently guarantee that a remote branch has not changed, that an approval remains current, or that an authorized bypass was not used. Those guarantees require trusted status reporting, repository authorization, and server-side enforcement.

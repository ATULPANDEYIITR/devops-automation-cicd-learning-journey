# Actions Matrix Builds: Matrix Strategy and Multi-Version Testing

## Scope

This project models matrix builds as a CI testing strategy in which one workflow definition expands into multiple concrete jobs. Each job represents a distinct combination of dimensions such as runtime version, operating system, and dependency policy.

The central relationship is:

**Matrix strategy → concrete build combinations → independent test execution → aggregated workflow result**

The implementation treats matrix expansion and test execution as separate concerns. Expansion answers which combinations should exist. Execution determines whether each combination passes. Aggregation determines whether the collection of results is acceptable for the workflow.

The examples use a Python-version dimension, an operating-system dimension, and a dependency dimension. This produces realistic compatibility coverage without treating every combination as automatically valuable.

## Matrix Strategy

A matrix is a Cartesian product of declared dimensions.

For example, four Python versions, three operating systems, and three dependency modes produce:

`4 × 3 × 3 = 36`

potential combinations before exclusions.

The matrix is therefore more than a list of versions. Every dimension multiplies the number of jobs. This has direct implications for CI duration, runner consumption, artifact volume, and maintenance.

The project uses three dependency modes:

| Dependency mode | Purpose |
|---|---|
| `minimum` | Detect compatibility problems against the lowest supported dependency boundary |
| `locked` | Validate the dependency set used by reproducible builds |
| `latest` | Detect forward-compatibility problems with current dependency releases |

The Python dimension represents supported runtimes. The operating-system dimension exposes platform-specific behavior. The dependency dimension tests different dependency compatibility boundaries.

These dimensions answer different engineering questions and should not be collapsed into one generic version variable.

## Matrix Expansion

The Python implementation uses `itertools.product` to construct the Cartesian product. The JavaScript implementation uses nested iteration, while the C++ and Java implementations explicitly construct domain combinations.

The SQL implementation uses `CROSS JOIN` because relational Cartesian products naturally express matrix expansion:

`python_version CROSS JOIN operating_system CROSS JOIN matrix_dependency`

Exclusions are evaluated after the product is constructed. This is important because an exclusion removes a specific combination rather than an entire dimension.

For example:

`Python 3.10 + macOS + minimum dependencies`

can be excluded without removing Python 3.10, macOS, or the minimum dependency mode from all other combinations.

## Include and Exclude Behavior

The examples distinguish between two different matrix operations.

An exclusion removes a combination that should not execute. Typical reasons include an unsupported platform-runtime pairing or a combination that has no meaningful coverage value.

An inclusion adds or enriches a combination that needs special treatment. The implementations use an experimental Python 3.13 combination as a canary-style matrix entry.

An important design distinction is that `include` should not be treated as a generic replacement for the base matrix. Its purpose is to introduce special matrix behavior or metadata while the base dimensions continue to describe ordinary coverage.

## Multi-Version Testing

Multi-version testing detects compatibility boundaries that a single runtime cannot expose.

The example intentionally models several failure classes:

- Python 3.10 with the latest dependency set represents an old-runtime versus new-dependency compatibility boundary.
- Python 3.13 with minimum dependencies represents a new-runtime versus old-dependency compatibility boundary.
- Python 3.10 on Windows represents an operating-system-specific legacy compatibility problem.
- Python 3.13 on macOS represents a platform-specific native-extension problem.

These failures are intentionally tied to matrix dimensions. A failure therefore communicates more information than a generic test failure. It identifies the particular environment in which compatibility broke.

## Python Implementation

The Python program provides the most complete simulation-oriented model.

`MatrixDefinition` contains the matrix dimensions, exclusions, and special inclusions. `MatrixEngine` validates those dimensions and expands them into immutable `MatrixJob` records.

Each `MatrixJob` contains:

- Python version
- operating system
- dependency mode
- experimental status

The job also produces a stable identifier derived from its dimensions. This demonstrates an important CI design property: artifacts and logs should be attributable to the exact matrix combination that produced them.

`TestSuite` contains deterministic compatibility rules. It does not use arbitrary randomness because reproducible CI demonstrations should produce the same result every time.

`MatrixRunner` demonstrates execution semantics, retry counts, fail-fast behavior, and tolerated experimental failures.

The program also calculates coverage statistics and produces machine-readable JSON output. This makes the distinction between human-readable CI logs and structured result data explicit.

## JavaScript Implementation

The JavaScript implementation emphasizes asynchronous and event-driven execution.

`MatrixWorkflow` extends `EventEmitter`. Job lifecycle events are emitted when jobs start, complete, or are cancelled.

This models the event-oriented nature of Node.js applications and provides a useful abstraction for CI systems where execution is asynchronous.

The workflow uses promises and asynchronous delays to represent independent runner activity without requiring an external CI service.

The implementation also demonstrates a practical distinction between:

- a job being executed,
- a job completing successfully or unsuccessfully,
- a workflow deciding whether that failure blocks the overall result.

The artifact identifier is generated from the matrix dimensions using Node's standard `crypto` module.

## C++ Case Study

The C++ program models a repository compatibility engine.

The domain is represented using enums and structures rather than loosely typed strings. `PythonVersion`, `OperatingSystem`, `DependencyMode`, and `JobStatus` make invalid state values harder to introduce accidentally.

`RepositoryGovernanceEngine` owns matrix expansion and evaluation. Its `expand` operation creates the Cartesian product and applies exclusions. Its evaluation operation executes compatibility rules against concrete matrix jobs.

The implementation uses `std::vector`, `std::tuple`, `std::map`, `std::set`, and standard algorithms such as `std::find_if` and `std::any_of`.

The `fail_fast` policy is represented explicitly. When enabled, a blocking failure prevents later release-blocking jobs from executing. Experimental jobs have different failure semantics and can continue to execute without being treated as release-blocking.

This separation is useful because matrix coverage and workflow control are different concerns.

## Java Implementation

The Java implementation models the matrix as an enterprise-oriented domain.

Enums represent the controlled dimensions and job lifecycle:

- `PythonVersion`
- `OperatingSystem`
- `DependencyMode`
- `JobState`

`MatrixJob` is a record, which provides a compact immutable representation of a concrete matrix combination.

`MatrixDefinition` owns matrix configuration and validates that its dimensions are non-empty.

`CompatibilityPolicy` contains compatibility rules separately from matrix construction. This is a significant architectural choice. A matrix describes what should be tested, while a compatibility policy describes whether a particular environment is supported.

`MatrixEvaluationService` owns job-state evaluation. It transitions a job conceptually from `PENDING` to `RUNNING` and then to either `PASSED` or `FAILED`. It can also create `CANCELLED` results when fail-fast behavior prevents a job from running.

This separation supports enterprise CI systems where matrix definition, compatibility policy, and workflow execution may be managed by different components.

## SQL Data Model

The PostgreSQL implementation represents matrix testing relationally.

The central entities are:

| Entity | Purpose |
|---|---|
| `repository` | Identifies the repository whose workflow is being evaluated |
| `branch` | Represents source and target development branches |
| `commit` | Associates a Pull Request with a concrete source revision |
| `pull_request` | Identifies the change being tested |
| `matrix_configuration` | Stores a named matrix strategy |
| `python_version` | Defines supported runtime versions |
| `operating_system` | Defines platform dimensions |
| `matrix_dependency` | Defines dependency strategies |
| `matrix_exclusion` | Records combinations that should not execute |
| `matrix_job` | Stores concrete expanded matrix combinations |
| `matrix_job_attempt` | Records execution attempts and failures |
| `test_result` | Stores test-suite-level results |

Foreign keys prevent matrix jobs from referencing undefined dimensions.

The unique constraint on a matrix job prevents duplicate combinations for the same Pull Request:

`pull_request_id + python_version + operating_system + dependency_mode`

The exclusion table represents matrix-specific exclusions as relational data rather than embedding them into application-only logic.

## Database-Level Enforcement

The SQL script uses `CHECK` constraints for values that belong at the database integrity layer.

Examples include:

- valid operating-system names
- valid dependency modes
- non-negative test durations
- non-negative test counts
- failure counts not exceeding executed tests
- valid attempt numbers
- valid Pull Request states
- consistent merged-state timestamps

The distinction between database integrity and CI policy is deliberate.

The database can enforce that a test result is structurally valid. It cannot universally determine whether Python 3.13 is appropriate for a particular dependency release without incorporating application-specific compatibility policy.

That policy remains represented by the matrix evaluation logic.

## Matrix Job Identity

Every concrete combination should remain distinguishable throughout CI execution.

The implementations therefore use composite identity information containing runtime, platform, and dependency strategy.

A useful artifact name might look like:

`test-results-py313-ubuntu-latest`

This prevents different matrix jobs from overwriting each other's outputs.

The Python implementation additionally creates a short stable hash identifier. The JavaScript implementation derives an identifier with SHA-256. The SQL model uses a relational primary key while retaining all matrix dimensions as queryable columns.

## Fail-Fast Behavior

Fail-fast is a workflow execution policy.

When fail-fast is enabled, a blocking failure can prevent matrix jobs that have not started from running.

This can reduce CI resource consumption and shorten feedback time when a failure makes further execution unnecessary.

The trade-off is diagnostic coverage. A fail-fast workflow may reveal only the first blocking failure while leaving other compatibility problems undiscovered.

The Python, C++, and Java implementations explicitly model cancellation. The JavaScript implementation represents cancellation as a workflow event.

Fail-fast should therefore be chosen according to the purpose of the matrix. A fast validation matrix may favor it, while a broad compatibility or release-validation matrix may disable it to collect complete evidence.

## Experimental Matrix Combinations

An experimental combination is useful when a runtime or dependency combination is informative but not yet release-blocking.

The examples mark a Python 3.13 Ubuntu latest-dependency combination as experimental.

This creates two distinct result categories:

- release-blocking failures
- tolerated experimental failures

An experimental job is not the same as a skipped job. It executes and produces evidence. Its result remains visible even though its failure does not necessarily fail the workflow.

This distinction is valuable for testing a future runtime before declaring it part of the supported release boundary.

## Retry Semantics

A retry is different from a second matrix combination.

A matrix combination identifies an environment. An attempt identifies another execution of that same environment.

The SQL schema therefore stores attempts separately from matrix jobs.

For example:

`Python 3.11 + Ubuntu + locked dependencies`

remains one matrix job even if the runner executes it twice.

This distinction is important for diagnosing flaky infrastructure failures. Without separate attempt records, repeated execution can be incorrectly interpreted as additional coverage.

## Coverage and Cost

Matrix size grows multiplicatively.

If a workflow contains:

| Dimension | Values |
|---|---:|
| Python | 4 |
| OS | 3 |
| Dependencies | 3 |

the theoretical maximum is 36 jobs.

Adding another independent dimension with five values would increase that to 180 jobs.

This makes matrix design an optimization problem. More combinations provide more coverage, but they also increase:

- runner consumption
- execution time
- artifact volume
- log volume
- queue pressure
- maintenance complexity

Exclusions should therefore remove combinations that genuinely have no coverage value rather than being used simply to reduce CI cost.

## Edge Cases

A matrix engine must account for invalid and unusual configurations.

An empty runtime dimension is rejected because no meaningful build can be produced.

Unknown runtime values are rejected by the Python, JavaScript, and domain-oriented implementations.

An exclusion that matches no combination is not automatically equivalent to an invalid matrix. It may indicate obsolete configuration, but the semantics are different from an invalid runtime value.

A duplicate concrete matrix job is dangerous because it can produce duplicate test execution and ambiguous artifact ownership. The SQL unique constraint prevents duplicate Pull Request combinations.

A failed retry should not create another logical matrix job. It should create another execution attempt.

An experimental failure should not silently disappear. It should remain visible while being treated differently for workflow success.

## Performance Considerations

Matrix expansion is proportional to the Cartesian product of its dimensions.

If the dimension sizes are:

`d1, d2, ..., dn`

then the maximum number of combinations is:

`d1 × d2 × ... × dn`

Exclusion processing can reduce actual execution count, but the engine may still need to generate or reason about the base combinations before removing them.

For large matrices, efficient exclusion lookup, lazy expansion, job scheduling, and bounded concurrency become important.

The SQL implementation indexes matrix dimensions and Pull Request relationships because operational queries commonly filter by those fields.

Artifact and log storage also becomes significant as matrix size grows. Each combination should have a stable, collision-resistant identity.

## Security Considerations

Matrix configuration should not automatically be treated as trusted executable input.

A matrix may influence:

- which runner executes a job
- which dependency versions are installed
- which external resources are contacted
- which credentials become available to the workflow

Runtime and dependency values should therefore be validated against allowed values.

Secrets should not be copied into matrix variables merely to simplify configuration. A matrix dimension should describe test configuration rather than become an uncontrolled secret-routing mechanism.

For workflows processing untrusted Pull Requests, runner isolation is particularly important. A matrix increases the number of execution environments, so the security boundary must remain consistent across every combination.

## Common Design Mistakes

A common mistake is creating every possible combination without considering whether each combination provides useful coverage. This can turn a small compatibility suite into hundreds of jobs.

Another mistake is confusing dependency versions with runtime versions. They test different compatibility boundaries and should remain separate dimensions when both are operationally meaningful.

Treating a failed experimental job as a successful test without recording its failure is also incorrect. Experimental status changes merge or workflow policy, not the underlying test result.

Using random failures to demonstrate matrix behavior makes debugging and validation difficult. The examples therefore use deterministic compatibility rules.

A further mistake is treating retries as new coverage. Repeating the same matrix combination provides another execution attempt, not another environment.

## Production Considerations

A production matrix should be driven by an explicit support policy.

Supported runtimes should correspond to actual product compatibility commitments. Operating systems should be included when platform behavior differs materially. Dependency strategies should reflect concrete release-management goals.

A useful production design commonly separates:

- the minimum supported environment
- the locked production environment
- the newest compatibility environment
- selected platform-specific environments
- experimental future environments

The matrix should also expose enough metadata to identify exactly which environment produced a result.

For large organizations, the matrix definition may be centrally governed while repository-specific workflows select the dimensions that apply to their products.

## Relationship Between Matrix Strategy and CI Results

Matrix strategy defines the test space.

A concrete matrix job represents one point in that space.

A test result describes what happened at that point.

An aggregated workflow conclusion evaluates the collection of results according to policy.

This separation prevents a common conceptual error: treating the matrix itself as the test result.

A matrix can be completely expanded successfully while multiple matrix jobs fail. Conversely, a matrix may intentionally exclude combinations that are unsupported, meaning the absence of a job does not necessarily represent missing test coverage.

## Practical Interpretation

The strongest use of matrix builds is not simply "test on many versions." It is to make compatibility boundaries explicit and machine-evaluable.

A well-designed matrix can answer questions such as:

- Does the oldest supported runtime still work with the supported dependency floor?
- Does the newest runtime work with the production lockfile?
- Does the latest dependency release break an older runtime?
- Does a platform-specific integration fail only on Windows?
- Is an emerging runtime safe to test without making it release-blocking?
- Which exact combination produced the failure?
- Was the failure reproduced on retry?
- Does the complete matrix satisfy the workflow's release criteria?

The six implementations use different programming models, but they preserve the same core distinction: matrix configuration determines coverage, concrete jobs execute that coverage, and policy interprets the resulting evidence.

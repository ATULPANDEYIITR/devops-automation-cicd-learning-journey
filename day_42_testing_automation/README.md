# Testing Automation: Unit, Integration, Smoke, and Regression Testing

## Purpose and technical scope

Testing automation executes repeatable checks against software behavior and uses the results to make release decisions. A useful testing system distinguishes the scope of each check, controls its dependencies, records evidence, and defines what happens when a check fails.

This project models an order-processing service and its release pipeline. The Python program implements business rules, relational integration tests, HTTP smoke tests, regression tests, and JSON reporting. The JavaScript program models an event-driven test pipeline. The C++ program evaluates test evidence alongside repository release requirements. The Java program represents release verification through explicit domain types and controlled state transitions. The PostgreSQL script stores test definitions, executions, results, quality policies, and deployment eligibility.

The four testing categories have different purposes:

| Category | Primary question | Typical dependencies | Main failure signal |
|---|---|---|---|
| Unit testing | Does an individual rule or component behave correctly? | In-memory objects, deterministic inputs | Incorrect calculation, validation, or state change |
| Integration testing | Do collaborating components work together correctly? | Database, service interfaces, serialization, transactions | Contract mismatch, failed persistence, broken transaction |
| Smoke testing | Does the essential service functionality work in the target environment? | Running application, network endpoint, deployment configuration | Service unavailable, unhealthy readiness endpoint, broken startup |
| Regression testing | Does previously verified behavior still work after a change? | Stable test cases and known expected outcomes | Previously corrected behavior fails again |

These categories are related, but they are not interchangeable. A unit test can prove that a function calculates a price correctly without proving that a database transaction persists an order. An integration test can verify database interaction without proving that a deployed HTTP endpoint is reachable. A smoke test can establish that the application is responsive without proving that every business rule remains correct. Regression testing protects previously established behavior and can contain unit, integration, or end-to-end tests.

## Architecture and execution flow

The implementations use a release-verification workflow:

- **Define expected behavior.** Test definitions specify the category, inputs, expected results, and criticality.
- **Execute checks.** The test runner invokes each test and records its outcome, duration, and failure details.
- **Evaluate quality requirements.** The release gate checks that required categories have successful evidence and that critical failures do not remain.
- **Control deployment.** A release can proceed only when its test and security requirements are satisfied.
- **Preserve evidence.** Reports and relational records support debugging, release audits, and comparison between builds.

The examples are deterministic local demonstrations. Their deployment functions do not contact a real hosting platform, and their test records are not evidence from an external continuous integration service.

## Python implementation

The Python script uses the standard library to build a working test laboratory without third-party dependencies.

### Business-rule unit tests

The `Inventory` and `OrderService` classes separate stock management from order calculations. `calculate_total` checks quantity validity and uses `Decimal` for monetary calculations. The tests verify exact totals, reject invalid quantities, and detect unknown product identifiers.

The distinction between a unit test and an integration test is reflected in the dependencies. Unit tests exercise an in-memory inventory and avoid opening a database or network connection. This reduces execution time and makes failures easier to localize.

Input validation covers cases that can be overlooked in ordinary happy-path testing. Python treats `bool` as a subclass of `int`, so a check that accepts every integer would accidentally accept `True` as a quantity. The implementation explicitly rejects Boolean quantities. Money parsing rejects floating-point input and values with more than two decimal places.

### Database integration tests

`SQLiteOrderRepository` uses a temporary SQLite database with primary keys, foreign keys, check constraints, and parameterized SQL statements.

The order transaction reserves inventory and inserts an order. Both operations must succeed together. If the order insertion fails because the order identifier already exists, the transaction rolls back the stock change. If available inventory is insufficient, the transaction is also rolled back.

The integration examples verify these outcomes against an actual relational database instead of a mocked repository. They demonstrate why testing an application component in isolation is insufficient when correctness depends on transaction boundaries and database constraints.

SQLite is suitable for this self-contained exercise. Applications using PostgreSQL, MySQL, or another production database should also execute integration tests against the actual database engine because SQL behavior, locking, types, and constraint semantics can differ.

### HTTP smoke tests

The script starts a local `ThreadingHTTPServer` on an operating-system-selected port. The smoke tests request `/health` and `/ready`, validate the HTTP status, parse the JSON response, and verify that an unknown route returns HTTP 404.

This approach checks the interaction between an HTTP server, request routing, response headers, serialization, and the HTTP client. It does not establish that a real production deployment is healthy. A production smoke test should contact the deployed release and use bounded timeouts, authentication where required, and a known release identifier.

The server is shut down in a `finally` block so that test failures do not leave the local server running.

### Regression tests and reporting

`OrderRegressionTests` protects previously established behavior, including monetary totals, inventory reservation, duplicate-order handling, invalid quantities, and failed-order side effects.

The `unittest` framework runs the cases and records failures separately from errors. The report includes execution counts, duration, and failure details. `write_json_report` writes a temporary file and replaces the destination, reducing the chance of leaving a partially written report.

Run the program with:

    python testing_automation.py

The process exits with a nonzero status if the regression suite reports failures or errors. This makes the script suitable for a continuous integration step that checks the process exit code and publishes the JSON report as a build artifact.

The JSON file is a test report, not a code-coverage report. Coverage requires separate instrumentation that records which statements, branches, or lines were executed.

## JavaScript implementation

The JavaScript file focuses on event-driven pipeline orchestration rather than duplicating the Python repository adapter.

### Test definitions and asynchronous execution

`TestCase` binds a name and category to an executable asynchronous function. `TestSuite` validates registrations, rejects duplicate test names, and filters cases by category and tags.

Each test returns a structured result with its category, outcome, duration, criticality, and optional error. A failed assertion becomes a failed result rather than terminating the entire suite immediately. This permits a release report to show multiple independent failures from the same run.

The suite runs tests sequentially. This is deliberate: tests that mutate shared inventory or use shared database fixtures can interfere with each other when run concurrently. Parallel execution is appropriate when test isolation is guaranteed and resource contention is controlled.

### Event-driven release state

`DeploymentPipeline` extends `EventEmitter` and records transitions such as `created`, `validating`, `testing`, `ready`, `deploying`, and `deployed`. The transition table rejects illegal state changes.

Listeners receive a state-change event containing the previous state, new state, timestamp, and associated details. This provides an observable event stream for a dashboard or audit logger without embedding presentation logic in the deployment policy.

Before deployment, the pipeline verifies that all required testing categories have successful evidence and that no critical test has failed. It then calls an injected deployment handler. The rollback handler is also injected, allowing the pipeline policy to be tested without depending on a particular deployment provider.

### Failure semantics and limitations

The example uses JavaScript assertions and simulated service functions. Its money calculation converts values to integer cents to avoid many common binary floating-point rounding errors, although production financial systems should use a decimal representation or integer minor units with a defined rounding policy.

A passing test category is not equivalent to a fully passing category if one of its required tests failed. A production policy should define category-level completeness, skipped-test handling, retries, flaky-test treatment, and whether noncritical failures block release. The example requires at least one passing test from each required category and separately rejects critical failures; more stringent policies may require every required test to pass.

Run the file with:

    node testing-automation.js

A non-deployed release sets the process exit code to `1`, making the outcome consumable by a build pipeline.

## C++ case study: Repository release governance

The C++ program treats testing evidence as one part of a repository's merge and release controls. The scenario is a proposed change to an order-processing API that must satisfy automated tests and protected-branch requirements before it can be accepted.

### Evidence model

`TestEvidence` records the test category, suite, state, number of executed tests, and failure count. `StatusCheck` represents a named build or security check. `PullRequest` holds source and target branches, draft status, synchronization state, merge-conflict information, approvals, unresolved review concerns, test evidence, and check results.

These are separate inputs because repository review and automated testing answer different questions. Reviewers assess correctness and maintainability. Automated tests provide repeatable behavioral evidence. Repository governance combines both without assuming that one substitutes for the other.

### Governance evaluation

`GovernanceEngine::evaluate` produces a `GateResult` containing eligibility and a list of blockers. It rejects invalid pull request metadata, draft changes, unsynchronized source branches, conflicts, insufficient approvals, unresolved conversations, non-linear history, missing testing evidence, failed test categories, and unsuccessful required status checks.

The engine distinguishes required status checks from optional checks. A skipped optional preview-environment check does not block the example change. A pending required build check does block it.

The sample scenarios show why passing tests alone cannot authorize a merge. A pull request with a failed integration suite remains blocked despite its approvals. Another change remains blocked while review conversations are unresolved. A draft remains ineligible until the author marks it ready.

### Complexity, trust, and production boundaries

For \(n\) pull requests, \(e\) test-evidence entries, and \(c\) status checks, evaluating one pull request takes \(O(e+c)\) time with the current vector-based searches. The evidence list is small in this demonstration. A service processing large evidence sets could index them by test category and check name.

The program validates policy values and request metadata, but it does not authenticate reviewers or retrieve signed CI evidence. A production governance service must obtain approval records from the repository provider, verify the identity and permissions of reviewers, confirm that evidence belongs to the exact source commit, and enforce policy at the server boundary. A locally supplied `passed` state must never be treated as trusted evidence merely because the caller provided it.

Compile and run with a C++17 compiler:

    g++ -std=c++17 -Wall -Wextra -pedantic testing_automation.cpp -o testing_automation

    ./testing_automation

## Java implementation: Enterprise release verification

The Java program models a release process using explicit domain types and an auditable state machine.

### Immutable test results

`TestResult` is a record containing the test identifier, category, status, criticality, diagnostic detail, duration, and completion timestamp. Its constructor validates mandatory values and rejects negative durations.

`TestDefinition` pairs a test category with an executable assertion. The execution method measures elapsed time and converts runtime exceptions into failed results. This keeps test execution outcomes structured while preserving diagnostic information.

`TestCatalog` rejects duplicate test identifiers and executes registered definitions in deterministic name order. Its registry makes test inventory and execution separate concerns.

### Release quality policy

`QualityPolicy` specifies required categories, the minimum number of successful tests in each category, and whether skipping a critical test is prohibited. Its evaluation method returns explicit policy violations rather than a single Boolean, making release failures easier to diagnose.

The test catalog includes distinct examples for price calculations, input validation, database migration verification, endpoint health, and duplicate-order prevention. The examples are simulated assertions against a release context. The database migration and endpoint checks therefore represent expected integration and smoke evidence rather than live database or network tests.

### State transitions and security controls

The `Release` class allows only declared transitions. An invalid transition raises `IllegalStateException`, and valid transitions are recorded in an audit trail with timestamps.

`ReleaseService` separates evidence collection from policy evaluation and deployment. The deployment example accepts only a staging target, evaluates the required testing categories, and verifies that the release artifact is signed. An unsigned artifact is rejected even when every test passes.

This is an important separation of concerns: a quality gate measures behavioral confidence, while artifact verification establishes a separate release-security condition. Neither should be silently substituted for the other.

Compile and run using Java 17 or later:

    javac TestingAutomation.java

    java TestingAutomation

The model uses in-memory collections and simulated deployment behavior. A production implementation would persist test results, authenticate evidence sources, integrate with actual deployment services, and verify the running version after rollout.

## PostgreSQL data model and release evidence

The SQL script stores the information needed to compare testing results and evaluate release eligibility. It uses PostgreSQL-specific types, partial indexes, filtered aggregates, interval arithmetic, and regular-expression checks.

### Relational structure

| Relation | Responsibility |
|---|---|
| `projects` | Identifies the software project and its production branch. |
| `test_suites` | Defines a test suite, category, execution scope, criticality, and timeout. |
| `test_cases` | Describes individual cases associated with a suite. |
| `release_candidates` | Identifies a version, source commit, target environment, and release state. |
| `test_runs` | Records the execution of a suite against a specific release. |
| `test_case_results` | Stores individual case outcomes, durations, and diagnostics. |
| `release_gate_policies` | Defines required evidence thresholds for each environment and test category. |
| `deployment_attempts` | Preserves the outcomes of deployment and rollback attempts. |

Foreign keys preserve relationships between projects, suites, cases, releases, and executions. Unique constraints prevent duplicate project versions, duplicate suite names, and repeated case identifiers within a suite. Check constraints reject invalid durations, negative test counts, invalid release environments, and inconsistent completion timestamps.

The schema deliberately separates test definitions from executions. A test case describes expected behavior; a test run records what happened against a particular release. The same case can therefore be executed across many versions without creating a new definition for every run.

### Evidence integrity

The `test_runs` table stores aggregate counts and execution metadata. The `test_case_results` table provides case-level outcomes and diagnostics. These records support different queries: aggregate counts help evaluate release gates, while individual results help locate the cause of a failure.

The database constraints protect basic invariants, but they do not prove that aggregate counts match every case-level record. A production ingestion service should calculate aggregates from authoritative results within a transaction, or enforce consistency through a controlled database function or trigger. Access controls should prevent untrusted clients from directly rewriting completed evidence.

### Release-gate views

`release_test_summary` aggregates executions by release and test category. `release_gate_evaluation` compares the available evidence against policy thresholds, including the number of successful runs, recorded failures, and evidence age.

`release_deployment_eligibility` combines the test gates with artifact-signing status and the release state. The sample release has passing unit, integration, and regression tests, but its smoke test fails because the readiness endpoint returned HTTP 503. Consequently, the test gate blocks deployment even though the other categories pass.

The final guarded update illustrates that a release should not move from testing to approved when the deployment eligibility view reports a failed gate. A production database should enforce allowed state transitions through a controlled function or trigger and restrict direct status changes through database permissions.

### Query performance

The indexes support common operational queries:

- `idx_test_runs_release_suite` helps retrieve recent executions for a release and suite.
- `idx_test_runs_failed` is a partial index for investigations of failed executions.
- `idx_test_case_results_run_status` supports queries for failed cases within a run.
- `idx_release_candidates_project_created` supports recent-release history.
- `idx_deployment_attempts_release` supports chronological deployment-attempt review.

Index design should follow observed query plans and data volume. Every additional index increases storage requirements and the cost of inserting or updating records.

## Choosing the right test level

A reliable test suite uses different levels for different risks instead of repeating the same assertion in every layer.

A unit test should verify a local rule such as rejecting zero quantity. An integration test should verify that a stock reservation and order insertion remain atomic when a database constraint rejects the order. A smoke test should verify that the deployed application starts and responds through its essential endpoint. A regression test should preserve a previously corrected failure, such as preventing duplicate order submission from reserving inventory twice.

Regression testing is not a synonym for end-to-end testing. A regression case can be a fast unit test or a full deployment-level test. The defining property is that the case protects known behavior against future changes.

## Failure handling and reliable automation

A testing pipeline must distinguish a failed assertion from a test execution error, an intentionally skipped case, and an infrastructure failure. Treating every non-passing result as a normal assertion failure can hide outages in the test environment. Treating infrastructure failures as success is equally dangerous.

Retries should be limited to failures that are plausibly transient, such as temporary network instability. Repeating a deterministic business-rule failure without investigating it can waste execution time and obscure the original problem. Test reports should preserve the first failure, retry history, environment details, and the final result.

Test isolation is essential. Tests that share mutable inventory, database records, accounts, or deployed environments can affect each other. Temporary databases, unique identifiers, transaction rollback, controlled fixtures, and explicit cleanup help keep results reproducible.

A passing test suite provides evidence about the behaviors it exercised under its tested conditions. It does not prove the absence of defects. Release decisions should therefore combine appropriate automated coverage, trusted test evidence, security checks, and deployment health verification.

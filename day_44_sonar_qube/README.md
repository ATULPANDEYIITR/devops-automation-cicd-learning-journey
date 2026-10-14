# SonarQube: Code Quality Gates, Technical Debt, and Quality Metrics

## Scope

This repository models software quality management around three connected concerns:

- **Quality metrics** describe measurable properties of a codebase, such as test coverage, duplicated lines, active findings, and remediation effort.
- **Technical debt** estimates the work required to correct maintainability problems and other findings. Its value depends on which issues are included and how remediation effort is estimated.
- **Quality gates** evaluate configured conditions against an analysis and produce a pass or fail decision. A gate turns selected quality measurements into an enforceable release policy.

The implementations use SonarQube-inspired terminology and deterministic sample data. They do not execute SonarQube's analyzers, reproduce its complete rating algorithms, or connect to a live SonarQube server. The examples focus on the engineering mechanisms surrounding analysis, metric interpretation, policy evaluation, and repository integration.

## Quality analysis and measurement

Static analysis examines source code without requiring the program to execute every possible path. A quality-analysis platform can combine rule findings with measurements obtained from source analysis and test execution.

An analysis should be associated with an identifiable project, branch, and commit. Without that association, a metric report cannot reliably establish which source revision it describes.

### Findings and issue categories

The examples distinguish the following finding types:

| Type | Engineering meaning | Typical response |
|---|---|---|
| Bug | A defect that may produce incorrect behavior | Reproduce the failure, correct the defect, and test the affected behavior |
| Vulnerability | A security weakness that may expose data or operations | Assess exploitability, remove the weakness, and verify the security boundary |
| Code smell | A maintainability problem or undesirable implementation pattern | Refactor where the expected maintenance benefit justifies the effort |
| Security hotspot | Code that requires contextual security review | Inspect the use case, threat model, configuration, and security assumptions |

Severity and issue type represent different dimensions. A severity describes the assessed importance of a finding, while its type identifies the nature of the concern. A security hotspot should not automatically be treated as a confirmed vulnerability. It represents a review obligation whose outcome depends on context.

Each modeled finding includes a stable key, rule identifier, source component, line number, remediation estimate, and lifecycle attributes. These fields make it possible to trace an issue to a location, estimate work, distinguish existing findings from findings introduced by a change, and exclude resolved issues from active debt.

## Quality metrics

### Test coverage

Coverage expresses the proportion of measurable source lines executed by the test suite.

\[
\text{Coverage} =
\frac{\text{Covered lines}}{\text{Lines of code}} \times 100
\]

The denominator must be interpreted carefully. Coverage depends on the files included in the analysis, the test execution data, and the platform's language-specific treatment of executable lines. A test report that was not imported correctly can produce misleading measurements.

The implementations reject impossible counts, such as covered lines exceeding total lines. They define coverage as zero when the denominator is zero, rather than incorrectly reporting complete coverage for an empty source set. A real SonarQube analysis can apply more detailed rules to files, generated code, exclusions, and executable-line detection.

Coverage measures execution, not test effectiveness. A line can execute without its result being asserted. Tests must still verify expected behavior, boundary conditions, error handling, and security-sensitive outcomes.

### Overall metrics and new-code metrics

Overall measurements describe the analyzed codebase. New-code measurements focus on the portion designated as new or changed under the applicable analysis configuration.

This distinction matters in repositories that contain legacy issues. A team may have thousands of existing findings while still requiring every new change to avoid introducing vulnerabilities and to maintain adequate coverage.

For example, a code smell that predates a pull request should contribute to overall maintainability debt but should not automatically count as newly introduced debt. The Python, JavaScript, C++, Java, and SQL models retain this distinction explicitly.

New-code measurements depend on the correct base revision and new-code definition. Incorrect branch comparison or an unsuitable baseline can misclassify existing findings as new, or hide findings introduced by a change.

### Duplication

Duplicated-line percentage measures the proportion of source lines identified as duplicated by the analysis engine. Duplication can increase the effort needed to make consistent changes across multiple implementations.

A simplified percentage is:

\[
\text{Duplication} =
\frac{\text{Duplicated lines}}{\text{Measured lines}} \times 100
\]

A low duplication percentage does not establish that an implementation is well designed. Some repeated code is intentional, while superficially similar blocks may have different behavioral requirements. Duplication thresholds are most useful when the team investigates the affected blocks and understands the reason for the repetition.

### Reliability, security, and maintainability ratings

SonarQube provides ratings for quality dimensions, but the exact rating rules depend on the platform version and its configured analysis behavior. The Python and JavaScript examples use simplified educational rating functions, not official SonarQube rating calculations.

The examples therefore keep raw finding counts and remediation effort available alongside ratings. A production decision should not rely on a locally invented rating when an authoritative server result is available.

## Technical debt

Technical debt represents the estimated effort required to address identified problems. In these implementations, each active finding carries a remediation estimate in minutes.

\[
\text{Estimated debt} =
\sum_{\text{active findings}} \text{remediation minutes}
\]

This is a model of estimated remediation effort, not a measurement of elapsed delivery time or financial cost.

The code distinguishes:

- **New technical debt:** estimated effort associated with active findings introduced by the current change.
- **Overall technical debt:** estimated effort associated with all active findings included in the model.

The distinction enables a team to prevent quality deterioration without requiring every legacy problem to be fixed in a single release.

### Debt ratio and remediation planning

Technical debt ratio is a separate concept from total debt. In quality platforms, a debt ratio relates estimated remediation effort to an estimated cost of developing or maintaining the relevant code. The precise definition depends on the platform's metric and scope.

A repository should not interpret 300 minutes of estimated debt as a universal percentage or as a guaranteed three-hundred-minute delivery commitment. Actual effort varies with test coverage, architectural dependencies, reviewer availability, and the risk of changing existing behavior.

Useful debt-management practices include:

- Prioritizing vulnerabilities and correctness defects according to risk rather than sorting exclusively by estimated effort.
- Reviewing recurring code smells that repeatedly increase the cost of changes.
- Recording whether a finding has been fixed, accepted through an appropriate process, or remains unresolved.
- Tracking trends across successful analyses so that a single measurement is not mistaken for sustained improvement.

Remediation estimates are imperfect. A small estimate does not make a critical vulnerability acceptable, and a large estimate does not automatically justify deferring a defect that threatens essential operations.

## Quality gates

A quality gate is a collection of conditions evaluated against an analysis. Each condition specifies a metric, comparison operator, threshold, and applicable scope.

Examples include:

| Condition | Illustrative policy |
|---|---|
| New-code coverage | At least 80% |
| New-code duplication | No more than 3% |
| New bugs | Zero |
| New vulnerabilities | Zero |
| New blocker issues | Zero |
| New remediation effort | No more than a defined debt budget |

These thresholds are illustrative project policy, not universal SonarQube defaults.

A gate can fail even when most metrics are acceptable. If the policy requires zero new vulnerabilities and an analysis reports one, the result remains a failure regardless of excellent coverage.

The Python implementation represents conditions with a validated `GateCondition` data class. Its `QualityGate.evaluate` method produces a result containing every evaluated condition and its failures. The explicit result supports readable reports, JSON output, and automation that needs to determine why a build was rejected.

The JavaScript implementation uses immutable condition objects and a `QualityGate` evaluator. It returns a structured result instead of embedding all policy decisions in console output. The event-driven workflow then records the analysis result before a later merge request is evaluated.

### Missing analysis is not a pass

An unavailable or failed analysis must not be treated as successful merely because there are no reported failures. An empty report and a successful report are different states.

The Python and JavaScript models represent missing analysis explicitly. The SQL schema distinguishes successful, failed, and in-progress analysis runs. This prevents a missing result from being silently interpreted as evidence of acceptable quality.

### Quality gates and release policy

A gate only enforces the conditions configured within it. It cannot establish that every important engineering risk has been addressed.

For example, a gate may enforce coverage, duplication, and selected issue thresholds while a separate CI check validates dependency policies. Repository review requirements may also be enforced independently. These controls overlap in their contribution to release confidence but answer different questions.

A passing quality gate therefore means that the configured quality conditions passed for the evaluated analysis. It does not, by itself, prove that the change is secure, correct, approved, or eligible for production deployment.

## Python implementation

The Python script, `sonarqube_quality_lab.py`, builds an executable model using standard-library data classes, enumerations, type annotations, and JSON serialization.

### Data model and validation

`Issue` describes a finding and validates its identifier, remediation estimate, and source line. `Analysis` records the analyzed project, branch, commit, source measurements, and findings.

The `Analysis.metrics()` method separates active overall findings from findings introduced by the current change. It calculates coverage, duplication, issue counts, remediation estimates, and simplified ratings.

`GateCondition` validates supported metrics, comparison operators, scopes, and numeric thresholds. `QualityGate.evaluate()` evaluates every configured condition and preserves failed conditions in the result.

### Executable workflow

The demonstration contains a payment-service change with a complexity-related code smell, a query-related vulnerability, an existing legacy smell, and an unreviewed security hotspot.

The sample gate requires sufficient new-code coverage, limited duplication, no new bugs, no new vulnerabilities, no new blocker findings, and completed hotspot review. The sample intentionally fails the policy so that the report exposes the blocking conditions.

The `RepositoryWorkflow` class associates analysis results with branches and rejects merges when the branch has no successful quality-gate result. Its merge check is intentionally limited: it states that other repository policies must also permit the merge rather than pretending to implement a complete hosting platform.

### Running the program

Run the complete script with Python 3.10 or later:

    python sonarqube_quality_lab.py

Use `--json` to produce structured analysis output suitable for inspection by another program:

    python sonarqube_quality_lab.py --json

Use `--strict` to apply additional limits on critical issues and new remediation effort:

    python sonarqube_quality_lab.py --strict

Run the built-in assertions with:

    python sonarqube_quality_lab.py --test

The assertions verify metric calculations, gate outcomes, missing-analysis behavior, merge rejection, and invalid metric detection. The exit code is zero for a passing gate or successful test run, one for a failing gate, and two for execution errors.

## JavaScript implementation

The JavaScript file provides an event-driven model of quality analysis in a pull-request workflow. It uses Node.js built-in modules and requires no npm packages.

### Immutable analysis snapshots

`QualityIssue` validates individual findings and freezes each instance. `SourceSnapshot` validates the source counters, copies its finding collection, and exposes a metric calculation method.

The implementation uses explicit issue types and severity values. It does not assume that all findings have the same risk or that an existing finding belongs to the current change.

The sample metrics are represented as an immutable object. This reduces the chance that a later workflow stage accidentally changes a value after the gate has been evaluated.

### Event-driven processing

`AnalysisEventBus` registers asynchronous listeners and returns an unsubscribe function. Its `emit` method awaits listeners in order, making the demonstration's audit-event ordering deterministic.

`PullRequestQualityService` evaluates the gate and records the resulting status against a specific commit. When the source commit changes, a new analysis generation is produced. A merge attempt uses the most recently stored result.

The workflow demonstrates an important separation of responsibility: analysis determines whether configured quality conditions pass, while the supplied repository-policy callback determines whether other merge requirements are satisfied.

The sample first attempts to merge a failing change and then analyzes a corrected snapshot. The successful merge uses a callback to represent external repository checks. The callback is an explicit integration boundary, not a replacement for actual access-control and branch-protection enforcement.

### Asynchronous failure handling

The entry point catches rejected promises and sets a nonzero process exit code for unexpected execution errors. The example also uses assertions to check the expected gate states and zero-line behavior.

In production, event delivery requires more than an in-memory listener collection. Durable audit storage, idempotent event handling, authorization, retry behavior, and failure recovery are necessary when analysis outcomes influence release decisions.

## C++ case study: Repository governance engine

The C++ program models a protected `main` branch in a payment-service repository. A pull request proposes a database-query change, and the governance engine evaluates source metrics, issue findings, reviewer decisions, and required CI checks.

### Architecture

The program separates its domain data from its policy calculations:

- `SourceMetrics` stores source and coverage counters and rejects invalid denominators.
- `Finding` records issue type, severity, remediation effort, and whether the finding was introduced by the change.
- `calculateMetrics()` derives overall and new-code measurements from the source snapshot and findings.
- `QualityGate` contains the policy thresholds.
- `evaluateQualityGate()` returns the gate result and the reasons for failure.
- `PullRequest` stores the source and target branches, commit identities, review decisions, and CI status checks.
- `BranchProtection` expresses the policy associated with the protected target.
- `evaluateMergeEligibility()` combines the gate result with repository-level requirements.

This separation permits the same metric-calculation mechanism to be tested independently from merge-policy decisions.

### Metric calculation and complexity

Metric calculation iterates over the findings once. Its time complexity is \(O(n)\), where \(n\) is the number of findings, and its additional working space is \(O(1)\), excluding the input collection.

The calculation excludes resolved findings from active issue counts. It adds remediation effort to new-code debt only when a finding is both active and introduced by the change. Overall active debt includes existing findings.

This is a deliberate accounting choice. It allows the gate to limit new debt without hiding the maintenance burden of existing code.

### Merge eligibility

The merge engine checks that the pull request is open, is not a draft, targets the branch covered by the supplied policy, has no conflicts, and has a quality-gate result for the current source commit.

It then evaluates current approvals, code-owner approval, resolved conversations, and required status checks. An approval on a different commit is stale in this simplified model and does not count toward the requirement.

The example changes the source commit after the original analysis and demonstrates rejection. It also demonstrates rejection when a required dependency-audit check fails.

The `requireLinearHistory`, direct-push, force-push, deletion, and administrator-bypass settings are represented as governance policy fields. Actual enforcement of these repository operations belongs to the hosting platform. The program does not claim to implement Git's commit graph or to control administrator permissions.

Compile with a C++17 compiler:

    g++ -std=c++17 -Wall -Wextra -pedantic quality_governance.cpp -o quality_governance

Run the resulting executable:

    ./quality_governance

The executable reports the metrics, gate failures, merge blockers, and validation outcome. Its sample vulnerability intentionally prevents a production-quality gate from passing.

## Java implementation: Enterprise quality service

The Java program uses Java 17 records, enums, immutable collections, and service classes to represent a repository quality workflow.

### Domain types

`Finding`, `SourceSnapshot`, `QualityMetrics`, `GateCondition`, and `GateResult` are records. Their constructors validate the invariants that belong to each value.

`QualityGateService` evaluates configured metric extractors against thresholds. The use of a `MetricExtractor` interface keeps the gate engine independent from the implementation details of individual measurements.

The `Comparison` enum restricts supported comparisons to explicit operations. Unsupported comparison behavior cannot be introduced through an arbitrary string supplied at runtime.

### Pull-request state management

The `PullRequest` class models the state transitions from draft to open and from open to merged. It rejects invalid transitions, such as merging a draft or updating a closed request.

The head commit, analyzed commit, review records, and status checks are kept together so that merge eligibility can be evaluated against the current source revision. Updating the head invalidates the attached analysis result and makes approvals on the earlier revision ineligible.

This behavior is essential because a successful analysis describes a specific source state. Reusing an earlier result after source changes can allow untested code to inherit a previous passing decision.

### Enterprise policy enforcement

The `BranchPolicy` record declares approval requirements, code-owner review, linear-history policy, required checks, and other protected-branch controls.

`mergeBlockers()` returns the reasons a request cannot be merged. It separately verifies the quality gate, current commit identity, reviewer eligibility, current approval state, code-owner approval, and required CI checks.

The service illustrates how repository governance can be modeled as explicit domain rules rather than as unrelated conditional print statements. The in-memory records are an educational domain model; a production service would need persistent storage, transactional state changes, authenticated identities, and authoritative integration with the repository host.

Compile and run:

    javac QualityGovernance.java
    java QualityGovernance

## SQL data model: Persistent quality governance

The PostgreSQL script stores quality analysis and repository-governance data relationally. It uses PostgreSQL enumerated types, identity columns, foreign keys, partial indexes, aggregate filters, views, triggers, and a PL/pgSQL function.

Run it in a dedicated learning database with a PostgreSQL client. The script drops and recreates the `quality_lab` schema, so it should not be executed in a database containing unrelated objects with that schema name.

### Relational entities and relationships

`repositories` identifies projects. `repository_branches` records branch names and head commits. `developers` and `repository_members` represent repository participants and their review permissions.

`quality_profiles` identifies the analysis profile associated with a run. `analysis_runs` associates a source revision with its measured counters, analysis state, and timestamp. The unique repository, branch, and commit constraint prevents duplicate records for the same analyzed revision.

`quality_issues` stores rule findings, severity, issue type, location, remediation estimate, and lifecycle state. `security_hotspot_reviews` records review dispositions separately because a hotspot's review history is not the same as its original finding.

The pull-request tables represent source and target branches, commits, review decisions, inline comments, and CI status checks. The branch-protection tables represent policy configuration independently from individual pull requests.

Finally, `quality_gates`, `quality_gate_conditions`, `quality_gate_evaluations`, and `quality_gate_condition_results` provide a relational structure for configured policies and their evaluation records.

### Integrity constraints

The schema uses foreign keys to prevent orphaned issues, reviews, checks, and analysis records. Unique constraints prevent duplicate branch names within a repository, duplicate issue keys within a repository, and duplicate status-check results for the same pull request, check name, and commit.

Check constraints reject negative remediation estimates and impossible coverage counts. They also restrict enumerated states and supported comparison operators.

A database constraint can enforce a numeric invariant, but it cannot prove that coverage data accurately represents executed tests. The correctness of imported reports and the integrity of the analysis pipeline remain separate responsibilities.

### Metric queries and indexes

The `issue_metrics` view combines analysis counters with active findings. Aggregate filters calculate new bugs, vulnerabilities, blockers, and remediation effort separately from overall debt.

The partial index on unresolved issues supports queries that focus on active findings. The branch-analysis index supports retrieval of recent runs for a repository and branch. The open-pull-request index excludes closed and merged requests from its indexed subset.

The `evaluate_numeric_quality_gate()` function retrieves the configured conditions for a gate, obtains the corresponding metric, applies the configured comparison, and returns each condition's result. It raises an exception when a requested metric is unavailable instead of silently treating missing data as a passing condition.

The SQL examples query current approval counts and produce a merge-eligibility reason. The script intentionally keeps metric evaluation and repository governance separate: a quality-gate result does not automatically establish that review and branch-protection requirements have been met.

### Transactions and trigger validation

The script creates its model and demonstration records in a transaction. Its trigger verifies that a reviewer is an active repository member authorized to review and that a declared code-owner review belongs to a registered code owner.

This trigger is an example of domain validation at the database layer. A real system also needs to authenticate the person or service submitting the review, prevent unauthorized direct database writes, and align the persisted identity with the identity trusted by the repository host.

The final validation block deliberately attempts an impossible coverage record. PostgreSQL rejects it through the table's check constraint, and the script catches the expected failure inside a nested block so that the rest of the transaction can complete.

## Interpreting the results

A useful quality report preserves the difference between a measured value, an identified problem, a remediation estimate, and a policy decision.

Coverage is a measurement. A vulnerability is a finding. Technical debt is an estimate of remediation effort. A quality gate is a decision derived from configured conditions.

These values should be interpreted together but not substituted for one another. A repository can have high coverage and a serious vulnerability. It can have low new-code debt while retaining substantial legacy debt. It can pass a quality gate while still lacking a required approval or failing a separate release policy.

The practical value of quality engineering comes from keeping these distinctions explicit, associating every analysis with the correct source revision, and making policy failures traceable to the conditions that caused them.

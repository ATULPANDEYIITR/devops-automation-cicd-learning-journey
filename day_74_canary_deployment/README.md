# Canary Deployment: Traffic Splitting and Gradual Production Releases

## 1. Technical Scope

Canary deployment is a progressive software release technique in which a new application version receives a controlled portion of production traffic before becoming the primary production version.

Instead of replacing the existing version immediately, the deployment system introduces the candidate release to a limited group of requests. It measures operational behavior, evaluates predefined health policies, and increases traffic only when the observed results satisfy release conditions.

A canary deployment reduces the potential impact of defective releases by limiting exposure during the initial production period.

The implementation covers:

- Progressive traffic allocation.
- Stable request routing.
- Baseline and candidate performance comparison.
- Automated health evaluation.
- Sequential traffic promotion.
- Deployment state management.
- Automatic and manual rollback.
- Release audit history.
- Enterprise release policies.
- Relational persistence and database-level integrity.

## 2. Core Deployment Architecture

The system separates application versions, deployment orchestration, traffic routing, health evaluation, and release governance.

### Logical architecture

Application clients
        |
        v
Traffic Router
        |
        +----------------------+
        |                      |
        v                      v
Existing Version        Canary Version
        |                      |
        +----------+-----------+
                   |
                   v
             Observability
                   |
          +--------+--------+
          |                 |
          v                 v
       Metrics          Health Checks
          |                 |
          +--------+--------+
                   |
                   v
            Release Controller
                   |
          +--------+--------+
          |                 |
          v                 v
       Promotion          Rollback
          |                 |
          v                 v
     New Active         Previous Active
       Version             Version

The traffic router determines which application version receives a request. The release controller coordinates deployment stages. The observability component supplies performance measurements used by the health evaluator.

The deployment controller must not confuse traffic allocation with application version activation. A candidate may receive 5% of traffic while the previous version remains the primary production version.

## 3. Canary Deployment Fundamentals

### 3.1 Progressive traffic splitting

Traffic splitting determines the proportion of production requests directed to the candidate release.

The included standard rollout uses:

| Stage | Candidate traffic | Existing version traffic |
|---|---:|---:|
| Initial canary | 5% | 95% |
| Stage 2 | 10% | 90% |
| Stage 3 | 25% | 75% |
| Stage 4 | 50% | 50% |
| Full promotion | 100% | 0% |

For a total of 10,000 requests, a 5% allocation targets approximately 500 candidate requests.

The actual request count can differ because traffic allocation is probabilistic or hash-based and depends on the routing mechanism.

### 3.2 Stable request assignment

A routing system should avoid repeatedly moving the same client between application versions.

The implementations use deterministic hashing to assign request identifiers to traffic buckets.

The basic calculation is:

`bucket = hash(request_key) mod 100`

A request is routed to the candidate when:

`bucket < candidate_traffic_percentage`

Otherwise, it reaches the existing active version.

The C++ implementation uses FNV-1a hashing. JavaScript uses SHA-256. Python and Java use their standard hashing mechanisms for the demonstration.

Production systems should select a stable, appropriately distributed hash function and a consistent routing key.

A stable customer identifier is generally more useful than an individual request identifier when maintaining customer-level session consistency is important.

### 3.3 Baseline comparison

A baseline represents the operational behavior of the currently deployed version.

The candidate version is evaluated against both absolute thresholds and baseline-relative thresholds.

For example:

- Existing error rate: 1%.
- Candidate error rate: 1.2%.
- Maximum absolute error rate: 2%.
- Maximum permitted regression: 1.5 percentage points.

The candidate satisfies these error-rate conditions.

Absolute thresholds prevent unacceptable service behavior. Baseline comparisons identify deterioration relative to the existing implementation.

A healthy baseline is not necessarily a perfect baseline. Existing production problems should not automatically become acceptable candidate behavior.

## 4. Observability and Health Evaluation

A canary release depends on sufficiently reliable production measurements.

The implemented health evaluator considers:

| Metric | Purpose | Example policy |
|---|---|---:|
| Request count | Measurement sufficiency | At least 100 |
| Error rate | Reliability | Maximum 2% |
| P95 latency | Response performance | Maximum 500 ms |
| Error-rate regression | Relative degradation | Maximum 1.5 percentage points |
| Consecutive successful evaluations | Release stability | Configurable |

### 4.1 Error rate

Error rate measures the proportion of unsuccessful requests.

`Error rate = Failed requests / Total requests`

For example:

- Total requests: 1,000.
- Failed requests: 15.
- Error rate: 0.015 or 1.5%.

An error rate above the configured threshold causes the health evaluator to reject the candidate.

The implementation validates that the error count cannot exceed the total request count.

### 4.2 P95 latency

P95 latency is the response time below which 95% of measured requests complete.

It is useful for identifying degraded user experiences that average latency may conceal.

A service may have an acceptable average response time while a significant minority of requests experience substantial delays.

The implementations accept an externally measured P95 value. They do not calculate percentiles from raw request traces.

Production monitoring should use an appropriately sized sample and a consistent percentile calculation method.

### 4.3 Minimum observation requirements

A low request count can make performance measurements unreliable.

For example, observing zero failures in five requests does not establish that the candidate is safe.

The minimum request threshold prevents promotion based on inadequate observations.

A production implementation should also consider:

- Minimum observation duration.
- Traffic volume.
- Time-of-day effects.
- Seasonal traffic variations.
- Regional differences.
- Service dependencies.
- Statistical uncertainty.
- Delayed failure signals.

### 4.4 Consecutive successful evaluations

A configurable number of consecutive successful observations can reduce premature promotion.

For example, a policy requiring two successful evaluations prevents a single successful measurement from advancing traffic.

The Java enterprise implementation includes this policy explicitly.

A consecutive-pass requirement is not a substitute for sufficient sample sizes or appropriate monitoring windows.

## 5. Deployment Lifecycle and State Management

The implementations use explicit deployment states.

| State | Meaning |
|---|---|
| CREATED | Release registered but not activated |
| RUNNING | Candidate is receiving production traffic |
| PROMOTED | Candidate has become the active version |
| ROLLED_BACK | Candidate exposure has been removed |
| FAILED | Deployment failed before successful activation |

### State transition diagram

CREATED
   |
   v
RUNNING
   |
   +------------------+
   |                  |
   v                  v
PROMOTED          ROLLED_BACK
   |
   |
Terminal state

The failed state is also terminal.

The state model prevents invalid operations, such as:

- Starting an already active release.
- Evaluating a release that has been rolled back.
- Rolling back a promoted deployment.
- Increasing traffic after terminal completion.

State transitions are enforced through service-level validation in the programming-language implementations and a PostgreSQL trigger in the database implementation.

### 5.1 Promotion

Promotion occurs when the candidate completes the configured release stages successfully.

The controller:

1. Evaluates candidate health.
2. Confirms the current stage has passed.
3. Advances traffic allocation.
4. Repeats evaluation.
5. Marks the candidate as promoted at the final stage.
6. Updates the active application version.

The active version changes only after successful promotion.

### 5.2 Rollback

Rollback removes candidate traffic and restores the previously active version.

Typical rollback conditions include:

- Excessive application errors.
- Increased latency.
- Health-check failures.
- Significant baseline regression.
- Insufficient or invalid observations.
- Operational intervention.

Rollback is not the same as deployment deletion.

The deployment record remains available for auditing, investigation, and release analysis.

A rollback does not necessarily reverse database migrations or undo external side effects produced by the candidate application.

## 6. Python Implementation: Workflow Simulation

**File:** `canary_deployment.py`

The Python implementation provides an object-oriented deployment simulator.

### Main components

| Component | Responsibility |
|---|---|
| `DeploymentState` | Defines lifecycle states |
| `ReleasePolicy` | Stores traffic stages and health thresholds |
| `Metrics` | Represents operational observations |
| `Deployment` | Maintains release state and event history |
| `CanaryController` | Coordinates rollout and rollback |
| `TrafficRouter` | Selects the application version |
| `simulate_metrics()` | Produces reproducible observations |
| `run_tests()` | Validates important workflow conditions |

### Implementation mechanisms

The `ReleasePolicy` dataclass is immutable. This prevents accidental modification of thresholds during a deployment.

The `Deployment` dataclass maintains mutable operational state, including:

- Current traffic percentage.
- Current stage index.
- Consecutive successful observations.
- Deployment event history.

The controller stores releases in a dictionary indexed by release identifier.

This supports direct deployment lookup without repeatedly scanning the release collection.

### Validation

The implementation checks:

- Unique deployment identifiers.
- Non-empty version identifiers.
- Valid traffic stages.
- Valid metric counts.
- Baseline observation sufficiency.
- Legal deployment transitions.

The report is persisted as JSON using the standard library.

For production use, the JSON report should be written atomically and protected by appropriate filesystem permissions.

The simulator is single-process and does not implement distributed locking.

## 7. JavaScript Implementation: Event-Driven Deployment

**File:** `canary_deployment.js`

The JavaScript implementation provides an event-driven release control plane.

It uses Node.js standard-library capabilities.

### Main components

| Component | Responsibility |
|---|---|
| `HealthPolicy` | Evaluates release thresholds |
| `Deployment` | Manages release state |
| `TrafficRouter` | Routes requests by stable hash |
| `CanaryPlatform` | Coordinates deployment operations |
| `DeploymentError` | Represents operational failures |

### Event-driven behavior

The `Deployment` class extends `EventEmitter`.

Important deployment transitions generate events such as:

- `started`
- `health_passed`
- `traffic_increased`
- `promoted`
- `rolled_back`

This separates deployment state changes from monitoring, logging, and reporting.

Independent components can subscribe to deployment events without becoming part of the release controller's core logic.

### Concurrency control

The implementation uses a Promise-based exclusive execution mechanism.

This prevents overlapping observations from simultaneously changing the same deployment stage.

The controller serializes operations for an individual deployment.

This is a local process-level mechanism. It does not coordinate multiple Node.js instances or independent deployment controllers.

Distributed production environments require shared coordination, durable state, and atomic traffic configuration updates.

### Asynchronous execution

The deployment API exposes asynchronous operations.

This makes it suitable for integration with monitoring systems, deployment pipelines, and other asynchronous Node.js services.

The implementation writes its operational report through the asynchronous filesystem API.

## 8. C++17 Implementation: Governance Engine

**File:** `canary_deployment.cpp`

The C++ implementation focuses on a deterministic governance engine.

### Main domain structures

- `Metrics`: request and latency measurements.
- `Policy`: rollout and health requirements.
- `ReviewEvent`: immutable-style event information.
- `Deployment`: release state and operational history.
- `TrafficRouter`: deterministic request allocation.
- `GovernanceEngine`: central deployment policy enforcement.

### Engineering decisions

The implementation uses:

- `enum class` for explicit deployment states.
- `struct` for domain records.
- `vector` for sequential traffic stages.
- `map` for release lookup.
- `STL algorithms` for policy validation.
- `uint64_t` for deterministic hash calculations.
- Exceptions for invalid operations.

The routing mechanism uses FNV-1a to avoid dependence on implementation-specific string hash behavior.

The engine rejects illegal state transitions through exception handling.

### Performance characteristics

Let:

- N represent the number of deployments.
- S represent the number of traffic stages.
- H represent the length of the request-routing key.

Expected deployment lookup in `std::map` is O(log N).

Policy stage advancement is O(1).

Request hashing is O(H).

Deployment event insertion into a vector is amortized O(1).

The ordered map provides predictable lookup behavior at the cost of logarithmic rather than average constant-time lookup.

## 9. Java 17 Implementation: Enterprise Release Governance

**File:** `CanaryDeploymentEnterprise.java`

The Java implementation models an enterprise deployment service.

It emphasizes explicit domain types, configurable policies, audit records, and controlled service operations.

### Enterprise domain model

| Type | Responsibility |
|---|---|
| `Metrics` | Immutable performance measurements |
| `ReleasePolicy` | Immutable release requirements |
| `PolicyDecision` | Health evaluation result |
| `AuditEvent` | Timestamped operational event |
| `Release` | Individual release lifecycle |
| `HealthEvaluator` | Health evaluation contract |
| `ProductionHealthEvaluator` | Production health implementation |
| `DeploymentService` | Release orchestration |
| `RequestRouter` | Request allocation |

### Records and immutability

Java 17 records provide compact immutable data structures.

The implementation uses records for:

- Metrics.
- Release policies.
- Policy decisions.
- Audit events.

The release policy copies its traffic stages into an immutable list.

This prevents a caller from changing the rollout sequence after the policy has been constructed.

### Interface-based evaluation

The `HealthEvaluator` interface separates evaluation behavior from release state management.

The `ProductionHealthEvaluator` implementation evaluates:

- Error rate.
- P95 latency.
- Baseline regression.
- Minimum request count.

This structure allows alternative health evaluation policies without redesigning the deployment lifecycle.

### Manual approval

Enterprise releases may require manual approval before final promotion.

The policy explicitly represents whether manual approval is required.

The release records an approval event and prevents final promotion until the required approval is received.

A production authorization implementation should verify the approver's identity, role, permissions, and separation-of-duties requirements.

### Thread safety

The `Release` class uses `ReentrantLock` to protect state transitions.

The deployment service uses synchronized operations for release registration and active-version synchronization.

These controls are suitable for demonstrating local concurrency management.

A multi-instance enterprise platform requires durable distributed coordination, optimistic concurrency control, or transactional locking in a shared database.

## 10. PostgreSQL Implementation: Relational Deployment Governance

**File:** `canary_deployment.sql`

The PostgreSQL implementation stores deployment state and operational history in a relational database.

### Database relationship model

Applications
    |
    +---- Application Versions
    |
    +---- Deployments
              |
              +---- Environments
              |
              +---- Release Policies
              |         |
              |         +---- Traffic Stages
              |
              +---- Deployment Metrics
              |
              +---- Deployment Checks
              |
              +---- Deployment Approvals
              |
              +---- Deployment Events

### Principal tables

| Table | Purpose |
|---|---|
| `applications` | Registered applications and owning teams |
| `application_versions` | Application release artifacts |
| `environments` | Deployment environments and regions |
| `deployment_actors` | Human and automated deployment identities |
| `release_policies` | Health and promotion requirements |
| `policy_traffic_stages` | Ordered traffic allocation stages |
| `deployments` | Release lifecycle and current allocation |
| `deployment_metrics` | Baseline and candidate measurements |
| `deployment_checks` | Individual health evaluation results |
| `deployment_approvals` | Release authorization decisions |
| `deployment_events` | Operational audit history |

### 10.1 Referential integrity

Foreign keys connect releases to their application, version, environment, policy, and initiating actor.

Unique constraints prevent duplicate application versions and release identifiers.

Check constraints prevent:

- Negative request counts.
- Negative error counts.
- Error counts exceeding request counts.
- Invalid traffic percentages.
- Invalid latency values.
- Invalid policy thresholds.

### 10.2 Partial indexes

The database includes a partial unique index:

`one_active_deployment_per_application_environment`

This permits only one deployment in the `running` state for a given application and environment.

Completed deployments remain in the database without preventing future releases.

This is an important distinction between operational uniqueness and historical record retention.

### 10.3 Trigger-based integrity

The `validate_deployment_transition()` trigger enforces permitted state changes.

It also prevents traffic reductions unless the deployment is being rolled back.

The `record_deployment_state_event()` trigger automatically records important state transitions.

The trigger-based approach ensures that database updates performed outside the main application service still encounter core integrity checks.

### 10.4 Health evaluation function

`evaluate_canary_health()` evaluates the latest candidate observation against the configured release policy and baseline.

It produces:

- A Boolean eligibility result.
- A collection of failure reasons.

It also records individual check results in `deployment_checks`.

The function evaluates absolute error rate, baseline regression, latency, and minimum sample requirements.

### 10.5 Promotion procedure

`advance_canary()` provides a controlled database workflow.

It:

1. Locks the deployment row.
2. Validates its current state.
3. Retrieves the active policy.
4. Loads the latest canary observation.
5. Evaluates health.
6. Rolls back on failed health checks.
7. Advances the traffic stage after successful evaluation.
8. Checks promotion eligibility before final promotion.

The row lock prevents competing transactions from independently advancing the same deployment stage.

### 10.6 Reporting

The database provides two reporting views.

`active_production_releases` identifies active production deployments.

`deployment_health_report` aggregates candidate observations and reports weighted error rates and maximum observed P95 latency.

Additional queries demonstrate:

- Health-check failures.
- Deployment audit history.
- Policy traffic stages.
- Traffic allocation by application and environment.
- Missing recent canary observations.

## 11. Canary Deployment Versus Other Release Strategies

| Strategy | Release mechanism | Main characteristic |
|---|---|---|
| Canary | Gradual traffic allocation | Limits initial candidate exposure |
| Blue-green | Switch between two environments | Supports rapid environment-level switching |
| Rolling deployment | Replace instances incrementally | Progressively changes application instances |
| Recreate | Replace the existing deployment | Introduces a replacement deployment directly |
| Feature flag | Enable or disable functionality | Separates feature activation from application deployment |
| A/B testing | Divide users between experiences | Primarily evaluates behavioral or business outcomes |

Canary deployment focuses on controlled production exposure and operational health.

Blue-green deployment focuses on maintaining separate application environments.

Feature flags control feature availability and can operate independently of deployment version.

A/B testing evaluates differences in user or business outcomes. It does not necessarily provide the infrastructure health protections of a canary release.

These mechanisms can be combined.

## 12. Production Governance and Operational Security

A production canary controller should treat traffic configuration and deployment authorization as security-sensitive operations.

### Identity and access control

Different roles should have different permissions.

| Role | Typical responsibility |
|---|---|
| Release engineer | Initiate approved releases |
| Site reliability engineer | Monitor health and initiate rollback |
| Security reviewer | Validate security-related release requirements |
| Administrator | Manage deployment policies and permissions |
| Automation identity | Execute authorized pipeline operations |

Human identities and automated service identities should be independently authenticated.

Administrative access should not automatically imply permission to bypass every release policy.

### Artifact integrity

A deployment should reference an immutable artifact identifier or cryptographic digest.

A version label alone is insufficient to prove that the deployed binary corresponds to the approved artifact.

The PostgreSQL model stores artifact digests with application versions.

### Auditability

A deployment audit trail should capture:

- Release registration.
- Initiating identity.
- Deployment start.
- Traffic changes.
- Health evaluations.
- Approval decisions.
- Promotion.
- Rollback.
- Failure reasons.

Audit records should be protected from unauthorized alteration.

The demonstration database records events but does not implement tamper-proof external audit storage.

### Sensitive information

Operational metrics should not contain unnecessary personal or confidential customer information.

Routing identifiers should be appropriately protected or pseudonymized.

Production logging should avoid credentials, authentication tokens, and sensitive request payloads.

### Failure containment

Rollback is most effective when:

- The previous version remains available.
- Traffic configuration can be restored quickly.
- Candidate instances can be isolated.
- Database changes remain backward-compatible.
- External dependencies tolerate mixed application versions.

## 13. Important Production Limitations

The implementations are deliberately scoped engineering models rather than complete production orchestration platforms.

| Area | Demonstrated capability | Production consideration |
|---|---|---|
| Traffic allocation | Deterministic hash routing | Distributed load-balancer configuration |
| Monitoring | Error rate and P95 latency | Continuous metrics and tracing |
| Health policy | Threshold evaluation | Statistical confidence and observation windows |
| Rollback | Restore previous application version | External side-effect and database compatibility |
| Concurrency | Local synchronization | Distributed locking and transactional coordination |
| Persistence | JSON and PostgreSQL | Durable, replicated operational storage |
| Audit | Event history | Tamper-resistant audit retention |
| Approval | Configurable manual authorization | Identity and role verification |
| Promotion | Sequential stage advancement | Atomic production traffic updates |
| Regional deployment | Environment and region records | Independent regional health and capacity evaluation |

A particularly important limitation concerns database schema changes.

An application rollback may fail if the candidate release introduced an incompatible schema migration.

Backward-compatible database evolution is therefore essential when old and new application versions run simultaneously.

The expand-and-contract migration approach supports this requirement:

1. Expand the schema without breaking the existing application.
2. Deploy a compatible application version.
3. Migrate data where necessary.
4. Remove obsolete schema elements only after older application versions are no longer required.

## 14. Testing and Failure Scenarios

The five implementations demonstrate several important validation scenarios.

| Scenario | Expected behavior |
|---|---|
| Healthy candidate metrics | Advance to the next traffic stage |
| Excessive error rate | Roll back |
| Excessive P95 latency | Roll back |
| Baseline regression | Reject the candidate |
| Insufficient observations | Reject the health evaluation |
| Errors exceed requests | Reject invalid metrics |
| Duplicate release identifier | Reject registration |
| Unknown release | Raise an error |
| Repeated deployment start | Reject invalid transition |
| Evaluation after rollback | Reject invalid transition |
| Successful final stage | Promote candidate |
| Failed candidate | Preserve previous active version |

The Python, JavaScript, C++17, and Java 17 programs include executable assertions or runtime checks covering successful promotion, rollback, and invalid state transitions.

The PostgreSQL script includes both successful and failing health observations.

The failure scenario demonstrates why a release controller must retain explicit rollback behavior rather than relying exclusively on successful deployment commands.

## 15. Complexity and Scalability Considerations

Traffic routing, health evaluation, and deployment orchestration have different computational characteristics.

| Operation | Expected complexity |
|---|---|
| Hash-based routing | O(H), where H is routing-key length |
| Health threshold evaluation | O(1) per observation |
| Traffic stage advancement | O(1) with indexed stage position |
| Python dictionary lookup | Average O(1) |
| JavaScript Map lookup | Average O(1) |
| C++ ordered map lookup | O(log N) |
| PostgreSQL deployment lookup | Index-dependent |
| Audit insertion | Amortized O(1), excluding database index costs |

For high-volume environments, health observations should be aggregated over controlled time windows instead of storing every raw request measurement in the deployment control database.

High-cardinality metrics should be handled carefully because they can increase monitoring storage and query costs.

The release controller should also avoid treating correlated observations as independent evidence. Multiple successful measurements from the same short observation period do not necessarily establish independent evidence of application stability.

## 16. Practical Release Execution Sequence

A production-oriented canary workflow follows this sequence:

1. Register the application version and immutable artifact digest.
2. Identify the existing active production version.
3. Select an approved release policy.
4. Collect baseline operational measurements.
5. Validate the baseline sample.
6. Start the candidate deployment.
7. Route a small proportion of production traffic to the candidate.
8. Collect candidate metrics.
9. Evaluate error rates, latency, and regression.
10. Verify required approvals and operational conditions.
11. Increase candidate traffic incrementally.
12. Repeat health evaluation at every stage.
13. Promote the candidate at 100% traffic.
14. Preserve the deployment history.
15. Roll back immediately when critical release conditions fail.

The key operational principle is that deployment completion and deployment success are different events. A release is successful only when the candidate satisfies its operational and governance requirements.

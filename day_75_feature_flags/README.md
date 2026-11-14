# Feature Flags: Decoupling Deployment from Feature Release

## 1. Project Overview

Feature flags are configuration-driven controls that determine whether specific application functionality is available at runtime.

They establish a separation between two software delivery activities:

- **Deployment:** Making application code available in an execution environment.
- **Release:** Making a particular capability available to selected users.

A feature can therefore be deployed to production without being immediately exposed to production users.

The application evaluates a flag whenever the relevant functionality is requested. The evaluation result determines whether the new implementation or an existing implementation should execute.

This approach supports controlled releases, progressive delivery, experimentation, operational safety, and independent release management.

### Core delivery model

Traditional deployment and release:

Code development → Testing → Production deployment → Feature availability

Feature-flag-driven delivery:

Code development → Testing → Production deployment → Runtime configuration → Controlled feature release

The application binary can remain unchanged while release configuration changes.

## 2. Technical Architecture

The implementations use a common domain model with different engineering perspectives.

| Component | Responsibility |
|---|---|
| Feature Flag | Defines a controllable application capability |
| Environment | Determines where a flag can operate |
| Evaluation Context | Provides user and group information |
| Targeting Rules | Determine which users qualify |
| Rollout Policy | Controls percentage-based exposure |
| Flag Status | Controls activation, disabling, and retirement |
| Configuration Version | Identifies a particular configuration revision |
| Approval Policy | Governs authorization of configuration changes |
| Kill Switch | Immediately disables a capability |
| Audit Log | Records configuration changes |
| Evaluation History | Records runtime evaluation outcomes |
| Expiration | Prevents indefinite retention of temporary flags |

### Logical architecture

Application Request  
↓  
Evaluation Context  
↓  
Feature Flag Service  
↓  
Environment Validation  
↓  
Status and Expiration Validation  
↓  
User and Group Targeting  
↓  
Percentage Rollout Evaluation  
↓  
Feature Enabled / Feature Disabled  
↓  
Audit and Operational Monitoring

The application is responsible for implementing both the enabled and disabled behavior safely.

## 3. Fundamental Concepts

### 3.1 Deployment and release decoupling

Deployment makes executable code available to an environment.

Release controls the availability of that code to users.

For example, an organization can deploy a redesigned checkout service to production while keeping the corresponding feature flag disabled.

The old checkout implementation remains available as the default behavior. The new implementation becomes available only after the release configuration permits it.

This arrangement provides several operational benefits:

- Separates application deployment from product decisions.
- Supports gradual user exposure.
- Reduces the impact of defective functionality.
- Enables controlled testing in production.
- Supports rapid feature disabling without rebuilding the application.
- Allows product and engineering teams to coordinate release decisions independently.

Feature flags do not eliminate deployment risk. Defective shared infrastructure, database migrations, incompatible APIs, and application-wide failures can still affect users.

### 3.2 Feature flag types

The implementations distinguish three principal flag types.

| Type | Mechanism | Typical use |
|---|---|---|
| Boolean | Uses a configured default value | Enable or disable a capability |
| Percentage | Assigns users to a deterministic rollout cohort | Progressive release |
| Targeted | Enables explicitly authorized users or groups | Beta testing and controlled access |

Boolean flags provide simple operational control.

Percentage flags provide controlled exposure across a user population.

Targeted flags support restricted testing and explicit audience selection.

A targeted flag does not automatically expose a capability to everyone outside its configured audience.

### 3.3 Environment isolation

A flag may be available in development and staging but unavailable in production.

| Environment | Purpose |
|---|---|
| Development | Developer testing |
| Staging | Pre-production verification |
| Production | Real operational traffic |

Environment configuration is separate from the feature's global status.

An active flag can still be unavailable in production when its production environment configuration is disabled.

### 3.4 Evaluation context

Evaluation requires information about the requesting user and execution environment.

The implementations support:

- User identifiers.
- Environment identifiers.
- Group memberships.
- Additional user attributes where appropriate.

The context should be constructed from trusted application identity information.

Client-supplied identifiers must not independently establish privileged targeting eligibility.

## 4. Targeting and Progressive Rollout

### 4.1 Explicit targeting

Explicit targeting provides access to predefined users or groups.

For example:

- An administrator may receive access to a new payment workflow.
- Members of a beta-testing group may receive a redesigned interface.
- Standard users may continue using the existing implementation.

Explicit user and group targeting takes priority over percentage allocation in these implementations.

This ordering makes controlled testing possible even when the percentage rollout is very small.

### 4.2 Percentage-based rollout

Percentage rollout determines which users receive a feature.

The implementations use deterministic hashing.

The conceptual calculation is:

`bucket = hash(flag_key + ":" + user_id)`

The resulting value is normalized into a range from 0 to 100.

The feature is enabled when:

`bucket < rollout_percentage`

For a 25% rollout, approximately one-quarter of the possible hash buckets qualify.

For a 50% rollout, approximately half qualify.

The same user receives the same allocation for the same flag key, provided the hashing algorithm and allocation scheme remain unchanged.

This avoids random assignment on every application request.

### 4.3 Why deterministic allocation matters

Random evaluation can cause inconsistent user experiences.

A customer might see the new checkout page on one request and the old checkout page on the next request.

Stable allocation avoids this problem.

Deterministic assignment also supports:

- Reproducible testing.
- Consistent feature exposure.
- Better operational debugging.
- Cohort-level monitoring.
- Gradual rollout expansion.

The sample implementations use SHA-256 or FNV-1a-based allocation.

These mechanisms provide stable assignment, not user authentication or authorization.

They should not be treated as security boundaries.

### 4.4 Progressive release strategy

A typical release can follow this sequence:

| Stage | Rollout | Operational activity |
|---|---:|---|
| Development | Internal | Verify functionality |
| Staging | Internal | Validate integration |
| Initial production | 1% | Observe initial behavior |
| Early expansion | 5% | Monitor error rates |
| Controlled expansion | 10% | Evaluate performance |
| Intermediate expansion | 25% | Review user impact |
| Broad release | 50% | Validate system stability |
| Full release | 100% | Complete exposure |

The percentages are illustrative rather than mandatory release thresholds.

Progression should depend on measured service health, business outcomes, security requirements, and operational capacity.

A rollout should pause or reverse when predefined release criteria are violated.

## 5. Python Implementation

### File characteristics

The Python implementation provides a self-contained feature flag management service.

It uses standard-library facilities, including:

- `dataclasses` for domain structures.
- `Enum` for controlled state values.
- `hashlib` for deterministic cohort assignment.
- `threading.RLock` for synchronized configuration access.
- `json` for configuration persistence.
- `pathlib` for filesystem operations.
- `logging` for operational diagnostics.
- `tempfile` for isolated persistence testing.

### FeatureFlagService

The service maintains two primary collections:

- A dictionary containing registered feature flags.
- A list containing audit events.

The dictionary provides efficient flag lookup by key.

The reentrant lock protects configuration updates, evaluations, and snapshots from concurrent access within the process.

### Important operations

| Method | Responsibility |
|---|---|
| `register()` | Registers a validated flag |
| `get()` | Retrieves a flag |
| `evaluate()` | Determines user eligibility |
| `update_rollout()` | Changes percentage exposure |
| `disable()` | Activates the kill switch |
| `enable()` | Restores an eligible flag |
| `archive()` | Retires a flag |
| `save()` | Persists configuration |
| `load()` | Restores validated configuration |
| `report()` | Generates an inventory |

### Persistence and failure handling

Configuration is written to a temporary file before replacement.

This reduces the likelihood of leaving a partially written configuration file when an ordinary filesystem operation fails.

Loading validates the complete configuration before replacing the service's current flag collection.

The example does not implement distributed configuration synchronization, encryption at rest, or durable audit transactions.

A production service should use a transactional database or a dedicated configuration-management service.

### Important limitation

The Python lock protects only one process.

Multiple application instances require centralized configuration, version control, and a consistent distribution mechanism.

## 6. JavaScript Implementation

### Event-driven architecture

The JavaScript implementation adopts an event-driven design using Node.js standard-library capabilities.

`EventEmitter` provides notifications for configuration changes, audit events, and evaluation errors.

This makes it possible for monitoring and operational components to subscribe to changes without becoming tightly coupled to the flag-management implementation.

### Asynchronous evaluation

The `evaluate()` method returns a Promise.

This provides an interface that can be extended to support remote configuration retrieval, distributed caching, and network-based evaluation services.

`evaluateBatch()` uses `Promise.all()` to evaluate multiple flags concurrently.

The batch interface returns a structured object mapping flag keys to their evaluation results.

### Optimistic concurrency

Each flag maintains a configuration version.

An update must supply the version expected by the caller.

For example:

- Current version: 4
- First administrator updates the configuration.
- New version: 5.
- Another administrator submits an update based on version 4.
- The second update is rejected.

This prevents stale configuration from silently overwriting a newer configuration.

### Immutable snapshots

The `snapshot()` method exposes a frozen configuration representation.

This limits accidental modification by consumers of the service.

The internal flag collection remains under the engine's control.

### Event categories

| Event | Purpose |
|---|---|
| `audit` | Records administrative changes |
| `flag:key` | Reports changes to an individual flag |
| `evaluation` | Reports evaluation outcomes |
| `evaluation:error` | Reports missing flags |

### Operational considerations

An event listener can itself fail. Production event handling should isolate listener failures and prevent monitoring failures from interrupting configuration management.

The in-memory event history is not durable and should be replaced or supplemented by persistent audit storage.

## 7. C++17 Implementation

### Engineering perspective

The C++17 implementation emphasizes explicit domain modeling, deterministic evaluation, and low-overhead data structures.

It uses:

- Structures for evaluation contexts and audit records.
- Enumerations for flag types, statuses, and environments.
- Classes for configuration management.
- `std::map` for flag lookup.
- `std::set` for user and group membership.
- `std::vector` for audit history.
- STL algorithms for validation.
- Exceptions for invalid operations.

### Deterministic hashing

The implementation uses FNV-1a to produce stable allocation buckets.

This is computationally inexpensive and suitable for deterministic cohort assignment.

It is not a cryptographic hash and must not be used to protect sensitive identity information or enforce access control.

### Configuration replacement

Updates operate on a copied configuration.

The new object is validated before replacing the existing configuration.

This reduces the risk of partially applying an invalid update.

### Version management

Every successful configuration modification increments the version.

An update based on an outdated version produces a concurrency conflict.

### Kill-switch behavior

The kill switch changes the flag status to `DISABLED`.

Subsequent evaluations reject the feature regardless of user targeting or percentage configuration.

### Performance characteristics

| Operation | Expected complexity |
|---|---|
| Flag lookup | O(log F) |
| User lookup | O(log U) |
| Group lookup | O(log G) |
| Hash evaluation | O(L) |
| Audit insertion | Amortized O(1) |
| Full inventory | O(F log F) |

Where:

- F represents the number of feature flags.
- U represents the number of explicitly targeted users.
- G represents the number of configured groups.
- L represents the length of the hash input.

The implementation is a single-process simulation. It does not provide distributed synchronization or thread-safe concurrent updates.

## 8. Java 17 Implementation

### Enterprise-oriented design

The Java implementation uses a layered architecture.

| Component | Responsibility |
|---|---|
| `FeatureFlag` | Immutable configuration model |
| `EvaluationContext` | Immutable user context |
| `FlagRepository` | Configuration persistence abstraction |
| `InMemoryFlagRepository` | Demonstration repository |
| `RolloutPolicy` | Targeting and percentage evaluation |
| `ApprovalPolicy` | Administrative authorization rules |
| `AuditService` | Change-event recording |
| `FeatureFlagService` | Application and governance operations |

### Domain modeling

Java records represent evaluation contexts, evaluation results, and audit events.

Immutable collections prevent callers from modifying stored targeting configuration through exposed collection references.

The repository interface separates business logic from the storage implementation.

The in-memory implementation can be replaced with a database-backed repository without changing the basic evaluation policy.

### Approval policy

Configuration modification requires:

1. An authorized release manager or platform administrator.
2. The configured number of approvals.
3. A valid configuration version.

This demonstrates how enterprise release governance can be incorporated into feature configuration management.

The sample approval mechanism is an in-memory policy model. It does not provide a complete enterprise identity, approval-signature, or separation-of-duties infrastructure.

### State transitions

The implementation supports:

`ACTIVE → DISABLED`

`DISABLED → ACTIVE`

`ACTIVE → ARCHIVED`

`DISABLED → ARCHIVED`

Archived flags cannot be reactivated through the provided service operations.

Expired flags cannot be enabled.

### Concurrency considerations

The service synchronizes configuration-changing operations.

The repository also synchronizes its individual storage operations.

A production distributed implementation should use database transactions, optimistic locking, and atomic configuration publication rather than relying on JVM-level synchronization.

## 9. PostgreSQL Database Architecture

The PostgreSQL implementation provides a relational model for feature flag configuration and governance.

### 9.1 Database entities

| Table | Purpose |
|---|---|
| `teams` | Organizational ownership |
| `users` | User identities |
| `user_groups` | Targeting groups |
| `user_group_memberships` | User-to-group relationships |
| `team_members` | Team roles |
| `feature_flags` | Primary flag configuration |
| `flag_environments` | Environment-specific availability |
| `flag_user_targets` | Explicit user targeting |
| `flag_group_targets` | Group targeting |
| `flag_approval_policies` | Approval requirements |
| `flag_change_requests` | Proposed configuration changes |
| `flag_change_approvals` | Approval decisions |
| `flag_evaluations` | Evaluation history |
| `flag_audit_log` | Administrative history |

### 9.2 Relational structure

Teams  
→ Team Members  
→ Users  
→ Group Memberships  
→ User Groups

Feature Flags  
→ Environment Configuration  
→ User Targets  
→ Group Targets  
→ Approval Policies  
→ Change Requests  
→ Change Approvals  
→ Evaluation History  
→ Audit History

### 9.3 Integrity constraints

The schema uses:

- Primary keys to identify records.
- Foreign keys to enforce relationships.
- Unique constraints to prevent duplicate identities and memberships.
- Check constraints to validate rollout percentages.
- Check constraints to validate flag keys and configuration versions.
- Enumerated types to constrain lifecycle states.
- Indexes to support common reporting and lookup operations.

### 9.4 Evaluation function

The `evaluate_flag()` function evaluates a feature using:

- Flag existence.
- User validity.
- Flag status.
- Expiration.
- Environment availability.
- Explicit user targeting.
- Group targeting.
- Boolean configuration.
- Percentage allocation.

The caller supplies a deterministic bucket in the interval `[0, 100)`.

The database implementation intentionally does not implement a hash function matching the application-language implementations. A production deployment must standardize bucket generation across all application instances and database consumers.

### 9.5 Approval workflow

The database maintains configuration requests separately from active configurations.

A request contains:

- Requested change.
- Proposed flag type.
- Proposed status.
- Proposed rollout percentage.
- Proposed default value.
- Expected configuration version.
- Requesting user.
- Approval state.

Reviewers record independent approval or rejection decisions.

The `is_change_eligible()` function evaluates whether the approval requirements have been satisfied.

The `apply_flag_change()` procedure:

1. Locks the change request.
2. Checks the request state.
3. Evaluates the approval policy.
4. Locks the current feature flag.
5. Checks the expected configuration version.
6. Applies the proposed configuration.
7. Increments the configuration version.
8. Marks the request as applied.
9. Records the resulting audit event.

The procedure must execute within a transaction so that a failed operation does not leave a partially applied change.

### 9.6 Audit and evaluation history

Audit history and evaluation history represent different operational records.

**Audit history** records administrative actions, including configuration creation and updates.

**Evaluation history** records the runtime decision for a particular user and environment.

This distinction allows administrators to investigate both configuration changes and actual feature exposure.

Evaluation history can grow rapidly. Production deployments should implement retention policies, partitioning, and appropriate access restrictions.

## 10. Feature Flag Lifecycle

Feature flags should have an explicit lifecycle.

### Creation

A team creates a flag with:

- A unique key.
- A clear description.
- An owner.
- A flag type.
- A default behavior.
- Environment restrictions.
- An optional expiration date.

### Configuration

The team defines targeting rules and rollout parameters.

Changes should be validated before publication.

### Controlled activation

The feature is made available to a restricted population.

Operational monitoring verifies that the new functionality behaves as expected.

### Progressive expansion

The rollout percentage increases according to predefined release criteria.

Monitoring should cover:

- Error rates.
- Response latency.
- Resource utilization.
- Transaction failures.
- Security events.
- User experience.
- Business metrics.

### Emergency disable

When the new functionality causes unacceptable behavior, the kill switch disables the feature.

The disabled path must be designed and tested before release.

### Retirement

After the feature has been fully released and the old implementation is no longer needed, the temporary flag should be removed.

A flag should not remain indefinitely without an identified owner or purpose.

## 11. Distinguishing Operational Controls

Feature flags support several related but distinct mechanisms.

| Mechanism | Primary function |
|---|---|
| Feature flag | Controls runtime feature availability |
| Environment configuration | Restricts availability by execution environment |
| Targeting | Selects eligible users or groups |
| Percentage rollout | Controls cohort exposure |
| Approval policy | Controls who can authorize configuration changes |
| Version control | Prevents stale updates |
| Kill switch | Disables functionality during an incident |
| Audit logging | Preserves administrative accountability |
| Expiration | Limits the lifetime of temporary flags |

A feature flag does not replace authentication, authorization, deployment controls, network security, or database migration management.

Sensitive capabilities must still enforce authorization independently of flag evaluation.

## 12. Security and Reliability Considerations

### Configuration access

Only authorized identities should be able to modify production flags.

Application users should not receive unrestricted configuration-management privileges.

### Secret management

Feature flag configurations should not contain passwords, API keys, private keys, or other secrets.

### Trusted identity

Targeting decisions must use trusted user identities.

A client must not be able to impersonate an administrator by changing a user identifier in an HTTP request.

### Kill-switch reliability

Emergency disabling should not depend on deploying new application code.

Production systems should distribute configuration changes rapidly and define acceptable propagation delays.

### Failure behavior

The system must define what happens when configuration retrieval fails.

A sensible approach depends on the feature:

- Nonessential experimental functionality should generally fail closed.
- Essential existing functionality should retain its independently implemented safe fallback.
- Security-sensitive operations must not depend on a feature flag as their only authorization mechanism.

### Configuration consistency

Multiple application instances must use compatible configuration versions.

Stale caches can cause different instances to evaluate the same user differently.

A distributed implementation should define cache expiration, configuration invalidation, version propagation, and recovery behavior.

### Observability

Monitoring should distinguish:

- Flag evaluation failures.
- Configuration retrieval failures.
- Application failures.
- Feature-specific business failures.

An enabled flag does not prove that the underlying feature is functioning correctly.

## 13. Feature Flag Categories and Appropriate Uses

| Category | Example | Expected lifetime |
|---|---|---|
| Release flag | New checkout interface | Temporary |
| Experiment flag | Alternative search layout | Experiment duration |
| Operational flag | Disable external payment routing | As operationally required |
| Permission flag | Restricted internal capability | Governed by authorization policy |
| Migration flag | Gradual transition to a new database-backed service | Migration duration |

These categories have different operational and governance requirements.

Release flags should generally be removed after a successful release.

Operational switches may remain as long-term controls when they have a clearly defined purpose and owner.

Permission-related flags must never replace proper access-control enforcement.

## 14. Testing and Validation Scenarios

The implementations include executable demonstrations and assertions.

Important scenarios include:

| Test | Expected behavior |
|---|---|
| Valid Boolean flag | Returns configured default |
| Unknown flag | Returns disabled |
| Inactive flag | Returns disabled |
| Expired flag | Returns disabled |
| Environment mismatch | Returns disabled |
| Explicit user target | Returns enabled |
| Explicit group target | Returns enabled |
| Percentage below threshold | Returns enabled |
| Percentage above threshold | Returns disabled |
| Repeated user evaluation | Produces stable allocation |
| Invalid percentage | Rejects configuration |
| Duplicate flag key | Rejects registration |
| Stale configuration version | Rejects update |
| Kill switch activation | Immediately blocks subsequent evaluations |
| Unauthorized change | Rejects modification |
| Archived flag | Remains unavailable |

Additional production tests should cover:

- Concurrent configuration updates.
- Distributed cache invalidation.
- Configuration service outages.
- High evaluation volume.
- Large targeting groups.
- Database transaction failures.
- Audit persistence failures.
- Application restarts.
- Configuration rollback.
- Partial deployment.
- Mixed application versions.

## 15. Performance and Scalability

Feature flag evaluation is normally performed frequently, potentially on every relevant application request.

The evaluation path should therefore remain lightweight.

### Performance principles

- Cache validated configuration locally.
- Use hash-based deterministic allocation.
- Avoid unnecessary database queries during request processing.
- Keep targeting rules bounded.
- Separate evaluation from administrative updates.
- Avoid writing a synchronous database record for every evaluation in high-throughput systems.
- Use asynchronous telemetry or aggregated evaluation statistics where appropriate.
- Apply expiration and retention policies to historical data.

### Complexity comparison

| Operation | Python | JavaScript | C++17 | Java 17 |
|---|---|---|---|---|
| Flag lookup | Average O(1) | Average O(1) | O(log F) | Average O(1) |
| User targeting | Average O(1) | Average O(1) | O(log U) | Average O(1) |
| Group targeting | Average O(1) | Average O(1) | O(log G) | Average O(1) |
| Percentage evaluation | O(L) | O(L) | O(L) | O(L) |
| Audit insertion | Amortized O(1) | Amortized O(1) | Amortized O(1) | Amortized O(1) |

F represents the number of flags, U the number of explicitly targeted users, G the number of groups, and L the hash input length.

The actual performance depends on runtime characteristics, collection sizes, synchronization, and the persistence implementation.

## 16. Implementation Limitations

These five implementations are executable educational models rather than complete distributed feature management platforms.

| Area | Current implementation | Production consideration |
|---|---|---|
| Configuration storage | In-memory or JSON in application examples | Centralized durable storage |
| Configuration delivery | Local service state | Distributed configuration updates |
| Evaluation | Local deterministic rules | Standardized cross-service evaluation |
| Authentication | Trusted identity assumed | Integrated identity provider |
| Authorization | Simplified administrative policies | Fine-grained role-based access |
| Audit | Local collections or database records | Durable, access-controlled audit storage |
| Approval | Simplified approval rules | Enterprise approval workflow |
| Monitoring | Console and database reports | Metrics, tracing, alerting |
| Rollback | Configuration state change | Versioned configuration restoration |
| Experimentation | Percentage allocation | Statistical experiment design |
| Security | Basic validation | Threat modeling and security testing |

The Python and JavaScript examples do not provide distributed locking.

The C++ example does not implement concurrent access protection.

The Java example uses an in-memory repository.

The PostgreSQL implementation provides relational persistence and transactional approval processing, but the caller remains responsible for standardized deterministic bucket generation.

## 17. Running the Implementations

### Python

Requirements: Python 3.10 or later.

Run the script directly using Python. It requires no third-party packages.

### JavaScript

Requirements: Node.js 18 or later.

Run the file using Node.js. It uses only built-in modules.

### C++17

Requirements: A compiler supporting C++17.

Compile with the C++17 language standard and run the resulting executable.

### Java 17

Requirements: JDK 17.

Compile the file named `Main.java` and execute its `Main` class.

### PostgreSQL

Requirements: PostgreSQL 15 or later.

Execute the complete SQL script against a database using `psql`.

The script creates the `feature_management` schema and its associated objects and demonstration records.

Running the SQL script again against an existing installation requires an explicit database reset or migration strategy because the schema objects are not designed as a repeatable migration.

## 18. Learning Outcomes

The implementations demonstrate the following technical concepts:

- Runtime configuration and deployment independence.
- Feature lifecycle management.
- Deterministic user cohort assignment.
- Boolean, percentage, and targeted evaluation.
- Environment-specific configuration.
- Event-driven state notifications.
- Optimistic concurrency control.
- Immutable configuration models.
- Enterprise approval policies.
- Emergency kill-switch design.
- Relational modeling and integrity constraints.
- Transactional configuration updates.
- Audit and evaluation history.
- Operational reporting.
- Failure handling and configuration validation.

The central engineering principle is that application deployment and feature availability are separate decisions. A controlled runtime configuration layer makes it possible to release functionality progressively while preserving an independently maintained fallback and an operational mechanism for disabling problematic features.

# Release Management: Versioning, Approvals and Release Governance

## 1. Domain Overview

Release management is the controlled process of preparing, validating, authorizing, publishing and maintaining software releases.

It connects software development with operational deployment and establishes accountability for changes entering production environments.

A release is not simply a version number or a collection of commits. It is a governed delivery unit containing:

- A defined software version.
- A source-code reference.
- A build artifact.
- Release notes.
- Quality validation results.
- Approval decisions.
- Deployment authorization.
- Deployment history.
- Rollback information.
- An auditable sequence of events.

The implementations model release management as a stateful business process with explicit eligibility rules.

### Four important concepts

| Concept | Purpose |
|---|---|
| Release Management | Coordinates the complete release lifecycle. |
| Versioning | Identifies software versions and their compatibility implications. |
| Approvals | Records accountable authorization decisions. |
| Release Governance | Establishes and enforces organizational release requirements. |

These concepts are related but not interchangeable.

Versioning identifies a release. Approvals record decisions about its suitability. Governance determines whether organizational requirements have been met. Release management coordinates the resulting operational workflow.

---

## 2. Release Lifecycle

A controlled release follows a sequence of states.

| State | Meaning |
|---|---|
| Draft | Release metadata and artifact information are being prepared. |
| Candidate | The release has entered formal validation and approval. |
| Approved | Required governance conditions have been satisfied. |
| Released | The approved version has been deployed to its intended production environment. |
| Rejected | The release has been rejected before deployment. |
| Rolled Back | A previously deployed release has been withdrawn from production. |

### State transition model

    DRAFT
      |
      v
    CANDIDATE
      |
      +------> REJECTED
      |
      v
    APPROVED
      |
      +------> REJECTED
      |
      v
    RELEASED
      |
      v
    ROLLED_BACK

The model prevents arbitrary state changes.

For example:

- A draft cannot be deployed directly.
- A candidate cannot be deployed without approval.
- An approved release cannot bypass deployment authorization.
- A rejected release cannot become released through an ordinary state update.
- A rolled-back release remains part of the historical record.

A production deployment is a separate operational action from approving a release.

This distinction is important because approval authorizes deployment but does not establish that deployment actually succeeded.

---

## 3. Semantic Versioning

Semantic Versioning provides a structured approach to identifying software changes.

The conventional format is:

`MAJOR.MINOR.PATCH`

| Component | Meaning | Example |
|---|---|---|
| Major | Incompatible public interface changes | 4.0.0 |
| Minor | Backward-compatible functionality | 4.2.0 |
| Patch | Backward-compatible corrections | 4.2.1 |

### Version progression

    4.2.0
      |
      +----> 4.2.1    Patch release
      |
      +----> 4.3.0    Minor release
      |
      +----> 5.0.0    Major release

Prerelease identifiers can distinguish versions that are not yet considered stable.

Examples:

- `5.0.0-alpha.1`
- `5.0.0-beta.2`
- `5.0.0-rc.1`
- `5.0.0`

A prerelease is not equivalent to the final stable release.

The implementations validate version syntax and use version comparisons when checking production deployment eligibility.

A production version must advance rather than regress.

One important distinction is that semantic versioning does not independently establish deployment eligibility. A correctly formatted version can still fail security checks, approval requirements or deployment policies.

The implementations use simplified prerelease ordering. A production-grade implementation should implement the complete Semantic Versioning 2.0.0 comparison rules, including numeric and textual prerelease identifier precedence.

---

## 4. Release Artifacts and Source Integrity

A release should identify both the source revision and the artifact being deployed.

These represent different objects.

| Element | Meaning |
|---|---|
| Source commit | Identifies the source-code revision. |
| Build artifact | The actual packaged software output. |
| Artifact digest | Cryptographic identifier calculated from artifact contents. |
| Release version | Human-readable software version. |
| Release notes | Description of changes included in the release. |

The implementations calculate SHA-256 digests for build artifacts.

A digest helps establish whether the artifact has changed after validation.

For example:

    Source commit
         |
         v
    Build pipeline
         |
         v
    Release artifact
         |
         v
    SHA-256 digest
         |
         v
    Release candidate
         |
         v
    Deployment

A source commit identifier does not prove that an artifact was built from that commit. Production systems should maintain build provenance, signed artifacts, trusted build identities and verifiable source-to-artifact relationships.

The database stores the commit identifier and artifact digest separately.

---

## 5. Release Approval Management

Approvals represent formal decisions made by authorized organizational participants.

An approval is not merely a notification or an informal statement that a release looks acceptable.

A decision should contain:

- Reviewer identity.
- Reviewer role.
- Release identifier.
- Decision.
- Decision timestamp.
- Supporting comments.

### Approval decisions

| Decision | Meaning |
|---|---|
| Pending | No final decision has been submitted. |
| Approved | The reviewer authorizes the release within their responsibility. |
| Rejected | The reviewer identifies a reason the release should not proceed. |

### Reviewer responsibilities

| Role | Typical responsibility |
|---|---|
| Security Lead | Security assessment and vulnerability disposition. |
| Engineering Lead | Technical readiness and implementation integrity. |
| QA Lead | Test completeness and quality validation. |
| Product Owner | Functional acceptance and business readiness. |
| Release Manager | Release coordination and governance execution. |

The implementations support eligible reviewer roles and minimum approval thresholds.

For example, a policy may require two distinct approvals.

Two approval records from the same reviewer must not count as two independent decisions.

A rejection blocks eligibility even when the required number of approvals has otherwise been achieved.

### Approval requirements versus approval records

An approval record describes an individual reviewer's decision.

An approval requirement describes the minimum organizational condition that must be satisfied.

These are different data structures and responsibilities.

The approval engine counts eligible, distinct reviewers and compares the result against the configured threshold.

An approval does not automatically authorize deployment. The release must still satisfy the applicable quality and governance conditions.

### Stale approvals

An approval may become invalid when the underlying release changes materially.

For example:

- A new artifact is generated.
- The source commit changes.
- A critical dependency is replaced.
- A security finding is introduced.
- The release scope changes.

The sample implementations maintain immutable release identity after creation, but do not implement automatic approval invalidation when an artifact is replaced.

A production system should bind approvals to a specific release revision or artifact digest and require renewed decisions when material changes occur.

---

## 6. Automated Release Validation

Automated quality checks provide technical evidence for release readiness.

The implementations use four mandatory checks.

| Check | Purpose |
|---|---|
| Unit Tests | Validate individual components. |
| Integration Tests | Validate interactions between components. |
| Security Scan | Identify security weaknesses. |
| Dependency Audit | Identify vulnerable or problematic dependencies. |

### Quality gate evaluation

A release becomes eligible only when:

1. It is in candidate state.
2. Release notes are present.
3. The artifact digest is valid.
4. The required approval threshold is satisfied.
5. No reviewer has rejected the release.
6. Every mandatory quality check has passed.
7. The target environment permits the version.
8. No applicable governance restriction is violated.

The evaluation produces two outputs:

- Eligibility status.
- A collection of blocking conditions.

This is preferable to returning only a Boolean result because operators need to understand why a release is blocked.

### Quality gate example

    Release candidate
          |
          v
    Artifact validation
          |
          v
    Automated testing
          |
          v
    Security validation
          |
          v
    Dependency validation
          |
          v
    Reviewer decisions
          |
          v
    Governance evaluation
          |
       +--+--+
       |     |
      PASS  FAIL
       |     |
       v     v
    Approve  Block

A pending check is not considered successful.

A missing check is also a blocking condition.

---

## 7. Release Governance

Release governance defines the organizational rules that determine whether a release can progress.

It is broader than approval collection.

A governance policy can specify:

- Minimum approval count.
- Eligible reviewer roles.
- Required automated checks.
- Artifact integrity requirements.
- Release-note requirements.
- Prerelease restrictions.
- Production version progression.
- Emergency release permissions.
- Deployment authorization.

### Policy evaluation

Consider a production release requiring:

| Requirement | Required condition |
|---|---|
| Approvals | At least two eligible reviewers |
| Unit tests | Passed |
| Integration tests | Passed |
| Security scan | Passed |
| Dependency audit | Passed |
| Artifact | Valid SHA-256 digest |
| Release notes | Present |
| Version | No production regression |
| Environment | Production permitted |

If any mandatory requirement is not satisfied, the release remains blocked.

### Emergency releases

Emergency releases are operationally important because critical security or availability issues may require accelerated delivery.

An emergency override should not automatically bypass every control.

A mature policy can define:

- Who may declare an emergency.
- Which requirements can be waived.
- Which requirements remain mandatory.
- Who must authorize the exception.
- How the exception is recorded.
- Whether retrospective review is required.

The sample implementations include emergency-override policy fields or validation concepts, but do not provide a complete emergency authorization workflow.

---

## 8. Deployment Management

Deployment is the process of introducing an approved software version into an environment.

Typical environments include:

| Environment | Purpose |
|---|---|
| Development | Initial engineering integration. |
| Staging | Preproduction validation. |
| Production | Operational software delivery. |

The sample systems distinguish staging from production and prevent deployment when the release is not approved for the production target.

### Deployment workflow

    Approved release
          |
          v
    Deployment authorization
          |
          v
    Artifact verification
          |
          v
    Deployment execution
          |
       +--+--+
       |     |
    Success Failure
       |     |
       v     v
    Update  Incident
    version investigation

The PostgreSQL implementation stores deployment attempts independently from release records.

This is important because one release can have multiple deployment attempts across environments.

A production implementation should also maintain deployment health checks, rollout percentages, infrastructure identifiers, deployment durations and operational incident references.

---

## 9. Rollback Management

Rollback restores a previously deployed software version when a new release creates unacceptable operational consequences.

Possible reasons include:

- Increased application errors.
- Transaction failures.
- Performance degradation.
- Security incidents.
- Data compatibility problems.
- Unexpected infrastructure interactions.

A rollback is not the same as deleting a release.

The original release remains part of the audit history.

The system records:

- The release being withdrawn.
- The restored version.
- The responsible operator.
- The rollback reason.
- The rollback timestamp.

### Rollback workflow

    Production version 5.3.0
             |
             v
       Incident detected
             |
             v
       Rollback authorized
             |
             v
       Restore version 5.2.0
             |
             v
       Verify service health
             |
             v
       Record rollback event

The previous version must be known and successfully deployed.

A rollback also requires operational compatibility.

For example, an application rollback may be unsafe after an irreversible database schema migration.

The sample implementations model version restoration but do not execute actual binary deployment or database restoration.

---

## 10. Python Implementation

**File:** `release_management.py`

The Python implementation models the complete release lifecycle using domain-oriented classes.

### Main structures

| Structure | Responsibility |
|---|---|
| `Version` | Semantic version parsing and progression. |
| `Release` | Release identity and mutable lifecycle state. |
| `ReleasePolicy` | Governance configuration. |
| `Approval` | Reviewer decisions. |
| `QualityCheck` | Automated validation results. |
| `ReleaseManager` | Workflow orchestration. |

### Important mechanisms

**Dataclasses**

Dataclasses provide structured representations of releases, approvals and quality checks.

**Enums**

Enums restrict lifecycle states, decisions, environments and check results to recognized values.

**Dictionaries and sets**

Dictionaries provide direct release lookup, while sets provide efficient membership checks for required checks and published versions.

**Exception handling**

The implementation distinguishes validation errors, governance violations and version conflicts.

**Artifact integrity**

The standard-library `hashlib` module calculates SHA-256 digests.

**Audit persistence**

JSON serialization records release metadata, approvals, checks and audit events.

The file is written through a temporary file followed by replacement to reduce the risk of partially written audit files.

### Execution

Run:

`python release_management.py`

The demonstration creates a production release, completes automated checks, collects two approvals, evaluates eligibility and deploys the release.

A second candidate demonstrates blocked eligibility due to missing approvals and quality checks.

The resulting audit file is `release_audit.json`.

---

## 11. JavaScript Implementation

**File:** `release_management.js`

The JavaScript implementation emphasizes event-driven orchestration and asynchronous quality validation.

### Main structures

| Structure | Responsibility |
|---|---|
| `Release` | Release state and event history. |
| `ReleaseGovernance` | Governance and deployment services. |
| `Map` | Release, approval and quality-check storage. |
| `Set` | Published-version tracking. |
| `EventEmitter` | Release lifecycle notifications. |
| `Promise.allSettled()` | Independent asynchronous check execution. |

### Event-driven behavior

The engine emits events when:

- A release is created.
- A candidate is submitted.
- An approval is recorded.
- Governance approval is granted.
- A release is deployed.
- A release is rolled back.

Event subscribers can respond without coupling every operational component to the release-management service.

### Asynchronous validation

`executeChecks()` runs independent validation functions concurrently.

`Promise.allSettled()` ensures that a failed security check does not prevent the remaining check results from being collected.

Each failure becomes an explicit failed result.

### Execution

Run:

`node release_management.js`

The demonstration produces one successful production release and one blocked candidate with a failed security check.

The audit is exported to `release-audit.json`.

---

## 12. C++17 Implementation

**File:** `release_management.cpp`

The C++ implementation emphasizes a governance engine with explicit domain structures and controlled state transitions.

### Main structures

| Structure | Responsibility |
|---|---|
| `Version` | Version representation and comparison. |
| `Release` | Release identity and lifecycle information. |
| `Approval` | Individual reviewer decisions. |
| `QualityCheck` | Automated validation evidence. |
| `ReleasePolicy` | Governance configuration. |
| `Evaluation` | Eligibility result and blockers. |
| `ReleaseGovernanceEngine` | Governance operations. |

### Engineering decisions

The implementation uses:

- `std::map` for deterministic keyed storage.
- `std::set` for required checks and published versions.
- `std::vector` for ordered audit history.
- Enumerations for controlled domain states.
- Exceptions for invalid operations.
- Standard algorithms for validation.

The engine separates evaluation from deployment.

This allows a release to be inspected without modifying its lifecycle state.

The implementation also prevents duplicate reviewer decisions and production version regression.

### Complexity considerations

| Operation | Expected complexity |
|---|---|
| Release lookup | O(log n) |
| Approval lookup | O(log a) |
| Check lookup | O(log c) |
| Required-check evaluation | O(c log c) |
| Release insertion | O(log n) |
| Audit append | Amortized O(1) |

Here, `n` represents the number of releases, `a` the number of approvals and `c` the number of quality checks.

### Compilation

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic release_management.cpp -o release_management`

Execution:

`./release_management`

The program demonstrates successful governance evaluation and a blocked incomplete candidate.

---

## 13. Java 17 Implementation

**File:** `ReleaseManagement.java`

The Java implementation adopts an enterprise service-oriented architecture.

### Domain model

The principal domain objects are:

- `Release`
- `Version`
- `Approval`
- `QualityCheck`
- `ReleasePolicy`
- `AuditEvent`
- `EligibilityResult`

### Service architecture

`ReleaseService` coordinates release creation, candidate submission, approval collection, evaluation, deployment and rollback.

`ReleaseValidator` defines a validation contract.

`ArtifactValidator` implements artifact digest and source-commit validation.

This separates validation responsibilities from release orchestration.

### Java 17 features

**Records**

Records represent immutable approval decisions, check results, audit events, policies and eligibility reports.

**Enums**

Enums provide controlled release states and decisions.

**Streams**

Streams are used to count decisions and process audit records.

**Collections**

Maps provide indexed release and approval storage. Sets track published versions.

**Immutable policy configuration**

The policy record copies supplied collections to prevent external modification.

**Custom exceptions**

Validation and governance failures are represented through separate exception types.

**SHA-256**

`MessageDigest` calculates artifact digests.

**Audit export**

The implementation exports release history to CSV with field escaping.

### Execution

Compile:

`javac ReleaseManagement.java`

Run:

`java ReleaseManagement`

The program generates an enterprise release report and exports `release-audit.csv`.

---

## 14. PostgreSQL Database Architecture

**File:** `release_management.sql`

The database implementation provides relational persistence and transactional release governance.

### Entity relationships

    USERS
      |
      +---- USER_ROLES
      |
      +---- PRODUCTS
                 |
                 +---- PRODUCT_VERSIONS
                 |
                 +---- GOVERNANCE_POLICIES
                 |          |
                 |          +---- POLICY_REQUIRED_CHECKS
                 |          |
                 |          +---- POLICY_ELIGIBLE_ROLES
                 |
                 +---- RELEASES
                            |
                            +---- RELEASE_APPROVALS
                            |
                            +---- RELEASE_CHECKS
                            |
                            +---- DEPLOYMENTS
                            |
                            +---- AUDIT_EVENTS
                            |
                            +---- ROLLBACK_EVENTS

### Table responsibilities

| Table | Purpose |
|---|---|
| `users` | Organizational identities. |
| `user_roles` | Reviewer and operational authorization roles. |
| `products` | Software product ownership. |
| `product_versions` | Semantic version records. |
| `governance_policies` | Product-level release rules. |
| `policy_required_checks` | Mandatory validation checks. |
| `policy_eligible_roles` | Authorized approval roles. |
| `releases` | Release lifecycle records. |
| `release_approvals` | Reviewer decisions. |
| `release_checks` | Automated quality evidence. |
| `deployments` | Deployment attempts and outcomes. |
| `production_versions` | Current production version. |
| `rollback_events` | Historical rollback operations. |
| `audit_events` | Release-related audit history. |

### Constraints and integrity

Primary keys establish entity identity.

Foreign keys preserve relationships between releases, products, reviewers, policies and deployments.

Unique constraints prevent duplicate release identifiers, product versions and reviewer decisions.

Check constraints validate version components, commit identifiers and artifact digests.

Indexes support common release, approval, check and audit queries.

### Database functions

| Function | Responsibility |
|---|---|
| `update_timestamp()` | Maintains modification timestamps. |
| `enforce_release_transition()` | Restricts invalid lifecycle transitions. |
| `audit_release_change()` | Records state changes. |
| `evaluate_release()` | Determines governance eligibility. |
| `submit_release()` | Submits a draft candidate. |
| `record_release_approval()` | Records an authorized reviewer decision. |
| `approve_release()` | Grants governance approval. |
| `rollback_release()` | Records a rollback and restores a previous production version. |

### Database procedure

`deploy_release()` performs production deployment within the calling transaction.

It:

1. Locks the release record.
2. Verifies approved state.
3. Verifies the production target.
4. Validates the deployer.
5. Serializes deployments for the product.
6. Checks version progression.
7. Creates a deployment record.
8. Updates the production version.
9. Marks the release as released.

If an operation fails, the transaction can be rolled back rather than leaving partially updated production metadata.

### Transaction management

The script uses an explicit transaction for schema creation and sample data.

Production deployment and rollback operations should also be invoked within controlled database transactions.

### Reporting

The database includes:

- Release governance reporting.
- Approval aggregation.
- Quality-check statistics.
- Deployment history.
- Current production version reporting.
- CTE-based readiness analysis.
- Audit event retrieval.
- Eligibility evaluation with blocking reasons.

### Execution

Create the database:

`createdb release_management`

Execute:

`psql -d release_management -f release_management.sql`

The SQL script creates its dedicated schema, builds the domain model, inserts sample data, executes governance workflows and produces reporting queries.

---

## 15. Cross-Language Design Comparison

| Engineering concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Domain modeling | Dataclasses | Classes | Structs and classes | Records and classes | Relational tables |
| Versioning | `Version` | `parseVersion()` | `Version` | `Version` | `product_versions` |
| Approval storage | Lists | Maps | Maps | Maps | Relational records |
| Quality checks | Dictionaries | Maps | Maps | Maps | `release_checks` |
| Policy evaluation | Manager | Governance service | Governance engine | Release service | SQL function |
| Event handling | Audit list | EventEmitter | Audit vector | Audit list | Audit table |
| State control | Enums | Frozen constants | Enums | Enums | Enum types and triggers |
| Persistence | JSON | JSON | In-memory | CSV | Relational database |
| Failure handling | Exceptions | Rejected promises and exceptions | Exceptions | Custom exceptions | SQL exceptions |
| Rollback | Version restoration | Version restoration | Version restoration | Version restoration | Transactional records |

The implementations share a common release-governance domain but use different engineering approaches.

Python emphasizes rapid workflow simulation.

JavaScript emphasizes asynchronous orchestration and event notifications.

C++ emphasizes explicit domain structures and controlled evaluation.

Java emphasizes enterprise service boundaries and immutable policy configuration.

PostgreSQL emphasizes persistent integrity, relational constraints and transactional operations.

---

## 16. Security and Operational Considerations

Release governance has security implications beyond application functionality.

### Artifact integrity

A release should be tied to a verifiable artifact digest.

A digest detects content changes but does not establish who produced the artifact.

Production environments should use signed artifacts and trusted build provenance.

### Separation of duties

A release author should not automatically satisfy independent approval requirements.

Reviewer eligibility should be based on assigned roles and organizational authorization.

High-risk releases may require approval from multiple independent functions.

### Least privilege

Deployment permissions should be separate from ordinary reviewer permissions.

A deployment service should receive only the access needed for its designated environment.

### Auditability

Audit records should preserve:

- Actor identity.
- Event type.
- Release identifier.
- Previous and new states.
- Timestamp.
- Decision details.
- Deployment result.

The demonstration programs maintain in-memory audit histories and export files.

The PostgreSQL implementation stores audit events relationally.

For production use, audit records should have restricted update and deletion permissions, protected backups and appropriate retention policies.

### Concurrency

Two release operators may attempt to deploy different versions of the same product simultaneously.

The database procedure uses a product-level row lock to serialize production deployment updates.

A production deployment service should also use idempotency keys and deployment leases where appropriate.

### Database security

The demonstration SQL uses schema-level isolation and integrity constraints.

A production deployment should additionally configure:

- Separate database roles.
- Least-privilege grants.
- Restricted schema ownership.
- Secure credential storage.
- Encrypted connections.
- Backup and recovery procedures.
- Audited administrative access.

---

## 17. Limitations and Implementation Boundaries

These implementations are executable educational models rather than complete integrations with external release platforms.

| Capability | Demonstrated | Not implemented |
|---|---|---|
| Semantic versioning | Parsing and basic comparison | Complete SemVer prerelease precedence |
| Release lifecycle | Explicit state transitions | Distributed lifecycle orchestration |
| Approvals | Reviewer decisions and thresholds | Enterprise identity provider integration |
| Quality gates | Simulated check results | Real CI/CD execution |
| Artifact integrity | SHA-256 digest | Artifact signing and provenance verification |
| Deployment | Governed state update | Actual infrastructure deployment |
| Rollback | Published version restoration | Binary, database and infrastructure restoration |
| Audit | Event history and exports | Tamper-proof external audit storage |
| Governance | Policy evaluation | Full organizational exception management |
| Persistence | JSON, CSV and PostgreSQL | Distributed event sourcing |

The PostgreSQL demonstration uses simplified prerelease version comparison and does not implement complete semantic-version precedence.

The Python, JavaScript, C++ and Java examples maintain process-local state. Their audit exports are not substitutes for durable transactional storage.

A real deployment platform must also address artifact retention, deployment health monitoring, database migration compatibility, secrets management, disaster recovery and concurrent operational workflows.

---

## 18. Technical Learning Outcomes

The five implementations demonstrate how release management can be modeled as a controlled software-delivery process.

The central engineering principle is the separation of identity, evidence, decisions, policy and operational execution.

- Versioning identifies the software release.
- Artifact integrity identifies the validated build.
- Quality checks provide technical evidence.
- Approvals record authorized human decisions.
- Governance evaluates organizational requirements.
- Deployment changes the operational environment.
- Rollback restores a previously deployed version.
- Audit records preserve accountability.

A release should progress to production only when the required evidence, authorization and governance conditions are satisfied.

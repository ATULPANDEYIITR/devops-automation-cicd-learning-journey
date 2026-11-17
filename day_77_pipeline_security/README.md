# Pipeline Security: Secrets, Permissions, and Supply-Chain Security

## 1. Introduction

Pipeline security protects the automated processes used to build, test, package, publish, and deploy software.

A software pipeline executes operations using identities, permissions, credentials, dependencies, build environments, and artifacts. A weakness in any of these components can allow unauthorized access, software modification, credential theft, or deployment of compromised software.

Three major security areas form the foundation of pipeline security:

1. **Secrets security:** Protecting credentials and sensitive configuration values.
2. **Permission security:** Controlling what pipeline identities and individual jobs can access or modify.
3. **Supply-chain security:** Verifying the integrity, origin, and security of software dependencies, build processes, and artifacts.

These areas are related but enforce different security properties.

| Security area | Primary concern | Main protection |
|---|---|---|
| Secrets security | Credential exposure | Secure storage, controlled retrieval, rotation, and revocation |
| Permission security | Unauthorized operations | Identity verification and least privilege |
| Supply-chain security | Compromised software components | Dependency verification, vulnerability assessment, and provenance |

The implementations provide five complementary perspectives:

| Deliverable | Engineering perspective |
|---|---|
| Python | Repository and pipeline security simulation |
| JavaScript | Event-driven security evaluation |
| C++17 | Policy enforcement and execution eligibility |
| Java 17 | Enterprise security services and domain modeling |
| PostgreSQL | Persistent security records, integrity constraints, and reporting |

## 2. Pipeline Security Architecture

A software delivery pipeline generally follows this sequence:

Source Repository  
→ Pipeline Trigger  
→ Identity Verification  
→ Permission Evaluation  
→ Secret Access Control  
→ Dependency Verification  
→ Build and Test  
→ Artifact Creation  
→ Provenance Verification  
→ Deployment Authorization  
→ Production Deployment  
→ Security Audit

Each stage introduces different security requirements.

### 2.1 Pipeline execution environment

A pipeline execution environment contains:

- Pipeline configuration.
- Execution identities.
- Job definitions.
- Environment variables.
- Secrets.
- Build tools.
- Third-party actions and plugins.
- External dependencies.
- Build artifacts.
- Deployment credentials.

The security boundary determines which resources a pipeline can access.

A pipeline that builds an application should not automatically receive production deployment permissions.

Likewise, a testing job should not automatically receive credentials belonging to a production deployment job.

### 2.2 Pipeline jobs and isolation

A pipeline can contain multiple independent jobs.

For example:

| Job | Required access |
|---|---|
| Source validation | Repository read |
| Unit testing | Repository read |
| Dependency scanning | Repository read and package metadata read |
| Artifact packaging | Repository read and package write |
| Production deployment | Deployment write and narrowly scoped deployment credentials |

The principle is to provide each job with only the permissions and secrets required for its operation.

## 3. Secrets Security

### 3.1 Meaning of secrets

Secrets are confidential values used to authenticate or authorize access to systems.

Examples include:

- API tokens.
- Database passwords.
- SSH private keys.
- Cloud access credentials.
- Deployment tokens.
- Signing keys.
- Registry credentials.
- Encryption keys.

A secret differs from an ordinary configuration value because disclosure can provide unauthorized access to another system.

### 3.2 Secret lifecycle

Secret management involves several stages.

| Stage | Operation | Security requirement |
|---|---|---|
| Creation | Generate a credential | Use sufficient randomness |
| Storage | Save the credential | Encrypt using managed keys |
| Authorization | Grant access | Restrict access to approved identities |
| Retrieval | Supply the credential to a job | Avoid unnecessary exposure |
| Rotation | Replace an existing credential | Update dependent systems safely |
| Revocation | Disable a compromised credential | Prevent further use |
| Expiration | End credential validity | Enforce time-based restrictions |

The Python `SecretManager`, JavaScript `SecretVault`, and Java `SecretService` implement these lifecycle operations.

The PostgreSQL schema stores encrypted secret payloads, key references, versions, expiration dates, and access grants.

### 3.3 Secret storage

Secrets should not be committed directly into source repositories.

The following locations are unsuitable for storing plaintext credentials:

- Source code.
- Repository configuration files.
- Public documentation.
- Container images.
- Build artifacts.
- Unrestricted environment variables.
- Debugging output.
- Application logs.

A dedicated secret-management system should store encrypted values and provide controlled access.

The encryption key should be managed separately from the encrypted secret.

This separation reduces the consequences of unauthorized database access.

### 3.4 Secret retrieval authorization

Secret retrieval requires two independent conditions:

1. The requested secret exists and remains valid.
2. The requesting job has an active authorization grant.

The Python implementation uses `allowed_secrets`.

The JavaScript implementation uses a private `Map` and `Set`-based identity permissions.

The Java implementation uses immutable `JobIdentity` records and a `ConcurrentHashMap`-based secret repository.

The database implements `secret_access_grants` and `validate_secret_access()`.

A missing grant, disabled secret, expired credential, or revoked credential results in denied access.

### 3.5 Secret rotation

Rotation replaces an existing credential with a new value.

The replacement should update the credential version and ensure dependent services can use the new value.

A secure rotation process should:

1. Generate a replacement credential.
2. Update the secret-management system.
3. Update the dependent application or service.
4. Verify successful authentication.
5. Revoke the previous credential.
6. Record the operation.

Rotation should not expose either the old or new credential in audit records.

### 3.6 Secret masking

Masking prevents known secret values from appearing in application output.

For example:

Original:

`Authorization: Bearer abc123secretvalue`

Masked:

`Authorization: Bearer ***REDACTED***`

The implementations provide masking methods that replace known secret values.

Masking is a supplementary protection. It does not prevent a compromised job from transmitting a secret through an external network connection.

Production systems should combine masking with restricted network access, secure logging, controlled process execution, and short-lived credentials.

### 3.7 Untrusted pull requests

External contributions introduce an important security risk.

A contributor may submit changes to pipeline configuration or application scripts. Executing those changes with production credentials can expose secrets.

The implementations therefore support a policy that blocks secret access for untrusted pull requests.

A safer execution model separates:

- Untrusted validation jobs.
- Trusted repository workflows.
- Protected deployment jobs.

Untrusted code should not execute with production credentials or privileged deployment identities.

## 4. Permission Security

### 4.1 Identity and authorization

An identity represents an entity requesting access to a resource.

Examples include:

- A developer.
- A repository administrator.
- A service account.
- A pipeline job.
- A deployment agent.

Authentication establishes the identity.

Authorization determines what the identity is permitted to do.

These operations must remain separate.

A successfully authenticated identity is not automatically authorized to access every resource.

### 4.2 Least privilege

Least privilege means granting the smallest permission set necessary for an operation.

Consider two pipeline identities.

| Permission | Testing job | Deployment job |
|---|---|---|
| Repository read | Yes | Yes |
| Repository write | No | No |
| Deployment write | No | Yes |
| Package read | Yes | As required |
| Package write | No | As required |
| Identity token creation | No | Only if required |

The deployment job receives additional authority only because its operation requires it.

The permission implementations enforce access through explicit checks.

### 4.3 Permission categories

The implementations use the following permission categories:

| Permission | Purpose |
|---|---|
| `contents:read` | Read repository contents |
| `contents:write` | Modify repository contents |
| `actions:read` | Read pipeline information |
| `actions:write` | Modify pipeline-related resources |
| `packages:read` | Retrieve packages |
| `packages:write` | Publish packages |
| `deployments:read` | Inspect deployments |
| `deployments:write` | Execute authorized deployment operations |
| `id-token:write` | Request an identity token |

A permission should be granted according to the actual job requirements.

Broad permissions increase the consequences of compromised pipeline execution.

### 4.4 Job-level permissions

Permission assignment at the job level provides better isolation than granting all permissions to an entire pipeline.

For example:

A testing job needs repository read access.

A deployment job needs repository read access and deployment write access.

If both jobs receive deployment write permission, compromising the testing job may provide an unnecessary route to production deployment.

The `PermissionManager`, `PermissionPolicy`, `PermissionEngine`, and `PermissionService` implement permission evaluation in their respective languages.

### 4.5 Permission validation

The implementations demonstrate several validation rules:

- An identity must have a valid name.
- Permission sets must remain within configured limits.
- Write operations must satisfy the applicable access policy.
- Secret access must be explicitly authorized.
- Unauthorized deployment operations must fail.
- Excessive secret grants must be rejected.

A permission check must occur at the point where the protected operation is performed.

Checking permissions only during initial pipeline creation is insufficient if the permissions can change before execution.

## 5. Supply-Chain Security

### 5.1 Meaning of software supply chain

The software supply chain consists of the components and processes used to create and distribute software.

It includes:

- Source code.
- Third-party libraries.
- Package registries.
- Build tools.
- Pipeline actions.
- Container images.
- Build environments.
- Artifact storage.
- Deployment infrastructure.

An attacker does not necessarily need to compromise the application's source code.

Compromising a dependency, package repository, build action, or artifact distribution process may produce a similar result.

### 5.2 Dependency management

A dependency is an external software component used by an application.

Examples include:

- Python packages.
- JavaScript packages.
- Java libraries.
- C++ libraries.
- Container base images.
- Build plugins.

A dependency should have a known identity and version.

Dependency verification should establish that the downloaded component corresponds to the expected component.

### 5.3 Dependency pinning

Dependency pinning specifies the exact version or immutable reference of a software component.

Consider two dependency references:

| Reference | Security characteristic |
|---|---|
| `framework` | Does not specify a version |
| `framework@1.2.0` | Specifies a version |

An exact version provides better reproducibility than an unrestricted reference.

A cryptographic digest provides an additional integrity check.

Pinning does not establish that a dependency is vulnerability-free. It establishes a more precise identity for the dependency.

### 5.4 Cryptographic integrity verification

The implementations use SHA-256 digest comparison.

A digest represents the result of applying a cryptographic hash function to a file or other data.

The verification process is:

1. Obtain the expected digest from a trusted source.
2. Calculate the digest of the downloaded component.
3. Compare both values.
4. Reject the component if the values differ.

<math block value="H(D_{downloaded}) = H(D_{expected})"/>

In this expression, the expected and downloaded digest values must refer to the same package contents.

A matching digest supports integrity verification but does not establish that the original package was safe.

The expected digest must itself come from a trusted source.

### 5.5 Vulnerability assessment

A dependency may be authentic but still contain a security vulnerability.

The implementations distinguish dependency integrity from vulnerability severity.

| Condition | Result | Decision |
|---|---|---|
| Digest matches and no high-severity finding exists | Verified | Eligible |
| Digest mismatch | Unverified | Reject |
| Unapproved package source | Blocked | Reject |
| High-severity vulnerability | Vulnerable | Reject |
| Critical vulnerability | Vulnerable | Reject |

The examples use severity classifications:

- Low.
- Medium.
- High.
- Critical.

Production vulnerability assessment should also consider exploitability, available fixes, affected versions, deployment exposure, and documented risk acceptance.

### 5.6 Software composition analysis

Software composition analysis identifies third-party components and their associated security risks.

Its main functions include:

- Dependency inventory.
- Version identification.
- Vulnerability identification.
- License identification.
- Dependency relationship analysis.
- Remediation tracking.

The PostgreSQL implementation separates dependency records from vulnerability findings.

This permits several findings to be associated with one dependency.

### 5.7 Immutable pipeline action references

Pipeline configurations often use third-party actions or plugins.

An action reference can point to a mutable tag or an immutable commit identifier.

For example:

| Reference | Characteristic |
|---|---|
| `v2` | Mutable version tag |
| Full 40-character commit SHA | Immutable commit reference |

A mutable tag can be moved to different code.

A full commit SHA provides a fixed reference to the selected revision.

The Python, JavaScript, C++17, and Java implementations include validation that rejects mutable references when pinning is required.

Pinning should be combined with source verification and regular security updates.

### 5.8 Artifact provenance

An artifact is a software output produced by a build process.

Examples include:

- Executable files.
- Container images.
- Application packages.
- Deployment bundles.
- Compiled libraries.

Artifact provenance describes where an artifact came from and how it was produced.

A provenance record can contain:

| Field | Purpose |
|---|---|
| Artifact name | Identifies the output |
| Artifact digest | Identifies the artifact contents |
| Source commit | Identifies the source revision |
| Builder identity | Identifies the build environment |
| Dependencies | Records the components used |
| Creation time | Records when the artifact was produced |
| Attestation | Provides verifiable provenance evidence |

The implementations use HMAC-SHA256 to demonstrate integrity-protected attestations.

An HMAC is a message authentication code that uses a shared secret key.

The artifact metadata is converted into a canonical representation before the signature is calculated.

Verification recalculates the authentication code and compares it with the supplied attestation.

Changing the artifact digest, source commit, builder identity, or dependency list invalidates the attestation.

The HMAC examples are educational integrity mechanisms. Production artifact signing should generally use asymmetric signing identities, managed keys, verifiable provenance statements, and independent verification.

## 6. Pipeline Policy Evaluation

Pipeline security depends on several independent checks.

A successful dependency scan does not compensate for excessive permissions.

Likewise, valid artifact provenance does not authorize an otherwise prohibited deployment.

The implementations therefore evaluate several conditions before execution.

| Policy | Required condition |
|---|---|
| Identity policy | Valid pipeline identity |
| Permission policy | Only authorized operations |
| Secret policy | No unauthorized secret exposure |
| Dependency policy | Approved and verified dependencies |
| Vulnerability policy | No prohibited vulnerability findings |
| Action policy | Immutable action references |
| Provenance policy | Valid artifact attestation |
| Deployment policy | Explicit deployment authorization |

### 6.1 Security decision model

The basic eligibility decision can be represented as:

<math block value="E = I \\land P \\land S \\land D \\land V \\land A \\land R"/>

Where:

- \(E\): Pipeline eligibility.
- \(I\): Valid identity.
- \(P\): Valid permissions.
- \(S\): Secret access compliance.
- \(D\): Dependency integrity.
- \(V\): Vulnerability policy compliance.
- \(A\): Artifact provenance.
- \(R\): Required deployment authorization.

A failed mandatory condition blocks the pipeline.

This model represents a fail-closed approach: missing or invalid security evidence does not automatically become approval.

## 7. Pipeline State Management

Pipeline execution requires explicit state transitions.

The implementations use the following states:

| State | Meaning |
|---|---|
| `CREATED` | Execution request has been created |
| `VALIDATING` | Security policies are being evaluated |
| `RUNNING` | Authorized execution is in progress |
| `BLOCKED` | A security policy prevents execution |
| `SUCCEEDED` | Execution completed successfully |
| `FAILED` | Execution failed |

The permitted transitions are:

CREATED  
↓  
VALIDATING  
↓  
RUNNING  
↓  
SUCCEEDED

Alternative transitions:

VALIDATING → BLOCKED

VALIDATING → FAILED

RUNNING → BLOCKED

RUNNING → FAILED

The PostgreSQL trigger `validate_pipeline_transition()` enforces permitted transitions.

This prevents invalid state changes, such as directly moving a newly created execution into a successful state.

The application implementations also prevent duplicate processing of the same pipeline run.

## 8. Language-Specific Implementation Decisions

### 8.1 Python implementation

The Python script uses standard-library features to construct a complete security simulation.

| Component | Implementation |
|---|---|
| `AuditLogger` | Security event collection |
| `SecretManager` | Secret storage and lifecycle |
| `PermissionManager` | Authorization decisions |
| `SupplyChainScanner` | Dependency integrity and vulnerability assessment |
| `ProvenanceManager` | HMAC-based artifact attestation |
| `ConfigurationValidator` | Action pinning and unsafe interpolation checks |
| `PipelineSecurityEngine` | Pipeline policy evaluation |

Python-specific design decisions include:

- Dataclasses for domain records.
- Enums for security states.
- Sets for permission and secret membership checks.
- Dictionaries for secret storage.
- Exceptions for security violations.
- Assertions for executable validation scenarios.
- `hmac.compare_digest()` for authentication-code comparison.

Dictionary and set membership checks generally provide average constant-time lookup.

The dependency scanner operates in linear time relative to the number of dependencies, excluding string-processing costs.

The script demonstrates six failure scenarios, including unauthorized secret access, mutable action references, dependency tampering, and untrusted input interpolation.

### 8.2 JavaScript implementation

The JavaScript file emphasizes asynchronous execution and event-driven monitoring.

| Component | Implementation |
|---|---|
| `SecurityEventBus` | Event publication |
| `AuditRepository` | Event retrieval and filtering |
| `SecretVault` | Private secret storage |
| `PermissionPolicy` | Permission validation |
| `DependencyRegistry` | Dependency assessment |
| `ProvenanceService` | Artifact attestation |
| `PipelinePolicyEngine` | Policy evaluation |
| `PipelineExecutor` | Asynchronous pipeline execution |

JavaScript-specific design decisions include:

- Private class fields for internal secret storage.
- `Map` for secret records.
- `Set` for authorization membership.
- `EventEmitter` for security notifications.
- `async` and `await` for asynchronous execution.
- `Promise` for execution completion.
- `crypto.timingSafeEqual()` for digest and authentication-code comparisons.

The event-driven design separates security event production from audit collection.

This makes it possible to add independent monitoring consumers without embedding all monitoring operations inside the execution engine.

### 8.3 C++17 implementation

The C++ program models a repository and pipeline governance engine.

Its main objective is evaluating whether proposed software changes satisfy the configured security conditions.

| Component | Responsibility |
|---|---|
| `JobIdentity` | Pipeline execution identity |
| `PermissionEngine` | Access control |
| `DependencyScanner` | Dependency integrity |
| `ProvenanceVerifier` | Artifact evidence validation |
| `ApprovalEngine` | Reviewer decision evaluation |
| `MergeEligibilityEngine` | Merge condition evaluation |
| `PipelineGovernance` | Execution policy enforcement |
| `AuditLog` | Security event recording |

C++17-specific decisions include:

- Enumerations for security states.
- Structures for domain objects.
- STL sets for unique identities and permissions.
- STL vectors for dependency and review collections.
- `std::optional`-compatible domain design for extending optional security evidence.
- Exceptions for rejected operations.
- Algorithms such as `std::all_of`, `std::any_of`, and `std::count_if`.

The merge eligibility engine evaluates:

- Pull Request status.
- Draft status.
- Target branch.
- Eligible approvals.
- Requested changes.
- Status checks.
- Conversation resolution.
- Linear history.
- Dependency verification.
- Artifact provenance.

The program demonstrates the difference between a review decision and a final merge eligibility decision.

### 8.4 Java 17 implementation

The Java implementation follows an enterprise service-oriented architecture.

| Service | Responsibility |
|---|---|
| `AuditService` | Audit event management |
| `SecretService` | Credential lifecycle |
| `PermissionService` | Identity authorization |
| `SupplyChainService` | Dependency verification |
| `ProvenanceService` | Artifact attestation |
| `WorkflowPolicy` | Pipeline configuration validation |
| `ApprovalService` | Approval policy |
| `BranchProtectionService` | Protected branch enforcement |
| `PipelineExecutionService` | Pipeline execution |

Java-specific design decisions include:

- Records for immutable domain objects.
- Enums for controlled states.
- Interfaces and service boundaries through independent service classes.
- `Set` and `List` for collections.
- Streams for filtering and aggregation.
- `ConcurrentHashMap` for concurrent state management.
- `CompletableFuture` for asynchronous pipeline execution.
- Custom exception types for security failures.
- `MessageDigest.isEqual()` for digest comparisons.

The implementation separates service responsibilities so that the permission service does not need to understand dependency scanning and the dependency service does not need to perform deployment authorization.

This reduces coupling between security mechanisms.

### 8.5 PostgreSQL implementation

The PostgreSQL script creates a relational model for pipeline security.

Its schema stores operational records and security evidence.

| Table | Purpose |
|---|---|
| `repositories` | Repository information |
| `principals` | Human and automated identities |
| `repository_memberships` | Repository-level access |
| `branches` | Source and target branches |
| `commits` | Source history |
| `pipeline_jobs` | Job definitions |
| `permission_definitions` | Available permissions |
| `job_permissions` | Assigned permissions |
| `secrets` | Encrypted secret records |
| `secret_access_grants` | Secret authorization |
| `secret_access_events` | Secret access decisions |
| `pull_requests` | Proposed changes |
| `pull_request_commits` | Commits associated with proposed changes |
| `reviews` | Review decisions |
| `review_comments` | Review discussions |
| `pipeline_runs` | Execution history |
| `dependencies` | Dependency inventory |
| `pipeline_run_dependencies` | Dependencies used in a run |
| `vulnerability_findings` | Security findings |
| `artifacts` | Build outputs and provenance |
| `status_checks` | Automated validation results |
| `branch_protection_policies` | Protected branch rules |
| `required_status_checks` | Mandatory checks |
| `security_audit_events` | Security event history |

The database uses foreign keys to maintain relationships between repositories, jobs, identities, pipeline runs, reviews, and artifacts.

Check constraints prevent invalid values.

Unique constraints prevent duplicate identities and assignments.

Indexes support frequent retrieval operations.

Functions implement dependency evaluation, secret authorization, approval counting, conversation resolution, and merge eligibility.

Triggers enforce pipeline state transitions and audit permission changes.

## 9. Database Relationships

The relational structure follows this model:

Repository  
→ Branches  
→ Commits  
→ Pull Requests  
→ Reviews  
→ Review Comments

Repository  
→ Pipeline Jobs  
→ Job Permissions  
→ Secret Access Grants

Pipeline Jobs  
→ Pipeline Runs  
→ Dependencies  
→ Vulnerability Findings

Pipeline Runs  
→ Artifacts  
→ Provenance Evidence

Branches  
→ Branch Protection Policies  
→ Required Status Checks

Pull Requests  
→ Reviews  
→ Status Checks  
→ Merge Eligibility

Security Events  
→ Audit Records

The use of separate tables prevents different security concepts from being stored as one undifferentiated record.

For example, a dependency and a vulnerability finding are separate entities because one dependency may have several vulnerabilities.

Likewise, a pipeline job and a permission assignment are separate entities because a job can have multiple permissions.

## 10. Security Testing and Failure Scenarios

The source files include practical failure scenarios.

| Test scenario | Expected outcome |
|---|---|
| Unauthorized secret retrieval | Denied |
| Expired secret retrieval | Denied |
| Revoked secret retrieval | Denied |
| Deployment without permission | Blocked |
| Excessive permissions | Rejected |
| Untrusted pull request with secret access | Blocked |
| Dependency digest mismatch | Unverified |
| Dependency from blocked source | Blocked |
| Critical dependency vulnerability | Vulnerable |
| Modified artifact attestation | Rejected |
| Mutable third-party action reference | Rejected |
| Untrusted shell interpolation | Rejected |
| Duplicate dependency | Rejected |
| Duplicate pipeline execution | Rejected |
| Invalid pipeline state transition | Rejected |

### 10.1 Fail-closed security

Fail-closed behavior means that a security decision defaults to rejection when required evidence is missing or invalid.

Examples include:

- Missing dependency digest.
- Missing artifact attestation.
- Missing deployment permission.
- Expired credentials.
- Unapproved package source.

A pipeline should not interpret unavailable security information as successful validation.

### 10.2 Auditability

Security audit records provide evidence of security-related activities.

Useful audit information includes:

- Event type.
- Actor.
- Resource.
- Decision.
- Timestamp.
- Failure reason.
- Associated execution identifier.

Audit records should not contain plaintext passwords, tokens, private keys, or other credentials.

Production audit storage should also provide access restrictions, retention controls, integrity protection, and appropriate separation of duties.

## 11. Performance and Scalability

Pipeline security checks should be designed to provide strong protection without creating unnecessary execution overhead.

| Operation | Typical complexity | Main consideration |
|---|---|---|
| Permission membership | Average O(1) | Set-based authorization |
| Secret lookup | Average O(1) | Indexed or key-based retrieval |
| Dependency scanning | O(n) | Number of dependencies |
| Duplicate detection | Average O(n) | Set-based comparison |
| Reviewer aggregation | O(r) | Number of reviews |
| Status check evaluation | O(c) with indexed lookup | Number of required checks |
| Audit insertion | Approximately O(1) before index maintenance | Write volume |
| Database reporting | Depends on joins and indexes | Data volume and query plans |

Here, \(n\) represents dependencies, \(r\) represents reviews, and \(c\) represents status checks.

For large environments:

- Cache non-sensitive policy metadata.
- Avoid repeatedly downloading unchanged dependencies.
- Use dependency and artifact digest caches.
- Index frequently queried foreign keys.
- Separate audit storage from operational workloads when necessary.
- Avoid unnecessary repeated vulnerability scans.
- Use asynchronous processing for independent checks.
- Limit concurrent access to privileged deployment resources.

Caching security decisions requires careful invalidation when permissions, policies, dependencies, or artifact evidence change.

## 12. Security Limitations and Production Considerations

The implementations demonstrate security mechanisms rather than replacing a complete production security platform.

Several boundaries require attention.

### 12.1 Secret management

The examples use in-memory secret storage in Python, JavaScript, and Java.

The PostgreSQL implementation stores demonstration ciphertext.

A production environment requires:

- A dedicated secret-management service.
- Managed encryption keys.
- Access policies.
- Credential rotation.
- Short-lived credentials where possible.
- Revocation mechanisms.
- Secret access monitoring.

### 12.2 Cryptographic signing

The implementations use HMAC-SHA256 to demonstrate artifact attestation integrity.

HMAC uses a shared secret key.

Production artifact verification should use an independently verifiable signing identity and a trusted key-management process.

The verification system must validate the signer, artifact digest, build identity, source revision, and provenance claims.

### 12.3 Dependency verification

A matching digest does not prove that software is secure.

The expected digest must originate from a trusted source.

Vulnerability databases and package metadata must also be maintained and updated.

### 12.4 Pipeline isolation

Application-level permission checks do not provide complete execution isolation.

Production pipeline environments should also restrict:

- Network connectivity.
- Filesystem access.
- Container privileges.
- Host access.
- Runtime identities.
- Build environment reuse.
- Access to deployment infrastructure.

### 12.5 Database authorization

The PostgreSQL schema provides data integrity and policy evaluation mechanisms.

Production deployment must separately establish database roles, row-level access restrictions where appropriate, controlled function execution, encryption, key management, and restricted administrative privileges.

The application must authenticate pipeline identities independently. Database identifiers supplied by an untrusted client must not be treated as proof of identity.

### 12.6 Atomic deployment decisions

A merge or deployment decision can become outdated if the branch changes after validation.

A production implementation should revalidate the source and target branch revisions immediately before the protected operation.

Where possible, policy evaluation and the corresponding state change should be performed atomically.

## 13. Technical Distinctions

The three major security areas address different failure conditions.

| Situation | Security mechanism |
|---|---|
| A password appears in source code | Secrets security |
| A testing job can deploy to production | Permission security |
| A package download differs from the approved digest | Supply-chain integrity |
| A dependency contains a critical vulnerability | Vulnerability management |
| A third-party pipeline action uses a mutable tag | Pipeline configuration security |
| An artifact has no verifiable build origin | Artifact provenance |
| An external contribution can access deployment credentials | Secret isolation and trust boundaries |
| A pipeline performs an unauthorized deployment | Authorization enforcement |

The mechanisms must operate together.

A secure secret vault cannot compensate for excessive job permissions.

Least privilege cannot establish whether a downloaded dependency is authentic.

A verified dependency cannot establish whether an artifact was produced by a trusted builder.

Pipeline security therefore requires multiple independent controls and evidence sources.

## 14. Practical Pipeline Security Evaluation

A pipeline security assessment can be organized into the following operational sequence:

| Stage | Evaluation question | Expected evidence |
|---|---|---|
| Identity | Is the execution identity authenticated? | Verified identity |
| Permissions | Does the job have only required permissions? | Permission assignment |
| Secrets | Are credentials restricted to authorized jobs? | Secret access grants |
| Dependencies | Are dependency identities and digests verified? | Dependency inventory and digests |
| Vulnerabilities | Are prohibited findings addressed? | Vulnerability assessment |
| Configuration | Are third-party actions pinned? | Immutable references |
| Build | Is the build process controlled? | Builder identity and build records |
| Artifact | Is the artifact integrity verified? | Cryptographic digest |
| Provenance | Is the artifact origin verifiable? | Signed provenance evidence |
| Deployment | Is the deployment explicitly authorized? | Deployment permission and audit record |

The six deliverables implement these mechanisms through executable security models, policy evaluation, domain validation, database constraints, and audit reporting.

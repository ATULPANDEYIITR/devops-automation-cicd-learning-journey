# Actions Secrets: Secrets, Credentials, and Secure Configuration

## Scope

This repository models secure configuration for GitHub Actions-style automation, with particular attention to secrets, credentials, environment-specific configuration, access control, rotation, expiration, auditability, and prevention of credential disclosure.

The central design distinction is between **configuration metadata** and **credential material**.

Configuration metadata can describe a secret such as `DATABASE_PASSWORD`, its scope, its expiration policy, or a reference to an external secret provider. The actual password should not be treated as ordinary repository configuration and should not be committed to source control, copied into workflow files, or written to logs.

The six deliverables use different technical perspectives:

| Deliverable | Primary perspective |
| --- | --- |
| Python | In-memory secret-management service, masking, validation, resolution, rotation, auditing, and CI simulation |
| JavaScript | Event-driven Actions job model with scoped resolution, runtime secret handling, masking, and lifecycle events |
| C++ | Repository governance and deployment-policy engine with explicit authorization and credential lifecycle states |
| Java | Enterprise domain model with typed scopes, principals, environments, policies, services, exceptions, and audit events |
| SQL | PostgreSQL relational model for repositories, environments, secrets, secret versions, workflow requirements, and access events |
| README | Conceptual and architectural explanation connecting the implementations |

The implementations are simulations rather than integrations with GitHub or an external secret provider. This keeps the examples executable without requiring credentials or network access while preserving the security properties that matter in a production design.

## Secrets and Credentials

A secret is sensitive information whose disclosure can provide unauthorized access or otherwise compromise a system. Typical CI/CD secrets include deployment credentials, package-registry tokens, database passwords, cloud credentials, signing keys, webhook credentials, and API tokens.

A credential is the material used to authenticate or authorize an action. The distinction matters because secure configuration should identify **which credential is required** without exposing **what the credential contains**.

For example, a workflow may need:

`DATABASE_PASSWORD`

The workflow configuration should identify that dependency while the credential itself is injected through a protected secret mechanism.

The Python implementation represents this separation with `SecretRecord.metadata()`. Metadata contains the name, scope, repository, environment, lifecycle dates, and active state, but not the value.

The C++ implementation takes the same principle further by replacing the credential with `[REDACTED]` when metadata is requested.

The Java implementation exposes `SecretMetadata` while keeping the actual value inside `SecretRecord`.

The SQL schema intentionally has no plaintext `secret_value` column. Instead, it stores `provider_reference` and `current_fingerprint`, allowing database records to identify external credential material without becoming the credential store themselves.

## Secure Configuration

Secure configuration has two different dimensions.

Ordinary configuration controls application behavior. Examples include an API base URL, log level, deployment region, or TLS mode.

Sensitive configuration contains credential material or references to credential material.

A useful boundary is:

`ordinary configuration -> application behavior`

`secret reference -> secure credential retrieval`

`credential value -> protected runtime memory`

The Python `SecureConfiguration` class demonstrates this separation. Its ordinary settings contain values such as `LOG_LEVEL` and `DATABASE_SSL_MODE`, while credential-bearing configuration is represented through secret names.

Embedding a value such as `DATABASE_PASSWORD=actual-password` directly into a source file defeats this separation because the credential becomes part of source history, code review, backups, forks, and potentially build artifacts.

## Secret Scope

Scope determines where a secret can be used.

The implementations distinguish three scopes:

- **Organization scope** provides a reusable credential boundary for repositories that are authorized to use it.
- **Repository scope** associates a credential with one repository.
- **Environment scope** associates a credential with both a repository and an environment such as staging or production.

Scope is not merely a naming convention. It is an authorization boundary.

A production database password should not automatically become available to a staging job merely because both jobs use the same secret name.

The examples therefore use the same name, `DATABASE_PASSWORD`, at different scopes. The resulting credentials are different.

## Environment-Specific Secrets

Environment-specific secrets are useful when the same application has separate infrastructure boundaries.

A typical configuration relationship is:

`repository -> development`

`repository -> staging`

`repository -> production`

Production can then use a different database credential, deployment token, cloud identity, or service credential.

The Python resolver explicitly applies this precedence:

`environment -> repository -> organization`

The JavaScript `SecretManager.resolve()` method implements the same hierarchy.

The C++ `SecretStore::resolve()` method makes the precedence explicit with an ordered collection of `SecretKey` candidates.

The SQL view `deployment_secret_readiness` uses a window function to select the highest-precedence matching secret.

This is important because precedence should be an explicit policy rather than an accidental consequence of implementation order.

## Credential Injection

A CI job should receive a secret as late as practical and only when the job needs it.

The JavaScript `ActionsJob` represents this with a `runtimeSecrets` map. The deployment job loads `DEPLOY_TOKEN` when execution begins instead of keeping every possible credential in a long-lived global configuration object.

After the simulated deployment, the runtime map is cleared.

Clearing a data structure does not provide complete memory security. Operating-system memory, process dumps, debugging facilities, garbage collection, logs, and third-party libraries can still affect exposure. The example demonstrates lifecycle discipline rather than claiming that memory clearing makes a process inherently secure.

## Secret Masking

Secret masking is a defensive control that attempts to prevent known sensitive values from appearing in CI logs.

The Python `SecretMasker` and JavaScript `SecretMasker` replace known values with `***`.

For example, simulated output containing a deployment credential becomes a masked log entry instead of displaying the credential.

Masking is not a substitute for preventing disclosure.

A secret can potentially be transformed before logging, split across output fragments, encoded, inserted into an artifact, included in an exception, or exposed through a command argument. A secure workflow should therefore avoid printing secrets rather than relying on masking to repair unsafe output.

## Access Control

Access should be evaluated against both the principal and the target resource.

The Python model distinguishes administrators, developers, and CI runners. A production runner has access to the production environment but not necessarily to development or staging credentials.

The Java model represents authorization with the `Principal` record and explicit roles:

- `DEVELOPER`
- `MAINTAINER`
- `SECURITY_ADMIN`
- `CI_RUNNER`

The C++ implementation similarly separates management permission from read permission. A user who can contribute code is not automatically treated as a security administrator.

The SQL model stores repository membership and role information in `repository_members`, providing a relational representation of the same governance boundary.

## Credential Rotation

Credential rotation replaces an existing credential with a new credential while preserving lifecycle information.

A useful rotation sequence is:

`new credential generated`

`external secret provider updated`

`application or workflow begins using new credential`

`old credential revoked`

`metadata and audit records updated`

The Python implementation changes the value while preserving the original creation time and recording `rotated_at`.

The Java implementation uses `SecretRecord.rotate()` to replace the runtime value and establish a new expiration timestamp.

The C++ model updates the active record and records a rotation event.

The SQL implementation represents rotation without storing the new credential itself. It updates the provider reference and fingerprint and inserts a new row into `secret_versions`.

Rotation must also address the old credential. Replacing a reference without revoking an old credential at its provider can leave two valid credentials active.

## Expiration

Expiration limits how long a credential remains usable.

The Python resolver rejects records whose `expires_at` has passed.

The JavaScript `SecretRecord.isUsable()` checks both state and expiration.

The C++ `isUsable()` function prevents resolution after expiration.

The Java domain model checks `Instant.now().isBefore(expiresAt)`.

The SQL readiness view evaluates whether an active secret has an expiration date that has not passed.

Expiration is particularly valuable for temporary credentials and deployment credentials because a leaked credential becomes less useful as time passes.

Expiration alone is not enough. A credential that never expires may remain dangerous indefinitely if leaked, while an expired credential may still need explicit revocation at its provider.

## Disabled Credentials

Expiration is time-driven. Disabling is an explicit administrative state transition.

The Python, C++, and Java implementations provide a disable operation.

A disabled secret remains represented as metadata but cannot be resolved.

This distinction is useful for incident response. Security personnel may need to invalidate a credential immediately rather than waiting for its scheduled expiration.

## External Secret Providers

The SQL implementation deliberately stores references such as:

`vault://ci/acme-payments/production/deploy-token`

The reference represents an external secret-management location rather than the secret itself.

A production architecture can use this pattern to separate:

`repository governance`

from

`secret storage`

from

`runtime credential retrieval`

This reduces the number of systems that need direct access to plaintext credentials.

The database can then answer questions such as:

- Which workflow requires a credential?
- Which environment owns it?
- When does it expire?
- Which version is current?
- Which provider reference should the deployment service request?
- Has the credential been disabled?

The database does not need to answer:

- What is the plaintext password?

That value belongs in the protected secret-management layer.

## Python Implementation

The Python program provides the most complete in-memory secret lifecycle simulation.

`SecretManager` owns secret records and implements:

- secret-name validation
- value validation
- organization, repository, and environment scopes
- management authorization
- runtime read authorization
- environment-aware resolution
- expiration handling
- disabling
- rotation
- metadata inspection
- access auditing

The `SecretRecord.metadata()` method is deliberately designed so that metadata output never contains the secret value.

`resolve()` implements explicit scope precedence. If a production environment has an environment-specific credential, it wins over the repository-level value. If no usable environment credential exists, the repository value is considered, followed by the organization-level value.

`SecretMasker` demonstrates defense-in-depth logging protection.

`evaluate_ci_configuration()` demonstrates a useful CI preflight pattern: verify that required credentials are available without printing them.

`simulate_github_actions_job()` demonstrates runtime credential retrieval and masking of simulated runner output.

The expiration example deliberately moves a test credential into the past so the failure behavior is deterministic.

The audit trail records actor, operation, scope, repository, environment, and result, but never records plaintext credentials.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven behavior.

`SecretManager` extends Node.js `EventEmitter`. Secret creation, rotation, reads, and denied access generate events that are converted into audit records.

This reflects the event-oriented nature of CI systems, where configuration changes and workflow execution can generate security-relevant events.

`ActionsJob` models a deployment process that obtains `DEPLOY_TOKEN` at runtime. It maintains a job-local `runtimeSecrets` map instead of making credentials part of application-wide configuration.

JavaScript's `Map` is used for runtime secret storage because the example needs explicit lifecycle management and lookup by secret name.

The `SecretMasker` uses the known runtime values to transform simulated runner output before it is displayed.

The implementation also uses Node's `crypto` module to generate high-entropy demonstration credentials and to calculate fingerprints.

`crypto.timingSafeEqual()` is used by `safeEqual()` when comparing equal-length sensitive byte sequences. The length check occurs before the constant-time comparison because Node's API requires buffers of equal length.

The event-driven architecture makes audit behavior a first-class part of the secret lifecycle rather than an unrelated logging statement.

## C++ Case Study

The C++ program models a repository security control plane.

Its principal domain types are:

- `Actor`
- `SecretKey`
- `Secret`
- `AuditEvent`
- `SecretStore`
- `DeploymentPolicy`

`SecretKey` makes scope part of the identity of a credential. An environment-level `DEPLOY_TOKEN` is therefore different from a repository-level credential with the same name.

`SecretStore::resolve()` uses ordered candidates to represent environment, repository, and organization precedence.

The deployment policy asks whether required credentials can be resolved. It reports availability and credential length but never prints credential contents.

The case study also demonstrates emergency disablement. A production deployment token is first resolved successfully, then disabled, after which resolution fails.

The C++ implementation treats authorization and lifecycle as separate concerns. Management determines whether an actor may change a secret, while read authorization determines whether a runtime principal may receive it.

## Java Implementation

The Java implementation uses explicit enterprise domain types.

`SecretIdentity` combines name, scope, repository, and environment.

`SecretMetadata` is immutable and contains lifecycle information without the credential value.

`Principal` models a repository security identity with a role, repository membership, and environment permissions.

`DeploymentPolicy` expresses required credentials as a domain policy rather than embedding policy decisions in output statements.

`SecretService` owns secret lifecycle operations and authorization.

`DeploymentEligibilityService` evaluates whether a deployment can obtain its required credentials. It records whether each required credential is available without exposing the credential itself.

Java's records are useful here because identities, metadata, policies, and audit events are value-oriented objects. Mutable credential lifecycle state remains inside `SecretRecord`.

The exception types distinguish policy violations from authorization failures.

## SQL Data Model

The PostgreSQL schema models the same security domain relationally.

### Repositories and environments

`repositories` identifies the application repository.

`environments` associates deployment environments with repositories. The `production` flag allows governance rules to distinguish production from lower-risk environments.

`branch_environments` associates environments with deployment branch patterns and records whether the environment requires approval.

### Secret definitions

`secrets` represents secret metadata.

Its most important security property is what it does **not** contain: there is no plaintext credential column.

The table stores:

- secret name
- scope
- repository
- environment
- provider reference
- fingerprint
- lifecycle state
- creation and update timestamps
- expiration timestamp

The `scope_relationship_is_valid` constraint prevents an organization secret from accidentally being assigned to a repository and prevents a repository secret from carrying an environment identifier.

The unique partial indexes enforce one active identity for each relevant scope/name combination.

### Secret versions

`secret_versions` models credential rotation history.

A version contains a fingerprint and lifecycle information rather than plaintext credential material.

This supports questions such as whether a new credential version was created without requiring the database to know the credential itself.

### Workflow runs

`workflow_runs` represents CI executions.

`workflow_secret_requirements` associates a workflow with the secrets it requires.

This creates a useful relationship:

`workflow run -> required secret -> scope -> environment -> provider reference`

The relationship allows a deployment preflight query to identify missing or unusable credentials.

### Access auditing

`secret_access_events` records access and administrative operations.

The event contains:

- timestamp
- repository
- environment
- secret identity
- principal
- action
- result
- reason

The schema does not provide a field for plaintext secret values.

## Database-Level Integrity

The SQL schema uses constraints rather than relying exclusively on application validation.

The `secret_name_format` constraint restricts names to an explicit format.

The `secret_name_not_generic` constraint prevents ambiguous names such as `PASSWORD` and `TOKEN`.

The scope constraint ensures that the relational shape matches the declared scope.

The environment trigger checks that an environment actually belongs to the repository referenced by an environment-scoped secret.

The unique partial indexes prevent multiple definitions of the same scoped secret identity.

Indexes on repository/name and environment/name support the lookup patterns used by runtime configuration resolution.

## Effective Secret Resolution in SQL

The `deployment_secret_readiness` view demonstrates scope precedence with a window function.

Potential candidates are collected from:

`environment`

`repository`

`organization`

A `ROW_NUMBER()` expression orders those candidates according to the intended precedence.

Only the highest-priority candidate is exposed by the view.

The resulting query can determine whether a required credential is usable without retrieving its secret material.

This is an important separation between **credential selection** and **credential retrieval**.

The database can determine which external secret reference should be used. A deployment service can then request the credential from the external secret provider.

## Transactions and Rotation

The SQL rotation example runs inside a transaction.

The transaction changes the provider reference, fingerprint, expiration, and state, creates a new secret version, and records an audit event.

The actual plaintext replacement is intentionally outside the SQL transaction because the schema is designed around an external provider.

In a real deployment, coordination between the external provider and database metadata needs an explicit failure strategy. A successful database transaction cannot by itself guarantee that an external credential provider changed successfully.

A production implementation may use versioned credentials, staged rollout, dual-credential overlap, provider-side revocation, and reconciliation jobs to manage this distributed state.

## Secure Configuration Failure Modes

A secure design should consider how credentials can leak even when source files contain no obvious passwords.

Important exposure channels include:

- CI log output
- command-line arguments
- shell tracing
- exception messages
- build artifacts
- generated configuration files
- temporary files
- caches
- container image layers
- test fixtures
- copied environment variables
- debug output
- crash dumps
- source-control history

The implementations specifically avoid printing secret values, but real deployments must also control the surrounding execution environment.

A particularly common mistake is to assume that moving a credential from source code into an environment variable automatically makes it safe. Environment variables reduce some source-control exposure but can still be exposed through process inspection, debugging, logs, child processes, or accidental serialization.

## Production Design Considerations

A production-grade implementation should keep the responsibilities separate:

`repository policy`

controls who may configure and use a credential.

`CI workflow`

declares when a credential is required.

`secret provider`

stores the sensitive credential material.

`deployment service`

requests only the credentials required for a specific operation.

`audit system`

records security-relevant events without recording plaintext secrets.

This separation reduces the blast radius of a compromise.

The strongest design is not merely "put the password into Actions Secrets." It is to define a controlled credential lifecycle from provisioning through runtime use, rotation, revocation, expiration, and auditing.

## Security and Operational Trade-offs

Long-lived static credentials are operationally simple but increase exposure duration after a leak.

Short-lived credentials reduce the useful lifetime of a compromised value but require stronger identity and token-management infrastructure.

Repository-wide credentials are convenient but can be broader than necessary.

Environment-specific credentials require more configuration but create stronger separation between staging and production.

Centralized organization credentials reduce duplication but require careful repository eligibility controls.

External secret providers add infrastructure and operational complexity but allow credential material to remain outside application repositories and relational databases.

Masking reduces accidental log exposure but cannot guarantee that every representation of a credential is detected.

Audit logging improves visibility but itself becomes security-sensitive and must not contain credential material.

## Common Mistakes

### Committing credentials to source control

Removing a password from the latest commit does not necessarily remove it from repository history, forks, caches, or previously generated artifacts.

Credential rotation is required when a real secret has been exposed.

### Treating secret names as secret values

A name such as `DATABASE_PASSWORD` is normally configuration metadata. The actual password is the sensitive value.

Names should still avoid unnecessary disclosure of internal infrastructure details, but they do not provide authentication by themselves.

### Sharing production credentials with development

Using one database password across environments increases the impact of a development compromise.

Separate credentials allow development access to be revoked without necessarily affecting production.

### Logging command lines containing credentials

A command can leak a credential even when the workflow's normal secret configuration is correct.

Credentials should not be inserted into command strings when a safer authentication mechanism exists.

### Assuming masking solves disclosure

Masking is a last line of defense. The primary control should be to avoid sending secret values to output channels.

### Never rotating credentials

A credential that remains valid for years creates a large exposure window.

Rotation policy should account for credential sensitivity, provider capabilities, incident response requirements, and operational constraints.

### Giving CI excessive access

A workflow that can access every environment's secrets creates a larger blast radius than a workflow restricted to the environment it deploys.

## Practical Security Model

The complete model represented by these implementations can be expressed as:

`Secret definition`

→ identifies purpose and scope

`Authorization`

→ determines whether the actor can manage or consume it

`Environment policy`

→ determines where the credential may be used

`Secret provider`

→ stores the sensitive material

`Workflow runtime`

→ receives the credential only when required

`Masking and output controls`

→ reduce accidental disclosure

`Expiration and rotation`

→ limit credential lifetime

`Audit events`

→ provide evidence of access and lifecycle operations

The key architectural principle is that secure configuration is a lifecycle and governance problem, not merely a storage problem.

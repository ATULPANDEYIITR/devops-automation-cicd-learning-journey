# Infrastructure as Code: Declarative Infrastructure Management

## 1. Introduction

Infrastructure as Code (IaC) is an approach to managing infrastructure through machine-readable configuration files rather than relying exclusively on manual configuration through cloud consoles or command-line operations.

An IaC definition describes the infrastructure that should exist. An execution engine compares that definition with the existing infrastructure and determines which operations are required to achieve the declared configuration.

Infrastructure can include:

- Virtual networks and subnets
- Compute instances and servers
- Storage systems
- Firewalls and security groups
- Managed databases
- Load balancers
- DNS and routing configurations
- Cloud infrastructure services

The central principle is that infrastructure is described as a desired state and managed through repeatable operations.

## 2. Fundamental IaC Concepts

### 2.1 Declarative Infrastructure

Declarative IaC specifies the required outcome rather than listing every operational command needed to produce it.

For example, a declaration might specify:

| Property | Desired value |
|---|---|
| Resource | Application server |
| CPU | 4 |
| Memory | 16 GB |
| Operating system | Ubuntu 24.04 |
| Network | Production network |
| Public SSH | Disabled |

The infrastructure engine determines whether the server must be created, modified, replaced, or left unchanged.

Declarative configuration separates infrastructure requirements from the implementation steps used to achieve them.

### 2.2 Imperative Infrastructure

Imperative infrastructure management specifies the operations to perform.

A typical sequence is:

1. Create a network.
2. Create a subnet.
3. Create a server.
4. Configure network access.
5. Attach storage.
6. Configure security rules.

The operator is responsible for defining the execution sequence and handling the resulting state.

### 2.3 Declarative versus Imperative IaC

| Characteristic | Declarative | Imperative |
|---|---|---|
| Main focus | Desired outcome | Required operations |
| Configuration | Resource specifications | Commands and procedures |
| Execution order | Derived from dependencies | Explicitly defined |
| State comparison | Central mechanism | Depends on implementation |
| Reconciliation | Commonly supported | Must be implemented |
| Idempotency | Designed into the workflow | Depends on command design |
| Drift management | Can be systematically detected | Requires additional mechanisms |

Declarative and imperative approaches are not mutually exclusive. A declarative infrastructure engine may internally execute imperative operations through cloud provider APIs.

## 3. Desired State and Actual State

The distinction between desired and actual infrastructure state is fundamental to IaC.

**Desired state** describes what the infrastructure configuration requires.

**Actual state** describes what currently exists in the infrastructure environment.

Consider an application server:

| Property | Desired state | Actual state |
|---|---:|---:|
| CPU | 4 | 8 |
| Memory | 16 GB | 16 GB |
| Operating system | Ubuntu 24.04 | Ubuntu 24.04 |
| Network | production-network | production-network |

The CPU configuration differs. This is configuration drift.

An IaC engine identifies the difference and determines whether an update or replacement is necessary.

The desired configuration should remain the authoritative declaration. Actual state must be observed from the infrastructure provider or a trustworthy state record.

## 4. Infrastructure Lifecycle

A typical declarative infrastructure lifecycle follows this sequence:

**Infrastructure definition**

The engineer declares resources, properties, dependencies, and security requirements.

**Validation**

The configuration is checked for invalid values, unsupported resource types, missing dependencies, and policy violations.

**Planning**

The engine compares desired state with actual state.

**Review**

The proposed operations are examined before execution, particularly when production infrastructure is involved.

**Application**

The engine provisions, updates, replaces, or deletes resources.

**Verification**

The resulting infrastructure is checked against the declared configuration.

**Monitoring and reconciliation**

The system periodically checks for drift and restores compliance when permitted.

### Lifecycle diagram

    Infrastructure Definition
              |
              v
       Configuration Validation
              |
              v
         Dependency Analysis
              |
              v
          State Comparison
              |
              v
         Execution Plan
              |
              v
        Policy Evaluation
              |
              v
       Approval (if required)
              |
              v
       Infrastructure Apply
              |
              v
        State Verification
              |
              v
         Drift Monitoring
              |
              +------> Reconciliation

## 5. Resources and Resource Modeling

A resource represents an independently managed infrastructure component.

The implementations use a common resource model.

| Field | Purpose |
|---|---|
| Resource ID | Unique logical identifier |
| Resource type | Network, server, storage, or firewall |
| Properties | Configuration values |
| Dependencies | Resources required by this resource |
| Protected | Indicates whether deletion is restricted |
| Status | Current lifecycle state |

Example resource types:

| Resource type | Important properties |
|---|---|
| Network | CIDR, region |
| Server | CPU, memory, operating system |
| Storage | Capacity, encryption, versioning |
| Firewall | Default action, allowed traffic |
| Database | Engine, storage, backup configuration |
| Load balancer | Listener, target groups, health checks |

A logical resource identifier should remain stable across ordinary configuration updates.

Changing a logical identifier can cause an infrastructure engine to interpret an existing resource as a new resource and potentially create unnecessary infrastructure.

## 6. Resource Dependencies

Infrastructure resources frequently depend on other resources.

For example:

- An application server requires a network.
- A database requires network connectivity.
- A load balancer requires target servers.
- A firewall may require an existing network.

Dependencies determine the correct execution sequence.

Consider:

    Production Network
           |
           +----------------+
           |                |
           v                v
    Application Server   Firewall
           |
           v
    Application Service

### 6.1 Dependency Graphs

The implementations represent dependencies as directed graphs.

An edge from resource A to resource B indicates that A depends on B.

For deployment, B must be provisioned before A.

### 6.2 Topological Sorting

Topological sorting determines a valid ordering of resources in a directed acyclic graph.

The implementations use Kahn's algorithm.

The algorithm:

1. Calculate the number of dependencies for each resource.
2. Identify resources with no dependencies.
3. Add those resources to the deployment queue.
4. Process each resource.
5. Reduce the dependency count of its dependents.
6. Add newly eligible resources to the queue.
7. Check whether every resource was processed.

If resources remain unprocessed, a dependency cycle exists.

For example:

    Network -> Server
    Server  -> Database
    Database -> Network

This configuration is invalid because no valid deployment order exists.

**Complexity:** Topological sorting requires O(V + E) time, where V represents resources and E represents dependency relationships.

## 7. Infrastructure Planning

Planning determines which operations are required to reconcile desired and actual infrastructure.

The six principal planning outcomes are:

| Action | Meaning |
|---|---|
| Create | Resource does not exist |
| Update | Existing mutable properties differ |
| Replace | An immutable property changes |
| Delete | Resource is no longer declared |
| No-op | Actual configuration already matches |
| Failed | Planning or validation cannot proceed |

The Python, C++, and Java implementations demonstrate create, update, delete, and no-op planning. The JavaScript implementation models create, update, delete, and no-op operations.

Replacement is an explicit planning action in the Python implementation.

### Example

Desired configuration:

- Server CPU: 4
- Memory: 16 GB

Actual configuration:

- Server CPU: 8
- Memory: 16 GB

The plan contains an update because the existing server differs from the desired specification.

If a provider treats a particular property as immutable, changing it may require replacing the resource rather than updating it.

Replacement requires additional care because it may cause downtime, data loss, or temporary resource duplication.

## 8. Idempotency

Idempotency means that applying the same desired configuration repeatedly should not produce unnecessary changes after the infrastructure has reached the required state.

For example:

| Deployment | Result |
|---|---|
| First application | Creates four resources |
| Second application | Four no-op operations |
| Third application | Four no-op operations |

Idempotency is important because infrastructure automation may run repeatedly through scheduled reconciliation, deployment pipelines, or manual execution.

A system that creates duplicate resources during repeated execution is not behaving as a reliable declarative infrastructure manager.

The implementations demonstrate idempotency through repeated planning and state comparison.

## 9. Infrastructure Drift

Infrastructure drift occurs when actual infrastructure differs from its declared configuration.

Common causes include:

- Manual cloud-console modifications
- Changes made through another automation system
- Emergency operational changes
- Unauthorized configuration modifications
- Provider-side changes
- Incomplete deployment operations

### 9.1 Drift Detection

The engine compares the desired properties with the observed properties.

Example:

| Property | Desired | Observed | Result |
|---|---|---|---|
| CPU | 4 | 8 | Drift |
| Memory | 16 GB | 16 GB | Compliant |
| Encryption | Enabled | Enabled | Compliant |
| Public SSH | Disabled | Enabled | Drift |

### 9.2 Drift Reconciliation

Reconciliation attempts to restore the declared configuration.

The appropriate response depends on the resource and operational policy.

Possible responses include:

- Automatic correction
- Manual review
- Resource replacement
- Deployment rejection
- Security incident investigation

Not every difference should automatically be overwritten. An emergency modification may require investigation before reconciliation.

The Python, JavaScript, C++, and Java programs demonstrate drift detection and configuration restoration.

The PostgreSQL implementation provides an `infrastructure_drift` view for comparing declared and recorded actual properties.

## 10. Infrastructure State Management

State management records the relationship between declared infrastructure and provisioned resources.

A state record commonly contains:

- Logical resource identifier
- Provider resource identifier
- Resource properties
- Resource status
- Configuration fingerprint
- State revision or version
- Last observed timestamp
- Last deployment timestamp
- Error information

### 10.1 Why State Matters

Without reliable state management, an infrastructure engine may not know:

- Which resources it previously created
- Which provider objects belong to the configuration
- Whether a resource has changed
- Whether a deletion is safe
- Whether another deployment has modified the environment

### 10.2 State Storage

The Python implementation supports JSON state persistence.

The PostgreSQL implementation separates `infrastructure_resources` from `infrastructure_state`.

This separation represents an important distinction:

| Table | Responsibility |
|---|---|
| infrastructure_resources | Desired configuration |
| infrastructure_state | Observed actual configuration |

### 10.3 State Locking

Concurrent deployments can interfere with each other.

For example:

1. Deployment A reads revision 10.
2. Deployment B reads revision 10.
3. Deployment A applies changes.
4. Deployment B applies its outdated plan.

This can produce inconsistent infrastructure.

Production systems should use appropriate locking, revision checks, and concurrency controls.

The PostgreSQL procedure locks the deployment plan and environment during processing. The JavaScript controller prevents overlapping deployments within its process.

A distributed deployment system requires distributed locking or equivalent coordination across multiple workers.

### 10.4 Sensitive State Information

Infrastructure state can contain sensitive information such as:

- Resource identifiers
- Internal network addresses
- Database connection details
- Configuration metadata
- Secret references

Production state storage should use encryption, access restrictions, audit logging, secure backup procedures, and appropriate secret-management mechanisms.

Actual credentials should not be stored directly in ordinary infrastructure configuration files.

## 11. Infrastructure Security Policies

IaC allows infrastructure requirements to be checked before provisioning.

Examples include:

| Policy | Requirement |
|---|---|
| Storage encryption | Encryption must be enabled |
| Firewall configuration | Default action must be DENY |
| SSH access | Public SSH access prohibited |
| Server capacity | Minimum resource capacity |
| Network exposure | Public access must be explicitly authorized |

### 11.1 Policy Evaluation

A policy engine evaluates declared resource properties against organizational requirements.

For example:

    Resource: application-storage
    Property: encrypted
    Required: true
    Declared: false
    Decision: REJECT

Policy evaluation should occur before infrastructure application.

A critical security policy violation should prevent deployment rather than simply produce a warning.

### 11.2 Policy as Code

Policy as Code expresses organizational infrastructure requirements as executable rules.

It provides:

- Repeatable security validation
- Consistent governance
- Automated compliance checks
- Reduced dependence on manual inspection
- Auditable deployment decisions

The JavaScript implementation uses policy objects and evaluation functions.

The Java implementation uses the `InfrastructurePolicy` interface and `SecurityPolicy` implementation.

The C++ implementation uses a dedicated `SecurityPolicy` class.

The PostgreSQL implementation stores policy definitions and evaluates declared resource properties through `evaluate_resource_policies()`.

## 12. Implementation Architecture

The five source files demonstrate different engineering perspectives.

| File | Main responsibility | Important mechanisms |
|---|---|---|
| Python | Infrastructure simulation | Dataclasses, JSON state, planning, dependency ordering |
| JavaScript | Event-driven deployment | Maps, Promises, asynchronous provisioning, events |
| C++17 | Governance and reconciliation engine | STL containers, dependency graphs, policy evaluation |
| Java 17 | Enterprise infrastructure management | Records, interfaces, immutable specifications, services |
| PostgreSQL | Relational infrastructure management | Constraints, JSONB, procedures, triggers, views, transactions |

### 12.1 Python Implementation

The Python program uses a modular design.

Its main components are:

- `Resource`: Represents an infrastructure resource.
- `InfrastructureDefinition`: Maintains the desired resource configuration.
- `InfrastructureState`: Maintains recorded infrastructure state.
- `Planner`: Generates infrastructure operations.
- `InfrastructureEngine`: Applies the generated plan.
- `detect_drift()`: Identifies differences between desired and actual properties.

The state can be saved to and restored from a JSON file.

The implementation also checks dependency cycles, missing dependencies, protected resources, and invalid resource properties.

Run the program:

`python infrastructure.py`

Run its tests:

`python infrastructure.py --test`

Persist infrastructure state:

`python infrastructure.py --state infrastructure-state.json`

The provider is simulated. It does not create actual cloud infrastructure.

### 12.2 JavaScript Implementation

The JavaScript implementation focuses on asynchronous deployment and event-driven monitoring.

Its principal components are:

- `InfrastructureSpec`: Maintains resource declarations.
- `PolicyEngine`: Evaluates infrastructure policies.
- `DeploymentPlanner`: Generates the execution plan.
- `InfrastructureProvider`: Simulates asynchronous resource operations.
- `DeploymentController`: Coordinates deployment and state management.

The `EventEmitter` interface exposes deployment events.

Examples include:

- `plan`
- `resource:deployed`
- `resource:unchanged`
- `resource:deleted`
- `deployment:completed`
- `deployment:failed`

This architecture separates deployment decisions from event consumers.

The implementation uses `structuredClone()` to maintain isolated state snapshots and restore the controller's state after simulated deployment failures.

Run:

`node infrastructure.js`

The provider operations are simulated and do not interact with a cloud account.

### 12.3 C++17 Implementation

The C++ implementation emphasizes resource governance, explicit domain modeling, and efficient graph processing.

Important components:

- `Resource`: Infrastructure resource representation.
- `InfrastructureDefinition`: Desired infrastructure registry.
- `InfrastructureState`: Actual infrastructure representation.
- `SecurityPolicy`: Security validation.
- `InfrastructurePlanner`: Deployment planning.
- `DeploymentEngine`: Infrastructure reconciliation.

The implementation uses:

- `std::map` for resource registries
- `std::vector` for ordered operations
- `std::set` for dependency validation
- `std::priority_queue` for deterministic topological sorting
- STL algorithms for validation and comparison
- Exceptions for invalid infrastructure operations

The deployment engine takes a snapshot of state and restores it when an operation fails.

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic infrastructure.cpp -o infrastructure`

Run:

`./infrastructure`

The implementation simulates infrastructure state and does not call external cloud APIs.

### 12.4 Java 17 Implementation

The Java implementation models enterprise infrastructure governance using explicit domain types and service boundaries.

Important components:

- `ResourceSpec`: Immutable infrastructure declaration.
- `ActualResource`: Recorded infrastructure state.
- `InfrastructureDefinition`: Resource registry and dependency validation.
- `InfrastructurePolicy`: Policy evaluation interface.
- `SecurityPolicy`: Concrete security rules.
- `InfrastructurePlanner`: Deployment plan generation.
- `InfrastructureState`: State management.
- `DeploymentService`: Execution and rollback handling.

Java records represent immutable data structures.

The policy interface allows additional policy implementations without modifying the deployment service.

The service uses synchronized execution to prevent overlapping operations on the same service instance.

Compile:

`javac InfrastructureAsCode.java`

Run:

`java InfrastructureAsCode`

The program uses only Java 17 standard-library functionality.

### 12.5 PostgreSQL Implementation

The SQL implementation represents IaC as a relational information system.

Its principal tables are:

| Table | Responsibility |
|---|---|
| organizations | Organization information |
| users | User identities and roles |
| repositories | Infrastructure configuration repositories |
| environments | Development and production environments |
| infrastructure_resources | Desired infrastructure |
| resource_dependencies | Resource dependency relationships |
| infrastructure_state | Actual infrastructure state |
| infrastructure_policies | Security and governance rules |
| deployment_plans | Planned infrastructure changes |
| deployment_plan_items | Individual planned operations |
| deployment_approvals | Deployment decisions |
| deployment_executions | Execution history |
| infrastructure_audit | Infrastructure activity history |

PostgreSQL capabilities include:

- Primary and foreign keys
- Unique constraints
- Check constraints
- JSONB configuration storage
- GIN indexing
- Recursive CTEs
- SQL functions
- Stored procedures
- Triggers
- Views
- Transactions
- Row-level locking

The `infrastructure_drift` view identifies resources whose actual properties differ from their declared properties.

The `deployment_eligibility` view evaluates approval requirements and plan status.

The `execute_deployment_plan()` procedure performs the database-side deployment workflow and records execution information.

The SQL implementation simulates provider state changes through database records. It does not directly provision cloud resources.

## 13. Database Design Decisions

### 13.1 JSONB for Resource Properties

Infrastructure resources do not all share identical properties.

A network requires a CIDR block, while a server requires CPU and memory configuration.

JSONB allows resource-specific properties to be represented without creating a separate table for every infrastructure type.

Important integrity requirements are still enforced through constraints.

### 13.2 Relational Dependencies

Dependencies are stored in `resource_dependencies` rather than embedded only in JSON.

This provides:

- Foreign-key enforcement
- Unique dependency relationships
- Efficient dependency queries
- Recursive dependency traversal
- Dependency-cycle validation

### 13.3 Audit History

Infrastructure operations should be traceable.

The audit table records:

- The resource involved
- The user associated with the action
- The event type
- Previous values
- New values
- Event timestamps

Audit history supports incident investigation and infrastructure governance.

### 13.4 Indexing

The SQL implementation uses indexes for common access patterns.

| Index | Purpose |
|---|---|
| Environment and enabled status | Resource inventory |
| Resource type | Resource classification |
| GIN properties index | JSONB property searches |
| Dependency parent | Dependency traversal |
| Deployment status and creation time | Execution monitoring |
| Audit resource and timestamp | Historical investigation |

Indexes improve retrieval performance but add storage and write-maintenance costs.

## 14. Infrastructure Deployment Decisions

Infrastructure deployment should distinguish between the following decisions:

| Decision | Responsibility |
|---|---|
| Configuration validation | Check whether the declaration is valid |
| Dependency validation | Check whether resource relationships are valid |
| Policy evaluation | Check organizational requirements |
| Planning | Determine required infrastructure operations |
| Approval | Authorize a deployment where required |
| Execution | Apply the approved operations |
| Verification | Confirm the resulting infrastructure state |
| Reconciliation | Correct permitted differences |

These mechanisms are related but serve different purposes.

A valid configuration is not automatically approved for production.

An approved deployment is not automatically successful.

A successful provider operation does not guarantee that the resulting infrastructure satisfies every organizational policy.

Independent verification remains necessary.

## 15. Failure Handling and Edge Cases

Reliable IaC implementations must account for failures at different stages.

| Failure | Expected handling |
|---|---|
| Missing dependency | Reject the configuration |
| Circular dependency | Reject the deployment plan |
| Duplicate resource ID | Reject the declaration |
| Invalid property | Fail validation |
| Unencrypted storage | Reject through policy |
| Protected resource deletion | Block deletion |
| Existing infrastructure drift | Generate reconciliation actions |
| Concurrent deployment | Apply locking or concurrency control |
| Provider failure | Record failure and reconcile actual state |
| Expired deployment plan | Reject execution |
| Stale state revision | Require a new plan |
| Partial provider execution | Inspect provider state and perform recovery |

### 15.1 Transaction Boundaries

Database transactions can make database changes atomic.

Cloud infrastructure operations are external side effects and cannot generally be rolled back simply by issuing a database rollback.

For example:

1. A network is created successfully.
2. A server is created successfully.
3. Firewall provisioning fails.
4. The database transaction is rolled back.

The cloud network and server may still exist.

Production deployment systems therefore require explicit recovery mechanisms, such as:

- Compensating operations
- Resource cleanup
- Deployment checkpoints
- Provider-state reconciliation
- Retry policies
- Idempotency keys
- Execution logs

The in-memory implementations demonstrate state rollback, not guaranteed rollback of real external infrastructure.

## 16. Performance and Scalability

Infrastructure management performance depends on resource count, dependency complexity, provider latency, and state-storage design.

| Operation | Typical complexity |
|---|---|
| Resource lookup using a hash map | O(1) average |
| Resource lookup using an ordered map | O(log V) |
| Dependency graph construction | O(V + E) |
| Topological sorting | O(V + E), excluding queue-ordering overhead |
| Resource comparison | Depends on configuration size |
| Drift detection | O(V) resource comparisons |
| Indexed relational lookup | Depends on index and query selectivity |

For large environments, deployment systems should consider:

- Parallel execution of independent resources
- Dependency-aware scheduling
- Batching provider requests
- Incremental planning
- Remote state locking
- State versioning
- Provider API rate limits
- Retry and timeout policies
- Deployment checkpoints
- Environment-level isolation

Parallel provisioning can reduce deployment time, but only resources without unresolved dependencies should execute concurrently.

## 17. Security and Production Considerations

Production IaC systems require controls beyond configuration validation.

Important considerations include:

- Least-privilege cloud credentials
- Secure storage of state files
- Encryption of sensitive information
- Secret references instead of embedded credentials
- Restricted production deployment permissions
- Separation of deployment and approval responsibilities
- Immutable audit records
- Protected critical resources
- Explicit network-access policies
- State locking
- Deployment plan expiration
- Monitoring of unauthorized modifications
- Controlled recovery procedures

Infrastructure configuration should also be reviewed for accidental public exposure, excessive permissions, insecure defaults, and unintended deletion operations.

A deployment engine should never assume that a syntactically valid declaration is secure.

## 18. Important Terminology

| Term | Meaning |
|---|---|
| Infrastructure as Code | Managing infrastructure through machine-readable definitions |
| Declarative configuration | Describing the required infrastructure outcome |
| Imperative configuration | Describing the operations required to create infrastructure |
| Desired state | Declared infrastructure configuration |
| Actual state | Observed infrastructure configuration |
| Resource | Independently managed infrastructure component |
| Dependency graph | Directed relationships between resources |
| Topological sorting | Ordering resources according to dependencies |
| Infrastructure plan | Proposed infrastructure operations |
| Apply | Execute planned infrastructure changes |
| Idempotency | Repeated execution produces no unnecessary changes |
| Drift | Difference between desired and actual state |
| Reconciliation | Restoring actual infrastructure to desired configuration |
| State file | Persistent record of managed infrastructure |
| State locking | Prevention of conflicting concurrent operations |
| Policy as Code | Executable organizational infrastructure rules |
| Immutable property | Property that cannot be changed through an ordinary update |
| Resource replacement | Deleting or recreating a resource to apply a change |
| Provider | Service responsible for interacting with infrastructure platforms |
| Infrastructure approval | Authorization to execute a deployment |
| Configuration fingerprint | Hash used to identify configuration changes |

## 19. Implementation Limitations

The five implementations provide executable infrastructure-management simulations and a relational deployment model.

They do not constitute production cloud provisioning systems.

Specific limitations include:

- Provider operations are simulated rather than connected to real cloud APIs.
- The Python JSON state file does not implement distributed locking.
- The JavaScript controller protects only its own process state.
- The C++ and Java implementations maintain in-memory infrastructure state.
- The PostgreSQL procedure updates recorded infrastructure state rather than invoking a cloud provider.
- The sample approval model demonstrates authorization decisions but does not implement a complete enterprise identity and access management system.
- The simulated state rollback mechanisms do not reverse real external infrastructure operations.
- Provider-specific replacement rules, retry semantics, and resource lifecycle behavior require additional implementation.

These distinctions are important when translating an educational IaC model into a production deployment platform.

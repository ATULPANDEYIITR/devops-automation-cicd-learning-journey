# Ansible Roles: Reusable Configuration-Management Architecture

## 1. Introduction

Ansible Roles provide a reusable, modular architecture for organizing configuration-management automation.

A role groups related configuration tasks, variables, handlers, templates, files, dependencies, and metadata into a standardized directory structure.

Instead of maintaining a large collection of unrelated tasks in one playbook, infrastructure engineers divide configuration into independently maintainable components.

Typical roles include:

- `common`: shared operating-system configuration
- `webserver`: web server installation and configuration
- `database`: database installation and administration
- `monitoring`: monitoring agent configuration
- `security`: operating-system hardening and security policies
- `firewall`: network access configuration

The implementations in this project model role registration, dependency management, variable resolution, execution, idempotence, handlers, and infrastructure state.

## 2. Ansible Role Architecture

### 2.1 Standard directory structure

A conventional Ansible role follows this structure:

    project/
    |
    +-- ansible.cfg
    |
    +-- inventory/
    |   +-- production/
    |   |   +-- hosts.yml
    |   |   +-- group_vars/
    |   |   +-- host_vars/
    |   |
    |   +-- staging/
    |       +-- hosts.yml
    |
    +-- playbooks/
    |   +-- site.yml
    |   +-- webservers.yml
    |
    +-- roles/
        |
        +-- common/
        |   +-- defaults/
        |   |   +-- main.yml
        |   +-- vars/
        |   |   +-- main.yml
        |   +-- tasks/
        |   |   +-- main.yml
        |   +-- handlers/
        |   |   +-- main.yml
        |   +-- templates/
        |   +-- files/
        |   +-- meta/
        |       +-- main.yml
        |
        +-- webserver/
        |   +-- defaults/
        |   +-- vars/
        |   +-- tasks/
        |   +-- handlers/
        |   +-- templates/
        |   +-- files/
        |   +-- meta/
        |
        +-- monitoring/
            +-- defaults/
            +-- vars/
            +-- tasks/
            +-- handlers/
            +-- templates/
            +-- files/
            +-- meta/

### 2.2 Role directory responsibilities

| Directory | Responsibility |
|---|---|
| `defaults/` | Default role variables with relatively low precedence |
| `vars/` | Role variables with higher precedence |
| `tasks/` | Configuration-management operations |
| `handlers/` | Actions triggered by task notifications |
| `templates/` | Jinja2 configuration templates |
| `files/` | Static files copied to managed hosts |
| `meta/` | Role metadata and dependencies |
| `tests/` | Role validation and testing |
| `README.md` | Role documentation |

Not every directory is mandatory. Ansible uses the conventional directory names to discover role components.

## 3. Role Dependencies and Composition

A role dependency expresses that one role requires another role to execute first.

Example:

    webserver
        |
        +-- common
        |
        +-- security

The dependency graph can be represented as a directed graph:

    common
       |
       v
    security
       |
       v
    webserver
       |
       v
    monitoring

A valid dependency graph must be acyclic.

### Dependency resolution

The Python, JavaScript, C++17, and Java implementations use graph traversal to determine execution order.

The resolution process is:

1. Identify requested roles.
2. Retrieve each role's dependencies.
3. Recursively resolve dependencies.
4. Detect circular dependencies.
5. Avoid executing the same dependency repeatedly.
6. Produce a dependency-respecting execution sequence.

Depth-first search provides a practical implementation.

For a graph with V roles and E dependency relationships:

- Time complexity: O(V + E)
- Space complexity: O(V + E)

Ansible roles can declare dependencies through `meta/main.yml`.

The simulator uses a registry and dependency graph to reproduce this architectural behavior.

## 4. Variable Management and Precedence

Variables allow reusable roles to support different infrastructure environments without changing task implementations.

For example, a web server role can use different ports and configuration values across development, staging, and production.

### 4.1 Variable categories

| Variable category | Purpose |
|---|---|
| Role defaults | Provide configurable fallback values |
| Inventory variables | Describe hosts and groups |
| Role variables | Define role-specific configuration |
| Play variables | Configure a particular play |
| Extra variables | Supply execution-time overrides |

The Python and JavaScript implementations use the following simplified precedence:

    Role defaults
         |
         v
    Inventory variables
         |
         v
    Role variables
         |
         v
    Play variables
         |
         v
    Extra variables

The Java implementation follows the same explicit resolution model.

The PostgreSQL implementation stores variable values as JSONB and resolves them using scope, priority, and deterministic ordering.

Actual Ansible variable precedence is more extensive than this educational model. It includes additional sources such as facts, registered variables, include variables, block variables, and command-line overrides.

### 4.2 Variable validation

Configuration variables should be validated before they are used.

Examples include:

- Port numbers must be within the valid TCP/UDP port range.
- Boolean configuration values must have valid representations.
- Configuration paths must follow the expected filesystem policy.
- Package names must use an accepted naming format.
- Required variables must not be missing.

Variable validation prevents malformed configuration from propagating to managed infrastructure.

## 5. Task Execution Architecture

A task represents an individual configuration-management operation.

Examples include:

- Installing a package.
- Creating a directory.
- Deploying a configuration file.
- Starting a service.
- Creating a system user.
- Applying filesystem permissions.

A role contains an ordered collection of tasks.

Example conceptual workflow:

    Webserver Role
         |
         v
    Install nginx
         |
         v
    Deploy configuration
         |
         v
    Start nginx
         |
         v
    Verify service state

The implementations model tasks as objects containing:

- Task name
- Execution action
- Execution tags
- Conditional expression
- Handler notifications
- Privilege-escalation metadata

A task can produce one of four principal outcomes.

| Status | Meaning |
|---|---|
| `ok` | Desired state already exists |
| `changed` | Configuration state was modified |
| `failed` | Task execution encountered an error |
| `skipped` | Task was excluded by a condition or execution filter |

These outcomes are useful for infrastructure reporting and diagnosing configuration failures.

## 6. Idempotence

Idempotence is a fundamental property of configuration management.

An operation is idempotent when repeated execution produces the same desired state without repeatedly modifying an already-correct resource.

Mathematically:

    F(F(x)) = F(x)

Where:

- x represents the initial infrastructure state.
- F represents the configuration operation.
- F(x) represents the resulting desired state.

Consider package installation.

First execution:

    nginx absent
        |
        v
    Install nginx
        |
        v
    nginx present
        |
        v
    CHANGED

Second execution:

    nginx present
        |
        v
    Verify package
        |
        v
    nginx present
        |
        v
    OK

Idempotence reduces unnecessary configuration changes, service interruptions, and operational overhead.

The Python, JavaScript, C++17, and Java implementations use state comparisons before modifying packages, services, and configuration files.

The PostgreSQL implementation uses `evaluate_resource_change()` and an upsert operation to maintain a desired-state ledger.

The ledger represents application-level configuration state. It does not independently verify the actual remote operating-system state.

## 7. Handlers and Notifications

Handlers are specialized tasks triggered by notifications from ordinary tasks.

They are useful when configuration changes require a subsequent service operation.

Example:

    Deploy nginx configuration
                |
                v
         Configuration changed?
                |
          +-----+-----+
          |           |
         YES          NO
          |           |
          v           v
      Notify       No action
      handler
          |
          v
      Restart nginx

A handler generally executes once per host for a notification cycle, even if several tasks notify it.

This behavior prevents repeated unnecessary service restarts.

The implementations maintain a pending-handler collection and execute handlers after the relevant task sequence.

The PostgreSQL implementation separates notification records from handler execution records.

This distinction provides traceability between:

- The task that generated a notification.
- The handler that received it.
- The host on which it was triggered.
- The execution result.

## 8. Tags and Conditional Execution

Tags provide selective execution of role tasks.

Example tag categories:

| Tag | Purpose |
|---|---|
| `packages` | Package installation |
| `configuration` | Configuration deployment |
| `services` | Service management |
| `security` | Security configuration |
| `monitoring` | Monitoring operations |
| `always` | Tasks intended to run regardless of ordinary tag selection |

A task may have multiple tags.

Conditional execution provides another control mechanism.

Examples include:

- Execute a monitoring task only when monitoring is enabled.
- Configure a firewall only on Linux hosts.
- Install a package only when the required operating-system family matches.
- Skip production-only tasks on development hosts.

The implementations combine tags with host and variable conditions.

Ansible supports additional tag behavior, including special tags such as `never` and `always`, and more advanced selection through command-line options.

## 9. Check Mode and Dry-Run Execution

Check mode evaluates the potential impact of configuration tasks without applying ordinary changes.

Example:

    Current state
        |
        v
    Evaluate desired state
        |
        v
    Would a change be necessary?
        |
        +------+
        |      |
       YES     NO
        |      |
        v      v
      Report   Report
      change   unchanged

The Python, JavaScript, C++17, and Java implementations provide a check-mode execution path.

Their check-mode implementation deliberately avoids state mutation.

Actual Ansible check-mode behavior depends on module support. Some modules can accurately predict changes, while others have limited or unavailable check-mode support.

A production configuration-management workflow should distinguish between:

- A task that can predict its result.
- A task that can inspect state but cannot predict its result.
- A task that does not support check mode.

## 10. Configuration Management and Inventory

Ansible inventory defines the infrastructure against which playbooks execute.

Inventory can contain:

- Individual hosts.
- Host groups.
- Group variables.
- Host variables.
- Connection parameters.
- Operating-system information.
- Environment-specific configuration.

Example logical inventory:

    production
       |
       +-- web-01
       |
       +-- web-02
       |
       +-- database-01

    staging
       |
       +-- staging-web-01

The PostgreSQL implementation models hosts, groups, and host-group memberships through relational tables.

The other implementations use in-memory host objects.

This enables the same reusable role to be applied to several hosts with different variable values.

## 11. Security and Privilege Management

Reusable roles should implement security controls consistently.

Important controls include:

### Privilege escalation

Ansible supports privilege escalation through mechanisms such as `become`.

Typical administrative operations requiring elevated permissions include:

- Installing system packages.
- Managing system services.
- Modifying protected configuration files.
- Creating system accounts.

The implementations include privilege-escalation metadata to identify tasks requiring administrative access.

The metadata does not independently implement operating-system privilege escalation.

### Secret management

Credentials, API tokens, private keys, and passwords must not be stored as ordinary plaintext role variables.

Sensitive information should be protected using:

- Ansible Vault.
- External secret-management systems.
- Restricted inventory access.
- Encrypted transport.
- Least-privilege execution accounts.

The PostgreSQL implementation intentionally does not treat JSONB storage as secure secret storage.

### Filesystem security

Configuration deployment should validate destination paths and restrict permissions.

Production implementations should also consider:

- Path traversal attacks.
- Symbolic-link handling.
- Ownership and group permissions.
- Atomic file replacement.
- Configuration backup and rollback.
- Restricted access to execution logs.

### Infrastructure access

SSH authentication, host-key verification, network restrictions, and credential rotation should be enforced independently of role organization.

A reusable role improves consistency but does not automatically guarantee secure infrastructure.

## 12. Python Implementation

The Python program provides a repository-style configuration-management simulator.

### Main components

| Component | Responsibility |
|---|---|
| `Host` | Represents a managed host |
| `Task` | Defines an executable configuration operation |
| `Handler` | Defines a notification-triggered action |
| `Role` | Groups tasks, variables, dependencies, and handlers |
| `RoleRegistry` | Registers roles and resolves dependencies |
| `VariableResolver` | Applies simplified variable precedence |
| `RoleExecutor` | Coordinates task execution and reporting |

### Implemented operations

The example includes:

- Installing curl.
- Installing nginx.
- Deploying nginx configuration.
- Starting nginx.
- Installing node exporter.
- Restarting nginx through a handler.

The registry resolves role dependencies before execution.

The executor maintains task results and skips further tasks on a host after a failure.

The final assertions verify that a second execution does not produce unnecessary changes.

The implementation uses Python dataclasses, enums, callable actions, dictionaries, sets, exceptions, and JSON reporting.

## 13. JavaScript Implementation

The JavaScript program provides an asynchronous, event-driven architecture.

### Main components

| Component | Responsibility |
|---|---|
| `Host` | Infrastructure state representation |
| `Task` | Task definition and execution conditions |
| `Role` | Reusable configuration component |
| `RoleRegistry` | Dependency resolution |
| `VariableResolver` | Variable precedence |
| `RoleExecutor` | Asynchronous orchestration |
| `EventEmitter` | Execution event publication |

### Asynchronous execution

The JavaScript executor uses:

- `async` and `await`
- Promises
- `EventEmitter`
- Maps and Sets
- Bounded host concurrency

Tasks remain sequential within a role for each host, while multiple hosts can be processed concurrently.

This design supports infrastructure operations where network requests and remote command execution may have variable response times.

### Event-driven reporting

Each task emits an execution event containing:

- Unique execution identifier.
- Timestamp.
- Host.
- Role.
- Task.
- Status.
- Message.

The reporting mechanism can be extended to feed an operational dashboard or execution-monitoring service.

The example also exports a JSON report through an atomic temporary-file replacement.

## 14. C++17 Implementation

The C++17 implementation focuses on a strongly typed infrastructure execution engine.

### Domain model

The program uses:

- `Host` for infrastructure resources.
- `Task` for executable operations.
- `Handler` for notification-triggered actions.
- `Role` for configuration modules.
- `RoleRegistry` for dependency resolution.
- `RoleEngine` for orchestration.
- `TaskResult` for execution records.

### Design decisions

The implementation uses STL containers according to their operational characteristics.

| Container | Application |
|---|---|
| `vector` | Ordered roles, tasks, and results |
| `unordered_map` | Role registry |
| `unordered_set` | Dependency traversal |
| `set` | Unique package names and execution tags |
| `map` | Deterministic resource state |
| `function` | Runtime task actions |

Role dependencies use depth-first search.

Package installation uses a set to provide efficient membership checks.

Service and file state use maps to support direct resource lookup.

The implementation also demonstrates exception handling, task failure propagation, and handler deduplication.

## 15. Java 17 Implementation

The Java implementation represents an enterprise-oriented configuration-management service.

### Architectural components

| Component | Responsibility |
|---|---|
| `Role` | Immutable role definition |
| `Task` | Configuration task |
| `Handler` | Event-triggered operation |
| `Host` | Managed infrastructure representation |
| `Variables` | Read-only variable collection |
| `RoleRegistry` | Role registration and dependency validation |
| `VariableResolver` | Variable resolution |
| `RoleExecutionService` | Execution orchestration |
| `ExecutionRecord` | Immutable execution record |

### Enterprise-oriented decisions

The implementation uses Java records for immutable execution results.

Enums represent task statuses and execution modes.

Functional interfaces separate task behavior from orchestration.

Collections maintain role definitions, host state, and notification queues.

The service layer separates execution policy from resource-management operations.

The implementation provides:

- Dependency validation.
- Task validation.
- Handler ownership validation.
- Variable precedence.
- Conditional execution.
- Check mode.
- Idempotence verification.
- Structured execution reporting.

The role definitions use immutable collection copies to reduce accidental modification of configuration metadata.

## 16. PostgreSQL Implementation

The PostgreSQL script provides a relational model for reusable configuration-management architecture.

### 16.1 Database entities

| Table | Responsibility |
|---|---|
| `roles` | Role catalogue and versions |
| `role_dependencies` | Role dependency relationships |
| `inventory_hosts` | Managed infrastructure |
| `inventory_groups` | Inventory groups |
| `host_group_memberships` | Host-group relationships |
| `configuration_variables` | Configuration variables |
| `playbooks` | Execution definitions |
| `playbook_roles` | Role assignments and ordering |
| `role_tasks` | Role task definitions |
| `role_handlers` | Handler definitions |
| `task_notifications` | Task-handler relationships |
| `execution_runs` | Execution sessions |
| `execution_run_hosts` | Hosts assigned to executions |
| `task_execution_results` | Task-level execution records |
| `handler_execution_queue` | Handler notifications |
| `managed_resources` | Last-applied desired resource state |

### 16.2 Relational architecture

    Roles
      |
      +---- Role Dependencies
      |
      +---- Role Tasks
      |        |
      |        +---- Task Notifications
      |                    |
      |                    v
      |                 Handlers
      |
      +---- Playbook Roles
                   |
                   v
                Playbooks
                   |
                   v
              Execution Runs
                   |
                   v
             Execution Hosts
                   |
                   v
            Task Execution Results
                   |
                   v
              Execution Reports

Inventory hosts connect the execution model with managed resources.

### 16.3 Database integrity

The script uses:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Partial indexes.
- GIN indexes.
- JSONB.
- Recursive CTEs.
- Views.
- Functions.
- Procedures.
- Triggers.
- Transactions.

The dependency trigger prevents insertion of a dependency that creates a cycle.

The notification trigger ensures that a task and its notified handler belong to the same role.

The resource-state procedure validates execution ownership and prevents mutation during check-mode execution.

### 16.4 Execution reporting

The `execution_report` view aggregates:

- Total tasks.
- Changed tasks.
- Successful unchanged tasks.
- Failed tasks.
- Skipped tasks.

The `role_dependency_report` view provides a readable dependency representation.

These views separate operational reporting from the underlying relational storage model.

## 17. Role Versioning and Reusability

Reusable roles should have explicit version management.

For example:

| Role | Version | Responsibility |
|---|---|---|
| `common` | 1.0.0 | Shared operating-system configuration |
| `webserver` | 2.0.0 | Web server deployment |
| `monitoring` | 1.0.0 | Monitoring agent deployment |

Versioning supports controlled infrastructure changes.

A role update should consider:

- Backward compatibility.
- Variable naming changes.
- Dependency changes.
- Handler behavior.
- Supported operating systems.
- Task execution order.
- Security implications.

Ansible role dependencies can be declared in metadata, while external role versions can be managed through dependency-management mechanisms such as `requirements.yml`.

The database schema supports multiple versions of the same role through a unique role-name and version combination.

## 18. Failure Handling and Recovery

Configuration management must account for partial failures.

Typical failure conditions include:

| Failure | Possible cause | Operational response |
|---|---|---|
| Dependency failure | Missing role or circular dependency | Correct dependency graph |
| Package failure | Repository unavailable | Verify repository connectivity |
| Template failure | Missing variable | Validate role configuration |
| Permission failure | Insufficient privileges | Correct privilege policy |
| Service failure | Invalid configuration | Validate configuration before restart |
| Handler failure | Service unavailable | Inspect service and handler logs |
| Host connection failure | SSH or network issue | Verify connectivity |
| Partial deployment | Some hosts completed successfully | Reconcile host states |

A production Ansible playbook can use `block`, `rescue`, and `always` for structured error handling.

It can also use controls such as `serial`, `any_errors_fatal`, and `max_fail_percentage` to govern deployment behavior.

The sample implementations use host-level failure flags and structured execution records.

These models are educational execution engines rather than complete replacements for Ansible's remote execution, rollback, and error-recovery facilities.

## 19. Performance Considerations

Role architecture affects configuration-management performance.

Important considerations include:

1. Reuse shared roles rather than duplicating equivalent tasks.
2. Avoid unnecessary dependency chains.
3. Minimize expensive configuration checks.
4. Use appropriate execution concurrency.
5. Avoid repeatedly restarting services.
6. Filter task execution with meaningful tags.
7. Keep role variables and task definitions maintainable.
8. Index frequently queried execution records.
9. Retain execution logs according to operational requirements.

### Complexity characteristics

| Operation | Expected complexity |
|---|---|
| Role lookup using a hash map | O(1) average |
| Dependency resolution | O(V + E) |
| Package membership using a set | O(1) average |
| Resource lookup using a hash map | O(1) average |
| Ordered task execution | O(T) per host |
| Execution reporting | O(R) |
| Database resource lookup | Index-dependent |

Where:

- V represents the number of roles.
- E represents dependency relationships.
- T represents the number of tasks.
- R represents execution records.

The JavaScript implementation uses bounded concurrency to avoid launching an unrestricted number of simultaneous operations.

The PostgreSQL implementation indexes execution status, role ordering, task tags, and host-specific resources.

## 20. Running the Implementations

### Python

Requirements: Python 3.10 or later.

Run:

    python ansible_roles.py

The program executes the sample infrastructure workflow and performs idempotence and dependency-cycle checks.

### JavaScript

Requirements: Node.js 18 or later.

Run:

    node ansible_roles.js

The program executes asynchronous host operations, displays events, verifies check mode, and exports `ansible-roles-report.json`.

### C++17

Compile:

    g++ -std=c++17 -O2 -Wall -Wextra -pedantic ansible_roles.cpp -o ansible_roles

Run:

    ./ansible_roles

On Windows:

    ansible_roles.exe

### Java 17

Compile:

    javac AnsibleRoles.java

Run:

    java AnsibleRoles

### PostgreSQL

Execute the SQL script:

    psql -U postgres -d postgres -f ansible_roles.sql

The script creates the `ansible_lab` schema, database objects, sample inventory, roles, tasks, dependencies, and execution records.

It uses PostgreSQL-specific features and requires an appropriate database account with schema and object-creation privileges.

## 21. Technical Distinctions

Several concepts within reusable configuration management are related but should not be treated as interchangeable.

| Concept | Primary purpose |
|---|---|
| Role | Organizes reusable configuration components |
| Task | Performs an individual configuration operation |
| Handler | Performs an action after receiving a notification |
| Dependency | Establishes role execution relationships |
| Inventory | Defines managed infrastructure |
| Variable | Supplies configuration data |
| Playbook | Coordinates infrastructure configuration |
| Tag | Selects tasks for execution |
| Check mode | Evaluates changes without ordinary mutation |
| Idempotence | Prevents unnecessary repeated changes |
| Metadata | Describes role properties and compatibility |

A role provides modular organization.

A playbook coordinates execution.

An inventory identifies the infrastructure.

Tasks implement configuration operations.

Handlers respond to relevant changes.

Dependencies determine execution relationships.

Variables make configuration reusable across environments.

Idempotence ensures that repeated execution converges toward the intended infrastructure state.

These mechanisms collectively provide a maintainable architecture for configuration management.

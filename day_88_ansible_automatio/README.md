# Ansible Automation: Variables, Handlers, Templates, and Conditionals

## 1. Technical Scope

Ansible is an agentless configuration-management and automation system used to configure servers, deploy applications, manage infrastructure, and execute repeatable operational workflows.

Its automation model uses declarative YAML playbooks, an inventory of managed hosts, modules, variables, Jinja2 templates, conditional expressions, and event-driven handlers.

This implementation examines four closely related but technically distinct mechanisms:

| Mechanism | Primary responsibility | Operational effect |
|---|---|---|
| Variables | Supply configuration values | Determine desired configuration |
| Handlers | Respond to notified changes | Execute deferred operations |
| Templates | Generate configuration files | Produce host-specific configuration |
| Conditionals | Control task eligibility | Determine whether tasks execute |

The implementations use a common application-deployment scenario involving two production web servers.

The application has configurable names, versions, installation directories, ports, and service settings.

The examples demonstrate configuration differences between hosts without duplicating the deployment workflow.

## 2. Ansible Execution Architecture

Ansible generally operates through a control node that communicates with managed nodes.

The control node interprets playbooks, resolves variables, evaluates conditions, executes modules, processes task results, and manages handler notifications.

A simplified execution architecture is:

Control Node
    |
    v
Inventory
    |
    v
Playbook
    |
    v
Variable Resolution
    |
    v
Host Selection
    |
    v
Conditional Evaluation
    |
    v
Task Execution
    |
    +----> Changed
    |         |
    |         v
    |      Handler Notification
    |         |
    |         v
    |      Handler Queue
    |         |
    |         v
    |      Handler Execution
    |
    +----> OK
    |
    +----> Skipped
    |
    +----> Failed

    |
    v
Execution Results

A typical Ansible playbook follows this structure:

- Inventory identifies managed hosts.
- Plays associate hosts with automation tasks.
- Variables describe desired configuration.
- Tasks invoke Ansible modules.
- Conditionals determine task eligibility.
- Templates generate configuration artifacts.
- Handlers respond to notifications.
- Execution results indicate whether operations succeeded, changed, were skipped, or failed.

The control node does not normally require a permanently installed Ansible agent on each managed host.

For SSH-managed Linux systems, Ansible generally connects through SSH and executes modules remotely.

## 3. Variables

### 3.1 Definition

Variables represent configuration values used by playbooks, tasks, templates, and automation logic.

They separate configuration data from execution instructions.

Consider an application deployment with these variables:

| Variable | Example value | Purpose |
|---|---|---|
| `application_name` | `inventory-api` | Application identifier |
| `application_version` | `1.1.0` | Deployment version |
| `application_port` | `8080` | Listening port |
| `application_directory` | `/opt/inventory` | Installation directory |
| `service_name` | `inventory-api` | Operating-system service |
| `environment` | `production` | Deployment environment |

Variables allow the same playbook to deploy different application configurations to different hosts.

### 3.2 Variable Sources

Ansible supports multiple variable-definition mechanisms.

| Source | Typical use |
|---|---|
| Role defaults | Reusable fallback configuration |
| Inventory variables | Inventory-wide configuration |
| Group variables | Shared settings for host groups |
| Host variables | Host-specific configuration |
| Play variables | Configuration scoped to a play |
| Task variables | Configuration scoped to a task |
| Extra variables | Explicit runtime overrides |

Ansible has a substantially more detailed precedence hierarchy than this simplified educational model.

The actual precedence depends on the variable source, scope, and execution context. Variables such as registered values, facts, role parameters, block variables, and include variables introduce additional rules.

Extra variables generally have very high precedence.

### 3.3 Group and Host Variables

Suppose an inventory contains:

- `web01.example.internal`
- `web02.example.internal`

Both hosts belong to the `web` group.

The group configuration specifies:

- Environment: production.
- Application version: 1.0.0.
- Default application port: 8080.

The second host overrides the port with 8081.

The effective configuration becomes:

| Variable | web01 | web02 |
|---|---|---|
| Environment | production | production |
| Port | 8080 | 8081 |
| Application | inventory-api | inventory-api |
| Version | 1.0.0 | 1.0.0 |

The group establishes shared configuration. The host-specific definition changes only the required value.

### 3.4 Variable Resolution

Variable resolution determines which value is used when multiple definitions have the same name.

The Python and Java implementations use an explicit educational precedence model.

The JavaScript implementation stores resolved configurations as immutable objects to reduce accidental modification during execution.

The PostgreSQL implementation uses `resolve_host_variables()` to retrieve the effective variable values for an inventory host.

Its `DISTINCT ON` query selects the highest-precedence definition for each variable.

This makes variable resolution inspectable and queryable.

### 3.5 Variable Validation

Variables must satisfy domain requirements before automation begins.

Examples include:

- Application names must not be empty.
- Application versions must be present.
- Application ports must be integers.
- Valid TCP/UDP port values range from 1 to 65535.
- Application directories must be absolute paths.
- Required service identifiers must be present.

Invalid configuration should fail before deployment changes infrastructure.

Secret variables require additional protection.

Ansible Vault can encrypt sensitive values at rest. Database-backed automation systems should also enforce access controls, avoid exposing secret values in reports, and use encrypted connections.

The SQL model includes an `is_secret` field and redacts marked values in the variable-retrieval query. This is a reporting safeguard, not an encryption mechanism.

## 4. Handlers

### 4.1 Definition

Handlers are special Ansible tasks that execute when another task explicitly notifies them.

They are designed for operations that should occur only when a relevant configuration change takes place.

Common examples include:

- Restarting an application service.
- Reloading a web server.
- Restarting a database service.
- Reloading a firewall configuration.
- Rebuilding a service configuration cache.

A normal task executes according to the playbook's task sequence.

A handler is deferred until its notification is processed.

### 4.2 Notification Mechanics

Consider a configuration deployment task.

When the template changes, it notifies a service-restart handler.

The relationship is:

Template Task
    |
    v
Configuration Changed?
    |
    +---- No ----> No Notification
    |
    +---- Yes
            |
            v
       Notify Handler
            |
            v
       Queue Handler
            |
            v
       Execute Handler

An unchanged task does not normally notify its handler.

### 4.3 Handler Deduplication

A handler notified several times during a play is normally executed only once for that play execution.

For example:

1. A package task changes the application.
2. A configuration task changes the application configuration.
3. Both notify the same restart handler.
4. The handler executes once when notifications are processed.

This avoids unnecessary repeated restarts.

The Python implementation uses sets to deduplicate pending handler notifications.

The JavaScript implementation uses `Map` and `Set` collections.

The C++ implementation uses `std::map` and `std::set`.

The Java implementation uses `LinkedHashMap` and `LinkedHashSet` to preserve predictable processing order.

The SQL implementation maintains one handler-execution record per host execution and handler.

The notification counter records how many times a handler was notified.

### 4.4 Handler Names and Listen Directives

Ansible supports notifying handlers by their names or by notification topics.

For example, multiple tasks can notify a shared topic such as `restart web service`.

A handler can subscribe to that topic through `listen`.

This separates the notification interface from the actual handler name.

It is useful when several independent tasks require the same operational response.

### 4.5 Handler Execution Timing

Handlers normally execute at the end of a play's task section.

The `ansible.builtin.meta` module supports explicit handler flushing through `flush_handlers`.

This allows a playbook to execute pending handlers before reaching its normal completion point.

Handler execution is affected by task failures. By default, a host with a failure does not necessarily execute pending handlers later in the play.

The `force_handlers` play keyword changes this behavior for applicable failures.

Handlers are also ordered according to their definition rather than the order in which they receive notifications.

### 4.6 Handler Limitations

Handlers are not a replacement for ordinary tasks.

They are inappropriate for operations that must execute every time, regardless of whether a configuration change occurred.

For example, a mandatory health-check task should not be implemented as a change-triggered handler.

A service restart should be notified only when an operation actually changes the relevant service configuration or deployed application.

## 5. Templates

### 5.1 Definition

Ansible templates use the Jinja2 templating language to generate files dynamically.

A template combines fixed configuration content with variable expressions and, where appropriate, Jinja2 control structures.

The standard template module is `ansible.builtin.template`.

Its main purpose is to generate host-specific configuration files from a reusable source.

### 5.2 Example Configuration Template

The application configuration can contain:

    server {
        listen {{ application_port }};
        server_name {{ application_name }};
        environment {{ environment }};
    }

For the first web server, the generated configuration contains port 8080.

For the second web server, it contains port 8081.

The same template produces different results because the effective host variables differ.

### 5.3 Template Workflow

The template deployment process follows these stages:

1. Load the template source.
2. Resolve variables for the managed host.
3. Evaluate supported Jinja2 expressions.
4. Generate the destination content.
5. Compare the desired content with the existing file.
6. Apply the configuration if required.
7. Report whether the task changed the managed host.
8. Notify relevant handlers when a change occurs.

### 5.4 Template Parameters

The Ansible template module supports operational attributes such as:

| Parameter | Function |
|---|---|
| `src` | Source template |
| `dest` | Destination file |
| `owner` | File owner |
| `group` | File group |
| `mode` | File permissions |
| `backup` | Create a backup before replacing an existing file |
| `validate` | Validate the temporary file before installation |
| `force` | Control whether replacement is permitted |

File permissions are particularly important for application configuration files containing credentials or other sensitive information.

### 5.5 Idempotent Template Deployment

Ansible modules generally aim to be idempotent.

Idempotency means that applying the same desired configuration repeatedly should not produce unnecessary changes after the system reaches the desired state.

For templates:

- First execution: the file is created or updated.
- Second execution: identical content produces no change.
- Third execution: identical content continues to produce no change.

The Python implementation compares the rendered content with its stored configuration.

The JavaScript implementation uses a `Map` to store destination content.

The C++ implementation compares strings in a file-state map.

The Java implementation maintains destination-to-content mappings.

The SQL model stores template source, destination, ownership, permissions, and version metadata.

The actual Ansible template module performs remote file management and change detection.

### 5.6 Template Security

Template rendering must not expose secrets through generated files, logs, or execution reports.

Appropriate controls include:

- Restricting permissions.
- Using Ansible Vault for encrypted secrets.
- Applying `no_log` to sensitive tasks where appropriate.
- Avoiding untrusted template input.
- Validating generated configuration before installation.
- Avoiding unnecessary exposure of sensitive registered variables.

A configuration file should be validated before restarting a production service.

## 6. Conditionals

### 6.1 Definition

Conditionals control whether an Ansible task, block, or play executes.

The primary conditional keyword is `when`.

It evaluates an expression and determines whether the associated operation is eligible to run.

A condition evaluating to false results in a skipped task rather than a successful configuration change.

### 6.2 Basic Conditional Example

A configuration task can execute only in production:

    when: environment == "production"

A deployment can also depend on a host group:

    when: "'web' in group_names"

A conditional can evaluate multiple requirements:

    when:
      - environment == "production"
      - application_port | int >= 1024

A list of conditions under `when` is evaluated using logical AND semantics.

### 6.3 Conditional Execution States

| Condition or execution outcome | Result |
|---|---|
| Condition is true and task changes state | Changed |
| Condition is true and task makes no change | OK |
| Condition is false | Skipped |
| Task execution encounters an error | Failed |

These outcomes should not be confused.

A skipped task does not indicate that the desired operation succeeded. It indicates that the operation was not attempted because its condition was not satisfied.

### 6.4 Common Conditional Patterns

**Environment selection**

Execute production-only configuration.

**Operating-system selection**

Use different package-management operations according to the target operating system.

**Service state**

Restart or configure a service only when it exists or meets the required conditions.

**Version comparison**

Perform upgrades only when the installed version differs from the desired version.

**Variable availability**

Use `is defined` and `is not defined` to test whether a variable exists.

**Registered results**

Use the output of an earlier task to determine whether a later operation should execute.

### 6.5 Conditionals and Error Handling

A conditional does not automatically validate every underlying configuration value.

For example, checking whether a port is defined does not establish that it is within the valid port range.

Variable validation and task eligibility are separate responsibilities.

Appropriate validation should happen before execution whenever possible.

## 7. Distinguishing the Four Mechanisms

The four mechanisms cooperate during automation but serve different purposes.

| Mechanism | Question answered | Example |
|---|---|---|
| Variables | What configuration should be used? | Port 8080 |
| Templates | What configuration file should be generated? | Application server configuration |
| Conditionals | Should this operation execute? | Production hosts only |
| Handlers | What should happen after a relevant change? | Restart application service |

A complete workflow connects them:

Variables
    |
    v
Template Rendering
    |
    v
Conditional Evaluation
    |
    v
Configuration Deployment
    |
    v
Change Detection
    |
    v
Handler Notification
    |
    v
Service Restart

The distinction matters because changing one mechanism does not automatically perform the responsibilities of the others.

For example, changing a variable does not guarantee a service restart. A task must consume the updated value, detect a change, and notify the appropriate handler.

## 8. Python Implementation

### 8.1 Architecture

The Python implementation provides an executable simulation of the configuration-management lifecycle.

Its principal components are:

| Component | Responsibility |
|---|---|
| `Host` | Represents an inventory host |
| `VariableResolver` | Resolves configuration precedence |
| `TemplateEngine` | Renders supported template expressions |
| `Task` | Defines an automation operation |
| `Handler` | Defines a deferred operation |
| `TaskResult` | Records execution outcomes |
| `AutomationEngine` | Coordinates the workflow |

### 8.2 Variable Resolution

The resolver merges dictionaries according to its defined precedence.

The implementation deliberately uses a simplified hierarchy rather than claiming to reproduce every Ansible variable-precedence rule.

Required variables are checked before hosts are added.

### 8.3 Template Rendering

The renderer supports simple variable interpolation using expressions such as `{{ application_port }}`.

It also supports dictionary-based dotted access.

Undefined variables raise `TemplateError`.

This implementation is intentionally smaller than Jinja2 and does not support filters, loops, macros, template inheritance, or the complete Jinja2 language.

### 8.4 Task Execution

Tasks can have:

- A name.
- An execution function.
- A conditional function.
- Handler notifications.
- Tags.

Each task returns a Boolean indicating whether it changed managed state.

The engine converts that result into `changed` or `ok`.

Exceptions produce a `failed` result and stop further execution on the affected host.

### 8.5 Handler Management

The engine maintains a per-host notification queue.

A handler is executed only when notified.

Pending notifications are stored in a set, preventing duplicate handler execution.

Host-specific queues ensure that restarting one server does not automatically restart every other server.

### 8.6 Execution Results

The report includes:

- Host identity.
- Task names.
- Execution statuses.
- Failure messages.
- Per-host statistics.

The program uses only the Python standard library.

Run it with Python 3.10 or later.

## 9. JavaScript Implementation

### 9.1 Architecture

The JavaScript implementation models automation as an event-driven system.

Its main components are:

| Component | Responsibility |
|---|---|
| `VariableStore` | Configuration resolution and validation |
| `TemplateRenderer` | Template interpolation |
| `Host` | Host state and inventory groups |
| `Task` | Asynchronous automation operations |
| `Handler` | Deferred event-driven operations |
| `AutomationEngine` | Execution orchestration |

### 9.2 Event-Driven Notifications

The engine extends Node.js `EventEmitter`.

A changed task emits a `handler-notification` event.

The notification listener resolves the relevant handler and places it into the host's pending queue.

This demonstrates event-driven coordination without requiring tasks to invoke restart operations directly.

### 9.3 Asynchronous Execution

Task actions return Promises.

The engine uses `Promise.all()` to execute tasks concurrently across hosts while preserving the ordering of task stages.

This is useful for modeling distributed infrastructure where independent hosts can be managed concurrently.

A production implementation must also account for:

- Connection limits.
- API rate limits.
- Remote execution timeouts.
- Resource contention.
- Cancellation.
- Retry policies.
- Host availability.

### 9.4 Immutable Variables

The variable store freezes resolved configuration objects.

This reduces accidental modification of configuration values during task execution.

The implementation also validates application ports and absolute destination directories.

### 9.5 Failure Isolation

A failed task marks its host as failed.

Other hosts continue through the automation workflow.

This models host-level execution isolation rather than treating every remote failure as a global execution failure.

The template renderer intentionally implements only simple interpolation and does not replace Jinja2.

## 10. C++17 Implementation

### 10.1 Architecture

The C++ implementation focuses on explicit state management and efficient in-memory representations.

| Component | Responsibility |
|---|---|
| `Variables` | Typed application configuration |
| `Host` | Host identity and managed state |
| `Task` | Task execution definition |
| `Handler` | Change-triggered operation |
| `TaskResult` | Execution result |
| `RepositoryAutomationEngine` | Execution and notification coordination |

### 10.2 Strongly Typed Configuration

The implementation uses an `Environment` enumeration rather than storing environment names as unrestricted strings.

The application configuration uses strongly typed fields.

Validation occurs before a host enters the engine.

This reduces invalid-state propagation.

### 10.3 STL Data Structures

The program uses:

- `std::vector` for ordered hosts, tasks, handlers, and results.
- `std::map` for file and service state.
- `std::set` for group membership and notification deduplication.
- `std::function` for task and handler behavior.
- `std::any_of` and `std::find_if` for collection validation.

The ordered handler vector preserves registration order.

The pending notification set prevents repeated execution of the same handler.

### 10.4 Complexity Considerations

For H hosts, T tasks, and R registered handlers, the basic execution model performs approximately:

- O(H × T) task evaluations.
- O(H × T × N) notification processing, where N represents the number of notifications generated per changed task.
- O(H × R) handler inspection per flush in the straightforward implementation.
- O(K) result storage, where K is the number of recorded outcomes.

The use of sets and maps provides efficient state lookups and duplicate detection.

The implementation favors clarity and predictable state transitions over highly optimized large-scale orchestration.

### 10.5 Error Handling

The program uses exceptions for invalid configuration, unknown handler notifications, and failed task operations.

Failures are recorded against the corresponding host.

The application returns a nonzero process exit code if any host fails.

The program requires only a C++17-compatible compiler.

## 11. Java 17 Implementation

### 11.1 Enterprise-Oriented Domain Model

The Java implementation separates configuration, inventory, execution, and policy-related responsibilities.

It uses:

- Records for immutable execution results.
- Enums for environments and task states.
- Interfaces for task and handler actions.
- Collections for host state.
- Predicates for conditional evaluation.
- Dedicated exception classes for configuration and template errors.

### 11.2 Immutable Configuration

The `Configuration` class validates resolved values during construction.

Once created, the configuration fields cannot be modified.

This prevents task operations from silently changing the desired deployment configuration.

### 11.3 Service-Oriented Execution

`AutomationService` manages:

- Host registration.
- Task registration.
- Handler registration.
- Task execution.
- Notification processing.
- Handler flushing.
- Execution reporting.

This separation supports enterprise-style extension without placing all execution responsibilities in the `main` method.

### 11.4 State Transitions

The implementation models task outcomes explicitly:

`OK`, `CHANGED`, `SKIPPED`, and `FAILED`.

The service checks conditions before invoking task actions.

Changed tasks generate notifications.

Pending handlers execute in registration order and are deduplicated per host.

### 11.5 Java Runtime

The implementation uses Java 17 language features, including records and text blocks.

It requires no third-party dependencies.

Compile and execute the class using a Java 17-compatible JDK.

## 12. PostgreSQL Implementation

### 12.1 Relational Data Model

The PostgreSQL implementation models the configuration-management workflow as relational entities.

The principal relationships are:

Inventory
    |
    +---- Inventory Groups
    |
    +---- Hosts
             |
             +---- Group Memberships
             |
             +---- Variable Definitions

Playbook
    |
    +---- Automation Tasks
    |
    +---- Configuration Templates
    |
    +---- Handlers
             |
             +---- Handler Listeners

Automation Run
    |
    +---- Host Run Results
              |
              +---- Task Execution Results
              |
              +---- Handler Execution Results
              |
              +---- Handler Notification Events

### 12.2 Inventory Tables

`inventories` stores infrastructure inventories.

`inventory_groups` represents logical host groups.

`hosts` stores managed host information.

`host_group_memberships` implements the many-to-many relationship between hosts and inventory groups.

This design permits a host to belong to multiple groups.

### 12.3 Variable Definitions

`variable_definitions` stores variable names, JSONB values, scope, and secret classification.

The `resolve_host_variables()` function resolves the effective configuration for a host.

It considers inventory scope, host membership, and precedence.

The function uses `DISTINCT ON` to select one winning definition for each variable.

This provides an auditable representation of the simplified precedence model.

### 12.4 Playbook and Task Definitions

`playbooks` stores automation workflow definitions.

`automation_tasks` stores ordered operations.

Each task has:

- A task name.
- An execution order.
- A module identifier.
- JSONB action parameters.
- An optional conditional expression.
- An enabled state.

The conditional expression is stored as data.

The database does not execute arbitrary Ansible conditional syntax.

### 12.5 Template Management

`configuration_templates` stores:

- Template names.
- Destination paths.
- Template content.
- File owners.
- File groups.
- File modes.
- Template version numbers.

The database preserves the template definition but does not implement the complete Jinja2 rendering engine.

### 12.6 Handler Management

`handlers` stores deferred operations.

`handler_listeners` associates handlers with notification topics.

`task_handler_notifications` describes which tasks are configured to notify particular handlers.

`handler_notification_events` records actual notifications.

`handler_execution_results` maintains one execution record per host execution and handler.

The notification count makes repeated notifications observable without requiring repeated handler execution.

### 12.7 Automation Run Management

`automation_runs` stores playbook execution records.

`host_run_results` tracks the outcome of each managed host.

`task_execution_results` stores individual task outcomes.

The database enforces relationships through primary keys and foreign keys.

Check constraints prevent inconsistent task-status and change-flag combinations.

The task-result trigger maintains status consistency and completion timestamps.

### 12.8 Stored Functions and Procedures

| Database object | Responsibility |
|---|---|
| `resolve_host_variables()` | Resolve effective host variables |
| `validate_application_variables()` | Validate required application configuration |
| `start_automation_run()` | Create an execution and host records |
| `record_task_execution()` | Record an individual task result |
| `notify_handler()` | Record and queue a handler notification |
| `mark_handler_executed()` | Complete a pending handler |
| `finalize_automation_run()` | Calculate the final execution status |

The stored procedures use database transactions and integrity checks to maintain consistent execution records.

### 12.9 Reporting

`automation_execution_report` provides a host-level view of completed and running executions.

It aggregates:

- Total executed tasks.
- Changed tasks.
- Successful tasks.
- Skipped tasks.
- Failed tasks.

`pending_handler_report` identifies handlers awaiting execution.

Additional queries investigate failed operations and compare task outcomes.

### 12.10 Database Security

The schema should be deployed with restricted application roles.

Production access should follow least-privilege principles.

Recommended controls within the database deployment include:

- Restricting direct modification of execution records.
- Granting execution procedures only to authorized roles.
- Protecting sensitive JSONB values.
- Encrypting connections.
- Auditing changes to automation definitions.
- Applying retention policies to historical execution data.

The `is_secret` field does not encrypt variable values. Secret storage and retrieval require separate security controls.

## 13. Idempotency and Operational Reliability

Idempotency is central to configuration management.

Ansible modules are designed to describe and enforce desired state instead of blindly repeating operations.

For example, a directory task should not report a change every time it runs when the directory already exists with the required properties.

A template task should not rewrite an identical file unnecessarily.

A service restart should not occur when no relevant change has taken place.

The distinction between `ok` and `changed` is therefore operationally significant.

| Status | Meaning |
|---|---|
| OK | Desired state already exists |
| Changed | The managed state was modified |
| Skipped | A condition prevented execution |
| Failed | The operation could not complete |

Incorrect change reporting can trigger unnecessary handlers and disrupt production systems.

## 14. Production Considerations

### Configuration Integrity

Validate variables before executing destructive operations.

Use explicit variable names and avoid ambiguous overrides.

Maintain consistent configuration across development, staging, and production inventories.

### Template Safety

Validate generated files before replacing active configuration.

Use restrictive file permissions for sensitive material.

Avoid exposing credentials in logs and debugging output.

### Handler Reliability

Restart services only after relevant changes.

Use configuration-validation commands before restarting critical services.

Separate restart and reload behavior when the underlying service supports both.

### Conditional Accuracy

Use conditions to control task eligibility rather than to conceal configuration errors.

Validate variable types and values independently.

Ensure that skipped tasks are visible in execution reports.

### Failure Management

Distinguish host-level failures from playbook-level failures.

Record the task that failed and its execution message.

Avoid treating partial execution success as complete infrastructure convergence.

### Performance

Group hosts logically.

Use controlled parallel execution.

Avoid unnecessary remote commands.

Use fact caching where appropriate.

Keep templates and variable structures maintainable.

For large inventories, monitor connection overhead, remote execution time, and task-level change rates.

## 15. Limitations of the Educational Implementations

The five implementations are complementary domain models rather than complete replacements for the Ansible execution engine.

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Variable resolution | Yes | Yes | Typed configuration | Yes | SQL function |
| Conditional evaluation | Yes | Yes | Yes | Yes | Stored expression |
| Template rendering | Basic interpolation | Basic interpolation | Direct configuration construction | Basic interpolation | Stores template |
| Handler notifications | Yes | Event-driven | Yes | Yes | Persistent records |
| Handler deduplication | Yes | Yes | Yes | Yes | Unique records |
| Host state | Dictionaries and sets | Maps and sets | STL containers | Collections | Relational tables |
| Async execution | No | Yes | No | No | Transactional operations |
| Full Jinja2 support | No | No | No | No | No |
| Native Ansible execution | No | No | No | No | No |

The simplified template renderers do not reproduce Jinja2 filters, tests, macros, inheritance, or complete expression evaluation.

The variable resolvers demonstrate selected precedence rules rather than the entire Ansible precedence hierarchy.

The in-memory implementations simulate configuration state and do not connect to real managed hosts.

The SQL implementation records automation definitions and outcomes but does not execute remote Ansible modules.

These distinctions are important when interpreting the programs as technical learning artifacts.

## 16. Execution and File Organization

The six independent deliverables are intended to be stored separately.

| File | Implementation |
|---|---|
| `ansible_automation.py` | Python automation simulator |
| `ansible_automation.js` | Node.js event-driven simulator |
| `ansible_automation.cpp` | C++17 configuration-management engine |
| `AnsibleAutomation.java` | Java 17 enterprise execution model |
| `ansible_automation.sql` | PostgreSQL automation database |
| `README.md` | Technical documentation |

Runtime requirements:

| Implementation | Requirement |
|---|---|
| Python | Python 3.10+ |
| JavaScript | Node.js 18+ |
| C++ | C++17-compatible compiler |
| Java | JDK 17+ |
| PostgreSQL | PostgreSQL 14+ |

The implementations demonstrate how variables establish desired configuration, templates translate configuration into files, conditionals govern task execution, and handlers respond to actual changes.

Together, these mechanisms provide the foundation for repeatable, controlled, and auditable infrastructure automation.

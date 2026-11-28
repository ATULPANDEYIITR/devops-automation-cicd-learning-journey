import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.BiPredicate;

public class AnsibleRoles {

    enum TaskStatus {
        OK,
        CHANGED,
        FAILED,
        SKIPPED
    }

    enum ExecutionMode {
        NORMAL,
        CHECK
    }

    static class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static class DependencyException extends RuntimeException {
        DependencyException(String message) {
            super(message);
        }
    }

    static class TaskException extends RuntimeException {
        TaskException(String message) {
            super(message);
        }
    }

    record ActionResult(boolean changed, String message) {
        ActionResult {
            Objects.requireNonNull(message);
        }
    }

    record ExecutionRecord(
        String id,
        Instant timestamp,
        String host,
        String role,
        String task,
        TaskStatus status,
        String message
    ) {}

    @FunctionalInterface
    interface TaskAction {
        ActionResult execute(Host host, Variables variables);
    }

    @FunctionalInterface
    interface HandlerAction {
        ActionResult execute(Host host, Variables variables);
    }

    static class Variables {
        private final Map<String, String> values;

        Variables(Map<String, String> source) {
            this.values = new LinkedHashMap<>(source);
        }

        String get(String key) {
            return values.get(key);
        }

        String getOrDefault(String key, String fallback) {
            return values.getOrDefault(key, fallback);
        }

        boolean getBoolean(String key, boolean fallback) {
            String value = values.get(key);

            if (value == null) return fallback;

            if (value.equalsIgnoreCase("true")) return true;
            if (value.equalsIgnoreCase("false")) return false;

            throw new ConfigurationException(
                "Invalid boolean variable: " + key
            );
        }

        Map<String, String> asMap() {
            return Collections.unmodifiableMap(values);
        }
    }

    static class Host {
        final String name;
        final Map<String, String> inventoryVariables;

        final Set<String> packages = new LinkedHashSet<>();
        final Map<String, String> services = new HashMap<>();
        final Map<String, String> files = new HashMap<>();
        final Map<String, Integer> restartCounts = new HashMap<>();

        boolean failed;

        Host(String name, Map<String, String> variables) {
            if (
                name == null ||
                !name.matches("[a-zA-Z0-9_-]+")
            ) {
                throw new ConfigurationException(
                    "Invalid host name."
                );
            }

            this.name = name;
            this.inventoryVariables = new HashMap<>(variables);
        }

        Map<String, Object> snapshot() {
            Map<String, Object> result = new LinkedHashMap<>();

            result.put("name", name);
            result.put("packages", List.copyOf(packages));
            result.put("services", Map.copyOf(services));
            result.put("files", Map.copyOf(files));
            result.put("restartCounts", Map.copyOf(restartCounts));
            result.put("failed", failed);

            return Collections.unmodifiableMap(result);
        }
    }

    static class Task {
        final String name;
        final TaskAction action;
        final Set<String> tags;
        final List<String> notifications;
        final BiPredicate<Host, Variables> condition;
        final boolean become;

        Task(
            String name,
            TaskAction action,
            Collection<String> tags,
            Collection<String> notifications,
            BiPredicate<Host, Variables> condition,
            boolean become
        ) {
            if (
                name == null ||
                name.isBlank() ||
                action == null
            ) {
                throw new ConfigurationException(
                    "Task requires a name and action."
                );
            }

            this.name = name;
            this.action = action;
            this.tags = Set.copyOf(tags);
            this.notifications = List.copyOf(notifications);
            this.condition = condition;
            this.become = become;
        }
    }

    record Handler(
        String name,
        HandlerAction action
    ) {
        Handler {
            if (
                name == null ||
                name.isBlank() ||
                action == null
            ) {
                throw new ConfigurationException(
                    "Invalid handler."
                );
            }
        }
    }

    static class Role {
        final String name;
        final Map<String, String> defaults;
        final Map<String, String> variables;
        final List<String> dependencies;
        final List<Task> tasks;
        final Map<String, Handler> handlers;
        final Map<String, String> metadata;

        Role(
            String name,
            Map<String, String> defaults,
            Map<String, String> variables,
            List<String> dependencies,
            List<Task> tasks,
            Map<String, Handler> handlers,
            Map<String, String> metadata
        ) {
            if (
                name == null ||
                !name.matches("[a-zA-Z0-9_-]+")
            ) {
                throw new ConfigurationException(
                    "Invalid role name."
                );
            }

            this.name = name;
            this.defaults = Map.copyOf(defaults);
            this.variables = Map.copyOf(variables);
            this.dependencies = List.copyOf(dependencies);
            this.tasks = List.copyOf(tasks);
            this.handlers = Map.copyOf(handlers);
            this.metadata = Map.copyOf(metadata);

            validate();
        }

        private void validate() {
            for (String dependency : dependencies) {
                if (name.equals(dependency)) {
                    throw new DependencyException(
                        "Self-dependent role: " + name
                    );
                }
            }

            for (Task task : tasks) {
                for (String notification : task.notifications) {
                    if (!handlers.containsKey(notification)) {
                        throw new ConfigurationException(
                            "Unknown handler: " + notification
                        );
                    }
                }
            }
        }
    }

    static class RoleRegistry {
        private final Map<String, Role> roles =
            new LinkedHashMap<>();

        void register(Role role) {
            if (roles.putIfAbsent(role.name, role) != null) {
                throw new ConfigurationException(
                    "Duplicate role: " + role.name
                );
            }
        }

        List<Role> resolve(List<String> requested) {
            List<Role> ordered = new ArrayList<>();

            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();

            for (String name : requested) {
                visit(name, visited, active, ordered);
            }

            return List.copyOf(ordered);
        }

        private void visit(
            String name,
            Set<String> visited,
            Set<String> active,
            List<Role> ordered
        ) {
            Role role = roles.get(name);

            if (role == null) {
                throw new DependencyException(
                    "Missing role: " + name
                );
            }

            if (active.contains(name)) {
                throw new DependencyException(
                    "Circular dependency: " + name
                );
            }

            if (visited.contains(name)) return;

            active.add(name);

            for (String dependency : role.dependencies) {
                visit(
                    dependency,
                    visited,
                    active,
                    ordered
                );
            }

            active.remove(name);
            visited.add(name);
            ordered.add(role);
        }
    }

    static class VariableResolver {

        static Variables resolve(
            Role role,
            Host host,
            Map<String, String> playVariables,
            Map<String, String> extraVariables
        ) {
            Map<String, String> resolved = new LinkedHashMap<>();

            resolved.putAll(role.defaults);
            resolved.putAll(host.inventoryVariables);
            resolved.putAll(role.variables);
            resolved.putAll(playVariables);
            resolved.putAll(extraVariables);

            return new Variables(resolved);
        }
    }

    static class PendingNotification {
        final Host host;
        final Role role;
        final String handler;

        PendingNotification(
            Host host,
            Role role,
            String handler
        ) {
            this.host = host;
            this.role = role;
            this.handler = handler;
        }
    }

    static class RoleExecutionService {

        private final RoleRegistry registry;
        private final ExecutionMode mode;
        private final Set<String> selectedTags;

        private final Map<String, String> playVariables;
        private final Map<String, String> extraVariables;

        private final List<ExecutionRecord> records =
            new ArrayList<>();

        private final List<PendingNotification> pending =
            new ArrayList<>();

        RoleExecutionService(
            RoleRegistry registry,
            ExecutionMode mode,
            Set<String> selectedTags,
            Map<String, String> playVariables,
            Map<String, String> extraVariables
        ) {
            this.registry = registry;
            this.mode = mode;
            this.selectedTags = Set.copyOf(selectedTags);
            this.playVariables = Map.copyOf(playVariables);
            this.extraVariables = Map.copyOf(extraVariables);
        }

        private void record(
            Host host,
            Role role,
            String task,
            TaskStatus status,
            String message
        ) {
            records.add(new ExecutionRecord(
                UUID.randomUUID().toString(),
                Instant.now(),
                host.name,
                role.name,
                task,
                status,
                message
            ));

            System.out.printf(
                "[%s] %s | %s | %s | %s%n",
                status,
                host.name,
                role.name,
                task,
                message
            );
        }

        private void executeTask(
            Host host,
            Role role,
            Task task,
            Variables variables
        ) {
            if (host.failed) return;

            if (!selectedTags.isEmpty()) {
                Set<String> matching = new HashSet<>(
                    task.tags
                );

                matching.retainAll(selectedTags);

                if (
                    matching.isEmpty() &&
                    !task.tags.contains("always")
                ) {
                    record(
                        host,
                        role,
                        task.name,
                        TaskStatus.SKIPPED,
                        "Tag mismatch."
                    );
                    return;
                }
            }

            try {
                if (!task.condition.test(host, variables)) {
                    record(
                        host,
                        role,
                        task.name,
                        TaskStatus.SKIPPED,
                        "Condition evaluated to false."
                    );
                    return;
                }

                if (mode == ExecutionMode.CHECK) {
                    record(
                        host,
                        role,
                        task.name,
                        TaskStatus.OK,
                        "Check mode: no changes made."
                    );
                    return;
                }

                ActionResult outcome = task.action.execute(
                    host,
                    variables
                );

                record(
                    host,
                    role,
                    task.name,
                    outcome.changed()
                        ? TaskStatus.CHANGED
                        : TaskStatus.OK,
                    outcome.message()
                );

                if (outcome.changed()) {
                    for (String handler : task.notifications) {
                        pending.add(
                            new PendingNotification(
                                host,
                                role,
                                handler
                            )
                        );
                    }
                }

            } catch (RuntimeException exception) {
                host.failed = true;

                record(
                    host,
                    role,
                    task.name,
                    TaskStatus.FAILED,
                    exception.getMessage()
                );
            }
        }

        private void flushHandlers() {
            Set<String> executed = new HashSet<>();

            for (PendingNotification notification : pending) {
                Host host = notification.host;
                Role role = notification.role;

                if (host.failed) continue;

                String key = host.name + ":" +
                    role.name + ":" +
                    notification.handler;

                if (!executed.add(key)) continue;

                try {
                    Handler handler = role.handlers.get(
                        notification.handler
                    );

                    if (handler == null) {
                        throw new ConfigurationException(
                            "Missing handler."
                        );
                    }

                    Variables variables = VariableResolver.resolve(
                        role,
                        host,
                        playVariables,
                        extraVariables
                    );

                    ActionResult outcome = handler.action().execute(
                        host,
                        variables
                    );

                    record(
                        host,
                        role,
                        "handler:" + handler.name(),
                        outcome.changed()
                            ? TaskStatus.CHANGED
                            : TaskStatus.OK,
                        outcome.message()
                    );

                } catch (RuntimeException exception) {
                    host.failed = true;

                    record(
                        host,
                        role,
                        "handler:" + notification.handler,
                        TaskStatus.FAILED,
                        exception.getMessage()
                    );
                }
            }

            pending.clear();
        }

        List<ExecutionRecord> execute(
            List<Host> hosts,
            List<String> requestedRoles
        ) {
            if (hosts.isEmpty()) {
                throw new ConfigurationException(
                    "Inventory cannot be empty."
                );
            }

            List<Role> ordered = registry.resolve(
                requestedRoles
            );

            for (Role role : ordered) {
                for (Host host : hosts) {
                    if (host.failed) continue;

                    Variables variables =
                        VariableResolver.resolve(
                            role,
                            host,
                            playVariables,
                            extraVariables
                        );

                    for (Task task : role.tasks) {
                        executeTask(
                            host,
                            role,
                            task,
                            variables
                        );
                    }
                }

                flushHandlers();
            }

            return List.copyOf(records);
        }

        Map<TaskStatus, Long> report() {
            Map<TaskStatus, Long> result =
                new EnumMap<>(TaskStatus.class);

            for (TaskStatus status : TaskStatus.values()) {
                result.put(status, 0L);
            }

            for (ExecutionRecord record : records) {
                result.merge(
                    record.status(),
                    1L,
                    Long::sum
                );
            }

            return Collections.unmodifiableMap(result);
        }
    }

    // Reusable infrastructure actions.

    static TaskAction installPackage(String packageName) {
        return (host, variables) -> {
            if (
                packageName == null ||
                !packageName.matches("[a-zA-Z0-9.+_-]+")
            ) {
                throw new TaskException(
                    "Invalid package name."
                );
            }

            if (!host.packages.add(packageName)) {
                return new ActionResult(
                    false,
                    packageName + " already installed."
                );
            }

            return new ActionResult(
                true,
                "Installed " + packageName
            );
        };
    }

    static TaskAction ensureService(String serviceName) {
        return (host, variables) -> {
            if (
                "running".equals(
                    host.services.get(serviceName)
                )
            ) {
                return new ActionResult(
                    false,
                    serviceName + " already running."
                );
            }

            host.services.put(serviceName, "running");

            return new ActionResult(
                true,
                "Started " + serviceName
            );
        };
    }

    static TaskAction deployConfiguration(
        String path,
        String variableName
    ) {
        return (host, variables) -> {
            if (!path.startsWith("/etc/")) {
                throw new TaskException(
                    "Configuration must be under /etc/."
                );
            }

            String content = variables.get(variableName);

            if (content == null || content.isBlank()) {
                throw new TaskException(
                    "Missing configuration variable: " +
                    variableName
                );
            }

            if (content.equals(host.files.get(path))) {
                return new ActionResult(
                    false,
                    "Configuration already current."
                );
            }

            host.files.put(path, content);

            return new ActionResult(
                true,
                "Deployed " + path
            );
        };
    }

    static HandlerAction restartService(String serviceName) {
        return (host, variables) -> {
            if (
                !"running".equals(
                    host.services.get(serviceName)
                )
            ) {
                throw new TaskException(
                    "Cannot restart inactive service: " +
                    serviceName
                );
            }

            host.restartCounts.merge(
                serviceName,
                1,
                Integer::sum
            );

            return new ActionResult(
                true,
                "Restarted " + serviceName
            );
        };
    }

    static Role createBaseRole() {
        Task installCurl = new Task(
            "Install curl",
            installPackage("curl"),
            Set.of("base", "packages"),
            List.of(),
            (host, variables) -> true,
            true
        );

        return new Role(
            "base",
            Map.of("timezone", "UTC"),
            Map.of(),
            List.of(),
            List.of(installCurl),
            Map.of(),
            Map.of(
                "version", "1.0.0",
                "description", "Common infrastructure configuration"
            )
        );
    }

    static Role createWebRole() {
        Handler restartNginx = new Handler(
            "restart nginx",
            restartService("nginx")
        );

        Task installNginx = new Task(
            "Install nginx",
            installPackage("nginx"),
            Set.of("web", "packages"),
            List.of(),
            (host, variables) -> true,
            true
        );

        Task configureNginx = new Task(
            "Deploy nginx configuration",
            deployConfiguration(
                "/etc/nginx/nginx.conf",
                "nginx_config"
            ),
            Set.of("web", "configuration"),
            List.of("restart nginx"),
            (host, variables) -> true,
            true
        );

        Task startNginx = new Task(
            "Start nginx",
            ensureService("nginx"),
            Set.of("web", "services"),
            List.of(),
            (host, variables) -> true,
            true
        );

        return new Role(
            "webserver",
            Map.of(
                "nginx_config",
                "server { listen 8080; server_name app.internal; }"
            ),
            Map.of(),
            List.of("base"),
            List.of(
                installNginx,
                configureNginx,
                startNginx
            ),
            Map.of("restart nginx", restartNginx),
            Map.of(
                "version", "2.0.0",
                "description", "Reusable nginx role"
            )
        );
    }

    static Role createMonitoringRole() {
        Task installExporter = new Task(
            "Install node exporter",
            installPackage("node-exporter"),
            Set.of("monitoring"),
            List.of(),
            (host, variables) ->
                variables.getBoolean(
                    "monitoring_enabled",
                    true
                ),
            true
        );

        return new Role(
            "monitoring",
            Map.of("monitoring_enabled", "true"),
            Map.of(),
            List.of(),
            List.of(installExporter),
            Map.of(),
            Map.of("version", "1.0.0")
        );
    }

    public static void main(String[] args) {
        RoleRegistry registry = new RoleRegistry();

        registry.register(createBaseRole());
        registry.register(createWebRole());
        registry.register(createMonitoringRole());

        List<Host> inventory = List.of(
            new Host(
                "web-01",
                Map.of("environment", "production")
            ),
            new Host(
                "web-02",
                Map.of(
                    "environment", "staging",
                    "monitoring_enabled", "false"
                )
            )
        );

        Map<String, String> playVariables = Map.of(
            "nginx_config",
            "server { listen 8080; server_name production.internal; }"
        );

        RoleExecutionService executor =
            new RoleExecutionService(
                registry,
                ExecutionMode.NORMAL,
                Set.of(),
                playVariables,
                Map.of()
            );

        List<ExecutionRecord> results = executor.execute(
            inventory,
            List.of("webserver", "monitoring")
        );

        System.out.println("\nExecution statistics:");

        executor.report().forEach(
            (status, count) ->
                System.out.println(status + ": " + count)
        );

        System.out.println("\nInfrastructure state:");

        for (Host host : inventory) {
            System.out.println(host.snapshot());
        }

        // Re-running the same desired state must not change resources.
        RoleExecutionService secondRun =
            new RoleExecutionService(
                registry,
                ExecutionMode.NORMAL,
                Set.of(),
                playVariables,
                Map.of()
            );

        List<ExecutionRecord> repeated = secondRun.execute(
            inventory,
            List.of("webserver", "monitoring")
        );

        if (
            repeated.stream().anyMatch(
                record -> record.status() == TaskStatus.CHANGED
            )
        ) {
            throw new AssertionError(
                "Idempotence verification failed."
            );
        }

        System.out.println("\nIdempotence verification passed.");

        // Check mode must not mutate infrastructure.
        Map<String, Object> before = inventory.get(0).snapshot();

        RoleExecutionService checkExecutor =
            new RoleExecutionService(
                registry,
                ExecutionMode.CHECK,
                Set.of(),
                playVariables,
                Map.of()
            );

        checkExecutor.execute(
            inventory,
            List.of("webserver")
        );

        Map<String, Object> after = inventory.get(0).snapshot();

        if (!before.equals(after)) {
            throw new AssertionError(
                "Check mode modified infrastructure."
            );
        }

        System.out.println("Check mode verification passed.");

        System.out.println(
            "\nCompleted records: " + results.size()
        );
    }
}

import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import java.util.regex.Pattern;

/**
 * Ansible Fundamentals: Enterprise Configuration Management
 *
 * Demonstrates inventory modeling, modules, playbooks,
 * variables, task execution, idempotency, handlers,
 * check mode, and execution reporting.
 *
 * Java 17, standard library only.
 */
public class AnsibleFundamentals {

    enum Status {
        OK,
        CHANGED,
        FAILED,
        SKIPPED
    }

    enum DesiredState {
        PRESENT,
        ABSENT,
        STARTED,
        STOPPED
    }

    static class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static class TaskException extends RuntimeException {
        TaskException(String message) {
            super(message);
        }
    }

    record TaskResult(
        String hostname,
        String taskName,
        Status status,
        String message
    ) {}

    record ExecutionReport(
        Map<String, Map<Status, Long>> hostResults
    ) {}

    static final Pattern IDENTIFIER =
        Pattern.compile("[A-Za-z0-9_.-]+");

    static void validateIdentifier(String value, String label) {
        if (
            value == null ||
            !IDENTIFIER.matcher(value).matches()
        ) {
            throw new ConfigurationException(
                "Invalid " + label + ": " + value
            );
        }
    }

    static final class Host {
        private final String name;
        private final String address;
        private final int port;
        private final String username;

        private final Map<String, String> variables;
        private final Set<String> packages = new HashSet<>();
        private final Map<String, String> services =
            new HashMap<>();
        private final Map<String, String> files =
            new HashMap<>();

        private boolean reachable = true;

        Host(
            String name,
            String address,
            int port,
            String username,
            Map<String, String> variables
        ) {
            validateIdentifier(name, "hostname");

            if (address == null || address.isBlank()) {
                throw new ConfigurationException(
                    "Host address is required."
                );
            }

            if (port < 1 || port > 65535) {
                throw new ConfigurationException(
                    "Invalid SSH port."
                );
            }

            this.name = name;
            this.address = address;
            this.port = port;
            this.username = username;
            this.variables = new HashMap<>(variables);
        }

        String getName() {
            return name;
        }

        void setReachable(boolean reachable) {
            this.reachable = reachable;
        }
    }

    static final class Inventory {
        private final Map<String, Host> hosts =
            new TreeMap<>();

        private final Map<String, Set<String>> groups =
            new TreeMap<>();

        private final Map<String, Map<String, String>>
            groupVariables = new HashMap<>();

        void addHost(Host host, String... groupNames) {
            if (hosts.containsKey(host.name)) {
                throw new ConfigurationException(
                    "Duplicate host: " + host.name
                );
            }

            hosts.put(host.name, host);

            for (String group : groupNames) {
                validateIdentifier(group, "group");

                groups.computeIfAbsent(
                    group,
                    key -> new TreeSet<>()
                ).add(host.name);
            }
        }

        void setGroupVariables(
            String group,
            Map<String, String> variables
        ) {
            if (!groups.containsKey(group)) {
                throw new ConfigurationException(
                    "Unknown group: " + group
                );
            }

            groupVariables.put(
                group,
                Map.copyOf(variables)
            );
        }

        List<Host> select(String pattern) {
            Set<String> selected;

            if (pattern.equals("all")) {
                selected = hosts.keySet();
            } else if (groups.containsKey(pattern)) {
                selected = groups.get(pattern);
            } else if (hosts.containsKey(pattern)) {
                selected = Set.of(pattern);
            } else {
                throw new ConfigurationException(
                    "Inventory pattern not found: " + pattern
                );
            }

            return selected.stream()
                .sorted()
                .map(hosts::get)
                .toList();
        }

        Map<String, String> effectiveVariables(Host host) {
            Map<String, String> result = new HashMap<>();

            for (var entry : groups.entrySet()) {
                if (entry.getValue().contains(host.name)) {
                    result.putAll(
                        groupVariables.getOrDefault(
                            entry.getKey(),
                            Map.of()
                        )
                    );
                }
            }

            // Host-level variables have higher precedence.
            result.putAll(host.variables);

            return result;
        }
    }

    interface ConfigurationModule {
        TaskResult execute(
            Host host,
            String taskName,
            Map<String, String> arguments,
            boolean checkMode
        );
    }

    static final class PackageModule
        implements ConfigurationModule {

        @Override
        public TaskResult execute(
            Host host,
            String taskName,
            Map<String, String> args,
            boolean checkMode
        ) {
            String name = required(args, "name");
            String state = args.getOrDefault(
                "state", "present"
            );

            validateIdentifier(name, "package");

            if (
                !state.equals("present") &&
                !state.equals("absent")
            ) {
                throw new TaskException(
                    "Invalid package state."
                );
            }

            boolean exists = host.packages.contains(name);

            if (
                (state.equals("present") && exists) ||
                (state.equals("absent") && !exists)
            ) {
                return result(
                    host,
                    taskName,
                    Status.OK,
                    "Package already compliant: " + name
                );
            }

            if (!checkMode) {
                if (state.equals("present")) {
                    host.packages.add(name);
                } else {
                    host.packages.remove(name);
                }
            }

            return result(
                host,
                taskName,
                Status.CHANGED,
                "Package " + name + ": " + state
            );
        }
    }

    static final class ServiceModule
        implements ConfigurationModule {

        @Override
        public TaskResult execute(
            Host host,
            String taskName,
            Map<String, String> args,
            boolean checkMode
        ) {
            String name = required(args, "name");
            String state = args.getOrDefault(
                "state", "started"
            );
            String enabled = args.getOrDefault(
                "enabled", "true"
            );

            validateIdentifier(name, "service");

            if (
                !Set.of("started", "stopped").contains(state)
            ) {
                throw new TaskException(
                    "Invalid service state."
                );
            }

            if (
                !Set.of("true", "false").contains(enabled)
            ) {
                throw new TaskException(
                    "Invalid enabled value."
                );
            }

            String desired = state + ":" + enabled;

            if (desired.equals(host.services.get(name))) {
                return result(
                    host,
                    taskName,
                    Status.OK,
                    "Service already compliant: " + name
                );
            }

            if (!checkMode) {
                host.services.put(name, desired);
            }

            return result(
                host,
                taskName,
                Status.CHANGED,
                "Service " + name + ": " + state
            );
        }
    }

    static final class FileModule
        implements ConfigurationModule {

        @Override
        public TaskResult execute(
            Host host,
            String taskName,
            Map<String, String> args,
            boolean checkMode
        ) {
            String path = required(args, "path");
            String state = args.getOrDefault(
                "state", "file"
            );
            String mode = args.getOrDefault(
                "mode", "0644"
            );

            if (
                !path.startsWith("/") ||
                Arrays.asList(path.split("/")).contains("..")
            ) {
                throw new TaskException(
                    "A safe absolute path is required."
                );
            }

            if (
                !Set.of("file", "directory", "absent")
                    .contains(state)
            ) {
                throw new TaskException(
                    "Invalid file state."
                );
            }

            if (!mode.matches("[0-7]{3,4}")) {
                throw new TaskException(
                    "Invalid permission mode."
                );
            }

            String desired = state + ":" + mode;
            String current = host.files.get(path);

            if (
                state.equals("absent") && current == null ||
                desired.equals(current)
            ) {
                return result(
                    host,
                    taskName,
                    Status.OK,
                    "File already compliant: " + path
                );
            }

            if (!checkMode) {
                if (state.equals("absent")) {
                    host.files.remove(path);
                } else {
                    host.files.put(path, desired);
                }
            }

            return result(
                host,
                taskName,
                Status.CHANGED,
                "File evaluated: " + path
            );
        }
    }

    static final class CommandModule
        implements ConfigurationModule {

        private final Map<String, String> allowedCommands =
            Map.of(
                "check_http", "HTTP configuration verified",
                "check_disk", "Disk capacity verified",
                "check_service", "Service availability verified"
            );

        @Override
        public TaskResult execute(
            Host host,
            String taskName,
            Map<String, String> args,
            boolean checkMode
        ) {
            String command = required(args, "command");

            if (!allowedCommands.containsKey(command)) {
                throw new TaskException(
                    "Command is not permitted."
                );
            }

            return result(
                host,
                taskName,
                Status.OK,
                allowedCommands.get(command)
            );
        }
    }

    static final class ModuleRegistry {
        private final Map<String, ConfigurationModule>
            modules = new HashMap<>();

        ModuleRegistry() {
            register("package", new PackageModule());
            register("service", new ServiceModule());
            register("file", new FileModule());
            register("command", new CommandModule());
        }

        void register(
            String name,
            ConfigurationModule module
        ) {
            if (modules.putIfAbsent(name, module) != null) {
                throw new ConfigurationException(
                    "Duplicate module: " + name
                );
            }
        }

        TaskResult execute(
            String module,
            Host host,
            String task,
            Map<String, String> args,
            boolean checkMode
        ) {
            ConfigurationModule selected = modules.get(module);

            if (selected == null) {
                throw new TaskException(
                    "Unknown module: " + module
                );
            }

            return selected.execute(
                host,
                task,
                args,
                checkMode
            );
        }
    }

    record Task(
        String name,
        String module,
        Map<String, String> arguments,
        List<String> notify,
        boolean condition,
        boolean ignoreErrors
    ) {
        Task {
            if (name == null || name.isBlank()) {
                throw new ConfigurationException(
                    "Task name is required."
                );
            }

            arguments = Map.copyOf(arguments);
            notify = List.copyOf(notify);
        }

        static Task of(
            String name,
            String module,
            Map<String, String> arguments
        ) {
            return new Task(
                name,
                module,
                arguments,
                List.of(),
                true,
                false
            );
        }
    }

    record Play(
        String name,
        String hosts,
        List<Task> tasks,
        Map<String, String> variables,
        Map<String, Task> handlers
    ) {
        Play {
            if (name == null || name.isBlank()) {
                throw new ConfigurationException(
                    "Play name is required."
                );
            }

            if (tasks == null || tasks.isEmpty()) {
                throw new ConfigurationException(
                    "Play must contain tasks."
                );
            }

            tasks = List.copyOf(tasks);
            variables = Map.copyOf(variables);
            handlers = Map.copyOf(handlers);
        }
    }

    static final class PlaybookEngine {
        private final Inventory inventory;
        private final ModuleRegistry registry =
            new ModuleRegistry();

        private final List<TaskResult> results =
            new CopyOnWriteArrayList<>();

        PlaybookEngine(Inventory inventory) {
            this.inventory = inventory;
        }

        private Map<String, String> resolveArguments(
            Map<String, String> arguments,
            Map<String, String> variables
        ) {
            Map<String, String> resolved =
                new HashMap<>(arguments);

            Pattern variablePattern = Pattern.compile(
                "^\\{\\{\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*}}$"
            );

            resolved.replaceAll((key, value) -> {
                var matcher = variablePattern.matcher(value);

                if (!matcher.matches()) {
                    return value;
                }

                String variable = matcher.group(1);

                if (!variables.containsKey(variable)) {
                    throw new TaskException(
                        "Undefined variable: " + variable
                    );
                }

                return variables.get(variable);
            });

            return resolved;
        }

        private void record(TaskResult result) {
            results.add(result);

            System.out.printf(
                "%-12s %-25s %-10s %s%n",
                result.hostname(),
                result.taskName(),
                result.status().name().toLowerCase(),
                result.message()
            );
        }

        void executePlay(Play play, boolean checkMode) {
            List<Host> hosts = inventory.select(play.hosts());

            for (Host host : hosts) {
                if (!host.reachable) {
                    record(new TaskResult(
                        host.name,
                        "connection",
                        Status.FAILED,
                        "Host unreachable"
                    ));

                    continue;
                }

                Map<String, String> variables =
                    inventory.effectiveVariables(host);

                variables.putAll(play.variables());

                Set<String> notified = new LinkedHashSet<>();
                boolean failed = false;

                for (Task task : play.tasks()) {
                    if (failed) {
                        break;
                    }

                    if (!task.condition()) {
                        record(new TaskResult(
                            host.name,
                            task.name(),
                            Status.SKIPPED,
                            "Condition evaluated to false"
                        ));

                        continue;
                    }

                    try {
                        Map<String, String> arguments =
                            resolveArguments(
                                task.arguments(),
                                variables
                            );

                        TaskResult result = registry.execute(
                            task.module(),
                            host,
                            task.name(),
                            arguments,
                            checkMode
                        );

                        record(result);

                        if (result.status() == Status.CHANGED) {
                            notified.addAll(task.notify());
                        }
                    } catch (RuntimeException error) {
                        record(new TaskResult(
                            host.name,
                            task.name(),
                            Status.FAILED,
                            error.getMessage()
                        ));

                        if (!task.ignoreErrors()) {
                            failed = true;
                        }
                    }
                }

                if (!failed) {
                    for (String handlerName : notified) {
                        Task handler = play.handlers().get(
                            handlerName
                        );

                        if (handler == null) {
                            record(new TaskResult(
                                host.name,
                                "handler:" + handlerName,
                                Status.FAILED,
                                "Handler not defined"
                            ));

                            continue;
                        }

                        try {
                            Map<String, String> arguments =
                                resolveArguments(
                                    handler.arguments(),
                                    variables
                                );

                            TaskResult result = registry.execute(
                                handler.module(),
                                host,
                                "handler:" + handlerName,
                                arguments,
                                checkMode
                            );

                            record(result);
                        } catch (RuntimeException error) {
                            record(new TaskResult(
                                host.name,
                                "handler:" + handlerName,
                                Status.FAILED,
                                error.getMessage()
                            ));
                        }
                    }
                }
            }
        }

        ExecutionReport report() {
            Map<String, Map<Status, Long>> grouped =
                new TreeMap<>();

            for (TaskResult result : results) {
                grouped.computeIfAbsent(
                    result.hostname(),
                    key -> new EnumMap<>(Status.class)
                ).merge(
                    result.status(),
                    1L,
                    Long::sum
                );
            }

            Map<String, Map<Status, Long>> immutable =
                new TreeMap<>();

            grouped.forEach((host, counts) ->
                immutable.put(host, Map.copyOf(counts))
            );

            return new ExecutionReport(
                Map.copyOf(immutable)
            );
        }
    }

    static String required(
        Map<String, String> arguments,
        String key
    ) {
        String value = arguments.get(key);

        if (value == null || value.isBlank()) {
            throw new TaskException(
                "Required argument missing: " + key
            );
        }

        return value;
    }

    static TaskResult result(
        Host host,
        String task,
        Status status,
        String message
    ) {
        return new TaskResult(
            host.name,
            task,
            status,
            message
        );
    }

    static Map<String, String> args(String... pairs) {
        if (pairs.length % 2 != 0) {
            throw new IllegalArgumentException(
                "Arguments must be key-value pairs."
            );
        }

        Map<String, String> result = new HashMap<>();

        for (int i = 0; i < pairs.length; i += 2) {
            result.put(pairs[i], pairs[i + 1]);
        }

        return result;
    }

    static Inventory createInventory() {
        Inventory inventory = new Inventory();

        inventory.addHost(
            new Host(
                "web01",
                "192.168.10.11",
                22,
                "ansible",
                Map.of("environment", "production")
            ),
            "web"
        );

        inventory.addHost(
            new Host(
                "web02",
                "192.168.10.12",
                22,
                "ansible",
                Map.of("environment", "production")
            ),
            "web"
        );

        inventory.addHost(
            new Host(
                "db01",
                "192.168.10.21",
                22,
                "ansible",
                Map.of()
            ),
            "database"
        );

        inventory.setGroupVariables(
            "web",
            Map.of("package_name", "nginx")
        );

        inventory.setGroupVariables(
            "database",
            Map.of("package_name", "postgresql")
        );

        return inventory;
    }

    static List<Play> createPlaybooks() {
        Task installNginx = Task.of(
            "Install nginx",
            "package",
            args(
                "name", "{{ package_name }}",
                "state", "present"
            )
        );

        Task createDirectory = Task.of(
            "Create application directory",
            "file",
            args(
                "path", "/srv/application",
                "state", "directory",
                "mode", "0755"
            )
        );

        Task startNginx = new Task(
            "Start nginx",
            "service",
            args(
                "name", "nginx",
                "state", "started",
                "enabled", "true"
            ),
            List.of("reload_nginx"),
            true,
            false
        );

        Task validateHTTP = Task.of(
            "Validate HTTP configuration",
            "command",
            args("command", "check_http")
        );

        Task reloadHandler = Task.of(
            "Reload nginx",
            "service",
            args(
                "name", "nginx",
                "state", "started",
                "enabled", "true"
            )
        );

        Play webPlay = new Play(
            "Configure web infrastructure",
            "web",
            List.of(
                installNginx,
                createDirectory,
                startNginx,
                validateHTTP
            ),
            Map.of(),
            Map.of("reload_nginx", reloadHandler)
        );

        Play databasePlay = new Play(
            "Configure database infrastructure",
            "database",
            List.of(
                Task.of(
                    "Install PostgreSQL",
                    "package",
                    args(
                        "name", "{{ package_name }}",
                        "state", "present"
                    )
                ),
                Task.of(
                    "Start PostgreSQL",
                    "service",
                    args(
                        "name", "postgresql",
                        "state", "started",
                        "enabled", "true"
                    )
                )
            ),
            Map.of(),
            Map.of()
        );

        return List.of(webPlay, databasePlay);
    }

    public static void main(String[] arguments) {
        boolean checkMode = Arrays.asList(arguments)
            .contains("--check");

        try {
            Inventory inventory = createInventory();

            PlaybookEngine engine =
                new PlaybookEngine(inventory);

            System.out.println(
                "Ansible Fundamentals: Enterprise Configuration"
            );

            System.out.println(
                "Execution mode: " +
                (checkMode ? "CHECK" : "NORMAL")
            );

            for (Play play : createPlaybooks()) {
                engine.executePlay(play, checkMode);
            }

            System.out.println("\nExecution report:");

            engine.report().hostResults().forEach(
                (host, counts) -> {
                    System.out.println(host);

                    counts.forEach((status, count) ->
                        System.out.printf(
                            "  %-10s %d%n",
                            status.name().toLowerCase(),
                            count
                        )
                    );
                }
            );

        } catch (RuntimeException error) {
            System.err.println(
                "Execution failed: " + error.getMessage()
            );

            System.exit(1);
        }
    }
}

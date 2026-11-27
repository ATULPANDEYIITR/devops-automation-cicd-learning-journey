import java.util.ArrayList;
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
import java.util.function.Predicate;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/*
 * Ansible Automation: Enterprise Configuration Management.
 *
 * Enterprise-oriented execution model covering:
 * - Variable precedence.
 * - Immutable execution configurations.
 * - Host and group inventory.
 * - Conditional task execution.
 * - Template rendering.
 * - Idempotent state changes.
 * - Handler notification and deduplication.
 * - Execution phases.
 * - Validation and failure isolation.
 * - Structured operational reporting.
 */

public class AnsibleAutomation {

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum Status {
        OK,
        CHANGED,
        SKIPPED,
        FAILED
    }

    static class AutomationException extends RuntimeException {
        AutomationException(String message) {
            super(message);
        }
    }

    static class VariableException extends AutomationException {
        VariableException(String message) {
            super(message);
        }
    }

    static class TemplateException extends AutomationException {
        TemplateException(String message) {
            super(message);
        }
    }

    record TaskResult(
        String host,
        String task,
        Status status,
        String message
    ) {}

    static final class VariableResolver {

        private static final List<String> PRECEDENCE = List.of(
            "defaults",
            "inventory",
            "groupVars",
            "hostVars",
            "playVars",
            "taskVars",
            "extraVars"
        );

        private VariableResolver() {}

        static Map<String, Object> resolve(
            Map<String, Map<String, Object>> sources
        ) {
            Map<String, Object> resolved = new LinkedHashMap<>();

            for (String source : PRECEDENCE) {
                Map<String, Object> values =
                    sources.getOrDefault(source, Map.of());

                if (values == null) {
                    throw new VariableException(
                        "Null variable source: " + source
                    );
                }

                resolved.putAll(values);
            }

            return Collections.unmodifiableMap(
                new LinkedHashMap<>(resolved)
            );
        }

        static void require(
            Map<String, Object> variables,
            String... names
        ) {
            for (String name : names) {
                Object value = variables.get(name);

                if (value == null || value.toString().isBlank()) {
                    throw new VariableException(
                        "Missing required variable: " + name
                    );
                }
            }
        }
    }

    static final class Configuration {

        final String applicationName;
        final String applicationVersion;
        final String applicationDirectory;
        final String serviceName;
        final int applicationPort;
        final Environment environment;

        Configuration(Map<String, Object> variables) {
            VariableResolver.require(
                variables,
                "applicationName",
                "applicationVersion",
                "applicationDirectory",
                "serviceName",
                "environment"
            );

            applicationName =
                variables.get("applicationName").toString();

            applicationVersion =
                variables.get("applicationVersion").toString();

            applicationDirectory =
                variables.get("applicationDirectory").toString();

            serviceName =
                variables.get("serviceName").toString();

            try {
                applicationPort =
                    Integer.parseInt(
                        variables.get("applicationPort").toString()
                    );

                environment = Environment.valueOf(
                    variables.get("environment").toString()
                        .toUpperCase()
                );
            } catch (IllegalArgumentException exception) {
                throw new VariableException(
                    "Invalid port or environment"
                );
            }

            validate();
        }

        private void validate() {
            if (applicationName.isBlank() ||
                applicationVersion.isBlank() ||
                serviceName.isBlank()) {
                throw new VariableException(
                    "Application identifiers cannot be empty"
                );
            }

            if (applicationPort < 1 || applicationPort > 65535) {
                throw new VariableException(
                    "Port must be between 1 and 65535"
                );
            }

            if (!applicationDirectory.startsWith("/")) {
                throw new VariableException(
                    "Application directory must be absolute"
                );
            }
        }
    }

    static final class Host {

        final String name;
        final Set<String> groups;
        final Configuration configuration;

        final Set<String> directories = new HashSet<>();
        final Map<String, String> files = new HashMap<>();
        final Map<String, String> services = new HashMap<>();

        String deployedVersion;
        boolean failed;

        Host(
            String name,
            Set<String> groups,
            Configuration configuration
        ) {
            this.name = Objects.requireNonNull(name);
            this.groups = Set.copyOf(groups);
            this.configuration = configuration;
        }
    }

    @FunctionalInterface
    interface TaskAction {
        boolean execute(Host host) throws Exception;
    }

    @FunctionalInterface
    interface HandlerAction {
        boolean execute(Host host) throws Exception;
    }

    record Task(
        String name,
        TaskAction action,
        Predicate<Host> condition,
        List<String> notifications
    ) {
        Task {
            Objects.requireNonNull(name);
            Objects.requireNonNull(action);
            notifications = List.copyOf(notifications);
        }
    }

    record Handler(
        String name,
        HandlerAction action,
        Set<String> listen
    ) {
        Handler {
            Objects.requireNonNull(name);
            Objects.requireNonNull(action);
            listen = Set.copyOf(listen);
        }
    }

    static final class TemplateRenderer {

        private static final Pattern VARIABLE = Pattern.compile(
            "\\{\\{\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*}}"
        );

        private TemplateRenderer() {}

        static String render(
            String template,
            Map<String, Object> variables
        ) {
            Matcher matcher = VARIABLE.matcher(template);
            StringBuffer output = new StringBuffer();

            while (matcher.find()) {
                String name = matcher.group(1);

                if (!variables.containsKey(name) ||
                    variables.get(name) == null) {
                    throw new TemplateException(
                        "Undefined template variable: " + name
                    );
                }

                Object value = variables.get(name);

                if (value instanceof Map<?, ?> ||
                    value instanceof Iterable<?>) {
                    throw new TemplateException(
                        "Unsupported template variable: " + name
                    );
                }

                matcher.appendReplacement(
                    output,
                    Matcher.quoteReplacement(value.toString())
                );
            }

            matcher.appendTail(output);

            return output.toString();
        }
    }

    static final class AutomationService {

        private final List<Host> hosts = new ArrayList<>();
        private final List<Task> tasks = new ArrayList<>();

        private final Map<String, Handler> handlers =
            new LinkedHashMap<>();

        private final Map<String, Set<String>> pending =
            new HashMap<>();

        private final List<TaskResult> results =
            new ArrayList<>();

        void registerHost(Host host) {
            boolean duplicate = hosts.stream().anyMatch(
                existing -> existing.name.equals(host.name)
            );

            if (duplicate) {
                throw new AutomationException(
                    "Duplicate host: " + host.name
                );
            }

            hosts.add(host);
        }

        void registerTask(Task task) {
            tasks.add(task);
        }

        void registerHandler(Handler handler) {
            if (handlers.putIfAbsent(
                handler.name(),
                handler
            ) != null) {
                throw new AutomationException(
                    "Duplicate handler: " + handler.name()
                );
            }
        }

        private void record(
            Host host,
            String task,
            Status status,
            String message
        ) {
            results.add(
                new TaskResult(
                    host.name,
                    task,
                    status,
                    message
                )
            );
        }

        private void notify(Host host, String event) {
            Set<String> matched = new LinkedHashSet<>();

            if (handlers.containsKey(event)) {
                matched.add(event);
            }

            for (Handler handler : handlers.values()) {
                if (handler.listen().contains(event)) {
                    matched.add(handler.name());
                }
            }

            if (matched.isEmpty()) {
                throw new AutomationException(
                    "Unknown handler event: " + event
                );
            }

            pending.computeIfAbsent(
                host.name,
                ignored -> new LinkedHashSet<>()
            ).addAll(matched);
        }

        private void executeTask(Task task, Host host) {
            if (host.failed) return;

            try {
                if (
                    task.condition() != null &&
                    !task.condition().test(host)
                ) {
                    record(
                        host,
                        task.name(),
                        Status.SKIPPED,
                        "Conditional expression evaluated to false"
                    );

                    return;
                }

                boolean changed = task.action().execute(host);

                record(
                    host,
                    task.name(),
                    changed ? Status.CHANGED : Status.OK,
                    "Task completed"
                );

                if (changed) {
                    for (String event : task.notifications()) {
                        notify(host, event);
                    }
                }
            } catch (Exception exception) {
                host.failed = true;

                record(
                    host,
                    task.name(),
                    Status.FAILED,
                    exception.getMessage()
                );
            }
        }

        private void flushHandlers(Host host) {
            Set<String> queue = pending.remove(host.name);

            if (queue == null || host.failed) return;

            // A handler is executed once even if several tasks
            // notify it during the same execution phase.
            for (Handler handler : handlers.values()) {
                if (!queue.contains(handler.name())) continue;

                try {
                    boolean changed =
                        handler.action().execute(host);

                    record(
                        host,
                        "Handler: " + handler.name(),
                        changed ? Status.CHANGED : Status.OK,
                        "Handler executed"
                    );
                } catch (Exception exception) {
                    host.failed = true;

                    record(
                        host,
                        "Handler: " + handler.name(),
                        Status.FAILED,
                        exception.getMessage()
                    );

                    break;
                }
            }
        }

        void execute() {
            for (Task task : tasks) {
                for (Host host : hosts) {
                    executeTask(task, host);
                }

                for (Host host : hosts) {
                    flushHandlers(host);
                }
            }
        }

        void printReport() {
            for (Host host : hosts) {
                System.out.println(
                    "\nHost: " + host.name
                );

                System.out.println(
                    "Environment: " +
                    host.configuration.environment
                );

                System.out.println(
                    "Deployed version: " +
                    Objects.toString(
                        host.deployedVersion,
                        "not deployed"
                    )
                );

                EnumMap<Status, Integer> counts =
                    new EnumMap<>(Status.class);

                for (Status status : Status.values()) {
                    counts.put(status, 0);
                }

                for (TaskResult result : results) {
                    if (!result.host().equals(host.name)) continue;

                    counts.merge(
                        result.status(),
                        1,
                        Integer::sum
                    );

                    System.out.printf(
                        "[%s] %s: %s%n",
                        result.status(),
                        result.task(),
                        result.message()
                    );
                }

                System.out.println("Statistics: " + counts);
                System.out.println(
                    "Host result: " +
                    (host.failed ? "FAILED" : "SUCCESS")
                );
            }
        }

        boolean hasFailures() {
            return hosts.stream().anyMatch(host -> host.failed);
        }
    }

    static boolean createDirectory(Host host) {
        return host.directories.add(
            host.configuration.applicationDirectory
        );
    }

    static boolean deployApplication(Host host) {
        String desired =
            host.configuration.applicationVersion;

        if (desired.equals(host.deployedVersion)) {
            return false;
        }

        host.deployedVersion = desired;
        return true;
    }

    static boolean renderConfiguration(Host host) {
        Configuration config = host.configuration;

        Map<String, Object> variables = Map.of(
            "applicationName", config.applicationName,
            "applicationPort", config.applicationPort,
            "environment", config.environment.name().toLowerCase()
        );

        String template = """
            server {
                listen {{ applicationPort }};
                server_name {{ applicationName }};
                environment {{ environment }};
            }
            """;

        String rendered = TemplateRenderer.render(
            template,
            variables
        );

        String destination =
            config.applicationDirectory + "/application.conf";

        if (rendered.equals(host.files.get(destination))) {
            return false;
        }

        host.files.put(destination, rendered);
        return true;
    }

    static boolean restartApplication(Host host) {
        host.services.put(
            host.configuration.serviceName,
            "running"
        );

        return true;
    }

    static boolean verifyApplication(Host host) {
        if (host.deployedVersion == null) {
            throw new AutomationException(
                "Application is not deployed"
            );
        }

        if (!"running".equals(
            host.services.get(host.configuration.serviceName)
        )) {
            throw new AutomationException(
                "Application service is not running"
            );
        }

        return false;
    }

    private static Map<String, Object> defaultVariables(
        int port
    ) {
        Map<String, Object> defaults = new HashMap<>();

        defaults.put("applicationName", "inventory-api");
        defaults.put("applicationVersion", "1.0.0");
        defaults.put("applicationDirectory", "/opt/inventory");
        defaults.put("serviceName", "inventory-api");
        defaults.put("applicationPort", 8080);
        defaults.put("environment", "development");

        Map<String, Object> groupVars = Map.of(
            "environment", "production"
        );

        Map<String, Object> hostVars = Map.of(
            "applicationPort", port
        );

        return VariableResolver.resolve(
            Map.of(
                "defaults", defaults,
                "groupVars", groupVars,
                "hostVars", hostVars
            )
        );
    }

    public static void main(String[] args) {
        try {
            AutomationService service = new AutomationService();

            Configuration firstConfig = new Configuration(
                defaultVariables(8080)
            );

            Configuration secondConfig = new Configuration(
                defaultVariables(8081)
            );

            service.registerHost(
                new Host(
                    "web01.example.internal",
                    Set.of("web"),
                    firstConfig
                )
            );

            service.registerHost(
                new Host(
                    "web02.example.internal",
                    Set.of("web", "canary"),
                    secondConfig
                )
            );

            service.registerHandler(
                new Handler(
                    "restart application",
                    AnsibleAutomation::restartApplication,
                    Set.of("application configuration changed")
                )
            );

            service.registerTask(
                new Task(
                    "Create application directory",
                    AnsibleAutomation::createDirectory,
                    null,
                    List.of()
                )
            );

            service.registerTask(
                new Task(
                    "Deploy application",
                    AnsibleAutomation::deployApplication,
                    null,
                    List.of("application configuration changed")
                )
            );

            service.registerTask(
                new Task(
                    "Render application configuration",
                    AnsibleAutomation::renderConfiguration,
                    host -> host.configuration.environment ==
                        Environment.PRODUCTION,
                    List.of("restart application")
                )
            );

            service.registerTask(
                new Task(
                    "Verify application",
                    AnsibleAutomation::verifyApplication,
                    host -> host.groups.contains("web"),
                    List.of()
                )
            );

            service.execute();
            service.printReport();

            if (service.hasFailures()) {
                System.exit(1);
            }

        } catch (AutomationException exception) {
            System.err.println(
                "Automation error: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}

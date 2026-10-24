import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/**
 * Enterprise-oriented Docker Compose lifecycle and governance model.
 * Compatible with Java 17 and the standard library.
 */
public class ComposeGovernance {

    enum ServiceState {
        CREATED, STARTING, HEALTHY, UNHEALTHY, STOPPED, FAILED
    }

    enum DependencyCondition {
        SERVICE_STARTED, SERVICE_HEALTHY
    }

    enum RestartPolicy {
        NO, ON_FAILURE, ALWAYS, UNLESS_STOPPED
    }

    record Network(String name, boolean internal, String driver) {
        Network {
            requireName(name, "network");
            Objects.requireNonNull(driver, "driver");

            if (!Set.of("bridge", "overlay").contains(driver)) {
                throw new ConfigurationException("Unsupported network driver");
            }
        }
    }

    record Dependency(String service, DependencyCondition condition) {
        Dependency {
            requireName(service, "dependency");
            Objects.requireNonNull(condition, "condition");
        }
    }

    record ServiceSpec(
        String name,
        String image,
        Set<String> networks,
        List<Dependency> dependencies,
        boolean healthcheckConfigured,
        RestartPolicy restartPolicy,
        Map<String, String> environment
    ) {
        ServiceSpec {
            requireName(name, "service");

            if (image == null || image.isBlank()) {
                throw new ConfigurationException("Image is required");
            }

            if (networks == null || networks.isEmpty()) {
                throw new ConfigurationException(
                    name + " must join at least one network"
                );
            }

            networks = Set.copyOf(networks);
            dependencies = List.copyOf(dependencies);
            environment = Map.copyOf(environment);
            Objects.requireNonNull(restartPolicy, "restartPolicy");

            for (Map.Entry<String, String> entry : environment.entrySet()) {
                String key = entry.getKey();
                String value = entry.getValue();

                if (
                    key.matches(".*_(PASSWORD|TOKEN|SECRET)$") &&
                    (value == null || value.isEmpty())
                ) {
                    throw new ConfigurationException(
                        "Empty secret variable " + key
                    );
                }
            }
        }
    }

    static final class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static final class LifecycleException extends RuntimeException {
        LifecycleException(String message) {
            super(message);
        }
    }

    static final class RuntimeService {
        private final ServiceSpec spec;
        private ServiceState state = ServiceState.CREATED;
        private int attempts;
        private boolean probeResult = true;

        RuntimeService(ServiceSpec spec) {
            this.spec = spec;
        }

        ServiceSpec spec() {
            return spec;
        }

        ServiceState state() {
            return state;
        }

        void state(ServiceState newState) {
            state = Objects.requireNonNull(newState);
        }

        void setProbeResult(boolean result) {
            probeResult = result;
        }

        boolean probe() {
            attempts++;
            return probeResult;
        }

        int attempts() {
            return attempts;
        }
    }

    static final class ComposeProject {
        private final String name;
        private final Map<String, Network> networks = new LinkedHashMap<>();
        private final Map<String, RuntimeService> services = new LinkedHashMap<>();
        private final List<String> auditLog = new ArrayList<>();

        ComposeProject(
            String name,
            List<Network> networkDefinitions,
            List<ServiceSpec> serviceDefinitions
        ) {
            requireName(name, "project");
            this.name = name;

            for (Network network : networkDefinitions) {
                if (networks.putIfAbsent(network.name(), network) != null) {
                    throw new ConfigurationException(
                        "Duplicate network " + network.name()
                    );
                }
            }

            for (ServiceSpec spec : serviceDefinitions) {
                if (services.putIfAbsent(
                    spec.name(), new RuntimeService(spec)
                ) != null) {
                    throw new ConfigurationException(
                        "Duplicate service " + spec.name()
                    );
                }
            }
        }

        void validate() {
            if (services.isEmpty()) {
                throw new ConfigurationException("No services defined");
            }

            for (RuntimeService runtime : services.values()) {
                ServiceSpec spec = runtime.spec();

                for (String network : spec.networks()) {
                    if (!networks.containsKey(network)) {
                        throw new ConfigurationException(
                            spec.name() + " references unknown network " + network
                        );
                    }
                }

                for (Dependency dependency : spec.dependencies()) {
                    RuntimeService target = services.get(dependency.service());

                    if (target == null || target == runtime) {
                        throw new ConfigurationException(
                            "Invalid dependency for " + spec.name()
                        );
                    }

                    if (
                        dependency.condition() ==
                            DependencyCondition.SERVICE_HEALTHY &&
                        !target.spec().healthcheckConfigured()
                    ) {
                        throw new ConfigurationException(
                            target.spec().name() +
                            " requires a configured health check"
                        );
                    }
                }
            }

            startupOrder();
        }

        List<String> startupOrder() {
            Map<String, Integer> indegree = new HashMap<>();
            Map<String, List<String>> dependents = new HashMap<>();

            for (String name : services.keySet()) {
                indegree.put(name, 0);
                dependents.put(name, new ArrayList<>());
            }

            for (RuntimeService runtime : services.values()) {
                for (Dependency dependency : runtime.spec().dependencies()) {
                    indegree.merge(runtime.spec().name(), 1, Integer::sum);
                    dependents.get(dependency.service()).add(runtime.spec().name());
                }
            }

            TreeSet<String> ready = new TreeSet<>();

            indegree.forEach((name, count) -> {
                if (count == 0) ready.add(name);
            });

            List<String> order = new ArrayList<>();

            while (!ready.isEmpty()) {
                String current = ready.pollFirst();
                order.add(current);

                for (String dependent : dependents.get(current)) {
                    int next = indegree.merge(dependent, -1, Integer::sum);
                    if (next == 0) ready.add(dependent);
                }
            }

            if (order.size() != services.size()) {
                throw new ConfigurationException(
                    "Circular service dependency detected"
                );
            }

            return List.copyOf(order);
        }

        boolean canCommunicate(String first, String second) {
            RuntimeService left = services.get(first);
            RuntimeService right = services.get(second);

            if (left == null || right == null) return false;

            Set<String> shared = new HashSet<>(left.spec().networks());
            shared.retainAll(right.spec().networks());
            return !shared.isEmpty();
        }

        void record(String service, String event) {
            String message = name + " / " + service + " / " + event;
            auditLog.add(message);
            System.out.println(message);
        }

        void start() {
            validate();
            List<String> started = new ArrayList<>();

            try {
                for (String name : startupOrder()) {
                    RuntimeService runtime = services.get(name);
                    ServiceSpec spec = runtime.spec();

                    for (Dependency dependency : spec.dependencies()) {
                        RuntimeService parent = services.get(dependency.service());

                        if (
                            dependency.condition() ==
                                DependencyCondition.SERVICE_HEALTHY &&
                            parent.state() != ServiceState.HEALTHY
                        ) {
                            throw new LifecycleException(
                                name + " requires healthy " + dependency.service()
                            );
                        }

                        if (
                            dependency.condition() ==
                                DependencyCondition.SERVICE_STARTED &&
                            parent.state() == ServiceState.CREATED
                        ) {
                            throw new LifecycleException(
                                name + " requires started " + dependency.service()
                            );
                        }
                    }

                    runtime.state(ServiceState.STARTING);
                    started.add(name);
                    record(name, "starting");

                    if (!runtime.probe()) {
                        runtime.state(ServiceState.UNHEALTHY);
                        record(name, "unhealthy");
                        throw new LifecycleException(
                            "Health check failed for " + name
                        );
                    }

                    runtime.state(ServiceState.HEALTHY);
                    record(name, "healthy");
                }
            } catch (RuntimeException error) {
                Collections.reverse(started);

                for (String name : started) {
                    services.get(name).state(ServiceState.STOPPED);
                    record(name, "rollback-stop");
                }

                throw error;
            }
        }

        void stop() {
            List<String> reverse = new ArrayList<>(startupOrder());
            Collections.reverse(reverse);

            for (String name : reverse) {
                services.get(name).state(ServiceState.STOPPED);
                record(name, "stopped");
            }
        }

        void printStatus() {
            services.values().stream()
                .sorted((a, b) -> a.spec().name().compareTo(b.spec().name()))
                .forEach(runtime -> System.out.printf(
                    "%s: %s (health attempts: %d)%n",
                    runtime.spec().name(),
                    runtime.state(),
                    runtime.attempts()
                ));
        }

        void setProbeResult(String service, boolean result) {
            RuntimeService runtime = services.get(service);

            if (runtime == null) {
                throw new ConfigurationException(
                    "Unknown service " + service
                );
            }

            runtime.setProbeResult(result);
        }
    }

    private static void requireName(String name, String type) {
        if (
            name == null ||
            !name.matches("[a-zA-Z0-9][a-zA-Z0-9_.-]*")
        ) {
            throw new ConfigurationException("Invalid " + type + " name");
        }
    }

    static ComposeProject buildProject() {
        List<Network> networks = List.of(
            new Network("frontend", false, "bridge"),
            new Network("backend", true, "bridge")
        );

        ServiceSpec db = new ServiceSpec(
            "db",
            "postgres:18",
            Set.of("backend"),
            List.of(),
            true,
            RestartPolicy.UNLESS_STOPPED,
            Map.of(
                "POSTGRES_DB", "orders",
                "POSTGRES_USER", "app"
            )
        );

        ServiceSpec api = new ServiceSpec(
            "api",
            "eclipse-temurin:17-jre",
            Set.of("frontend", "backend"),
            List.of(new Dependency(
                "db", DependencyCondition.SERVICE_HEALTHY
            )),
            true,
            RestartPolicy.ON_FAILURE,
            Map.of("DATABASE_HOST", "db")
        );

        ServiceSpec web = new ServiceSpec(
            "web",
            "nginx:alpine",
            Set.of("frontend"),
            List.of(new Dependency(
                "api", DependencyCondition.SERVICE_HEALTHY
            )),
            true,
            RestartPolicy.UNLESS_STOPPED,
            Map.of()
        );

        return new ComposeProject(
            "orders-stack", networks, List.of(db, api, web)
        );
    }

    public static void main(String[] args) {
        ComposeProject project = buildProject();

        System.out.println("Startup order: " + project.startupOrder());
        System.out.println(
            "API can reach DB: " + project.canCommunicate("api", "db")
        );
        System.out.println(
            "Web can reach DB directly: " +
            project.canCommunicate("web", "db")
        );

        project.start();
        project.printStatus();
        project.stop();

        System.out.println("\nTesting failed health check:");

        ComposeProject failing = buildProject();
        failing.setProbeResult("db", false);

        try {
            failing.start();
        } catch (LifecycleException error) {
            System.out.println("Expected failure: " + error.getMessage());
            failing.printStatus();
        }
    }
}

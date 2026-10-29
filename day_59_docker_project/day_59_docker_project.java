import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;

/*
 * Enterprise-oriented Docker deployment governance model.
 *
 * The application models a five-service order platform:
 * frontend -> api -> database
 *                    -> redis
 * worker  -> database
 * worker  -> redis
 *
 * Explicit domain types separate configuration validation, lifecycle state,
 * dependency policy, network membership, and deployment orchestration.
 */

public class DockerMultiServiceApplication {

    enum ServiceState {
        CREATED,
        STARTING,
        HEALTHY,
        UNHEALTHY,
        STOPPED
    }

    enum DependencyCondition {
        SERVICE_STARTED,
        SERVICE_HEALTHY
    }

    record Dependency(String serviceName, DependencyCondition condition) {
        public Dependency {
            Objects.requireNonNull(serviceName);
            Objects.requireNonNull(condition);
        }
    }

    record EnvironmentVariable(String name, String value) {
        public EnvironmentVariable {
            if (name == null || !name.matches("[A-Z][A-Z0-9_]*")) {
                throw new ConfigurationException(
                    "Invalid environment variable: " + name
                );
            }

            if (value == null || value.indexOf('\0') >= 0) {
                throw new ConfigurationException(
                    "Invalid environment value for " + name
                );
            }
        }
    }

    static final class ServiceDefinition {
        private final String name;
        private final String image;
        private final Integer hostPort;
        private final int memoryMb;
        private final List<EnvironmentVariable> environment;
        private final List<Dependency> dependencies;

        private ServiceState state = ServiceState.CREATED;
        private int restartCount;

        ServiceDefinition(
            String name,
            String image,
            Integer hostPort,
            int memoryMb,
            List<EnvironmentVariable> environment,
            List<Dependency> dependencies
        ) {
            this.name = Objects.requireNonNull(name);
            this.image = Objects.requireNonNull(image);
            this.hostPort = hostPort;
            this.memoryMb = memoryMb;
            this.environment = List.copyOf(environment);
            this.dependencies = List.copyOf(dependencies);
        }

        void validate() {
            if (!name.matches("[a-z0-9][a-z0-9-]*")) {
                throw new ConfigurationException(
                    "Invalid service name: " + name
                );
            }

            int lastSlash = image.lastIndexOf('/');
            int lastColon = image.lastIndexOf(':');

            if (lastColon <= lastSlash || lastColon == image.length() - 1) {
                throw new ConfigurationException(
                    name + ": image must have an explicit tag"
                );
            }

            if (hostPort != null &&
                (hostPort < 1 || hostPort > 65535)) {
                throw new ConfigurationException(
                    name + ": invalid host port"
                );
            }

            if (memoryMb < 64) {
                throw new ConfigurationException(
                    name + ": memory must be at least 64 MB"
                );
            }

            for (Dependency dependency : dependencies) {
                if (dependency.serviceName().equals(name)) {
                    throw new ConfigurationException(
                        name + ": self-dependency is forbidden"
                    );
                }
            }
        }

        String name() {
            return name;
        }

        String image() {
            return image;
        }

        Integer hostPort() {
            return hostPort;
        }

        int memoryMb() {
            return memoryMb;
        }

        List<Dependency> dependencies() {
            return dependencies;
        }

        ServiceState state() {
            return state;
        }

        void state(ServiceState state) {
            this.state = state;
        }

        int restartCount() {
            return restartCount;
        }

        void incrementRestartCount() {
            restartCount++;
        }
    }

    static class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    interface DeploymentPolicy {
        void validate(Map<String, ServiceDefinition> services);
    }

    static final class ProductionPolicy implements DeploymentPolicy {

        @Override
        public void validate(Map<String, ServiceDefinition> services) {
            if (services.isEmpty()) {
                throw new ConfigurationException(
                    "At least one service is required"
                );
            }

            Map<Integer, String> ports = new HashMap<>();

            for (ServiceDefinition service : services.values()) {
                service.validate();

                if (service.hostPort() != null) {
                    String previous = ports.put(
                        service.hostPort(),
                        service.name()
                    );

                    if (previous != null) {
                        throw new ConfigurationException(
                            "Host port " + service.hostPort() +
                            " is assigned to both " +
                            previous + " and " + service.name()
                        );
                    }
                }

                for (Dependency dependency : service.dependencies()) {
                    if (!services.containsKey(dependency.serviceName())) {
                        throw new ConfigurationException(
                            service.name() +
                            ": dependency does not exist: " +
                            dependency.serviceName()
                        );
                    }
                }
            }

            validateAcyclic(services);
        }

        private void validateAcyclic(
            Map<String, ServiceDefinition> services
        ) {
            Set<String> visiting = new HashSet<>();
            Set<String> visited = new HashSet<>();

            for (String name : services.keySet()) {
                visit(name, services, visiting, visited);
            }
        }

        private void visit(
            String name,
            Map<String, ServiceDefinition> services,
            Set<String> visiting,
            Set<String> visited
        ) {
            if (visiting.contains(name)) {
                throw new ConfigurationException(
                    "Dependency cycle detected at " + name
                );
            }

            if (visited.contains(name)) {
                return;
            }

            visiting.add(name);

            for (Dependency dependency :
                services.get(name).dependencies()) {
                visit(
                    dependency.serviceName(),
                    services,
                    visiting,
                    visited
                );
            }

            visiting.remove(name);
            visited.add(name);
        }
    }

    static final class DeploymentNetwork {
        private final Set<String> members = new HashSet<>();

        void connect(String serviceName) {
            members.add(serviceName);
        }

        void disconnect(String serviceName) {
            members.remove(serviceName);
        }

        boolean canReach(String source, String destination) {
            return members.contains(source) &&
                   members.contains(destination);
        }

        Set<String> members() {
            return Collections.unmodifiableSet(members);
        }
    }

    static final class DeploymentService {
        private final Map<String, ServiceDefinition> services;
        private final DeploymentPolicy policy;
        private final DeploymentNetwork network;

        DeploymentService(
            Map<String, ServiceDefinition> services,
            DeploymentPolicy policy,
            DeploymentNetwork network
        ) {
            this.services = services;
            this.policy = policy;
            this.network = network;
        }

        void validate() {
            policy.validate(services);
        }

        List<String> startupOrder() {
            Map<String, Integer> indegree = new LinkedHashMap<>();
            Map<String, List<String>> graph = new LinkedHashMap<>();

            for (String name : services.keySet()) {
                indegree.put(name, 0);
                graph.put(name, new ArrayList<>());
            }

            for (ServiceDefinition service : services.values()) {
                for (Dependency dependency : service.dependencies()) {
                    graph.get(dependency.serviceName())
                         .add(service.name());

                    indegree.compute(
                        service.name(),
                        (key, value) -> value + 1
                    );
                }
            }

            Queue<String> ready = new ArrayDeque<>();

            for (Map.Entry<String, Integer> entry :
                indegree.entrySet()) {
                if (entry.getValue() == 0) {
                    ready.add(entry.getKey());
                }
            }

            List<String> result = new ArrayList<>();

            while (!ready.isEmpty()) {
                String current = ready.remove();
                result.add(current);

                for (String dependent : graph.get(current)) {
                    int next = indegree.get(dependent) - 1;
                    indegree.put(dependent, next);

                    if (next == 0) {
                        ready.add(dependent);
                    }
                }
            }

            if (result.size() != services.size()) {
                throw new ConfigurationException(
                    "Unable to construct dependency-safe startup order"
                );
            }

            return List.copyOf(result);
        }

        private boolean dependenciesReady(
            ServiceDefinition service
        ) {
            for (Dependency dependency : service.dependencies()) {
                ServiceDefinition target =
                    services.get(dependency.serviceName());

                if (dependency.condition() ==
                    DependencyCondition.SERVICE_STARTED) {
                    if (target.state() != ServiceState.STARTING &&
                        target.state() != ServiceState.HEALTHY) {
                        return false;
                    }
                } else if (target.state() != ServiceState.HEALTHY) {
                    return false;
                }
            }

            return true;
        }

        void start(String name) {
            ServiceDefinition service = require(name);

            if (service.state() == ServiceState.HEALTHY) {
                return;
            }

            if (!dependenciesReady(service)) {
                throw new DeploymentException(
                    name + ": dependency policy is not satisfied"
                );
            }

            service.state(ServiceState.STARTING);
            network.connect(name);

            service.state(ServiceState.HEALTHY);
        }

        void startAll() {
            validate();

            for (String name : startupOrder()) {
                start(name);
            }
        }

        void stop(String name) {
            ServiceDefinition service = require(name);
            service.state(ServiceState.STOPPED);
            network.disconnect(name);
        }

        void restart(String name) {
            ServiceDefinition service = require(name);

            stop(name);
            service.incrementRestartCount();
            start(name);
        }

        void setHealthy(String name, boolean healthy) {
            ServiceDefinition service = require(name);

            service.state(
                healthy
                    ? ServiceState.HEALTHY
                    : ServiceState.UNHEALTHY
            );
        }

        private ServiceDefinition require(String name) {
            ServiceDefinition service = services.get(name);

            if (service == null) {
                throw new DeploymentException(
                    "Unknown service: " + name
                );
            }

            return service;
        }

        void printStatus() {
            System.out.println("\nSERVICE STATUS");

            services.values().stream()
                .sorted((a, b) -> a.name().compareTo(b.name()))
                .forEach(service ->
                    System.out.printf(
                        "%-10s state=%-10s image=%-22s memory=%4dMB restarts=%d%n",
                        service.name(),
                        service.state(),
                        service.image(),
                        service.memoryMb(),
                        service.restartCount()
                    )
                );

            System.out.println(
                "network members: " +
                network.members().stream()
                    .sorted()
                    .toList()
            );
        }
    }

    static Map<String, ServiceDefinition> createApplication() {
        Map<String, ServiceDefinition> services =
            new LinkedHashMap<>();

        services.put(
            "db",
            new ServiceDefinition(
                "db",
                "postgres:18",
                5432,
                512,
                List.of(
                    new EnvironmentVariable(
                        "POSTGRES_DB",
                        "orders"
                    ),
                    new EnvironmentVariable(
                        "POSTGRES_USER",
                        "app"
                    )
                ),
                List.of()
            )
        );

        services.put(
            "redis",
            new ServiceDefinition(
                "redis",
                "redis:8",
                6379,
                256,
                List.of(),
                List.of()
            )
        );

        services.put(
            "api",
            new ServiceDefinition(
                "api",
                "orders-api:1.0",
                8080,
                512,
                List.of(
                    new EnvironmentVariable(
                        "DATABASE_HOST",
                        "db"
                    ),
                    new EnvironmentVariable(
                        "REDIS_HOST",
                        "redis"
                    )
                ),
                List.of(
                    new Dependency(
                        "db",
                        DependencyCondition.SERVICE_HEALTHY
                    ),
                    new Dependency(
                        "redis",
                        DependencyCondition.SERVICE_HEALTHY
                    )
                )
            )
        );

        services.put(
            "worker",
            new ServiceDefinition(
                "worker",
                "orders-worker:1.0",
                null,
                384,
                List.of(),
                List.of(
                    new Dependency(
                        "db",
                        DependencyCondition.SERVICE_HEALTHY
                    ),
                    new Dependency(
                        "redis",
                        DependencyCondition.SERVICE_HEALTHY
                    )
                )
            )
        );

        services.put(
            "frontend",
            new ServiceDefinition(
                "frontend",
                "orders-frontend:1.0",
                3000,
                256,
                List.of(
                    new EnvironmentVariable(
                        "API_BASE_URL",
                        "http://api:8080"
                    )
                ),
                List.of(
                    new Dependency(
                        "api",
                        DependencyCondition.SERVICE_HEALTHY
                    )
                )
            )
        );

        return services;
    }

    static void runValidationTests() {
        Map<String, ServiceDefinition> invalid =
            new LinkedHashMap<>();

        invalid.put(
            "broken",
            new ServiceDefinition(
                "broken",
                "postgres",
                5432,
                256,
                List.of(),
                List.of()
            )
        );

        try {
            new ProductionPolicy().validate(invalid);
            throw new AssertionError(
                "Expected invalid image validation"
            );
        } catch (ConfigurationException expected) {
            // Expected failure.
        }

        Map<String, ServiceDefinition> cyclic =
            new LinkedHashMap<>();

        cyclic.put(
            "a",
            new ServiceDefinition(
                "a",
                "a:1.0",
                null,
                256,
                List.of(),
                List.of(
                    new Dependency(
                        "b",
                        DependencyCondition.SERVICE_STARTED
                    )
                )
            )
        );

        cyclic.put(
            "b",
            new ServiceDefinition(
                "b",
                "b:1.0",
                null,
                256,
                List.of(),
                List.of(
                    new Dependency(
                        "a",
                        DependencyCondition.SERVICE_STARTED
                    )
                )
            )
        );

        try {
            new ProductionPolicy().validate(cyclic);
            throw new AssertionError(
                "Expected dependency cycle validation"
            );
        } catch (ConfigurationException expected) {
            // Expected failure.
        }
    }

    public static void main(String[] args) {
        try {
            runValidationTests();

            Map<String, ServiceDefinition> services =
                createApplication();

            DeploymentNetwork network =
                new DeploymentNetwork();

            DeploymentService deployment =
                new DeploymentService(
                    services,
                    new ProductionPolicy(),
                    network
                );

            System.out.println("VALIDATING APPLICATION");
            deployment.validate();

            System.out.println("STARTUP ORDER");
            System.out.println(
                String.join(
                    " -> ",
                    deployment.startupOrder()
                )
            );

            deployment.startAll();
            deployment.printStatus();

            if (!network.canReach("frontend", "api")) {
                throw new DeploymentException(
                    "Frontend must reach API"
                );
            }

            if (!network.canReach("api", "db")) {
                throw new DeploymentException(
                    "API must reach database"
                );
            }

            if (network.canReach("frontend", "db")) {
                throw new DeploymentException(
                    "Frontend must not directly depend on database"
                );
            }

            System.out.println("\nSIMULATING API FAILURE");
            deployment.setHealthy("api", false);
            deployment.printStatus();

            System.out.println("\nRECOVERING API");
            deployment.restart("api");
            deployment.printStatus();

            System.out.println(
                "\nEnterprise deployment model completed."
            );
        } catch (RuntimeException error) {
            System.err.println(
                "fatal: " + error.getMessage()
            );
            System.exit(1);
        }
    }
}

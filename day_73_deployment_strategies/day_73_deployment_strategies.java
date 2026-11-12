/*
 * Enterprise Deployment Governance System
 *
 * Java 17
 *
 * Implements:
 * - Recreate deployment
 * - Rolling deployment
 * - Blue-green deployment
 * - Immutable deployment requests
 * - Deployment policy objects
 * - Infrastructure capacity validation
 * - Health-check services
 * - Traffic management
 * - State transitions
 * - Rollback management
 *
 * Standard Java library only.
 */

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Predicate;

public class DeploymentGovernance {

    enum Strategy {
        RECREATE,
        ROLLING,
        BLUE_GREEN
    }

    enum DeploymentState {
        PENDING,
        PROVISIONING,
        VALIDATING,
        SWITCHING,
        SUCCEEDED,
        FAILED,
        ROLLED_BACK
    }

    enum InstanceState {
        STARTING,
        HEALTHY,
        UNHEALTHY,
        STOPPED
    }

    record DeploymentRequest(
        String application,
        String version,
        Strategy strategy,
        int desiredReplicas,
        int batchSize,
        int trafficWeight
    ) {
        DeploymentRequest {
            Objects.requireNonNull(application);
            Objects.requireNonNull(version);
            Objects.requireNonNull(strategy);

            if (application.isBlank() || version.isBlank()) {
                throw new IllegalArgumentException(
                    "Application and version are required"
                );
            }

            if (desiredReplicas < 1 || batchSize < 1) {
                throw new IllegalArgumentException(
                    "Replica count and batch size must be positive"
                );
            }

            if (trafficWeight < 0 || trafficWeight > 100) {
                throw new IllegalArgumentException(
                    "Traffic weight must be between 0 and 100"
                );
            }
        }
    }

    record DeploymentEvent(
        Instant timestamp,
        String event,
        String details
    ) {}

    record Instance(
        String id,
        String version,
        InstanceState state
    ) {
        Instance withState(InstanceState newState) {
            return new Instance(id, version, newState);
        }
    }

    record DeploymentReport(
        UUID id,
        String application,
        String version,
        Strategy strategy,
        DeploymentState state,
        String previousVersion,
        String error,
        Instant startedAt,
        Instant completedAt
    ) {}

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static class CapacityException extends DeploymentException {
        CapacityException(String message) {
            super(message);
        }
    }

    static class HealthException extends DeploymentException {
        HealthException(String message) {
            super(message);
        }
    }

    static final class DeploymentPolicy {

        private final int maximumCapacity;
        private final int maxSurge;
        private final int maxUnavailable;
        private final double minimumHealthyRatio;
        private final boolean allowRecreate;
        private final boolean allowBlueGreen;
        private final boolean requireHealthChecks;

        DeploymentPolicy(
            int maximumCapacity,
            int maxSurge,
            int maxUnavailable,
            double minimumHealthyRatio,
            boolean allowRecreate,
            boolean allowBlueGreen,
            boolean requireHealthChecks
        ) {
            if (maximumCapacity < 1 ||
                maxSurge < 0 ||
                maxUnavailable < 0) {
                throw new IllegalArgumentException(
                    "Invalid infrastructure policy"
                );
            }

            if (maxSurge + maxUnavailable < 1) {
                throw new IllegalArgumentException(
                    "Rolling deployment cannot make progress"
                );
            }

            if (minimumHealthyRatio < 0 ||
                minimumHealthyRatio > 1) {
                throw new IllegalArgumentException(
                    "Invalid health threshold"
                );
            }

            this.maximumCapacity = maximumCapacity;
            this.maxSurge = maxSurge;
            this.maxUnavailable = maxUnavailable;
            this.minimumHealthyRatio = minimumHealthyRatio;
            this.allowRecreate = allowRecreate;
            this.allowBlueGreen = allowBlueGreen;
            this.requireHealthChecks = requireHealthChecks;
        }

        void authorize(
            DeploymentRequest request,
            int currentInstances
        ) {
            if (request.desiredReplicas() > maximumCapacity) {
                throw new CapacityException(
                    "Desired replicas exceed infrastructure capacity"
                );
            }

            if (request.strategy() == Strategy.RECREATE &&
                !allowRecreate) {
                throw new DeploymentException(
                    "Recreate deployment is prohibited"
                );
            }

            if (request.strategy() == Strategy.BLUE_GREEN) {
                if (!allowBlueGreen) {
                    throw new DeploymentException(
                        "Blue-green deployment is prohibited"
                    );
                }

                if (currentInstances + request.desiredReplicas()
                    > maximumCapacity) {
                    throw new CapacityException(
                        "Insufficient capacity for blue-green deployment"
                    );
                }
            }
        }

        int maxSurge() {
            return maxSurge;
        }

        int maxUnavailable() {
            return maxUnavailable;
        }

        int maximumCapacity() {
            return maximumCapacity;
        }

        double minimumHealthyRatio() {
            return minimumHealthyRatio;
        }

        boolean requireHealthChecks() {
            return requireHealthChecks;
        }
    }

    static final class TrafficManager {

        private final Map<String, Integer> weights =
            new HashMap<>();

        TrafficManager(String initialVersion) {
            weights.put(initialVersion, 100);
        }

        synchronized void switchTo(String version) {
            weights.clear();
            weights.put(version, 100);
        }

        synchronized void shift(
            String oldVersion,
            String newVersion,
            int newWeight
        ) {
            if (newWeight < 0 || newWeight > 100) {
                throw new IllegalArgumentException(
                    "Invalid traffic allocation"
                );
            }

            weights.clear();

            if (newWeight < 100) {
                weights.put(oldVersion, 100 - newWeight);
            }

            if (newWeight > 0) {
                weights.put(newVersion, newWeight);
            }

            int total = weights.values()
                .stream()
                .mapToInt(Integer::intValue)
                .sum();

            if (total != 100) {
                throw new DeploymentException(
                    "Traffic allocation must equal 100%"
                );
            }
        }

        synchronized Map<String, Integer> snapshot() {
            return Collections.unmodifiableMap(
                new HashMap<>(weights)
            );
        }

        synchronized void restore(Map<String, Integer> snapshot) {
            weights.clear();
            weights.putAll(snapshot);
        }
    }

    static final class InfrastructureService {

        private final int maximumCapacity;
        private int nextId = 1;

        InfrastructureService(int maximumCapacity) {
            this.maximumCapacity = maximumCapacity;
        }

        Instance provision(String version) {
            return new Instance(
                "node-" + nextId++,
                version,
                InstanceState.HEALTHY
            );
        }

        void validateCapacity(int required) {
            if (required > maximumCapacity) {
                throw new CapacityException(
                    "Infrastructure capacity exceeded"
                );
            }
        }
    }

    static final class HealthService {

        private final double threshold;
        private final Predicate<List<Instance>> customHealthCheck;

        HealthService(
            double threshold,
            Predicate<List<Instance>> customHealthCheck
        ) {
            this.threshold = threshold;
            this.customHealthCheck = customHealthCheck;
        }

        boolean validate(List<Instance> instances) {
            if (instances.isEmpty()) {
                return false;
            }

            long healthy = instances.stream()
                .filter(instance ->
                    instance.state() == InstanceState.HEALTHY)
                .count();

            double ratio = (double) healthy / instances.size();

            return ratio >= threshold &&
                healthy == instances.size() &&
                customHealthCheck.test(
                    Collections.unmodifiableList(instances)
                );
        }

        void requireHealthy(List<Instance> instances) {
            if (!validate(instances)) {
                throw new HealthException(
                    "Application health validation failed"
                );
            }
        }
    }

    static final class DeploymentService {

        private final DeploymentPolicy policy;
        private final InfrastructureService infrastructure;
        private final HealthService health;
        private final TrafficManager traffic;

        private final List<Instance> instances =
            new ArrayList<>();

        private final List<DeploymentReport> history =
            new ArrayList<>();

        private final List<DeploymentEvent> events =
            new ArrayList<>();

        private final ReentrantLock deploymentLock =
            new ReentrantLock();

        private String activeVersion;
        private String previousVersion;

        DeploymentService(
            String initialVersion,
            DeploymentPolicy policy
        ) {
            this.policy = policy;

            infrastructure = new InfrastructureService(
                policy.maximumCapacity()
            );

            health = new HealthService(
                policy.minimumHealthyRatio(),
                DeploymentService::applicationHealthCheck
            );

            traffic = new TrafficManager(initialVersion);

            activeVersion = initialVersion;

            for (int i = 0; i < 4; i++) {
                instances.add(
                    infrastructure.provision(initialVersion)
                );
            }

            infrastructure.validateCapacity(instances.size());
        }

        private static boolean applicationHealthCheck(
            List<Instance> instances
        ) {
            // This represents an application-level health probe.
            // Production systems should evaluate readiness,
            // dependencies, error rate and response latency.
            return !instances.isEmpty() &&
                instances.stream().allMatch(
                    instance ->
                        instance.state() == InstanceState.HEALTHY
                );
        }

        private void event(String name, String details) {
            events.add(new DeploymentEvent(
                Instant.now(),
                name,
                details
            ));
        }

        private List<Instance> provisionEnvironment(
            String version,
            int replicas
        ) {
            List<Instance> result = new ArrayList<>();

            for (int i = 0; i < replicas; i++) {
                result.add(
                    infrastructure.provision(version)
                );
            }

            return result;
        }

        private void recreate(DeploymentRequest request) {
            List<Instance> old = new ArrayList<>(instances);

            try {
                event("RECREATE_STOP", activeVersion);

                instances.clear();

                infrastructure.validateCapacity(
                    request.desiredReplicas()
                );

                instances.addAll(
                    provisionEnvironment(
                        request.version(),
                        request.desiredReplicas()
                    )
                );

                if (policy.requireHealthChecks()) {
                    health.requireHealthy(instances);
                }

            } catch (RuntimeException exception) {
                instances.clear();
                instances.addAll(old);
                throw exception;
            }
        }

        private void rolling(DeploymentRequest request) {
            List<Instance> original =
                new ArrayList<>(instances);

            try {
                int position = 0;

                while (position < original.size()) {
                    int count = Math.min(
                        request.batchSize(),
                        original.size() - position
                    );

                    int replaceCount = Math.min(
                        count,
                        policy.maxSurge() +
                            policy.maxUnavailable()
                    );

                    if (replaceCount < 1) {
                        throw new DeploymentException(
                            "Rolling policy prevents progress"
                        );
                    }

                    List<Instance> oldBatch =
                        original.subList(
                            position,
                            position + replaceCount
                        );

                    instances.removeAll(oldBatch);

                    List<Instance> replacement =
                        provisionEnvironment(
                            request.version(),
                            replaceCount
                        );

                    infrastructure.validateCapacity(
                        instances.size() + replacement.size()
                    );

                    instances.addAll(replacement);

                    if (policy.requireHealthChecks()) {
                        health.requireHealthy(replacement);
                    }

                    event(
                        "ROLLING_BATCH_COMPLETE",
                        "Position: " + position
                    );

                    position += replaceCount;
                }

                if (instances.size() != request.desiredReplicas()) {
                    throw new DeploymentException(
                        "Final replica count mismatch"
                    );
                }

                if (policy.requireHealthChecks()) {
                    health.requireHealthy(instances);
                }

            } catch (RuntimeException exception) {
                instances.clear();
                instances.addAll(original);
                throw exception;
            }
        }

        private void blueGreen(DeploymentRequest request) {
            List<Instance> oldInstances =
                new ArrayList<>(instances);

            Map<String, Integer> oldTraffic =
                traffic.snapshot();

            infrastructure.validateCapacity(
                instances.size() + request.desiredReplicas()
            );

            try {
                event("GREEN_PROVISIONING", request.version());

                List<Instance> green =
                    provisionEnvironment(
                        request.version(),
                        request.desiredReplicas()
                    );

                if (policy.requireHealthChecks()) {
                    health.requireHealthy(green);
                }

                event("GREEN_VALIDATED", request.version());

                traffic.shift(
                    activeVersion,
                    request.version(),
                    request.trafficWeight()
                );

                if (request.trafficWeight() == 100) {
                    instances.clear();
                    instances.addAll(green);
                } else {
                    instances.addAll(green);
                }

                event(
                    "TRAFFIC_SWITCH",
                    traffic.snapshot().toString()
                );

            } catch (RuntimeException exception) {
                instances.clear();
                instances.addAll(oldInstances);
                traffic.restore(oldTraffic);
                throw exception;
            }
        }

        private void validateRequest(DeploymentRequest request) {
            if (request.version().equals(activeVersion)) {
                throw new DeploymentException(
                    "Requested version is already active"
                );
            }

            policy.authorize(request, instances.size());
        }

        DeploymentReport deploy(DeploymentRequest request) {
            Objects.requireNonNull(request);

            if (!deploymentLock.tryLock()) {
                throw new DeploymentException(
                    "Another deployment is in progress"
                );
            }

            Instant started = Instant.now();

            UUID id = UUID.randomUUID();

            String oldVersion = activeVersion;
            String oldPrevious = previousVersion;

            List<Instance> oldInstances =
                new ArrayList<>(instances);

            Map<String, Integer> oldTraffic =
                traffic.snapshot();

            DeploymentState state = DeploymentState.PENDING;
            String error = null;

            try {
                validateRequest(request);

                state = DeploymentState.PROVISIONING;

                event(
                    "DEPLOYMENT_STARTED",
                    request.version()
                );

                switch (request.strategy()) {
                    case RECREATE:
                        recreate(request);
                        break;

                    case ROLLING:
                        rolling(request);
                        break;

                    case BLUE_GREEN:
                        state = DeploymentState.VALIDATING;
                        blueGreen(request);
                        break;
                }

                if (request.strategy() != Strategy.BLUE_GREEN ||
                    request.trafficWeight() == 100) {

                    previousVersion = activeVersion;
                    activeVersion = request.version();
                    traffic.switchTo(activeVersion);
                }

                state = DeploymentState.SUCCEEDED;

                event(
                    "DEPLOYMENT_SUCCEEDED",
                    request.version()
                );

            } catch (RuntimeException exception) {
                instances.clear();
                instances.addAll(oldInstances);

                traffic.restore(oldTraffic);

                activeVersion = oldVersion;
                previousVersion = oldPrevious;

                state = DeploymentState.FAILED;
                error = exception.getMessage();

                event("DEPLOYMENT_FAILED", error);

            } finally {
                deploymentLock.unlock();
            }

            DeploymentReport report = new DeploymentReport(
                id,
                request.application(),
                request.version(),
                request.strategy(),
                state,
                oldVersion,
                error,
                started,
                Instant.now()
            );

            history.add(report);

            return report;
        }

        void rollback() {
            if (previousVersion == null ||
                previousVersion.isBlank()) {
                throw new DeploymentException(
                    "No previous release available"
                );
            }

            if (!deploymentLock.tryLock()) {
                throw new DeploymentException(
                    "Cannot rollback during another deployment"
                );
            }

            try {
                List<Instance> replacement =
                    provisionEnvironment(previousVersion, 4);

                if (policy.requireHealthChecks()) {
                    health.requireHealthy(replacement);
                }

                String current = activeVersion;

                instances.clear();
                instances.addAll(replacement);

                activeVersion = previousVersion;
                previousVersion = current;

                traffic.switchTo(activeVersion);

                event("ROLLBACK_COMPLETED", activeVersion);

            } finally {
                deploymentLock.unlock();
            }
        }

        void printReport() {
            System.out.println("\nActive version: " + activeVersion);
            System.out.println("Previous version: " + previousVersion);

            System.out.println("\nTraffic allocation:");

            traffic.snapshot().forEach(
                (version, weight) ->
                    System.out.println(version + " = " + weight + "%")
            );

            System.out.println("\nInfrastructure:");

            instances.forEach(System.out::println);

            System.out.println("\nDeployment history:");

            history.forEach(System.out::println);

            System.out.println("\nEvents:");

            events.forEach(System.out::println);
        }

        String activeVersion() {
            return activeVersion;
        }

        List<DeploymentReport> history() {
            return Collections.unmodifiableList(history);
        }
    }

    public static void main(String[] args) {

        DeploymentPolicy policy = new DeploymentPolicy(
            12,
            1,
            1,
            1.0,
            true,
            true,
            true
        );

        DeploymentService service = new DeploymentService(
            "1.0.0",
            policy
        );

        List<DeploymentRequest> requests = List.of(
            new DeploymentRequest(
                "payment-service",
                "1.1.0",
                Strategy.ROLLING,
                4,
                1,
                100
            ),
            new DeploymentRequest(
                "payment-service",
                "1.2.0",
                Strategy.BLUE_GREEN,
                4,
                1,
                100
            ),
            new DeploymentRequest(
                "payment-service",
                "1.3.0",
                Strategy.RECREATE,
                4,
                1,
                100
            )
        );

        for (DeploymentRequest request : requests) {
            DeploymentReport report = service.deploy(request);

            System.out.println(
                report.strategy() + " -> " +
                report.state() + " -> " +
                report.version()
            );

            if (report.error() != null) {
                System.err.println(report.error());
            }
        }

        service.printReport();

        if (!service.activeVersion().equals("1.3.0")) {
            throw new AssertionError(
                "Unexpected deployment version"
            );
        }

        service.rollback();

        if (!service.activeVersion().equals("1.2.0")) {
            throw new AssertionError(
                "Rollback verification failed"
            );
        }

        System.out.println("\nAll Java 17 tests passed.");
    }
}

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class ContainerHealthGovernance {

    enum HealthStatus {
        STARTING,
        HEALTHY,
        UNHEALTHY
    }

    enum ContainerState {
        CREATED,
        RUNNING,
        STOPPED,
        RESTARTING
    }

    enum RestartPolicy {
        NO,
        ON_FAILURE,
        ALWAYS,
        UNLESS_STOPPED
    }

    record ResourceLimits(int cpuMillicores, int memoryMb) {
        ResourceLimits {
            if (cpuMillicores <= 0) {
                throw new IllegalArgumentException(
                    "CPU limit must be positive"
                );
            }

            if (memoryMb <= 0) {
                throw new IllegalArgumentException(
                    "Memory limit must be positive"
                );
            }
        }
    }

    record HealthCheckPolicy(
        int intervalSeconds,
        int timeoutSeconds,
        int retries,
        int startPeriodSeconds
    ) {
        HealthCheckPolicy {
            if (intervalSeconds <= 0) {
                throw new IllegalArgumentException(
                    "Health interval must be positive"
                );
            }

            if (timeoutSeconds <= 0 ||
                timeoutSeconds > intervalSeconds) {
                throw new IllegalArgumentException(
                    "Invalid health-check timeout"
                );
            }

            if (retries < 1) {
                throw new IllegalArgumentException(
                    "Retries must be at least one"
                );
            }

            if (startPeriodSeconds < 0) {
                throw new IllegalArgumentException(
                    "Start period cannot be negative"
                );
            }
        }
    }

    record HealthResult(
        boolean success,
        long latencyMs,
        String message
    ) {
        HealthResult {
            Objects.requireNonNull(message);
            if (latencyMs < 0) {
                throw new IllegalArgumentException(
                    "Latency cannot be negative"
                );
            }
        }
    }

    record StatusCheck(String name, boolean passed) {}

    static final class ContainerFailure extends Exception {
        ContainerFailure(String message) {
            super(message);
        }
    }

    static final class Container {
        private final String name;
        private final String image;
        private final ResourceLimits resources;
        private final HealthCheckPolicy healthPolicy;
        private final RestartPolicy restartPolicy;
        private final int maxRestarts;

        private ContainerState state = ContainerState.CREATED;
        private HealthStatus health = HealthStatus.STARTING;
        private int consecutiveFailures;
        private int restartCount;
        private boolean manuallyStopped;

        Container(
            String name,
            String image,
            ResourceLimits resources,
            HealthCheckPolicy healthPolicy,
            RestartPolicy restartPolicy,
            int maxRestarts
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Container name is required"
                );
            }

            if (image == null || image.isBlank()) {
                throw new IllegalArgumentException(
                    "Container image is required"
                );
            }

            if (maxRestarts < 0) {
                throw new IllegalArgumentException(
                    "Maximum restarts cannot be negative"
                );
            }

            this.name = name;
            this.image = image;
            this.resources = Objects.requireNonNull(resources);
            this.healthPolicy =
                Objects.requireNonNull(healthPolicy);
            this.restartPolicy =
                Objects.requireNonNull(restartPolicy);
            this.maxRestarts = maxRestarts;
        }

        void start() {
            state = ContainerState.RUNNING;
            health = HealthStatus.STARTING;
            consecutiveFailures = 0;
            manuallyStopped = false;
        }

        void stop(boolean manual) {
            state = ContainerState.STOPPED;
            manuallyStopped = manual;
        }

        void evaluateHealth(
            HealthResult result,
            int elapsedSeconds
        ) throws ContainerFailure {
            if (state != ContainerState.RUNNING) {
                throw new ContainerFailure(
                    "Container is not running: " + name
                );
            }

            if (elapsedSeconds < healthPolicy.startPeriodSeconds()) {
                health = HealthStatus.STARTING;
                consecutiveFailures = 0;
                return;
            }

            boolean valid =
                result.success() &&
                result.latencyMs() <=
                    healthPolicy.timeoutSeconds() * 1000L;

            if (valid) {
                health = HealthStatus.HEALTHY;
                consecutiveFailures = 0;
                return;
            }

            consecutiveFailures++;

            if (consecutiveFailures >= healthPolicy.retries()) {
                health = HealthStatus.UNHEALTHY;
            }
        }

        boolean shouldRestart(int exitCode) {
            if (manuallyStopped || restartCount >= maxRestarts) {
                return false;
            }

            return switch (restartPolicy) {
                case NO -> false;
                case ALWAYS, UNLESS_STOPPED -> true;
                case ON_FAILURE -> exitCode != 0;
            };
        }

        boolean restart(int exitCode) {
            if (!shouldRestart(exitCode)) {
                return false;
            }

            state = ContainerState.RESTARTING;
            restartCount++;
            start();
            return true;
        }

        String name() {
            return name;
        }

        ContainerState state() {
            return state;
        }

        HealthStatus health() {
            return health;
        }

        int restartCount() {
            return restartCount;
        }

        ResourceLimits resources() {
            return resources;
        }
    }

    interface HealthPolicyEvaluator {
        boolean eligibleForMergeLikeRecovery(
            Container container,
            List<StatusCheck> checks
        );
    }

    static final class RuntimePolicyEvaluator
        implements HealthPolicyEvaluator {

        @Override
        public boolean eligibleForMergeLikeRecovery(
            Container container,
            List<StatusCheck> checks
        ) {
            if (container.state() != ContainerState.RUNNING) {
                return false;
            }

            if (container.health() != HealthStatus.HEALTHY) {
                return false;
            }

            return checks.stream().allMatch(StatusCheck::passed);
        }
    }

    static final class ContainerService {
        private final Map<ContainerState, Integer> stateCounts =
            new EnumMap<>(ContainerState.class);

        void register(Container container) {
            stateCounts.merge(
                container.state(),
                1,
                Integer::sum
            );
        }

        void start(Container container) {
            container.start();
        }

        void recover(Container container) {
            if (container.health() == HealthStatus.UNHEALTHY) {
                container.restart(1);
            }
        }

        void print(Container container) {
            System.out.printf(
                "%-10s state=%-10s health=%-10s restarts=%d " +
                "cpu=%dm memory=%dMB%n",
                container.name(),
                container.state(),
                container.health(),
                container.restartCount(),
                container.resources().cpuMillicores(),
                container.resources().memoryMb()
            );
        }
    }

    public static void main(String[] args)
        throws ContainerFailure {

        Container api = new Container(
            "api",
            "example/api:2.4",
            new ResourceLimits(500, 512),
            new HealthCheckPolicy(5, 2, 3, 5),
            RestartPolicy.UNLESS_STOPPED,
            5
        );

        Container worker = new Container(
            "worker",
            "example/worker:4.1",
            new ResourceLimits(750, 1024),
            new HealthCheckPolicy(10, 3, 2, 0),
            RestartPolicy.ON_FAILURE,
            2
        );

        ContainerService service = new ContainerService();
        service.register(api);
        service.register(worker);

        service.start(api);
        service.start(worker);

        api.evaluateHealth(
            new HealthResult(
                true,
                42,
                "HTTP 200 /health"
            ),
            8
        );

        for (int i = 0; i < 5; i++) {
            worker.evaluateHealth(
                new HealthResult(
                    false,
                    5000,
                    "database dependency unavailable"
                ),
                20
            );

            service.recover(worker);
        }

        RuntimePolicyEvaluator evaluator =
            new RuntimePolicyEvaluator();

        List<StatusCheck> checks = new ArrayList<>();
        checks.add(new StatusCheck("cpu-budget", true));
        checks.add(new StatusCheck("memory-budget", true));

        boolean eligible =
            evaluator.eligibleForMergeLikeRecovery(
                api,
                checks
            );

        System.out.println("API operational policy: " + eligible);
        service.print(api);
        service.print(worker);

        api.stop(true);

        if (!api.shouldRestart(1)) {
            System.out.println(
                "Manual stop correctly suppresses restart."
            );
        }

        try {
            new ResourceLimits(0, 512);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "Rejected invalid resources: " + ex.getMessage()
            );
        }

        /*
         * Enterprise design decision:
         * resource limits are infrastructure constraints,
         * health status is application state, and restart policy
         * determines recovery behavior. Keeping these concepts
         * separate avoids treating a healthy process as proof that
         * the service has sufficient resources.
         */
        System.out.println(
            "Container governance evaluation completed."
        );
    }
}

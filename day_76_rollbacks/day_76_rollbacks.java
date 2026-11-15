import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

/*
 * Automated Rollback Strategies and Release Recovery
 *
 * Java 17
 * Enterprise-oriented release governance and recovery engine.
 */

public class ReleaseRecovery {

    enum ReleaseState {
        CREATED,
        DEPLOYING,
        ACTIVE,
        FAILED,
        ROLLING_BACK,
        ROLLED_BACK,
        RECOVERED
    }

    enum DeploymentStrategy {
        IMMEDIATE,
        BLUE_GREEN,
        CANARY,
        PROGRESSIVE
    }

    enum ReviewStatus {
        PASSED,
        FAILED
    }

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static class RecoveryException extends RuntimeException {
        RecoveryException(String message) {
            super(message);
        }
    }

    record Release(
        UUID id,
        String version,
        String artifactDigest,
        Instant createdAt
    ) {
        private static final Pattern DIGEST =
            Pattern.compile("^sha256:[a-fA-F0-9]{64}$");

        Release {
            Objects.requireNonNull(id);
            Objects.requireNonNull(createdAt);

            if (version == null || version.isBlank()) {
                throw new IllegalArgumentException("Version is required");
            }

            if (artifactDigest == null ||
                !DIGEST.matcher(artifactDigest).matches()) {
                throw new IllegalArgumentException("Invalid artifact digest");
            }
        }

        static Release create(String version, String digest) {
            return new Release(
                UUID.randomUUID(),
                version,
                digest,
                Instant.now()
            );
        }
    }

    record HealthMetrics(
        double errorRate,
        double latencyMs,
        double availability,
        int failedChecks
    ) {
        HealthMetrics {
            if (!Double.isFinite(errorRate) ||
                errorRate < 0 || errorRate > 1) {
                throw new IllegalArgumentException("Invalid error rate");
            }

            if (!Double.isFinite(latencyMs) || latencyMs < 0) {
                throw new IllegalArgumentException("Invalid latency");
            }

            if (!Double.isFinite(availability) ||
                availability < 0 || availability > 1) {
                throw new IllegalArgumentException("Invalid availability");
            }

            if (failedChecks < 0) {
                throw new IllegalArgumentException("Invalid failed checks");
            }
        }
    }

    record HealthDecision(
        boolean healthy,
        List<String> violations
    ) {
        HealthDecision {
            violations = List.copyOf(violations);
        }
    }

    record AuditEvent(
        Instant timestamp,
        String action,
        UUID releaseId,
        String detail
    ) {}

    record ApprovalPolicy(
        int requiredHealthyWindows,
        double maxErrorRate,
        double maxLatencyMs,
        double minAvailability,
        int maxFailedChecks
    ) {
        ApprovalPolicy {
            if (requiredHealthyWindows < 1 ||
                maxErrorRate < 0 || maxErrorRate > 1 ||
                maxLatencyMs <= 0 ||
                minAvailability <= 0 || minAvailability > 1 ||
                maxFailedChecks < 0) {
                throw new IllegalArgumentException("Invalid approval policy");
            }
        }

        HealthDecision evaluate(HealthMetrics metrics) {
            List<String> violations = new ArrayList<>();

            if (metrics.errorRate() > maxErrorRate) {
                violations.add("ERROR_RATE");
            }

            if (metrics.latencyMs() > maxLatencyMs) {
                violations.add("LATENCY");
            }

            if (metrics.availability() < minAvailability) {
                violations.add("AVAILABILITY");
            }

            if (metrics.failedChecks() > maxFailedChecks) {
                violations.add("FAILED_CHECKS");
            }

            return new HealthDecision(
                violations.isEmpty(),
                violations
            );
        }
    }

    static final class Deployment {
        private final Release release;
        private ReleaseState state = ReleaseState.CREATED;
        private int trafficPercentage;
        private final List<HealthMetrics> history = new ArrayList<>();
        private String failureReason;

        Deployment(Release release) {
            this.release = release;
        }

        Release release() {
            return release;
        }

        ReleaseState state() {
            return state;
        }

        int trafficPercentage() {
            return trafficPercentage;
        }

        List<HealthMetrics> history() {
            return List.copyOf(history);
        }
    }

    interface ReleaseListener {
        void onEvent(AuditEvent event);
    }

    static final class ReleaseRegistry {
        private final Map<UUID, Deployment> deployments = new HashMap<>();

        void register(Release release) {
            if (deployments.putIfAbsent(
                release.id(),
                new Deployment(release)
            ) != null) {
                throw new DeploymentException("Duplicate release");
            }
        }

        Deployment get(UUID id) {
            Deployment deployment = deployments.get(id);

            if (deployment == null) {
                throw new DeploymentException("Unknown release");
            }

            return deployment;
        }

        List<Deployment> all() {
            return List.copyOf(deployments.values());
        }
    }

    static final class ReleaseService {
        private final ApprovalPolicy policy;
        private final ReleaseRegistry registry = new ReleaseRegistry();
        private final List<AuditEvent> audit = new ArrayList<>();
        private final List<ReleaseListener> listeners = new ArrayList<>();

        private UUID activeRelease;
        private UUID previousRelease;
        private boolean deploymentRunning;

        ReleaseService(ApprovalPolicy policy) {
            this.policy = policy;
        }

        void addListener(ReleaseListener listener) {
            listeners.add(Objects.requireNonNull(listener));
        }

        private void emit(String action, UUID id, String detail) {
            AuditEvent event = new AuditEvent(
                Instant.now(),
                action,
                id,
                detail
            );

            audit.add(event);

            for (ReleaseListener listener : listeners) {
                try {
                    listener.onEvent(event);
                } catch (RuntimeException exception) {
                    // Monitoring failures must not silently reverse deployment state.
                    System.err.println(
                        "Audit listener failure: " + exception.getMessage()
                    );
                }
            }
        }

        UUID register(String version, String digest) {
            Release release = Release.create(version, digest);
            registry.register(release);

            emit("RELEASE_REGISTERED", release.id(), version);
            return release.id();
        }

        private void setTraffic(UUID id, int percentage) {
            if (percentage < 0 || percentage > 100) {
                throw new IllegalArgumentException("Invalid traffic percentage");
            }

            Deployment deployment = registry.get(id);
            deployment.trafficPercentage = percentage;

            emit("TRAFFIC_CHANGED", id, percentage + "%");
        }

        private void validate(UUID id, HealthMetrics metrics) {
            HealthDecision decision = policy.evaluate(metrics);

            registry.get(id).history.add(metrics);

            emit(
                "HEALTH_EVALUATED",
                id,
                decision.violations().toString()
            );

            if (!decision.healthy()) {
                throw new DeploymentException(
                    "Health gate failed: " + decision.violations()
                );
            }
        }

        void deploy(
            UUID id,
            DeploymentStrategy strategy,
            List<HealthMetrics> windows
        ) {
            if (deploymentRunning) {
                throw new DeploymentException("Another deployment is running");
            }

            Deployment deployment = registry.get(id);

            if (deployment.state != ReleaseState.CREATED &&
                deployment.state != ReleaseState.ROLLED_BACK) {
                throw new DeploymentException("Invalid state transition");
            }

            List<Integer> stages = switch (strategy) {
                case IMMEDIATE, BLUE_GREEN -> List.of(100);
                case CANARY -> List.of(5, 25, 50, 100);
                case PROGRESSIVE -> List.of(10, 30, 60, 100);
            };

            if (strategy == DeploymentStrategy.BLUE_GREEN) {
                if (windows.isEmpty()) {
                    throw new DeploymentException("Missing health evidence");
                }
            } else if (windows.size() < stages.size()) {
                throw new DeploymentException("Insufficient health windows");
            }

            deploymentRunning = true;
            deployment.state = ReleaseState.DEPLOYING;

            emit("DEPLOYMENT_STARTED", id, strategy.name());

            try {
                if (strategy == DeploymentStrategy.BLUE_GREEN) {
                    // Verify the inactive environment before the traffic switch.
                    for (HealthMetrics metrics : windows) {
                        validate(id, metrics);
                    }

                    setTraffic(id, 100);

                } else {
                    for (int i = 0; i < stages.size(); i++) {
                        setTraffic(id, stages.get(i));
                        validate(id, windows.get(i));
                    }
                }

                if (activeRelease != null && !activeRelease.equals(id)) {
                    previousRelease = activeRelease;
                }

                activeRelease = id;
                deployment.state = ReleaseState.ACTIVE;

                emit("DEPLOYMENT_ACTIVATED", id, deployment.release.version());

            } catch (RuntimeException exception) {
                deployment.state = ReleaseState.FAILED;
                deployment.failureReason = exception.getMessage();

                emit("DEPLOYMENT_FAILED", id, exception.getMessage());

                if (previousRelease != null) {
                    rollback(id, previousRelease);
                }

                throw exception;

            } finally {
                deploymentRunning = false;
            }
        }

        void rollback(UUID failedId, UUID targetId) {
            Deployment failed = registry.get(failedId);
            Deployment target = registry.get(targetId);

            if (target.state != ReleaseState.ACTIVE &&
                target.state != ReleaseState.RECOVERED &&
                target.state != ReleaseState.ROLLED_BACK) {
                throw new RecoveryException("Unvalidated rollback target");
            }

            failed.state = ReleaseState.ROLLING_BACK;

            emit("ROLLBACK_STARTED", failedId, targetId.toString());

            try {
                setTraffic(failedId, 0);
                setTraffic(targetId, 100);

                activeRelease = targetId;
                failed.state = ReleaseState.ROLLED_BACK;

                emit("ROLLBACK_COMPLETED", failedId, targetId.toString());

            } catch (RuntimeException exception) {
                failed.state = ReleaseState.FAILED;
                throw new RecoveryException(
                    "Rollback failed: " + exception.getMessage()
                );
            }
        }

        UUID recoverForward(
            UUID failedId,
            String version,
            String digest,
            List<HealthMetrics> windows
        ) {
            Deployment failed = registry.get(failedId);

            if (failed.state != ReleaseState.FAILED &&
                failed.state != ReleaseState.ROLLED_BACK) {
                throw new RecoveryException("Invalid recovery state");
            }

            UUID replacementId = register(version, digest);

            try {
                deploy(
                    replacementId,
                    DeploymentStrategy.CANARY,
                    windows
                );

                Deployment replacement = registry.get(replacementId);
                replacement.state = ReleaseState.RECOVERED;

                emit(
                    "FORWARD_RECOVERY_COMPLETED",
                    replacementId,
                    failedId.toString()
                );

                return replacementId;

            } catch (RuntimeException exception) {
                emit(
                    "FORWARD_RECOVERY_FAILED",
                    replacementId,
                    exception.getMessage()
                );

                throw exception;
            }
        }

        void report() {
            System.out.println("\nENTERPRISE RELEASE REPORT");

            System.out.printf(
                "%-12s %-16s %-12s %-12s%n",
                "VERSION",
                "STATE",
                "TRAFFIC",
                "OBSERVATIONS"
            );

            registry.all().stream()
                .sorted((a, b) -> a.release().version()
                    .compareTo(b.release().version()))
                .forEach(d -> System.out.printf(
                    "%-12s %-16s %-12s %-12d%n",
                    d.release().version(),
                    d.state(),
                    d.trafficPercentage() + "%",
                    d.history().size()
                ));

            System.out.println("Audit events: " + audit.size());
            System.out.println("Active release: " + activeRelease);
        }

        UUID activeRelease() {
            return activeRelease;
        }

        ReleaseState state(UUID id) {
            return registry.get(id).state;
        }
    }

    public static void main(String[] args) {
        ApprovalPolicy policy = new ApprovalPolicy(
            2,
            0.05,
            500,
            0.99,
            2
        );

        ReleaseService service = new ReleaseService(policy);

        service.addListener(event ->
            System.out.printf(
                "[%s] %s %s%n",
                event.timestamp(),
                event.action(),
                event.detail()
            )
        );

        List<HealthMetrics> healthy = List.of(
            new HealthMetrics(0.01, 120, 0.999, 0),
            new HealthMetrics(0.02, 150, 0.998, 0),
            new HealthMetrics(0.015, 130, 0.999, 0),
            new HealthMetrics(0.01, 125, 0.999, 0)
        );

        UUID v1 = service.register(
            "1.0.0",
            "sha256:" + "a".repeat(64)
        );

        service.deploy(
            v1,
            DeploymentStrategy.IMMEDIATE,
            healthy.subList(0, 2)
        );

        UUID v2 = service.register(
            "2.0.0",
            "sha256:" + "b".repeat(64)
        );

        List<HealthMetrics> degraded = List.of(
            healthy.get(0),
            healthy.get(1),
            new HealthMetrics(0.20, 1200, 0.90, 5),
            healthy.get(3)
        );

        try {
            service.deploy(
                v2,
                DeploymentStrategy.CANARY,
                degraded
            );
        } catch (DeploymentException exception) {
            System.out.println(
                "Automatic rollback: " + exception.getMessage()
            );
        }

        if (!Objects.equals(service.activeRelease(), v1)) {
            throw new IllegalStateException("Rollback verification failed");
        }

        UUID v3 = service.recoverForward(
            v2,
            "2.0.1",
            "sha256:" + "c".repeat(64),
            healthy
        );

        if (service.state(v3) != ReleaseState.RECOVERED) {
            throw new IllegalStateException("Recovery verification failed");
        }

        service.report();
    }
}

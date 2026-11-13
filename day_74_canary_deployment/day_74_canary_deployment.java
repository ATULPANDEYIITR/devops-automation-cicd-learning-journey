import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/**
 * Enterprise Canary Release Governance System.
 * Requires Java 17.
 */
public class CanaryDeploymentEnterprise {

    enum State {
        CREATED,
        RUNNING,
        PROMOTED,
        ROLLED_BACK,
        FAILED
    }

    enum Environment {
        STAGING,
        PRODUCTION
    }

    enum CheckType {
        ERROR_RATE,
        LATENCY,
        BASELINE_REGRESSION,
        MINIMUM_SAMPLE
    }

    record Metrics(
        long requests,
        long errors,
        double p95LatencyMs
    ) {
        Metrics {
            if (requests < 0 || errors < 0 || errors > requests) {
                throw new IllegalArgumentException(
                    "Invalid request or error counts."
                );
            }

            if (!Double.isFinite(p95LatencyMs) ||
                p95LatencyMs < 0) {
                throw new IllegalArgumentException(
                    "Invalid latency."
                );
            }
        }

        double errorRate() {
            return requests == 0
                ? 1.0
                : (double) errors / requests;
        }
    }

    record ReleasePolicy(
        List<Integer> stages,
        double maximumErrorRate,
        double maximumLatencyMs,
        double maximumRegression,
        long minimumRequests,
        int requiredConsecutivePasses,
        boolean manualApprovalRequired
    ) {
        ReleasePolicy {
            stages = List.copyOf(stages);

            if (stages.isEmpty() || stages.get(stages.size() - 1) != 100) {
                throw new IllegalArgumentException(
                    "Stages must end at 100%."
                );
            }

            int previous = 0;

            for (int stage : stages) {
                if (stage <= previous || stage > 100) {
                    throw new IllegalArgumentException(
                        "Stages must be strictly increasing."
                    );
                }
                previous = stage;
            }

            if (maximumErrorRate <= 0 ||
                maximumErrorRate >= 1 ||
                maximumLatencyMs <= 0 ||
                maximumRegression < 0 ||
                minimumRequests < 1 ||
                requiredConsecutivePasses < 1) {
                throw new IllegalArgumentException(
                    "Invalid release policy."
                );
            }
        }

        static ReleasePolicy productionDefaults() {
            return new ReleasePolicy(
                List.of(5, 10, 25, 50, 100),
                0.02,
                500,
                0.015,
                100,
                1,
                false
            );
        }
    }

    record PolicyDecision(
        boolean permitted,
        Set<CheckType> failures,
        String explanation
    ) {
        PolicyDecision {
            failures = Collections.unmodifiableSet(
                EnumSet.copyOf(
                    failures.isEmpty()
                        ? EnumSet.noneOf(CheckType.class)
                        : failures
                )
            );
        }
    }

    record AuditEvent(
        Instant timestamp,
        long revision,
        String event,
        String details
    ) {}

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    interface HealthEvaluator {
        PolicyDecision evaluate(
            Metrics candidate,
            Metrics baseline,
            ReleasePolicy policy
        );
    }

    static final class ProductionHealthEvaluator
        implements HealthEvaluator {

        @Override
        public PolicyDecision evaluate(
            Metrics candidate,
            Metrics baseline,
            ReleasePolicy policy
        ) {
            EnumSet<CheckType> failures =
                EnumSet.noneOf(CheckType.class);

            if (candidate.requests() < policy.minimumRequests()) {
                failures.add(CheckType.MINIMUM_SAMPLE);
            }

            if (candidate.errorRate() > policy.maximumErrorRate()) {
                failures.add(CheckType.ERROR_RATE);
            }

            if (candidate.p95LatencyMs() > policy.maximumLatencyMs()) {
                failures.add(CheckType.LATENCY);
            }

            if (candidate.errorRate() - baseline.errorRate() >
                policy.maximumRegression()) {
                failures.add(CheckType.BASELINE_REGRESSION);
            }

            return new PolicyDecision(
                failures.isEmpty(),
                failures,
                failures.isEmpty()
                    ? "All production health policies passed."
                    : "One or more health policies failed."
            );
        }
    }

    static final class Release {

        private final String releaseId;
        private final String application;
        private final String version;
        private final String previousVersion;
        private final Environment environment;
        private final ReleasePolicy policy;
        private final Metrics baseline;

        private final ReentrantLock lock = new ReentrantLock();
        private final List<AuditEvent> history = new ArrayList<>();

        private State state = State.CREATED;
        private int trafficPercent;
        private int stageIndex;
        private int consecutivePasses;
        private long revision;
        private boolean manuallyApproved;

        Release(
            String releaseId,
            String application,
            String version,
            String previousVersion,
            Environment environment,
            ReleasePolicy policy,
            Metrics baseline
        ) {
            this.releaseId = Objects.requireNonNull(releaseId);
            this.application = Objects.requireNonNull(application);
            this.version = Objects.requireNonNull(version);
            this.previousVersion = Objects.requireNonNull(previousVersion);
            this.environment = Objects.requireNonNull(environment);
            this.policy = Objects.requireNonNull(policy);
            this.baseline = Objects.requireNonNull(baseline);

            if (releaseId.isBlank() ||
                application.isBlank() ||
                version.isBlank()) {
                throw new IllegalArgumentException(
                    "Release identity fields cannot be blank."
                );
            }

            if (baseline.requests() < policy.minimumRequests()) {
                throw new IllegalArgumentException(
                    "Baseline has insufficient observations."
                );
            }

            record("REGISTERED", version);
        }

        private void record(String event, String details) {
            history.add(new AuditEvent(
                Instant.now(),
                ++revision,
                event,
                details
            ));
        }

        void approveManually(String approver) {
            lock.lock();

            try {
                if (state != State.RUNNING || approver.isBlank()) {
                    throw new DeploymentException(
                        "Manual approval is invalid."
                    );
                }

                manuallyApproved = true;
                record("MANUAL_APPROVAL", approver);
            } finally {
                lock.unlock();
            }
        }

        void start() {
            lock.lock();

            try {
                if (state != State.CREATED) {
                    throw new DeploymentException(
                        "Release cannot be started twice."
                    );
                }

                state = State.RUNNING;
                stageIndex = 0;
                trafficPercent = policy.stages().get(0);

                record("STARTED", trafficPercent + "%");
            } finally {
                lock.unlock();
            }
        }

        State observe(
            Metrics metrics,
            HealthEvaluator evaluator
        ) {
            lock.lock();

            try {
                if (state != State.RUNNING) {
                    throw new DeploymentException(
                        "Release is not active."
                    );
                }

                PolicyDecision decision = evaluator.evaluate(
                    metrics,
                    baseline,
                    policy
                );

                if (!decision.permitted()) {
                    rollbackInternal(decision.failures().toString());
                    return state;
                }

                consecutivePasses++;

                record("HEALTH_PASSED", decision.explanation());

                if (consecutivePasses <
                    policy.requiredConsecutivePasses()) {
                    return state;
                }

                if (stageIndex + 1 >= policy.stages().size()) {
                    if (policy.manualApprovalRequired() &&
                        !manuallyApproved) {
                        record(
                            "AWAITING_MANUAL_APPROVAL",
                            "Automatic promotion suspended."
                        );
                        return state;
                    }

                    state = State.PROMOTED;
                    trafficPercent = 100;
                    record("PROMOTED", version);
                } else {
                    stageIndex++;
                    trafficPercent = policy.stages().get(stageIndex);

                    record(
                        "TRAFFIC_INCREASED",
                        trafficPercent + "%"
                    );
                }

                consecutivePasses = 0;
                return state;

            } finally {
                lock.unlock();
            }
        }

        void rollback(String reason) {
            lock.lock();

            try {
                if (state != State.RUNNING) {
                    throw new DeploymentException(
                        "Only running releases can roll back."
                    );
                }

                rollbackInternal(reason);
            } finally {
                lock.unlock();
            }
        }

        private void rollbackInternal(String reason) {
            state = State.ROLLED_BACK;
            trafficPercent = 0;
            consecutivePasses = 0;

            record("ROLLED_BACK", reason);
        }

        State state() {
            return state;
        }

        int trafficPercent() {
            return trafficPercent;
        }

        String version() {
            return version;
        }

        String previousVersion() {
            return previousVersion;
        }

        String releaseId() {
            return releaseId;
        }

        Environment environment() {
            return environment;
        }

        List<AuditEvent> history() {
            return List.copyOf(history);
        }
    }

    static final class DeploymentService {

        private final Map<String, Release> releases = new HashMap<>();
        private final Map<String, String> activeVersions = new HashMap<>();
        private final HealthEvaluator evaluator =
            new ProductionHealthEvaluator();

        synchronized Release create(
            String id,
            String application,
            String version,
            Environment environment,
            ReleasePolicy policy,
            Metrics baseline
        ) {
            if (releases.containsKey(id)) {
                throw new DeploymentException(
                    "Duplicate release identifier."
                );
            }

            String active = activeVersions.getOrDefault(
                application,
                "v1.0.0"
            );

            Release release = new Release(
                id,
                application,
                version,
                active,
                environment,
                policy,
                baseline
            );

            releases.put(id, release);
            return release;
        }

        void start(String id) {
            get(id).start();
        }

        synchronized State evaluate(String id, Metrics metrics) {
            Release release = get(id);
            State state = release.observe(metrics, evaluator);

            synchronizeActiveVersion(release);
            return state;
        }

        synchronized void rollback(String id, String reason) {
            Release release = get(id);
            release.rollback(reason);
            synchronizeActiveVersion(release);
        }

        private void synchronizeActiveVersion(Release release) {
            if (release.state() == State.PROMOTED) {
                activeVersions.put(
                    release.application,
                    release.version()
                );
            } else if (release.state() == State.ROLLED_BACK) {
                activeVersions.put(
                    release.application,
                    release.previousVersion()
                );
            }
        }

        synchronized String activeVersion(String application) {
            return activeVersions.getOrDefault(application, "v1.0.0");
        }

        Release get(String id) {
            Release release = releases.get(id);

            if (release == null) {
                throw new DeploymentException("Unknown release.");
            }

            return release;
        }

        List<Release> releases() {
            return List.copyOf(releases.values());
        }
    }

    static final class RequestRouter {

        private final DeploymentService service;

        RequestRouter(DeploymentService service) {
            this.service = service;
        }

        String route(String requestId, Release release) {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                    "Request identifier is required."
                );
            }

            if (release.state() != State.RUNNING) {
                return service.activeVersion(release.application);
            }

            int bucket = Math.floorMod(
                requestId.hashCode(),
                100
            );

            return bucket < release.trafficPercent()
                ? release.version()
                : release.previousVersion();
        }
    }

    private static void runTests() {
        DeploymentService service = new DeploymentService();

        ReleasePolicy policy = ReleasePolicy.productionDefaults();

        Metrics baseline = new Metrics(5000, 50, 180);

        Release successful = service.create(
            "release-001",
            "payment-service",
            "v2.0.0",
            Environment.PRODUCTION,
            policy,
            baseline
        );

        service.start(successful.releaseId());

        for (int i = 0; i < 5; i++) {
            service.evaluate(
                successful.releaseId(),
                new Metrics(1000, 12, 200)
            );
        }

        if (successful.state() != State.PROMOTED ||
            !service.activeVersion("payment-service").equals("v2.0.0")) {
            throw new AssertionError("Promotion test failed.");
        }

        Release failed = service.create(
            "release-002",
            "payment-service",
            "v3.0.0",
            Environment.PRODUCTION,
            policy,
            baseline
        );

        service.start(failed.releaseId());

        service.evaluate(
            failed.releaseId(),
            new Metrics(1000, 200, 900)
        );

        if (failed.state() != State.ROLLED_BACK ||
            !service.activeVersion("payment-service").equals("v2.0.0")) {
            throw new AssertionError("Rollback test failed.");
        }

        boolean rejected = false;

        try {
            service.evaluate(
                failed.releaseId(),
                new Metrics(1000, 0, 100)
            );
        } catch (DeploymentException exception) {
            rejected = true;
        }

        if (!rejected) {
            throw new AssertionError("Invalid transition accepted.");
        }

        System.out.println("All Java 17 tests passed.");
    }

    public static void main(String[] args) {
        try {
            runTests();

            DeploymentService service = new DeploymentService();

            Release release = service.create(
                "production-2026-11",
                "inventory-service",
                "v2.1.0",
                Environment.PRODUCTION,
                ReleasePolicy.productionDefaults(),
                new Metrics(10000, 100, 190)
            );

            RequestRouter router = new RequestRouter(service);

            service.start(release.releaseId());

            List<Metrics> observations = List.of(
                new Metrics(1000, 12, 210),
                new Metrics(1000, 14, 220),
                new Metrics(1000, 13, 225),
                new Metrics(1000, 11, 230),
                new Metrics(1000, 15, 240)
            );

            for (Metrics metrics : observations) {
                if (release.state() != State.RUNNING) {
                    break;
                }

                service.evaluate(release.releaseId(), metrics);

                System.out.println(
                    "State=" + release.state() +
                    ", traffic=" + release.trafficPercent() + "%"
                );
            }

            System.out.println("\nRequest routing:");

            List.of(
                "customer-001",
                "customer-002",
                "customer-003"
            ).forEach(client ->
                System.out.println(
                    client + " -> " + router.route(client, release)
                )
            );

            System.out.println("\nAudit history:");

            release.history().forEach(event ->
                System.out.println(
                    event.timestamp() + " | " +
                    event.event() + " | " +
                    event.details()
                )
            );

        } catch (RuntimeException exception) {
            System.err.println(
                "Enterprise deployment failure: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}

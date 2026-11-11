import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.locks.ReentrantLock;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Enterprise Deployment Environment Governance System.
 *
 * Java 17
 *
 * Models environment policies, artifact promotion, release approvals,
 * deployment state transitions, health verification, audit history,
 * and rollback.
 */
public class DeploymentGovernance {

    enum Environment {
        DEVELOPMENT,
        QA,
        STAGING,
        PRODUCTION
    }

    enum DeploymentStatus {
        PENDING,
        SUCCEEDED,
        FAILED,
        ROLLED_BACK
    }

    enum DeploymentStrategy {
        ROLLING,
        BLUE_GREEN,
        CANARY
    }

    enum Permission {
        DEPLOY_DEVELOPMENT,
        DEPLOY_QA,
        DEPLOY_STAGING,
        DEPLOY_PRODUCTION,
        APPROVE_RELEASE,
        ROLLBACK
    }

    static final List<Environment> PROMOTION_ORDER = List.of(
        Environment.DEVELOPMENT,
        Environment.QA,
        Environment.STAGING,
        Environment.PRODUCTION
    );

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static class PolicyException extends DeploymentException {
        PolicyException(String message) {
            super(message);
        }
    }

    record Artifact(
        String name,
        String version,
        String checksum,
        String commitSha
    ) {
        private static final Pattern VERSION =
            Pattern.compile("\\d+\\.\\d+\\.\\d+(?:-[a-zA-Z0-9.-]+)?");

        private static final Pattern CHECKSUM =
            Pattern.compile("[a-f0-9]{64}");

        Artifact {
            Objects.requireNonNull(name);
            Objects.requireNonNull(version);
            Objects.requireNonNull(checksum);
            Objects.requireNonNull(commitSha);

            if (!name.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}")) {
                throw new IllegalArgumentException("Invalid artifact name.");
            }

            if (!VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("Invalid semantic version.");
            }

            if (!CHECKSUM.matcher(checksum).matches()) {
                throw new IllegalArgumentException("Invalid SHA-256 checksum.");
            }

            if (!commitSha.matches("[a-fA-F0-9]{7,40}")) {
                throw new IllegalArgumentException("Invalid commit SHA.");
            }
        }

        String identity() {
            return name + ":" + version + ":" + checksum;
        }
    }

    record DeploymentActor(
        String username,
        Set<Permission> permissions
    ) {
        DeploymentActor {
            if (username == null || username.isBlank()) {
                throw new IllegalArgumentException("Username is required.");
            }

            permissions = Set.copyOf(permissions);
        }

        boolean has(Permission permission) {
            return permissions.contains(permission);
        }
    }

    record Approval(
        String approver,
        Instant approvedAt,
        String changeReference
    ) {
        Approval {
            if (approver == null || approver.isBlank()) {
                throw new IllegalArgumentException("Approver is required.");
            }

            Objects.requireNonNull(approvedAt);

            if (changeReference == null || changeReference.isBlank()) {
                throw new IllegalArgumentException(
                    "Approval change reference is required."
                );
            }
        }
    }

    record EnvironmentPolicy(
        Environment environment,
        String endpoint,
        int replicas,
        boolean approvalRequired,
        Set<String> requiredChecks,
        DeploymentStrategy strategy
    ) {
        EnvironmentPolicy {
            Objects.requireNonNull(environment);
            Objects.requireNonNull(endpoint);
            Objects.requireNonNull(strategy);

            if (!endpoint.startsWith("https://")) {
                throw new IllegalArgumentException(
                    "Environment endpoint must use HTTPS."
                );
            }

            if (replicas < 1 || replicas > 100) {
                throw new IllegalArgumentException(
                    "Replica count must be between 1 and 100."
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    record DeploymentRequest(
        Environment environment,
        Artifact artifact,
        DeploymentActor actor,
        Approval approval,
        Set<String> passedChecks
    ) {
        DeploymentRequest {
            Objects.requireNonNull(environment);
            Objects.requireNonNull(artifact);
            Objects.requireNonNull(actor);

            passedChecks = Set.copyOf(passedChecks);
        }
    }

    record DeploymentResult(
        UUID deploymentId,
        Environment environment,
        String artifactIdentity,
        DeploymentStatus status,
        String deployedBy,
        String approvedBy,
        Instant deployedAt,
        String failureReason
    ) {}

    interface HealthVerifier {
        boolean verify(
            Environment environment,
            Artifact artifact,
            EnvironmentPolicy policy
        );
    }

    interface DeploymentExecutor {
        void execute(
            Environment environment,
            Artifact artifact,
            EnvironmentPolicy policy
        );
    }

    static final class DeploymentAudit {
        private final List<DeploymentResult> records =
            new ArrayList<>();

        void record(DeploymentResult result) {
            records.add(result);
        }

        List<DeploymentResult> getRecords() {
            return Collections.unmodifiableList(
                new ArrayList<>(records)
            );
        }

        Map<DeploymentStatus, Long> statusCounts() {
            return records.stream().collect(
                Collectors.groupingBy(
                    DeploymentResult::status,
                    Collectors.counting()
                )
            );
        }
    }

    static final class DeploymentService {

        private final Map<Environment, EnvironmentPolicy> policies =
            new EnumMap<>(Environment.class);

        private final Map<Environment, Artifact> activeArtifacts =
            new EnumMap<>(Environment.class);

        private final Map<String, Artifact> artifactRegistry =
            new HashMap<>();

        private final Set<Environment> deploymentsInProgress =
            new HashSet<>();

        private final DeploymentAudit audit = new DeploymentAudit();

        private final HealthVerifier healthVerifier;
        private final DeploymentExecutor executor;

        private final ReentrantLock lock = new ReentrantLock();

        DeploymentService(
            List<EnvironmentPolicy> policies,
            HealthVerifier healthVerifier,
            DeploymentExecutor executor
        ) {
            this.healthVerifier = Objects.requireNonNull(healthVerifier);
            this.executor = Objects.requireNonNull(executor);

            for (EnvironmentPolicy policy : policies) {
                if (this.policies.putIfAbsent(
                    policy.environment(),
                    policy
                ) != null) {
                    throw new PolicyException("Duplicate environment policy.");
                }
            }

            if (this.policies.size() != Environment.values().length) {
                throw new PolicyException(
                    "All four environment policies are required."
                );
            }
        }

        void registerArtifact(Artifact artifact) {
            lock.lock();

            try {
                artifactRegistry.put(artifact.identity(), artifact);
            } finally {
                lock.unlock();
            }
        }

        private Permission requiredPermission(Environment environment) {
            return switch (environment) {
                case DEVELOPMENT -> Permission.DEPLOY_DEVELOPMENT;
                case QA -> Permission.DEPLOY_QA;
                case STAGING -> Permission.DEPLOY_STAGING;
                case PRODUCTION -> Permission.DEPLOY_PRODUCTION;
            };
        }

        private void validate(DeploymentRequest request) {
            Environment environment = request.environment();
            EnvironmentPolicy policy = policies.get(environment);

            if (policy == null) {
                throw new PolicyException("Missing environment policy.");
            }

            if (!request.actor().has(requiredPermission(environment))) {
                throw new PolicyException(
                    "Actor lacks deployment permission."
                );
            }

            if (policy.approvalRequired()) {
                Approval approval = request.approval();

                if (approval == null) {
                    throw new PolicyException(
                        "Required release approval is missing."
                    );
                }

                if (!request.actor().has(Permission.APPROVE_RELEASE)) {
                    throw new PolicyException(
                        "Actor cannot approve releases."
                    );
                }

                if (approval.approver().equals(request.actor().username())) {
                    throw new PolicyException(
                        "Self-approval is prohibited."
                    );
                }
            }

            Set<String> missing = new HashSet<>(policy.requiredChecks());
            missing.removeAll(request.passedChecks());

            if (!missing.isEmpty()) {
                throw new PolicyException(
                    "Required checks failed or missing: " + missing
                );
            }

            int position = PROMOTION_ORDER.indexOf(environment);

            if (position > 0) {
                Environment previousEnvironment =
                    PROMOTION_ORDER.get(position - 1);

                Artifact previous = activeArtifacts.get(previousEnvironment);

                if (previous == null) {
                    throw new PolicyException(
                        "Previous environment is not deployed."
                    );
                }

                if (!previous.identity().equals(
                    request.artifact().identity()
                )) {
                    throw new PolicyException(
                        "Artifact identity differs from previous environment."
                    );
                }
            }
        }

        DeploymentResult deploy(DeploymentRequest request) {
            UUID deploymentId = UUID.randomUUID();

            lock.lock();

            try {
                validate(request);

                if (!deploymentsInProgress.add(request.environment())) {
                    throw new DeploymentException(
                        "Another deployment is in progress."
                    );
                }

                DeploymentResult pending = new DeploymentResult(
                    deploymentId,
                    request.environment(),
                    request.artifact().identity(),
                    DeploymentStatus.PENDING,
                    request.actor().username(),
                    request.approval() == null
                        ? null
                        : request.approval().approver(),
                    Instant.now(),
                    null
                );

                audit.record(pending);

            } finally {
                lock.unlock();
            }

            DeploymentResult result;

            try {
                EnvironmentPolicy policy =
                    policies.get(request.environment());

                executor.execute(
                    request.environment(),
                    request.artifact(),
                    policy
                );

                if (!healthVerifier.verify(
                    request.environment(),
                    request.artifact(),
                    policy
                )) {
                    throw new DeploymentException(
                        "Readiness verification failed."
                    );
                }

                lock.lock();

                try {
                    activeArtifacts.put(
                        request.environment(),
                        request.artifact()
                    );

                    result = new DeploymentResult(
                        deploymentId,
                        request.environment(),
                        request.artifact().identity(),
                        DeploymentStatus.SUCCEEDED,
                        request.actor().username(),
                        request.approval() == null
                            ? null
                            : request.approval().approver(),
                        Instant.now(),
                        null
                    );

                    audit.record(result);

                } finally {
                    lock.unlock();
                }

            } catch (RuntimeException exception) {
                lock.lock();

                try {
                    result = new DeploymentResult(
                        deploymentId,
                        request.environment(),
                        request.artifact().identity(),
                        DeploymentStatus.FAILED,
                        request.actor().username(),
                        request.approval() == null
                            ? null
                            : request.approval().approver(),
                        Instant.now(),
                        exception.getMessage()
                    );

                    audit.record(result);

                } finally {
                    lock.unlock();
                }

            } finally {
                lock.lock();

                try {
                    deploymentsInProgress.remove(request.environment());
                } finally {
                    lock.unlock();
                }
            }

            return result;
        }

        DeploymentResult rollback(
            Environment environment,
            DeploymentActor actor,
            String previousIdentity
        ) {
            lock.lock();

            try {
                if (!actor.has(Permission.ROLLBACK)) {
                    throw new PolicyException("Rollback permission denied.");
                }

                if (deploymentsInProgress.contains(environment)) {
                    throw new DeploymentException(
                        "Deployment currently in progress."
                    );
                }

                Artifact current = activeArtifacts.get(environment);
                Artifact previous = artifactRegistry.get(previousIdentity);

                if (current == null || previous == null) {
                    throw new DeploymentException(
                        "Current or previous artifact unavailable."
                    );
                }

                if (current.identity().equals(previous.identity())) {
                    throw new DeploymentException(
                        "Rollback target is already active."
                    );
                }

                if (!deploymentsInProgress.add(environment)) {
                    throw new DeploymentException(
                        "Another deployment is in progress."
                    );
                }

                try {
                    EnvironmentPolicy policy = policies.get(environment);

                    executor.execute(environment, previous, policy);

                    if (!healthVerifier.verify(environment, previous, policy)) {
                        throw new DeploymentException(
                            "Rollback health check failed."
                        );
                    }

                    activeArtifacts.put(environment, previous);

                    DeploymentResult result = new DeploymentResult(
                        UUID.randomUUID(),
                        environment,
                        previous.identity(),
                        DeploymentStatus.SUCCEEDED,
                        actor.username(),
                        null,
                        Instant.now(),
                        null
                    );

                    audit.record(result);
                    return result;

                } catch (RuntimeException exception) {
                    DeploymentResult failed = new DeploymentResult(
                        UUID.randomUUID(),
                        environment,
                        previous.identity(),
                        DeploymentStatus.FAILED,
                        actor.username(),
                        null,
                        Instant.now(),
                        exception.getMessage()
                    );

                    audit.record(failed);
                    throw exception;

                } finally {
                    deploymentsInProgress.remove(environment);
                }

            } finally {
                lock.unlock();
            }
        }

        Map<Environment, String> environmentReport() {
            lock.lock();

            try {
                Map<Environment, String> report =
                    new EnumMap<>(Environment.class);

                for (Environment environment : Environment.values()) {
                    Artifact artifact = activeArtifacts.get(environment);

                    report.put(
                        environment,
                        artifact == null ? "NOT_DEPLOYED" : artifact.identity()
                    );
                }

                return Collections.unmodifiableMap(report);

            } finally {
                lock.unlock();
            }
        }

        DeploymentAudit audit() {
            return audit;
        }
    }

    static List<EnvironmentPolicy> createPolicies() {
        return List.of(
            new EnvironmentPolicy(
                Environment.DEVELOPMENT,
                "https://dev.example.internal",
                1,
                false,
                Set.of("build", "unit_tests"),
                DeploymentStrategy.ROLLING
            ),
            new EnvironmentPolicy(
                Environment.QA,
                "https://qa.example.internal",
                2,
                false,
                Set.of(
                    "build",
                    "unit_tests",
                    "integration_tests",
                    "security_scan"
                ),
                DeploymentStrategy.ROLLING
            ),
            new EnvironmentPolicy(
                Environment.STAGING,
                "https://staging.example.internal",
                3,
                true,
                Set.of(
                    "build",
                    "unit_tests",
                    "integration_tests",
                    "security_scan",
                    "load_tests"
                ),
                DeploymentStrategy.BLUE_GREEN
            ),
            new EnvironmentPolicy(
                Environment.PRODUCTION,
                "https://production.example.com",
                5,
                true,
                Set.of(
                    "build",
                    "unit_tests",
                    "integration_tests",
                    "security_scan",
                    "load_tests",
                    "acceptance_tests"
                ),
                DeploymentStrategy.CANARY
            )
        );
    }

    public static void main(String[] args) {
        DeploymentActor releaseBot = new DeploymentActor(
            "release-bot",
            Set.of(
                Permission.DEPLOY_DEVELOPMENT,
                Permission.DEPLOY_QA,
                Permission.DEPLOY_STAGING,
                Permission.DEPLOY_PRODUCTION,
                Permission.ROLLBACK
            )
        );

        DeploymentActor releaseManager = new DeploymentActor(
            "release-manager",
            Set.of(
                Permission.APPROVE_RELEASE,
                Permission.ROLLBACK
            )
        );

        DeploymentService service = new DeploymentService(
            createPolicies(),
            (environment, artifact, policy) -> true,
            (environment, artifact, policy) -> {
                System.out.printf(
                    "Executing %s deployment of %s using %s, replicas=%d%n",
                    environment,
                    artifact.identity(),
                    policy.strategy(),
                    policy.replicas()
                );
            }
        );

        Artifact release = new Artifact(
            "billing-service",
            "1.0.0",
            "a".repeat(64),
            "b".repeat(40)
        );

        service.registerArtifact(release);

        Set<String> checks = Set.of(
            "build",
            "unit_tests",
            "integration_tests",
            "security_scan",
            "load_tests",
            "acceptance_tests"
        );

        for (Environment environment : PROMOTION_ORDER) {
            Approval approval = (
                environment == Environment.STAGING ||
                environment == Environment.PRODUCTION
            )
                ? new Approval(
                    releaseManager.username(),
                    Instant.now(),
                    "CHG-2026-1042"
                )
                : null;

            DeploymentResult result = service.deploy(
                new DeploymentRequest(
                    environment,
                    release,
                    releaseBot,
                    approval,
                    checks
                )
            );

            System.out.println(
                environment + " -> " + result.status()
            );

            if (result.status() != DeploymentStatus.SUCCEEDED) {
                throw new DeploymentException(
                    "Release promotion stopped."
                );
            }
        }

        // Demonstrate failure without replacing the active artifact.
        Artifact nextRelease = new Artifact(
            "billing-service",
            "1.1.0",
            "c".repeat(64),
            "d".repeat(40)
        );

        service.registerArtifact(nextRelease);

        DeploymentService failingService = new DeploymentService(
            createPolicies(),
            (environment, artifact, policy) -> false,
            (environment, artifact, policy) -> {}
        );

        DeploymentResult failed = failingService.deploy(
            new DeploymentRequest(
                Environment.DEVELOPMENT,
                nextRelease,
                releaseBot,
                null,
                checks
            )
        );

        System.out.println("Failure scenario: " + failed.status());

        System.out.println("\nACTIVE ENVIRONMENT STATE");

        service.environmentReport().forEach(
            (environment, artifact) ->
                System.out.println(environment + ": " + artifact)
        );

        System.out.println("\nAUDIT STATUS COUNTS");

        System.out.println(service.audit().statusCounts());

        System.out.println("\nDeployment governance completed.");
    }
}

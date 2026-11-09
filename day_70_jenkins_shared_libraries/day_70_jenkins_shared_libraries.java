import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Jenkins Shared Libraries
 * Enterprise pipeline governance and execution.
 *
 * Runtime: Java 17
 *
 * Compile:
 * javac Main.java
 *
 * Run:
 * java Main
 */

public class Main {

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum ReleaseStatus {
        DRAFT,
        TESTED,
        APPROVED,
        REJECTED
    }

    enum PipelineStatus {
        CREATED,
        RUNNING,
        SUCCESS,
        FAILED
    }

    enum StageStatus {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILED,
        SKIPPED
    }

    enum ReviewStatus {
        NOT_REVIEWED,
        APPROVED,
        REJECTED
    }

    static class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }

        PipelineException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class ValidationException extends PipelineException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class PolicyException extends PipelineException {
        PolicyException(String message) {
            super(message);
        }
    }

    static class ExecutionException extends PipelineException {
        ExecutionException(String message) {
            super(message);
        }
    }

    record LibraryRelease(
        String name,
        String version,
        String commit,
        ReleaseStatus status,
        Instant publishedAt
    ) {
        private static final Pattern VERSION =
            Pattern.compile("\\d+\\.\\d+\\.\\d+");

        private static final Pattern COMMIT =
            Pattern.compile("[a-fA-F0-9]{7,40}");

        LibraryRelease {
            if (name == null || name.isBlank()) {
                throw new ValidationException("Library name is required.");
            }

            if (version == null || !VERSION.matcher(version).matches()) {
                throw new ValidationException("Invalid semantic version.");
            }

            if (commit == null || !COMMIT.matcher(commit).matches()) {
                throw new ValidationException("Invalid commit identifier.");
            }

            Objects.requireNonNull(status);
            Objects.requireNonNull(publishedAt);
        }
    }

    record StageResult(
        String name,
        StageStatus status,
        int attempts,
        long durationMillis,
        String message
    ) {}

    record PipelineConfiguration(
        String application,
        String repository,
        String branch,
        int buildNumber,
        Environment environment,
        String libraryName,
        String libraryVersion,
        boolean productionApproved
    ) {
        PipelineConfiguration {
            if (application == null || application.isBlank()) {
                throw new ValidationException("Application is required.");
            }

            if (repository == null ||
                !(repository.startsWith("https://") ||
                  repository.startsWith("ssh://"))) {
                throw new ValidationException("Invalid repository URL.");
            }

            if (branch == null || branch.isBlank()) {
                throw new ValidationException("Branch is required.");
            }

            if (buildNumber <= 0) {
                throw new ValidationException("Build number must be positive.");
            }

            Objects.requireNonNull(environment);
            Objects.requireNonNull(libraryName);
            Objects.requireNonNull(libraryVersion);
        }
    }

    static final class LibraryRegistry {
        private final Map<String, LibraryRelease> releases =
            new HashMap<>();

        private String key(String name, String version) {
            return name + "@" + version;
        }

        public void register(LibraryRelease release) {
            String key = key(release.name(), release.version());

            if (releases.containsKey(key)) {
                throw new ValidationException("Duplicate library release.");
            }

            releases.put(key, release);
        }

        public LibraryRelease resolve(String name, String version) {
            LibraryRelease release = releases.get(key(name, version));

            if (release == null) {
                throw new ValidationException("Library release not found.");
            }

            if (release.status() != ReleaseStatus.APPROVED) {
                throw new PolicyException("Library is not approved.");
            }

            return release;
        }

        public List<LibraryRelease> approvedReleases() {
            return releases.values()
                .stream()
                .filter(r -> r.status() == ReleaseStatus.APPROVED)
                .sorted((a, b) -> a.name().compareTo(b.name()))
                .toList();
        }
    }

    interface PipelineStep<T> {
        T execute() throws Exception;
    }

    interface DeploymentService {
        boolean deploy(
            String artifact,
            Environment environment
        );
    }

    static final class SimulatedDeploymentService
        implements DeploymentService {

        @Override
        public boolean deploy(
            String artifact,
            Environment environment
        ) {
            if (artifact == null || artifact.isBlank()) {
                throw new ExecutionException("Artifact is missing.");
            }

            System.out.println(
                "Deploying " + artifact + " to " + environment
            );

            return true;
        }
    }

    static final class ApprovalPolicy {
        private final boolean requireProductionApproval;
        private final Set<Environment> allowedEnvironments;

        ApprovalPolicy(
            boolean requireProductionApproval,
            Set<Environment> allowedEnvironments
        ) {
            this.requireProductionApproval = requireProductionApproval;

            this.allowedEnvironments = Collections.unmodifiableSet(
                EnumSet.copyOf(allowedEnvironments)
            );
        }

        void validate(PipelineConfiguration configuration) {
            if (!allowedEnvironments.contains(configuration.environment())) {
                throw new PolicyException("Environment is not permitted.");
            }

            if (configuration.environment() == Environment.PRODUCTION &&
                requireProductionApproval &&
                !configuration.productionApproved()) {
                throw new PolicyException(
                    "Production deployment requires approval."
                );
            }
        }
    }

    static final class CredentialStore {
        private final Map<String, String> credentials = new HashMap<>();

        void register(String id, String secret) {
            if (id == null || id.isBlank() ||
                secret == null || secret.isBlank()) {
                throw new ValidationException("Invalid credential.");
            }

            if (credentials.containsKey(id)) {
                throw new ValidationException("Credential already registered.");
            }

            credentials.put(id, secret);
        }

        public <T> T withCredential(
            String id,
            java.util.function.Function<String, T> operation
        ) {
            String secret = credentials.get(id);

            if (secret == null) {
                throw new PolicyException("Credential is unavailable.");
            }

            try {
                return operation.apply(secret);
            } finally {
                // The secret is never included in execution reports.
                secret = null;
            }
        }
    }

    static final class PipelineExecution {
        private final String runId = UUID.randomUUID().toString();
        private final PipelineConfiguration configuration;
        private final LibraryRelease library;
        private final ApprovalPolicy policy;
        private final DeploymentService deploymentService;

        private final List<StageResult> stageResults =
            new ArrayList<>();

        private PipelineStatus status = PipelineStatus.CREATED;
        private String artifact;
        private Instant startedAt;
        private Instant finishedAt;

        PipelineExecution(
            PipelineConfiguration configuration,
            LibraryRelease library,
            ApprovalPolicy policy,
            DeploymentService deploymentService
        ) {
            this.configuration = configuration;
            this.library = library;
            this.policy = policy;
            this.deploymentService = deploymentService;
        }

        private <T> T executeStage(
            String name,
            PipelineStep<T> operation
        ) {
            long start = System.nanoTime();

            try {
                System.out.println("\nStage: " + name);

                T result = operation.execute();

                stageResults.add(new StageResult(
                    name,
                    StageStatus.SUCCESS,
                    1,
                    (System.nanoTime() - start) / 1_000_000,
                    "Completed"
                ));

                return result;

            } catch (Exception exception) {
                stageResults.add(new StageResult(
                    name,
                    StageStatus.FAILED,
                    1,
                    (System.nanoTime() - start) / 1_000_000,
                    exception.getMessage()
                ));

                throw new ExecutionException(
                    "Stage failed: " + name,
                    exception
                );
            }
        }

        public PipelineExecution execute() {
            if (status != PipelineStatus.CREATED) {
                throw new ExecutionException(
                    "Execution cannot be repeated."
                );
            }

            status = PipelineStatus.RUNNING;
            startedAt = Instant.now();

            try {
                policy.validate(configuration);

                if (library.status() != ReleaseStatus.APPROVED) {
                    throw new PolicyException(
                        "Shared library is not approved."
                    );
                }

                String source = executeStage(
                    "checkout",
                    () -> {
                        System.out.println(
                            "Repository: " + configuration.repository()
                        );

                        return configuration.branch() + "-source";
                    }
                );

                executeStage(
                    "build",
                    () -> {
                        artifact = configuration.application()
                            + "-" + configuration.buildNumber() + ".jar";

                        System.out.println("Built: " + artifact);

                        return artifact;
                    }
                );

                Map<String, Integer> testResults = executeStage(
                    "test",
                    () -> {
                        if (source.isBlank()) {
                            throw new ExecutionException(
                                "Source checkout is empty."
                            );
                        }

                        Map<String, Integer> results = new HashMap<>();
                        results.put("passed", 42);
                        results.put("failed", 0);

                        return results;
                    }
                );

                if (testResults.get("failed") != 0 ||
                    testResults.get("passed") < 1) {
                    throw new PolicyException(
                        "Automated quality gate failed."
                    );
                }

                executeStage(
                    "package",
                    () -> {
                        if (artifact == null) {
                            throw new ExecutionException(
                                "Build artifact is unavailable."
                            );
                        }

                        return artifact;
                    }
                );

                executeStage(
                    "deploy",
                    () -> deploymentService.deploy(
                        artifact,
                        configuration.environment()
                    )
                );

                status = PipelineStatus.SUCCESS;

            } catch (Exception exception) {
                status = PipelineStatus.FAILED;
                System.err.println(
                    "Pipeline failure: " + exception.getMessage()
                );

            } finally {
                finishedAt = Instant.now();
            }

            return this;
        }

        public void printReport() {
            System.out.println("\n======================================");
            System.out.println("ENTERPRISE PIPELINE REPORT");
            System.out.println("======================================");

            System.out.println("Run ID: " + runId);
            System.out.println("Application: " + configuration.application());

            System.out.println(
                "Shared library: " + library.name() + "@" + library.version()
            );

            System.out.println("Branch: " + configuration.branch());
            System.out.println("Build: " + configuration.buildNumber());
            System.out.println("Environment: " + configuration.environment());
            System.out.println("Status: " + status);
            System.out.println("Started: " + startedAt);
            System.out.println("Finished: " + finishedAt);

            System.out.println("\nStage results:");

            stageResults.forEach(stage ->
                System.out.printf(
                    "%-12s %-10s %d ms%n",
                    stage.name(),
                    stage.status(),
                    stage.durationMillis()
                )
            );
        }

        public PipelineStatus getStatus() {
            return status;
        }

        public List<StageResult> getStageResults() {
            return List.copyOf(stageResults);
        }
    }

    static void validateRegistry(LibraryRegistry registry) {
        boolean rejected = false;

        try {
            registry.resolve("enterprise-ci", "9.9.9");
        } catch (ValidationException exception) {
            rejected = true;
        }

        if (!rejected) {
            throw new AssertionError("Unknown release was accepted.");
        }

        System.out.println("Library registry validation passed.");
    }

    public static void main(String[] args) {
        LibraryRegistry registry = new LibraryRegistry();

        LibraryRelease release = new LibraryRelease(
            "enterprise-ci",
            "2.1.0",
            "a1b2c3d4e5f6789",
            ReleaseStatus.APPROVED,
            Instant.now()
        );

        registry.register(release);

        LibraryRelease resolved = registry.resolve(
            "enterprise-ci",
            "2.1.0"
        );

        ApprovalPolicy policy = new ApprovalPolicy(
            true,
            EnumSet.allOf(Environment.class)
        );

        DeploymentService deploymentService =
            new SimulatedDeploymentService();

        PipelineConfiguration configuration =
            new PipelineConfiguration(
                "payment-service",
                "https://git.example.com/platform/payment-service.git",
                "main",
                401,
                Environment.STAGING,
                "enterprise-ci",
                "2.1.0",
                false
            );

        PipelineExecution execution = new PipelineExecution(
            configuration,
            resolved,
            policy,
            deploymentService
        );

        execution.execute();
        execution.printReport();

        if (execution.getStatus() != PipelineStatus.SUCCESS) {
            throw new AssertionError("Staging pipeline failed.");
        }

        // Production execution is rejected without an approval decision.
        PipelineConfiguration productionConfiguration =
            new PipelineConfiguration(
                "payment-service",
                "https://git.example.com/platform/payment-service.git",
                "main",
                402,
                Environment.PRODUCTION,
                "enterprise-ci",
                "2.1.0",
                false
            );

        PipelineExecution productionExecution =
            new PipelineExecution(
                productionConfiguration,
                resolved,
                policy,
                deploymentService
            );

        productionExecution.execute();

        if (productionExecution.getStatus() != PipelineStatus.FAILED) {
            throw new AssertionError(
                "Production approval policy was not enforced."
            );
        }

        validateRegistry(registry);

        System.out.println("\nAll enterprise validation checks passed.");
    }
}

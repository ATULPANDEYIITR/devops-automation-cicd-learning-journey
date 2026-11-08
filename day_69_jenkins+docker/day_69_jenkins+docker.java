import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Jenkins + Docker enterprise deployment pipeline.
 *
 * Java 17
 *
 * Features:
 * - Immutable pipeline configuration
 * - Typed pipeline stages and states
 * - Docker image lifecycle
 * - Build and test gates
 * - Security scan policy
 * - Registry publishing
 * - Environment authorization
 * - Deployment state transitions
 * - Audit reporting
 *
 * Compile:
 * javac JenkinsDockerPipeline.java
 *
 * Run:
 * java JenkinsDockerPipeline
 */

public class JenkinsDockerPipeline {

    // ----------------------------------------------------
    // Domain enums
    // ----------------------------------------------------

    enum Stage {
        CHECKOUT,
        BUILD,
        TEST,
        SECURITY_SCAN,
        PUSH,
        DEPLOY
    }

    enum Status {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILED,
        SKIPPED
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum MergeStrategy {
        ROLLING,
        RECREATE
    }

    // ----------------------------------------------------
    // Exceptions
    // ----------------------------------------------------

    static class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }
    }

    static class PolicyViolationException extends PipelineException {
        PolicyViolationException(String message) {
            super(message);
        }
    }

    // ----------------------------------------------------
    // Immutable configuration
    // ----------------------------------------------------

    record Configuration(
        String application,
        String repository,
        String tag,
        String commit,
        String branch,
        String dockerfile,
        String composeFile,
        Environment environment,
        int retries,
        boolean requireTests,
        boolean requireScan,
        boolean requirePush,
        boolean productionAuthorized
    ) {

        private static final Pattern TAG_PATTERN =
            Pattern.compile("[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}");

        Configuration {
            Objects.requireNonNull(application);
            Objects.requireNonNull(repository);
            Objects.requireNonNull(tag);
            Objects.requireNonNull(commit);
            Objects.requireNonNull(branch);
            Objects.requireNonNull(dockerfile);
            Objects.requireNonNull(composeFile);
            Objects.requireNonNull(environment);

            if (application.isBlank() ||
                repository.isBlank() ||
                branch.isBlank()) {
                throw new IllegalArgumentException(
                    "Application, repository and branch are required."
                );
            }

            if (!TAG_PATTERN.matcher(tag).matches()) {
                throw new IllegalArgumentException("Invalid Docker tag.");
            }

            if (commit.length() < 7) {
                throw new IllegalArgumentException(
                    "Commit identifier must contain at least seven characters."
                );
            }

            if (retries < 0) {
                throw new IllegalArgumentException("Invalid retry count.");
            }

            if (
                environment == Environment.PRODUCTION &&
                !productionAuthorized
            ) {
                throw new PolicyViolationException(
                    "Production deployment is not authorized."
                );
            }
        }

        String image() {
            return repository + ":" + tag;
        }
    }

    // ----------------------------------------------------
    // Docker image domain
    // ----------------------------------------------------

    static final class DockerImage {

        private final String name;
        private String digest;
        private boolean built;
        private boolean tested;
        private boolean scanned;
        private boolean published;

        DockerImage(String name) {
            this.name = Objects.requireNonNull(name);

            if (name.isBlank()) {
                throw new IllegalArgumentException(
                    "Image name cannot be empty."
                );
            }
        }

        void markBuilt(String digest) {
            if (digest == null || digest.isBlank()) {
                throw new PipelineException("Image digest is required.");
            }

            this.digest = digest;
            this.built = true;
        }

        void markTested() {
            requireBuilt();
            tested = true;
        }

        void markScanned() {
            requireBuilt();
            scanned = true;
        }

        void markPublished() {
            requireBuilt();
            published = true;
        }

        private void requireBuilt() {
            if (!built) {
                throw new PipelineException(
                    "Docker image must be built first."
                );
            }
        }

        String name() {
            return name;
        }

        String digest() {
            return digest;
        }

        boolean isBuilt() {
            return built;
        }

        boolean isTested() {
            return tested;
        }

        boolean isScanned() {
            return scanned;
        }

        boolean isPublished() {
            return published;
        }
    }

    // ----------------------------------------------------
    // Stage result
    // ----------------------------------------------------

    static final class StageResult {

        private final Stage stage;
        private Status status = Status.PENDING;
        private String message = "Awaiting execution";
        private Instant startedAt;
        private Instant finishedAt;
        private int attempts;

        StageResult(Stage stage) {
            this.stage = stage;
        }

        void start() {
            if (status != Status.PENDING) {
                throw new PipelineException(
                    "Invalid stage transition: " + stage
                );
            }

            status = Status.RUNNING;
            startedAt = Instant.now();
        }

        void complete(Status finalStatus, String message) {
            if (status != Status.RUNNING) {
                throw new PipelineException(
                    "Stage is not running: " + stage
                );
            }

            if (
                finalStatus != Status.SUCCESS &&
                finalStatus != Status.FAILED
            ) {
                throw new IllegalArgumentException(
                    "Invalid completion status."
                );
            }

            this.status = finalStatus;
            this.message = message;
            this.finishedAt = Instant.now();
        }

        void skip(String reason) {
            if (status != Status.PENDING) {
                throw new PipelineException("Cannot skip completed stage.");
            }

            status = Status.SKIPPED;
            message = reason;
        }

        void incrementAttempts() {
            attempts++;
        }

        Status status() {
            return status;
        }

        Stage stage() {
            return stage;
        }

        String message() {
            return message;
        }

        int attempts() {
            return attempts;
        }
    }

    // ----------------------------------------------------
    // Deployment policy
    // ----------------------------------------------------

    interface DeploymentPolicy {
        void validate(
            Configuration config,
            DockerImage image
        );
    }

    static final class StandardDeploymentPolicy
            implements DeploymentPolicy {

        @Override
        public void validate(
            Configuration config,
            DockerImage image
        ) {
            if (!image.isBuilt()) {
                throw new PolicyViolationException(
                    "Image has not been built."
                );
            }

            if (config.requireTests() && !image.isTested()) {
                throw new PolicyViolationException(
                    "Required container tests have not passed."
                );
            }

            if (config.requireScan() && !image.isScanned()) {
                throw new PolicyViolationException(
                    "Security scan has not passed."
                );
            }

            if (config.requirePush() && !image.isPublished()) {
                throw new PolicyViolationException(
                    "Image has not been published."
                );
            }
        }
    }

    // ----------------------------------------------------
    // Pipeline service
    // ----------------------------------------------------

    static final class PipelineService {

        private final Configuration config;
        private final DockerImage image;
        private final DeploymentPolicy policy;

        private final Map<Stage, StageResult> results =
            new EnumMap<>(Stage.class);

        private final List<String> auditLog =
            new ArrayList<>();

        private final String pipelineId =
            UUID.randomUUID().toString();

        private Status pipelineStatus = Status.PENDING;

        PipelineService(
            Configuration config,
            DeploymentPolicy policy
        ) {
            this.config = config;
            this.policy = policy;
            this.image = new DockerImage(config.image());

            for (Stage stage : Stage.values()) {
                results.put(stage, new StageResult(stage));
            }
        }

        private void log(String message) {
            String entry = Instant.now() + " | " + message;
            auditLog.add(entry);
            System.out.println(entry);
        }

        private void execute(
            Stage stage,
            Runnable action
        ) {
            StageResult result = results.get(stage);
            result.start();

            int maxAttempts = config.retries() + 1;

            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                result.incrementAttempts();

                try {
                    action.run();

                    result.complete(
                        Status.SUCCESS,
                        "Execution completed."
                    );

                    log(stage + " SUCCESS");
                    return;

                } catch (RuntimeException exception) {
                    log(
                        stage + " attempt " + attempt +
                        " failed: " + exception.getMessage()
                    );

                    if (attempt == maxAttempts) {
                        result.complete(
                            Status.FAILED,
                            exception.getMessage()
                        );

                        throw exception;
                    }
                }
            }
        }

        private void skip(Stage stage, String reason) {
            results.get(stage).skip(reason);
            log(stage + " SKIPPED: " + reason);
        }

        private void checkout() {
            execute(Stage.CHECKOUT, () -> {
                if (config.commit().length() < 7) {
                    throw new PipelineException("Invalid commit.");
                }

                if (config.branch().isBlank()) {
                    throw new PipelineException("Invalid branch.");
                }
            });
        }

        private void build() {
            execute(Stage.BUILD, () -> {
                if (config.dockerfile().isBlank()) {
                    throw new PipelineException("Dockerfile is missing.");
                }

                image.markBuilt("sha256:enterprise-build-digest");
            });
        }

        private void test() {
            if (!config.requireTests()) {
                skip(Stage.TEST, "Tests not required by policy.");
                return;
            }

            execute(Stage.TEST, image::markTested);
        }

        private void scan() {
            if (!config.requireScan()) {
                skip(Stage.SECURITY_SCAN, "Security scan disabled.");
                return;
            }

            execute(Stage.SECURITY_SCAN, image::markScanned);
        }

        private void push() {
            if (!config.requirePush()) {
                skip(Stage.PUSH, "Registry publishing disabled.");
                return;
            }

            execute(Stage.PUSH, image::markPublished);
        }

        private void deploy() {
            execute(Stage.DEPLOY, () -> {
                policy.validate(config, image);

                log(
                    "Deployment strategy: " +
                    MergeStrategy.ROLLING
                );

                log(
                    "Target environment: " +
                    config.environment()
                );
            });
        }

        void run() {
            pipelineStatus = Status.RUNNING;
            log("Pipeline " + pipelineId + " started.");

            try {
                checkout();
                build();
                test();
                scan();
                push();
                deploy();

                pipelineStatus = Status.SUCCESS;

            } catch (RuntimeException exception) {
                pipelineStatus = Status.FAILED;

                StageResult running = results.values()
                    .stream()
                    .filter(result -> result.status() == Status.RUNNING)
                    .findFirst()
                    .orElse(null);

                if (running != null) {
                    log("Failure in stage: " + running.stage());
                }

                // Stages that depend on a failed stage cannot run.
                for (StageResult result : results.values()) {
                    if (result.status() == Status.PENDING) {
                        result.skip("Blocked by pipeline failure.");
                    }
                }

                log("Pipeline failed: " + exception.getMessage());
            }

            log("Pipeline finished: " + pipelineStatus);
        }

        void report() {
            System.out.println("\n========== ENTERPRISE REPORT ==========");
            System.out.println("Pipeline ID: " + pipelineId);
            System.out.println("Application: " + config.application());
            System.out.println("Image: " + image.name());
            System.out.println("Digest: " + image.digest());
            System.out.println("Environment: " + config.environment());
            System.out.println("Pipeline status: " + pipelineStatus);

            System.out.println("\nStage results:");

            for (StageResult result : results.values()) {
                System.out.printf(
                    "%-16s %-10s Attempts: %-3d %s%n",
                    result.stage(),
                    result.status(),
                    result.attempts(),
                    result.message()
                );
            }

            System.out.println("\nAudit events: " + auditLog.size());
        }
    }

    // ----------------------------------------------------
    // Application entry point
    // ----------------------------------------------------

    public static void main(String[] args) {

        try {
            Configuration config = new Configuration(
                "inventory-api",
                "inventory-api",
                "1.0.0",
                "a83f9c2",
                "main",
                "Dockerfile",
                "compose.yaml",
                Environment.PRODUCTION,
                2,
                true,
                true,
                true,
                true
            );

            DeploymentPolicy policy =
                new StandardDeploymentPolicy();

            PipelineService pipeline =
                new PipelineService(config, policy);

            pipeline.run();
            pipeline.report();

        } catch (PipelineException |
                 IllegalArgumentException exception) {

            System.err.println(
                "Pipeline initialization failed: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}

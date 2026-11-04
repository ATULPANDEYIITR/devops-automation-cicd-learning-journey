import java.time.Duration;
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
import java.util.function.Predicate;

/*
 * Enterprise Jenkinsfile Pipeline Governance Model
 *
 * Java 17
 *
 * Covers:
 * - Pipeline configuration
 * - Immutable pipeline domain types
 * - Stage and step execution
 * - Environment inheritance
 * - Conditional stages
 * - Dependency validation
 * - Post-build conditions
 * - Execution events
 * - Build reporting
 * - Enterprise failure handling
 */

public class JenkinsPipelineEnterprise {

    enum BuildStatus {
        CREATED,
        RUNNING,
        SUCCESS,
        FAILURE,
        UNSTABLE,
        ABORTED
    }

    enum StageStatus {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILURE,
        SKIPPED
    }

    enum PostCondition {
        ALWAYS,
        SUCCESS,
        FAILURE,
        UNSTABLE,
        CLEANUP
    }

    static class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }

        PipelineException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record ExecutionEvent(
        String id,
        Instant timestamp,
        String type,
        String stage,
        String details
    ) {}

    record StepResult(
        String stepName,
        boolean successful,
        String message,
        Duration duration
    ) {}

    record StageReport(
        String name,
        StageStatus status,
        Duration duration,
        String error
    ) {}

    record PipelineReport(
        String pipelineName,
        BuildStatus status,
        Instant startedAt,
        Instant completedAt,
        Duration duration,
        List<StageReport> stages,
        int eventCount
    ) {}

    @FunctionalInterface
    interface PipelineAction {
        String execute(PipelineContext context) throws Exception;
    }

    @FunctionalInterface
    interface PostAction {
        void execute(PipelineContext context) throws Exception;
    }

    static final class PipelineContext {

        private final Map<String, String> environment;
        private final Map<String, String> artifacts;
        private final List<ExecutionEvent> events;

        PipelineContext(
            Map<String, String> environment,
            Map<String, String> artifacts,
            List<ExecutionEvent> events
        ) {
            this.environment = new HashMap<>(environment);
            this.artifacts = artifacts;
            this.events = events;
        }

        String get(String key) {
            return environment.get(key);
        }

        Map<String, String> environment() {
            return Collections.unmodifiableMap(environment);
        }

        void putArtifact(String name, String value) {
            if (name == null || name.isBlank()) {
                throw new PipelineException(
                    "Artifact name cannot be empty"
                );
            }

            artifacts.put(name, value);
        }

        String getArtifact(String name) {
            return artifacts.get(name);
        }

        Map<String, String> artifacts() {
            return Collections.unmodifiableMap(artifacts);
        }
    }

    static final class PipelineStep {

        private final String name;
        private final PipelineAction action;
        private final boolean continueOnError;

        PipelineStep(
            String name,
            PipelineAction action,
            boolean continueOnError
        ) {
            if (name == null || name.isBlank()) {
                throw new PipelineException(
                    "Step name is required"
                );
            }

            this.name = name;
            this.action = Objects.requireNonNull(action);
            this.continueOnError = continueOnError;
        }

        String name() {
            return name;
        }

        PipelineAction action() {
            return action;
        }

        boolean continueOnError() {
            return continueOnError;
        }
    }

    static final class PipelineStage {

        private final String name;
        private final List<PipelineStep> steps;
        private final Map<String, String> environment;
        private final List<String> dependencies;
        private final Predicate<Map<String, String>> condition;

        private StageStatus status = StageStatus.PENDING;
        private Duration duration = Duration.ZERO;
        private String error = "";

        PipelineStage(
            String name,
            List<PipelineStep> steps,
            Map<String, String> environment,
            List<String> dependencies,
            Predicate<Map<String, String>> condition
        ) {
            if (name == null || name.isBlank()) {
                throw new PipelineException(
                    "Stage name is required"
                );
            }

            if (steps == null || steps.isEmpty()) {
                throw new PipelineException(
                    "Stage requires at least one step"
                );
            }

            this.name = name;
            this.steps = List.copyOf(steps);
            this.environment = Map.copyOf(environment);
            this.dependencies = List.copyOf(dependencies);
            this.condition = Objects.requireNonNull(condition);
        }

        String name() {
            return name;
        }

        List<PipelineStep> steps() {
            return steps;
        }

        Map<String, String> environment() {
            return environment;
        }

        List<String> dependencies() {
            return dependencies;
        }

        StageStatus status() {
            return status;
        }

        Duration duration() {
            return duration;
        }

        String error() {
            return error;
        }

        Predicate<Map<String, String>> condition() {
            return condition;
        }
    }

    record PostActionDefinition(
        String name,
        PostCondition condition,
        PostAction action
    ) {
        PostActionDefinition {
            if (name == null || name.isBlank()) {
                throw new PipelineException(
                    "Post action name is required"
                );
            }

            Objects.requireNonNull(condition);
            Objects.requireNonNull(action);
        }
    }

    static final class PipelinePolicy {

        private final boolean requireTests;
        private final boolean allowProductionDeployment;

        PipelinePolicy(
            boolean requireTests,
            boolean allowProductionDeployment
        ) {
            this.requireTests = requireTests;
            this.allowProductionDeployment =
                allowProductionDeployment;
        }

        void validate(Map<String, String> environment) {
            if (requireTests &&
                !"true".equals(environment.get("TESTS_REQUIRED"))) {
                throw new PipelineException(
                    "Pipeline policy requires test execution"
                );
            }

            if ("production".equals(
                environment.get("DEPLOY_TARGET")
            ) && !allowProductionDeployment) {
                throw new PipelineException(
                    "Production deployment is prohibited"
                );
            }
        }
    }

    static final class JenkinsPipeline {

        private final String name;
        private final Map<String, String> environment;
        private final List<PipelineStage> stages;
        private final List<PostActionDefinition> postActions;
        private final PipelinePolicy policy;

        private final List<ExecutionEvent> events =
            new ArrayList<>();

        private final Map<String, String> artifacts =
            new HashMap<>();

        private BuildStatus status = BuildStatus.CREATED;
        private Instant startedAt;
        private Instant completedAt;

        JenkinsPipeline(
            String name,
            Map<String, String> environment,
            List<PipelineStage> stages,
            List<PostActionDefinition> postActions,
            PipelinePolicy policy
        ) {
            if (name == null || name.isBlank()) {
                throw new PipelineException(
                    "Pipeline name is required"
                );
            }

            if (stages == null || stages.isEmpty()) {
                throw new PipelineException(
                    "Pipeline requires stages"
                );
            }

            this.name = name;
            this.environment = Map.copyOf(environment);
            this.stages = new ArrayList<>(stages);
            this.postActions = List.copyOf(postActions);
            this.policy = Objects.requireNonNull(policy);

            validateConfiguration();
        }

        private void validateConfiguration() {
            Set<String> names = new HashSet<>();

            for (PipelineStage stage : stages) {
                if (!names.add(stage.name())) {
                    throw new PipelineException(
                        "Duplicate stage: " + stage.name()
                    );
                }
            }

            for (PipelineStage stage : stages) {
                for (String dependency : stage.dependencies()) {
                    if (!names.contains(dependency)) {
                        throw new PipelineException(
                            "Unknown dependency: " + dependency
                        );
                    }
                }
            }

            validateDependencyGraph();
            policy.validate(environment);
        }

        private void validateDependencyGraph() {
            Map<String, PipelineStage> stageMap =
                new HashMap<>();

            stages.forEach(stage ->
                stageMap.put(stage.name(), stage)
            );

            Set<String> visiting = new HashSet<>();
            Set<String> visited = new HashSet<>();

            for (PipelineStage stage : stages) {
                visit(
                    stage.name(),
                    stageMap,
                    visiting,
                    visited
                );
            }
        }

        private void visit(
            String name,
            Map<String, PipelineStage> stageMap,
            Set<String> visiting,
            Set<String> visited
        ) {
            if (visiting.contains(name)) {
                throw new PipelineException(
                    "Circular stage dependency: " + name
                );
            }

            if (visited.contains(name)) {
                return;
            }

            visiting.add(name);

            for (String dependency :
                stageMap.get(name).dependencies()) {
                visit(
                    dependency,
                    stageMap,
                    visiting,
                    visited
                );
            }

            visiting.remove(name);
            visited.add(name);
        }

        private void record(
            String type,
            String stage,
            String details
        ) {
            ExecutionEvent event = new ExecutionEvent(
                UUID.randomUUID().toString(),
                Instant.now(),
                type,
                stage,
                details
            );

            events.add(event);

            System.out.printf(
                "[%s] %s | %s%n",
                type,
                stage,
                details
            );
        }

        private boolean dependenciesSucceeded(
            PipelineStage stage
        ) {
            for (String dependency : stage.dependencies()) {
                PipelineStage required = stages.stream()
                    .filter(item ->
                        item.name().equals(dependency)
                    )
                    .findFirst()
                    .orElseThrow();

                if (required.status() != StageStatus.SUCCESS) {
                    return false;
                }
            }

            return true;
        }

        private void executeStage(PipelineStage stage) {
            if (!dependenciesSucceeded(stage)) {
                stage.status = StageStatus.SKIPPED;

                record(
                    "STAGE_SKIPPED",
                    stage.name(),
                    "Dependency did not succeed"
                );

                return;
            }

            Map<String, String> stageEnvironment =
                new HashMap<>(environment);

            stageEnvironment.putAll(stage.environment());

            if (!stage.condition().test(
                Map.copyOf(stageEnvironment)
            )) {
                stage.status = StageStatus.SKIPPED;

                record(
                    "STAGE_SKIPPED",
                    stage.name(),
                    "Condition returned false"
                );

                return;
            }

            stage.status = StageStatus.RUNNING;

            PipelineContext context = new PipelineContext(
                stageEnvironment,
                artifacts,
                events
            );

            Instant start = Instant.now();

            record(
                "STAGE_STARTED",
                stage.name(),
                "Stage execution started"
            );

            try {
                for (PipelineStep step : stage.steps()) {
                    Instant stepStart = Instant.now();

                    record(
                        "STEP_STARTED",
                        stage.name(),
                        step.name()
                    );

                    try {
                        String result = step.action().execute(context);

                        record(
                            "STEP_SUCCESS",
                            stage.name(),
                            step.name() + ": " + result
                        );

                    } catch (Exception exception) {
                        record(
                            "STEP_FAILURE",
                            stage.name(),
                            step.name() + ": " +
                                exception.getMessage()
                        );

                        if (!step.continueOnError()) {
                            throw exception;
                        }
                    }

                    Duration stepDuration =
                        Duration.between(
                            stepStart,
                            Instant.now()
                        );

                    if (stepDuration.isNegative()) {
                        throw new PipelineException(
                            "Invalid step duration"
                        );
                    }
                }

                stage.status = StageStatus.SUCCESS;

                record(
                    "STAGE_SUCCESS",
                    stage.name(),
                    "Stage completed"
                );

            } catch (Exception exception) {
                stage.status = StageStatus.FAILURE;
                stage.error = exception.getMessage();

                throw new PipelineException(
                    "Stage failed: " + stage.name(),
                    exception
                );

            } finally {
                stage.duration = Duration.between(
                    start,
                    Instant.now()
                );
            }
        }

        private void executePostActions() {
            PipelineContext context = new PipelineContext(
                environment,
                artifacts,
                events
            );

            for (PostActionDefinition definition : postActions) {
                boolean shouldRun = switch (
                    definition.condition()
                ) {
                    case ALWAYS, CLEANUP -> true;
                    case SUCCESS -> status == BuildStatus.SUCCESS;
                    case FAILURE -> status == BuildStatus.FAILURE;
                    case UNSTABLE -> status == BuildStatus.UNSTABLE;
                };

                if (!shouldRun) {
                    continue;
                }

                try {
                    definition.action().execute(context);

                    record(
                        "POST_SUCCESS",
                        "POST",
                        definition.name()
                    );

                } catch (Exception exception) {
                    record(
                        "POST_FAILURE",
                        "POST",
                        definition.name() + ": " +
                            exception.getMessage()
                    );

                    if (status == BuildStatus.SUCCESS) {
                        status = BuildStatus.FAILURE;
                    }
                }
            }
        }

        PipelineReport execute() {
            if (status != BuildStatus.CREATED) {
                throw new PipelineException(
                    "Pipeline instance cannot be reused"
                );
            }

            startedAt = Instant.now();
            status = BuildStatus.RUNNING;

            record(
                "PIPELINE_STARTED",
                name,
                "Execution started"
            );

            try {
                for (PipelineStage stage : stages) {
                    executeStage(stage);
                }

                status = BuildStatus.SUCCESS;

            } catch (PipelineException exception) {
                status = BuildStatus.FAILURE;

                record(
                    "PIPELINE_FAILURE",
                    name,
                    exception.getMessage()
                );

                for (PipelineStage stage : stages) {
                    if (stage.status == StageStatus.PENDING) {
                        stage.status = StageStatus.SKIPPED;
                    }
                }

            } finally {
                executePostActions();
                completedAt = Instant.now();
            }

            record(
                "PIPELINE_COMPLETED",
                name,
                status.name()
            );

            List<StageReport> reports = stages.stream()
                .map(stage -> new StageReport(
                    stage.name(),
                    stage.status(),
                    stage.duration(),
                    stage.error()
                ))
                .toList();

            return new PipelineReport(
                name,
                status,
                startedAt,
                completedAt,
                Duration.between(startedAt, completedAt),
                List.copyOf(reports),
                events.size()
            );
        }
    }

    public static void main(String[] args) {

        PipelinePolicy policy = new PipelinePolicy(
            true,
            true
        );

        List<PipelineStage> stages = List.of(

            new PipelineStage(
                "Checkout",
                List.of(
                    new PipelineStep(
                        "Validate source",
                        context -> {
                            String branch = context.get("GIT_BRANCH");

                            if (branch == null || branch.isBlank()) {
                                throw new PipelineException(
                                    "Source branch is missing"
                                );
                            }

                            return "Checked out " + branch;
                        },
                        false
                    )
                ),
                Map.of(),
                List.of(),
                environment -> true
            ),

            new PipelineStage(
                "Build",
                List.of(
                    new PipelineStep(
                        "Compile application",
                        context -> {
                            context.putArtifact(
                                "application",
                                "customer-service.jar"
                            );

                            return "Artifact created";
                        },
                        false
                    )
                ),
                Map.of("BUILD_MODE", "release"),
                List.of("Checkout"),
                environment -> true
            ),

            new PipelineStage(
                "Test",
                List.of(
                    new PipelineStep(
                        "Run unit tests",
                        context -> {
                            if ("FAIL".equals(
                                context.get("TEST_RESULT")
                            )) {
                                throw new PipelineException(
                                    "Unit tests failed"
                                );
                            }

                            return "All tests passed";
                        },
                        false
                    )
                ),
                Map.of(),
                List.of("Build"),
                environment -> true
            ),

            new PipelineStage(
                "Deploy",
                List.of(
                    new PipelineStep(
                        "Deploy artifact",
                        context -> {
                            if (context.getArtifact(
                                "application"
                            ) == null) {
                                throw new PipelineException(
                                    "Build artifact missing"
                                );
                            }

                            return "Deployed to " +
                                context.get("DEPLOY_TARGET");
                        },
                        false
                    )
                ),
                Map.of("DEPLOY_TARGET", "staging"),
                List.of("Test"),
                environment ->
                    "main".equals(environment.get("GIT_BRANCH"))
            )
        );

        List<PostActionDefinition> postActions = List.of(

            new PostActionDefinition(
                "Build notification",
                PostCondition.ALWAYS,
                context -> System.out.println(
                    "Notification processed"
                )
            ),

            new PostActionDefinition(
                "Archive successful artifact",
                PostCondition.SUCCESS,
                context -> System.out.println(
                    "Successful artifact archived"
                )
            ),

            new PostActionDefinition(
                "Failure alert",
                PostCondition.FAILURE,
                context -> System.out.println(
                    "Failure alert dispatched"
                )
            ),

            new PostActionDefinition(
                "Cleanup",
                PostCondition.CLEANUP,
                context -> System.out.println(
                    "Temporary resources removed"
                )
            )
        );

        JenkinsPipeline pipeline = new JenkinsPipeline(
            "Enterprise Customer Service CI/CD",
            Map.of(
                "GIT_BRANCH", "main",
                "BUILD_NUMBER", "307",
                "TEST_RESULT", "PASS",
                "TESTS_REQUIRED", "true",
                "DEPLOY_TARGET", "staging"
            ),
            stages,
            postActions,
            policy
        );

        PipelineReport report = pipeline.execute();

        System.out.println("\nENTERPRISE PIPELINE REPORT");
        System.out.println("Pipeline: " + report.pipelineName());
        System.out.println("Status: " + report.status());
        System.out.println("Duration: " + report.duration());

        report.stages().forEach(stage ->
            System.out.printf(
                "%-15s %-10s %s%n",
                stage.name(),
                stage.status(),
                stage.duration()
            )
        );

        if (report.status() != BuildStatus.SUCCESS) {
            System.exit(1);
        }

        System.out.println("\nValidation completed successfully.");
    }
}

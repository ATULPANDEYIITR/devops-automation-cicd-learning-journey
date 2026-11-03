import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Predicate;

public final class JenkinsPipelineDemo {

    enum PipelineKind {
        DECLARATIVE,
        SCRIPTED
    }

    enum StageState {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILED,
        SKIPPED,
        UNSTABLE
    }

    enum BuildState {
        SUCCESS,
        FAILURE,
        UNSTABLE
    }

    @FunctionalInterface
    interface StageAction {
        void execute(PipelineContext context, int attempt) throws Exception;
    }

    @FunctionalInterface
    interface ScriptedProgram {
        void execute(ScriptRuntime runtime) throws Exception;
    }

    record StageSpec(
        String name,
        Set<String> dependencies,
        String agent,
        int retries,
        boolean optional,
        Predicate<PipelineContext> condition,
        StageAction action
    ) {
        StageSpec {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Stage name cannot be empty"
                );
            }
            if (agent == null || agent.isBlank()) {
                throw new IllegalArgumentException(
                    "Stage agent cannot be empty"
                );
            }
            if (retries < 0) {
                throw new IllegalArgumentException(
                    "Stage retries cannot be negative"
                );
            }

            dependencies = Set.copyOf(
                dependencies == null ? Set.of() : dependencies
            );
            Objects.requireNonNull(action, "Stage action is required");
            condition = condition == null ? context -> true : condition;
        }
    }

    record PipelineDefinition(
        String name,
        PipelineKind kind,
        List<StageSpec> stages,
        Map<String, Consumer<PipelineContext>> postActions
    ) {
        PipelineDefinition {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Pipeline name cannot be empty"
                );
            }
            Objects.requireNonNull(kind, "Pipeline kind is required");

            stages = List.copyOf(stages);
            postActions = Map.copyOf(
                postActions == null ? Map.of() : postActions
            );

            if (kind != PipelineKind.DECLARATIVE) {
                throw new IllegalArgumentException(
                    "PipelineDefinition is for declarative pipelines"
                );
            }
        }
    }

    record StageRun(
        String name,
        StageState state,
        int attempts,
        Duration duration,
        String message
    ) {}

    record PipelineResult(
        String pipelineName,
        BuildState state,
        List<StageRun> stages,
        Set<String> artifacts,
        List<String> logs
    ) {
        PipelineResult {
            stages = List.copyOf(stages);
            artifacts = Set.copyOf(artifacts);
            logs = List.copyOf(logs);
        }
    }

    static final class PipelineContext {
        private final Map<String, Object> parameters;
        private final Map<String, String> credentials;
        private final ConcurrentHashMap<String, String> artifacts =
            new ConcurrentHashMap<>();
        private final ConcurrentLinkedQueue<String> logs =
            new ConcurrentLinkedQueue<>();

        PipelineContext(
            Map<String, Object> parameters,
            Map<String, String> credentials
        ) {
            this.parameters = Map.copyOf(parameters);
            this.credentials = Map.copyOf(credentials);
        }

        Object parameter(String name) {
            return parameters.get(name);
        }

        boolean booleanParameter(String name) {
            return Boolean.TRUE.equals(parameters.get(name));
        }

        String stringParameter(String name, String fallback) {
            Object value = parameters.get(name);
            return value == null ? fallback : value.toString();
        }

        void addArtifact(String name, String checksum) {
            if (name == null || name.isBlank() ||
                checksum == null || checksum.isBlank()) {
                throw new IllegalArgumentException(
                    "Artifact name and checksum are required"
                );
            }

            String previous = artifacts.putIfAbsent(name, checksum);
            if (previous != null) {
                throw new IllegalStateException(
                    "Artifact already exists: " + name
                );
            }

            log("Artifact registered: " + name);
        }

        void useCredential(
            String credentialId,
            Consumer<String> operation
        ) {
            String secret = credentials.get(credentialId);
            if (secret == null) {
                throw new IllegalStateException(
                    "Credential is unavailable: " + credentialId
                );
            }

            // The secret is passed to a scoped operation rather than
            // placed in a pipeline parameter or artifact.
            operation.accept(secret);
        }

        void log(String message) {
            String safe = message;
            for (String secret : credentials.values()) {
                if (!secret.isEmpty()) {
                    safe = safe.replace(secret, "****");
                }
            }

            logs.add(safe);
            System.out.println(safe);
        }

        Set<String> artifactNames() {
            return Set.copyOf(artifacts.keySet());
        }

        List<String> logEntries() {
            return List.copyOf(logs);
        }
    }

    static final class PipelineExecutionException extends RuntimeException {
        PipelineExecutionException(String message) {
            super(message);
        }

        PipelineExecutionException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class PipelineEngine implements AutoCloseable {
        private final ExecutorService executor;

        PipelineEngine(int workerCount) {
            if (workerCount < 1) {
                throw new IllegalArgumentException(
                    "Worker count must be positive"
                );
            }
            executor = Executors.newFixedThreadPool(workerCount);
        }

        PipelineResult runDeclarative(
            PipelineDefinition definition,
            PipelineContext context
        ) {
            if (definition.kind() != PipelineKind.DECLARATIVE) {
                throw new IllegalArgumentException(
                    "Declarative execution requires a declarative definition"
                );
            }

            Map<String, StageSpec> byName = validateGraph(
                definition.stages()
            );

            Set<String> pending = new LinkedHashSet<>(byName.keySet());
            Map<String, StageRun> results = new LinkedHashMap<>();

            context.log(
                "Starting declarative pipeline: " + definition.name()
            );

            while (!pending.isEmpty()) {
                List<StageSpec> ready = definition.stages().stream()
                    .filter(stage -> pending.contains(stage.name()))
                    .filter(stage -> stage.dependencies().stream()
                        .allMatch(results::containsKey))
                    .toList();

                if (ready.isEmpty()) {
                    throw new PipelineExecutionException(
                        "No ready stage remains; dependency graph is inconsistent"
                    );
                }

                List<StageSpec> runnable = new ArrayList<>();

                for (StageSpec stage : ready) {
                    boolean blocked = stage.dependencies().stream()
                        .map(results::get)
                        .anyMatch(result ->
                            result.state() != StageState.SUCCESS
                        );

                    if (blocked) {
                        results.put(
                            stage.name(),
                            skipped(stage.name(),
                                "A dependency did not succeed")
                        );
                        context.log(
                            "[" + stage.name() + "] skipped due to dependency"
                        );
                    } else {
                        try {
                            if (stage.condition().test(context)) {
                                runnable.add(stage);
                            } else {
                                results.put(
                                    stage.name(),
                                    skipped(stage.name(),
                                        "Condition evaluated to false")
                                );
                                context.log(
                                    "[" + stage.name() + "] condition skipped stage"
                                );
                            }
                        } catch (RuntimeException error) {
                            results.put(
                                stage.name(),
                                new StageRun(
                                    stage.name(),
                                    StageState.FAILED,
                                    0,
                                    Duration.ZERO,
                                    error.getMessage()
                                )
                            );
                        }
                    }

                    pending.remove(stage.name());
                }

                List<CompletableFuture<StageRun>> futures =
                    runnable.stream()
                        .map(stage -> CompletableFuture.supplyAsync(
                            () -> executeStage(stage, context),
                            executor
                        ))
                        .toList();

                for (CompletableFuture<StageRun> future : futures) {
                    StageRun result = future.join();
                    results.put(result.name(), result);
                }
            }

            List<StageRun> orderedResults = definition.stages().stream()
                .map(stage -> results.get(stage.name()))
                .toList();

            BuildState buildState = determineBuildState(orderedResults);

            runPostActions(
                definition.postActions(),
                context,
                buildState
            );

            PipelineResult result = new PipelineResult(
                definition.name(),
                buildState,
                orderedResults,
                context.artifactNames(),
                context.logEntries()
            );

            context.log(
                "Declarative build state: " + result.state()
            );
            return result;
        }

        PipelineResult runScripted(
            String name,
            PipelineContext context,
            ScriptedProgram program,
            Map<String, Consumer<PipelineContext>> postActions
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Pipeline name cannot be empty"
                );
            }

            ScriptRuntime runtime = new ScriptRuntime(this, context);
            boolean scriptFailed = false;

            context.log("Starting scripted pipeline: " + name);

            try {
                program.execute(runtime);
            } catch (Exception error) {
                scriptFailed = true;
                context.log(
                    "Scripted execution failed: " + error.getMessage()
                );
            }

            List<StageRun> stages = runtime.results();
            BuildState state = scriptFailed
                ? BuildState.FAILURE
                : determineBuildState(stages);

            runPostActions(postActions, context, state);

            return new PipelineResult(
                name,
                state,
                stages,
                context.artifactNames(),
                context.logEntries()
            );
        }

        private Map<String, StageSpec> validateGraph(
            List<StageSpec> stages
        ) {
            if (stages.isEmpty()) {
                throw new IllegalArgumentException(
                    "Pipeline must have at least one stage"
                );
            }

            Map<String, StageSpec> byName = new LinkedHashMap<>();

            for (StageSpec stage : stages) {
                if (byName.putIfAbsent(stage.name(), stage) != null) {
                    throw new IllegalArgumentException(
                        "Duplicate stage: " + stage.name()
                    );
                }
            }

            Map<String, Integer> indegree = new HashMap<>();
            Map<String, List<String>> dependents = new HashMap<>();

            for (StageSpec stage : stages) {
                indegree.put(stage.name(), stage.dependencies().size());
                dependents.put(stage.name(), new ArrayList<>());

                for (String dependency : stage.dependencies()) {
                    if (!byName.containsKey(dependency)) {
                        throw new IllegalArgumentException(
                            "Unknown dependency: " + dependency
                        );
                    }
                    if (dependency.equals(stage.name())) {
                        throw new IllegalArgumentException(
                            "A stage cannot depend on itself"
                        );
                    }
                    dependents.get(dependency).add(stage.name());
                }
            }

            List<String> queue = new ArrayList<>();
            indegree.forEach((name, degree) -> {
                if (degree == 0) {
                    queue.add(name);
                }
            });

            int visited = 0;
            for (int cursor = 0; cursor < queue.size(); cursor++) {
                String current = queue.get(cursor);
                visited++;

                for (String dependent : dependents.get(current)) {
                    int degree = indegree.compute(
                        dependent,
                        (key, oldValue) -> oldValue - 1
                    );
                    if (degree == 0) {
                        queue.add(dependent);
                    }
                }
            }

            if (visited != stages.size()) {
                throw new IllegalArgumentException(
                    "Pipeline contains a dependency cycle"
                );
            }

            return byName;
        }

        private StageRun executeStage(
            StageSpec stage,
            PipelineContext context
        ) {
            Instant start = Instant.now();
            context.log(
                "[" + stage.name() + "] allocated agent " + stage.agent()
            );

            String lastError = "";

            for (int attempt = 1; attempt <= stage.retries() + 1; attempt++) {
                try {
                    stage.action().execute(context, attempt);

                    return new StageRun(
                        stage.name(),
                        StageState.SUCCESS,
                        attempt,
                        Duration.between(start, Instant.now()),
                        "Completed"
                    );
                } catch (Exception error) {
                    lastError = error.getClass().getSimpleName()
                        + ": " + error.getMessage();

                    context.log(
                        "[" + stage.name() + "] attempt " + attempt
                            + " failed: " + lastError
                    );
                }
            }

            StageState state = stage.optional()
                ? StageState.UNSTABLE
                : StageState.FAILED;

            return new StageRun(
                stage.name(),
                state,
                stage.retries() + 1,
                Duration.between(start, Instant.now()),
                lastError
            );
        }

        private StageRun executeScriptedStage(
            StageSpec stage,
            PipelineContext context
        ) {
            return executeStage(stage, context);
        }

        private void runPostActions(
            Map<String, Consumer<PipelineContext>> actions,
            PipelineContext context,
            BuildState state
        ) {
            Set<String> allowed = Set.of(
                "always", "success", "failure", "unstable"
            );

            for (String key : actions.keySet()) {
                if (!allowed.contains(key)) {
                    throw new IllegalArgumentException(
                        "Unsupported post condition: " + key
                    );
                }
            }

            List<String> selected = List.of(
                "always",
                state.name().toLowerCase()
            );

            for (String condition : selected) {
                Consumer<PipelineContext> action = actions.get(condition);
                if (action == null) {
                    continue;
                }

                try {
                    action.accept(context);
                } catch (RuntimeException error) {
                    context.log(
                        "[post:" + condition + "] failed: "
                            + error.getMessage()
                    );
                }
            }
        }

        private static StageRun skipped(String name, String reason) {
            return new StageRun(
                name,
                StageState.SKIPPED,
                0,
                Duration.ZERO,
                reason
            );
        }

        private static BuildState determineBuildState(
            Collection<StageRun> stages
        ) {
            if (stages.stream().anyMatch(
                run -> run.state() == StageState.FAILED
            )) {
                return BuildState.FAILURE;
            }

            if (stages.stream().anyMatch(
                run -> run.state() == StageState.UNSTABLE
            )) {
                return BuildState.UNSTABLE;
            }

            return BuildState.SUCCESS;
        }

        @Override
        public void close() {
            executor.shutdown();
        }
    }

    static final class ScriptRuntime {
        private final PipelineEngine engine;
        private final PipelineContext context;
        private final List<StageRun> completed =
            java.util.Collections.synchronizedList(new ArrayList<>());

        ScriptRuntime(
            PipelineEngine engine,
            PipelineContext context
        ) {
            this.engine = engine;
            this.context = context;
        }

        void stage(StageSpec stage) {
            StageRun result = engine.executeScriptedStage(stage, context);
            completed.add(result);

            if (result.state() == StageState.FAILED) {
                throw new PipelineExecutionException(
                    "Scripted stage failed: " + stage.name()
                );
            }
        }

        void parallel(Map<String, Runnable> branches) {
            if (branches == null || branches.isEmpty()) {
                throw new IllegalArgumentException(
                    "Parallel execution requires at least one branch"
                );
            }

            List<CompletableFuture<Void>> futures = branches.entrySet()
                .stream()
                .map(entry -> CompletableFuture.runAsync(() -> {
                    context.log(
                        "[parallel:" + entry.getKey() + "] started"
                    );
                    entry.getValue().run();
                    context.log(
                        "[parallel:" + entry.getKey() + "] completed"
                    );
                }, engine.executor))
                .toList();

            try {
                CompletableFuture.allOf(
                    futures.toArray(CompletableFuture[]::new)
                ).join();
            } catch (RuntimeException error) {
                throw new PipelineExecutionException(
                    "A scripted parallel branch failed",
                    error
                );
            }
        }

        List<StageRun> results() {
            synchronized (completed) {
                return completed.stream().toList();
            }
        }
    }

    private static StageSpec stage(
        String name,
        Set<String> dependencies,
        String agent,
        int retries,
        boolean optional,
        Predicate<PipelineContext> condition,
        StageAction action
    ) {
        return new StageSpec(
            name,
            dependencies,
            agent,
            retries,
            optional,
            condition,
            action
        );
    }

    private static void printResult(PipelineResult result) {
        System.out.println("\nPipeline: " + result.pipelineName());
        System.out.println("Build state: " + result.state());

        result.stages().stream()
            .sorted(Comparator.comparing(StageRun::name))
            .forEach(run -> System.out.println(
                "  " + run.name()
                    + ": " + run.state()
                    + ", attempts=" + run.attempts()
                    + ", duration=" + run.duration().toMillis() + "ms"
            ));

        System.out.println("Artifacts: " + result.artifacts());
    }

    public static void main(String[] args) {
        Map<String, String> credentials = Map.of(
            "production-deploy-token",
            "prod-secret-98f2"
        );

        try (PipelineEngine engine = new PipelineEngine(3)) {
            PipelineContext declarativeContext = new PipelineContext(
                Map.of(
                    "branch", "main",
                    "deploymentApproved", true
                ),
                credentials
            );

            AtomicInteger integrationAttempts = new AtomicInteger();

            List<StageSpec> declarativeStages = List.of(
                stage(
                    "Checkout",
                    Set.of(),
                    "linux",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.log("Checked out payments-service")
                ),
                stage(
                    "Compile",
                    Set.of("Checkout"),
                    "linux-docker",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.addArtifact(
                            "application.jar",
                            "sha256:abc123"
                        )
                ),
                stage(
                    "Unit Tests",
                    Set.of("Compile"),
                    "linux",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.log("Unit tests passed")
                ),
                stage(
                    "Integration Tests",
                    Set.of("Compile"),
                    "linux-docker",
                    1,
                    false,
                    null,
                    (context, attempt) -> {
                        if (integrationAttempts.incrementAndGet() == 1) {
                            throw new IllegalStateException(
                                "Temporary test service outage"
                            );
                        }
                        context.log("Integration tests passed");
                    }
                ),
                stage(
                    "Package",
                    Set.of("Unit Tests", "Integration Tests"),
                    "linux-docker",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.addArtifact(
                            "payments-release.tar.gz",
                            "sha256:def456"
                        )
                ),
                stage(
                    "Deploy Production",
                    Set.of("Package"),
                    "linux-deploy",
                    0,
                    false,
                    context ->
                        "main".equals(
                            context.stringParameter("branch", "")
                        ) && context.booleanParameter("deploymentApproved"),
                    (context, attempt) ->
                        context.useCredential(
                            "production-deploy-token",
                            token -> context.log(
                                "Deployment credential length: "
                                    + token.length()
                            )
                        )
                )
            );

            PipelineDefinition declarative = new PipelineDefinition(
                "payments-declarative",
                PipelineKind.DECLARATIVE,
                declarativeStages,
                Map.of(
                    "always",
                    context -> context.log(
                        "Declarative cleanup completed"
                    ),
                    "success",
                    context -> context.log(
                        "Declarative pipeline succeeded"
                    )
                )
            );

            PipelineResult declarativeResult =
                engine.runDeclarative(declarative, declarativeContext);

            printResult(declarativeResult);

            PipelineContext scriptedContext = new PipelineContext(
                Map.of("branch", "feature/metrics"),
                credentials
            );

            ScriptedProgram scriptedProgram = runtime -> {
                runtime.stage(stage(
                    "Checkout",
                    Set.of(),
                    "linux",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.log("Scripted checkout completed")
                ));

                runtime.stage(stage(
                    "Build",
                    Set.of(),
                    "linux-docker",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.addArtifact(
                            "scripted-app.jar",
                            "sha256:scripted"
                        )
                ));

                runtime.parallel(Map.of(
                    "unit-tests",
                    () -> runtime.stage(stage(
                        "Unit Tests",
                        Set.of(),
                        "linux",
                        0,
                        false,
                        null,
                        (context, attempt) ->
                            context.log("Scripted unit tests passed")
                    )),
                    "security-scan",
                    () -> runtime.stage(stage(
                        "Security Scan",
                        Set.of(),
                        "linux",
                        0,
                        false,
                        null,
                        (context, attempt) ->
                            context.log("Scripted security scan passed")
                    ))
                ));

                runtime.stage(stage(
                    "Package",
                    Set.of(),
                    "linux-docker",
                    0,
                    false,
                    null,
                    (context, attempt) ->
                        context.addArtifact(
                            "scripted-release.tar.gz",
                            "sha256:release"
                        )
                ));

                if ("main".equals(
                    scriptedContext.stringParameter("branch", "")
                )) {
                    runtime.stage(stage(
                        "Deploy Production",
                        Set.of(),
                        "linux-deploy",
                        0,
                        false,
                        null,
                        (context, attempt) ->
                            context.log("Scripted deployment completed")
                    ));
                } else {
                    scriptedContext.log(
                        "Deployment omitted for a feature branch"
                    );
                }
            };

            PipelineResult scriptedResult = engine.runScripted(
                "payments-scripted",
                scriptedContext,
                scriptedProgram,
                Map.of(
                    "always",
                    context -> context.log(
                        "Scripted cleanup completed"
                    )
                )
            );

            printResult(scriptedResult);
        }
    }
}

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/**
 * Enterprise CI/CD optimization and release governance.
 *
 * Java 17, no external dependencies.
 */
public class CICDOptimization {

    enum StageState {
        PENDING, RUNNING, SUCCESS, CACHED, FAILED, BLOCKED
    }

    enum ReviewState {
        APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
    }

    enum MergeStrategy {
        MERGE_COMMIT, SQUASH, REBASE
    }

    record Artifact(
        String name,
        String content,
        String digest
    ) {
        Artifact {
            Objects.requireNonNull(name);
            Objects.requireNonNull(content);
            Objects.requireNonNull(digest);
        }
    }

    record StageDefinition(
        String id,
        String command,
        List<String> dependencies,
        Map<String, String> inputs,
        Supplier<String> operation
    ) {
        StageDefinition {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                    "Stage ID is required"
                );
            }

            if (command == null || command.isBlank()) {
                throw new IllegalArgumentException(
                    "Stage command is required"
                );
            }

            dependencies = List.copyOf(dependencies);
            inputs = Map.copyOf(inputs);
            Objects.requireNonNull(operation);
        }
    }

    record StageResult(
        StageState state,
        Artifact artifact,
        Duration duration,
        String error
    ) {}

    static class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }
    }

    static class ArtifactRepository {
        private final ConcurrentHashMap<String, Artifact> storage =
            new ConcurrentHashMap<>();

        private final AtomicInteger hits = new AtomicInteger();
        private final AtomicInteger misses = new AtomicInteger();

        Artifact get(String key) {
            Artifact artifact = storage.get(key);

            if (artifact == null) {
                misses.incrementAndGet();
            } else {
                hits.incrementAndGet();
            }

            return artifact;
        }

        void put(String key, Artifact artifact) {
            storage.putIfAbsent(key, artifact);
        }

        void report() {
            System.out.println("Artifact entries: " + storage.size());
            System.out.println("Cache hits: " + hits.get());
            System.out.println("Cache misses: " + misses.get());
        }
    }

    static class PipelineService {
        private final Map<String, StageDefinition> stages;
        private final ArtifactRepository artifacts;
        private final ExecutorService executor;
        private final int maxRetries;

        private final Map<String, StageResult> results =
            new ConcurrentHashMap<>();

        PipelineService(
            List<StageDefinition> definitions,
            ArtifactRepository artifacts,
            int concurrency,
            int maxRetries
        ) {
            if (concurrency < 1 || maxRetries < 0) {
                throw new IllegalArgumentException(
                    "Invalid execution configuration"
                );
            }

            this.artifacts = artifacts;
            this.executor = Executors.newFixedThreadPool(concurrency);
            this.maxRetries = maxRetries;

            Map<String, StageDefinition> indexed =
                new LinkedHashMap<>();

            for (StageDefinition stage : definitions) {
                if (indexed.putIfAbsent(stage.id(), stage) != null) {
                    throw new PipelineException(
                        "Duplicate stage: " + stage.id()
                    );
                }
            }

            this.stages = Collections.unmodifiableMap(indexed);
            validateGraph();
        }

        private void validateGraph() {
            for (StageDefinition stage : stages.values()) {
                for (String dependency : stage.dependencies()) {
                    if (!stages.containsKey(dependency)) {
                        throw new PipelineException(
                            "Unknown dependency: " + dependency
                        );
                    }
                }
            }

            Set<String> visiting = new HashSet<>();
            Set<String> visited = new HashSet<>();

            for (String id : stages.keySet()) {
                visit(id, visiting, visited);
            }
        }

        private void visit(
            String id,
            Set<String> visiting,
            Set<String> visited
        ) {
            if (visiting.contains(id)) {
                throw new PipelineException(
                    "Circular dependency detected"
                );
            }

            if (visited.contains(id)) {
                return;
            }

            visiting.add(id);

            for (String dependency :
                 stages.get(id).dependencies()) {
                visit(dependency, visiting, visited);
            }

            visiting.remove(id);
            visited.add(id);
        }

        private String digest(String value) {
            try {
                MessageDigest md =
                    MessageDigest.getInstance("SHA-256");

                byte[] bytes = md.digest(
                    value.getBytes(StandardCharsets.UTF_8)
                );

                StringBuilder result = new StringBuilder();

                for (byte b : bytes) {
                    result.append(
                        String.format("%02x", b & 0xff)
                    );
                }

                return result.toString();

            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException(e);
            }
        }

        private String cacheKey(StageDefinition stage) {
            StringBuilder key = new StringBuilder();

            key.append(stage.id())
               .append('|')
               .append(stage.command());

            stage.inputs().entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> key
                    .append('|')
                    .append(entry.getKey())
                    .append('=')
                    .append(entry.getValue()));

            stage.dependencies().stream()
                .sorted()
                .forEach(dependency -> {
                    StageResult result = results.get(dependency);

                    if (result == null || result.artifact() == null) {
                        throw new PipelineException(
                            "Dependency artifact unavailable"
                        );
                    }

                    key.append('|')
                       .append(dependency)
                       .append(':')
                       .append(result.artifact().digest());
                });

            return digest(key.toString());
        }

        private StageResult execute(StageDefinition stage) {
            long start = System.nanoTime();

            try {
                String key = cacheKey(stage);

                Artifact cached = artifacts.get(key);

                if (cached != null) {
                    return new StageResult(
                        StageState.CACHED,
                        cached,
                        Duration.ofNanos(System.nanoTime() - start),
                        null
                    );
                }

                RuntimeException lastError = null;

                for (int attempt = 0; attempt <= maxRetries; attempt++) {
                    try {
                        String output = stage.operation().get();

                        if (output == null) {
                            throw new PipelineException(
                                "Stage returned null output"
                            );
                        }

                        Artifact artifact = new Artifact(
                            stage.id(),
                            output,
                            digest(output)
                        );

                        artifacts.put(key, artifact);

                        return new StageResult(
                            StageState.SUCCESS,
                            artifact,
                            Duration.ofNanos(
                                System.nanoTime() - start
                            ),
                            null
                        );

                    } catch (RuntimeException error) {
                        lastError = error;
                    }
                }

                throw lastError;

            } catch (RuntimeException error) {
                return new StageResult(
                    StageState.FAILED,
                    null,
                    Duration.ofNanos(System.nanoTime() - start),
                    error.getMessage()
                );
            }
        }

        Map<String, StageResult> run() {
            results.clear();

            stages.keySet().forEach(id ->
                results.put(
                    id,
                    new StageResult(
                        StageState.PENDING,
                        null,
                        Duration.ZERO,
                        null
                    )
                )
            );

            Map<String, CompletableFuture<StageResult>> futures =
                new HashMap<>();

            try {
                for (StageDefinition stage : stages.values()) {
                    List<CompletableFuture<StageResult>> dependencies =
                        new ArrayList<>();

                    for (String dependency : stage.dependencies()) {
                        dependencies.add(futures.get(dependency));
                    }

                    CompletableFuture<Void> ready =
                        CompletableFuture.allOf(
                            dependencies.toArray(
                                new CompletableFuture<?>[0]
                            )
                        );

                    CompletableFuture<StageResult> future =
                        ready.thenApplyAsync(ignored -> {
                            boolean failed =
                                stage.dependencies().stream()
                                    .map(results::get)
                                    .anyMatch(result ->
                                        result.state() == StageState.FAILED ||
                                        result.state() == StageState.BLOCKED
                                    );

                            if (failed) {
                                return new StageResult(
                                    StageState.BLOCKED,
                                    null,
                                    Duration.ZERO,
                                    "Dependency failure"
                                );
                            }

                            return execute(stage);

                        }, executor).thenApply(result -> {
                            results.put(stage.id(), result);
                            return result;
                        });

                    futures.put(stage.id(), future);
                }

                CompletableFuture.allOf(
                    futures.values().toArray(
                        new CompletableFuture<?>[0]
                    )
                ).join();

            } catch (CompletionException error) {
                throw new PipelineException(
                    "Pipeline execution failed: " +
                    error.getMessage()
                );
            }

            return Collections.unmodifiableMap(
                new LinkedHashMap<>(results)
            );
        }

        void close() {
            executor.shutdown();

            try {
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException error) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    record Review(
        String reviewer,
        boolean eligible,
        ReviewState state,
        boolean stale,
        boolean author
    ) {}

    record BranchProtection(
        int requiredApprovals,
        Set<String> requiredChecks,
        boolean requireResolvedConversations,
        boolean requireUpToDateBranch,
        boolean requireLinearHistory,
        boolean allowDirectPush,
        boolean allowForcePush,
        boolean allowDeletion
    ) {
        BranchProtection {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Approval count cannot be negative"
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    record PullRequest(
        long id,
        String source,
        String target,
        boolean open,
        boolean draft,
        boolean conflicts,
        boolean sourceUpToDate,
        boolean conversationsResolved,
        boolean linearHistoryAvailable,
        List<Review> reviews,
        Map<String, Boolean> checks
    ) {
        PullRequest {
            reviews = List.copyOf(reviews);
            checks = Map.copyOf(checks);
        }
    }

    record Eligibility(
        boolean allowed,
        List<String> violations
    ) {
        Eligibility {
            violations = List.copyOf(violations);
        }
    }

    interface MergePolicy {
        Eligibility evaluate(
            PullRequest request,
            BranchProtection protection
        );
    }

    static class DefaultMergePolicy implements MergePolicy {

        @Override
        public Eligibility evaluate(
            PullRequest request,
            BranchProtection protection
        ) {
            List<String> violations = new ArrayList<>();

            if (!request.open()) {
                violations.add("Pull Request is closed");
            }

            if (request.draft()) {
                violations.add("Draft cannot be merged");
            }

            if (
                request.source() == null ||
                request.target() == null ||
                request.source().isBlank() ||
                request.target().isBlank() ||
                request.source().equals(request.target())
            ) {
                violations.add("Invalid source or target branch");
            }

            if (request.conflicts()) {
                violations.add("Merge conflicts detected");
            }

            if (
                protection.requireUpToDateBranch() &&
                !request.sourceUpToDate()
            ) {
                violations.add("Branch synchronization required");
            }

            if (
                protection.requireResolvedConversations() &&
                !request.conversationsResolved()
            ) {
                violations.add("Unresolved review conversations");
            }

            if (
                protection.requireLinearHistory() &&
                !request.linearHistoryAvailable()
            ) {
                violations.add("Linear history required");
            }

            long approvals = request.reviews().stream()
                .filter(Review::eligible)
                .filter(review -> !review.author())
                .filter(review -> !review.stale())
                .filter(review ->
                    review.state() == ReviewState.APPROVED
                )
                .count();

            if (approvals < protection.requiredApprovals()) {
                violations.add("Insufficient eligible approvals");
            }

            for (String required : protection.requiredChecks()) {
                if (!Boolean.TRUE.equals(
                    request.checks().get(required)
                )) {
                    violations.add(
                        "Required check not passed: " + required
                    );
                }
            }

            return new Eligibility(
                violations.isEmpty(),
                violations
            );
        }
    }

    static class MergeService {
        private final MergePolicy policy;

        MergeService(MergePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        boolean merge(
            PullRequest request,
            BranchProtection protection,
            MergeStrategy strategy
        ) {
            Eligibility eligibility =
                policy.evaluate(request, protection);

            if (!eligibility.allowed()) {
                System.out.println("MERGE REJECTED");

                eligibility.violations().forEach(
                    violation -> System.out.println(
                        "- " + violation
                    )
                );

                return false;
            }

            System.out.println(
                "MERGE AUTHORIZED: PR #" + request.id()
            );

            System.out.println("Strategy: " + strategy);
            return true;
        }
    }

    private static StageDefinition stage(
        String id,
        List<String> dependencies,
        String command,
        String input,
        String output
    ) {
        return new StageDefinition(
            id,
            command,
            dependencies,
            Map.of("version", input),
            () -> {
                System.out.println("Executing " + id);

                try {
                    Thread.sleep(100);
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new PipelineException("Stage interrupted");
                }

                return output;
            }
        );
    }

    private static List<StageDefinition> createStages() {
        return List.of(
            stage("checkout", List.of(), "git checkout", "commit-a", "source"),
            stage("compile", List.of("checkout"), "compile", "gcc-v1", "binary"),
            stage("lint", List.of("checkout"), "static analysis", "rules-v1", "clean"),
            stage("unit", List.of("compile"), "unit tests", "suite-v1", "passed"),
            stage("integration", List.of("compile"), "integration tests", "suite-v1", "passed"),
            stage("security", List.of("checkout"), "security scan", "scan-v1", "passed"),
            stage(
                "package",
                List.of("unit", "integration", "lint", "security"),
                "package",
                "tar-v1",
                "release-package"
            ),
            stage("deploy", List.of("package"), "deploy staging", "staging", "deployed")
        );
    }

    public static void main(String[] args) {
        ArtifactRepository repository = new ArtifactRepository();

        System.out.println("FIRST ENTERPRISE PIPELINE");

        PipelineService first = new PipelineService(
            createStages(),
            repository,
            4,
            1
        );

        try {
            Map<String, StageResult> firstResults = first.run();

            firstResults.forEach((id, result) ->
                System.out.println(
                    id + " -> " + result.state()
                )
            );

            if (firstResults.values().stream().anyMatch(
                result ->
                    result.state() != StageState.SUCCESS &&
                    result.state() != StageState.CACHED
            )) {
                throw new PipelineException("Initial build failed");
            }

        } finally {
            first.close();
        }

        System.out.println("\nSECOND PIPELINE EXECUTION");

        PipelineService second = new PipelineService(
            createStages(),
            repository,
            4,
            1
        );

        try {
            Map<String, StageResult> secondResults = second.run();

            secondResults.forEach((id, result) ->
                System.out.println(
                    id + " -> " + result.state()
                )
            );

        } finally {
            second.close();
        }

        repository.report();

        BranchProtection protection = new BranchProtection(
            2,
            Set.of("build", "unit", "integration", "security"),
            true,
            true,
            true,
            false,
            false,
            false
        );

        PullRequest request = new PullRequest(
            104,
            "feature/parallel-build",
            "main",
            true,
            false,
            false,
            true,
            true,
            true,
            List.of(
                new Review(
                    "reviewer-1",
                    true,
                    ReviewState.APPROVED,
                    false,
                    false
                ),
                new Review(
                    "reviewer-2",
                    true,
                    ReviewState.APPROVED,
                    false,
                    false
                ),
                new Review(
                    "author",
                    false,
                    ReviewState.APPROVED,
                    false,
                    true
                )
            ),
            Map.of(
                "build", true,
                "unit", true,
                "integration", true,
                "security", true
            )
        );

        MergeService mergeService = new MergeService(
            new DefaultMergePolicy()
        );

        System.out.println("\nRELEASE GOVERNANCE");

        mergeService.merge(
            request,
            protection,
            MergeStrategy.SQUASH
        );

        System.out.println("\nEnterprise CI/CD validation completed.");
    }
}

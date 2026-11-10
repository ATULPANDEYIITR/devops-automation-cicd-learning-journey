import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import java.util.stream.Collectors;

/**
 * Enterprise CI/CD Architecture and Repository Governance.
 *
 * Java 17, standard library only.
 */
public class CICDArchitecture {

    enum PRState {
        DRAFT, OPEN, MERGED, CLOSED
    }

    enum ReviewState {
        APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
    }

    enum CheckState {
        PENDING, SUCCESS, FAILURE, CANCELLED
    }

    enum JobState {
        QUEUED, RUNNING, SUCCESS, FAILURE, CANCELLED
    }

    enum Environment {
        DEVELOPMENT, STAGING, PRODUCTION
    }

    enum MergeStrategy {
        MERGE_COMMIT, SQUASH, REBASE
    }

    enum RunnerStatus {
        ONLINE, OFFLINE, DRAINING
    }

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DomainException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends DomainException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class TransitionException extends DomainException {
        TransitionException(String message) {
            super(message);
        }
    }

    static class PipelineException extends DomainException {
        PipelineException(String message) {
            super(message);
        }
    }

    record Commit(
        String sha,
        String message,
        String author,
        Instant timestamp
    ) {
        Commit {
            Objects.requireNonNull(sha);
            Objects.requireNonNull(message);
            Objects.requireNonNull(author);
            Objects.requireNonNull(timestamp);

            if (!sha.matches("[0-9a-f]{7,40}")) {
                throw new ValidationException("Invalid commit SHA.");
            }

            if (message.isBlank() || author.isBlank()) {
                throw new ValidationException(
                    "Commit message and author are required."
                );
            }
        }
    }

    static final class Branch {
        private final String name;
        private final List<Commit> commits = new ArrayList<>();

        Branch(String name) {
            if (name == null || name.isBlank()) {
                throw new ValidationException("Branch name required.");
            }
            this.name = name;
        }

        synchronized void append(Commit commit) {
            if (commits.stream().anyMatch(
                existing -> existing.sha().equals(commit.sha())
            )) {
                throw new ValidationException("Duplicate commit.");
            }

            commits.add(commit);
        }

        synchronized Optional<String> head() {
            return commits.isEmpty()
                ? Optional.empty()
                : Optional.of(commits.get(commits.size() - 1).sha());
        }

        synchronized List<Commit> commits() {
            return List.copyOf(commits);
        }

        String name() {
            return name;
        }
    }

    record Reviewer(
        String username,
        Set<String> roles,
        boolean active
    ) {
        Reviewer {
            if (username == null || username.isBlank()) {
                throw new ValidationException("Username required.");
            }
            roles = Set.copyOf(roles);
        }

        boolean eligible() {
            return active && roles.stream().anyMatch(
                role -> Set.of(
                    "reviewer", "maintainer", "security"
                ).contains(role)
            );
        }
    }

    record ReviewComment(
        String id,
        String path,
        int line,
        String body,
        boolean resolved
    ) {
        ReviewComment {
            if (id == null || path == null || body == null) {
                throw new ValidationException("Invalid review comment.");
            }

            if (line < 1 || body.isBlank()) {
                throw new ValidationException("Invalid comment location.");
            }
        }
    }

    static final class Review {
        private final String reviewer;
        private final ReviewState state;
        private final String commitSha;
        private final Instant submittedAt;
        private final List<ReviewComment> comments;
        private boolean dismissed;

        Review(
            String reviewer,
            ReviewState state,
            String commitSha,
            List<ReviewComment> comments
        ) {
            this.reviewer = reviewer;
            this.state = state;
            this.commitSha = commitSha;
            this.comments = new ArrayList<>(comments);
            this.submittedAt = Instant.now();
        }

        String reviewer() {
            return reviewer;
        }

        ReviewState state() {
            return dismissed ? ReviewState.DISMISSED : state;
        }

        String commitSha() {
            return commitSha;
        }

        Instant submittedAt() {
            return submittedAt;
        }

        void dismiss() {
            dismissed = true;
        }

        List<ReviewComment> comments() {
            return List.copyOf(comments);
        }
    }

    record StatusCheck(
        String name,
        CheckState state,
        String commitSha,
        String details,
        Instant completedAt
    ) {
        StatusCheck {
            Objects.requireNonNull(name);
            Objects.requireNonNull(state);
            Objects.requireNonNull(commitSha);
            Objects.requireNonNull(completedAt);
        }
    }

    static final class Conversation {
        private final String id;
        private final String body;
        private boolean resolved;

        Conversation(String id, String body) {
            this.id = id;
            this.body = body;
        }

        String id() {
            return id;
        }

        String body() {
            return body;
        }

        boolean resolved() {
            return resolved;
        }

        void resolve() {
            resolved = true;
        }
    }

    record BranchProtection(
        int requiredReviews,
        Set<String> requiredChecks,
        boolean requireConversationResolution,
        boolean requireLinearHistory,
        boolean allowDirectPush,
        boolean allowForcePush,
        boolean allowDeletion,
        boolean dismissStaleReviews,
        boolean enforceAdmins,
        Set<MergeStrategy> allowedStrategies
    ) {
        BranchProtection {
            if (requiredReviews < 0) {
                throw new ValidationException(
                    "Required review count cannot be negative."
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
            allowedStrategies = Set.copyOf(allowedStrategies);
        }

        static BranchProtection productionPolicy() {
            return new BranchProtection(
                2,
                Set.of("unit-tests", "security-scan"),
                true,
                true,
                false,
                false,
                false,
                true,
                true,
                EnumSet.of(
                    MergeStrategy.SQUASH,
                    MergeStrategy.MERGE_COMMIT
                )
            );
        }
    }

    static final class PullRequest {
        private final int id;
        private final String title;
        private final String author;
        private final String sourceBranch;
        private final String targetBranch;

        private Optional<String> baseSha;
        private PRState state;
        private final List<String> proposedCommits = new ArrayList<>();
        private final List<Review> reviews = new ArrayList<>();
        private final Map<String, StatusCheck> checks = new HashMap<>();
        private final Map<String, Conversation> conversations =
            new LinkedHashMap<>();
        private final Set<String> requestedReviewers = new HashSet<>();

        private Optional<String> mergedSha = Optional.empty();
        private long version = 1;

        PullRequest(
            int id,
            String title,
            String author,
            String sourceBranch,
            String targetBranch,
            Optional<String> baseSha,
            boolean draft
        ) {
            this.id = id;
            this.title = title;
            this.author = author;
            this.sourceBranch = sourceBranch;
            this.targetBranch = targetBranch;
            this.baseSha = baseSha;
            this.state = draft ? PRState.DRAFT : PRState.OPEN;
        }

        synchronized void open() {
            if (state != PRState.DRAFT && state != PRState.CLOSED) {
                throw new TransitionException("PR cannot be opened.");
            }
            state = PRState.OPEN;
            version++;
        }

        synchronized void addCommit(
            String sha,
            BranchProtection policy
        ) {
            if (state != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }

            if (proposedCommits.contains(sha)) {
                throw new ValidationException("Duplicate proposed commit.");
            }

            proposedCommits.add(sha);

            if (policy.dismissStaleReviews()) {
                reviews.stream()
                    .filter(r -> r.state() == ReviewState.APPROVED)
                    .forEach(Review::dismiss);
            }

            version++;
        }

        synchronized void requestReviewer(String username) {
            if (state != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }
            requestedReviewers.add(username);
        }

        synchronized void addReview(
            Review review,
            Map<String, Reviewer> reviewers
        ) {
            if (state != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }

            Reviewer reviewer = reviewers.get(review.reviewer());

            if (reviewer == null || !reviewer.eligible()) {
                throw new AuthorizationException(
                    "Reviewer is not eligible."
                );
            }

            if (review.reviewer().equals(author)) {
                throw new AuthorizationException(
                    "Self-approval is prohibited."
                );
            }

            if (!proposedCommits.contains(review.commitSha())) {
                throw new ValidationException(
                    "Review references an invalid commit."
                );
            }

            reviews.add(review);
            version++;
        }

        synchronized void addConversation(String id, String body) {
            if (state != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }

            if (conversations.containsKey(id)) {
                throw new ValidationException("Duplicate conversation.");
            }

            conversations.put(id, new Conversation(id, body));
        }

        synchronized void resolveConversation(String id) {
            Conversation conversation = conversations.get(id);

            if (conversation == null) {
                throw new ValidationException("Unknown conversation.");
            }

            conversation.resolve();
        }

        synchronized void setCheck(StatusCheck check) {
            checks.put(check.name(), check);
        }

        synchronized Map<String, Review> latestReviews() {
            Map<String, Review> latest = new HashMap<>();

            reviews.stream()
                .sorted(Comparator.comparing(Review::submittedAt))
                .forEach(review ->
                    latest.put(review.reviewer(), review)
                );

            return latest;
        }

        synchronized List<String> proposedCommits() {
            return List.copyOf(proposedCommits);
        }

        synchronized Map<String, StatusCheck> checks() {
            return Map.copyOf(checks);
        }

        synchronized List<Conversation> conversations() {
            return List.copyOf(conversations.values());
        }

        synchronized void close() {
            if (state != PRState.OPEN && state != PRState.DRAFT) {
                throw new TransitionException("PR cannot be closed.");
            }
            state = PRState.CLOSED;
        }

        int id() {
            return id;
        }

        String author() {
            return author;
        }

        String title() {
            return title;
        }

        String sourceBranch() {
            return sourceBranch;
        }

        String targetBranch() {
            return targetBranch;
        }

        PRState state() {
            return state;
        }

        Optional<String> baseSha() {
            return baseSha;
        }

        void setBaseSha(Optional<String> sha) {
            baseSha = sha;
            version++;
        }

        void markMerged(String sha) {
            if (state != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }
            mergedSha = Optional.of(sha);
            state = PRState.MERGED;
            version++;
        }
    }

    record MergeDecision(
        boolean eligible,
        List<String> reasons,
        int approvalCount
    ) {
        MergeDecision {
            reasons = List.copyOf(reasons);
        }
    }

    static final class Repository {
        private final String name;
        private final Map<String, Branch> branches = new HashMap<>();
        private final Map<String, Reviewer> reviewers = new HashMap<>();
        private final Map<String, BranchProtection> policies =
            new HashMap<>();
        private final Map<Integer, PullRequest> pullRequests =
            new HashMap<>();
        private int nextId = 1;

        Repository(String name) {
            if (name == null || name.isBlank()) {
                throw new ValidationException("Repository name required.");
            }
            this.name = name;
        }

        synchronized void addBranch(Branch branch) {
            if (branches.putIfAbsent(branch.name(), branch) != null) {
                throw new ValidationException("Branch already exists.");
            }
        }

        synchronized void registerReviewer(Reviewer reviewer) {
            reviewers.put(reviewer.username(), reviewer);
        }

        synchronized void protect(
            String branchName,
            BranchProtection policy
        ) {
            if (!branches.containsKey(branchName)) {
                throw new ValidationException("Branch does not exist.");
            }
            policies.put(branchName, policy);
        }

        synchronized PullRequest createPR(
            String title,
            String author,
            String source,
            String target,
            boolean draft
        ) {
            if (title == null || title.isBlank()) {
                throw new ValidationException("PR title required.");
            }

            if (source.equals(target)) {
                throw new ValidationException("Branches must differ.");
            }

            Branch sourceBranch = branches.get(source);
            Branch targetBranch = branches.get(target);

            if (sourceBranch == null || targetBranch == null) {
                throw new ValidationException("Unknown branch.");
            }

            PullRequest pr = new PullRequest(
                nextId++,
                title,
                author,
                source,
                target,
                targetBranch.head(),
                draft
            );

            Set<String> targetShas = targetBranch.commits().stream()
                .map(Commit::sha)
                .collect(Collectors.toSet());

            sourceBranch.commits().stream()
                .map(Commit::sha)
                .filter(sha -> !targetShas.contains(sha))
                .forEach(pr.proposedCommits::add);

            pullRequests.put(pr.id(), pr);
            return pr;
        }

        synchronized MergeDecision evaluate(PullRequest pr) {
            List<String> reasons = new ArrayList<>();

            if (pr.state() != PRState.OPEN) {
                return new MergeDecision(
                    false,
                    List.of("PR is not open."),
                    0
                );
            }

            BranchProtection policy = policies.get(pr.targetBranch());

            if (policy == null) {
                return new MergeDecision(
                    false,
                    List.of("No branch protection policy."),
                    0
                );
            }

            Branch source = branches.get(pr.sourceBranch());
            Branch target = branches.get(pr.targetBranch());

            if (!pr.baseSha().equals(target.head())) {
                reasons.add(
                    "Target branch changed; synchronize the PR."
                );
            }

            List<String> commits = pr.proposedCommits();

            if (commits.isEmpty()) {
                reasons.add("No proposed commits.");
            }

            Set<String> sourceShas = source.commits().stream()
                .map(Commit::sha)
                .collect(Collectors.toSet());

            if (!sourceShas.containsAll(commits)) {
                reasons.add("Proposed commits are absent from source.");
            }

            String head = source.head().orElse("");
            int approvals = 0;

            for (Map.Entry<String, Review> entry :
                pr.latestReviews().entrySet()) {

                Review review = entry.getValue();
                Reviewer reviewer = reviewers.get(entry.getKey());

                if (
                    review.state() == ReviewState.CHANGES_REQUESTED &&
                    review.commitSha().equals(head)
                ) {
                    reasons.add(
                        "Changes requested by " + entry.getKey() + "."
                    );
                }

                if (
                    review.state() == ReviewState.APPROVED &&
                    review.commitSha().equals(head) &&
                    reviewer != null &&
                    reviewer.eligible() &&
                    !entry.getKey().equals(pr.author())
                ) {
                    approvals++;
                }
            }

            if (approvals < policy.requiredReviews()) {
                reasons.add(
                    "Insufficient approvals: " + approvals +
                    "/" + policy.requiredReviews()
                );
            }

            Map<String, StatusCheck> checks = pr.checks();

            for (String required : policy.requiredChecks()) {
                StatusCheck check = checks.get(required);

                if (
                    check == null ||
                    check.state() != CheckState.SUCCESS ||
                    !check.commitSha().equals(head)
                ) {
                    reasons.add("Required check not successful: " + required);
                }
            }

            if (policy.requireConversationResolution()) {
                pr.conversations().stream()
                    .filter(c -> !c.resolved())
                    .forEach(c ->
                        reasons.add(
                            "Unresolved conversation: " + c.id()
                        )
                    );
            }

            return new MergeDecision(
                reasons.isEmpty(),
                reasons,
                approvals
            );
        }

        synchronized void synchronize(PullRequest pr) {
            if (pr.state() != PRState.OPEN) {
                throw new TransitionException("PR is not open.");
            }

            pr.setBaseSha(
                branches.get(pr.targetBranch()).head()
            );
        }

        synchronized String merge(
            PullRequest pr,
            MergeStrategy strategy
        ) {
            BranchProtection policy = policies.get(pr.targetBranch());

            if (
                policy == null ||
                !policy.allowedStrategies().contains(strategy)
            ) {
                throw new AuthorizationException(
                    "Merge strategy is prohibited."
                );
            }

            MergeDecision decision = evaluate(pr);

            if (!decision.eligible()) {
                throw new AuthorizationException(
                    String.join("; ", decision.reasons())
                );
            }

            Branch source = branches.get(pr.sourceBranch());
            Branch target = branches.get(pr.targetBranch());

            String material = name + ":" + pr.id() + ":" +
                strategy + ":" + source.head() + ":" + target.head();

            String mergedSha = sha256(material);

            target.append(new Commit(
                mergedSha,
                "Merge PR #" + pr.id() + ": " + pr.title(),
                "repository-service",
                Instant.now()
            ));

            pr.markMerged(mergedSha);
            return mergedSha;
        }

        String name() {
            return name;
        }
    }

    record RunnerConfig(
        String id,
        Set<String> labels,
        int capacity
    ) {
        RunnerConfig {
            if (id == null || id.isBlank() || capacity < 1) {
                throw new ValidationException("Invalid runner.");
            }
            labels = Set.copyOf(labels);
        }
    }

    static final class Runner {
        private final RunnerConfig config;
        private RunnerStatus status = RunnerStatus.ONLINE;
        private int runningJobs;

        Runner(RunnerConfig config) {
            this.config = config;
        }

        synchronized boolean available(Set<String> requirements) {
            return status == RunnerStatus.ONLINE &&
                runningJobs < config.capacity() &&
                config.labels().containsAll(requirements);
        }

        synchronized void acquire() {
            if (runningJobs >= config.capacity()) {
                throw new TransitionException("Runner is full.");
            }
            runningJobs++;
        }

        synchronized void release() {
            if (runningJobs <= 0) {
                throw new TransitionException("Runner accounting error.");
            }
            runningJobs--;
        }

        String id() {
            return config.id();
        }

        int load() {
            return runningJobs;
        }
    }

    record JobDefinition(
        String id,
        String name,
        Set<String> requiredLabels,
        Supplier<String> action
    ) {
        JobDefinition {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
            Objects.requireNonNull(action);
            requiredLabels = Set.copyOf(requiredLabels);
        }
    }

    static final class PipelineJob {
        private final JobDefinition definition;
        private JobState state = JobState.QUEUED;
        private String runnerId;
        private String output;
        private String failure;

        PipelineJob(JobDefinition definition) {
            this.definition = definition;
        }

        JobState state() {
            return state;
        }

        String name() {
            return definition.name();
        }
    }

    static final class RunnerScheduler {
        private final Map<String, Runner> runners = new HashMap<>();

        synchronized void register(RunnerConfig config) {
            if (runners.containsKey(config.id())) {
                throw new ValidationException("Duplicate runner.");
            }
            runners.put(config.id(), new Runner(config));
        }

        synchronized Runner acquire(Set<String> labels) {
            return runners.values().stream()
                .filter(r -> r.available(labels))
                .min(Comparator.comparingInt(Runner::load))
                .map(r -> {
                    r.acquire();
                    return r;
                })
                .orElseThrow(() ->
                    new PipelineException("No compatible runner.")
                );
        }

        synchronized void release(String runnerId) {
            Runner runner = runners.get(runnerId);

            if (runner == null) {
                throw new TransitionException("Unknown runner.");
            }

            runner.release();
        }
    }

    static final class Pipeline {
        private final String id;
        private final String commitSha;
        private final List<List<PipelineJob>> stages;
        private final RunnerScheduler scheduler;
        private JobState state = JobState.QUEUED;
        private final ExecutorService executor;
        private Instant startedAt;
        private Instant completedAt;

        Pipeline(
            String id,
            String commitSha,
            List<List<JobDefinition>> definitions,
            RunnerScheduler scheduler,
            int parallelism
        ) {
            if (parallelism < 1 || definitions.isEmpty()) {
                throw new ValidationException("Invalid pipeline.");
            }

            this.id = id;
            this.commitSha = commitSha;
            this.scheduler = scheduler;
            this.executor = Executors.newFixedThreadPool(parallelism);

            this.stages = definitions.stream()
                .map(stage -> stage.stream()
                    .map(PipelineJob::new)
                    .collect(Collectors.toCollection(ArrayList::new)))
                .collect(Collectors.toCollection(ArrayList::new));
        }

        void execute() {
            state = JobState.RUNNING;
            startedAt = Instant.now();

            try {
                for (List<PipelineJob> stage : stages) {
                    List<CompletableFuture<Void>> futures = stage.stream()
                        .map(job -> CompletableFuture.runAsync(
                            () -> executeJob(job),
                            executor
                        ))
                        .toList();

                    CompletableFuture.allOf(
                        futures.toArray(CompletableFuture[]::new)
                    ).join();

                    boolean failed = stage.stream().anyMatch(
                        job -> job.state == JobState.FAILURE
                    );

                    if (failed) {
                        throw new PipelineException(
                            "A pipeline stage failed."
                        );
                    }
                }

                state = JobState.SUCCESS;
            } catch (CompletionException | PipelineException error) {
                state = JobState.FAILURE;
                throw new PipelineException(
                    "Pipeline execution failed: " + error.getMessage()
                );
            } finally {
                completedAt = Instant.now();
                executor.shutdown();

                try {
                    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                        executor.shutdownNow();
                    }
                } catch (InterruptedException error) {
                    executor.shutdownNow();
                    Thread.currentThread().interrupt();
                }
            }
        }

        private void executeJob(PipelineJob job) {
            Runner runner = scheduler.acquire(
                job.definition.requiredLabels()
            );

            job.runnerId = runner.id();
            job.state = JobState.RUNNING;

            try {
                job.output = job.definition.action().get();
                job.state = JobState.SUCCESS;
            } catch (RuntimeException error) {
                job.failure = error.getMessage();
                job.state = JobState.FAILURE;
                throw error;
            } finally {
                scheduler.release(runner.id());
            }
        }

        JobState state() {
            return state;
        }

        String commitSha() {
            return commitSha;
        }

        List<PipelineJob> jobs() {
            return stages.stream()
                .flatMap(List::stream)
                .toList();
        }
    }

    record Artifact(
        String name,
        String digest,
        String commitSha,
        long sizeBytes,
        Instant createdAt
    ) {}

    static final class ArtifactRegistry {
        private final Map<String, Artifact> artifacts =
            new HashMap<>();

        private final long maxBytes;

        ArtifactRegistry(long maxBytes) {
            if (maxBytes < 1) {
                throw new ValidationException("Invalid artifact limit.");
            }
            this.maxBytes = maxBytes;
        }

        synchronized Artifact publish(
            String name,
            byte[] content,
            String commitSha
        ) {
            if (
                name == null || name.isBlank() ||
                content == null || content.length == 0 ||
                commitSha == null
            ) {
                throw new ValidationException("Invalid artifact.");
            }

            if (content.length > maxBytes) {
                throw new ValidationException("Artifact exceeds limit.");
            }

            String digest = sha256(content);

            Artifact artifact = new Artifact(
                name,
                digest,
                commitSha,
                content.length,
                Instant.now()
            );

            artifacts.putIfAbsent(digest, artifact);
            return artifacts.get(digest);
        }

        synchronized Artifact verify(String digest) {
            Artifact artifact = artifacts.get(digest);

            if (artifact == null) {
                throw new ValidationException("Artifact not found.");
            }

            return artifact;
        }
    }

    record Deployment(
        String artifactDigest,
        String commitSha,
        Environment environment,
        Instant deployedAt,
        Optional<String> previousDigest
    ) {}

    static final class DeploymentService {
        private final ArtifactRegistry registry;
        private final Map<Environment, Deployment> current =
            new HashMap<>();
        private final Deque<Deployment> history = new ArrayDeque<>();

        DeploymentService(ArtifactRegistry registry) {
            this.registry = registry;
        }

        synchronized Deployment deploy(
            String digest,
            Environment environment,
            Pipeline pipeline,
            boolean authorized,
            Optional<String> expectedCurrentDigest
        ) {
            Artifact artifact = registry.verify(digest);

            if (pipeline.state() != JobState.SUCCESS) {
                throw new PipelineException(
                    "Deployment requires successful pipeline."
                );
            }

            if (!artifact.commitSha().equals(pipeline.commitSha())) {
                throw new PipelineException("Artifact commit mismatch.");
            }

            if (
                environment == Environment.PRODUCTION &&
                !authorized
            ) {
                throw new AuthorizationException(
                    "Production deployment requires authorization."
                );
            }

            Deployment existing = current.get(environment);
            Optional<String> actual = existing == null
                ? Optional.empty()
                : Optional.of(existing.artifactDigest());

            if (
                expectedCurrentDigest.isPresent() &&
                !expectedCurrentDigest.equals(actual)
            ) {
                throw new TransitionException(
                    "Environment changed concurrently."
                );
            }

            Deployment deployment = new Deployment(
                digest,
                artifact.commitSha(),
                environment,
                Instant.now(),
                actual
            );

            current.put(environment, deployment);
            history.push(deployment);
            return deployment;
        }

        synchronized Optional<Deployment> current(
            Environment environment
        ) {
            return Optional.ofNullable(current.get(environment));
        }
    }

    static String sha256(String value) {
        return sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    static String sha256(byte[] bytes) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");

            byte[] result = digest.digest(bytes);
            StringBuilder hex = new StringBuilder();

            for (byte value : result) {
                hex.append(String.format("%02x", value));
            }

            return hex.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    static void testGovernance() {
        Repository repository = new Repository("payment-platform");

        Branch main = new Branch("main");
        main.append(new Commit(
            "aaaaaaa",
            "Initial release",
            "admin",
            Instant.now()
        ));

        Branch feature = new Branch("feature/payment");
        feature.append(new Commit(
            "aaaaaaa",
            "Initial release",
            "admin",
            Instant.now()
        ));
        feature.append(new Commit(
            "bbbbbbb",
            "Add payment validation",
            "developer",
            Instant.now()
        ));

        repository.addBranch(main);
        repository.addBranch(feature);

        repository.registerReviewer(
            new Reviewer("alice", Set.of("reviewer"), true)
        );
        repository.registerReviewer(
            new Reviewer("bob", Set.of("maintainer"), true)
        );

        repository.protect(
            "main",
            BranchProtection.productionPolicy()
        );

        PullRequest pr = repository.createPR(
            "Payment validation",
            "developer",
            "feature/payment",
            "main",
            false
        );

        pr.addReview(
            new Review(
                "alice",
                ReviewState.APPROVED,
                "bbbbbbb",
                List.of()
            ),
            Map.of(
                "alice", new Reviewer(
                    "alice", Set.of("reviewer"), true
                )
            )
        );

        pr.addReview(
            new Review(
                "bob",
                ReviewState.APPROVED,
                "bbbbbbb",
                List.of()
            ),
            Map.of(
                "bob", new Reviewer(
                    "bob", Set.of("maintainer"), true
                )
            )
        );

        pr.setCheck(new StatusCheck(
            "unit-tests",
            CheckState.SUCCESS,
            "bbbbbbb",
            "125 tests passed",
            Instant.now()
        ));

        pr.setCheck(new StatusCheck(
            "security-scan",
            CheckState.SUCCESS,
            "bbbbbbb",
            "No critical findings",
            Instant.now()
        ));

        pr.addConversation("review-1", "Security review complete.");
        pr.resolveConversation("review-1");

        assert repository.evaluate(pr).eligible();

        String merged = repository.merge(pr, MergeStrategy.SQUASH);

        assert merged.length() == 64;
        assert pr.state() == PRState.MERGED;

        boolean rejected = false;

        try {
            repository.merge(pr, MergeStrategy.REBASE);
        } catch (DomainException error) {
            rejected = true;
        }

        assert rejected;
    }

    static void testPipelineAndDeployment() {
        RunnerScheduler scheduler = new RunnerScheduler();

        scheduler.register(new RunnerConfig(
            "linux-runner-01",
            Set.of("linux", "java", "docker"),
            2
        ));

        List<List<JobDefinition>> definitions = List.of(
            List.of(
                new JobDefinition(
                    "lint-1",
                    "lint",
                    Set.of("linux", "java"),
                    () -> "Lint completed"
                )
            ),
            List.of(
                new JobDefinition(
                    "test-1",
                    "unit-tests",
                    Set.of("linux", "java"),
                    () -> "125 tests passed"
                ),
                new JobDefinition(
                    "security-1",
                    "security-scan",
                    Set.of("linux", "java"),
                    () -> "No critical findings"
                )
            ),
            List.of(
                new JobDefinition(
                    "build-1",
                    "container-build",
                    Set.of("linux", "docker"),
                    () -> "Container built"
                )
            )
        );

        Pipeline pipeline = new Pipeline(
            "pipeline-001",
            "bbbbbbb",
            definitions,
            scheduler,
            2
        );

        pipeline.execute();

        assert pipeline.state() == JobState.SUCCESS;
        assert pipeline.jobs().size() == 4;

        ArtifactRegistry registry = new ArtifactRegistry(
            50 * 1024 * 1024
        );

        Artifact artifact = registry.publish(
            "payment-service.tar",
            "compiled-payment-service-v1".getBytes(
                StandardCharsets.UTF_8
            ),
            "bbbbbbb"
        );

        DeploymentService deployment = new DeploymentService(registry);

        deployment.deploy(
            artifact.digest(),
            Environment.STAGING,
            pipeline,
            false,
            Optional.empty()
        );

        assert deployment.current(Environment.STAGING).isPresent();

        boolean rejected = false;

        try {
            deployment.deploy(
                artifact.digest(),
                Environment.PRODUCTION,
                pipeline,
                false,
                Optional.empty()
            );
        } catch (AuthorizationException error) {
            rejected = true;
        }

        assert rejected;
    }

    public static void main(String[] args) {
        try {
            testGovernance();
            testPipelineAndDeployment();

            System.out.println("All enterprise CI/CD tests passed.");
            System.out.println();

            System.out.println("IMPLEMENTED COMPONENTS");
            System.out.println("- Repository and branch domain model");
            System.out.println("- Pull Request state transitions");
            System.out.println("- Review and approval evaluation");
            System.out.println("- Branch protection enforcement");
            System.out.println("- Runner scheduling");
            System.out.println("- Parallel pipeline execution");
            System.out.println("- Artifact integrity");
            System.out.println("- Environment promotion");
            System.out.println("- Production authorization");

        } catch (RuntimeException error) {
            System.err.println(
                "CI/CD execution failed: " + error.getMessage()
            );
            System.exit(1);
        }
    }
}

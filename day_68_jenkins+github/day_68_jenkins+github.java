import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Enterprise Jenkins + GitHub repository governance.
 *
 * Java 17
 * No third-party dependencies.
 *
 * Models:
 * - Repository and branch lifecycle
 * - GitHub webhook and SCM polling triggers
 * - Jenkins build execution
 * - Pull Requests and proposed changes
 * - Code review and approval decisions
 * - Status checks
 * - Branch protection
 * - Merge eligibility and state transitions
 */

public class JenkinsGitHubEnterprise {

    // ========================================================
    // 1. ENUMERATIONS
    // ========================================================

    enum EventType {
        PUSH,
        PULL_REQUEST,
        PULL_REQUEST_REVIEW,
        STATUS_CHECK,
        PING
    }

    enum TriggerType {
        WEBHOOK,
        SCM_POLL,
        MANUAL
    }

    enum PRState {
        OPEN,
        DRAFT,
        CLOSED,
        MERGED
    }

    enum ReviewState {
        APPROVED,
        CHANGES_REQUESTED,
        COMMENTED,
        DISMISSED
    }

    enum CheckState {
        SUCCESS,
        FAILURE,
        PENDING,
        ERROR
    }

    enum BuildState {
        QUEUED,
        RUNNING,
        SUCCESS,
        FAILURE,
        ABORTED
    }

    // ========================================================
    // 2. EXCEPTIONS
    // ========================================================

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends RuntimeException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class MergeRejectedException extends RuntimeException {
        private final List<String> reasons;

        MergeRejectedException(List<String> reasons) {
            super(String.join("; ", reasons));
            this.reasons = List.copyOf(reasons);
        }

        public List<String> getReasons() {
            return reasons;
        }
    }

    // ========================================================
    // 3. VALIDATION
    // ========================================================

    static final Pattern SHA_PATTERN =
            Pattern.compile("[0-9a-f]{7,64}");

    static final Pattern BRANCH_PATTERN =
            Pattern.compile("[A-Za-z0-9._/-]{1,255}");

    static void validateSHA(String sha) {
        if (sha == null || !SHA_PATTERN.matcher(sha).matches()) {
            throw new DomainException("Invalid commit SHA");
        }
    }

    static void validateBranch(String branch) {
        if (
            branch == null ||
            !BRANCH_PATTERN.matcher(branch).matches() ||
            branch.startsWith("-") ||
            branch.contains("..")
        ) {
            throw new DomainException("Invalid branch name");
        }
    }

    // ========================================================
    // 4. IMMUTABLE DOMAIN RECORDS
    // ========================================================

    record Commit(
            String sha,
            String message,
            String author,
            Instant createdAt
    ) {
        Commit {
            validateSHA(sha);
            Objects.requireNonNull(message);
            Objects.requireNonNull(author);
            Objects.requireNonNull(createdAt);

            if (message.isBlank() || author.isBlank()) {
                throw new DomainException(
                        "Commit message and author are required"
                );
            }
        }
    }

    record Review(
            String reviewer,
            ReviewState state,
            String commitSHA,
            Instant submittedAt
    ) {
        Review {
            Objects.requireNonNull(reviewer);
            Objects.requireNonNull(state);
            Objects.requireNonNull(submittedAt);

            validateSHA(commitSHA);

            if (reviewer.isBlank()) {
                throw new DomainException("Reviewer is required");
            }
        }
    }

    record StatusCheck(
            String name,
            CheckState state,
            String commitSHA,
            Instant updatedAt
    ) {
        StatusCheck {
            Objects.requireNonNull(name);
            Objects.requireNonNull(state);
            Objects.requireNonNull(updatedAt);

            validateSHA(commitSHA);

            if (name.isBlank()) {
                throw new DomainException("Check name is required");
            }
        }
    }

    record ReviewComment(
            long id,
            String reviewer,
            String filePath,
            int line,
            String content,
            boolean resolved
    ) {
        ReviewComment {
            Objects.requireNonNull(reviewer);
            Objects.requireNonNull(filePath);
            Objects.requireNonNull(content);

            if (
                id <= 0 ||
                line <= 0 ||
                reviewer.isBlank() ||
                filePath.isBlank() ||
                content.isBlank()
            ) {
                throw new DomainException("Invalid review comment");
            }
        }

        ReviewComment resolve() {
            return new ReviewComment(
                    id,
                    reviewer,
                    filePath,
                    line,
                    content,
                    true
            );
        }
    }

    // ========================================================
    // 5. BRANCH MODEL
    // ========================================================

    static final class Branch {

        private final String name;
        private String headSHA;
        private final boolean protectedBranch;

        Branch(
                String name,
                String headSHA,
                boolean protectedBranch
        ) {
            validateBranch(name);
            validateSHA(headSHA);

            this.name = name;
            this.headSHA = headSHA;
            this.protectedBranch = protectedBranch;
        }

        String getName() {
            return name;
        }

        String getHeadSHA() {
            return headSHA;
        }

        boolean isProtected() {
            return protectedBranch;
        }

        void updateHead(String newSHA) {
            validateSHA(newSHA);
            this.headSHA = newSHA;
        }
    }

    // ========================================================
    // 6. PULL REQUEST MODEL
    // ========================================================

    static final class PullRequest {

        private final int number;
        private final String sourceBranch;
        private final String targetBranch;

        private String sourceSHA;
        private String targetSHA;

        private PRState state;

        private boolean mergeConflict;
        private boolean baseSynchronized;
        private boolean draft;

        private final List<Commit> commits = new ArrayList<>();
        private final List<Review> reviews = new ArrayList<>();

        private final Map<String, StatusCheck> checks =
                new LinkedHashMap<>();

        private final Map<Long, ReviewComment> comments =
                new LinkedHashMap<>();

        PullRequest(
                int number,
                String sourceBranch,
                String targetBranch,
                String sourceSHA,
                String targetSHA,
                List<Commit> commits,
                boolean draft
        ) {
            if (number <= 0) {
                throw new DomainException("Invalid PR number");
            }

            validateBranch(sourceBranch);
            validateBranch(targetBranch);
            validateSHA(sourceSHA);
            validateSHA(targetSHA);

            if (sourceBranch.equals(targetBranch)) {
                throw new DomainException(
                        "Source and target must differ"
                );
            }

            if (commits == null || commits.isEmpty()) {
                throw new DomainException(
                        "Pull Request must contain commits"
                );
            }

            this.number = number;
            this.sourceBranch = sourceBranch;
            this.targetBranch = targetBranch;
            this.sourceSHA = sourceSHA;
            this.targetSHA = targetSHA;
            this.commits.addAll(commits);
            this.draft = draft;
            this.state = draft ? PRState.DRAFT : PRState.OPEN;
            this.baseSynchronized = true;
        }

        int getNumber() {
            return number;
        }

        String getSourceBranch() {
            return sourceBranch;
        }

        String getTargetBranch() {
            return targetBranch;
        }

        String getSourceSHA() {
            return sourceSHA;
        }

        String getTargetSHA() {
            return targetSHA;
        }

        PRState getState() {
            return state;
        }

        boolean isDraft() {
            return draft;
        }

        boolean hasMergeConflict() {
            return mergeConflict;
        }

        boolean isBaseSynchronized() {
            return baseSynchronized;
        }

        List<Review> getReviews() {
            return Collections.unmodifiableList(reviews);
        }

        Map<String, StatusCheck> getChecks() {
            return Collections.unmodifiableMap(checks);
        }

        Map<Long, ReviewComment> getComments() {
            return Collections.unmodifiableMap(comments);
        }

        void addReview(Review review) {
            requireOpen();
            reviews.add(review);
        }

        void updateCheck(StatusCheck check) {
            requireOpen();
            checks.put(check.name(), check);
        }

        void addComment(ReviewComment comment) {
            requireOpen();

            if (comments.containsKey(comment.id())) {
                throw new DomainException("Duplicate comment ID");
            }

            comments.put(comment.id(), comment);
        }

        void resolveComment(long id) {
            ReviewComment comment = comments.get(id);

            if (comment == null) {
                throw new DomainException("Comment not found");
            }

            comments.put(id, comment.resolve());
        }

        void synchronizeSource(String newSHA) {
            requireOpen();
            validateSHA(newSHA);

            sourceSHA = newSHA;

            // Previous checks and approvals are retained as history.
            // Their old commit SHA prevents them from satisfying policy.
        }

        void synchronizeBase(String newTargetSHA) {
            requireOpen();
            validateSHA(newTargetSHA);

            targetSHA = newTargetSHA;
            baseSynchronized = true;
        }

        void setBaseSynchronized(boolean synchronizedState) {
            requireOpen();
            baseSynchronized = synchronizedState;
        }

        void setMergeConflict(boolean conflict) {
            requireOpen();
            mergeConflict = conflict;
        }

        void close() {
            if (state == PRState.MERGED) {
                throw new DomainException(
                        "Merged PR cannot be closed"
                );
            }

            state = PRState.CLOSED;
        }

        void reopen() {
            if (state != PRState.CLOSED) {
                throw new DomainException(
                        "Only closed PR can be reopened"
                );
            }

            state = draft ? PRState.DRAFT : PRState.OPEN;
        }

        void markMerged() {
            requireOpen();

            if (draft) {
                throw new DomainException(
                        "Draft PR cannot be merged"
                );
            }

            state = PRState.MERGED;
        }

        private void requireOpen() {
            if (state != PRState.OPEN) {
                throw new DomainException(
                        "Operation requires an open Pull Request"
                );
            }
        }
    }

    // ========================================================
    // 7. BRANCH PROTECTION POLICY
    // ========================================================

    record BranchProtectionPolicy(
            String branchName,
            int requiredApprovals,
            Set<String> requiredChecks,
            boolean requireConversationResolution,
            boolean requireUpToDate,
            boolean requireCodeOwnerApproval,
            boolean requireLinearHistory,
            boolean allowDirectPush,
            boolean allowForcePush,
            boolean allowDeletion,
            boolean dismissStaleApprovals,
            boolean administratorBypass
    ) {
        BranchProtectionPolicy {
            validateBranch(branchName);

            if (requiredApprovals < 0) {
                throw new DomainException(
                        "Required approvals cannot be negative"
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    // ========================================================
    // 8. REPOSITORY MODEL
    // ========================================================

    static final class Repository {

        private final String name;

        private final Map<String, Branch> branches =
                new TreeMap<>();

        private final Map<String, Commit> commits =
                new HashMap<>();

        private final Map<Integer, PullRequest> pullRequests =
                new TreeMap<>();

        private final Map<String, BranchProtectionPolicy> policies =
                new HashMap<>();

        private final Set<String> eligibleReviewers =
                new HashSet<>();

        private final Set<String> codeOwners =
                new HashSet<>();

        Repository(String name) {
            if (name == null || name.isBlank()) {
                throw new DomainException(
                        "Repository name is required"
                );
            }

            this.name = name;
        }

        String getName() {
            return name;
        }

        void addBranch(Branch branch) {
            if (branches.putIfAbsent(
                    branch.getName(),
                    branch
            ) != null) {
                throw new DomainException("Duplicate branch");
            }
        }

        void addCommit(Commit commit) {
            commits.put(commit.sha(), commit);
        }

        void addReviewer(String reviewer) {
            if (reviewer == null || reviewer.isBlank()) {
                throw new DomainException("Invalid reviewer");
            }

            eligibleReviewers.add(reviewer);
        }

        void addCodeOwner(String reviewer) {
            addReviewer(reviewer);
            codeOwners.add(reviewer);
        }

        void setPolicy(BranchProtectionPolicy policy) {
            if (!branches.containsKey(policy.branchName())) {
                throw new DomainException(
                        "Protection policy references unknown branch"
                );
            }

            policies.put(policy.branchName(), policy);
        }

        Branch getBranch(String name) {
            Branch branch = branches.get(name);

            if (branch == null) {
                throw new DomainException("Branch not found");
            }

            return branch;
        }

        PullRequest getPullRequest(int number) {
            PullRequest pr = pullRequests.get(number);

            if (pr == null) {
                throw new DomainException("PR not found");
            }

            return pr;
        }

        Optional<BranchProtectionPolicy> getPolicy(String branch) {
            return Optional.ofNullable(policies.get(branch));
        }

        Set<String> getEligibleReviewers() {
            return Collections.unmodifiableSet(eligibleReviewers);
        }

        Set<String> getCodeOwners() {
            return Collections.unmodifiableSet(codeOwners);
        }

        void createPullRequest(
                int number,
                String source,
                String target,
                List<Commit> changes,
                boolean draft
        ) {
            if (pullRequests.containsKey(number)) {
                throw new DomainException("Duplicate PR number");
            }

            Branch sourceBranch = getBranch(source);
            Branch targetBranch = getBranch(target);

            if (source.equals(target)) {
                throw new DomainException("Invalid PR branches");
            }

            if (changes == null || changes.isEmpty()) {
                throw new DomainException("Empty changeset");
            }

            changes.forEach(this::addCommit);

            PullRequest pr = new PullRequest(
                    number,
                    source,
                    target,
                    sourceBranch.getHeadSHA(),
                    targetBranch.getHeadSHA(),
                    changes,
                    draft
            );

            pullRequests.put(number, pr);
        }

        void submitReview(
                int number,
                String reviewer,
                ReviewState state
        ) {
            if (!eligibleReviewers.contains(reviewer)) {
                throw new AuthorizationException(
                        "Reviewer is not eligible"
                );
            }

            PullRequest pr = getPullRequest(number);

            pr.addReview(
                    new Review(
                            reviewer,
                            state,
                            pr.getSourceSHA(),
                            Instant.now()
                    )
            );
        }

        void publishCheck(
                int number,
                String name,
                CheckState state
        ) {
            PullRequest pr = getPullRequest(number);

            pr.updateCheck(
                    new StatusCheck(
                            name,
                            state,
                            pr.getSourceSHA(),
                            Instant.now()
                    )
            );
        }

        void addReviewComment(
                int number,
                ReviewComment comment
        ) {
            getPullRequest(number).addComment(comment);
        }

        void resolveDiscussion(int number, long commentId) {
            getPullRequest(number).resolveComment(commentId);
        }

        void synchronizeSource(int number, String newSHA) {
            getPullRequest(number).synchronizeSource(newSHA);
        }

        void synchronizeBase(int number, String newSHA) {
            getPullRequest(number).synchronizeBase(newSHA);
        }

        void updateBranchHead(String branch, String sha) {
            getBranch(branch).updateHead(sha);
        }

        Map<Integer, PullRequest> getPullRequests() {
            return Collections.unmodifiableMap(pullRequests);
        }
    }

    // ========================================================
    // 9. MERGE DECISION
    // ========================================================

    record MergeDecision(
            boolean eligible,
            List<String> reasons
    ) {
        MergeDecision {
            reasons = List.copyOf(reasons);
        }
    }

    // ========================================================
    // 10. POLICY EVALUATION SERVICE
    // ========================================================

    static final class MergeEligibilityService {

        MergeDecision evaluate(
                Repository repository,
                PullRequest pr,
                boolean administrator
        ) {
            List<String> reasons = new ArrayList<>();

            if (pr.getState() != PRState.OPEN) {
                reasons.add("PR is not open");
            }

            if (pr.isDraft()) {
                reasons.add("Draft PR cannot be merged");
            }

            BranchProtectionPolicy policy =
                    repository.getPolicy(pr.getTargetBranch())
                            .orElse(null);

            if (policy == null) {
                return new MergeDecision(
                        reasons.isEmpty(),
                        reasons
                );
            }

            if (
                administrator &&
                policy.administratorBypass() &&
                !pr.hasMergeConflict() &&
                !pr.isDraft()
            ) {
                return new MergeDecision(true, List.of());
            }

            if (pr.hasMergeConflict()) {
                reasons.add("Merge conflict exists");
            }

            if (
                policy.requireUpToDate() &&
                !pr.isBaseSynchronized()
            ) {
                reasons.add("Source branch must be synchronized");
            }

            if (policy.requireConversationResolution()) {
                boolean unresolved = pr.getComments()
                        .values()
                        .stream()
                        .anyMatch(comment -> !comment.resolved());

                if (unresolved) {
                    reasons.add("Unresolved discussions exist");
                }
            }

            for (String required : policy.requiredChecks()) {
                StatusCheck check = pr.getChecks().get(required);

                if (check == null) {
                    reasons.add("Missing required check: " + required);
                    continue;
                }

                if (check.state() != CheckState.SUCCESS) {
                    reasons.add(
                            "Check " + required +
                            " is " + check.state()
                    );
                }

                if (!check.commitSHA().equals(pr.getSourceSHA())) {
                    reasons.add("Check " + required + " is stale");
                }
            }

            // Use the latest review decision from each eligible reviewer.
            Map<String, Review> latestReviews = pr.getReviews()
                    .stream()
                    .filter(review ->
                            repository.getEligibleReviewers()
                                    .contains(review.reviewer())
                    )
                    .filter(review ->
                            !policy.dismissStaleApprovals() ||
                            review.commitSHA().equals(pr.getSourceSHA())
                    )
                    .collect(Collectors.toMap(
                            Review::reviewer,
                            review -> review,
                            (previous, latest) ->
                                    latest.submittedAt().isAfter(
                                            previous.submittedAt()
                                    ) ? latest : previous
                    ));

            Set<String> approvals = latestReviews.values()
                    .stream()
                    .filter(review ->
                            review.state() == ReviewState.APPROVED
                    )
                    .map(Review::reviewer)
                    .collect(Collectors.toSet());

            if (approvals.size() < policy.requiredApprovals()) {
                reasons.add(
                        "Insufficient approvals: " +
                        approvals.size() + "/" +
                        policy.requiredApprovals()
                );
            }

            if (policy.requireCodeOwnerApproval()) {
                boolean approvedByOwner = approvals.stream()
                        .anyMatch(repository.getCodeOwners()::contains);

                if (!approvedByOwner) {
                    reasons.add("Code owner approval required");
                }
            }

            return new MergeDecision(
                    reasons.isEmpty(),
                    reasons
            );
        }
    }

    // ========================================================
    // 11. MERGE SERVICE
    // ========================================================

    static final class MergeService {

        private final Repository repository;

        private final MergeEligibilityService eligibilityService =
                new MergeEligibilityService();

        MergeService(Repository repository) {
            this.repository = repository;
        }

        void merge(int prNumber, String mergeSHA) {
            validateSHA(mergeSHA);

            PullRequest pr = repository.getPullRequest(prNumber);

            MergeDecision decision =
                    eligibilityService.evaluate(
                            repository,
                            pr,
                            false
                    );

            if (!decision.eligible()) {
                throw new MergeRejectedException(decision.reasons());
            }

            // In production, the actual Git merge must succeed before
            // committing the repository state transition.
            repository.addCommit(
                    new Commit(
                            mergeSHA,
                            "Merge pull request #" + prNumber,
                            "jenkins",
                            Instant.now()
                    )
            );

            repository.updateBranchHead(
                    pr.getTargetBranch(),
                    mergeSHA
            );

            pr.markMerged();
        }
    }

    // ========================================================
    // 12. JENKINS BUILD MODEL
    // ========================================================

    record Build(
            long id,
            String repository,
            String branch,
            String commitSHA,
            TriggerType trigger,
            BuildState state,
            Instant createdAt
    ) {
        Build {
            validateSHA(commitSHA);
            validateBranch(branch);
            Objects.requireNonNull(trigger);
            Objects.requireNonNull(state);
            Objects.requireNonNull(createdAt);
        }

        Build withState(BuildState newState) {
            return new Build(
                    id,
                    repository,
                    branch,
                    commitSHA,
                    trigger,
                    newState,
                    createdAt
            );
        }
    }

    // ========================================================
    // 13. JENKINS SERVICE
    // ========================================================

    static final class JenkinsService {

        private long nextId = 1;

        private final Map<Long, Build> builds =
                new LinkedHashMap<>();

        private final Set<String> pending =
                new HashSet<>();

        synchronized Optional<Build> enqueue(
                String repository,
                String branch,
                String sha,
                TriggerType trigger
        ) {
            validateSHA(sha);
            validateBranch(branch);

            String key = repository + ":" + sha;

            if (!pending.add(key)) {
                return Optional.empty();
            }

            Build build = new Build(
                    nextId++,
                    repository,
                    branch,
                    sha,
                    trigger,
                    BuildState.QUEUED,
                    Instant.now()
            );

            builds.put(build.id(), build);

            return Optional.of(build);
        }

        synchronized Build execute(
                long buildId,
                boolean pipelineSuccess
        ) {
            Build build = builds.get(buildId);

            if (build == null) {
                throw new DomainException("Build not found");
            }

            if (build.state() != BuildState.QUEUED) {
                throw new DomainException("Build is not queued");
            }

            Build running = build.withState(BuildState.RUNNING);
            builds.put(buildId, running);

            Build completed = running.withState(
                    pipelineSuccess
                            ? BuildState.SUCCESS
                            : BuildState.FAILURE
            );

            builds.put(buildId, completed);

            pending.remove(
                    build.repository() + ":" + build.commitSHA()
            );

            return completed;
        }

        synchronized List<Build> getHistory() {
            return List.copyOf(builds.values());
        }
    }

    // ========================================================
    // 14. SCM POLLING SERVICE
    // ========================================================

    static final class SCMPollingService {

        private final Map<String, String> observed =
                new HashMap<>();

        synchronized boolean hasChanged(
                String repository,
                String branch,
                String remoteSHA
        ) {
            validateBranch(branch);
            validateSHA(remoteSHA);

            String key = repository + ":" + branch;

            String previous = observed.put(key, remoteSHA);

            return !remoteSHA.equals(previous);
        }
    }

    // ========================================================
    // 15. WEBHOOK DELIVERY REGISTRY
    // ========================================================

    static final class WebhookDeliveryRegistry {

        private final Set<String> processed =
                new HashSet<>();

        synchronized boolean accept(String deliveryId) {
            if (deliveryId == null || deliveryId.isBlank()) {
                throw new DomainException("Missing delivery ID");
            }

            return processed.add(deliveryId);
        }
    }

    // ========================================================
    // 16. WEBHOOK EVENT
    // ========================================================

    record WebhookEvent(
            String deliveryId,
            EventType eventType,
            String repository,
            String branch,
            String commitSHA
    ) {
        WebhookEvent {
            Objects.requireNonNull(deliveryId);
            Objects.requireNonNull(eventType);
            Objects.requireNonNull(repository);

            if (deliveryId.isBlank() || repository.isBlank()) {
                throw new DomainException("Invalid webhook event");
            }

            if (
                eventType == EventType.PUSH ||
                eventType == EventType.PULL_REQUEST
            ) {
                validateBranch(branch);
                validateSHA(commitSHA);
            }
        }
    }

    // ========================================================
    // 17. WEBHOOK PROCESSOR
    // ========================================================

    static final class WebhookProcessor {

        private final WebhookDeliveryRegistry registry;
        private final JenkinsService jenkins;

        WebhookProcessor(
                WebhookDeliveryRegistry registry,
                JenkinsService jenkins
        ) {
            this.registry = registry;
            this.jenkins = jenkins;
        }

        Optional<Build> process(WebhookEvent event) {
            if (!registry.accept(event.deliveryId())) {
                return Optional.empty();
            }

            if (
                event.eventType() == EventType.PING ||
                event.eventType() == EventType.PULL_REQUEST_REVIEW ||
                event.eventType() == EventType.STATUS_CHECK
            ) {
                return Optional.empty();
            }

            return jenkins.enqueue(
                    event.repository(),
                    event.branch(),
                    event.commitSHA(),
                    TriggerType.WEBHOOK
            );
        }
    }

    // ========================================================
    // 18. APPLICATION DEMONSTRATION
    // ========================================================

    public static void main(String[] args) {

        try {
            System.out.println(
                    "=== ENTERPRISE JENKINS + GITHUB ===\n"
            );

            Repository repository =
                    new Repository("payment-service");

            String mainSHA = "a".repeat(40);
            String featureSHA = "b".repeat(40);

            repository.addBranch(
                    new Branch("main", mainSHA, true)
            );

            repository.addBranch(
                    new Branch(
                            "feature/payment-validation",
                            featureSHA,
                            false
                    )
            );

            repository.addCommit(
                    new Commit(
                            mainSHA,
                            "Initial production release",
                            "platform-team",
                            Instant.now()
                    )
            );

            Commit featureCommit = new Commit(
                    featureSHA,
                    "Add payment validation",
                    "developer",
                    Instant.now()
            );

            repository.addCommit(featureCommit);

            repository.addReviewer("reviewer-alice");
            repository.addReviewer("reviewer-bob");
            repository.addCodeOwner("reviewer-alice");

            BranchProtectionPolicy policy =
                    new BranchProtectionPolicy(
                            "main",
                            2,
                            Set.of(
                                    "unit-tests",
                                    "integration-tests",
                                    "security-scan"
                            ),
                            true,
                            true,
                            true,
                            false,
                            false,
                            false,
                            false,
                            true,
                            false
                    );

            repository.setPolicy(policy);

            repository.createPullRequest(
                    101,
                    "feature/payment-validation",
                    "main",
                    List.of(featureCommit),
                    false
            );

            // Code review decisions.
            repository.submitReview(
                    101,
                    "reviewer-alice",
                    ReviewState.APPROVED
            );

            repository.submitReview(
                    101,
                    "reviewer-bob",
                    ReviewState.APPROVED
            );

            // Jenkins status checks.
            repository.publishCheck(
                    101,
                    "unit-tests",
                    CheckState.SUCCESS
            );

            repository.publishCheck(
                    101,
                    "integration-tests",
                    CheckState.SUCCESS
            );

            repository.publishCheck(
                    101,
                    "security-scan",
                    CheckState.SUCCESS
            );

            // Review conversation.
            repository.addReviewComment(
                    101,
                    new ReviewComment(
                            1,
                            "reviewer-alice",
                            "src/payment.java",
                            45,
                            "Validate transaction amount",
                            false
                    )
            );

            repository.resolveDiscussion(101, 1);

            PullRequest pr = repository.getPullRequest(101);

            MergeEligibilityService eligibility =
                    new MergeEligibilityService();

            MergeDecision decision =
                    eligibility.evaluate(
                            repository,
                            pr,
                            false
                    );

            System.out.println(
                    "PR #101 merge eligible: " +
                    decision.eligible()
            );

            if (!decision.eligible()) {
                decision.reasons().forEach(
                        reason -> System.out.println(" - " + reason)
                );
            } else {
                MergeService mergeService =
                        new MergeService(repository);

                mergeService.merge(101, "c".repeat(40));

                System.out.println("PR merged successfully");
            }

            // Jenkins webhook automation.
            System.out.println("\n=== WEBHOOK AUTOMATION ===");

            JenkinsService jenkins = new JenkinsService();

            WebhookProcessor processor =
                    new WebhookProcessor(
                            new WebhookDeliveryRegistry(),
                            jenkins
                    );

            WebhookEvent pushEvent = new WebhookEvent(
                    "github-delivery-001",
                    EventType.PUSH,
                    "payment-service",
                    "feature/payment-validation",
                    featureSHA
            );

            Optional<Build> queued =
                    processor.process(pushEvent);

            queued.ifPresent(build -> {
                System.out.println(
                        "Queued Jenkins build: " + build.id()
                );

                Build completed = jenkins.execute(
                        build.id(),
                        true
                );

                System.out.println(
                        "Build status: " + completed.state()
                );
            });

            // Duplicate delivery is ignored.
            System.out.println(
                    "Duplicate delivery accepted: " +
                    processor.process(pushEvent).isPresent()
            );

            // SCM polling.
            System.out.println("\n=== SCM POLLING ===");

            SCMPollingService polling =
                    new SCMPollingService();

            boolean first = polling.hasChanged(
                    "payment-service",
                    "main",
                    mainSHA
            );

            boolean second = polling.hasChanged(
                    "payment-service",
                    "main",
                    mainSHA
            );

            System.out.println("First poll changed: " + first);
            System.out.println("Second poll changed: " + second);

            // Stale approval demonstration.
            System.out.println("\n=== STALE APPROVAL TEST ===");

            repository.createPullRequest(
                    102,
                    "feature/payment-validation",
                    "main",
                    List.of(featureCommit),
                    false
            );

            repository.submitReview(
                    102,
                    "reviewer-alice",
                    ReviewState.APPROVED
            );

            repository.publishCheck(
                    102,
                    "unit-tests",
                    CheckState.SUCCESS
            );

            repository.publishCheck(
                    102,
                    "integration-tests",
                    CheckState.SUCCESS
            );

            repository.publishCheck(
                    102,
                    "security-scan",
                    CheckState.SUCCESS
            );

            repository.synchronizeSource(
                    102,
                    "d".repeat(40)
            );

            MergeDecision staleDecision =
                    eligibility.evaluate(
                            repository,
                            repository.getPullRequest(102),
                            false
                    );

            System.out.println(
                    "Stale PR eligible: " +
                    staleDecision.eligible()
            );

            staleDecision.reasons().forEach(
                    reason -> System.out.println(" - " + reason)
            );

            System.out.println("\n=== BUILD HISTORY ===");

            jenkins.getHistory().forEach(
                    build -> System.out.println(
                            "Build #" + build.id() +
                            " | " + build.branch() +
                            " | " + build.state()
                    )
            );

        } catch (MergeRejectedException error) {
            System.err.println(
                    "Merge rejected: " + error.getReasons()
            );

        } catch (DomainException | AuthorizationException error) {
            System.err.println(
                    "Domain error: " + error.getMessage()
            );

        } catch (Exception error) {
            System.err.println(
                    "Unexpected failure: " + error.getMessage()
            );
        }
    }
}

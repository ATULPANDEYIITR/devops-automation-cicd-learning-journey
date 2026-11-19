import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Enterprise Multi-Stage CI/CD Governance Platform.
 *
 * Java 17
 * No third-party dependencies.
 *
 * Implements:
 * - Repository and branch domain models
 * - Pull Request lifecycle
 * - Code review and inline discussions
 * - Approval policies
 * - Branch protection
 * - CI pipeline orchestration
 * - Automated quality and security checks
 * - Artifact management
 * - Environment promotion
 * - Deployment approvals
 * - Health checks and rollback
 * - Audit logging
 */
public class EnterpriseCICD {

    // ========================================================
    // ENUMERATIONS
    // ========================================================

    enum PRState {
        DRAFT,
        OPEN,
        MERGED,
        CLOSED
    }

    enum ReviewState {
        APPROVED,
        CHANGES_REQUESTED,
        COMMENTED,
        DISMISSED
    }

    enum CheckState {
        PENDING,
        SUCCESS,
        FAILURE
    }

    enum PipelineState {
        QUEUED,
        RUNNING,
        SUCCESS,
        FAILURE
    }

    enum StageState {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILURE,
        SKIPPED
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum DeploymentState {
        PENDING,
        APPROVED,
        DEPLOYING,
        SUCCESS,
        ROLLED_BACK
    }

    enum MergeStrategy {
        MERGE_COMMIT,
        SQUASH,
        REBASE
    }


    // ========================================================
    // EXCEPTIONS
    // ========================================================

    static class CICDError extends RuntimeException {
        CICDError(String message) {
            super(message);
        }
    }

    static class ValidationException extends CICDError {
        ValidationException(String message) {
            super(message);
        }
    }

    static class PolicyException extends CICDError {
        PolicyException(String message) {
            super(message);
        }
    }

    static class TransitionException extends CICDError {
        TransitionException(String message) {
            super(message);
        }
    }


    // ========================================================
    // UTILITIES
    // ========================================================

    static String id(String prefix) {
        return prefix + "-" +
                UUID.randomUUID().toString().substring(0, 10);
    }

    static String now() {
        return Instant.now().toString();
    }

    static void required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new ValidationException(
                    field + " is required"
            );
        }
    }


    // ========================================================
    // DOMAIN RECORDS
    // ========================================================

    record Commit(
            String id,
            String message,
            String author,
            List<String> files,
            String timestamp
    ) {
        Commit {
            required(id, "Commit ID");
            required(message, "Commit message");
            required(author, "Commit author");

            if (files == null || files.isEmpty()) {
                throw new ValidationException(
                        "Commit must contain files"
                );
            }

            for (String file : files) {
                if (
                        file == null ||
                        file.isBlank() ||
                        file.startsWith("/") ||
                        List.of(file.split("/")).contains("..")
                ) {
                    throw new ValidationException(
                            "Unsafe repository file path"
                    );
                }
            }

            files = List.copyOf(new LinkedHashSet<>(files));
        }
    }

    record ReviewPolicy(
            int requiredApprovals,
            Set<String> eligibleRoles,
            boolean dismissStaleApprovals,
            boolean rejectAuthorApproval
    ) {
        ReviewPolicy {
            if (requiredApprovals < 0) {
                throw new ValidationException(
                        "Invalid approval requirement"
                );
            }

            eligibleRoles = Set.copyOf(eligibleRoles);
        }
    }

    record StatusCheck(
            String name,
            CheckState state,
            String commitId,
            String details
    ) {}

    record AuditEvent(
            String id,
            String actor,
            String action,
            String resource,
            String details,
            String timestamp
    ) {}

    record Eligibility(
            boolean eligible,
            List<String> reasons
    ) {
        Eligibility {
            reasons = List.copyOf(reasons);
        }
    }


    // ========================================================
    // REVIEWER
    // ========================================================

    static final class Reviewer {
        private final String username;
        private final Set<String> roles;
        private final boolean active;

        Reviewer(
                String username,
                Set<String> roles,
                boolean active
        ) {
            required(username, "Reviewer");

            this.username = username;
            this.roles = Set.copyOf(roles);
            this.active = active;
        }

        String username() {
            return username;
        }

        boolean hasEligibleRole(Set<String> allowedRoles) {
            return active &&
                    roles.stream().anyMatch(allowedRoles::contains);
        }
    }


    // ========================================================
    // REVIEW MODEL
    // ========================================================

    static final class Review {
        final String reviewer;
        final ReviewState state;
        final String commitId;
        final List<String> comments;
        final String timestamp;
        boolean dismissed;

        Review(
                String reviewer,
                ReviewState state,
                String commitId,
                List<String> comments
        ) {
            this.reviewer = reviewer;
            this.state = state;
            this.commitId = commitId;
            this.comments = List.copyOf(comments);
            this.timestamp = now();
            this.dismissed = false;
        }
    }

    static final class Conversation {
        final String id;
        final String file;
        final int line;
        final String reviewer;
        final String body;

        boolean resolved;

        Conversation(
                String file,
                int line,
                String reviewer,
                String body
        ) {
            required(file, "Comment file");
            required(reviewer, "Reviewer");
            required(body, "Comment body");

            if (line < 1) {
                throw new ValidationException("Invalid comment line");
            }

            this.id = id("conversation");
            this.file = file;
            this.line = line;
            this.reviewer = reviewer;
            this.body = body;
            this.resolved = false;
        }
    }


    // ========================================================
    // BRANCH AND PROTECTION
    // ========================================================

    static final class BranchProtection {
        final int requiredChecks;
        final Set<String> requiredCheckNames;
        final ReviewPolicy reviewPolicy;

        final boolean requireResolvedConversations;
        final boolean requireLinearHistory;
        final boolean allowDirectPush;
        final boolean allowForcePush;
        final boolean allowDeletion;
        final boolean allowAdminBypass;

        BranchProtection(
                int requiredChecks,
                Set<String> requiredCheckNames,
                ReviewPolicy reviewPolicy,
                boolean requireResolvedConversations,
                boolean requireLinearHistory,
                boolean allowDirectPush,
                boolean allowForcePush,
                boolean allowDeletion,
                boolean allowAdminBypass
        ) {
            if (requiredChecks < 0) {
                throw new ValidationException(
                        "Invalid required check count"
                );
            }

            this.requiredChecks = requiredChecks;
            this.requiredCheckNames = Set.copyOf(
                    requiredCheckNames
            );

            this.reviewPolicy = reviewPolicy;
            this.requireResolvedConversations =
                    requireResolvedConversations;

            this.requireLinearHistory = requireLinearHistory;
            this.allowDirectPush = allowDirectPush;
            this.allowForcePush = allowForcePush;
            this.allowDeletion = allowDeletion;
            this.allowAdminBypass = allowAdminBypass;
        }

        static BranchProtection standard() {
            return new BranchProtection(
                    3,
                    Set.of(
                            "build",
                            "unit_tests",
                            "security_scan"
                    ),
                    new ReviewPolicy(
                            2,
                            Set.of("senior_engineer", "maintainer"),
                            true,
                            true
                    ),
                    true,
                    true,
                    false,
                    false,
                    false,
                    false
            );
        }
    }

    static final class Branch {
        final String name;
        final List<String> commits = new ArrayList<>();

        String head;
        boolean protectedBranch;
        boolean deleted;

        Branch(String name, String head, List<String> history) {
            this.name = name;
            this.head = head;
            this.commits.addAll(history);
        }
    }


    // ========================================================
    // PULL REQUEST
    // ========================================================

    static final class PullRequest {
        final String id;
        final String source;
        final String target;
        final String author;
        final List<String> commits;

        final List<Review> reviews = new ArrayList<>();
        final List<Conversation> conversations =
                new ArrayList<>();

        PRState state;
        MergeStrategy strategy = MergeStrategy.SQUASH;

        PullRequest(
                String source,
                String target,
                String author,
                List<String> commits,
                boolean draft
        ) {
            this.id = id("pr");
            this.source = source;
            this.target = target;
            this.author = author;
            this.commits = new ArrayList<>(commits);

            this.state = draft
                    ? PRState.DRAFT
                    : PRState.OPEN;
        }
    }


    // ========================================================
    // REPOSITORY SERVICE
    // ========================================================

    static final class RepositoryService {
        final String name;

        final Map<String, Branch> branches =
                new LinkedHashMap<>();

        final Map<String, Commit> commits =
                new HashMap<>();

        final Map<String, PullRequest> pullRequests =
                new LinkedHashMap<>();

        final Map<String, BranchProtection> protections =
                new HashMap<>();

        final Map<String, Reviewer> reviewers =
                new HashMap<>();

        final List<AuditEvent> auditLog =
                new ArrayList<>();

        RepositoryService(String name) {
            required(name, "Repository name");

            this.name = name;

            branches.put(
                    "main",
                    new Branch("main", null, List.of())
            );

            branches.get("main").protectedBranch = true;
            protections.put("main", BranchProtection.standard());
        }

        void audit(
                String actor,
                String action,
                String resource,
                String details
        ) {
            auditLog.add(new AuditEvent(
                    id("event"),
                    actor,
                    action,
                    resource,
                    details,
                    now()
            ));
        }

        void registerReviewer(Reviewer reviewer) {
            reviewers.put(reviewer.username(), reviewer);
        }

        void createBranch(String name, String base) {
            required(name, "Branch name");

            if (branches.containsKey(name)) {
                throw new ValidationException(
                        "Branch already exists"
                );
            }

            Branch source = branches.get(base);

            if (source == null || source.deleted) {
                throw new ValidationException(
                        "Base branch unavailable"
                );
            }

            branches.put(
                    name,
                    new Branch(
                            name,
                            source.head,
                            source.commits
                    )
            );

            audit("system", "branch_created", name, base);
        }

        Commit addCommit(
                String branchName,
                String message,
                String author,
                List<String> files
        ) {
            Branch branch = branches.get(branchName);

            if (branch == null || branch.deleted) {
                throw new ValidationException(
                        "Branch unavailable"
                );
            }

            if (branch.protectedBranch) {
                BranchProtection policy =
                        protections.get(branchName);

                if (!policy.allowDirectPush) {
                    throw new PolicyException(
                            "Direct push prohibited"
                    );
                }
            }

            Commit commit = new Commit(
                    id("commit"),
                    message,
                    author,
                    files,
                    now()
            );

            commits.put(commit.id(), commit);
            branch.commits.add(commit.id());
            branch.head = commit.id();

            audit(author, "commit_added", branchName, commit.id());

            return commit;
        }

        PullRequest createPR(
                String source,
                String target,
                String author,
                boolean draft
        ) {
            Branch sourceBranch = branches.get(source);
            Branch targetBranch = branches.get(target);

            if (
                    sourceBranch == null ||
                    targetBranch == null ||
                    source.equals(target) ||
                    sourceBranch.deleted ||
                    targetBranch.deleted
            ) {
                throw new ValidationException(
                        "Invalid Pull Request branches"
                );
            }

            Set<String> targetHistory = new HashSet<>(
                    targetBranch.commits
            );

            List<String> proposed = sourceBranch.commits
                    .stream()
                    .filter(commit -> !targetHistory.contains(commit))
                    .toList();

            if (proposed.isEmpty()) {
                throw new ValidationException(
                        "No proposed changes"
                );
            }

            PullRequest pr = new PullRequest(
                    source,
                    target,
                    author,
                    proposed,
                    draft
            );

            pullRequests.put(pr.id, pr);

            audit(
                    author,
                    "pull_request_created",
                    pr.id,
                    source + " -> " + target
            );

            return pr;
        }

        PullRequest openPR(String prId) {
            PullRequest pr = pullRequests.get(prId);

            if (pr == null || pr.state != PRState.OPEN) {
                throw new TransitionException(
                        "Pull Request is not open"
                );
            }

            return pr;
        }

        void markReady(String prId) {
            PullRequest pr = pullRequests.get(prId);

            if (pr == null || pr.state != PRState.DRAFT) {
                throw new TransitionException(
                        "Only draft PRs can become ready"
                );
            }

            pr.state = PRState.OPEN;
        }

        void addReview(
                String prId,
                String reviewerName,
                ReviewState state,
                List<String> comments
        ) {
            PullRequest pr = openPR(prId);

            if (pr.author.equals(reviewerName)) {
                throw new PolicyException(
                        "Self-approval prohibited"
                );
            }

            Reviewer reviewer = reviewers.get(reviewerName);

            if (reviewer == null || !reviewer.active) {
                throw new PolicyException(
                        "Reviewer is not active or registered"
                );
            }

            String head = branches.get(pr.source).head;

            pr.reviews.add(new Review(
                    reviewerName,
                    state,
                    head,
                    comments
            ));

            audit(
                    reviewerName,
                    "review_submitted",
                    prId,
                    state.name()
            );
        }

        void addConversation(
                String prId,
                String file,
                int line,
                String reviewer,
                String body
        ) {
            PullRequest pr = openPR(prId);

            pr.conversations.add(
                    new Conversation(file, line, reviewer, body)
            );
        }

        void resolveConversations(String prId) {
            PullRequest pr = openPR(prId);

            pr.conversations.forEach(
                    conversation -> conversation.resolved = true
            );
        }

        void updateProtection(
                String branchName,
                BranchProtection policy
        ) {
            Branch branch = branches.get(branchName);

            if (branch == null) {
                throw new ValidationException("Branch not found");
            }

            branch.protectedBranch = true;
            protections.put(branchName, policy);

            audit(
                    "administrator",
                    "branch_protection_updated",
                    branchName,
                    "Protection policy replaced"
            );
        }

        void closePR(String prId) {
            PullRequest pr = openPR(prId);
            pr.state = PRState.CLOSED;
        }

        void reopenPR(String prId) {
            PullRequest pr = pullRequests.get(prId);

            if (pr == null || pr.state != PRState.CLOSED) {
                throw new TransitionException(
                        "Only closed PRs can reopen"
                );
            }

            pr.state = PRState.OPEN;
        }

        void merge(String prId) {
            PullRequest pr = openPR(prId);

            Branch source = branches.get(pr.source);
            Branch target = branches.get(pr.target);

            for (String commit : pr.commits) {
                if (!target.commits.contains(commit)) {
                    target.commits.add(commit);
                }
            }

            target.head = source.head;
            pr.state = PRState.MERGED;

            audit(
                    "maintainer",
                    "pull_request_merged",
                    prId,
                    pr.strategy.name()
            );
        }
    }


    // ========================================================
    // APPROVAL POLICY SERVICE
    // ========================================================

    static final class ApprovalService {

        static Eligibility evaluate(
                RepositoryService repository,
                PullRequest pr
        ) {
            BranchProtection protection =
                    repository.protections.get(pr.target);

            if (protection == null) {
                return new Eligibility(true, List.of());
            }

            List<String> reasons = new ArrayList<>();

            ReviewPolicy policy = protection.reviewPolicy;

            String currentHead =
                    repository.branches.get(pr.source).head;

            Set<String> approved = new HashSet<>();

            for (Review review : pr.reviews) {
                if (review.dismissed) continue;

                if (
                        policy.dismissStaleApprovals() &&
                        !Objects.equals(review.commitId, currentHead)
                ) {
                    continue;
                }

                if (review.state == ReviewState.CHANGES_REQUESTED) {
                    reasons.add(
                            "Changes requested by " + review.reviewer
                    );
                    continue;
                }

                if (review.state != ReviewState.APPROVED) {
                    continue;
                }

                Reviewer reviewer =
                        repository.reviewers.get(review.reviewer);

                if (
                        reviewer == null ||
                        !reviewer.hasEligibleRole(policy.eligibleRoles())
                ) {
                    reasons.add(
                            "Ineligible reviewer: " + review.reviewer
                    );
                    continue;
                }

                if (
                        policy.rejectAuthorApproval() &&
                        review.reviewer.equals(pr.author)
                ) {
                    reasons.add("Author approval is invalid");
                    continue;
                }

                approved.add(review.reviewer);
            }

            if (approved.size() < policy.requiredApprovals()) {
                reasons.add(
                        "Insufficient eligible approvals: " +
                        approved.size() + "/" +
                        policy.requiredApprovals()
                );
            }

            return new Eligibility(
                    reasons.isEmpty(),
                    reasons
            );
        }
    }


    // ========================================================
    // PIPELINE DOMAIN
    // ========================================================

    static final class Pipeline {
        final String id = id("pipeline");
        final String commitId;

        PipelineState state = PipelineState.QUEUED;
        final List<StatusCheck> checks = new ArrayList<>();
        final Map<String, StageState> stages =
                new LinkedHashMap<>();

        String artifactHash;

        Pipeline(String commitId) {
            this.commitId = commitId;
        }
    }

    interface StageExecutor {
        String execute(
                Commit commit,
                Pipeline pipeline
        );
    }


    // ========================================================
    // CI PIPELINE SERVICE
    // ========================================================

    static final class PipelineService {
        final RepositoryService repository;

        final Map<String, Pipeline> history =
                new LinkedHashMap<>();

        PipelineService(RepositoryService repository) {
            this.repository = repository;
        }

        Pipeline execute(String commitId) {
            Commit commit = repository.commits.get(commitId);

            if (commit == null) {
                throw new ValidationException(
                        "Commit not found"
                );
            }

            Pipeline pipeline = new Pipeline(commitId);
            history.put(pipeline.id, pipeline);

            pipeline.state = PipelineState.RUNNING;

            Map<String, StageExecutor> stages =
                    new LinkedHashMap<>();

            stages.put(
                    "checkout",
                    (source, run) -> "Checkout successful"
            );

            stages.put(
                    "build",
                    (source, run) -> "Application build successful"
            );

            stages.put(
                    "unit_tests",
                    (source, run) -> "42 unit tests passed"
            );

            stages.put(
                    "integration_tests",
                    (source, run) -> "18 integration tests passed"
            );

            stages.put(
                    "security_scan",
                    (source, run) -> {
                        Set<String> forbidden = Set.of(
                                ".env",
                                "private.key",
                                "id_rsa",
                                "credentials.json"
                        );

                        List<String> violations = source.files()
                                .stream()
                                .filter(file -> forbidden.contains(
                                        file.substring(
                                                file.lastIndexOf('/') + 1
                                        )
                                ))
                                .toList();

                        if (!violations.isEmpty()) {
                            throw new PolicyException(
                                    "Sensitive files detected: " +
                                    violations
                            );
                        }

                        return "Security checks passed";
                    }
            );

            stages.put(
                    "package",
                    (source, run) -> {
                        run.artifactHash =
                                Integer.toHexString(
                                        Objects.hash(
                                                source.id(),
                                                source.files()
                                        )
                                );

                        return "Artifact packaged";
                    }
            );

            for (var entry : stages.entrySet()) {
                String name = entry.getKey();
                StageExecutor executor = entry.getValue();

                pipeline.stages.put(name, StageState.RUNNING);

                try {
                    String output = executor.execute(
                            commit,
                            pipeline
                    );

                    pipeline.stages.put(
                            name,
                            StageState.SUCCESS
                    );

                    pipeline.checks.add(new StatusCheck(
                            name,
                            CheckState.SUCCESS,
                            commitId,
                            output
                    ));

                } catch (RuntimeException error) {
                    pipeline.stages.put(
                            name,
                            StageState.FAILURE
                    );

                    pipeline.checks.add(new StatusCheck(
                            name,
                            CheckState.FAILURE,
                            commitId,
                            error.getMessage()
                    ));

                    pipeline.state = PipelineState.FAILURE;

                    break;
                }
            }

            if (pipeline.state != PipelineState.FAILURE) {
                pipeline.state = PipelineState.SUCCESS;
            }

            return pipeline;
        }
    }


    // ========================================================
    // MERGE GOVERNANCE
    // ========================================================

    static final class MergeService {

        static Eligibility evaluate(
                RepositoryService repository,
                PullRequest pr,
                Pipeline pipeline
        ) {
            List<String> reasons = new ArrayList<>();

            BranchProtection policy =
                    repository.protections.get(pr.target);

            if (policy == null) {
                return new Eligibility(true, List.of());
            }

            Eligibility approvals =
                    ApprovalService.evaluate(repository, pr);

            reasons.addAll(approvals.reasons());

            if (
                    policy.requireResolvedConversations &&
                    pr.conversations.stream().anyMatch(
                            conversation -> !conversation.resolved
                    )
            ) {
                reasons.add("Unresolved review conversations");
            }

            if (pipeline.state != PipelineState.SUCCESS) {
                reasons.add("CI pipeline has not succeeded");
            }

            Map<String, StatusCheck> checks =
                    pipeline.checks.stream().collect(
                            Collectors.toMap(
                                    StatusCheck::name,
                                    check -> check,
                                    (first, second) -> second
                            )
                    );

            for (String required : policy.requiredCheckNames) {
                StatusCheck check = checks.get(required);

                if (
                        check == null ||
                        !check.commitId().equals(
                                repository.branches.get(pr.source).head
                        ) ||
                        check.state() != CheckState.SUCCESS
                ) {
                    reasons.add(
                            "Required status check missing or stale: " +
                            required
                    );
                }
            }

            if (
                    policy.requiredChecks > 0 &&
                    checks.size() < policy.requiredChecks
            ) {
                reasons.add("Insufficient completed status checks");
            }

            return new Eligibility(
                    reasons.isEmpty(),
                    reasons
            );
        }

        static void merge(
                RepositoryService repository,
                PullRequest pr,
                Pipeline pipeline
        ) {
            Eligibility eligibility =
                    evaluate(repository, pr, pipeline);

            if (!eligibility.eligible()) {
                throw new PolicyException(
                        "Merge blocked: " + eligibility.reasons()
                );
            }

            repository.merge(pr.id);
        }
    }


    // ========================================================
    // DEPLOYMENT SERVICE
    // ========================================================

    static final class Deployment {
        final String id = id("deployment");
        final String pipelineId;
        final Environment environment;
        final String version;
        final String previousVersion;

        DeploymentState state = DeploymentState.PENDING;
        String approver;

        Deployment(
                String pipelineId,
                Environment environment,
                String version,
                String previousVersion
        ) {
            this.pipelineId = pipelineId;
            this.environment = environment;
            this.version = version;
            this.previousVersion = previousVersion;
        }
    }

    static final class DeploymentService {
        final Map<Environment, String> activeVersions =
                new EnumMap<>(Environment.class);

        final Map<String, Deployment> deployments =
                new LinkedHashMap<>();

        DeploymentService() {
            for (Environment environment : Environment.values()) {
                activeVersions.put(environment, "0.0.0");
            }
        }

        Deployment request(
                Pipeline pipeline,
                Environment environment,
                String version
        ) {
            if (pipeline.state != PipelineState.SUCCESS) {
                throw new PolicyException(
                        "Successful pipeline required"
                );
            }

            if (!Pattern.matches(
                    "\\d+\\.\\d+\\.\\d+",
                    version
            )) {
                throw new ValidationException(
                        "Invalid semantic version"
                );
            }

            Deployment deployment = new Deployment(
                    pipeline.id,
                    environment,
                    version,
                    activeVersions.get(environment)
            );

            deployments.put(deployment.id, deployment);

            return deployment;
        }

        void approve(
                String deploymentId,
                String username,
                Set<String> roles
        ) {
            Deployment deployment =
                    deployments.get(deploymentId);

            if (
                    deployment == null ||
                    deployment.state != DeploymentState.PENDING
            ) {
                throw new TransitionException(
                        "Deployment is not pending"
                );
            }

            required(username, "Approver");

            if (
                    deployment.environment == Environment.PRODUCTION &&
                    Collections.disjoint(
                            roles,
                            Set.of("release_manager", "platform_admin")
                    )
            ) {
                throw new PolicyException(
                        "Production approval denied"
                );
            }

            deployment.approver = username;
            deployment.state = DeploymentState.APPROVED;
        }

        void deploy(
                String deploymentId,
                boolean healthCheckPassed
        ) {
            Deployment deployment =
                    deployments.get(deploymentId);

            if (
                    deployment == null ||
                    deployment.state != DeploymentState.APPROVED
            ) {
                throw new PolicyException(
                        "Deployment requires approval"
                );
            }

            deployment.state = DeploymentState.DEPLOYING;

            if (!healthCheckPassed) {
                activeVersions.put(
                        deployment.environment,
                        deployment.previousVersion
                );

                deployment.state = DeploymentState.ROLLED_BACK;
                return;
            }

            activeVersions.put(
                    deployment.environment,
                    deployment.version
            );

            deployment.state = DeploymentState.SUCCESS;
        }
    }


    // ========================================================
    // REPORTING
    // ========================================================

    static void report(Pipeline pipeline) {
        System.out.println("\nPIPELINE REPORT");
        System.out.println("Pipeline: " + pipeline.id);
        System.out.println("Commit: " + pipeline.commitId);
        System.out.println("State: " + pipeline.state);

        pipeline.stages.forEach(
                (name, state) ->
                        System.out.printf(
                                "%-22s %s%n",
                                name,
                                state
                        )
        );

        System.out.println(
                "Artifact: " + pipeline.artifactHash
        );
    }


    // ========================================================
    // APPLICATION ENTRY POINT
    // ========================================================

    public static void main(String[] args) {

        try {
            System.out.println(
                    "ENTERPRISE MULTI-STAGE CI/CD PLATFORM"
            );

            RepositoryService repository =
                    new RepositoryService("enterprise-platform");

            repository.registerReviewer(
                    new Reviewer(
                            "reviewer-01",
                            Set.of("senior_engineer"),
                            true
                    )
            );

            repository.registerReviewer(
                    new Reviewer(
                            "reviewer-02",
                            Set.of("maintainer"),
                            true
                    )
            );

            repository.createBranch(
                    "feature/inventory-api",
                    "main"
            );

            Commit commit = repository.addCommit(
                    "feature/inventory-api",
                    "Implement inventory API",
                    "developer-01",
                    List.of(
                            "src/InventoryService.java",
                            "tests/InventoryServiceTest.java",
                            "pom.xml"
                    )
            );

            PullRequest pr = repository.createPR(
                    "feature/inventory-api",
                    "main",
                    "developer-01",
                    false
            );

            repository.addReview(
                    pr.id,
                    "reviewer-01",
                    ReviewState.APPROVED,
                    List.of("Validation and error handling verified")
            );

            repository.addReview(
                    pr.id,
                    "reviewer-02",
                    ReviewState.APPROVED,
                    List.of("Tests and API contract verified")
            );

            repository.addConversation(
                    pr.id,
                    "src/InventoryService.java",
                    45,
                    "reviewer-01",
                    "Verify inventory quantity before reservation"
            );

            repository.resolveConversations(pr.id);

            PipelineService pipelineService =
                    new PipelineService(repository);

            Pipeline pipeline =
                    pipelineService.execute(commit.id());

            report(pipeline);

            Eligibility eligibility =
                    MergeService.evaluate(
                            repository,
                            pr,
                            pipeline
                    );

            System.out.println("\nMERGE ELIGIBILITY");
            System.out.println("Eligible: " + eligibility.eligible());

            eligibility.reasons().forEach(
                    reason -> System.out.println("Blocked: " + reason)
            );

            if (eligibility.eligible()) {
                MergeService.merge(
                        repository,
                        pr,
                        pipeline
                );
            }

            DeploymentService deploymentService =
                    new DeploymentService();

            Deployment staging = deploymentService.request(
                    pipeline,
                    Environment.STAGING,
                    "1.0.0"
            );

            deploymentService.approve(
                    staging.id,
                    "release-operator",
                    Set.of("release_manager")
            );

            deploymentService.deploy(staging.id, true);

            Deployment production = deploymentService.request(
                    pipeline,
                    Environment.PRODUCTION,
                    "1.0.0"
            );

            deploymentService.approve(
                    production.id,
                    "production-manager",
                    Set.of("release_manager")
            );

            // Failed production health check triggers rollback.
            deploymentService.deploy(production.id, false);

            System.out.println("\nDEPLOYMENT REPORT");

            deploymentService.deployments.values().forEach(
                    deployment -> System.out.printf(
                            "%-14s %-10s %s%n",
                            deployment.environment,
                            deployment.version,
                            deployment.state
                    )
            );

            System.out.println("\nACTIVE ENVIRONMENTS");

            deploymentService.activeVersions.forEach(
                    (environment, version) ->
                            System.out.println(
                                    environment + ": " + version
                            )
            );

            System.out.println(
                    "\nFINAL PR STATE: " + pr.state
            );

            System.out.println(
                    "AUDIT EVENTS: " + repository.auditLog.size()
            );

        } catch (CICDError error) {
            System.err.println(
                    "CI/CD ERROR: " + error.getMessage()
            );

            System.exit(1);
        }
    }
}

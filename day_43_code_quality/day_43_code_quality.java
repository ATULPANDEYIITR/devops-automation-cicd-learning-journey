import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.HashSet;

/**
 * Enterprise repository governance and code quality model.
 *
 * Java 17+
 *
 * Compile:
 *   javac CodeQualityGovernance.java
 *
 * Run:
 *   java CodeQualityGovernance
 *
 * The model separates review decisions, approval eligibility, quality-check
 * evidence, and protected-branch policy. It is an executable policy example,
 * not a Git hosting service integration.
 */
public class CodeQualityGovernance {

    enum ReviewState {
        PENDING,
        APPROVED,
        CHANGES_REQUESTED,
        DISMISSED
    }

    enum MergeMethod {
        MERGE_COMMIT,
        SQUASH,
        REBASE
    }

    enum CheckStatus {
        PENDING,
        PASSED,
        FAILED,
        CANCELLED
    }

    record Reviewer(
            String username,
            boolean active,
            boolean canReviewCode,
            boolean bot,
            boolean administrator) {

        Reviewer {
            Objects.requireNonNull(username, "username");
            if (username.isBlank()) {
                throw new IllegalArgumentException("Username cannot be blank.");
            }
        }

        boolean eligibleToReview(String author) {
            return active
                    && canReviewCode
                    && !bot
                    && !username.equals(author);
        }
    }

    record ReviewDecision(
            String reviewer,
            ReviewState state,
            String reviewedCommit,
            String comment) {

        ReviewDecision {
            Objects.requireNonNull(reviewer, "reviewer");
            Objects.requireNonNull(state, "state");
            Objects.requireNonNull(reviewedCommit, "reviewedCommit");
            Objects.requireNonNull(comment, "comment");

            if (reviewer.isBlank() || reviewedCommit.isBlank()) {
                throw new IllegalArgumentException(
                        "Reviewer and reviewed commit are required.");
            }
        }
    }

    record StatusCheck(String name, CheckStatus status, String commitSha) {
        StatusCheck {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(status, "status");
            Objects.requireNonNull(commitSha, "commitSha");

            if (name.isBlank() || commitSha.isBlank()) {
                throw new IllegalArgumentException(
                        "Check name and commit SHA are required.");
            }
        }
    }

    record BranchProtectionPolicy(
            String branchName,
            int requiredApprovals,
            Set<String> requiredChecks,
            boolean requireUpToDateBranch,
            boolean requireResolvedConversations,
            boolean requireLinearHistory,
            boolean allowDirectPushes,
            boolean allowForcePushes,
            boolean allowDeletion,
            boolean allowAdministratorBypass,
            boolean dismissStaleApprovals) {

        BranchProtectionPolicy {
            Objects.requireNonNull(branchName, "branchName");
            Objects.requireNonNull(requiredChecks, "requiredChecks");

            if (branchName.isBlank()) {
                throw new IllegalArgumentException("Branch name is required.");
            }
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                        "Required approvals cannot be negative.");
            }
            requiredChecks = Collections.unmodifiableSet(
                    new HashSet<>(requiredChecks));
        }
    }

    static final class PullRequest {
        private final long number;
        private final String author;
        private final String baseBranch;
        private final String headBranch;
        private String headCommit;
        private boolean open = true;
        private boolean draft;
        private boolean branchUpToDate;
        private boolean mergeConflicts;
        private int unresolvedConversations;
        private final Map<String, ReviewDecision> reviews = new LinkedHashMap<>();
        private final Map<String, StatusCheck> checks = new HashMap<>();

        PullRequest(
                long number,
                String author,
                String baseBranch,
                String headBranch,
                String headCommit) {

            if (number <= 0) {
                throw new IllegalArgumentException(
                        "Pull request number must be positive.");
            }

            this.number = number;
            this.author = requireText(author, "author");
            this.baseBranch = requireText(baseBranch, "baseBranch");
            this.headBranch = requireText(headBranch, "headBranch");
            this.headCommit = requireText(headCommit, "headCommit");
        }

        long number() {
            return number;
        }

        String author() {
            return author;
        }

        String baseBranch() {
            return baseBranch;
        }

        String headCommit() {
            return headCommit;
        }

        boolean isOpen() {
            return open;
        }

        void markDraft(boolean value) {
            requireOpen();
            draft = value;
        }

        void setBranchUpToDate(boolean value) {
            requireOpen();
            branchUpToDate = value;
        }

        void setMergeConflicts(boolean value) {
            requireOpen();
            mergeConflicts = value;
        }

        void setUnresolvedConversations(int count) {
            requireOpen();
            if (count < 0) {
                throw new IllegalArgumentException(
                        "Conversation count cannot be negative.");
            }
            unresolvedConversations = count;
        }

        void submitReview(Reviewer reviewer, ReviewDecision decision) {
            requireOpen();
            Objects.requireNonNull(reviewer, "reviewer");
            Objects.requireNonNull(decision, "decision");

            if (!reviewer.eligibleToReview(author)) {
                throw new IllegalArgumentException(
                        "Reviewer is inactive, unauthorized, a bot, or the author.");
            }
            if (!reviewer.username().equals(decision.reviewer())) {
                throw new IllegalArgumentException(
                        "Decision reviewer does not match reviewer identity.");
            }

            // Each reviewer has one current decision in this compact model.
            reviews.put(reviewer.username(), decision);
        }

        void recordCheck(StatusCheck check) {
            requireOpen();
            Objects.requireNonNull(check, "check");
            checks.put(check.name(), check);
        }

        void pushNewCommit(String commitSha, boolean dismissStaleApprovals) {
            requireOpen();
            headCommit = requireText(commitSha, "commitSha");
            branchUpToDate = false;

            // Check evidence belongs to a specific commit. Old results must
            // not silently certify newly pushed source code.
            checks.entrySet().removeIf(
                    entry -> !entry.getValue().commitSha().equals(headCommit));

            if (dismissStaleApprovals) {
                reviews.replaceAll((username, decision) -> {
                    if (decision.state() == ReviewState.APPROVED
                            && !decision.reviewedCommit().equals(headCommit)) {
                        return new ReviewDecision(
                                username,
                                ReviewState.DISMISSED,
                                decision.reviewedCommit(),
                                "Dismissed because the source commit changed.");
                    }
                    return decision;
                });
            }
        }

        private void requireOpen() {
            if (!open) {
                throw new IllegalStateException(
                        "Closed pull requests cannot be modified.");
            }
        }

        private static String requireText(String value, String field) {
            Objects.requireNonNull(value, field);
            if (value.isBlank()) {
                throw new IllegalArgumentException(field + " cannot be blank.");
            }
            return value;
        }
    }

    record GateResult(
            boolean eligible,
            int validApprovals,
            List<String> blockers,
            List<String> warnings) {

        GateResult {
            blockers = List.copyOf(blockers);
            warnings = List.copyOf(warnings);
        }
    }

    static final class GovernanceService {
        private final BranchProtectionPolicy policy;
        private final Map<String, Reviewer> reviewers = new HashMap<>();
        private final Map<Long, PullRequest> requests = new HashMap<>();

        GovernanceService(BranchProtectionPolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        void registerReviewer(Reviewer reviewer) {
            reviewers.put(reviewer.username(), reviewer);
        }

        void openPullRequest(PullRequest request) {
            Objects.requireNonNull(request, "request");

            if (!request.baseBranch().equals(policy.branchName())) {
                throw new IllegalArgumentException(
                        "Pull request does not target the governed branch.");
            }
            if (requests.putIfAbsent(request.number(), request) != null) {
                throw new IllegalArgumentException(
                        "Pull request number already exists.");
            }
        }

        GateResult evaluate(long number, MergeMethod method) {
            PullRequest request = findRequest(number);
            List<String> blockers = new ArrayList<>();
            List<String> warnings = new ArrayList<>();

            if (!request.open) {
                blockers.add("Pull request is closed.");
            }
            if (request.draft) {
                blockers.add("Draft pull request cannot be merged.");
            }
            if (request.mergeConflicts) {
                blockers.add("Merge conflicts must be resolved.");
            }
            if (policy.requireUpToDateBranch() && !request.branchUpToDate) {
                blockers.add("Source branch must be synchronized with base.");
            }
            if (policy.requireResolvedConversations()
                    && request.unresolvedConversations > 0) {
                blockers.add(
                        request.unresolvedConversations
                                + " review conversation(s) remain unresolved.");
            }
            if (policy.requireLinearHistory()
                    && method == MergeMethod.MERGE_COMMIT) {
                blockers.add("Merge commits violate linear-history policy.");
            }

            int approvals = 0;
            for (ReviewDecision decision : request.reviews.values()) {
                Optional<Reviewer> identity =
                        Optional.ofNullable(reviewers.get(decision.reviewer()));

                if (identity.isEmpty()
                        || !identity.get().eligibleToReview(request.author)) {
                    continue;
                }

                if (decision.state() == ReviewState.CHANGES_REQUESTED
                        && decision.reviewedCommit().equals(request.headCommit())) {
                    blockers.add(
                            "Changes requested by " + decision.reviewer() + ".");
                }

                boolean currentApproval =
                        decision.state() == ReviewState.APPROVED
                                && (!policy.dismissStaleApprovals()
                                || decision.reviewedCommit()
                                        .equals(request.headCommit()));

                if (currentApproval) {
                    approvals++;
                }
            }

            if (approvals < policy.requiredApprovals()) {
                blockers.add(
                        "Current approvals " + approvals + "/"
                                + policy.requiredApprovals() + ".");
            }

            for (String required : policy.requiredChecks()) {
                StatusCheck check = request.checks.get(required);

                if (check == null) {
                    blockers.add("Required check is missing: " + required + ".");
                } else if (!check.commitSha().equals(request.headCommit())) {
                    blockers.add("Required check is stale: " + required + ".");
                } else if (check.status() != CheckStatus.PASSED) {
                    blockers.add(
                            "Required check is not passing: " + required
                                    + " (" + check.status() + ").");
                }
            }

            if (!policy.allowDirectPushes()) {
                warnings.add("Direct pushes are restricted on the protected branch.");
            }
            if (!policy.allowForcePushes()) {
                warnings.add("Force pushes are disabled.");
            }
            if (!policy.allowDeletion()) {
                warnings.add("Protected branch deletion is disabled.");
            }

            return new GateResult(
                    blockers.isEmpty(),
                    approvals,
                    blockers,
                    warnings);
        }

        boolean merge(long number, MergeMethod method) {
            PullRequest request = findRequest(number);
            GateResult result = evaluate(number, method);

            if (!result.eligible()) {
                return false;
            }

            request.open = false;
            return true;
        }

        boolean mayPushDirectly(Reviewer actor) {
            return policy.allowDirectPushes()
                    || (actor.administrator()
                    && policy.allowAdministratorBypass());
        }

        private PullRequest findRequest(long number) {
            PullRequest request = requests.get(number);
            if (request == null) {
                throw new IllegalArgumentException(
                        "Unknown pull request: " + number);
            }
            return request;
        }
    }

    private static void printResult(String label, GateResult result) {
        System.out.println("\n" + label);
        System.out.println("Merge eligible: " + result.eligible());
        System.out.println("Valid approvals: " + result.validApprovals());

        for (String blocker : result.blockers()) {
            System.out.println("BLOCKED: " + blocker);
        }
        for (String warning : result.warnings()) {
            System.out.println("POLICY: " + warning);
        }

        if (result.blockers().isEmpty()) {
            System.out.println("All required conditions are satisfied.");
        }
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " cannot be blank.");
        }
        return value;
    }

    public static void main(String[] args) {
        Set<String> requiredChecks = Set.of(
                "tests",
                "lint",
                "format",
                "static-analysis");

        BranchProtectionPolicy policy = new BranchProtectionPolicy(
                "main",
                2,
                requiredChecks,
                true,
                true,
                true,
                false,
                false,
                false,
                false,
                true);

        GovernanceService service = new GovernanceService(policy);

        Reviewer author = new Reviewer(
                "sam-developer", true, true, false, false);
        Reviewer reviewerOne = new Reviewer(
                "alex-reviewer", true, true, false, false);
        Reviewer reviewerTwo = new Reviewer(
                "morgan-reviewer", true, true, false, false);
        Reviewer automation = new Reviewer(
                "quality-bot", true, true, true, false);

        service.registerReviewer(author);
        service.registerReviewer(reviewerOne);
        service.registerReviewer(reviewerTwo);
        service.registerReviewer(automation);

        PullRequest request = new PullRequest(
                126,
                "sam-developer",
                "main",
                "feature/quality-gate",
                "commit-a126");

        request.setBranchUpToDate(true);
        request.setUnresolvedConversations(0);
        service.openPullRequest(request);

        request.submitReview(
                reviewerOne,
                new ReviewDecision(
                        "alex-reviewer",
                        ReviewState.APPROVED,
                        "commit-a126",
                        "The error paths are covered."));

        request.submitReview(
                reviewerTwo,
                new ReviewDecision(
                        "morgan-reviewer",
                        ReviewState.APPROVED,
                        "commit-a126",
                        "The quality policy is consistent."));

        for (String check : requiredChecks) {
            CheckStatus status = check.equals("static-analysis")
                    ? CheckStatus.FAILED
                    : CheckStatus.PASSED;

            request.recordCheck(
                    new StatusCheck(check, status, "commit-a126"));
        }

        printResult(
                "Initial release review",
                service.evaluate(126, MergeMethod.SQUASH));

        // A commit update invalidates old check evidence and stale approvals.
        request.pushNewCommit("commit-b126", true);
        request.setBranchUpToDate(true);

        printResult(
                "After source changes",
                service.evaluate(126, MergeMethod.SQUASH));

        request.submitReview(
                reviewerOne,
                new ReviewDecision(
                        "alex-reviewer",
                        ReviewState.APPROVED,
                        "commit-b126",
                        "Reviewed the latest source."));

        request.submitReview(
                reviewerTwo,
                new ReviewDecision(
                        "morgan-reviewer",
                        ReviewState.APPROVED,
                        "commit-b126",
                        "Approved the latest source."));

        for (String check : requiredChecks) {
            request.recordCheck(
                    new StatusCheck(check, CheckStatus.PASSED, "commit-b126"));
        }

        printResult(
                "After checks and reviews are refreshed",
                service.evaluate(126, MergeMethod.SQUASH));

        System.out.println(
                "\nDirect push by author allowed: "
                        + service.mayPushDirectly(author));

        System.out.println(
                "Merge succeeded: "
                        + service.merge(126, MergeMethod.SQUASH));
    }
}

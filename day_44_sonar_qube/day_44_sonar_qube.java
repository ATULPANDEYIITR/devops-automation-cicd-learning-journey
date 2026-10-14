import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/*
 * Enterprise repository-quality governance model.
 *
 * Compile and run:
 *   javac QualityGovernance.java
 *   java QualityGovernance
 *
 * Java 17 or later; no third-party dependencies.
 */

public class QualityGovernance {

    enum IssueType {
        BUG, VULNERABILITY, CODE_SMELL, SECURITY_HOTSPOT
    }

    enum Severity {
        BLOCKER, CRITICAL, MAJOR, MINOR, INFO
    }

    enum ReviewState {
        COMMENTED, APPROVED, CHANGES_REQUESTED, DISMISSED
    }

    enum GateStatus {
        OK, ERROR, NO_ANALYSIS
    }

    enum PullRequestState {
        DRAFT, OPEN, CLOSED, MERGED
    }

    record Finding(
            String key,
            String component,
            String rule,
            IssueType type,
            Severity severity,
            String message,
            int remediationMinutes,
            int line,
            boolean newCode,
            boolean resolved,
            boolean hotspotReviewed) {

        Finding {
            requireText(key, "Finding key");
            requireText(component, "Component");
            requireText(rule, "Rule");
            requireText(message, "Message");
            Objects.requireNonNull(type, "Issue type");
            Objects.requireNonNull(severity, "Severity");
            if (remediationMinutes < 0 || line < 1) {
                throw new IllegalArgumentException("Invalid remediation effort or line.");
            }
        }
    }

    record SourceSnapshot(
            String projectKey,
            String branch,
            String commit,
            int totalLines,
            int coveredLines,
            int duplicatedLines,
            int newLines,
            int newCoveredLines,
            int newDuplicatedLines,
            List<Finding> findings,
            Instant analyzedAt) {

        SourceSnapshot {
            requireText(projectKey, "Project key");
            requireText(branch, "Branch");
            requireText(commit, "Commit");
            Objects.requireNonNull(analyzedAt, "Analysis timestamp");
            findings = List.copyOf(findings);

            if (totalLines < 0 || coveredLines < 0 || duplicatedLines < 0
                    || newLines < 0 || newCoveredLines < 0
                    || newDuplicatedLines < 0
                    || coveredLines > totalLines
                    || duplicatedLines > totalLines
                    || newCoveredLines > newLines
                    || newDuplicatedLines > newLines) {
                throw new IllegalArgumentException("Invalid source metric denominators.");
            }
        }

        double coveragePercent() {
            return percentage(coveredLines, totalLines);
        }

        double newCoveragePercent() {
            return percentage(newCoveredLines, newLines);
        }

        double duplicationPercent() {
            return percentage(duplicatedLines, totalLines);
        }

        double newDuplicationPercent() {
            return percentage(newDuplicatedLines, newLines);
        }

        private static double percentage(int numerator, int denominator) {
            return denominator == 0
                    ? 0.0
                    : Math.round(10000.0 * numerator / denominator) / 100.0;
        }

        List<Finding> activeFindings() {
            return findings.stream()
                    .filter(finding -> !finding.resolved())
                    .toList();
        }

        List<Finding> newFindings() {
            return activeFindings().stream()
                    .filter(Finding::newCode)
                    .toList();
        }
    }

    record QualityMetrics(
            double coverage,
            double newCoverage,
            double duplication,
            double newDuplication,
            int newBugs,
            int newVulnerabilities,
            int newBlockers,
            int newCriticalIssues,
            int newCodeSmells,
            int newDebtMinutes,
            int totalDebtMinutes,
            int unreviewedHotspots,
            int activeFindings) {

        static QualityMetrics from(SourceSnapshot snapshot) {
            List<Finding> active = snapshot.activeFindings();
            List<Finding> fresh = snapshot.newFindings();

            return new QualityMetrics(
                    snapshot.coveragePercent(),
                    snapshot.newCoveragePercent(),
                    snapshot.duplicationPercent(),
                    snapshot.newDuplicationPercent(),
                    count(fresh, IssueType.BUG),
                    count(fresh, IssueType.VULNERABILITY),
                    countSeverity(fresh, Severity.BLOCKER),
                    countSeverity(fresh, Severity.CRITICAL),
                    count(fresh, IssueType.CODE_SMELL),
                    debt(fresh),
                    debt(active),
                    (int) active.stream()
                            .filter(f -> f.type() == IssueType.SECURITY_HOTSPOT)
                            .filter(f -> !f.hotspotReviewed())
                            .count(),
                    active.size());
        }

        private static int count(List<Finding> findings, IssueType type) {
            return (int) findings.stream().filter(f -> f.type() == type).count();
        }

        private static int countSeverity(List<Finding> findings, Severity severity) {
            return (int) findings.stream().filter(f -> f.severity() == severity).count();
        }

        private static int debt(List<Finding> findings) {
            return findings.stream().mapToInt(Finding::remediationMinutes).sum();
        }
    }

    record GateCondition(
            String name,
            double threshold,
            Comparison comparison,
            MetricExtractor extractor) {

        GateCondition {
            requireText(name, "Condition name");
            Objects.requireNonNull(comparison);
            Objects.requireNonNull(extractor);
            if (!Double.isFinite(threshold)) {
                throw new IllegalArgumentException("Gate threshold must be finite.");
            }
        }

        GateFailure evaluate(QualityMetrics metrics) {
            double actual = extractor.extract(metrics);
            boolean passed = comparison.test(actual, threshold);
            return new GateFailure(name, actual, comparison.symbol(), threshold, passed);
        }
    }

    enum Comparison {
        AT_LEAST(">=") {
            boolean test(double a, double b) { return a >= b; }
        },
        AT_MOST("<=") {
            boolean test(double a, double b) { return a <= b; }
        },
        EQUALS("=") {
            boolean test(double a, double b) { return Double.compare(a, b) == 0; }
        };

        private final String symbol;

        Comparison(String symbol) {
            this.symbol = symbol;
        }

        abstract boolean test(double actual, double threshold);

        String symbol() {
            return symbol;
        }
    }

    @FunctionalInterface
    interface MetricExtractor {
        double extract(QualityMetrics metrics);
    }

    record GateFailure(
            String condition,
            double actual,
            String operator,
            double threshold,
            boolean passed) {
    }

    record GateResult(
            GateStatus status,
            QualityMetrics metrics,
            List<GateFailure> conditions) {

        GateResult {
            Objects.requireNonNull(status);
            conditions = List.copyOf(conditions);
        }

        List<GateFailure> failures() {
            return conditions.stream().filter(result -> !result.passed()).toList();
        }
    }

    static final class QualityGateService {
        private final List<GateCondition> conditions;

        QualityGateService(List<GateCondition> conditions) {
            this.conditions = List.copyOf(conditions);
        }

        GateResult evaluate(SourceSnapshot snapshot) {
            if (snapshot == null) {
                return new GateResult(GateStatus.NO_ANALYSIS, null, List.of());
            }

            QualityMetrics metrics = QualityMetrics.from(snapshot);
            List<GateFailure> results = conditions.stream()
                    .map(condition -> condition.evaluate(metrics))
                    .toList();

            GateStatus status = results.stream().allMatch(GateFailure::passed)
                    ? GateStatus.OK
                    : GateStatus.ERROR;

            return new GateResult(status, metrics, results);
        }
    }

    record Review(
            String reviewer,
            ReviewState state,
            String reviewedCommit,
            boolean eligible,
            boolean codeOwner) {

        Review {
            requireText(reviewer, "Reviewer");
            Objects.requireNonNull(state);
            requireText(reviewedCommit, "Reviewed commit");
        }
    }

    record StatusCheck(String name, boolean passed, String commit) {
        StatusCheck {
            requireText(name, "Check name");
            requireText(commit, "Check commit");
        }
    }

    record BranchPolicy(
            String protectedBranch,
            int requiredApprovals,
            boolean requireCodeOwner,
            boolean requireLinearHistory,
            boolean disallowDirectPush,
            boolean disallowForcePush,
            boolean disallowDeletion,
            boolean requireResolvedConversations,
            boolean allowAdministratorBypass,
            Set<String> requiredChecks) {

        BranchPolicy {
            requireText(protectedBranch, "Protected branch");
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException("Required approvals cannot be negative.");
            }
            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    static final class PullRequest {
        private final String id;
        private final String sourceBranch;
        private final String targetBranch;
        private final BranchPolicy policy;
        private final List<Review> reviews = new ArrayList<>();
        private final Map<String, StatusCheck> checks = new HashMap<>();
        private PullRequestState state;
        private String headCommit;
        private String analyzedCommit;
        private boolean conflicts;
        private boolean conversationsResolved;
        private boolean linearHistory;
        private GateResult gateResult;

        PullRequest(String id, String sourceBranch, String targetBranch,
                    String headCommit, BranchPolicy policy, boolean draft) {
            requireText(id, "Pull request ID");
            requireText(sourceBranch, "Source branch");
            requireText(targetBranch, "Target branch");
            requireText(headCommit, "Head commit");
            if (sourceBranch.equals(targetBranch)) {
                throw new IllegalArgumentException("Source and target must differ.");
            }

            this.id = id;
            this.sourceBranch = sourceBranch;
            this.targetBranch = targetBranch;
            this.headCommit = headCommit;
            this.policy = Objects.requireNonNull(policy);
            this.state = draft ? PullRequestState.DRAFT : PullRequestState.OPEN;
        }

        void markReadyForReview() {
            if (state != PullRequestState.DRAFT) {
                throw new IllegalStateException("Only a draft can become ready.");
            }
            state = PullRequestState.OPEN;
        }

        void updateHead(String commit) {
            requireText(commit, "Head commit");
            if (state != PullRequestState.OPEN && state != PullRequestState.DRAFT) {
                throw new IllegalStateException("A closed or merged request cannot be updated.");
            }
            headCommit = commit;
            gateResult = null;
            analyzedCommit = null;
        }

        void addReview(Review review) {
            if (state != PullRequestState.OPEN) {
                throw new IllegalStateException("Reviews can be recorded only on open requests.");
            }
            reviews.add(Objects.requireNonNull(review));
        }

        void publishCheck(StatusCheck check) {
            checks.put(check.name(), check);
        }

        void setMergeContext(boolean conflicts, boolean conversationsResolved,
                             boolean linearHistory) {
            this.conflicts = conflicts;
            this.conversationsResolved = conversationsResolved;
            this.linearHistory = linearHistory;
        }

        void attachAnalysis(String analyzedCommit, GateResult gateResult) {
            if (state != PullRequestState.OPEN) {
                throw new IllegalStateException("Analysis is attached to an open request.");
            }
            this.analyzedCommit = Objects.requireNonNull(analyzedCommit);
            this.gateResult = Objects.requireNonNull(gateResult);
        }

        List<String> mergeBlockers() {
            List<String> blockers = new ArrayList<>();

            if (state != PullRequestState.OPEN) {
                blockers.add("Pull request must be open and ready.");
            }
            if (!targetBranch.equals(policy.protectedBranch())) {
                blockers.add("Policy does not match the target branch.");
            }
            if (conflicts) {
                blockers.add("Merge conflicts remain.");
            }
            if (gateResult == null || gateResult.status() != GateStatus.OK) {
                blockers.add("A successful quality-gate result is required.");
            }
            if (!headCommit.equals(analyzedCommit)) {
                blockers.add("Analysis is missing or stale for the current head commit.");
            }
            if (policy.requireResolvedConversations() && !conversationsResolved) {
                blockers.add("Review conversations remain unresolved.");
            }
            if (policy.requireLinearHistory() && !linearHistory) {
                blockers.add("The resulting history must be linear.");
            }

            long validApprovals = reviews.stream()
                    .filter(Review::eligible)
                    .filter(review -> review.state() == ReviewState.APPROVED)
                    .filter(review -> review.reviewedCommit().equals(headCommit))
                    .count();

            if (validApprovals < policy.requiredApprovals()) {
                blockers.add("Required non-stale approvals are missing.");
            }

            if (policy.requireCodeOwner() && reviews.stream()
                    .noneMatch(review -> review.eligible()
                            && review.codeOwner()
                            && review.state() == ReviewState.APPROVED
                            && review.reviewedCommit().equals(headCommit))) {
                blockers.add("A current code-owner approval is missing.");
            }

            for (String required : policy.requiredChecks()) {
                StatusCheck check = checks.get(required);
                if (check == null || !check.passed()
                        || !check.commit().equals(headCommit)) {
                    blockers.add("Required check is missing, failing, or stale: " + required);
                }
            }
            return Collections.unmodifiableList(blockers);
        }

        void merge() {
            List<String> blockers = mergeBlockers();
            if (!blockers.isEmpty()) {
                throw new IllegalStateException(
                        "Merge denied: " + String.join("; ", blockers));
            }
            state = PullRequestState.MERGED;
        }

        String id() { return id; }
        String headCommit() { return headCommit; }
        PullRequestState state() { return state; }
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank.");
        }
    }

    private static QualityGateService productionGate() {
        return new QualityGateService(List.of(
                new GateCondition(
                        "New-code coverage", 80,
                        Comparison.AT_LEAST, QualityMetrics::newCoverage),
                new GateCondition(
                        "New-code duplication", 3,
                        Comparison.AT_MOST, QualityMetrics::newDuplication),
                new GateCondition(
                        "New bugs", 0,
                        Comparison.EQUALS, QualityMetrics::newBugs),
                new GateCondition(
                        "New vulnerabilities", 0,
                        Comparison.EQUALS, QualityMetrics::newVulnerabilities),
                new GateCondition(
                        "New blockers", 0,
                        Comparison.EQUALS, QualityMetrics::newBlockers),
                new GateCondition(
                        "New technical debt minutes", 60,
                        Comparison.AT_MOST, QualityMetrics::newDebtMinutes),
                new GateCondition(
                        "Unreviewed security hotspots", 0,
                        Comparison.EQUALS, QualityMetrics::unreviewedHotspots)
        ));
    }

    private static SourceSnapshot createSnapshot(
            String commit, String branch, List<Finding> findings) {
        return new SourceSnapshot(
                "payments-platform",
                branch,
                commit,
                3200, 2800, 64,
                100, 91, 2,
                findings,
                Instant.now());
    }

    private static List<Finding> cleanNewCodeFindings() {
        return List.of(
                new Finding(
                        "PAY-OLD-1", "src/legacy/adapter.java", "java:S1481",
                        IssueType.CODE_SMELL, Severity.MINOR,
                        "Existing unused local variable.", 15, 22,
                        false, false, true),
                new Finding(
                        "PAY-HOT-1", "src/security/crypto.java", "java:S4787",
                        IssueType.SECURITY_HOTSPOT, Severity.MAJOR,
                        "Cryptographic usage has been reviewed by the security owner.",
                        30, 81, false, false, true)
        );
    }

    public static void main(String[] args) {
        QualityGateService gateService = productionGate();
        String branch = "feature/parameterized-payment-query";
        String commit = "d91e7b4";

        SourceSnapshot snapshot = createSnapshot(commit, branch, cleanNewCodeFindings());
        GateResult gateResult = gateService.evaluate(snapshot);

        System.out.println("Project: " + snapshot.projectKey());
        System.out.println("Commit: " + snapshot.commit());
        System.out.println("Overall coverage: " + snapshot.coveragePercent() + "%");
        System.out.println("New-code coverage: " + snapshot.newCoveragePercent() + "%");
        System.out.println("New-code duplication: " + snapshot.newDuplicationPercent() + "%");
        System.out.println("Gate status: " + gateResult.status());

        gateResult.conditions().forEach(condition ->
                System.out.printf(
                        "  %s: %.2f %s %.2f -> %s%n",
                        condition.condition(),
                        condition.actual(),
                        condition.operator(),
                        condition.threshold(),
                        condition.passed() ? "PASS" : "FAIL"));

        BranchPolicy policy = new BranchPolicy(
                "main",
                2,
                true,
                true,
                true,
                true,
                true,
                true,
                false,
                Set.of("build-linux", "unit-tests", "dependency-audit"));

        PullRequest request = new PullRequest(
                "PR-315", branch, "main", commit, policy, false);

        request.addReview(new Review(
                "reviewer-lee", ReviewState.APPROVED, commit, true, false));
        request.addReview(new Review(
                "code-owner", ReviewState.APPROVED, commit, true, true));

        request.publishCheck(new StatusCheck("build-linux", true, commit));
        request.publishCheck(new StatusCheck("unit-tests", true, commit));
        request.publishCheck(new StatusCheck("dependency-audit", true, commit));
        request.setMergeContext(false, true, true);
        request.attachAnalysis(snapshot.commit(), gateResult);

        List<String> blockers = request.mergeBlockers();
        if (blockers.isEmpty()) {
            request.merge();
            System.out.println("Pull request " + request.id() + " merged.");
        } else {
            System.out.println("Merge blocked:");
            blockers.forEach(reason -> System.out.println("  " + reason));
        }

        // Changing the head invalidates the earlier gate result and makes approvals stale.
        request.updateHead("new-head-commit");
        System.out.println("\nAfter source changes:");
        request.mergeBlockers().forEach(reason -> System.out.println("  " + reason));

        // Invalid lifecycle transitions fail explicitly instead of silently mutating state.
        PullRequest draft = new PullRequest(
                "PR-316", "feature/draft", "main", "draft-commit", policy, true);
        try {
            draft.merge();
        } catch (IllegalStateException expected) {
            System.out.println("\nDraft merge rejected: " + expected.getMessage());
        }

        try {
            new SourceSnapshot(
                    "invalid", "feature/bad", "bad",
                    10, 11, 0, 2, 1, 0,
                    List.of(), Instant.now());
            throw new AssertionError("Invalid metrics were accepted.");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid source metrics rejected.");
        }
    }
}

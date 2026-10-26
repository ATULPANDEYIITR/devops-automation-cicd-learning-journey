import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RepositoryGovernanceApp {

    enum PullRequestState {
        DRAFT, OPEN, CLOSED, MERGED
    }

    enum ReviewState {
        COMMENTED, APPROVED, CHANGES_REQUESTED, DISMISSED
    }

    enum CheckState {
        PENDING, PASSED, FAILED
    }

    enum Severity {
        LOW, MEDIUM, HIGH, CRITICAL
    }

    interface SecurityPolicy {
        List<String> evaluate(ContainerImage image);
    }

    record User(String username, Set<String> teams) {
        User {
            Objects.requireNonNull(username);
            teams = Set.copyOf(teams);
        }
    }

    record Review(
        String reviewer,
        ReviewState state,
        String commitSha
    ) {}

    record StatusCheck(
        String name,
        CheckState state
    ) {}

    record Vulnerability(
        String packageName,
        Severity severity,
        String fixedVersion
    ) {}

    static final class ContainerImage {
        private final String name;
        private final String user;
        private final List<String> secrets;
        private final List<Vulnerability> vulnerabilities;

        ContainerImage(
            String name,
            String user,
            List<String> secrets,
            List<Vulnerability> vulnerabilities
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "image name is required"
                );
            }

            if (user == null) {
                throw new IllegalArgumentException(
                    "container user must be explicit"
                );
            }

            this.name = name;
            this.user = user;
            this.secrets = List.copyOf(secrets);
            this.vulnerabilities = List.copyOf(vulnerabilities);
        }

        String name() {
            return name;
        }

        List<String> securityFindings() {
            List<String> findings = new ArrayList<>();

            if (user.isBlank() || user.equals("root") || user.equals("0")) {
                findings.add("container runs as root");
            }

            if (!secrets.isEmpty()) {
                findings.add(
                    "secrets detected: " + String.join(", ", secrets)
                );
            }

            for (Vulnerability vulnerability : vulnerabilities) {
                if (vulnerability.severity() == Severity.CRITICAL) {
                    findings.add(
                        "critical vulnerability in " +
                        vulnerability.packageName()
                    );
                } else if (vulnerability.severity() == Severity.HIGH) {
                    findings.add(
                        "high vulnerability in " +
                        vulnerability.packageName()
                    );
                }
            }

            return findings;
        }
    }

    static final class NonRootAndVulnerabilityPolicy
        implements SecurityPolicy {

        @Override
        public List<String> evaluate(ContainerImage image) {
            return image.securityFindings();
        }
    }

    record BranchProtectionPolicy(
        int requiredApprovals,
        Set<String> requiredChecks,
        boolean requireResolvedConversations,
        boolean restrictDirectPush,
        boolean restrictForcePush,
        boolean restrictDeletion,
        boolean requireLinearHistory,
        boolean allowAdminBypass
    ) {
        BranchProtectionPolicy {
            if (requiredApprovals < 1) {
                throw new IllegalArgumentException(
                    "at least one approval is required"
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    static final class PullRequest {
        private final int number;
        private final String author;
        private final String targetBranch;
        private final String headSha;

        private PullRequestState state = PullRequestState.OPEN;
        private boolean draft;
        private boolean mergeConflict;
        private boolean baseSynced = true;
        private boolean approvalsStale;
        private int openConversations;

        private final List<Review> reviews = new ArrayList<>();
        private final Map<String, StatusCheck> checks = new HashMap<>();

        PullRequest(
            int number,
            String author,
            String targetBranch,
            String headSha
        ) {
            if (number <= 0) {
                throw new IllegalArgumentException(
                    "pull request number must be positive"
                );
            }

            this.number = number;
            this.author = Objects.requireNonNull(author);
            this.targetBranch = Objects.requireNonNull(targetBranch);
            this.headSha = Objects.requireNonNull(headSha);
        }

        int number() {
            return number;
        }

        String author() {
            return author;
        }

        String targetBranch() {
            return targetBranch;
        }

        String headSha() {
            return headSha;
        }

        PullRequestState state() {
            return state;
        }

        void setDraft(boolean draft) {
            this.draft = draft;
        }

        boolean isDraft() {
            return draft;
        }

        void setMergeConflict(boolean mergeConflict) {
            this.mergeConflict = mergeConflict;
        }

        boolean hasMergeConflict() {
            return mergeConflict;
        }

        void setBaseSynced(boolean baseSynced) {
            this.baseSynced = baseSynced;
        }

        boolean isBaseSynced() {
            return baseSynced;
        }

        void setApprovalsStale(boolean approvalsStale) {
            this.approvalsStale = approvalsStale;
        }

        boolean areApprovalsStale() {
            return approvalsStale;
        }

        void setOpenConversations(int count) {
            if (count < 0) {
                throw new IllegalArgumentException(
                    "conversation count cannot be negative"
                );
            }
            openConversations = count;
        }

        int openConversations() {
            return openConversations;
        }

        void addReview(Review review) {
            reviews.add(Objects.requireNonNull(review));
        }

        void addCheck(StatusCheck check) {
            checks.put(check.name(), check);
        }

        List<Review> reviews() {
            return Collections.unmodifiableList(reviews);
        }

        Map<String, StatusCheck> checks() {
            return Collections.unmodifiableMap(checks);
        }
    }

    record MergeDecision(
        boolean eligible,
        List<String> reasons
    ) {
        MergeDecision {
            reasons = List.copyOf(reasons);
        }
    }

    static final class MergeEligibilityService {
        private final Map<String, User> users;
        private final Map<String, BranchProtectionPolicy> policies;
        private final SecurityPolicy securityPolicy;

        MergeEligibilityService(
            Map<String, User> users,
            Map<String, BranchProtectionPolicy> policies,
            SecurityPolicy securityPolicy
        ) {
            this.users = Map.copyOf(users);
            this.policies = Map.copyOf(policies);
            this.securityPolicy = Objects.requireNonNull(securityPolicy);
        }

        MergeDecision evaluate(
            PullRequest pr,
            ContainerImage image
        ) {
            List<String> reasons = new ArrayList<>();

            BranchProtectionPolicy policy =
                policies.get(pr.targetBranch());

            if (policy == null) {
                reasons.add(
                    "target branch has no protection policy"
                );
                return new MergeDecision(false, reasons);
            }

            if (pr.state() != PullRequestState.OPEN) {
                reasons.add("pull request is not open");
            }

            if (pr.isDraft()) {
                reasons.add("pull request is a draft");
            }

            if (pr.hasMergeConflict()) {
                reasons.add("merge conflict must be resolved");
            }

            if (!pr.isBaseSynced()) {
                reasons.add(
                    "source branch is not synchronized with base"
                );
            }

            if (
                policy.requireResolvedConversations() &&
                pr.openConversations() > 0
            ) {
                reasons.add(
                    pr.openConversations() +
                    " review conversations remain unresolved"
                );
            }

            if (pr.areApprovalsStale()) {
                reasons.add("approvals are stale");
            }

            long approvals = pr.reviews()
                .stream()
                .filter(review ->
                    review.state() == ReviewState.APPROVED
                )
                .filter(review ->
                    !review.reviewer().equals(pr.author())
                )
                .filter(review ->
                    users.containsKey(review.reviewer())
                )
                .filter(review ->
                    review.commitSha().equals(pr.headSha())
                )
                .map(Review::reviewer)
                .distinct()
                .count();

            if (approvals < policy.requiredApprovals()) {
                reasons.add(
                    "requires " + policy.requiredApprovals() +
                    " eligible approvals; found " + approvals
                );
            }

            for (String requiredCheck : policy.requiredChecks()) {
                StatusCheck check = pr.checks().get(requiredCheck);

                if (check == null) {
                    reasons.add(
                        "missing required check: " + requiredCheck
                    );
                } else if (check.state() != CheckState.PASSED) {
                    reasons.add(
                        "required check failed: " + requiredCheck
                    );
                }
            }

            reasons.addAll(
                securityPolicy.evaluate(image)
                    .stream()
                    .map(finding ->
                        "container security: " + finding
                    )
                    .toList()
            );

            return new MergeDecision(reasons.isEmpty(), reasons);
        }
    }

    static void printDecision(
        String title,
        MergeDecision decision
    ) {
        System.out.println("\n=== " + title + " ===");
        System.out.println(
            "merge eligible: " + decision.eligible()
        );

        if (decision.reasons().isEmpty()) {
            System.out.println(
                "  - all governance and container-security controls passed"
            );
        } else {
            decision.reasons()
                .forEach(reason ->
                    System.out.println("  - " + reason)
                );
        }
    }

    public static void main(String[] args) {
        Map<String, User> users = new HashMap<>();

        users.put(
            "alice",
            new User("alice", Set.of("developers"))
        );

        users.put(
            "bob",
            new User("bob", Set.of("security-reviewers"))
        );

        users.put(
            "carol",
            new User("carol", Set.of("platform-reviewers"))
        );

        BranchProtectionPolicy mainPolicy =
            new BranchProtectionPolicy(
                2,
                Set.of(
                    "container-build",
                    "container-vulnerability-scan",
                    "container-secret-scan"
                ),
                true,
                true,
                true,
                true,
                true,
                false
            );

        Map<String, BranchProtectionPolicy> policies =
            Map.of("main", mainPolicy);

        PullRequest pr = new PullRequest(
            105,
            "alice",
            "main",
            "e71a92c1"
        );

        pr.addCheck(
            new StatusCheck(
                "container-build",
                CheckState.PASSED
            )
        );

        pr.addCheck(
            new StatusCheck(
                "container-vulnerability-scan",
                CheckState.PASSED
            )
        );

        pr.addCheck(
            new StatusCheck(
                "container-secret-scan",
                CheckState.PASSED
            )
        );

        pr.addReview(
            new Review(
                "bob",
                ReviewState.APPROVED,
                "e71a92c1"
            )
        );

        pr.addReview(
            new Review(
                "carol",
                ReviewState.APPROVED,
                "e71a92c1"
            )
        );

        SecurityPolicy securityPolicy =
            new NonRootAndVulnerabilityPolicy();

        MergeEligibilityService service =
            new MergeEligibilityService(
                users,
                policies,
                securityPolicy
            );

        ContainerImage secureImage =
            new ContainerImage(
                "payments:105",
                "10001",
                List.of(),
                List.of(
                    new Vulnerability(
                        "openssl",
                        Severity.MEDIUM,
                        "3.2.1"
                    )
                )
            );

        MergeDecision secureDecision =
            service.evaluate(pr, secureImage);

        printDecision("secure container", secureDecision);

        ContainerImage insecureImage =
            new ContainerImage(
                "payments:105",
                "root",
                List.of("DATABASE_PASSWORD"),
                List.of(
                    new Vulnerability(
                        "openssl",
                        Severity.CRITICAL,
                        "3.2.1"
                    ),
                    new Vulnerability(
                        "curl",
                        Severity.HIGH,
                        "8.10.0"
                    )
                )
            );

        MergeDecision insecureDecision =
            service.evaluate(pr, insecureImage);

        printDecision("insecure container", insecureDecision);

        if (!secureDecision.eligible()) {
            throw new IllegalStateException(
                "secure container should be eligible"
            );
        }

        if (insecureDecision.eligible()) {
            throw new IllegalStateException(
                "insecure container must not be eligible"
            );
        }

        System.out.println(
            "\nEnterprise policy chain: Pull Request -> Code Review -> " +
            "Approval -> Security Checks -> Branch Protection -> Merge."
        );
    }
}

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
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
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Enterprise Release Management and Governance System
 *
 * Java 17
 *
 * Domain modeling:
 * - Semantic versioning
 * - Release lifecycle
 * - Approval requirements
 * - Reviewer authorization
 * - Automated quality gates
 * - Deployment authorization
 * - Production version tracking
 * - Rollback management
 * - Structured audit events
 */

public class ReleaseManagement {

    enum ReleaseState {
        DRAFT,
        CANDIDATE,
        APPROVED,
        RELEASED,
        REJECTED,
        ROLLED_BACK
    }

    enum ApprovalDecision {
        APPROVED,
        REJECTED
    }

    enum CheckStatus {
        PASSED,
        FAILED,
        PENDING
    }

    enum Environment {
        STAGING,
        PRODUCTION
    }

    static class ReleaseException extends RuntimeException {
        ReleaseException(String message) {
            super(message);
        }
    }

    static class ValidationException extends ReleaseException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class GovernanceException extends ReleaseException {
        GovernanceException(String message) {
            super(message);
        }
    }

    static class Version implements Comparable<Version> {

        private static final Pattern PATTERN = Pattern.compile(
            "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)"
            + "(?:-([0-9A-Za-z.-]+))?$"
        );

        private final int major;
        private final int minor;
        private final int patch;
        private final String prerelease;

        private Version(
            int major,
            int minor,
            int patch,
            String prerelease
        ) {
            if (major < 0 || minor < 0 || patch < 0) {
                throw new ValidationException("Negative version component.");
            }

            this.major = major;
            this.minor = minor;
            this.patch = patch;
            this.prerelease = prerelease;
        }

        static Version parse(String text) {
            Matcher matcher = PATTERN.matcher(text);

            if (!matcher.matches()) {
                throw new ValidationException(
                    "Invalid semantic version: " + text
                );
            }

            try {
                return new Version(
                    Integer.parseInt(matcher.group(1)),
                    Integer.parseInt(matcher.group(2)),
                    Integer.parseInt(matcher.group(3)),
                    matcher.group(4)
                );
            } catch (NumberFormatException exception) {
                throw new ValidationException("Version component too large.");
            }
        }

        boolean isPrerelease() {
            return prerelease != null;
        }

        @Override
        public int compareTo(Version other) {
            int comparison = Integer.compare(major, other.major);

            if (comparison != 0) return comparison;

            comparison = Integer.compare(minor, other.minor);

            if (comparison != 0) return comparison;

            comparison = Integer.compare(patch, other.patch);

            if (comparison != 0) return comparison;

            if (prerelease == null && other.prerelease == null) return 0;
            if (prerelease == null) return 1;
            if (other.prerelease == null) return -1;

            return prerelease.compareTo(other.prerelease);
        }

        @Override
        public String toString() {
            String base = major + "." + minor + "." + patch;
            return prerelease == null ? base : base + "-" + prerelease;
        }

        @Override
        public boolean equals(Object object) {
            if (!(object instanceof Version other)) return false;

            return major == other.major
                && minor == other.minor
                && patch == other.patch
                && Objects.equals(prerelease, other.prerelease);
        }

        @Override
        public int hashCode() {
            return Objects.hash(major, minor, patch, prerelease);
        }
    }

    record Approval(
        String reviewer,
        String role,
        ApprovalDecision decision,
        String comment,
        Instant timestamp
    ) {}

    record QualityCheck(
        String name,
        CheckStatus status,
        String details,
        Instant timestamp
    ) {}

    record AuditEvent(
        long sequence,
        Instant timestamp,
        String actor,
        String action,
        String details
    ) {}

    record EligibilityResult(
        boolean eligible,
        List<String> blockers,
        int approvedCount,
        int requiredCount
    ) {
        EligibilityResult {
            blockers = List.copyOf(blockers);
        }
    }

    record ReleasePolicy(
        int requiredApprovals,
        Set<String> eligibleRoles,
        Set<String> requiredChecks,
        boolean requireReleaseNotes,
        boolean allowPrereleaseProduction
    ) {
        ReleasePolicy {
            if (requiredApprovals < 1) {
                throw new ValidationException(
                    "Approval threshold must be positive."
                );
            }

            eligibleRoles = Set.copyOf(eligibleRoles);
            requiredChecks = Set.copyOf(requiredChecks);

            if (eligibleRoles.isEmpty() || requiredChecks.isEmpty()) {
                throw new ValidationException(
                    "Roles and quality checks cannot be empty."
                );
            }
        }

        static ReleasePolicy standard() {
            return new ReleasePolicy(
                2,
                Set.of(
                    "security_lead",
                    "engineering_lead",
                    "qa_lead",
                    "product_owner"
                ),
                Set.of(
                    "unit_tests",
                    "integration_tests",
                    "security_scan",
                    "dependency_audit"
                ),
                true,
                false
            );
        }
    }

    static class Release {

        private final String id;
        private final String product;
        private final Version version;
        private final String sourceCommit;
        private final String artifactDigest;
        private final String releaseNotes;
        private final Environment environment;

        private ReleaseState state = ReleaseState.DRAFT;

        private final Map<String, Approval> approvals =
            new TreeMap<>();

        private final Map<String, QualityCheck> checks =
            new TreeMap<>();

        private final List<AuditEvent> audit =
            new ArrayList<>();

        private String rollbackVersion;

        Release(
            String id,
            String product,
            Version version,
            String sourceCommit,
            String artifactDigest,
            String releaseNotes,
            Environment environment
        ) {
            this.id = id;
            this.product = product;
            this.version = version;
            this.sourceCommit = sourceCommit;
            this.artifactDigest = artifactDigest;
            this.releaseNotes = releaseNotes;
            this.environment = environment;
        }

        private void log(String actor, String action, String details) {
            audit.add(new AuditEvent(
                audit.size() + 1L,
                Instant.now(),
                actor,
                action,
                details
            ));
        }

        String getId() {
            return id;
        }

        String getProduct() {
            return product;
        }

        Version getVersion() {
            return version;
        }

        ReleaseState getState() {
            return state;
        }
    }

    interface ReleaseValidator {
        void validate(Release release);
    }

    static class ArtifactValidator implements ReleaseValidator {

        @Override
        public void validate(Release release) {
            if (release.artifactDigest == null ||
                !release.artifactDigest.matches("[a-fA-F0-9]{64}")) {
                throw new ValidationException(
                    "Artifact digest must be SHA-256."
                );
            }

            if (release.sourceCommit == null ||
                !release.sourceCommit.matches("[a-fA-F0-9]{7,64}")) {
                throw new ValidationException("Invalid source commit.");
            }
        }
    }

    static class ReleaseService {

        private final ReleasePolicy policy;
        private final ReleaseValidator artifactValidator =
            new ArtifactValidator();

        private final Map<String, Release> releases =
            new HashMap<>();

        private final Map<String, Set<Version>> published =
            new HashMap<>();

        private final Map<String, Version> production =
            new HashMap<>();

        ReleaseService(ReleasePolicy policy) {
            this.policy = policy;
        }

        Release create(
            String id,
            String product,
            String versionText,
            String commit,
            byte[] artifact,
            String notes,
            Environment environment
        ) {
            if (id == null ||
                !id.matches("[A-Za-z0-9][A-Za-z0-9_-]{2,63}")) {
                throw new ValidationException("Invalid release ID.");
            }

            if (product == null || product.isBlank()) {
                throw new ValidationException("Product is required.");
            }

            if (releases.containsKey(id)) {
                throw new GovernanceException("Duplicate release ID.");
            }

            if (artifact == null || artifact.length == 0) {
                throw new ValidationException("Artifact is empty.");
            }

            Version version = Version.parse(versionText);

            Release release = new Release(
                id,
                product,
                version,
                commit,
                sha256(artifact),
                notes == null ? "" : notes,
                environment
            );

            artifactValidator.validate(release);

            if (policy.requireReleaseNotes() && notes.isBlank()) {
                throw new ValidationException("Release notes are required.");
            }

            release.log(
                "release_service",
                "CREATED",
                version.toString()
            );

            releases.put(id, release);
            return release;
        }

        Release get(String id) {
            Release release = releases.get(id);

            if (release == null) {
                throw new ValidationException("Unknown release: " + id);
            }

            return release;
        }

        void submitCandidate(String id) {
            Release release = get(id);

            if (release.state != ReleaseState.DRAFT) {
                throw new GovernanceException("Release is not a draft.");
            }

            Set<Version> versions = published.getOrDefault(
                release.product,
                Collections.emptySet()
            );

            if (versions.contains(release.version)) {
                throw new GovernanceException("Version already published.");
            }

            Version current = production.get(release.product);

            if (
                release.environment == Environment.PRODUCTION &&
                current != null &&
                release.version.compareTo(current) <= 0
            ) {
                throw new GovernanceException(
                    "Production version must advance."
                );
            }

            release.state = ReleaseState.CANDIDATE;
            release.log("release_manager", "CANDIDATE_SUBMITTED", "");
        }

        void recordCheck(
            String id,
            String name,
            CheckStatus status,
            String details
        ) {
            Release release = get(id);

            if (release.state != ReleaseState.CANDIDATE) {
                throw new GovernanceException(
                    "Checks require candidate state."
                );
            }

            if (!policy.requiredChecks().contains(name)) {
                throw new GovernanceException("Unrecognized quality check.");
            }

            release.checks.put(
                name,
                new QualityCheck(
                    name,
                    status,
                    details,
                    Instant.now()
                )
            );

            release.log(
                "ci_pipeline",
                "CHECK_RECORDED",
                name + "=" + status
            );
        }

        void recordApproval(
            String id,
            String reviewer,
            String role,
            ApprovalDecision decision,
            String comment
        ) {
            Release release = get(id);

            if (release.state != ReleaseState.CANDIDATE) {
                throw new GovernanceException(
                    "Approvals require candidate state."
                );
            }

            if (reviewer == null || reviewer.isBlank()) {
                throw new ValidationException("Reviewer is required.");
            }

            if (!policy.eligibleRoles().contains(role)) {
                throw new GovernanceException(
                    "Reviewer is not eligible."
                );
            }

            if (release.approvals.containsKey(reviewer)) {
                throw new GovernanceException(
                    "Reviewer has already submitted a decision."
                );
            }

            Approval approval = new Approval(
                reviewer,
                role,
                decision,
                comment == null ? "" : comment,
                Instant.now()
            );

            release.approvals.put(reviewer, approval);

            release.log(
                reviewer,
                "APPROVAL_RECORDED",
                decision.toString()
            );
        }

        EligibilityResult evaluate(String id) {
            Release release = get(id);
            List<String> blockers = new ArrayList<>();

            if (release.state != ReleaseState.CANDIDATE) {
                blockers.add("Release must be a candidate.");
            }

            if (
                policy.requireReleaseNotes() &&
                release.releaseNotes.isBlank()
            ) {
                blockers.add("Release notes missing.");
            }

            long rejected = release.approvals.values()
                .stream()
                .filter(a -> a.decision() == ApprovalDecision.REJECTED)
                .count();

            if (rejected > 0) {
                blockers.add("One or more reviewers rejected the release.");
            }

            int approved = (int) release.approvals.values()
                .stream()
                .filter(a -> a.decision() == ApprovalDecision.APPROVED)
                .count();

            if (approved < policy.requiredApprovals()) {
                blockers.add("Approval threshold not satisfied.");
            }

            for (String required : policy.requiredChecks()) {
                QualityCheck check = release.checks.get(required);

                if (check == null) {
                    blockers.add("Missing check: " + required);
                } else if (check.status() != CheckStatus.PASSED) {
                    blockers.add("Unsuccessful check: " + required);
                }
            }

            if (
                release.environment == Environment.PRODUCTION &&
                release.version.isPrerelease() &&
                !policy.allowPrereleaseProduction()
            ) {
                blockers.add("Prerelease production deployment is prohibited.");
            }

            return new EligibilityResult(
                blockers.isEmpty(),
                blockers,
                approved,
                policy.requiredApprovals()
            );
        }

        void approveForDeployment(String id) {
            Release release = get(id);
            EligibilityResult result = evaluate(id);

            if (!result.eligible()) {
                throw new GovernanceException(
                    String.join("; ", result.blockers())
                );
            }

            release.state = ReleaseState.APPROVED;
            release.log(
                "governance_service",
                "GOVERNANCE_APPROVED",
                ""
            );
        }

        void deploy(String id, String actor) {
            Release release = get(id);

            if (release.state != ReleaseState.APPROVED) {
                throw new GovernanceException(
                    "Release is not approved."
                );
            }

            if (release.environment != Environment.PRODUCTION) {
                throw new GovernanceException(
                    "Production target required."
                );
            }

            Version current = production.get(release.product);

            if (
                current != null &&
                release.version.compareTo(current) <= 0
            ) {
                throw new GovernanceException(
                    "Production version regression."
                );
            }

            published.computeIfAbsent(
                release.product,
                key -> new HashSet<>()
            ).add(release.version);

            production.put(release.product, release.version);

            release.state = ReleaseState.RELEASED;
            release.log(actor, "DEPLOYED", release.version.toString());
        }

        void rollback(
            String id,
            String previousVersion,
            String actor
        ) {
            Release release = get(id);

            if (release.state != ReleaseState.RELEASED) {
                throw new GovernanceException(
                    "Only released versions can be rolled back."
                );
            }

            Version target = Version.parse(previousVersion);

            if (
                !published.getOrDefault(
                    release.product,
                    Collections.emptySet()
                ).contains(target)
            ) {
                throw new GovernanceException(
                    "Rollback target was not published."
                );
            }

            if (target.equals(release.version)) {
                throw new GovernanceException(
                    "Cannot roll back to the same version."
                );
            }

            release.rollbackVersion = target.toString();
            release.state = ReleaseState.ROLLED_BACK;
            production.put(release.product, target);

            release.log(actor, "ROLLBACK", target.toString());
        }

        void reject(String id, String actor, String reason) {
            Release release = get(id);

            if (
                release.state != ReleaseState.DRAFT &&
                release.state != ReleaseState.CANDIDATE
            ) {
                throw new GovernanceException(
                    "Invalid rejection transition."
                );
            }

            if (reason == null || reason.isBlank()) {
                throw new ValidationException(
                    "Rejection reason is required."
                );
            }

            release.state = ReleaseState.REJECTED;
            release.log(actor, "REJECTED", reason);
        }

        void printReport(String id) {
            Release release = get(id);

            System.out.println("\nRELEASE GOVERNANCE REPORT");
            System.out.println("-------------------------");
            System.out.println("Release: " + release.id);
            System.out.println("Product: " + release.product);
            System.out.println("Version: " + release.version);
            System.out.println("State: " + release.state);
            System.out.println("Commit: " + release.sourceCommit);
            System.out.println("Artifact digest: " + release.artifactDigest);

            System.out.println("\nApprovals:");

            release.approvals.values().forEach(System.out::println);

            System.out.println("\nQuality checks:");

            release.checks.values().forEach(System.out::println);

            System.out.println("\nAudit events:");

            release.audit.forEach(System.out::println);
        }

        void exportAudit(Path path) throws Exception {
            StringBuilder output = new StringBuilder();

            output.append("release_id,product,version,state,events\n");

            for (Release release : releases.values()) {
                String events = release.audit.stream()
                    .map(e -> e.action() + ":" + e.actor())
                    .collect(Collectors.joining("|"));

                output.append(csv(release.id)).append(',')
                    .append(csv(release.product)).append(',')
                    .append(csv(release.version.toString())).append(',')
                    .append(csv(release.state.toString())).append(',')
                    .append(csv(events)).append('\n');
            }

            Files.writeString(
                path,
                output.toString(),
                StandardCharsets.UTF_8
            );
        }

        private static String csv(String value) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }

        private static String sha256(byte[] content) {
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] bytes = digest.digest(content);

                StringBuilder result = new StringBuilder();

                for (byte value : bytes) {
                    result.append(String.format("%02x", value & 0xff));
                }

                return result.toString();

            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException(
                    "SHA-256 unavailable.",
                    exception
                );
            }
        }
    }

    public static void main(String[] args) {
        try {
            ReleasePolicy policy = ReleasePolicy.standard();
            ReleaseService service = new ReleaseService(policy);

            Release release = service.create(
                "REL-2026-001",
                "EnterpriseBanking",
                "5.3.0",
                "a".repeat(40),
                "enterprise-production-artifact".getBytes(
                    StandardCharsets.UTF_8
                ),
                "Improved transaction processing and security.",
                Environment.PRODUCTION
            );

            service.submitCandidate(release.getId());

            for (String check : policy.requiredChecks()) {
                service.recordCheck(
                    release.getId(),
                    check,
                    CheckStatus.PASSED,
                    "Automated validation completed."
                );
            }

            service.recordApproval(
                release.getId(),
                "security_reviewer",
                "security_lead",
                ApprovalDecision.APPROVED,
                "Security controls verified."
            );

            service.recordApproval(
                release.getId(),
                "engineering_reviewer",
                "engineering_lead",
                ApprovalDecision.APPROVED,
                "Release artifact verified."
            );

            EligibilityResult evaluation =
                service.evaluate(release.getId());

            System.out.println("Eligible: " + evaluation.eligible());
            System.out.println("Approvals: " +
                evaluation.approvedCount() + "/" +
                evaluation.requiredCount());

            if (evaluation.eligible()) {
                service.approveForDeployment(release.getId());
                service.deploy(
                    release.getId(),
                    "production_deployment_service"
                );
            }

            service.printReport(release.getId());

            Release incomplete = service.create(
                "REL-2026-002",
                "EnterpriseBanking",
                "5.4.0",
                "b".repeat(40),
                "next-artifact".getBytes(StandardCharsets.UTF_8),
                "New account management functionality.",
                Environment.PRODUCTION
            );

            service.submitCandidate(incomplete.getId());

            EligibilityResult blocked =
                service.evaluate(incomplete.getId());

            System.out.println("\nSecond release eligible: " +
                blocked.eligible());

            blocked.blockers().forEach(
                reason -> System.out.println("BLOCKED: " + reason)
            );

            service.exportAudit(Path.of("release-audit.csv"));

            System.out.println("\nAudit exported successfully.");

        } catch (Exception exception) {
            System.err.println(
                "Release management failure: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}

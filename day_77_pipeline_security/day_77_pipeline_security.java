import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Predicate;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Enterprise Pipeline Security and Governance System
 *
 * Java 17 implementation covering:
 * - Secret lifecycle management
 * - Job identities and permissions
 * - Dependency verification
 * - Vulnerability policy
 * - Artifact provenance
 * - Workflow action pinning
 * - Approval policies
 * - Protected branch requirements
 * - Pipeline state transitions
 * - Audit logging
 *
 * Compile:
 * javac PipelineSecurity.java
 *
 * Run:
 * java PipelineSecurity
 */

public class PipelineSecurity {

    // ========================================================
    // 1. Enumerations and Exceptions
    // ========================================================

    enum Permission {
        CONTENTS_READ,
        CONTENTS_WRITE,
        ACTIONS_READ,
        ACTIONS_WRITE,
        PACKAGES_READ,
        PACKAGES_WRITE,
        DEPLOYMENTS_READ,
        DEPLOYMENTS_WRITE,
        IDENTITY_WRITE
    }

    enum Severity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    enum PipelineState {
        CREATED,
        VALIDATING,
        RUNNING,
        BLOCKED,
        SUCCEEDED,
        FAILED
    }

    enum ReviewState {
        PENDING,
        APPROVED,
        CHANGES_REQUESTED,
        DISMISSED
    }

    enum DependencyStatus {
        VERIFIED,
        UNVERIFIED,
        VULNERABLE,
        BLOCKED
    }

    static class SecurityException extends RuntimeException {

        SecurityException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends SecurityException {

        AuthorizationException(String message) {
            super(message);
        }
    }

    static class SupplyChainException extends SecurityException {

        SupplyChainException(String message) {
            super(message);
        }
    }


    // ========================================================
    // 2. Immutable Domain Records
    // ========================================================

    record AuditEvent(
        String id,
        Instant timestamp,
        String eventType,
        String actor,
        String resource,
        String outcome,
        Map<String, String> details
    ) {
        AuditEvent {
            details = Map.copyOf(details);
        }
    }


    record JobIdentity(
        String name,
        Set<Permission> permissions,
        Set<String> allowedSecrets
    ) {
        JobIdentity {
            Objects.requireNonNull(name);
            Objects.requireNonNull(permissions);
            Objects.requireNonNull(allowedSecrets);

            if (name.isBlank()) {
                throw new SecurityException("Identity name is required");
            }

            permissions = Set.copyOf(permissions);
            allowedSecrets = Set.copyOf(allowedSecrets);
        }
    }


    record Dependency(
        String name,
        String version,
        String expectedDigest,
        String actualDigest,
        String source,
        Severity severity
    ) {}


    record DependencyAssessment(
        String name,
        DependencyStatus status,
        String reason
    ) {}


    record Artifact(
        String name,
        String digest,
        String sourceCommit,
        String builderIdentity,
        Set<String> dependencies,
        Instant createdAt
    ) {
        Artifact {
            dependencies = Set.copyOf(dependencies);
        }
    }


    record Review(
        String reviewer,
        ReviewState state,
        boolean eligible,
        boolean stale
    ) {}


    record StatusCheck(
        String name,
        boolean completed,
        boolean passed
    ) {}


    record PipelineRequest(
        String id,
        String sourceBranch,
        String targetBranch,
        JobIdentity identity,
        boolean untrustedSource,
        int approvalCount,
        List<Dependency> dependencies,
        Artifact artifact,
        String attestation
    ) {
        PipelineRequest {
            dependencies = List.copyOf(dependencies);

            if (approvalCount < 0) {
                throw new IllegalArgumentException(
                    "Approval count cannot be negative"
                );
            }
        }
    }


    record ApprovalPolicy(
        int minimumApprovals,
        boolean requireEligibleReviewers,
        boolean rejectChangesRequested,
        boolean rejectStaleApprovals
    ) {
        ApprovalPolicy {
            if (minimumApprovals < 0) {
                throw new IllegalArgumentException(
                    "Invalid approval threshold"
                );
            }
        }
    }


    record BranchProtectionPolicy(
        String branchName,
        ApprovalPolicy approvalPolicy,
        Set<String> requiredChecks,
        boolean requireResolvedConversations,
        boolean requireLinearHistory,
        boolean allowDirectPush,
        boolean allowForcePush,
        boolean allowDeletion,
        boolean allowAdministratorBypass
    ) {
        BranchProtectionPolicy {
            requiredChecks = Set.copyOf(requiredChecks);
        }
    }


    record PullRequest(
        String id,
        String sourceBranch,
        String targetBranch,
        boolean open,
        boolean draft,
        boolean conversationsResolved,
        boolean linearHistory,
        List<Review> reviews,
        List<StatusCheck> checks
    ) {
        PullRequest {
            reviews = List.copyOf(reviews);
            checks = List.copyOf(checks);
        }
    }


    record PolicyResult(
        boolean eligible,
        List<String> violations
    ) {
        PolicyResult {
            violations = List.copyOf(violations);
        }
    }


    // ========================================================
    // 3. Audit Service
    // ========================================================

    static class AuditService {

        private final List<AuditEvent> events =
            Collections.synchronizedList(new ArrayList<>());

        void record(
            String type,
            String actor,
            String resource,
            String outcome,
            Map<String, String> details
        ) {

            events.add(new AuditEvent(
                UUID.randomUUID().toString(),
                Instant.now(),
                type,
                actor,
                resource,
                outcome,
                details
            ));
        }

        void record(
            String type,
            String actor,
            String resource,
            String outcome
        ) {

            record(
                type,
                actor,
                resource,
                outcome,
                Map.of()
            );
        }

        List<AuditEvent> find(Predicate<AuditEvent> predicate) {

            synchronized (events) {
                return events.stream()
                    .filter(predicate)
                    .toList();
            }
        }

        long countFailures() {

            return find(event ->
                event.outcome().equals("DENIED") ||
                event.outcome().equals("BLOCKED") ||
                event.outcome().equals("FAILED")
            ).size();
        }
    }


    // ========================================================
    // 4. Secret Management Service
    // ========================================================

    static class SecretService {

        private record SecretRecord(
            String name,
            String value,
            int version,
            Instant expiresAt,
            boolean enabled
        ) {}

        private final Map<String, SecretRecord> secrets =
            new ConcurrentHashMap<>();

        private final AuditService audit;

        private static final Pattern NAME_PATTERN =
            Pattern.compile("[A-Z][A-Z0-9_]{1,63}");

        SecretService(AuditService audit) {
            this.audit = audit;
        }

        void store(
            String name,
            String value,
            String actor,
            Instant expiresAt
        ) {

            if (!NAME_PATTERN.matcher(name).matches()) {
                throw new SecurityException("Invalid secret name");
            }

            if (value == null ||
                value.isBlank() ||
                value.length() > 16384) {

                throw new SecurityException("Invalid secret value");
            }

            if (expiresAt != null &&
                !expiresAt.isAfter(Instant.now())) {

                throw new SecurityException(
                    "Secret expiration must be in the future"
                );
            }

            secrets.compute(name, (key, previous) -> {

                int version = previous == null
                    ? 1
                    : previous.version() + 1;

                return new SecretRecord(
                    name,
                    value,
                    version,
                    expiresAt,
                    true
                );
            });

            audit.record(
                "SECRET_STORED",
                actor,
                name,
                "SUCCESS"
            );
        }

        String retrieve(String name, JobIdentity identity) {

            if (!identity.allowedSecrets().contains(name)) {

                audit.record(
                    "SECRET_ACCESS",
                    identity.name(),
                    name,
                    "DENIED"
                );

                throw new AuthorizationException(
                    "Secret access denied"
                );
            }

            SecretRecord record = secrets.get(name);

            if (record == null || !record.enabled()) {
                throw new SecurityException("Secret unavailable");
            }

            if (
                record.expiresAt() != null &&
                !record.expiresAt().isAfter(Instant.now())
            ) {
                throw new SecurityException("Secret expired");
            }

            audit.record(
                "SECRET_ACCESS",
                identity.name(),
                name,
                "SUCCESS"
            );

            return record.value();
        }

        void rotate(String name, String value, String actor) {

            if (!secrets.containsKey(name)) {
                throw new SecurityException("Unknown secret");
            }

            store(name, value, actor, null);

            audit.record(
                "SECRET_ROTATED",
                actor,
                name,
                "SUCCESS"
            );
        }

        void revoke(String name, String actor) {

            secrets.compute(name, (key, record) -> {

                if (record == null) {
                    throw new SecurityException("Unknown secret");
                }

                return new SecretRecord(
                    record.name(),
                    record.value(),
                    record.version(),
                    record.expiresAt(),
                    false
                );
            });

            audit.record(
                "SECRET_REVOKED",
                actor,
                name,
                "SUCCESS"
            );
        }

        List<Map<String, Object>> metadata() {

            return secrets.values().stream()
                .map(record -> Map.<String, Object>of(
                    "name", record.name(),
                    "version", record.version(),
                    "enabled", record.enabled()
                ))
                .toList();
        }

        String mask(String input) {

            String result = input;

            for (SecretRecord record : secrets.values()) {

                if (!record.value().isEmpty()) {
                    result = result.replace(
                        record.value(),
                        "***REDACTED***"
                    );
                }
            }

            return result;
        }
    }


    // ========================================================
    // 5. Permission Policy Service
    // ========================================================

    static class PermissionService {

        private final AuditService audit;

        PermissionService(AuditService audit) {
            this.audit = audit;
        }

        void validate(JobIdentity identity) {

            if (identity.permissions().size() > 5) {
                throw new AuthorizationException(
                    "Excessive permissions"
                );
            }

            if (
                identity.permissions().contains(
                    Permission.CONTENTS_WRITE
                ) &&
                !identity.permissions().contains(
                    Permission.CONTENTS_READ
                )
            ) {
                throw new AuthorizationException(
                    "Content write requires content read"
                );
            }

            if (identity.allowedSecrets().size() > 20) {
                throw new AuthorizationException(
                    "Excessive secret access"
                );
            }
        }

        void authorize(
            JobIdentity identity,
            Permission permission,
            String resource
        ) {

            boolean allowed =
                identity.permissions().contains(permission);

            audit.record(
                "PERMISSION_CHECK",
                identity.name(),
                resource,
                allowed ? "SUCCESS" : "DENIED"
            );

            if (!allowed) {
                throw new AuthorizationException(
                    "Missing permission: " + permission
                );
            }
        }
    }


    // ========================================================
    // 6. Supply-Chain Verification
    // ========================================================

    static class SupplyChainService {

        private static final Pattern DIGEST =
            Pattern.compile("[a-fA-F0-9]{64}");

        private static final Pattern PACKAGE_NAME =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_.-]{0,127}");

        private final Set<String> blockedSources =
            Set.of("untrusted-mirror");

        DependencyAssessment assess(Dependency dependency) {

            if (
                dependency.name() == null ||
                !PACKAGE_NAME.matcher(dependency.name()).matches()
            ) {
                throw new SupplyChainException(
                    "Invalid dependency name"
                );
            }

            if (
                dependency.version() == null ||
                dependency.version().isBlank()
            ) {
                throw new SupplyChainException(
                    "Dependency version is required"
                );
            }

            if (blockedSources.contains(dependency.source())) {

                return new DependencyAssessment(
                    dependency.name(),
                    DependencyStatus.BLOCKED,
                    "Unapproved package source"
                );
            }

            if (
                !DIGEST.matcher(dependency.expectedDigest()).matches() ||
                !DIGEST.matcher(dependency.actualDigest()).matches()
            ) {
                throw new SupplyChainException(
                    "Invalid dependency digest"
                );
            }

            if (!MessageDigest.isEqual(
                HexFormat.of().parseHex(dependency.expectedDigest()),
                HexFormat.of().parseHex(dependency.actualDigest())
            )) {

                return new DependencyAssessment(
                    dependency.name(),
                    DependencyStatus.UNVERIFIED,
                    "Digest mismatch"
                );
            }

            if (
                dependency.severity() == Severity.HIGH ||
                dependency.severity() == Severity.CRITICAL
            ) {

                return new DependencyAssessment(
                    dependency.name(),
                    DependencyStatus.VULNERABLE,
                    "High or critical vulnerability"
                );
            }

            return new DependencyAssessment(
                dependency.name(),
                DependencyStatus.VERIFIED,
                "Dependency integrity verified"
            );
        }

        List<DependencyAssessment> scan(
            List<Dependency> dependencies
        ) {

            Set<String> names = new HashSet<>();

            return dependencies.stream()
                .map(dependency -> {

                    if (!names.add(dependency.name().toLowerCase())) {
                        throw new SupplyChainException(
                            "Duplicate dependency detected"
                        );
                    }

                    return assess(dependency);
                })
                .toList();
        }

        boolean allVerified(List<Dependency> dependencies) {

            return scan(dependencies).stream()
                .allMatch(result ->
                    result.status() == DependencyStatus.VERIFIED
                );
        }
    }


    // ========================================================
    // 7. Artifact Provenance Service
    // ========================================================

    static class ProvenanceService {

        private final byte[] signingKey;

        ProvenanceService(byte[] signingKey) {

            if (signingKey == null || signingKey.length < 32) {
                throw new SecurityException(
                    "Signing key must contain at least 32 bytes"
                );
            }

            this.signingKey = signingKey.clone();
        }

        private byte[] canonicalPayload(Artifact artifact) {

            String dependencies = artifact.dependencies().stream()
                .sorted()
                .collect(Collectors.joining(","));

            String payload = String.join(
                "|",
                artifact.name(),
                artifact.digest(),
                artifact.sourceCommit(),
                artifact.builderIdentity(),
                dependencies,
                artifact.createdAt().toString()
            );

            return payload.getBytes(StandardCharsets.UTF_8);
        }

        String sign(Artifact artifact) {

            try {

                javax.crypto.Mac mac =
                    javax.crypto.Mac.getInstance("HmacSHA256");

                mac.init(
                    new javax.crypto.spec.SecretKeySpec(
                        signingKey,
                        "HmacSHA256"
                    )
                );

                return HexFormat.of().formatHex(
                    mac.doFinal(canonicalPayload(artifact))
                );

            } catch (Exception exception) {

                throw new SecurityException(
                    "Unable to sign artifact"
                );
            }
        }

        boolean verify(Artifact artifact, String signature) {

            if (
                signature == null ||
                !signature.matches("[a-fA-F0-9]{64}")
            ) {
                return false;
            }

            byte[] expected = HexFormat.of().parseHex(
                sign(artifact)
            );

            byte[] actual = HexFormat.of().parseHex(signature);

            return MessageDigest.isEqual(expected, actual);
        }

        boolean validateArtifact(Artifact artifact) {

            return artifact != null &&
                artifact.name() != null &&
                !artifact.name().isBlank() &&
                artifact.digest() != null &&
                artifact.digest().matches("[a-fA-F0-9]{64}") &&
                artifact.sourceCommit() != null &&
                artifact.sourceCommit().matches("[a-fA-F0-9]{40}") &&
                artifact.builderIdentity() != null &&
                !artifact.builderIdentity().isBlank();
        }
    }


    // ========================================================
    // 8. Workflow Configuration Policy
    // ========================================================

    static class WorkflowPolicy {

        private static final Pattern COMMIT_SHA =
            Pattern.compile("[a-fA-F0-9]{40}");

        static void validateAction(String name, String reference) {

            if (name == null || name.isBlank()) {
                throw new SecurityException("Action name is required");
            }

            if (
                reference == null ||
                !COMMIT_SHA.matcher(reference).matches()
            ) {
                throw new SecurityException(
                    "Third-party actions must use a full commit SHA"
                );
            }
        }

        static void validateShellInput(String input) {

            List<Pattern> dangerousPatterns = List.of(
                Pattern.compile(
                    "\\$\\{\\{\\s*github\\.event\\.issue\\.title",
                    Pattern.CASE_INSENSITIVE
                ),
                Pattern.compile(
                    "\\$\\{\\{\\s*github\\.event\\.pull_request\\.title",
                    Pattern.CASE_INSENSITIVE
                ),
                Pattern.compile(
                    "\\$\\{\\{\\s*github\\.event\\.comment\\.body",
                    Pattern.CASE_INSENSITIVE
                )
            );

            if (dangerousPatterns.stream().anyMatch(
                pattern -> pattern.matcher(input).find()
            )) {
                throw new SecurityException(
                    "Untrusted event data must not be interpolated "
                    + "directly into shell commands"
                );
            }
        }
    }


    // ========================================================
    // 9. Approval and Branch Protection
    // ========================================================

    static class ApprovalService {

        int countValidApprovals(
            List<Review> reviews,
            ApprovalPolicy policy
        ) {

            Set<String> reviewers = new HashSet<>();

            for (Review review : reviews) {

                if (review.state() != ReviewState.APPROVED) {
                    continue;
                }

                if (
                    policy.requireEligibleReviewers() &&
                    !review.eligible()
                ) {
                    continue;
                }

                if (
                    policy.rejectStaleApprovals() &&
                    review.stale()
                ) {
                    continue;
                }

                reviewers.add(review.reviewer());
            }

            return reviewers.size();
        }

        boolean hasActiveChangeRequest(
            List<Review> reviews
        ) {

            return reviews.stream().anyMatch(review ->
                review.eligible() &&
                !review.stale() &&
                review.state() == ReviewState.CHANGES_REQUESTED
            );
        }
    }


    static class BranchProtectionService {

        private final ApprovalService approvalService =
            new ApprovalService();

        PolicyResult evaluate(
            PullRequest pullRequest,
            BranchProtectionPolicy policy
        ) {

            List<String> violations = new ArrayList<>();

            if (!pullRequest.open()) {
                violations.add("Pull Request is closed");
            }

            if (pullRequest.draft()) {
                violations.add("Draft Pull Request cannot merge");
            }

            if (!pullRequest.targetBranch().equals(policy.branchName())) {
                violations.add("Target branch policy mismatch");
            }

            if (
                policy.requireResolvedConversations() &&
                !pullRequest.conversationsResolved()
            ) {
                violations.add("Unresolved review conversations");
            }

            if (
                policy.requireLinearHistory() &&
                !pullRequest.linearHistory()
            ) {
                violations.add("Linear history requirement failed");
            }

            if (
                approvalService.hasActiveChangeRequest(
                    pullRequest.reviews()
                )
            ) {
                violations.add("Active requested changes");
            }

            int approvals = approvalService.countValidApprovals(
                pullRequest.reviews(),
                policy.approvalPolicy()
            );

            if (
                approvals <
                policy.approvalPolicy().minimumApprovals()
            ) {
                violations.add("Insufficient eligible approvals");
            }

            Map<String, StatusCheck> checkMap =
                new HashMap<>();

            for (StatusCheck check : pullRequest.checks()) {
                checkMap.put(check.name(), check);
            }

            for (String required : policy.requiredChecks()) {

                StatusCheck check = checkMap.get(required);

                if (
                    check == null ||
                    !check.completed() ||
                    !check.passed()
                ) {
                    violations.add(
                        "Required check failed: " + required
                    );
                }
            }

            return new PolicyResult(
                violations.isEmpty(),
                violations
            );
        }
    }


    // ========================================================
    // 10. Pipeline Execution Service
    // ========================================================

    static class PipelineExecutionService {

        private final AuditService audit;
        private final PermissionService permissions;
        private final SupplyChainService supplyChain;
        private final ProvenanceService provenance;

        private final Set<String> processedRuns =
            ConcurrentHashMap.newKeySet();

        PipelineExecutionService(
            AuditService audit,
            PermissionService permissions,
            SupplyChainService supplyChain,
            ProvenanceService provenance
        ) {

            this.audit = audit;
            this.permissions = permissions;
            this.supplyChain = supplyChain;
            this.provenance = provenance;
        }

        CompletableFuture<PipelineState> execute(
            PipelineRequest request
        ) {

            if (!processedRuns.add(request.id())) {
                throw new SecurityException(
                    "Duplicate pipeline execution"
                );
            }

            return CompletableFuture.supplyAsync(() -> {

                audit.record(
                    "PIPELINE_VALIDATION",
                    request.identity().name(),
                    request.id(),
                    "STARTED"
                );

                try {

                    permissions.validate(request.identity());

                    if (
                        request.untrustedSource() &&
                        !request.identity().allowedSecrets().isEmpty()
                    ) {
                        throw new AuthorizationException(
                            "Untrusted source cannot access secrets"
                        );
                    }

                    if (!supplyChain.allVerified(request.dependencies())) {
                        throw new SupplyChainException(
                            "Dependency policy failed"
                        );
                    }

                    if (!provenance.validateArtifact(request.artifact())) {
                        throw new SecurityException(
                            "Artifact metadata is invalid"
                        );
                    }

                    if (!provenance.verify(
                        request.artifact(),
                        request.attestation()
                    )) {
                        throw new SecurityException(
                            "Artifact provenance verification failed"
                        );
                    }

                    permissions.authorize(
                        request.identity(),
                        Permission.DEPLOYMENTS_WRITE,
                        request.targetBranch()
                    );

                    audit.record(
                        "PIPELINE_EXECUTION",
                        request.identity().name(),
                        request.id(),
                        "SUCCESS"
                    );

                    return PipelineState.SUCCEEDED;

                } catch (RuntimeException exception) {

                    audit.record(
                        "PIPELINE_EXECUTION",
                        request.identity().name(),
                        request.id(),
                        "BLOCKED",
                        Map.of("reason", exception.getMessage())
                    );

                    return PipelineState.BLOCKED;
                }
            });
        }
    }


    // ========================================================
    // 11. Demonstration and Validation
    // ========================================================

    public static void main(String[] args) {

        AuditService audit = new AuditService();

        SecretService secretService = new SecretService(audit);

        PermissionService permissionService =
            new PermissionService(audit);

        SupplyChainService supplyChain =
            new SupplyChainService();

        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);

        ProvenanceService provenance =
            new ProvenanceService(key);

        secretService.store(
            "PRODUCTION_TOKEN",
            UUID.randomUUID().toString(),
            "security-admin",
            null
        );

        JobIdentity identity = new JobIdentity(
            "production-deployment",
            EnumSet.of(
                Permission.CONTENTS_READ,
                Permission.DEPLOYMENTS_WRITE
            ),
            Set.of()
        );

        String dependencyDigest = "a".repeat(64);

        Dependency dependency = new Dependency(
            "framework",
            "1.2.0",
            dependencyDigest,
            dependencyDigest,
            "approved-registry",
            Severity.LOW
        );

        Artifact artifact = new Artifact(
            "application-release",
            "b".repeat(64),
            "c".repeat(40),
            "trusted-ci-builder",
            Set.of("framework@1.2.0"),
            Instant.now()
        );

        String attestation = provenance.sign(artifact);

        PipelineExecutionService execution =
            new PipelineExecutionService(
                audit,
                permissionService,
                supplyChain,
                provenance
            );

        PipelineRequest request = new PipelineRequest(
            "RUN-4001",
            "release/1.0",
            "production",
            identity,
            false,
            2,
            List.of(dependency),
            artifact,
            attestation
        );

        PipelineState state = execution.execute(request).join();

        System.out.println("PIPELINE RESULT");
        System.out.println("Run: " + request.id());
        System.out.println("State: " + state);

        // Branch protection configuration.
        ApprovalPolicy approvalPolicy = new ApprovalPolicy(
            2,
            true,
            true,
            true
        );

        BranchProtectionPolicy branchPolicy =
            new BranchProtectionPolicy(
                "main",
                approvalPolicy,
                Set.of("unit-tests", "security-scan", "build"),
                true,
                true,
                false,
                false,
                false,
                false
            );

        PullRequest pullRequest = new PullRequest(
            "PR-4001",
            "release/1.0",
            "main",
            true,
            false,
            true,
            true,
            List.of(
                new Review("reviewer-1", ReviewState.APPROVED, true, false),
                new Review("reviewer-2", ReviewState.APPROVED, true, false)
            ),
            List.of(
                new StatusCheck("unit-tests", true, true),
                new StatusCheck("security-scan", true, true),
                new StatusCheck("build", true, true)
            )
        );

        BranchProtectionService branchProtection =
            new BranchProtectionService();

        PolicyResult result = branchProtection.evaluate(
            pullRequest,
            branchPolicy
        );

        System.out.println("\nMERGE ELIGIBILITY");
        System.out.println("Eligible: " + result.eligible());
        System.out.println("Violations: " + result.violations());

        // Test 1: Dependency digest mismatch.
        Dependency tampered = new Dependency(
            "framework",
            "1.2.0",
            "a".repeat(64),
            "f".repeat(64),
            "approved-registry",
            Severity.LOW
        );

        assert supplyChain.assess(tampered).status()
            == DependencyStatus.UNVERIFIED;

        // Test 2: Critical vulnerability.
        Dependency vulnerable = new Dependency(
            "framework",
            "1.2.0",
            dependencyDigest,
            dependencyDigest,
            "approved-registry",
            Severity.CRITICAL
        );

        assert supplyChain.assess(vulnerable).status()
            == DependencyStatus.VULNERABLE;

        // Test 3: Invalid secret access.
        JobIdentity unauthorized = new JobIdentity(
            "external-job",
            Set.of(),
            Set.of()
        );

        try {
            secretService.retrieve(
                "PRODUCTION_TOKEN",
                unauthorized
            );
            throw new AssertionError("Unauthorized access succeeded");
        } catch (AuthorizationException expected) {
            System.out.println("Unauthorized secret access: BLOCKED");
        }

        // Test 4: Invalid action reference.
        try {
            WorkflowPolicy.validateAction(
                "third-party/action",
                "v2"
            );
            throw new AssertionError("Mutable action accepted");
        } catch (SecurityException expected) {
            System.out.println("Mutable action reference: BLOCKED");
        }

        // Test 5: Stale approval.
        List<Review> staleReviews = List.of(
            new Review("reviewer-1", ReviewState.APPROVED, true, true),
            new Review("reviewer-2", ReviewState.APPROVED, true, false)
        );

        assert new ApprovalService().countValidApprovals(
            staleReviews,
            approvalPolicy
        ) == 1;

        // Test 6: Unresolved discussions.
        PullRequest unresolved = new PullRequest(
            "PR-4002",
            "release/1.0",
            "main",
            true,
            false,
            false,
            true,
            pullRequest.reviews(),
            pullRequest.checks()
        );

        assert !branchProtection.evaluate(
            unresolved,
            branchPolicy
        ).eligible();

        // Test 7: Tampered artifact attestation.
        Artifact modifiedArtifact = new Artifact(
            artifact.name(),
            "f".repeat(64),
            artifact.sourceCommit(),
            artifact.builderIdentity(),
            artifact.dependencies(),
            artifact.createdAt()
        );

        assert !provenance.verify(
            modifiedArtifact,
            attestation
        );

        // Test 8: Untrusted pipeline cannot access secrets.
        PipelineRequest untrusted = new PipelineRequest(
            "RUN-4002",
            "external/contribution",
            "production",
            new JobIdentity(
                "external-deployment",
                EnumSet.of(
                    Permission.CONTENTS_READ,
                    Permission.DEPLOYMENTS_WRITE
                ),
                Set.of("PRODUCTION_TOKEN")
            ),
            true,
            2,
            List.of(dependency),
            artifact,
            attestation
        );

        assert execution.execute(untrusted).join()
            == PipelineState.BLOCKED;

        System.out.println("\nALL SECURITY TESTS PASSED");

        System.out.println("\nAUDIT REPORT");
        System.out.println("Total events: " +
            audit.find(event -> true).size());

        System.out.println("Failed events: " +
            audit.countFailures());
    }
}

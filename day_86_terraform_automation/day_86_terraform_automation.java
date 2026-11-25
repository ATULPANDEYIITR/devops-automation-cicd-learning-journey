import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/*
 * Terraform Automation Integrated with CI/CD
 *
 * Enterprise-oriented Terraform delivery governance.
 *
 * Java 17
 * Standard library only.
 *
 * Domain components:
 * - Repository and environment configuration
 * - Infrastructure change plans
 * - Terraform pipeline state machine
 * - Policy evaluation
 * - Security validation
 * - Independent approvals
 * - Automated status checks
 * - Deployment locking
 * - Merge/deployment eligibility
 * - Audit events
 */

public class TerraformCICD {

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum PipelineStatus {
        CREATED,
        VALIDATING,
        INITIALIZING,
        PLANNING,
        SECURITY_SCANNING,
        REVIEW_PENDING,
        APPLYING,
        SUCCEEDED,
        FAILED,
        CANCELLED
    }

    enum ReviewDecision {
        APPROVED,
        REJECTED,
        COMMENTED
    }

    enum CheckStatus {
        PENDING,
        PASSED,
        FAILED,
        SKIPPED
    }

    enum ChangeAction {
        CREATE,
        UPDATE,
        DELETE
    }

    static class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }
    }

    record Repository(
        String name,
        String defaultBranch,
        String owner
    ) {
        Repository {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Repository name is required"
                );
            }

            if (defaultBranch == null || defaultBranch.isBlank()) {
                throw new IllegalArgumentException(
                    "Default branch is required"
                );
            }

            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException(
                    "Repository owner is required"
                );
            }
        }
    }

    record Branch(
        String name,
        String commitSha,
        boolean protectedBranch
    ) {
        Branch {
            Objects.requireNonNull(name);
            Objects.requireNonNull(commitSha);

            if (name.isBlank() || commitSha.isBlank()) {
                throw new IllegalArgumentException(
                    "Invalid branch information"
                );
            }
        }
    }

    record ResourceChange(
        String resourceType,
        String resourceName,
        ChangeAction action,
        boolean encrypted,
        boolean publicIngress
    ) {
        ResourceChange {
            Objects.requireNonNull(resourceType);
            Objects.requireNonNull(resourceName);
            Objects.requireNonNull(action);

            if (resourceType.isBlank() || resourceName.isBlank()) {
                throw new IllegalArgumentException(
                    "Resource identifiers cannot be empty"
                );
            }
        }
    }

    record TerraformPlan(
        String planId,
        String configurationHash,
        String sourceCommit,
        List<ResourceChange> changes,
        Instant createdAt
    ) {
        TerraformPlan {
            Objects.requireNonNull(planId);
            Objects.requireNonNull(configurationHash);
            Objects.requireNonNull(sourceCommit);
            Objects.requireNonNull(createdAt);

            changes = List.copyOf(changes);

            if (!configurationHash.matches("[a-fA-F0-9]{64}")) {
                throw new IllegalArgumentException(
                    "Configuration hash must be SHA-256"
                );
            }

            if (changes.isEmpty()) {
                throw new IllegalArgumentException(
                    "Plan must contain at least one resource change"
                );
            }
        }

        long count(ChangeAction action) {
            return changes.stream()
                .filter(change -> change.action() == action)
                .count();
        }
    }

    record Reviewer(
        String id,
        String role,
        boolean active,
        boolean authorized
    ) {
        Reviewer {
            Objects.requireNonNull(id);
            Objects.requireNonNull(role);
        }
    }

    record Review(
        Reviewer reviewer,
        ReviewDecision decision,
        String comment,
        Instant submittedAt
    ) {
        Review {
            Objects.requireNonNull(reviewer);
            Objects.requireNonNull(decision);
            Objects.requireNonNull(submittedAt);

            comment = comment == null ? "" : comment;
        }
    }

    record StatusCheck(
        String name,
        CheckStatus status,
        String details,
        Instant updatedAt
    ) {
        StatusCheck {
            Objects.requireNonNull(name);
            Objects.requireNonNull(status);
            Objects.requireNonNull(updatedAt);

            if (name.isBlank()) {
                throw new IllegalArgumentException(
                    "Status check name is required"
                );
            }
        }
    }

    record AuditEvent(
        String eventId,
        String runId,
        String eventType,
        String details,
        Instant timestamp
    ) {}

    record Evaluation(
        boolean eligible,
        List<String> violations
    ) {
        Evaluation {
            violations = List.copyOf(violations);
        }
    }

    static final class ReviewPolicy {
        private final int requiredApprovals;
        private final boolean independentReview;
        private final Set<String> eligibleRoles;

        ReviewPolicy(
            int requiredApprovals,
            boolean independentReview,
            Set<String> eligibleRoles
        ) {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Required approvals cannot be negative"
                );
            }

            if (eligibleRoles == null || eligibleRoles.isEmpty()) {
                throw new IllegalArgumentException(
                    "Eligible reviewer roles are required"
                );
            }

            this.requiredApprovals = requiredApprovals;
            this.independentReview = independentReview;
            this.eligibleRoles = Set.copyOf(eligibleRoles);
        }

        int requiredApprovals() {
            return requiredApprovals;
        }

        boolean eligible(Reviewer reviewer) {
            return reviewer.active()
                && reviewer.authorized()
                && eligibleRoles.contains(reviewer.role());
        }

        boolean independentReview() {
            return independentReview;
        }
    }

    static final class InfrastructurePolicy {
        private final boolean requireEncryption;
        private final boolean prohibitPublicIngress;
        private final boolean prohibitDestruction;
        private final int maximumChanges;

        InfrastructurePolicy(
            boolean requireEncryption,
            boolean prohibitPublicIngress,
            boolean prohibitDestruction,
            int maximumChanges
        ) {
            if (maximumChanges <= 0) {
                throw new IllegalArgumentException(
                    "Maximum changes must be positive"
                );
            }

            this.requireEncryption = requireEncryption;
            this.prohibitPublicIngress = prohibitPublicIngress;
            this.prohibitDestruction = prohibitDestruction;
            this.maximumChanges = maximumChanges;
        }

        List<String> evaluate(TerraformPlan plan) {
            List<String> violations = new ArrayList<>();

            if (plan.changes().size() > maximumChanges) {
                violations.add(
                    "Plan exceeds maximum permitted resource changes"
                );
            }

            for (ResourceChange change : plan.changes()) {
                if (
                    requireEncryption &&
                    !change.encrypted()
                ) {
                    violations.add(
                        "Encryption violation: " + change.resourceName()
                    );
                }

                if (
                    prohibitPublicIngress &&
                    change.publicIngress()
                ) {
                    violations.add(
                        "Public ingress prohibited: " +
                        change.resourceName()
                    );
                }

                if (
                    prohibitDestruction &&
                    change.action() == ChangeAction.DELETE
                ) {
                    violations.add(
                        "Destruction prohibited: " +
                        change.resourceName()
                    );
                }
            }

            return violations;
        }
    }

    static final class DeploymentLock {

        private final ConcurrentHashMap<Environment, String> owners =
            new ConcurrentHashMap<>();

        void acquire(Environment environment, String runId) {
            String existing = owners.putIfAbsent(
                environment,
                runId
            );

            if (existing != null) {
                throw new PipelineException(
                    "Environment is locked by another deployment"
                );
            }
        }

        void release(Environment environment, String runId) {
            boolean released = owners.remove(
                environment,
                runId
            );

            if (!released) {
                throw new PipelineException(
                    "Deployment lock ownership mismatch"
                );
            }
        }
    }

    static final class ApprovalService {

        private final ReviewPolicy policy;
        private final Map<String, Review> reviews = new HashMap<>();
        private final String requester;

        ApprovalService(
            ReviewPolicy policy,
            String requester
        ) {
            this.policy = policy;
            this.requester = requester;
        }

        void submit(
            Reviewer reviewer,
            ReviewDecision decision,
            String comment
        ) {
            if (!policy.eligible(reviewer)) {
                throw new PipelineException(
                    "Reviewer is not eligible"
                );
            }

            if (
                policy.independentReview() &&
                reviewer.id().equals(requester)
            ) {
                throw new PipelineException(
                    "Self-approval is prohibited"
                );
            }

            if (reviews.containsKey(reviewer.id())) {
                throw new PipelineException(
                    "Duplicate reviewer decision"
                );
            }

            reviews.put(
                reviewer.id(),
                new Review(
                    reviewer,
                    decision,
                    comment,
                    Instant.now()
                )
            );
        }

        Evaluation evaluate() {
            List<String> violations = new ArrayList<>();

            long rejections = reviews.values().stream()
                .filter(review ->
                    review.decision() == ReviewDecision.REJECTED
                )
                .count();

            long approvals = reviews.values().stream()
                .filter(review ->
                    review.decision() == ReviewDecision.APPROVED
                )
                .count();

            if (rejections > 0) {
                violations.add(
                    "At least one reviewer rejected the plan"
                );
            }

            if (approvals < policy.requiredApprovals()) {
                violations.add(
                    "Insufficient independent approvals"
                );
            }

            return new Evaluation(
                violations.isEmpty(),
                violations
            );
        }

        List<Review> allReviews() {
            return List.copyOf(reviews.values());
        }
    }

    static final class PipelineStateMachine {

        private final Map<PipelineStatus, Set<PipelineStatus>> transitions =
            new EnumMap<>(PipelineStatus.class);

        PipelineStateMachine() {
            transitions.put(
                PipelineStatus.CREATED,
                Set.of(
                    PipelineStatus.VALIDATING,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.VALIDATING,
                Set.of(
                    PipelineStatus.INITIALIZING,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.INITIALIZING,
                Set.of(
                    PipelineStatus.PLANNING,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.PLANNING,
                Set.of(
                    PipelineStatus.SECURITY_SCANNING,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.SECURITY_SCANNING,
                Set.of(
                    PipelineStatus.REVIEW_PENDING,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.REVIEW_PENDING,
                Set.of(
                    PipelineStatus.APPLYING,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );

            transitions.put(
                PipelineStatus.APPLYING,
                Set.of(
                    PipelineStatus.SUCCEEDED,
                    PipelineStatus.FAILED,
                    PipelineStatus.CANCELLED
                )
            );
        }

        void validate(
            PipelineStatus current,
            PipelineStatus next
        ) {
            if (!transitions
                .getOrDefault(current, Set.of())
                .contains(next)) {

                throw new PipelineException(
                    "Invalid transition: " + current + " -> " + next
                );
            }
        }
    }

    static final class TerraformPipeline {

        private final String runId = UUID.randomUUID().toString();

        private final Repository repository;
        private final Branch sourceBranch;
        private final Branch targetBranch;
        private final Environment environment;

        private final TerraformPlan plan;
        private final ReviewPolicy reviewPolicy;
        private final InfrastructurePolicy infrastructurePolicy;
        private final ApprovalService approvalService;
        private final DeploymentLock deploymentLock;
        private final PipelineStateMachine stateMachine;

        private final Map<String, StatusCheck> checks =
            new HashMap<>();

        private final List<AuditEvent> auditEvents =
            new ArrayList<>();

        private final ReentrantLock transitionLock =
            new ReentrantLock();

        private PipelineStatus status = PipelineStatus.CREATED;
        private boolean validated;
        private boolean initialized;
        private boolean securityPassed;
        private boolean planApplied;

        TerraformPipeline(
            Repository repository,
            Branch sourceBranch,
            Branch targetBranch,
            Environment environment,
            TerraformPlan plan,
            ReviewPolicy reviewPolicy,
            InfrastructurePolicy infrastructurePolicy,
            DeploymentLock deploymentLock,
            String requester
        ) {
            this.repository = repository;
            this.sourceBranch = sourceBranch;
            this.targetBranch = targetBranch;
            this.environment = environment;
            this.plan = plan;
            this.reviewPolicy = reviewPolicy;
            this.infrastructurePolicy = infrastructurePolicy;
            this.deploymentLock = deploymentLock;
            this.stateMachine = new PipelineStateMachine();

            this.approvalService = new ApprovalService(
                reviewPolicy,
                requester
            );

            if (
                sourceBranch.name().equals(targetBranch.name())
            ) {
                throw new IllegalArgumentException(
                    "Source and target branches must differ"
                );
            }

            if (!targetBranch.protectedBranch() &&
                environment == Environment.PRODUCTION) {
                throw new PipelineException(
                    "Production target branch must be protected"
                );
            }

            record("pipeline_created", repository.name());
        }

        private void record(String type, String details) {
            auditEvents.add(
                new AuditEvent(
                    UUID.randomUUID().toString(),
                    runId,
                    type,
                    details,
                    Instant.now()
                )
            );
        }

        private void transition(PipelineStatus next) {
            transitionLock.lock();

            try {
                stateMachine.validate(status, next);

                PipelineStatus previous = status;
                status = next;

                record(
                    "stage_transition",
                    previous + " -> " + next
                );
            } finally {
                transitionLock.unlock();
            }
        }

        void updateCheck(
            String name,
            CheckStatus checkStatus,
            String details
        ) {
            checks.put(
                name,
                new StatusCheck(
                    name,
                    checkStatus,
                    details,
                    Instant.now()
                )
            );

            record("status_check_updated", name);
        }

        void validateConfiguration() {
            transition(PipelineStatus.VALIDATING);

            List<String> violations =
                infrastructurePolicy.evaluate(plan);

            if (!violations.isEmpty()) {
                throw new PipelineException(
                    String.join("; ", violations)
                );
            }

            if (
                !plan.sourceCommit().equals(
                    sourceBranch.commitSha()
                )
            ) {
                throw new PipelineException(
                    "Plan source commit does not match branch commit"
                );
            }

            validated = true;
            record("configuration_validated", "passed");
        }

        void initialize() {
            if (!validated) {
                throw new PipelineException(
                    "Configuration validation is required"
                );
            }

            transition(PipelineStatus.INITIALIZING);
            initialized = true;

            record("terraform_initialized", "passed");
        }

        void generatePlan() {
            if (!initialized) {
                throw new PipelineException(
                    "Terraform initialization is required"
                );
            }

            transition(PipelineStatus.PLANNING);

            record(
                "plan_generated",
                "Plan ID: " + plan.planId()
            );
        }

        void scanSecurity() {
            if (status != PipelineStatus.PLANNING) {
                throw new PipelineException(
                    "Plan must exist before security scanning"
                );
            }

            StatusCheck security = checks.get("security-scan");

            if (
                security == null ||
                security.status() != CheckStatus.PASSED
            ) {
                throw new PipelineException(
                    "Security scan has not passed"
                );
            }

            securityPassed = true;

            transition(PipelineStatus.SECURITY_SCANNING);
            record("security_scan_passed", "passed");
        }

        void submitReview(
            Reviewer reviewer,
            ReviewDecision decision,
            String comment
        ) {
            approvalService.submit(
                reviewer,
                decision,
                comment
            );

            record(
                "review_decision",
                reviewer.id() + ": " + decision
            );
        }

        Evaluation evaluateEligibility() {
            List<String> violations = new ArrayList<>();

            if (!validated) {
                violations.add("Configuration not validated");
            }

            if (!initialized) {
                violations.add("Terraform not initialized");
            }

            if (!securityPassed) {
                violations.add("Security scan not passed");
            }

            Evaluation approval = approvalService.evaluate();

            violations.addAll(approval.violations());

            if (checks.isEmpty()) {
                violations.add("No automated status checks");
            }

            for (StatusCheck check : checks.values()) {
                if (check.status() != CheckStatus.PASSED) {
                    violations.add(
                        "Status check not passed: " + check.name()
                    );
                }
            }

            return new Evaluation(
                violations.isEmpty(),
                violations
            );
        }

        void deploy() {
            transition(PipelineStatus.REVIEW_PENDING);

            Evaluation evaluation = evaluateEligibility();

            if (!evaluation.eligible()) {
                throw new PipelineException(
                    String.join("; ", evaluation.violations())
                );
            }

            transition(PipelineStatus.APPLYING);

            deploymentLock.acquire(environment, runId);

            try {
                // In production, execute terraform apply using
                // the exact reviewed, immutable plan artifact.
                planApplied = true;

                record(
                    "terraform_apply",
                    "Reviewed plan applied"
                );
            } finally {
                deploymentLock.release(environment, runId);
            }

            transition(PipelineStatus.SUCCEEDED);

            record("deployment_completed", "success");
        }

        void fail(String reason) {
            if (
                status == PipelineStatus.SUCCEEDED ||
                status == PipelineStatus.FAILED ||
                status == PipelineStatus.CANCELLED
            ) {
                throw new PipelineException(
                    "Pipeline is already in a terminal state"
                );
            }

            transition(PipelineStatus.FAILED);
            record("pipeline_failed", reason);
        }

        void printReport() {
            System.out.println("\nENTERPRISE TERRAFORM PIPELINE");

            System.out.println(
                "Repository: " + repository.name()
            );

            System.out.println(
                "Source branch: " + sourceBranch.name()
            );

            System.out.println(
                "Target branch: " + targetBranch.name()
            );

            System.out.println(
                "Environment: " + environment
            );

            System.out.println(
                "Pipeline status: " + status
            );

            System.out.println(
                "Plan ID: " + plan.planId()
            );

            System.out.println(
                "Created resources: " +
                plan.count(ChangeAction.CREATE)
            );

            System.out.println(
                "Updated resources: " +
                plan.count(ChangeAction.UPDATE)
            );

            System.out.println(
                "Deleted resources: " +
                plan.count(ChangeAction.DELETE)
            );

            System.out.println(
                "Deployment eligible: " +
                evaluateEligibility().eligible()
            );

            System.out.println(
                "Plan applied: " + planApplied
            );

            System.out.println("\nAUDIT EVENTS");

            auditEvents.forEach(event ->
                System.out.println(
                    event.timestamp() + " | " +
                    event.eventType() + " | " +
                    event.details()
                )
            );
        }
    }

    public static void main(String[] args) {

        Repository repository = new Repository(
            "cloud-infrastructure",
            "main",
            "platform-engineering"
        );

        Branch source = new Branch(
            "feature/network-hardening",
            "aabbccddeeff00112233445566778899",
            false
        );

        Branch target = new Branch(
            "main",
            "11223344556677889900aabbccddeeff",
            true
        );

        TerraformPlan plan = new TerraformPlan(
            "plan-2026-001",
            "a1234567890123456789012345678901" +
            "a1234567890123456789012345678901",
            source.commitSha(),
            List.of(
                new ResourceChange(
                    "aws_s3_bucket",
                    "application_storage",
                    ChangeAction.CREATE,
                    true,
                    false
                ),
                new ResourceChange(
                    "aws_security_group",
                    "application_network",
                    ChangeAction.UPDATE,
                    true,
                    false
                ),
                new ResourceChange(
                    "aws_db_instance",
                    "application_database",
                    ChangeAction.UPDATE,
                    true,
                    false
                )
            ),
            Instant.now()
        );

        ReviewPolicy reviewPolicy = new ReviewPolicy(
            2,
            true,
            Set.of(
                "platform-lead",
                "security-lead",
                "cloud-architect"
            )
        );

        InfrastructurePolicy infrastructurePolicy =
            new InfrastructurePolicy(
                true,
                true,
                true,
                50
            );

        DeploymentLock lock = new DeploymentLock();

        TerraformPipeline pipeline = new TerraformPipeline(
            repository,
            source,
            target,
            Environment.PRODUCTION,
            plan,
            reviewPolicy,
            infrastructurePolicy,
            lock,
            "developer-001"
        );

        pipeline.updateCheck(
            "terraform-format",
            CheckStatus.PASSED,
            "Formatting passed"
        );

        pipeline.updateCheck(
            "terraform-validation",
            CheckStatus.PASSED,
            "Configuration valid"
        );

        pipeline.updateCheck(
            "security-scan",
            CheckStatus.PASSED,
            "No critical findings"
        );

        pipeline.updateCheck(
            "policy-check",
            CheckStatus.PASSED,
            "Policies satisfied"
        );

        Reviewer platformLead = new Reviewer(
            "reviewer-101",
            "platform-lead",
            true,
            true
        );

        Reviewer securityLead = new Reviewer(
            "reviewer-102",
            "security-lead",
            true,
            true
        );

        try {
            pipeline.validateConfiguration();
            pipeline.initialize();
            pipeline.generatePlan();
            pipeline.scanSecurity();

            pipeline.submitReview(
                platformLead,
                ReviewDecision.APPROVED,
                "Infrastructure architecture verified"
            );

            pipeline.submitReview(
                securityLead,
                ReviewDecision.APPROVED,
                "Security review completed"
            );

            pipeline.deploy();

        } catch (Exception exception) {
            try {
                pipeline.fail(exception.getMessage());
            } catch (PipelineException terminalError) {
                System.err.println(terminalError.getMessage());
            }

            System.err.println(
                "PIPELINE FAILURE: " + exception.getMessage()
            );
        }

        pipeline.printReport();
    }
}

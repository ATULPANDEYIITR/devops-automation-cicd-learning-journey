#include <algorithm>
#include <array>
#include <cassert>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Pipeline Security and Merge-Execution Governance Engine
 *
 * C++17 implementation of a security decision engine.
 *
 * Evaluates:
 * - Secret exposure
 * - Job permissions
 * - Dependency integrity
 * - Vulnerability severity
 * - Artifact provenance
 * - Action reference pinning
 * - Approval requirements
 * - Deployment authorization
 * - Pipeline execution eligibility
 *
 * Build:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic pipeline_security.cpp -o pipeline_security
 */

namespace security {

enum class Permission {
    ContentsRead,
    ContentsWrite,
    ActionsRead,
    ActionsWrite,
    PackagesRead,
    PackagesWrite,
    DeploymentsRead,
    DeploymentsWrite,
    IdentityWrite
};

enum class Severity {
    Low,
    Medium,
    High,
    Critical
};

enum class DependencyStatus {
    Verified,
    Unverified,
    Vulnerable,
    Blocked
};

enum class PipelineState {
    Created,
    Validating,
    Running,
    Blocked,
    Succeeded,
    Failed
};

enum class ReviewState {
    Pending,
    Approved,
    ChangesRequested,
    Dismissed
};


std::string toString(PipelineState state) {

    switch (state) {
        case PipelineState::Created: return "CREATED";
        case PipelineState::Validating: return "VALIDATING";
        case PipelineState::Running: return "RUNNING";
        case PipelineState::Blocked: return "BLOCKED";
        case PipelineState::Succeeded: return "SUCCEEDED";
        case PipelineState::Failed: return "FAILED";
    }

    return "UNKNOWN";
}


std::string toString(DependencyStatus status) {

    switch (status) {
        case DependencyStatus::Verified: return "VERIFIED";
        case DependencyStatus::Unverified: return "UNVERIFIED";
        case DependencyStatus::Vulnerable: return "VULNERABLE";
        case DependencyStatus::Blocked: return "BLOCKED";
    }

    return "UNKNOWN";
}


// ============================================================
// 1. Domain Models
// ============================================================

struct SecurityEvent {
    std::string type;
    std::string actor;
    std::string resource;
    std::string outcome;
    std::string details;
};

class SecurityException : public std::runtime_error {
public:
    explicit SecurityException(const std::string& message)
        : std::runtime_error(message) {}
};


struct JobIdentity {
    std::string name;
    std::set<Permission> permissions;
    std::set<std::string> allowedSecrets;
};


struct Dependency {
    std::string name;
    std::string version;
    std::string expectedDigest;
    std::string actualDigest;
    std::string source;
    Severity severity;
};


struct Artifact {
    std::string name;
    std::string digest;
    std::string sourceCommit;
    std::string builderIdentity;
    std::set<std::string> dependencies;
    bool provenanceVerified = false;
};


struct Review {
    std::string reviewer;
    ReviewState state;
    bool eligible = true;
    bool stale = false;
};


struct StatusCheck {
    std::string name;
    bool completed = false;
    bool passed = false;
};


struct BranchProtection {
    std::string branchName;
    int requiredApprovals = 2;
    bool requireStatusChecks = true;
    bool requireConversationResolution = true;
    bool requireLinearHistory = true;
    bool allowDirectPush = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool allowAdministratorBypass = false;
};


struct PullRequest {
    std::string id;
    std::string sourceBranch;
    std::string targetBranch;
    std::string headCommit;
    std::string baseCommit;

    bool draft = false;
    bool open = true;
    bool conversationsResolved = true;
    bool linearHistory = true;
    bool provenanceValid = false;
    bool dependenciesValid = false;
    bool untrustedSource = false;

    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;
    std::vector<Dependency> dependencies;
    Artifact artifact;
};


struct SecurityPolicy {
    std::size_t maximumPermissions = 5;
    bool prohibitSecretsForUntrustedJobs = true;
    bool requirePinnedActions = true;
    bool requireVerifiedDependencies = true;
    bool requireProvenance = true;
    bool requireEligibleReviews = true;
};


// ============================================================
// 2. Audit Management
// ============================================================

class AuditLog {

private:
    std::vector<SecurityEvent> events_;

public:

    void record(
        const std::string& type,
        const std::string& actor,
        const std::string& resource,
        const std::string& outcome,
        const std::string& details = ""
    ) {

        events_.push_back({
            type,
            actor,
            resource,
            outcome,
            details
        });
    }

    const std::vector<SecurityEvent>& events() const {
        return events_;
    }

    std::size_t count(const std::string& outcome) const {

        return std::count_if(
            events_.begin(),
            events_.end(),
            [&](const SecurityEvent& event) {
                return event.outcome == outcome;
            }
        );
    }
};


// ============================================================
// 3. Permission Evaluation
// ============================================================

class PermissionEngine {

private:
    AuditLog& audit_;

public:

    explicit PermissionEngine(AuditLog& audit)
        : audit_(audit) {}

    bool authorize(
        const JobIdentity& identity,
        Permission required,
        const std::string& resource
    ) {

        const bool allowed =
            identity.permissions.count(required) > 0;

        audit_.record(
            "PERMISSION_CHECK",
            identity.name,
            resource,
            allowed ? "ALLOWED" : "DENIED"
        );

        if (!allowed) {
            throw SecurityException(
                "Permission denied for " + identity.name
            );
        }

        return true;
    }

    void validate(const JobIdentity& identity) const {

        if (identity.name.empty()) {
            throw SecurityException("Missing job identity");
        }

        if (identity.permissions.size() > 5) {
            throw SecurityException(
                "Excessive permissions granted to job"
            );
        }

        if (
            identity.permissions.count(Permission::ContentsWrite) &&
            !identity.permissions.count(Permission::ContentsRead)
        ) {
            throw SecurityException(
                "Content write requires content read"
            );
        }

        if (identity.allowedSecrets.size() > 20) {
            throw SecurityException(
                "Excessive secret access"
            );
        }
    }
};


// ============================================================
// 4. Dependency Integrity
// ============================================================

class DependencyScanner {

private:

    std::set<std::string> blockedSources_;

    static bool validName(const std::string& value) {

        if (value.empty() || value.size() > 128) {
            return false;
        }

        return std::all_of(
            value.begin(),
            value.end(),
            [](unsigned char c) {
                return std::isalnum(c) ||
                    c == '_' || c == '-' || c == '.';
            }
        );
    }

    static bool validDigest(const std::string& digest) {

        if (digest.size() != 64) {
            return false;
        }

        return std::all_of(
            digest.begin(),
            digest.end(),
            [](unsigned char c) {
                return std::isxdigit(c);
            }
        );
    }

public:

    explicit DependencyScanner(
        std::set<std::string> blockedSources
    ) : blockedSources_(std::move(blockedSources)) {}

    DependencyStatus assess(
        const Dependency& dependency
    ) const {

        if (!validName(dependency.name)) {
            throw SecurityException("Invalid dependency name");
        }

        if (dependency.version.empty() ||
            dependency.version.size() > 64) {
            throw SecurityException("Invalid dependency version");
        }

        if (blockedSources_.count(dependency.source)) {
            return DependencyStatus::Blocked;
        }

        if (
            !validDigest(dependency.expectedDigest) ||
            !validDigest(dependency.actualDigest)
        ) {
            throw SecurityException("Invalid dependency digest");
        }

        if (dependency.expectedDigest != dependency.actualDigest) {
            return DependencyStatus::Unverified;
        }

        if (
            dependency.severity == Severity::High ||
            dependency.severity == Severity::Critical
        ) {
            return DependencyStatus::Vulnerable;
        }

        return DependencyStatus::Verified;
    }

    bool scan(const std::vector<Dependency>& dependencies) const {

        std::set<std::string> names;

        for (const auto& dependency : dependencies) {

            if (!names.insert(dependency.name).second) {
                throw SecurityException(
                    "Duplicate dependency detected"
                );
            }

            if (assess(dependency) != DependencyStatus::Verified) {
                return false;
            }
        }

        return true;
    }
};


// ============================================================
// 5. Artifact Provenance
// ============================================================

class ProvenanceVerifier {

public:

    static bool validate(const Artifact& artifact) {

        if (artifact.name.empty() ||
            artifact.builderIdentity.empty()) {
            return false;
        }

        if (artifact.sourceCommit.size() != 40) {
            return false;
        }

        if (artifact.digest.size() != 64) {
            return false;
        }

        if (!artifact.provenanceVerified) {
            return false;
        }

        return true;
    }
};


// ============================================================
// 6. Workflow Configuration
// ============================================================

class WorkflowSecurity {

public:

    static bool isPinnedReference(const std::string& reference) {

        if (reference.size() != 40) {
            return false;
        }

        return std::all_of(
            reference.begin(),
            reference.end(),
            [](unsigned char c) {
                return std::isxdigit(c);
            }
        );
    }

    static void validateAction(
        const std::string& name,
        const std::string& reference,
        bool requirePinned
    ) {

        if (name.empty()) {
            throw SecurityException("Action name is required");
        }

        if (requirePinned && !isPinnedReference(reference)) {
            throw SecurityException(
                "Third-party action must use a full commit SHA"
            );
        }
    }
};


// ============================================================
// 7. Review and Approval Evaluation
// ============================================================

class ApprovalEngine {

public:

    static int validApprovals(
        const std::vector<Review>& reviews
    ) {

        std::set<std::string> reviewers;

        for (const auto& review : reviews) {

            if (
                !review.eligible ||
                review.stale ||
                review.state != ReviewState::Approved
            ) {
                continue;
            }

            reviewers.insert(review.reviewer);
        }

        return static_cast<int>(reviewers.size());
    }

    static bool hasRequestedChanges(
        const std::vector<Review>& reviews
    ) {

        return std::any_of(
            reviews.begin(),
            reviews.end(),
            [](const Review& review) {
                return review.eligible &&
                    !review.stale &&
                    review.state == ReviewState::ChangesRequested;
            }
        );
    }
};


// ============================================================
// 8. Branch Protection and Merge Eligibility
// ============================================================

struct EligibilityResult {
    bool eligible = false;
    std::vector<std::string> violations;
};


class MergeEligibilityEngine {

private:
    AuditLog& audit_;

public:

    explicit MergeEligibilityEngine(AuditLog& audit)
        : audit_(audit) {}

    EligibilityResult evaluate(
        const PullRequest& pr,
        const BranchProtection& protection
    ) {

        EligibilityResult result;

        auto reject = [&](const std::string& reason) {
            result.violations.push_back(reason);
        };

        if (!pr.open) {
            reject("Pull Request is closed");
        }

        if (pr.draft) {
            reject("Draft Pull Request cannot be merged");
        }

        if (pr.targetBranch != protection.branchName) {
            reject("Protection policy does not match target branch");
        }

        if (pr.sourceBranch.empty() ||
            pr.targetBranch.empty() ||
            pr.headCommit.empty() ||
            pr.baseCommit.empty()) {
            reject("Incomplete Pull Request metadata");
        }

        if (!pr.conversationsResolved &&
            protection.requireConversationResolution) {
            reject("Unresolved review conversations");
        }

        if (!pr.linearHistory &&
            protection.requireLinearHistory) {
            reject("Linear history requirement not satisfied");
        }

        if (ApprovalEngine::hasRequestedChanges(pr.reviews)) {
            reject("Active requested-changes review exists");
        }

        if (
            ApprovalEngine::validApprovals(pr.reviews) <
            protection.requiredApprovals
        ) {
            reject("Insufficient eligible approvals");
        }

        if (protection.requireStatusChecks) {

            if (pr.checks.empty()) {
                reject("No required status checks configured");
            }

            for (const auto& check : pr.checks) {

                if (!check.completed || !check.passed) {
                    reject(
                        "Required status check failed: " + check.name
                    );
                }
            }
        }

        if (!pr.dependenciesValid) {
            reject("Dependency security verification failed");
        }

        if (!pr.provenanceValid) {
            reject("Artifact provenance verification failed");
        }

        result.eligible = result.violations.empty();

        audit_.record(
            "MERGE_ELIGIBILITY",
            "merge-engine",
            pr.id,
            result.eligible ? "ELIGIBLE" : "BLOCKED",
            std::to_string(result.violations.size()) +
                " policy violations"
        );

        return result;
    }
};


// ============================================================
// 9. Pipeline Governance Engine
// ============================================================

class PipelineGovernance {

private:

    AuditLog& audit_;
    PermissionEngine permissionEngine_;
    DependencyScanner dependencyScanner_;
    SecurityPolicy policy_;

public:

    PipelineGovernance(
        AuditLog& audit,
        SecurityPolicy policy
    )
        : audit_(audit),
          permissionEngine_(audit),
          dependencyScanner_({"untrusted-mirror"}),
          policy_(policy) {}

    PipelineState execute(
        PullRequest& pr,
        const JobIdentity& identity
    ) {

        if (!pr.open) {
            throw SecurityException(
                "Cannot process a closed Pull Request"
            );
        }

        PipelineState state = PipelineState::Validating;

        audit_.record(
            "PIPELINE_VALIDATION",
            identity.name,
            pr.id,
            "STARTED"
        );

        try {

            permissionEngine_.validate(identity);

            if (
                policy_.prohibitSecretsForUntrustedJobs &&
                pr.untrustedSource &&
                !identity.allowedSecrets.empty()
            ) {
                throw SecurityException(
                    "Untrusted source cannot access secrets"
                );
            }

            if (
                policy_.requireVerifiedDependencies &&
                !dependencyScanner_.scan(pr.dependencies)
            ) {
                throw SecurityException(
                    "Dependency verification failed"
                );
            }

            if (
                policy_.requireProvenance &&
                !ProvenanceVerifier::validate(pr.artifact)
            ) {
                throw SecurityException(
                    "Artifact provenance failed"
                );
            }

            if (policy_.requirePinnedActions) {
                WorkflowSecurity::validateAction(
                    "third-party-action",
                    "a",
                    true
                );
            }

            pr.dependenciesValid = dependencyScanner_.scan(
                pr.dependencies
            );

            pr.provenanceValid = ProvenanceVerifier::validate(
                pr.artifact
            );

            state = PipelineState::Running;

            permissionEngine_.authorize(
                identity,
                Permission::DeploymentsWrite,
                pr.targetBranch
            );

            state = PipelineState::Succeeded;

            audit_.record(
                "PIPELINE_EXECUTION",
                identity.name,
                pr.id,
                "SUCCESS"
            );

        } catch (const std::exception& exception) {

            state = PipelineState::Blocked;

            audit_.record(
                "PIPELINE_EXECUTION",
                identity.name,
                pr.id,
                "BLOCKED",
                exception.what()
            );
        }

        return state;
    }
};

} // namespace security


// ============================================================
// 10. Demonstration
// ============================================================

int main() {

    using namespace security;

    AuditLog audit;

    SecurityPolicy policy;

    PipelineGovernance governance(
        audit,
        policy
    );

    Dependency dependency{
        "framework",
        "1.2.0",
        std::string(64, 'a'),
        std::string(64, 'a'),
        "approved-registry",
        Severity::Low
    };

    Artifact artifact{
        "application-release",
        std::string(64, 'b'),
        std::string(40, 'c'),
        "trusted-ci-builder",
        {"framework@1.2.0"},
        true
    };

    PullRequest pr;

    pr.id = "PR-3001";
    pr.sourceBranch = "release/1.0";
    pr.targetBranch = "main";
    pr.headCommit = std::string(40, 'c');
    pr.baseCommit = std::string(40, 'd');

    pr.open = true;
    pr.draft = false;
    pr.conversationsResolved = true;
    pr.linearHistory = true;
    pr.dependencies = {dependency};
    pr.artifact = artifact;

    pr.reviews = {
        {"reviewer-1", ReviewState::Approved, true, false},
        {"reviewer-2", ReviewState::Approved, true, false}
    };

    pr.checks = {
        {"unit-tests", true, true},
        {"security-scan", true, true},
        {"build", true, true}
    };

    BranchProtection protection;

    protection.branchName = "main";
    protection.requiredApprovals = 2;

    MergeEligibilityEngine mergeEngine(audit);

    EligibilityResult eligibility =
        mergeEngine.evaluate(pr, protection);

    std::cout << "MERGE ELIGIBILITY\n";
    std::cout << "Eligible: "
              << std::boolalpha
              << eligibility.eligible << '\n';

    for (const auto& violation : eligibility.violations) {
        std::cout << "Violation: " << violation << '\n';
    }

    JobIdentity deploymentIdentity{
        "production-deployment",
        {
            Permission::ContentsRead,
            Permission::DeploymentsWrite
        },
        {}
    };

    PipelineState successful = governance.execute(
        pr,
        deploymentIdentity
    );

    std::cout << "\nPIPELINE STATE: "
              << toString(successful) << '\n';

    // Test 1: Dependency tampering.
    DependencyScanner scanner({"untrusted-mirror"});

    Dependency tampered = dependency;
    tampered.actualDigest = std::string(64, 'f');

    assert(
        scanner.assess(tampered) ==
        DependencyStatus::Unverified
    );

    // Test 2: Vulnerable dependency.
    Dependency vulnerable = dependency;
    vulnerable.severity = Severity::Critical;

    assert(
        scanner.assess(vulnerable) ==
        DependencyStatus::Vulnerable
    );

    // Test 3: Blocked dependency source.
    Dependency blocked = dependency;
    blocked.source = "untrusted-mirror";

    assert(
        scanner.assess(blocked) ==
        DependencyStatus::Blocked
    );

    // Test 4: Missing deployment permission.
    JobIdentity readOnly{
        "read-only-job",
        {Permission::ContentsRead},
        {}
    };

    try {

        PermissionEngine permissionEngine(audit);

        permissionEngine.authorize(
            readOnly,
            Permission::DeploymentsWrite,
            "production"
        );

        assert(false);

    } catch (const SecurityException&) {
        std::cout << "Unauthorized deployment: BLOCKED\n";
    }

    // Test 5: Stale approvals do not count.
    std::vector<Review> staleReviews{
        {"reviewer-1", ReviewState::Approved, true, true},
        {"reviewer-2", ReviewState::Approved, true, false}
    };

    assert(
        ApprovalEngine::validApprovals(staleReviews) == 1
    );

    // Test 6: Draft Pull Request cannot merge.
    PullRequest draft = pr;
    draft.id = "PR-3002";
    draft.draft = true;

    assert(
        !mergeEngine.evaluate(draft, protection).eligible
    );

    // Test 7: Unresolved discussions block merging.
    PullRequest unresolved = pr;
    unresolved.id = "PR-3003";
    unresolved.conversationsResolved = false;

    assert(
        !mergeEngine.evaluate(unresolved, protection).eligible
    );

    // Test 8: Mutable action references are rejected.
    assert(!WorkflowSecurity::isPinnedReference("v2"));

    // Test 9: Untrusted pull request cannot access secrets.
    PullRequest external = pr;
    external.id = "PR-3004";
    external.untrustedSource = true;

    JobIdentity externalIdentity{
        "external-job",
        {
            Permission::ContentsRead,
            Permission::DeploymentsWrite
        },
        {"PRODUCTION_TOKEN"}
    };

    assert(
        governance.execute(external, externalIdentity) ==
        PipelineState::Blocked
    );

    std::cout << "\nSECURITY ASSERTIONS: PASSED\n";

    std::cout << "\nAUDIT EVENTS: "
              << audit.events().size() << '\n';

    std::cout << "DENIED OR BLOCKED EVENTS: "
              << audit.count("DENIED") +
                 audit.count("BLOCKED") << '\n';

    return 0;
}

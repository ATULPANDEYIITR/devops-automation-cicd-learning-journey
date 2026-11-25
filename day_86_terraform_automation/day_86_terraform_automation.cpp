#include <algorithm>
#include <chrono>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Terraform Automation Integrated with CI/CD
 *
 * C++17 repository-independent infrastructure governance engine.
 *
 * Implements:
 * - Repository and environment modeling
 * - Infrastructure change plans
 * - Terraform validation stages
 * - Security policy evaluation
 * - Reviewer eligibility
 * - Approval quorum
 * - Status check enforcement
 * - Protected environment rules
 * - State locking
 * - Merge/deployment eligibility
 * - Auditable state transitions
 */

enum class Environment {
    Development,
    Staging,
    Production
};

enum class PipelineStage {
    Created,
    Validating,
    Initialized,
    Planned,
    SecurityChecked,
    AwaitingApproval,
    Applying,
    Succeeded,
    Failed
};

enum class ReviewDecision {
    Approved,
    Rejected,
    Commented
};

enum class CheckStatus {
    Pending,
    Passed,
    Failed,
    Skipped
};

enum class ChangeAction {
    Create,
    Update,
    Delete
};

std::string toString(Environment environment) {
    switch (environment) {
        case Environment::Development: return "development";
        case Environment::Staging: return "staging";
        case Environment::Production: return "production";
    }
    throw std::invalid_argument("Unknown environment");
}

std::string toString(PipelineStage stage) {
    switch (stage) {
        case PipelineStage::Created: return "created";
        case PipelineStage::Validating: return "validating";
        case PipelineStage::Initialized: return "initialized";
        case PipelineStage::Planned: return "planned";
        case PipelineStage::SecurityChecked: return "security_checked";
        case PipelineStage::AwaitingApproval: return "awaiting_approval";
        case PipelineStage::Applying: return "applying";
        case PipelineStage::Succeeded: return "succeeded";
        case PipelineStage::Failed: return "failed";
    }
    throw std::invalid_argument("Unknown pipeline stage");
}

struct ResourceChange {
    std::string resourceType;
    std::string resourceName;
    ChangeAction action;
    bool encrypted;
    bool publicIngress;

    ResourceChange(
        std::string type,
        std::string name,
        ChangeAction action,
        bool encrypted,
        bool publicIngress
    ) : resourceType(std::move(type)),
        resourceName(std::move(name)),
        action(action),
        encrypted(encrypted),
        publicIngress(publicIngress) {

        if (resourceType.empty() || resourceName.empty()) {
            throw std::invalid_argument(
                "Resource type and name are required"
            );
        }
    }
};

struct TerraformPlan {
    std::string id;
    std::string configurationHash;
    std::vector<ResourceChange> changes;
    bool reviewed = false;
    bool applied = false;

    int count(ChangeAction action) const {
        return static_cast<int>(
            std::count_if(
                changes.begin(),
                changes.end(),
                [action](const ResourceChange& change) {
                    return change.action == action;
                }
            )
        );
    }

    bool empty() const {
        return changes.empty();
    }
};

struct Reviewer {
    std::string id;
    std::string role;
    bool active = true;
    bool authorized = true;
};

struct Review {
    Reviewer reviewer;
    ReviewDecision decision;
    std::string comment;
};

struct StatusCheck {
    std::string name;
    CheckStatus status;
    std::string details;
};

struct GovernancePolicy {
    int requiredApprovals = 1;
    bool requireSecurityScan = true;
    bool requireSuccessfulChecks = true;
    bool prohibitDestruction = true;
    bool requireEncryption = true;
    bool prohibitPublicIngress = true;
    bool requireIndependentReview = true;
    bool allowDirectDeployment = false;

    std::set<std::string> permittedReviewers = {
        "platform-lead",
        "security-lead",
        "cloud-architect"
    };

    void validate() const {
        if (requiredApprovals < 0) {
            throw std::invalid_argument(
                "Approval requirement cannot be negative"
            );
        }
    }
};

class AuditLog {
private:
    std::vector<std::string> entries;

public:
    void record(const std::string& event) {
        auto now = std::chrono::system_clock::now();
        auto timestamp = std::chrono::system_clock::to_time_t(now);

        std::ostringstream stream;

        stream << std::put_time(
            std::gmtime(&timestamp),
            "%Y-%m-%dT%H:%M:%SZ"
        );

        entries.push_back(stream.str() + " | " + event);
    }

    void print() const {
        for (const auto& entry : entries) {
            std::cout << entry << '\n';
        }
    }

    std::size_t size() const {
        return entries.size();
    }
};

class StateLock {
private:
    std::mutex mutex;
    bool locked = false;
    std::string owner;

public:
    void acquire(const std::string& runId) {
        std::lock_guard<std::mutex> guard(mutex);

        if (locked) {
            throw std::runtime_error(
                "Infrastructure state is already locked"
            );
        }

        locked = true;
        owner = runId;
    }

    void release(const std::string& runId) {
        std::lock_guard<std::mutex> guard(mutex);

        if (!locked || owner != runId) {
            throw std::runtime_error(
                "Invalid state lock release"
            );
        }

        locked = false;
        owner.clear();
    }

    bool isLocked() const {
        return locked;
    }
};

class TerraformGovernanceEngine {
private:
    Environment environment;
    GovernancePolicy policy;
    PipelineStage stage = PipelineStage::Created;

    TerraformPlan plan;
    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;

    bool configurationValid = false;
    bool securityPassed = false;
    bool initialized = false;

    AuditLog audit;
    StateLock& stateLock;

    std::set<std::string> validTransitions(
        PipelineStage current
    ) const {
        switch (current) {
            case PipelineStage::Created:
                return {"validating", "failed"};

            case PipelineStage::Validating:
                return {"initialized", "failed"};

            case PipelineStage::Initialized:
                return {"planned", "failed"};

            case PipelineStage::Planned:
                return {"security_checked", "failed"};

            case PipelineStage::SecurityChecked:
                return {"awaiting_approval", "failed"};

            case PipelineStage::AwaitingApproval:
                return {"applying", "failed"};

            case PipelineStage::Applying:
                return {"succeeded", "failed"};

            default:
                return {};
        }
    }

    void transition(PipelineStage next) {
        auto allowed = validTransitions(stage);
        auto target = toString(next);

        if (!allowed.count(target)) {
            throw std::runtime_error(
                "Invalid pipeline state transition"
            );
        }

        stage = next;
        audit.record("Stage changed to " + target);
    }

    bool approvalsSatisfied() const {
        std::set<std::string> approved;
        std::set<std::string> rejected;

        for (const auto& review : reviews) {
            if (
                !review.reviewer.active ||
                !review.reviewer.authorized ||
                !policy.permittedReviewers.count(
                    review.reviewer.role
                )
            ) {
                continue;
            }

            if (review.decision == ReviewDecision::Approved) {
                approved.insert(review.reviewer.id);
            }

            if (review.decision == ReviewDecision::Rejected) {
                rejected.insert(review.reviewer.id);
            }
        }

        if (!rejected.empty()) {
            return false;
        }

        if (
            policy.requireIndependentReview &&
            approved.size() > 0
        ) {
            // A reviewer cannot approve their own change.
            // The requester identity is checked separately
            // when reviews are submitted.
        }

        return static_cast<int>(approved.size()) >=
            policy.requiredApprovals;
    }

public:
    TerraformGovernanceEngine(
        Environment environment,
        GovernancePolicy policy,
        StateLock& stateLock,
        TerraformPlan plan
    ) : environment(environment),
        policy(std::move(policy)),
        stateLock(stateLock),
        plan(std::move(plan)) {

        this->policy.validate();

        if (this->plan.id.empty()) {
            throw std::invalid_argument(
                "Plan identifier is required"
            );
        }

        if (this->plan.configurationHash.empty()) {
            throw std::invalid_argument(
                "Configuration hash is required"
            );
        }

        audit.record("Pipeline created: " + this->plan.id);
    }

    void addReview(
        const Reviewer& reviewer,
        ReviewDecision decision,
        const std::string& comment,
        const std::string& requester
    ) {
        if (!reviewer.active || !reviewer.authorized) {
            throw std::runtime_error(
                "Reviewer is inactive or unauthorized"
            );
        }

        if (
            !policy.permittedReviewers.count(reviewer.role)
        ) {
            throw std::runtime_error(
                "Reviewer role is not eligible"
            );
        }

        if (
            policy.requireIndependentReview &&
            reviewer.id == requester
        ) {
            throw std::runtime_error(
                "Self-approval is prohibited"
            );
        }

        auto duplicate = std::find_if(
            reviews.begin(),
            reviews.end(),
            [&reviewer](const Review& review) {
                return review.reviewer.id == reviewer.id;
            }
        );

        if (duplicate != reviews.end()) {
            throw std::runtime_error(
                "Reviewer has already submitted a decision"
            );
        }

        reviews.push_back({
            reviewer,
            decision,
            comment
        });

        audit.record(
            "Review submitted by " + reviewer.id
        );
    }

    void addStatusCheck(
        const std::string& name,
        CheckStatus status,
        const std::string& details
    ) {
        if (name.empty()) {
            throw std::invalid_argument(
                "Status check name is required"
            );
        }

        auto existing = std::find_if(
            checks.begin(),
            checks.end(),
            [&name](const StatusCheck& check) {
                return check.name == name;
            }
        );

        if (existing != checks.end()) {
            existing->status = status;
            existing->details = details;
        } else {
            checks.push_back({name, status, details});
        }

        audit.record("Status check updated: " + name);
    }

    void validateConfiguration() {
        transition(PipelineStage::Validating);

        if (plan.configurationHash.size() != 64) {
            throw std::runtime_error(
                "Expected SHA-256 configuration hash"
            );
        }

        for (const auto& change : plan.changes) {
            if (
                policy.requireEncryption &&
                !change.encrypted
            ) {
                throw std::runtime_error(
                    "Encryption policy violation: " +
                    change.resourceName
                );
            }

            if (
                policy.prohibitPublicIngress &&
                change.publicIngress
            ) {
                throw std::runtime_error(
                    "Public ingress prohibited: " +
                    change.resourceName
                );
            }

            if (
                policy.prohibitDestruction &&
                change.action == ChangeAction::Delete
            ) {
                throw std::runtime_error(
                    "Resource destruction prohibited"
                );
            }
        }

        configurationValid = true;
        audit.record("Configuration validation passed");
    }

    void initialize() {
        if (!configurationValid) {
            throw std::runtime_error(
                "Validation must complete first"
            );
        }

        transition(PipelineStage::Initialized);
        initialized = true;

        audit.record("Terraform initialization completed");
    }

    void generatePlan() {
        if (!initialized) {
            throw std::runtime_error(
                "Terraform must be initialized"
            );
        }

        transition(PipelineStage::Planned);

        audit.record(
            "Plan generated: additions=" +
            std::to_string(plan.count(ChangeAction::Create)) +
            ", updates=" +
            std::to_string(plan.count(ChangeAction::Update)) +
            ", deletions=" +
            std::to_string(plan.count(ChangeAction::Delete))
        );
    }

    void runSecurityChecks() {
        if (stage != PipelineStage::Planned) {
            throw std::runtime_error(
                "Plan generation must precede security scanning"
            );
        }

        if (policy.requireSecurityScan) {
            auto security = std::find_if(
                checks.begin(),
                checks.end(),
                [](const StatusCheck& check) {
                    return check.name == "security-scan";
                }
            );

            if (
                security == checks.end() ||
                security->status != CheckStatus::Passed
            ) {
                throw std::runtime_error(
                    "Security scan has not passed"
                );
            }
        }

        securityPassed = true;
        transition(PipelineStage::SecurityChecked);

        audit.record("Security evaluation passed");
    }

    bool mergeEligible() const {
        if (!configurationValid || !initialized) {
            return false;
        }

        if (!securityPassed) {
            return false;
        }

        if (!approvalsSatisfied()) {
            return false;
        }

        if (policy.requireSuccessfulChecks) {
            if (checks.empty()) {
                return false;
            }

            for (const auto& check : checks) {
                if (check.status != CheckStatus::Passed) {
                    return false;
                }
            }
        }

        return true;
    }

    void deploy() {
        if (stage != PipelineStage::SecurityChecked) {
            throw std::runtime_error(
                "Security checks must finish before approval"
            );
        }

        transition(PipelineStage::AwaitingApproval);

        if (!approvalsSatisfied()) {
            throw std::runtime_error(
                "Required approvals have not been received"
            );
        }

        if (!mergeEligible()) {
            throw std::runtime_error(
                "Infrastructure deployment is not eligible"
            );
        }

        transition(PipelineStage::Applying);

        stateLock.acquire(plan.id);

        try {
            audit.record(
                "Applying reviewed Terraform plan"
            );

            plan.applied = true;

            stateLock.release(plan.id);
        } catch (...) {
            stateLock.release(plan.id);
            throw;
        }

        transition(PipelineStage::Succeeded);

        audit.record("Infrastructure deployment succeeded");
    }

    void printReport() const {
        std::cout << "\nINFRASTRUCTURE PIPELINE REPORT\n";

        std::cout << "Environment: "
                  << toString(environment) << '\n';

        std::cout << "Plan ID: "
                  << plan.id << '\n';

        std::cout << "Stage: "
                  << toString(stage) << '\n';

        std::cout << "Additions: "
                  << plan.count(ChangeAction::Create) << '\n';

        std::cout << "Updates: "
                  << plan.count(ChangeAction::Update) << '\n';

        std::cout << "Deletions: "
                  << plan.count(ChangeAction::Delete) << '\n';

        std::cout << "Approvals satisfied: "
                  << (approvalsSatisfied() ? "YES" : "NO")
                  << '\n';

        std::cout << "Deployment eligible: "
                  << (mergeEligible() ? "YES" : "NO")
                  << '\n';

        std::cout << "Plan applied: "
                  << (plan.applied ? "YES" : "NO")
                  << '\n';

        std::cout << "\nAUDIT TRAIL\n";
        audit.print();
    }
};

int main() {
    try {
        GovernancePolicy policy;

        policy.requiredApprovals = 2;
        policy.requireSecurityScan = true;
        policy.requireSuccessfulChecks = true;
        policy.prohibitDestruction = true;
        policy.requireEncryption = true;
        policy.prohibitPublicIngress = true;

        TerraformPlan plan;

        plan.id = "plan-production-2026-001";
        plan.configurationHash =
            "a1234567890123456789012345678901"
            "a1234567890123456789012345678901";

        plan.changes = {
            {
                "aws_s3_bucket",
                "application_data",
                ChangeAction::Create,
                true,
                false
            },
            {
                "aws_security_group",
                "application_network",
                ChangeAction::Update,
                true,
                false
            },
            {
                "aws_db_instance",
                "application_database",
                ChangeAction::Update,
                true,
                false
            }
        };

        StateLock lock;

        TerraformGovernanceEngine engine(
            Environment::Production,
            policy,
            lock,
            plan
        );

        engine.addStatusCheck(
            "terraform-format",
            CheckStatus::Passed,
            "Formatting verified"
        );

        engine.addStatusCheck(
            "terraform-validation",
            CheckStatus::Passed,
            "Configuration valid"
        );

        engine.addStatusCheck(
            "security-scan",
            CheckStatus::Passed,
            "No critical findings"
        );

        engine.addStatusCheck(
            "policy-evaluation",
            CheckStatus::Passed,
            "Policies satisfied"
        );

        engine.validateConfiguration();
        engine.initialize();
        engine.generatePlan();
        engine.runSecurityChecks();

        Reviewer platform {
            "reviewer-101",
            "platform-lead",
            true,
            true
        };

        Reviewer security {
            "reviewer-102",
            "security-lead",
            true,
            true
        };

        engine.addReview(
            platform,
            ReviewDecision::Approved,
            "Infrastructure architecture verified",
            "developer-001"
        );

        engine.addReview(
            security,
            ReviewDecision::Approved,
            "Security controls verified",
            "developer-001"
        );

        engine.deploy();
        engine.printReport();

    } catch (const std::exception& error) {
        std::cerr << "PIPELINE ERROR: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}

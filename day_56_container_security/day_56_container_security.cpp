#include <algorithm>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class PullRequestState {
    Draft,
    Open,
    Closed,
    Merged
};

enum class ReviewState {
    Commented,
    Approved,
    ChangesRequested,
    Dismissed
};

enum class CheckState {
    Pending,
    Passed,
    Failed
};

enum class Severity {
    Low = 1,
    Medium = 2,
    High = 3,
    Critical = 4
};

struct Vulnerability {
    std::string package;
    Severity severity;
    std::string fixedVersion;
};

struct ContainerImage {
    std::string name;
    std::string user;
    std::vector<std::string> secrets;
    std::vector<Vulnerability> vulnerabilities;

    std::vector<std::string> securityFindings() const {
        std::vector<std::string> findings;

        if (user.empty() || user == "root" || user == "0") {
            findings.emplace_back("container runs as root");
        }

        if (!secrets.empty()) {
            std::string message = "secrets detected: ";
            for (std::size_t i = 0; i < secrets.size(); ++i) {
                if (i > 0) {
                    message += ", ";
                }
                message += secrets[i];
            }
            findings.push_back(message);
        }

        for (const auto& vulnerability : vulnerabilities) {
            if (vulnerability.severity == Severity::Critical) {
                findings.push_back(
                    "critical vulnerability in " + vulnerability.package
                );
            } else if (vulnerability.severity == Severity::High) {
                findings.push_back(
                    "high vulnerability in " + vulnerability.package
                );
            }
        }

        return findings;
    }
};

struct Review {
    std::string reviewer;
    ReviewState state;
    std::string commitSha;
};

struct StatusCheck {
    std::string name;
    CheckState state;
};

struct Commit {
    std::string sha;
    std::string message;
    std::string author;
};

struct PullRequest {
    int number{};
    std::string author;
    std::string sourceBranch;
    std::string targetBranch;
    std::string headSha;
    PullRequestState state{PullRequestState::Open};
    bool draft{false};
    bool mergeConflict{false};
    bool baseSynced{true};
    bool approvalsStale{false};
    int openConversations{0};
    std::vector<Commit> commits;
    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;
};

struct BranchProtection {
    int requiredApprovals{2};
    std::set<std::string> requiredChecks{
        "container-build",
        "container-vulnerability-scan",
        "container-secret-scan"
    };
    bool restrictDirectPush{true};
    bool restrictForcePush{true};
    bool restrictDeletion{true};
    bool requireResolvedConversations{true};
    bool requireLinearHistory{true};
    bool allowAdminBypass{false};
};

struct Repository {
    std::string name;
    std::set<std::string> users;
    std::set<std::string> branches;
    std::map<std::string, BranchProtection> protectionPolicies;
};

struct Evaluation {
    bool eligible{false};
    std::vector<std::string> reasons;
};

class GovernanceEngine {
public:
    explicit GovernanceEngine(const Repository& repository)
        : repository_(repository) {}

    Evaluation evaluate(
        const PullRequest& pr,
        const ContainerImage& image
    ) const {
        Evaluation result;

        if (!repository_.branches.count(pr.targetBranch)) {
            result.reasons.push_back("target branch does not exist");
            return result;
        }

        auto policyIt = repository_.protectionPolicies.find(pr.targetBranch);
        if (policyIt == repository_.protectionPolicies.end()) {
            result.reasons.push_back(
                "target branch has no branch-protection policy"
            );
            return result;
        }

        const BranchProtection& policy = policyIt->second;

        if (pr.state != PullRequestState::Open) {
            result.reasons.push_back("pull request is not open");
        }

        if (pr.draft) {
            result.reasons.push_back("pull request is a draft");
        }

        if (pr.mergeConflict) {
            result.reasons.push_back("merge conflicts must be resolved");
        }

        if (!pr.baseSynced) {
            result.reasons.push_back(
                "source branch is not synchronized with base"
            );
        }

        if (policy.requireResolvedConversations &&
            pr.openConversations > 0) {
            result.reasons.push_back(
                std::to_string(pr.openConversations) +
                " review conversations remain unresolved"
            );
        }

        if (pr.approvalsStale) {
            result.reasons.push_back("approvals are stale");
        }

        const int approvals = eligibleApprovals(pr);

        if (approvals < policy.requiredApprovals) {
            result.reasons.push_back(
                "required approvals: " +
                std::to_string(policy.requiredApprovals) +
                ", eligible approvals: " +
                std::to_string(approvals)
            );
        }

        for (const auto& requiredCheck : policy.requiredChecks) {
            auto check = std::find_if(
                pr.checks.begin(),
                pr.checks.end(),
                [&](const StatusCheck& candidate) {
                    return candidate.name == requiredCheck;
                }
            );

            if (check == pr.checks.end()) {
                result.reasons.push_back(
                    "missing required status check: " + requiredCheck
                );
            } else if (check->state != CheckState::Passed) {
                result.reasons.push_back(
                    "required status check failed: " + requiredCheck
                );
            }
        }

        const auto findings = image.securityFindings();

        for (const auto& finding : findings) {
            result.reasons.push_back(
                "container security: " + finding
            );
        }

        result.eligible = result.reasons.empty();
        return result;
    }

private:
    int eligibleApprovals(const PullRequest& pr) const {
        std::map<std::string, Review> latestReviews;

        for (const auto& review : pr.reviews) {
            latestReviews[review.reviewer] = review;
        }

        std::set<std::string> eligibleReviewers;

        for (const auto& [reviewer, review] : latestReviews) {
            if (review.state != ReviewState::Approved) {
                continue;
            }

            if (reviewer == pr.author) {
                continue;
            }

            if (!repository_.users.count(reviewer)) {
                continue;
            }

            if (review.commitSha != pr.headSha) {
                continue;
            }

            eligibleReviewers.insert(reviewer);
        }

        return static_cast<int>(eligibleReviewers.size());
    }

    const Repository& repository_;
};

std::string severityName(Severity severity) {
    switch (severity) {
        case Severity::Low:
            return "low";
        case Severity::Medium:
            return "medium";
        case Severity::High:
            return "high";
        case Severity::Critical:
            return "critical";
    }

    throw std::invalid_argument("unknown severity");
}

void printEvaluation(
    const std::string& title,
    const Evaluation& evaluation
) {
    std::cout << "\n=== " << title << " ===\n";
    std::cout << "merge eligible: "
              << std::boolalpha
              << evaluation.eligible
              << '\n';

    if (evaluation.reasons.empty()) {
        std::cout
            << "  - all governance and container-security controls passed\n";
        return;
    }

    for (const auto& reason : evaluation.reasons) {
        std::cout << "  - " << reason << '\n';
    }
}

void validateImage(const ContainerImage& image) {
    if (image.name.empty()) {
        throw std::invalid_argument("image name cannot be empty");
    }

    if (image.user.empty()) {
        throw std::invalid_argument(
            "container user must be explicitly declared"
        );
    }

    for (const auto& vulnerability : image.vulnerabilities) {
        if (vulnerability.package.empty()) {
            throw std::invalid_argument(
                "vulnerability package cannot be empty"
            );
        }

        if (vulnerability.fixedVersion.empty() &&
            (vulnerability.severity == Severity::Critical ||
             vulnerability.severity == Severity::High)) {
            throw std::invalid_argument(
                "high and critical findings require remediation metadata"
            );
        }
    }
}

int main() {
    try {
        Repository repository{
            "payments-service",
            {"alice", "bob", "carol"},
            {"main", "feature/container-hardening"},
            {
                {
                    "main",
                    BranchProtection{
                        2,
                        {
                            "container-build",
                            "container-vulnerability-scan",
                            "container-secret-scan"
                        },
                        true,
                        true,
                        true,
                        true,
                        true,
                        false
                    }
                }
            }
        };

        PullRequest pr;
        pr.number = 91;
        pr.author = "alice";
        pr.sourceBranch = "feature/container-hardening";
        pr.targetBranch = "main";
        pr.headSha = "a91f42c7";
        pr.commits.push_back({
            "a91f42c7",
            "Harden production container",
            "alice"
        });

        pr.checks = {
            {"container-build", CheckState::Passed},
            {"container-vulnerability-scan", CheckState::Passed},
            {"container-secret-scan", CheckState::Passed}
        };

        pr.reviews = {
            {"bob", ReviewState::Approved, "a91f42c7"},
            {"carol", ReviewState::Approved, "a91f42c7"}
        };

        ContainerImage secureImage{
            "payments:91",
            "10001",
            {},
            {
                {"openssl", Severity::Medium, "3.2.1"}
            }
        };

        validateImage(secureImage);

        GovernanceEngine engine(repository);

        auto secureResult = engine.evaluate(pr, secureImage);
        printEvaluation("secure image", secureResult);

        ContainerImage insecureImage{
            "payments:91",
            "root",
            {"DATABASE_PASSWORD"},
            {
                {"openssl", Severity::Critical, "3.2.1"},
                {"curl", Severity::High, "8.10.0"}
            }
        };

        validateImage(insecureImage);

        auto insecureResult = engine.evaluate(pr, insecureImage);
        printEvaluation("insecure image", insecureResult);

        if (!secureResult.eligible) {
            throw std::runtime_error(
                "secure image should have been merge eligible"
            );
        }

        if (insecureResult.eligible) {
            throw std::runtime_error(
                "insecure image must not be merge eligible"
            );
        }

        std::cout
            << "\nSecurity decision model:\n"
            << "Pull Request -> Reviews -> Approvals -> Status Checks -> "
               "Container Security -> Branch Protection -> Merge Eligibility\n";

        std::cout
            << "\nDesign trade-off: repository governance is evaluated in "
               "memory for deterministic policy decisions, while the "
               "database implementation persists the same entities and "
               "constraints for durable enforcement and auditability.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fatal error: " << error.what() << '\n';
        return 1;
    }
}

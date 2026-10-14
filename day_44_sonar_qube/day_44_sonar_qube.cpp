#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Repository governance case study:
 * A C++ quality-gate engine evaluates a proposed payment-service change.
 *
 * Build:
 *   g++ -std=c++17 -Wall -Wextra -pedantic quality_governance.cpp -o quality_governance
 *
 * This is a deterministic policy simulation, not the SonarQube analyzer.
 */

enum class IssueKind {
    Bug,
    Vulnerability,
    CodeSmell,
    SecurityHotspot
};

enum class Severity {
    Blocker,
    Critical,
    Major,
    Minor,
    Info
};

enum class GateStatus {
    Passed,
    Failed,
    MissingAnalysis
};

enum class ReviewState {
    NotReviewed,
    ChangesRequested,
    Approved,
    Dismissed
};

struct Finding {
    std::string key;
    std::string file;
    std::string rule;
    std::string message;
    IssueKind kind;
    Severity severity;
    int remediationMinutes;
    bool introducedByChange;
    bool resolved;
    bool hotspotReviewed;
};

struct SourceMetrics {
    int totalLines = 0;
    int coveredLines = 0;
    int duplicatedLines = 0;
    int newLines = 0;
    int newCoveredLines = 0;
    int newDuplicatedLines = 0;

    static double percentage(int numerator, int denominator) {
        return denominator == 0
            ? 0.0
            : 100.0 * static_cast<double>(numerator) / denominator;
    }

    void validate() const {
        if (totalLines < 0 || coveredLines < 0 || duplicatedLines < 0 ||
            newLines < 0 || newCoveredLines < 0 || newDuplicatedLines < 0) {
            throw std::invalid_argument("Source metrics cannot be negative.");
        }
        if (coveredLines > totalLines || duplicatedLines > totalLines ||
            newCoveredLines > newLines || newDuplicatedLines > newLines) {
            throw std::invalid_argument("Source metrics exceed their denominators.");
        }
    }
};

struct Review {
    std::string reviewer;
    ReviewState state;
    std::string commitReviewed;
    bool eligible;
};

struct PullRequest {
    std::string id;
    std::string sourceBranch;
    std::string targetBranch;
    std::string headCommit;
    std::string analyzedCommit;
    bool open;
    bool draft;
    bool conversationsResolved;
    bool conflicts;
    std::vector<Review> reviews;
    std::map<std::string, bool> checks;
};

struct BranchProtection {
    std::string branch;
    int requiredApprovals;
    bool requireCodeOwnerApproval;
    bool requireLinearHistory;
    bool disallowDirectPush;
    bool disallowForcePush;
    bool disallowDeletion;
    bool requireResolvedConversations;
    bool allowAdministratorBypass;
    std::vector<std::string> requiredChecks;
};

struct QualityGate {
    double minimumNewCoverage;
    double maximumNewDuplication;
    int maximumNewBugs;
    int maximumNewVulnerabilities;
    int maximumNewBlockers;
    int maximumNewDebtMinutes;
    bool requireReviewedHotspots;
};

struct Metrics {
    double overallCoverage = 0.0;
    double newCoverage = 0.0;
    double overallDuplication = 0.0;
    double newDuplication = 0.0;
    int newBugs = 0;
    int newVulnerabilities = 0;
    int newBlockers = 0;
    int newDebtMinutes = 0;
    int activeIssues = 0;
    int unreviewedHotspots = 0;
};

std::string toString(IssueKind kind) {
    switch (kind) {
        case IssueKind::Bug: return "BUG";
        case IssueKind::Vulnerability: return "VULNERABILITY";
        case IssueKind::CodeSmell: return "CODE_SMELL";
        case IssueKind::SecurityHotspot: return "SECURITY_HOTSPOT";
    }
    throw std::logic_error("Unknown issue kind.");
}

std::string toString(Severity severity) {
    switch (severity) {
        case Severity::Blocker: return "BLOCKER";
        case Severity::Critical: return "CRITICAL";
        case Severity::Major: return "MAJOR";
        case Severity::Minor: return "MINOR";
        case Severity::Info: return "INFO";
    }
    throw std::logic_error("Unknown severity.");
}

Metrics calculateMetrics(const SourceMetrics& source,
                         const std::vector<Finding>& findings) {
    source.validate();
    Metrics result;
    result.overallCoverage = SourceMetrics::percentage(
        source.coveredLines, source.totalLines);
    result.newCoverage = SourceMetrics::percentage(
        source.newCoveredLines, source.newLines);
    result.overallDuplication = SourceMetrics::percentage(
        source.duplicatedLines, source.totalLines);
    result.newDuplication = SourceMetrics::percentage(
        source.newDuplicatedLines, source.newLines);

    for (const auto& finding : findings) {
        if (finding.remediationMinutes < 0) {
            throw std::invalid_argument("Finding effort cannot be negative.");
        }
        if (finding.resolved) {
            continue;
        }

        ++result.activeIssues;
        if (finding.kind == IssueKind::SecurityHotspot &&
            !finding.hotspotReviewed) {
            ++result.unreviewedHotspots;
        }

        // New-code metrics must not silently count existing technical debt.
        if (!finding.introducedByChange) {
            continue;
        }

        result.newDebtMinutes += finding.remediationMinutes;
        if (finding.kind == IssueKind::Bug) {
            ++result.newBugs;
        } else if (finding.kind == IssueKind::Vulnerability) {
            ++result.newVulnerabilities;
        }
        if (finding.severity == Severity::Blocker) {
            ++result.newBlockers;
        }
    }
    return result;
}

struct GateDecision {
    GateStatus status;
    std::vector<std::string> failures;
};

GateDecision evaluateQualityGate(const QualityGate& gate,
                                 const Metrics& metrics) {
    GateDecision result{GateStatus::Passed, {}};

    auto fail = [&](const std::string& reason) {
        result.failures.push_back(reason);
    };

    if (metrics.newCoverage < gate.minimumNewCoverage) {
        fail("New-code coverage is below the configured minimum.");
    }
    if (metrics.newDuplication > gate.maximumNewDuplication) {
        fail("New-code duplication exceeds the configured maximum.");
    }
    if (metrics.newBugs > gate.maximumNewBugs) {
        fail("The change introduces too many bugs.");
    }
    if (metrics.newVulnerabilities > gate.maximumNewVulnerabilities) {
        fail("The change introduces a security vulnerability.");
    }
    if (metrics.newBlockers > gate.maximumNewBlockers) {
        fail("The change introduces a blocker issue.");
    }
    if (metrics.newDebtMinutes > gate.maximumNewDebtMinutes) {
        fail("New technical debt exceeds the remediation budget.");
    }
    if (gate.requireReviewedHotspots && metrics.unreviewedHotspots > 0) {
        fail("At least one active security hotspot remains unreviewed.");
    }

    if (!result.failures.empty()) {
        result.status = GateStatus::Failed;
    }
    return result;
}

struct MergeDecision {
    bool allowed;
    std::vector<std::string> blockers;
};

MergeDecision evaluateMergeEligibility(
    const PullRequest& request,
    const BranchProtection& protection,
    const GateDecision& gate,
    const std::string& currentBaseCommit
) {
    MergeDecision result{true, {}};
    auto reject = [&](const std::string& reason) {
        result.allowed = false;
        result.blockers.push_back(reason);
    };

    if (!request.open) reject("Pull request is closed.");
    if (request.draft) reject("Draft pull requests cannot be merged.");
    if (request.sourceBranch.empty() || request.targetBranch.empty() ||
        request.sourceBranch == request.targetBranch) {
        reject("Source and target branches must be distinct and non-empty.");
    }
    if (request.targetBranch != protection.branch) {
        reject("The supplied branch policy does not protect the pull request target.");
    }
    if (request.conflicts) reject("Merge conflicts must be resolved.");

    // A green gate belongs to the exact commit analyzed, not a later source revision.
    if (request.headCommit.empty() ||
        request.headCommit != request.analyzedCommit) {
        reject("The source commit changed after analysis; rerun CI and analysis.");
    }
    if (currentBaseCommit.empty()) {
        reject("The current base commit is unavailable.");
    }

    if (gate.status != GateStatus::Passed) {
        reject("Quality gate has not passed.");
    }

    int validApprovals = 0;
    bool ownerApproved = false;
    for (const auto& review : request.reviews) {
        // Approval on an old commit is stale and cannot satisfy this policy.
        if (!review.eligible ||
            review.commitReviewed != request.headCommit ||
            review.state != ReviewState::Approved) {
            continue;
        }
        ++validApprovals;
        ownerApproved = ownerApproved || review.reviewer == "code-owner";
    }

    if (validApprovals < protection.requiredApprovals) {
        reject("Insufficient eligible, non-stale approvals.");
    }
    if (protection.requireCodeOwnerApproval && !ownerApproved) {
        reject("A code-owner approval is required.");
    }
    if (protection.requireResolvedConversations &&
        !request.conversationsResolved) {
        reject("Review conversations remain unresolved.");
    }

    for (const auto& required : protection.requiredChecks) {
        const auto found = request.checks.find(required);
        if (found == request.checks.end() || !found->second) {
            reject("Required status check is missing or failing: " + required);
        }
    }

    if (protection.disallowDirectPush && request.sourceBranch.empty()) {
        reject("Direct updates are prohibited by branch protection.");
    }

    if (!result.blockers.empty()) {
        result.allowed = false;
    }
    return result;
}

void printGateReport(const Metrics& metrics, const GateDecision& decision) {
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "\nQuality metrics\n"
              << "  Overall coverage:       " << metrics.overallCoverage << "%\n"
              << "  New-code coverage:      " << metrics.newCoverage << "%\n"
              << "  Overall duplication:    " << metrics.overallDuplication << "%\n"
              << "  New-code duplication:   " << metrics.newDuplication << "%\n"
              << "  New bugs:               " << metrics.newBugs << "\n"
              << "  New vulnerabilities:    " << metrics.newVulnerabilities << "\n"
              << "  New blocker issues:     " << metrics.newBlockers << "\n"
              << "  New debt:               " << metrics.newDebtMinutes << " minutes\n"
              << "  Unreviewed hotspots:    " << metrics.unreviewedHotspots << "\n"
              << "  Gate: "
              << (decision.status == GateStatus::Passed ? "PASSED" : "FAILED")
              << "\n";

    for (const auto& failure : decision.failures) {
        std::cout << "  BLOCK: " << failure << "\n";
    }
}

int main() {
    try {
        const SourceMetrics source{
            4200, 3500, 126, 100, 72, 2
        };

        const std::vector<Finding> findings{
            {
                "PAY-201", "src/payment_repository.cpp", "cpp:S3649",
                "Unsafe construction of a payment lookup query.",
                IssueKind::Vulnerability, Severity::Critical, 90,
                true, false, true
            },
            {
                "PAY-202", "src/payment_service.cpp", "cpp:S3776",
                "Authorization function has excessive complexity.",
                IssueKind::CodeSmell, Severity::Major, 45,
                true, false, true
            },
            {
                "PAY-203", "src/legacy_adapter.cpp", "cpp:S1481",
                "Unused variable in a legacy adapter.",
                IssueKind::CodeSmell, Severity::Minor, 15,
                false, false, true
            },
            {
                "PAY-204", "src/crypto_adapter.cpp", "cpp:S4787",
                "Cryptographic construction needs expert review.",
                IssueKind::SecurityHotspot, Severity::Major, 30,
                false, false, false
            }
        };

        const QualityGate gate{
            80.0, 3.0, 0, 0, 0, 60, true
        };

        const Metrics metrics = calculateMetrics(source, findings);
        const GateDecision gateDecision = evaluateQualityGate(gate, metrics);
        printGateReport(metrics, gateDecision);

        const BranchProtection protection{
            "main",
            2,
            true,
            true,
            true,
            true,
            true,
            true,
            false,
            {"build-linux", "unit-tests", "dependency-audit"}
        };

        PullRequest request{
            "PR-284",
            "feature/safe-payment-query",
            "main",
            "commit-c7f91ad",
            "commit-c7f91ad",
            true,
            false,
            true,
            false,
            {
                {"reviewer-alex", ReviewState::Approved, "commit-c7f91ad", true},
                {"code-owner", ReviewState::Approved, "commit-c7f91ad", true}
            },
            {
                {"build-linux", true},
                {"unit-tests", true},
                {"dependency-audit", true}
            }
        };

        const auto decision = evaluateMergeEligibility(
            request, protection, gateDecision, "base-90b31"
        );

        std::cout << "\nMerge eligibility for " << request.id << "\n";
        std::cout << "  " << (decision.allowed ? "ELIGIBLE" : "BLOCKED") << "\n";
        for (const auto& reason : decision.blockers) {
            std::cout << "  BLOCK: " << reason << "\n";
        }

        // Demonstrate stale approval and stale-analysis protection.
        PullRequest stale = request;
        stale.headCommit = "commit-newer";
        const auto staleDecision = evaluateMergeEligibility(
            stale, protection, gateDecision, "base-90b31"
        );
        std::cout << "\nAfter a source commit changes:\n";
        for (const auto& reason : staleDecision.blockers) {
            std::cout << "  BLOCK: " << reason << "\n";
        }

        // A quality gate is one independent control, not a substitute for review.
        PullRequest missingCheck = request;
        missingCheck.checks["dependency-audit"] = false;
        const auto checkDecision = evaluateMergeEligibility(
            missingCheck, protection, gateDecision, "base-90b31"
        );
        std::cout << "\nWith dependency audit failing:\n";
        for (const auto& reason : checkDecision.blockers) {
            std::cout << "  BLOCK: " << reason << "\n";
        }

        SourceMetrics invalid{10, 11, 0, 2, 1, 0};
        bool rejectedInvalidMetrics = false;
        try {
            invalid.validate();
        } catch (const std::invalid_argument&) {
            rejectedInvalidMetrics = true;
        }
        if (!rejectedInvalidMetrics) {
            throw std::logic_error("Invalid source metrics were accepted.");
        }

        std::cout << "\nInvalid metric validation: passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Governance engine error: " << error.what() << '\n';
        return 1;
    }
}

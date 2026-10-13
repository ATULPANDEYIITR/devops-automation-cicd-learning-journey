#include <algorithm>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Repository Governance and Code Quality Gate
 *
 * C++17 case study:
 * A team proposes a change to a protected release branch. The repository
 * governance engine evaluates code quality evidence, reviewer decisions,
 * unresolved discussions, and branch policy before allowing a merge.
 *
 * Build:
 *   g++ -std=c++17 -Wall -Wextra -Wpedantic -O2 governance.cpp -o governance
 *
 * This program models policy evaluation; it does not contact GitHub or
 * replace a production C++ linter or static analyzer.
 */

enum class Severity {
    Info,
    Warning,
    Error
};

enum class ReviewState {
    Pending,
    Approved,
    ChangesRequested,
    Dismissed
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};

struct Finding {
    std::string rule;
    Severity severity;
    std::string message;
    std::size_t line;
};

struct QualityEvidence {
    bool lintPassed = false;
    bool formatPassed = false;
    bool staticAnalysisPassed = false;
    bool testsPassed = false;
    bool branchUpToDate = false;
    bool hasConflicts = false;
    bool isDraft = true;
    std::size_t unresolvedThreads = 0;
};

struct Reviewer {
    std::string login;
    bool active = true;
    bool canReviewCode = true;
    bool isAuthor = false;
    bool isBot = false;
};

struct Review {
    std::string reviewer;
    ReviewState state = ReviewState::Pending;
    std::string commitSha;
    std::string comment;
};

struct BranchPolicy {
    std::string branchName = "main";
    bool protectedBranch = true;
    bool requireLint = true;
    bool requireFormat = true;
    bool requireStaticAnalysis = true;
    bool requireTests = true;
    bool requireUpToDateBranch = true;
    bool requireLinearHistory = true;
    bool allowDirectPushes = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool allowAdministratorBypass = false;
    bool dismissStaleApprovals = true;
    std::size_t requiredApprovals = 2;
    std::size_t requiredStatusChecks = 4;
};

struct PullRequest {
    unsigned number = 0;
    std::string title;
    std::string author;
    std::string baseBranch;
    std::string headBranch;
    std::string headCommit;
    bool open = true;
    bool draft = false;
    QualityEvidence evidence;
    std::vector<Review> reviews;
};

struct GateResult {
    bool eligible = false;
    std::vector<std::string> blockers;
    std::size_t validApprovals = 0;
    std::size_t passingChecks = 0;
};

class Repository {
public:
    explicit Repository(BranchPolicy policy) : policy_(std::move(policy)) {
        if (policy_.branchName.empty()) {
            throw std::invalid_argument("Protected branch name cannot be empty.");
        }
        if (policy_.requiredStatusChecks > 100) {
            throw std::invalid_argument("Status check policy is unreasonable.");
        }
    }

    void registerReviewer(Reviewer reviewer) {
        if (reviewer.login.empty()) {
            throw std::invalid_argument("Reviewer login cannot be empty.");
        }
        reviewers_[reviewer.login] = std::move(reviewer);
    }

    void addPullRequest(PullRequest request) {
        if (request.number == 0) {
            throw std::invalid_argument("Pull request number must be positive.");
        }
        if (request.author.empty() || request.headBranch.empty()) {
            throw std::invalid_argument(
                "Pull request author and source branch are required."
            );
        }
        if (request.baseBranch != policy_.branchName) {
            throw std::invalid_argument(
                "This repository model accepts requests targeting its "
                "configured protected branch."
            );
        }
        if (requests_.count(request.number) != 0) {
            throw std::invalid_argument("Duplicate pull request number.");
        }
        requests_.emplace(request.number, std::move(request));
    }

    void submitReview(unsigned number, Review review) {
        PullRequest& request = findRequest(number);
        if (!request.open) {
            throw std::logic_error("Cannot review a closed pull request.");
        }

        const auto reviewer = reviewers_.find(review.reviewer);
        if (reviewer == reviewers_.end()) {
            throw std::invalid_argument("Reviewer is not registered.");
        }
        if (!reviewer->second.active || !reviewer->second.canReviewCode ||
            reviewer->second.isBot || reviewer->second.isAuthor ||
            reviewer->second.login == request.author) {
            throw std::invalid_argument(
                "Reviewer is not eligible to review this pull request."
            );
        }
        if (review.commitSha.empty()) {
            throw std::invalid_argument("Review must identify the reviewed commit.");
        }

        // A new review from the same reviewer replaces the previous current
        // decision, matching the idea of a reviewer updating their assessment.
        auto existing = std::find_if(
            request.reviews.begin(),
            request.reviews.end(),
            [&](const Review& candidate) {
                return candidate.reviewer == review.reviewer;
            }
        );

        if (existing == request.reviews.end()) {
            request.reviews.push_back(std::move(review));
        } else {
            *existing = std::move(review);
        }
    }

    void updateEvidence(unsigned number, QualityEvidence evidence) {
        findRequest(number).evidence = evidence;
    }

    void updateHeadCommit(unsigned number, std::string newSha) {
        if (newSha.empty()) {
            throw std::invalid_argument("Commit SHA cannot be empty.");
        }
        PullRequest& request = findRequest(number);
        request.headCommit = std::move(newSha);

        // When policy dismisses stale approvals, approvals on the old commit
        // no longer count until the reviewers reassess the new changeset.
        if (policy_.dismissStaleApprovals) {
            for (Review& review : request.reviews) {
                if (review.commitSha != request.headCommit &&
                    review.state == ReviewState::Approved) {
                    review.state = ReviewState::Dismissed;
                }
            }
        }
    }

    GateResult evaluate(unsigned number, MergeStrategy strategy) const {
        const PullRequest& request = findRequestConst(number);
        GateResult result;

        if (!request.open) {
            result.blockers.push_back("Pull request is closed.");
        }
        if (request.draft || request.evidence.isDraft) {
            result.blockers.push_back("Draft pull request is not mergeable.");
        }
        if (!policy_.protectedBranch) {
            result.blockers.push_back("Configured protected branch is not protected.");
        }
        if (request.headCommit.empty()) {
            result.blockers.push_back("Source commit is missing.");
        }
        if (request.evidence.hasConflicts) {
            result.blockers.push_back("Merge conflicts must be resolved.");
        }
        if (policy_.requireUpToDateBranch &&
            !request.evidence.branchUpToDate) {
            result.blockers.push_back(
                "Source branch must be synchronized with the base branch."
            );
        }

        if (policy_.requireLint && !request.evidence.lintPassed) {
            result.blockers.push_back("Required lint check failed.");
        }
        if (policy_.requireFormat && !request.evidence.formatPassed) {
            result.blockers.push_back("Formatting check failed.");
        }
        if (policy_.requireStaticAnalysis &&
            !request.evidence.staticAnalysisPassed) {
            result.blockers.push_back("Static analysis check failed.");
        }
        if (policy_.requireTests && !request.evidence.testsPassed) {
            result.blockers.push_back("Automated tests failed.");
        }

        if (request.evidence.unresolvedThreads > 0) {
            result.blockers.push_back(
                std::to_string(request.evidence.unresolvedThreads) +
                " review discussion(s) remain unresolved."
            );
        }

        if (policy_.requireLinearHistory &&
            strategy == MergeStrategy::MergeCommit) {
            result.blockers.push_back(
                "Merge commits violate the configured linear-history policy."
            );
        }

        std::set<std::string> countedReviewers;
        for (const Review& review : request.reviews) {
            const auto reviewer = reviewers_.find(review.reviewer);
            if (reviewer == reviewers_.end()) {
                continue;
            }

            const Reviewer& identity = reviewer->second;
            const bool eligible =
                identity.active &&
                identity.canReviewCode &&
                !identity.isAuthor &&
                !identity.isBot &&
                identity.login != request.author;

            if (!eligible) {
                continue;
            }

            if (review.state == ReviewState::ChangesRequested &&
                review.commitSha == request.headCommit) {
                result.blockers.push_back(
                    "Changes requested by " + review.reviewer + "."
                );
            }

            const bool currentApproval =
                review.state == ReviewState::Approved &&
                (!policy_.dismissStaleApprovals ||
                 review.commitSha == request.headCommit);

            if (currentApproval &&
                countedReviewers.insert(review.reviewer).second) {
                ++result.validApprovals;
            }
        }

        if (result.validApprovals < policy_.requiredApprovals) {
            result.blockers.push_back(
                "Insufficient current approvals: " +
                std::to_string(result.validApprovals) + "/" +
                std::to_string(policy_.requiredApprovals) + "."
            );
        }

        result.passingChecks =
            static_cast<std::size_t>(request.evidence.lintPassed) +
            static_cast<std::size_t>(request.evidence.formatPassed) +
            static_cast<std::size_t>(request.evidence.staticAnalysisPassed) +
            static_cast<std::size_t>(request.evidence.testsPassed);

        if (result.passingChecks < policy_.requiredStatusChecks) {
            result.blockers.push_back(
                "Required status-check count not met: " +
                std::to_string(result.passingChecks) + "/" +
                std::to_string(policy_.requiredStatusChecks) + "."
            );
        }

        result.eligible = result.blockers.empty();
        return result;
    }

    bool merge(unsigned number, MergeStrategy strategy) {
        PullRequest& request = findRequest(number);
        const GateResult result = evaluate(number, strategy);

        if (!result.eligible) {
            return false;
        }

        request.open = false;
        return true;
    }

    bool canDirectPush(bool administrator) const {
        if (policy_.allowDirectPushes) {
            return true;
        }
        return administrator && policy_.allowAdministratorBypass;
    }

    bool canForcePush(bool administrator) const {
        if (policy_.allowForcePush) {
            return true;
        }
        return administrator && policy_.allowAdministratorBypass;
    }

    bool canDeleteBranch(bool administrator) const {
        if (policy_.allowDeletion) {
            return true;
        }
        return administrator && policy_.allowAdministratorBypass;
    }

private:
    BranchPolicy policy_;
    std::map<std::string, Reviewer> reviewers_;
    std::map<unsigned, PullRequest> requests_;

    PullRequest& findRequest(unsigned number) {
        const auto found = requests_.find(number);
        if (found == requests_.end()) {
            throw std::out_of_range("Pull request does not exist.");
        }
        return found->second;
    }

    const PullRequest& findRequestConst(unsigned number) const {
        const auto found = requests_.find(number);
        if (found == requests_.end()) {
            throw std::out_of_range("Pull request does not exist.");
        }
        return found->second;
    }
};

std::string strategyName(MergeStrategy strategy) {
    switch (strategy) {
        case MergeStrategy::MergeCommit:
            return "merge commit";
        case MergeStrategy::Squash:
            return "squash";
        case MergeStrategy::Rebase:
            return "rebase";
    }
    throw std::logic_error("Unknown merge strategy.");
}

void printGateResult(
    const std::string& title,
    const GateResult& result
) {
    std::cout << "\n" << title << '\n';
    std::cout << "Eligible: " << std::boolalpha << result.eligible << '\n';
    std::cout << "Current approvals: " << result.validApprovals << '\n';
    std::cout << "Passing checks: " << result.passingChecks << '\n';

    if (result.blockers.empty()) {
        std::cout << "No policy blockers.\n";
    } else {
        for (const auto& blocker : result.blockers) {
            std::cout << "BLOCKED: " << blocker << '\n';
        }
    }
}

int main() {
    try {
        BranchPolicy policy;
        policy.requiredApprovals = 2;
        policy.requiredStatusChecks = 4;
        policy.requireLinearHistory = true;
        policy.allowDirectPushes = false;
        policy.allowForcePush = false;
        policy.allowDeletion = false;
        policy.allowAdministratorBypass = false;

        Repository repository(policy);

        repository.registerReviewer(
            Reviewer{"reviewer-alex", true, true, false, false}
        );
        repository.registerReviewer(
            Reviewer{"reviewer-morgan", true, true, false, false}
        );
        repository.registerReviewer(
            Reviewer{"release-bot", true, true, false, true}
        );
        repository.registerReviewer(
            Reviewer{"developer-jamie", true, true, true, false}
        );

        PullRequest request;
        request.number = 84;
        request.title = "Enforce static analysis on release changes";
        request.author = "developer-jamie";
        request.baseBranch = "main";
        request.headBranch = "feature/static-analysis-gate";
        request.headCommit = "a84c0ffee";
        request.open = true;
        request.draft = false;
        request.evidence = QualityEvidence{
            true, true, false, true, true, false, false, 0
        };

        repository.addPullRequest(request);

        repository.submitReview(
            84,
            Review{
                "reviewer-alex",
                ReviewState::Approved,
                "a84c0ffee",
                "Policy boundary conditions are covered."
            }
        );

        repository.submitReview(
            84,
            Review{
                "reviewer-morgan",
                ReviewState::Approved,
                "a84c0ffee",
                "The quality gate is clear."
            }
        );

        GateResult first = repository.evaluate(
            84,
            MergeStrategy::Squash
        );
        printGateResult("Initial evaluation", first);

        QualityEvidence corrected{
            true, true, true, true, true, false, false, 0
        };
        repository.updateEvidence(84, corrected);

        // A new commit invalidates approvals under this branch policy.
        repository.updateHeadCommit(84, "b84c0ffee");

        GateResult afterPush = repository.evaluate(
            84,
            MergeStrategy::Squash
        );
        printGateResult("After a new commit", afterPush);

        repository.submitReview(
            84,
            Review{
                "reviewer-alex",
                ReviewState::Approved,
                "b84c0ffee",
                "Rechecked the latest changes."
            }
        );
        repository.submitReview(
            84,
            Review{
                "reviewer-morgan",
                ReviewState::Approved,
                "b84c0ffee",
                "The revised changes are acceptable."
            }
        );

        GateResult finalResult = repository.evaluate(
            84,
            MergeStrategy::Squash
        );
        printGateResult("Final evaluation", finalResult);

        std::cout << "\nMerge strategy: "
                  << strategyName(MergeStrategy::Squash) << '\n';
        std::cout << "Direct push permitted: "
                  << repository.canDirectPush(false) << '\n';
        std::cout << "Force push permitted: "
                  << repository.canForcePush(false) << '\n';
        std::cout << "Branch deletion permitted: "
                  << repository.canDeleteBranch(false) << '\n';

        if (repository.merge(84, MergeStrategy::Squash)) {
            std::cout << "Pull request merged successfully.\n";
        } else {
            std::cout << "Pull request remains open.\n";
            return 1;
        }

        // A stale review cannot be treated as approval for the new commit.
        try {
            repository.submitReview(
                84,
                Review{
                    "reviewer-alex",
                    ReviewState::Approved,
                    "",
                    "Missing commit identity"
                }
            );
        } catch (const std::exception& error) {
            std::cout << "Validation correctly rejected review: "
                      << error.what() << '\n';
        }

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Governance engine error: "
                  << error.what() << '\n';
        return 2;
    }
}

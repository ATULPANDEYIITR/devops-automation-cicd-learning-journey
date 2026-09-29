/*
 * Pull Requests, Code Review, Approvals, and Branch Protection
 * ==============================================================
 *
 * C++17 industry-style case study:
 *
 * A small payment-service repository is modeled with:
 *   - branches and commits
 *   - pull requests
 *   - code reviews
 *   - approval requirements
 *   - status checks
 *   - code ownership
 *   - unresolved review conversations
 *   - stale approvals
 *   - branch freshness
 *   - security findings
 *   - merge-policy evaluation
 *   - merge strategies
 *   - audit logging
 *
 * Build:
 *     g++ -std=c++17 -Wall -Wextra -pedantic pull_requests.cpp -o pull_requests
 *
 * Run:
 *     ./pull_requests
 */

#include <algorithm>
#include <chrono>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

// ============================================================================
// 1. ENUMERATIONS
// ============================================================================

enum class ReviewState {
    Approved,
    ChangesRequested,
    Commented,
    Dismissed
};

enum class CheckState {
    Passed,
    Failed,
    Pending
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};

std::string toString(ReviewState state) {
    switch (state) {
        case ReviewState::Approved:
            return "approved";
        case ReviewState::ChangesRequested:
            return "changes requested";
        case ReviewState::Commented:
            return "commented";
        case ReviewState::Dismissed:
            return "dismissed";
    }

    return "unknown";
}

std::string toString(CheckState state) {
    switch (state) {
        case CheckState::Passed:
            return "passed";
        case CheckState::Failed:
            return "failed";
        case CheckState::Pending:
            return "pending";
    }

    return "unknown";
}

std::string toString(MergeStrategy strategy) {
    switch (strategy) {
        case MergeStrategy::MergeCommit:
            return "merge commit";
        case MergeStrategy::Squash:
            return "squash";
        case MergeStrategy::Rebase:
            return "rebase";
    }

    return "unknown";
}

// ============================================================================
// 2. BASIC REPOSITORY OBJECTS
// ============================================================================

struct Commit {
    std::string id;
    std::string author;
    std::string message;
    std::map<std::string, std::string> files;
    bool signedCommit{false};

    static Commit create(
        const std::string& author,
        const std::string& message,
        const std::map<std::string, std::string>& files,
        bool signedCommit = false
    ) {
        /*
         * This is an educational commit ID. It is intentionally not an
         * implementation of Git's actual object hashing format.
         */
        std::ostringstream input;
        input << author << '\n' << message << '\n';

        for (const auto& [filename, content] : files) {
            input << filename << '\n' << content << '\n';
        }

        const std::string serialized = input.str();
        const std::size_t hashValue = std::hash<std::string>{}(serialized);

        std::ostringstream idStream;
        idStream << std::hex << hashValue;

        return Commit{
            idStream.str(),
            author,
            message,
            files,
            signedCommit
        };
    }
};

struct Branch {
    std::string name;
    std::string headCommitId;
};

class Repository {
private:
    std::string name_;
    std::unordered_map<std::string, Commit> commits_;
    std::unordered_map<std::string, Branch> branches_;

public:
    explicit Repository(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    void addCommit(const Commit& commit) {
        commits_[commit.id] = commit;
    }

    void createBranch(
        const std::string& branchName,
        const std::string& sourceBranch
    ) {
        if (branches_.contains(branchName)) {
            throw std::runtime_error(
                "Branch already exists: " + branchName
            );
        }

        const Branch* source = getBranch(sourceBranch);

        if (source == nullptr) {
            throw std::runtime_error(
                "Source branch does not exist: " + sourceBranch
            );
        }

        branches_[branchName] = Branch{
            branchName,
            source->headCommitId
        };
    }

    void createInitialBranch(
        const std::string& branchName,
        const Commit& initialCommit
    ) {
        addCommit(initialCommit);

        branches_[branchName] = Branch{
            branchName,
            initialCommit.id
        };
    }

    void updateBranch(
        const std::string& branchName,
        const Commit& commit
    ) {
        if (!branches_.contains(branchName)) {
            throw std::runtime_error(
                "Unknown branch: " + branchName
            );
        }

        addCommit(commit);
        branches_.at(branchName).headCommitId = commit.id;
    }

    const Commit* getCommit(const std::string& commitId) const {
        auto it = commits_.find(commitId);

        if (it == commits_.end()) {
            return nullptr;
        }

        return &it->second;
    }

    const Branch* getBranch(const std::string& branchName) const {
        auto it = branches_.find(branchName);

        if (it == branches_.end()) {
            return nullptr;
        }

        return &it->second;
    }
};

// ============================================================================
// 3. REVIEW AND CI OBJECTS
// ============================================================================

struct Review {
    std::string reviewer;
    ReviewState state;
    std::string commitId;
    std::string comment;
};

struct ReviewComment {
    std::string reviewer;
    std::string filename;
    std::size_t lineNumber;
    std::string body;
    bool resolved{false};
};

struct StatusCheck {
    std::string name;
    CheckState state;
    std::string commitId;
};

struct SecurityFinding {
    std::string filename;
    std::size_t lineNumber;
    std::string severity;
    std::string message;
};

// ============================================================================
// 4. PULL REQUEST
// ============================================================================

class PullRequest {
public:
    int number;
    std::string title;
    std::string author;
    std::string baseBranch;
    std::string headBranch;
    std::string baseCommitId;
    Commit headCommit;

    bool draft{false};
    bool merged{false};
    bool closed{false};
    bool branchIsUpToDate{true};

    std::vector<Review> reviews;
    std::vector<ReviewComment> comments;
    std::vector<StatusCheck> statusChecks;
    std::set<std::string> codeOwnerApprovals;

    PullRequest(
        int number,
        std::string title,
        std::string author,
        std::string baseBranch,
        std::string headBranch,
        std::string baseCommitId,
        Commit headCommit
    )
        : number(number),
          title(std::move(title)),
          author(std::move(author)),
          baseBranch(std::move(baseBranch)),
          headBranch(std::move(headBranch)),
          baseCommitId(std::move(baseCommitId)),
          headCommit(std::move(headCommit)) {}

    const std::string& headCommitId() const {
        return headCommit.id;
    }
};

// ============================================================================
// 5. BRANCH PROTECTION POLICY
// ============================================================================

struct BranchProtectionPolicy {
    std::string protectedBranch{"main"};

    std::size_t requiredApprovals{1};

    std::vector<std::string> requiredStatusChecks{
        "unit-tests",
        "static-analysis"
    };

    bool requireCodeOwnerReview{false};
    bool dismissStaleApprovals{true};
    bool requireConversationResolution{true};
    bool requireUpToDateBranch{true};

    bool allowForcePush{false};
    bool allowDeletions{false};
    bool allowDirectPush{false};

    bool requireSignedCommits{false};
    bool requireLinearHistory{false};
};

struct PolicyResult {
    bool allowed{false};
    std::vector<std::string> reasons;

    std::string toString() const {
        std::ostringstream output;

        if (allowed) {
            output << "MERGE ALLOWED";
            return output.str();
        }

        output << "MERGE BLOCKED";

        for (const auto& reason : reasons) {
            output << "\n  - " << reason;
        }

        return output.str();
    }
};

// ============================================================================
// 6. AUDIT LOG
// ============================================================================

struct AuditEvent {
    std::string actor;
    std::string action;
    std::string detail;
};

class AuditLog {
private:
    std::vector<AuditEvent> events_;

public:
    void record(
        const std::string& actor,
        const std::string& action,
        const std::string& detail
    ) {
        events_.push_back(AuditEvent{
            actor,
            action,
            detail
        });
    }

    void print() const {
        std::cout << "\nAUDIT LOG\n";
        std::cout << "---------\n";

        for (const auto& event : events_) {
            std::cout
                << event.actor << " | "
                << event.action << " | "
                << event.detail << '\n';
        }
    }
};

// ============================================================================
// 7. POLICY ENGINE
// ============================================================================

class PullRequestPolicyEngine {
private:
    const BranchProtectionPolicy& policy_;

    std::set<std::string> currentApprovers(
        const PullRequest& pullRequest
    ) const {
        std::set<std::string> approvers;

        for (const Review& review : pullRequest.reviews) {
            if (review.state != ReviewState::Approved) {
                continue;
            }

            /*
             * When stale approvals are dismissed, an approval for an older
             * commit cannot satisfy the current review requirement.
             */
            if (
                policy_.dismissStaleApprovals &&
                review.commitId != pullRequest.headCommitId()
            ) {
                continue;
            }

            approvers.insert(review.reviewer);
        }

        return approvers;
    }

    bool hasCurrentChangeRequest(
        const PullRequest& pullRequest
    ) const {
        for (const Review& review : pullRequest.reviews) {
            if (review.state != ReviewState::ChangesRequested) {
                continue;
            }

            if (
                policy_.dismissStaleApprovals &&
                review.commitId != pullRequest.headCommitId()
            ) {
                continue;
            }

            return true;
        }

        return false;
    }

    bool requiredChecksPass(
        const PullRequest& pullRequest
    ) const {
        std::unordered_map<std::string, CheckState> checks;

        for (const StatusCheck& check : pullRequest.statusChecks) {
            if (check.commitId == pullRequest.headCommitId()) {
                checks[check.name] = check.state;
            }
        }

        for (const std::string& required : policy_.requiredStatusChecks) {
            auto it = checks.find(required);

            if (
                it == checks.end() ||
                it->second != CheckState::Passed
            ) {
                return false;
            }
        }

        return true;
    }

public:
    explicit PullRequestPolicyEngine(
        const BranchProtectionPolicy& policy
    )
        : policy_(policy) {}

    PolicyResult evaluate(
        const PullRequest& pullRequest,
        const std::string& currentBaseCommitId
    ) const {
        PolicyResult result;

        if (pullRequest.merged) {
            result.reasons.push_back(
                "Pull request is already merged."
            );
        }

        if (pullRequest.closed) {
            result.reasons.push_back(
                "Pull request is closed."
            );
        }

        if (pullRequest.draft) {
            result.reasons.push_back(
                "Draft pull requests are not mergeable under this policy."
            );
        }

        if (
            pullRequest.baseBranch !=
            policy_.protectedBranch
        ) {
            result.reasons.push_back(
                "The pull request does not target the protected branch."
            );
        }

        if (policy_.requireUpToDateBranch) {
            if (!pullRequest.branchIsUpToDate) {
                result.reasons.push_back(
                    "The head branch is not up to date with the base branch."
                );
            }

            if (
                pullRequest.baseCommitId !=
                currentBaseCommitId
            ) {
                result.reasons.push_back(
                    "The pull request was opened against an outdated base."
                );
            }
        }

        if (hasCurrentChangeRequest(pullRequest)) {
            result.reasons.push_back(
                "A current reviewer has requested changes."
            );
        }

        std::set<std::string> approvers =
            currentApprovers(pullRequest);

        /*
         * The author is intentionally excluded from the independent approval
         * count. Repository policy determines exactly which reviewers are
         * eligible in a real implementation.
         */
        approvers.erase(pullRequest.author);

        if (
            approvers.size() <
            policy_.requiredApprovals
        ) {
            std::ostringstream reason;

            reason
                << "Required approvals: "
                << policy_.requiredApprovals
                << ", independent current approvals: "
                << approvers.size();

            result.reasons.push_back(reason.str());
        }

        if (
            policy_.requireCodeOwnerReview &&
            pullRequest.codeOwnerApprovals.empty()
        ) {
            result.reasons.push_back(
                "A code-owner approval is required."
            );
        }

        if (policy_.requireConversationResolution) {
            std::size_t unresolved = 0;

            for (const auto& comment : pullRequest.comments) {
                if (!comment.resolved) {
                    ++unresolved;
                }
            }

            if (unresolved > 0) {
                result.reasons.push_back(
                    "There are " +
                    std::to_string(unresolved) +
                    " unresolved review conversation(s)."
                );
            }
        }

        if (!requiredChecksPass(pullRequest)) {
            result.reasons.push_back(
                "One or more required status checks have not passed."
            );
        }

        if (
            policy_.requireSignedCommits &&
            !pullRequest.headCommit.signedCommit
        ) {
            result.reasons.push_back(
                "The current commit is not signed."
            );
        }

        result.allowed = result.reasons.empty();

        return result;
    }
};

// ============================================================================
// 8. DIFF GENERATION
// ============================================================================

std::vector<std::string> splitLines(const std::string& text) {
    std::vector<std::string> lines;
    std::stringstream stream(text);
    std::string line;

    while (std::getline(stream, line)) {
        lines.push_back(line);
    }

    return lines;
}

void printSimpleDiff(
    const Commit& base,
    const Commit& head
) {
    std::set<std::string> filenames;

    for (const auto& [filename, content] : base.files) {
        filenames.insert(filename);
    }

    for (const auto& [filename, content] : head.files) {
        filenames.insert(filename);
    }

    for (const auto& filename : filenames) {
        const auto baseIt = base.files.find(filename);
        const auto headIt = head.files.find(filename);

        const std::string oldContent =
            baseIt == base.files.end()
                ? ""
                : baseIt->second;

        const std::string newContent =
            headIt == head.files.end()
                ? ""
                : headIt->second;

        if (oldContent == newContent) {
            continue;
        }

        std::cout
            << "\n--- a/" << filename
            << "\n+++ b/" << filename
            << '\n';

        const auto oldLines = splitLines(oldContent);
        const auto newLines = splitLines(newContent);

        const std::size_t maxSize =
            std::max(oldLines.size(), newLines.size());

        for (std::size_t i = 0; i < maxSize; ++i) {
            const bool hasOld = i < oldLines.size();
            const bool hasNew = i < newLines.size();

            if (hasOld && hasNew && oldLines[i] == newLines[i]) {
                std::cout << "  " << oldLines[i] << '\n';
            } else {
                if (hasOld) {
                    std::cout << "- " << oldLines[i] << '\n';
                }

                if (hasNew) {
                    std::cout << "+ " << newLines[i] << '\n';
                }
            }
        }
    }
}

// ============================================================================
// 9. CODE OWNERS
// ============================================================================

struct CodeOwnerRule {
    std::string pattern;
    std::set<std::string> owners;
};

bool pathMatches(
    const std::string& path,
    const std::string& pattern
) {
    if (pattern == "*") {
        return true;
    }

    if (!pattern.empty() && pattern.back() == '/') {
        return path.rfind(pattern, 0) == 0;
    }

    if (
        pattern.size() >= 2 &&
        pattern[0] == '*' &&
        pattern[1] == '.'
    ) {
        const std::string suffix = pattern.substr(1);

        if (path.size() < suffix.size()) {
            return false;
        }

        return path.compare(
            path.size() - suffix.size(),
            suffix.size(),
            suffix
        ) == 0;
    }

    return path == pattern;
}

std::set<std::string> determineCodeOwners(
    const std::vector<std::string>& changedPaths,
    const std::vector<CodeOwnerRule>& rules
) {
    std::set<std::string> owners;

    for (const auto& path : changedPaths) {
        for (const auto& rule : rules) {
            if (pathMatches(path, rule.pattern)) {
                owners.insert(
                    rule.owners.begin(),
                    rule.owners.end()
                );
            }
        }
    }

    return owners;
}

// ============================================================================
// 10. SECURITY SCANNER
// ============================================================================

std::vector<SecurityFinding> scanForObviousSecrets(
    const std::map<std::string, std::string>& files
) {
    /*
     * This scanner intentionally demonstrates the mechanism rather than
     * claiming to be a production-grade secret detector.
     */
    const std::regex passwordPattern(
        R"(password\s*=\s*["'][^"']+["'])",
        std::regex_constants::icase
    );

    const std::regex privateKeyPattern(
        R"(-----BEGIN .*PRIVATE KEY-----)"
    );

    std::vector<SecurityFinding> findings;

    for (const auto& [filename, content] : files) {
        const auto lines = splitLines(content);

        for (std::size_t index = 0; index < lines.size(); ++index) {
            const std::string& line = lines[index];

            if (
                std::regex_search(line, passwordPattern) ||
                std::regex_search(line, privateKeyPattern)
            ) {
                findings.push_back(SecurityFinding{
                    filename,
                    index + 1,
                    "high",
                    "Potential credential or private key detected."
                });
            }
        }
    }

    return findings;
}

// ============================================================================
// 11. CI SIMULATION
// ============================================================================

StatusCheck runUnitTests(const Commit& commit) {
    for (const auto& [filename, content] : commit.files) {
        if (content.find("INTENTIONALLY_BROKEN") !=
            std::string::npos) {
            return StatusCheck{
                "unit-tests",
                CheckState::Failed,
                commit.id
            };
        }
    }

    return StatusCheck{
        "unit-tests",
        CheckState::Passed,
        commit.id
    };
}

StatusCheck runStaticAnalysis(const Commit& commit) {
    for (const auto& [filename, content] : commit.files) {
        /*
         * Tabs are treated as a style violation in this educational rule.
         */
        if (
            filename.size() >= 4 &&
            filename.substr(filename.size() - 4) == ".cpp" &&
            content.find('\t') != std::string::npos
        ) {
            return StatusCheck{
                "static-analysis",
                CheckState::Failed,
                commit.id
            };
        }
    }

    return StatusCheck{
        "static-analysis",
        CheckState::Passed,
        commit.id
    };
}

// ============================================================================
// 12. FEATURE COMMIT CONSTRUCTION
// ============================================================================

Commit buildFeatureCommit(
    const Commit& base,
    const std::string& author,
    bool secure = true,
    bool broken = false,
    bool signedCommit = true
) {
    auto files = base.files;

    if (secure) {
        files["payment.cpp"] =
            "#include <stdexcept>\n"
            "\n"
            "double calculateTotal(double amount, double tax) {\n"
            "    if (amount < 0 || tax < 0) {\n"
            "        throw std::invalid_argument(\n"
            "            \"amount and tax must be non-negative\"\n"
            "        );\n"
            "    }\n"
            "\n"
            "    return amount + tax;\n"
            "}\n";
    } else {
        files["payment.cpp"] =
            "#include <string>\n"
            "\n"
            "const std::string API_PASSWORD = \"hard-coded-secret\";\n"
            "\n"
            "double calculateTotal(double amount, double tax) {\n"
            "    return amount + tax;\n"
            "}\n";
    }

    files["tests.cpp"] =
        "#include <cassert>\n"
        "\n"
        "void testCalculateTotal() {\n"
        "    assert(100.0 + 10.0 == 110.0);\n"
        "}\n";

    if (broken) {
        files["payment.cpp"] +=
            "\n// INTENTIONALLY_BROKEN\n";
    }

    return Commit::create(
        author,
        "Validate payment totals",
        files,
        signedCommit
    );
}

// ============================================================================
// 13. PULL REQUEST CREATION
// ============================================================================

PullRequest createPullRequest(
    Repository& repository,
    int number,
    const std::string& author
) {
    const Branch* mainBranch =
        repository.getBranch("main");

    if (mainBranch == nullptr) {
        throw std::runtime_error(
            "main branch does not exist"
        );
    }

    const Commit* base =
        repository.getCommit(mainBranch->headCommitId);

    if (base == nullptr) {
        throw std::runtime_error(
            "main branch references an unknown commit"
        );
    }

    repository.createBranch(
        "feature/payment-validation",
        "main"
    );

    Commit featureCommit =
        buildFeatureCommit(
            *base,
            author,
            true,
            false,
            true
        );

    repository.updateBranch(
        "feature/payment-validation",
        featureCommit
    );

    return PullRequest(
        number,
        "Validate payment totals",
        author,
        "main",
        "feature/payment-validation",
        base->id,
        featureCommit
    );
}

// ============================================================================
// 14. REVIEW WORKFLOW
// ============================================================================

void addApproval(
    PullRequest& pullRequest,
    const std::string& reviewer
) {
    pullRequest.reviews.push_back(
        Review{
            reviewer,
            ReviewState::Approved,
            pullRequest.headCommitId(),
            "Implementation approved."
        }
    );
}

void addPassingChecks(PullRequest& pullRequest) {
    pullRequest.statusChecks.push_back(
        runUnitTests(pullRequest.headCommit)
    );

    pullRequest.statusChecks.push_back(
        runStaticAnalysis(pullRequest.headCommit)
    );
}

void demonstrateCompleteWorkflow() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n1. COMPLETE INDUSTRY-STYLE WORKFLOW\n"
        << std::string(78, '=')
        << "\n";

    Repository repository("payment-service");

    const Commit initialCommit = Commit::create(
        "system",
        "Initial payment service",
        {
            {
                "README.md",
                "# Payment Service\n"
            },
            {
                "payment.cpp",
                "double calculateTotal(double amount, double tax) {\n"
                "    return amount + tax;\n"
                "}\n"
            }
        },
        true
    );

    repository.createInitialBranch(
        "main",
        initialCommit
    );

    PullRequest pullRequest =
        createPullRequest(
            repository,
            42,
            "alice"
        );

    std::cout
        << "PR #" << pullRequest.number
        << ": " << pullRequest.title << '\n';

    std::cout
        << "Base: " << pullRequest.baseBranch
        << '\n';

    std::cout
        << "Head: " << pullRequest.headBranch
        << '\n';

    std::cout
        << "Current commit: "
        << pullRequest.headCommitId()
        << '\n';

    std::cout
        << "\nDIFF:\n";

    const Commit* currentBase =
        repository.getCommit(
            pullRequest.baseCommitId
        );

    if (currentBase != nullptr) {
        printSimpleDiff(
            *currentBase,
            pullRequest.headCommit
        );
    }

    /*
     * Reviewer Bob reviews the exact current commit. This matters because
     * approval is connected to the state that was actually reviewed.
     */
    addApproval(
        pullRequest,
        "bob"
    );

    pullRequest.comments.push_back(
        ReviewComment{
            "bob",
            "payment.cpp",
            3,
            "Please validate negative amounts.",
            true
        }
    );

    addPassingChecks(pullRequest);

    BranchProtectionPolicy policy;

    PullRequestPolicyEngine engine(policy);

    const Branch* currentMain =
        repository.getBranch("main");

    PolicyResult result =
        engine.evaluate(
            pullRequest,
            currentMain->headCommitId
        );

    std::cout
        << "\nPOLICY RESULT:\n"
        << result.toString()
        << '\n';

    if (result.allowed) {
        pullRequest.merged = true;

        repository.updateBranch(
            "main",
            pullRequest.headCommit
        );

        std::cout
            << "\nMerge completed. Protected main now references "
            << pullRequest.headCommitId()
            << ".\n";
    }
}

// ============================================================================
// 15. STALE APPROVAL CASE
// ============================================================================

void demonstrateStaleApproval() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n2. STALE APPROVAL SCENARIO\n"
        << std::string(78, '=')
        << "\n";

    Repository repository("payment-service");

    const Commit initialCommit = Commit::create(
        "system",
        "Initial commit",
        {
            {
                "README.md",
                "# Payment Service\n"
            }
        }
    );

    repository.createInitialBranch(
        "main",
        initialCommit
    );

    PullRequest pullRequest =
        createPullRequest(
            repository,
            43,
            "alice"
        );

    const std::string approvedCommit =
        pullRequest.headCommitId();

    addApproval(
        pullRequest,
        "bob"
    );

    std::cout
        << "Bob approved commit: "
        << approvedCommit
        << '\n';

    auto changedFiles =
        pullRequest.headCommit.files;

    changedFiles["README.md"] =
        "# Payment Service\n"
        "Additional documentation.\n";

    pullRequest.headCommit =
        Commit::create(
            "alice",
            "Update documentation",
            changedFiles
        );

    std::cout
        << "New commit after approval: "
        << pullRequest.headCommitId()
        << '\n';

    BranchProtectionPolicy policy;

    policy.requiredStatusChecks.clear();
    policy.requireConversationResolution = false;

    PullRequestPolicyEngine engine(policy);

    const Branch* main =
        repository.getBranch("main");

    PolicyResult result =
        engine.evaluate(
            pullRequest,
            main->headCommitId
        );

    std::cout
        << result.toString()
        << '\n';
}

// ============================================================================
// 16. CODE OWNERSHIP
// ============================================================================

void demonstrateCodeOwners() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n3. CODE OWNERSHIP\n"
        << std::string(78, '=')
        << "\n";

    const std::vector<CodeOwnerRule> rules{
        {
            "payment.cpp",
            {"alice", "security-team"}
        },
        {
            "*.md",
            {"documentation-team"}
        }
    };

    const std::vector<std::string> changedPaths{
        "payment.cpp",
        "README.md"
    };

    const auto owners =
        determineCodeOwners(
            changedPaths,
            rules
        );

    std::cout
        << "Changed files:\n";

    for (const auto& path : changedPaths) {
        std::cout
            << "  - "
            << path
            << '\n';
    }

    std::cout
        << "Potential required owners:\n";

    for (const auto& owner : owners) {
        std::cout
            << "  - "
            << owner
            << '\n';
    }
}

// ============================================================================
// 17. SECURITY REVIEW
// ============================================================================

void demonstrateSecurityReview() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n4. SECURITY REVIEW\n"
        << std::string(78, '=')
        << "\n";

    const Commit insecureCommit =
        Commit::create(
            "alice",
            "Insecure implementation",
            {
                {
                    "payment.cpp",
                    "const std::string password = "
                    "\"hard-coded-secret\";\n"
                }
            }
        );

    const auto findings =
        scanForObviousSecrets(
            insecureCommit.files
        );

    if (findings.empty()) {
        std::cout
            << "No obvious secrets detected.\n";
        return;
    }

    for (const auto& finding : findings) {
        std::cout
            << finding.severity
            << " | "
            << finding.filename
            << ":"
            << finding.lineNumber
            << " | "
            << finding.message
            << '\n';
    }

    std::cout
        << "\nA small regex scanner is not a complete security solution. "
        << "Production systems should combine secret detection, credential "
        << "rotation, secure storage, and appropriate CI security controls.\n";
}

// ============================================================================
// 18. FAILED CI CASE
// ============================================================================

void demonstrateFailedChecks() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n5. FAILED STATUS CHECK\n"
        << std::string(78, '=')
        << "\n";

    Repository repository("payment-service");

    const Commit initialCommit = Commit::create(
        "system",
        "Initial commit",
        {
            {
                "README.md",
                "# Payment Service\n"
            }
        }
    );

    repository.createInitialBranch(
        "main",
        initialCommit
    );

    PullRequest pullRequest =
        createPullRequest(
            repository,
            44,
            "alice"
        );

    /*
     * Insert a marker that makes the simulated unit-test job fail.
     */
    pullRequest.headCommit.files["payment.cpp"] +=
        "\n// INTENTIONALLY_BROKEN\n";

    addApproval(
        pullRequest,
        "bob"
    );

    pullRequest.statusChecks.push_back(
        runUnitTests(
            pullRequest.headCommit
        )
    );

    pullRequest.statusChecks.push_back(
        runStaticAnalysis(
            pullRequest.headCommit
        )
    );

    BranchProtectionPolicy policy;

    PullRequestPolicyEngine engine(policy);

    const Branch* main =
        repository.getBranch("main");

    PolicyResult result =
        engine.evaluate(
            pullRequest,
            main->headCommitId
        );

    std::cout
        << result.toString()
        << '\n';
}

// ============================================================================
// 19. UNRESOLVED REVIEW CONVERSATION
// ============================================================================

void demonstrateUnresolvedConversation() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n6. UNRESOLVED REVIEW CONVERSATION\n"
        << std::string(78, '=')
        << "\n";

    Repository repository("payment-service");

    const Commit initialCommit = Commit::create(
        "system",
        "Initial commit",
        {
            {
                "README.md",
                "# Payment Service\n"
            }
        }
    );

    repository.createInitialBranch(
        "main",
        initialCommit
    );

    PullRequest pullRequest =
        createPullRequest(
            repository,
            45,
            "alice"
        );

    addApproval(
        pullRequest,
        "bob"
    );

    addPassingChecks(
        pullRequest
    );

    pullRequest.comments.push_back(
        ReviewComment{
            "bob",
            "payment.cpp",
            4,
            "Please explain the exception type.",
            false
        }
    );

    BranchProtectionPolicy policy;

    PullRequestPolicyEngine engine(policy);

    const Branch* main =
        repository.getBranch("main");

    PolicyResult result =
        engine.evaluate(
            pullRequest,
            main->headCommitId
        );

    std::cout
        << result.toString()
        << '\n';
}

// ============================================================================
// 20. MERGE STRATEGIES
// ============================================================================

void demonstrateMergeStrategies() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n7. MERGE STRATEGIES\n"
        << std::string(78, '=')
        << "\n";

    const std::vector<std::pair<MergeStrategy, std::string>> strategies{
        {
            MergeStrategy::MergeCommit,
            "Preserves the branch relationship and records an explicit merge."
        },
        {
            MergeStrategy::Squash,
            "Combines the pull request changes into a single integration commit."
        },
        {
            MergeStrategy::Rebase,
            "Replays commits on a new base to maintain a linear history."
        }
    };

    for (const auto& [strategy, description] : strategies) {
        std::cout
            << std::left
            << std::setw(15)
            << toString(strategy)
            << " "
            << description
            << '\n';
    }
}

// ============================================================================
// 21. POLICY UNIT TESTS
// ============================================================================

void expect(
    bool condition,
    const std::string& message
) {
    if (!condition) {
        throw std::runtime_error(
            "TEST FAILURE: " + message
        );
    }
}

struct TestRunner {
    int passed{0};
    int failed{0};

    void run(
        const std::string& name,
        const std::function<void()>& test
    ) {
        try {
            test();
            ++passed;
            std::cout
                << "PASS: "
                << name
                << '\n';
        } catch (const std::exception& error) {
            ++failed;
            std::cout
                << "FAIL: "
                << name
                << " -> "
                << error.what()
                << '\n';
        }
    }
};

PullRequest createReadyPullRequest(
    Repository& repository
) {
    const Commit initialCommit = Commit::create(
        "system",
        "Initial commit",
        {
            {
                "README.md",
                "# Payment Service\n"
            }
        },
        true
    );

    repository.createInitialBranch(
        "main",
        initialCommit
    );

    PullRequest pullRequest =
        createPullRequest(
            repository,
            999,
            "alice"
        );

    addApproval(
        pullRequest,
        "bob"
    );

    addPassingChecks(
        pullRequest
    );

    return pullRequest;
}

void runPolicyTests() {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n8. POLICY UNIT TESTS\n"
        << std::string(78, '=')
        << "\n";

    TestRunner tests;

    tests.run(
        "ready pull request is mergeable",
        [] {
            Repository repository("test");

            PullRequest pullRequest =
                createReadyPullRequest(
                    repository
                );

            BranchProtectionPolicy policy;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                result.allowed,
                "ready PR should be allowed"
            );
        }
    );

    tests.run(
        "missing approval blocks merge",
        [] {
            Repository repository("test");

            const Commit initialCommit =
                Commit::create(
                    "system",
                    "Initial",
                    {
                        {
                            "README.md",
                            "# Test\n"
                        }
                    }
                );

            repository.createInitialBranch(
                "main",
                initialCommit
            );

            PullRequest pullRequest =
                createPullRequest(
                    repository,
                    100,
                    "alice"
                );

            addPassingChecks(
                pullRequest
            );

            BranchProtectionPolicy policy;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                !result.allowed,
                "missing approval should block"
            );
        }
    );

    tests.run(
        "failed check blocks merge",
        [] {
            Repository repository("test");

            PullRequest pullRequest =
                createReadyPullRequest(
                    repository
                );

            pullRequest.statusChecks.clear();

            pullRequest.statusChecks.push_back(
                StatusCheck{
                    "unit-tests",
                    CheckState::Failed,
                    pullRequest.headCommitId()
                }
            );

            pullRequest.statusChecks.push_back(
                StatusCheck{
                    "static-analysis",
                    CheckState::Passed,
                    pullRequest.headCommitId()
                }
            );

            BranchProtectionPolicy policy;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                !result.allowed,
                "failed CI check should block"
            );
        }
    );

    tests.run(
        "unresolved conversation blocks merge",
        [] {
            Repository repository("test");

            PullRequest pullRequest =
                createReadyPullRequest(
                    repository
                );

            pullRequest.comments.push_back(
                ReviewComment{
                    "bob",
                    "payment.cpp",
                    4,
                    "Explain this line.",
                    false
                }
            );

            BranchProtectionPolicy policy;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                !result.allowed,
                "unresolved conversation should block"
            );
        }
    );

    tests.run(
        "self approval does not satisfy independent review",
        [] {
            Repository repository("test");

            const Commit initialCommit =
                Commit::create(
                    "system",
                    "Initial",
                    {
                        {
                            "README.md",
                            "# Test\n"
                        }
                    }
                );

            repository.createInitialBranch(
                "main",
                initialCommit
            );

            PullRequest pullRequest =
                createPullRequest(
                    repository,
                    101,
                    "alice"
                );

            addApproval(
                pullRequest,
                "alice"
            );

            addPassingChecks(
                pullRequest
            );

            BranchProtectionPolicy policy;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                !result.allowed,
                "author approval should not count"
            );
        }
    );

    tests.run(
        "stale approval does not satisfy current review",
        [] {
            Repository repository("test");

            PullRequest pullRequest =
                createReadyPullRequest(
                    repository
                );

            const std::string oldCommit =
                pullRequest.headCommitId();

            auto files =
                pullRequest.headCommit.files;

            files["README.md"] =
                "# Test\n"
                "Modified after review.\n";

            pullRequest.headCommit =
                Commit::create(
                    "alice",
                    "Modify after approval",
                    files
                );

            BranchProtectionPolicy policy;

            policy.requiredStatusChecks.clear();
            policy.requireConversationResolution =
                false;

            PullRequestPolicyEngine engine(policy);

            const Branch* main =
                repository.getBranch("main");

            const PolicyResult result =
                engine.evaluate(
                    pullRequest,
                    main->headCommitId
                );

            expect(
                !result.allowed,
                "approval for old commit should not count"
            );

            expect(
                oldCommit != pullRequest.headCommitId(),
                "test setup must create a new commit"
            );
        }
    );

    std::cout
        << "\nTests run: "
        << tests.passed + tests.failed
        << ", passed: "
        << tests.passed
        << ", failed: "
        << tests.failed
        << '\n';
}

// ============================================================================
// 22. MAIN
// ============================================================================

int main() {
    try {
        std::cout
            << "PULL REQUESTS, CODE REVIEW, APPROVALS, "
            << "AND BRANCH PROTECTION\n"
            << "============================================================\n";

        demonstrateCompleteWorkflow();
        demonstrateStaleApproval();
        demonstrateCodeOwners();
        demonstrateSecurityReview();
        demonstrateFailedChecks();
        demonstrateUnresolvedConversation();
        demonstrateMergeStrategies();
        runPolicyTests();

        std::cout
            << "\n"
            << std::string(78, '=')
            << "\nKEY ENGINEERING MODEL\n"
            << std::string(78, '=')
            << "\n"
            << "Branch -> Pull Request -> Diff -> Review -> CI checks -> "
            << "Protection policy -> Merge\n";

        std::cout
            << "\nImportant distinction: Git provides version-control "
            << "mechanisms, while pull-request review and branch-protection "
            << "rules are repository workflow controls layered on top of Git.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}

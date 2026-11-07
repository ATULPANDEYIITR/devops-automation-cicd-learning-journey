#include <algorithm>
#include <chrono>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std;

// ============================================================
// 1. DOMAIN ENUMS
// ============================================================

enum class PullRequestState {
    OPEN,
    DRAFT,
    CLOSED,
    MERGED
};

enum class ReviewState {
    APPROVED,
    CHANGES_REQUESTED,
    COMMENTED,
    DISMISSED
};

enum class CheckState {
    SUCCESS,
    FAILURE,
    PENDING,
    ERROR
};

enum class TriggerType {
    WEBHOOK,
    SCM_POLL,
    MANUAL
};

enum class BuildState {
    QUEUED,
    RUNNING,
    SUCCESS,
    FAILURE
};

string toString(PullRequestState state) {
    switch (state) {
        case PullRequestState::OPEN: return "OPEN";
        case PullRequestState::DRAFT: return "DRAFT";
        case PullRequestState::CLOSED: return "CLOSED";
        case PullRequestState::MERGED: return "MERGED";
    }
    return "UNKNOWN";
}

string toString(CheckState state) {
    switch (state) {
        case CheckState::SUCCESS: return "SUCCESS";
        case CheckState::FAILURE: return "FAILURE";
        case CheckState::PENDING: return "PENDING";
        case CheckState::ERROR: return "ERROR";
    }
    return "UNKNOWN";
}

string toString(BuildState state) {
    switch (state) {
        case BuildState::QUEUED: return "QUEUED";
        case BuildState::RUNNING: return "RUNNING";
        case BuildState::SUCCESS: return "SUCCESS";
        case BuildState::FAILURE: return "FAILURE";
    }
    return "UNKNOWN";
}


// ============================================================
// 2. VALIDATION
// ============================================================

bool validSHA(const string& sha) {
    if (sha.size() < 7 || sha.size() > 64) {
        return false;
    }

    return all_of(
        sha.begin(),
        sha.end(),
        [](unsigned char c) {
            return isxdigit(c) && !isupper(c);
        }
    );
}

void validateBranch(const string& branch) {
    if (
        branch.empty() ||
        branch.size() > 255 ||
        branch.find("..") != string::npos ||
        branch.front() == '-' ||
        branch.find(' ') != string::npos
    ) {
        throw invalid_argument("Invalid branch name");
    }
}

void validateSHA(const string& sha) {
    if (!validSHA(sha)) {
        throw invalid_argument("Invalid commit SHA");
    }
}


// ============================================================
// 3. REPOSITORY STRUCTURES
// ============================================================

struct Commit {
    string sha;
    string message;
    string author;
};

struct Branch {
    string name;
    string headSHA;
    bool protectedBranch = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
};

struct Review {
    string reviewer;
    ReviewState state;
    string commitSHA;
};

struct StatusCheck {
    string name;
    CheckState state;
    string commitSHA;
};

struct ReviewComment {
    int id;
    string reviewer;
    string filePath;
    int line;
    string content;
    bool resolved = false;
};

struct PullRequest {
    int number;
    string sourceBranch;
    string targetBranch;
    string sourceSHA;
    string targetSHA;

    PullRequestState state = PullRequestState::OPEN;

    vector<Commit> commits;
    vector<Review> reviews;
    map<string, StatusCheck> checks;
    vector<ReviewComment> comments;

    bool mergeConflict = false;
    bool baseSynchronized = true;
    bool draft = false;
};

struct BranchProtectionPolicy {
    string branchName;

    int requiredApprovals = 1;

    set<string> requiredChecks;

    bool requireConversationResolution = true;
    bool requireUpToDate = true;
    bool requireCodeOwnerApproval = false;
    bool requireLinearHistory = false;

    bool allowDirectPush = false;
    bool allowForcePush = false;
    bool allowDeletion = false;

    bool dismissStaleApprovals = true;
    bool administratorBypass = false;
};

struct MergeDecision {
    bool eligible = false;
    vector<string> reasons;
};

struct Build {
    int id;
    string repository;
    string branch;
    string commitSHA;
    TriggerType trigger;
    BuildState state = BuildState::QUEUED;
};


// ============================================================
// 4. REPOSITORY
// ============================================================

class Repository {
private:
    string name;

    map<string, Branch> branches;
    unordered_map<string, Commit> commits;
    map<int, PullRequest> pullRequests;
    map<string, BranchProtectionPolicy> policies;

    set<string> eligibleReviewers;
    set<string> codeOwners;

public:
    explicit Repository(string repositoryName)
        : name(move(repositoryName)) {
        if (name.empty()) {
            throw invalid_argument("Repository name cannot be empty");
        }
    }

    const string& getName() const {
        return name;
    }

    void addBranch(const Branch& branch) {
        validateBranch(branch.name);
        validateSHA(branch.headSHA);

        if (branches.count(branch.name)) {
            throw invalid_argument("Branch already exists");
        }

        branches.emplace(branch.name, branch);
    }

    void addCommit(const Commit& commit) {
        validateSHA(commit.sha);

        if (commit.message.empty()) {
            throw invalid_argument("Commit message cannot be empty");
        }

        commits[commit.sha] = commit;
    }

    void addReviewer(const string& reviewer) {
        if (reviewer.empty()) {
            throw invalid_argument("Invalid reviewer");
        }

        eligibleReviewers.insert(reviewer);
    }

    void addCodeOwner(const string& reviewer) {
        codeOwners.insert(reviewer);
        eligibleReviewers.insert(reviewer);
    }

    void setPolicy(const BranchProtectionPolicy& policy) {
        validateBranch(policy.branchName);

        if (!branches.count(policy.branchName)) {
            throw invalid_argument("Policy references unknown branch");
        }

        if (policy.requiredApprovals < 0) {
            throw invalid_argument("Invalid approval count");
        }

        policies[policy.branchName] = policy;
    }

    const Branch& getBranch(const string& branch) const {
        auto it = branches.find(branch);

        if (it == branches.end()) {
            throw out_of_range("Branch not found");
        }

        return it->second;
    }

    Branch& getMutableBranch(const string& branch) {
        auto it = branches.find(branch);

        if (it == branches.end()) {
            throw out_of_range("Branch not found");
        }

        return it->second;
    }

    const BranchProtectionPolicy* getPolicy(
        const string& branch
    ) const {
        auto it = policies.find(branch);

        if (it == policies.end()) {
            return nullptr;
        }

        return &it->second;
    }

    const set<string>& getEligibleReviewers() const {
        return eligibleReviewers;
    }

    const set<string>& getCodeOwners() const {
        return codeOwners;
    }

    bool hasCommit(const string& sha) const {
        return commits.count(sha) > 0;
    }

    bool hasPullRequest(int number) const {
        return pullRequests.count(number) > 0;
    }

    PullRequest& getPullRequest(int number) {
        auto it = pullRequests.find(number);

        if (it == pullRequests.end()) {
            throw out_of_range("Pull Request not found");
        }

        return it->second;
    }

    const map<int, PullRequest>& getPullRequests() const {
        return pullRequests;
    }

    void createPullRequest(
        int number,
        const string& source,
        const string& target,
        vector<Commit> proposedChanges
    ) {
        if (number <= 0 || hasPullRequest(number)) {
            throw invalid_argument("Invalid or duplicate PR number");
        }

        if (source == target) {
            throw invalid_argument("Source and target must differ");
        }

        validateBranch(source);
        validateBranch(target);

        if (!branches.count(source) || !branches.count(target)) {
            throw invalid_argument("Unknown PR branch");
        }

        if (proposedChanges.empty()) {
            throw invalid_argument("PR must contain commits");
        }

        for (const auto& commit : proposedChanges) {
            addCommit(commit);
        }

        const Branch& sourceBranch = branches.at(source);
        const Branch& targetBranch = branches.at(target);

        PullRequest pr;

        pr.number = number;
        pr.sourceBranch = source;
        pr.targetBranch = target;
        pr.sourceSHA = sourceBranch.headSHA;
        pr.targetSHA = targetBranch.headSHA;
        pr.commits = move(proposedChanges);

        pullRequests.emplace(number, move(pr));
    }

    void submitReview(
        int number,
        const string& reviewer,
        ReviewState state
    ) {
        if (!eligibleReviewers.count(reviewer)) {
            throw invalid_argument("Reviewer is not eligible");
        }

        PullRequest& pr = getPullRequest(number);

        if (pr.state != PullRequestState::OPEN) {
            throw logic_error("PR is not open");
        }

        pr.reviews.push_back({
            reviewer,
            state,
            pr.sourceSHA
        });
    }

    void updateCheck(
        int number,
        const string& name,
        CheckState state
    ) {
        if (name.empty()) {
            throw invalid_argument("Check name cannot be empty");
        }

        PullRequest& pr = getPullRequest(number);

        pr.checks[name] = {
            name,
            state,
            pr.sourceSHA
        };
    }

    void addReviewComment(
        int number,
        ReviewComment comment
    ) {
        PullRequest& pr = getPullRequest(number);

        if (comment.line <= 0 || comment.content.empty()) {
            throw invalid_argument("Invalid review comment");
        }

        pr.comments.push_back(move(comment));
    }

    void resolveComment(int number, int commentId) {
        PullRequest& pr = getPullRequest(number);

        auto it = find_if(
            pr.comments.begin(),
            pr.comments.end(),
            [commentId](const ReviewComment& comment) {
                return comment.id == commentId;
            }
        );

        if (it == pr.comments.end()) {
            throw out_of_range("Review comment not found");
        }

        it->resolved = true;
    }

    void synchronizeSource(int number, const string& newSHA) {
        validateSHA(newSHA);

        PullRequest& pr = getPullRequest(number);
        pr.sourceSHA = newSHA;

        // Previous checks and approvals refer to an older commit.
        // They remain recorded but no longer satisfy current policy.
        pr.baseSynchronized = false;
    }

    void synchronizeBase(int number, const string& newTargetSHA) {
        validateSHA(newTargetSHA);

        PullRequest& pr = getPullRequest(number);
        pr.targetSHA = newTargetSHA;
        pr.baseSynchronized = true;
    }

    void setConflict(int number, bool conflict) {
        getPullRequest(number).mergeConflict = conflict;
    }

    void setDraft(int number, bool draft) {
        PullRequest& pr = getPullRequest(number);

        if (pr.state != PullRequestState::OPEN) {
            throw logic_error("Cannot change closed PR");
        }

        pr.draft = draft;
        pr.state = draft
            ? PullRequestState::DRAFT
            : PullRequestState::OPEN;
    }

    void closePullRequest(int number) {
        PullRequest& pr = getPullRequest(number);

        if (pr.state == PullRequestState::MERGED) {
            throw logic_error("Merged PR cannot be closed again");
        }

        pr.state = PullRequestState::CLOSED;
    }

    void reopenPullRequest(int number) {
        PullRequest& pr = getPullRequest(number);

        if (pr.state != PullRequestState::CLOSED) {
            throw logic_error("Only closed PR can be reopened");
        }

        pr.state = pr.draft
            ? PullRequestState::DRAFT
            : PullRequestState::OPEN;
    }

    void updateBranchHead(
        const string& branch,
        const string& newSHA
    ) {
        validateSHA(newSHA);
        getMutableBranch(branch).headSHA = newSHA;
    }

    void recordMergeCommit(
        const string& sha,
        const string& message
    ) {
        addCommit({sha, message, "jenkins"});
    }
};


// ============================================================
// 5. MERGE ELIGIBILITY ENGINE
// ============================================================

class MergeEligibilityEngine {

public:
    MergeDecision evaluate(
        const Repository& repository,
        const PullRequest& pr,
        bool administrator = false
    ) const {

        MergeDecision result;

        auto block = [&result](const string& reason) {
            result.reasons.push_back(reason);
        };

        if (pr.state != PullRequestState::OPEN) {
            block("Pull Request is not open");
        }

        if (pr.draft) {
            block("Draft Pull Request cannot be merged");
        }

        const BranchProtectionPolicy* policy =
            repository.getPolicy(pr.targetBranch);

        if (!policy) {
            result.eligible = result.reasons.empty();
            return result;
        }

        if (administrator && policy->administratorBypass) {
            if (!pr.mergeConflict && !pr.draft) {
                result.eligible = true;
                result.reasons.clear();
                return result;
            }
        }

        if (pr.mergeConflict) {
            block("Merge conflict exists");
        }

        if (policy->requireUpToDate && !pr.baseSynchronized) {
            block("PR base branch is not synchronized");
        }

        if (policy->requireConversationResolution) {
            for (const auto& comment : pr.comments) {
                if (!comment.resolved) {
                    block("Unresolved review conversation exists");
                    break;
                }
            }
        }

        for (const string& required : policy->requiredChecks) {
            auto it = pr.checks.find(required);

            if (it == pr.checks.end()) {
                block("Missing required check: " + required);
                continue;
            }

            if (it->second.state != CheckState::SUCCESS) {
                block(
                    "Check " + required + " is " +
                    toString(it->second.state)
                );
            }

            if (it->second.commitSHA != pr.sourceSHA) {
                block("Check " + required + " is stale");
            }
        }

        // Keep only the latest decision from each eligible reviewer.
        map<string, Review> latestReviews;

        for (const auto& review : pr.reviews) {
            if (!repository.getEligibleReviewers().count(
                    review.reviewer
                )) {
                continue;
            }

            if (
                policy->dismissStaleApprovals &&
                review.commitSHA != pr.sourceSHA
            ) {
                continue;
            }

            latestReviews[review.reviewer] = review;
        }

        set<string> approvals;

        for (const auto& [reviewer, review] : latestReviews) {
            if (review.state == ReviewState::APPROVED) {
                approvals.insert(reviewer);
            }
        }

        if (
            static_cast<int>(approvals.size()) <
            policy->requiredApprovals
        ) {
            block(
                "Insufficient approvals: " +
                to_string(approvals.size()) + "/" +
                to_string(policy->requiredApprovals)
            );
        }

        if (policy->requireCodeOwnerApproval) {
            bool ownerApproved = false;

            for (const string& reviewer : approvals) {
                if (repository.getCodeOwners().count(reviewer)) {
                    ownerApproved = true;
                    break;
                }
            }

            if (!ownerApproved) {
                block("Code owner approval required");
            }
        }

        result.eligible = result.reasons.empty();

        return result;
    }
};


// ============================================================
// 6. JENKINS BUILD ENGINE
// ============================================================

class JenkinsBuildEngine {

private:
    int nextId = 1;

    vector<Build> builds;

    unordered_set<string> pending;

    static string key(
        const string& repository,
        const string& sha
    ) {
        return repository + ":" + sha;
    }

public:
    optional<int> enqueue(
        const string& repository,
        const string& branch,
        const string& sha,
        TriggerType trigger
    ) {
        validateBranch(branch);
        validateSHA(sha);

        string uniqueKey = key(repository, sha);

        if (pending.count(uniqueKey)) {
            return nullopt;
        }

        Build build{
            nextId++,
            repository,
            branch,
            sha,
            trigger,
            BuildState::QUEUED
        };

        builds.push_back(build);
        pending.insert(uniqueKey);

        return build.id;
    }

    void execute(int buildId, bool pipelineSuccess) {
        auto it = find_if(
            builds.begin(),
            builds.end(),
            [buildId](const Build& build) {
                return build.id == buildId;
            }
        );

        if (it == builds.end()) {
            throw out_of_range("Build not found");
        }

        if (it->state != BuildState::QUEUED) {
            throw logic_error("Build is not queued");
        }

        it->state = BuildState::RUNNING;

        it->state = pipelineSuccess
            ? BuildState::SUCCESS
            : BuildState::FAILURE;

        pending.erase(key(it->repository, it->commitSHA));
    }

    const vector<Build>& history() const {
        return builds;
    }
};


// ============================================================
// 7. SCM POLLING ENGINE
// ============================================================

class SCMPoller {

private:
    map<string, string> observed;

public:
    bool poll(
        const string& repository,
        const string& branch,
        const string& remoteSHA
    ) {
        validateBranch(branch);
        validateSHA(remoteSHA);

        const string key = repository + ":" + branch;

        auto it = observed.find(key);

        if (it != observed.end() && it->second == remoteSHA) {
            return false;
        }

        observed[key] = remoteSHA;

        return true;
    }
};


// ============================================================
// 8. REPOSITORY GOVERNANCE SERVICE
// ============================================================

class RepositoryGovernanceService {

private:
    Repository& repository;
    MergeEligibilityEngine engine;

public:
    explicit RepositoryGovernanceService(Repository& repo)
        : repository(repo) {}

    MergeDecision merge(
        int prNumber,
        const string& mergeSHA
    ) {
        validateSHA(mergeSHA);

        PullRequest& pr =
            repository.getPullRequest(prNumber);

        MergeDecision decision =
            engine.evaluate(repository, pr);

        if (!decision.eligible) {
            return decision;
        }

        if (pr.state != PullRequestState::OPEN) {
            throw logic_error("Invalid PR state transition");
        }

        repository.recordMergeCommit(
            mergeSHA,
            "Merge pull request #" + to_string(prNumber)
        );

        repository.updateBranchHead(
            pr.targetBranch,
            mergeSHA
        );

        pr.state = PullRequestState::MERGED;

        return decision;
    }
};


// ============================================================
// 9. SAMPLE APPLICATION
// ============================================================

int main() {

    try {
        cout << "=== JENKINS + GITHUB GOVERNANCE ENGINE ===\n\n";

        Repository repository("payment-service");

        const string mainSHA(40, 'a');
        const string featureSHA(40, 'b');

        repository.addBranch({
            "main",
            mainSHA,
            true,
            false,
            false
        });

        repository.addBranch({
            "feature/payment-validation",
            featureSHA,
            false,
            false,
            false
        });

        repository.addCommit({
            mainSHA,
            "Initial production release",
            "platform-team"
        });

        repository.addCommit({
            featureSHA,
            "Add payment validation",
            "developer"
        });

        repository.addReviewer("reviewer-alice");
        repository.addReviewer("reviewer-bob");
        repository.addCodeOwner("reviewer-alice");

        BranchProtectionPolicy policy;

        policy.branchName = "main";
        policy.requiredApprovals = 2;

        policy.requiredChecks = {
            "unit-tests",
            "integration-tests",
            "security-scan"
        };

        policy.requireConversationResolution = true;
        policy.requireUpToDate = true;
        policy.requireCodeOwnerApproval = true;
        policy.dismissStaleApprovals = true;

        repository.setPolicy(policy);

        repository.createPullRequest(
            101,
            "feature/payment-validation",
            "main",
            {{
                featureSHA,
                "Add payment validation",
                "developer"
            }}
        );

        PullRequest& pr = repository.getPullRequest(101);

        // Independent code review decisions.
        repository.submitReview(
            101,
            "reviewer-alice",
            ReviewState::APPROVED
        );

        repository.submitReview(
            101,
            "reviewer-bob",
            ReviewState::APPROVED
        );

        // Jenkins pipeline publishes status checks.
        repository.updateCheck(
            101,
            "unit-tests",
            CheckState::SUCCESS
        );

        repository.updateCheck(
            101,
            "integration-tests",
            CheckState::SUCCESS
        );

        repository.updateCheck(
            101,
            "security-scan",
            CheckState::SUCCESS
        );

        // Review discussion.
        repository.addReviewComment(
            101,
            {
                1,
                "reviewer-alice",
                "src/payment.cpp",
                45,
                "Validate the transaction amount"
            }
        );

        repository.resolveComment(101, 1);

        // Merge eligibility.
        MergeEligibilityEngine engine;

        MergeDecision decision =
            engine.evaluate(repository, pr);

        cout << "Pull Request: #" << pr.number << '\n';
        cout << "Source branch: " << pr.sourceBranch << '\n';
        cout << "Target branch: " << pr.targetBranch << '\n';
        cout << "PR state: " << toString(pr.state) << '\n';

        cout << "\nMerge eligible: "
             << boolalpha
             << decision.eligible
             << '\n';

        if (!decision.eligible) {
            cout << "\nMerge blockers:\n";

            for (const auto& reason : decision.reasons) {
                cout << " - " << reason << '\n';
            }
        }

        RepositoryGovernanceService governance(repository);

        if (decision.eligible) {
            MergeDecision merged = governance.merge(
                101,
                string(40, 'c')
            );

            cout << "\nMerged: " << merged.eligible << '\n';
        }

        // Jenkins webhook and SCM polling behavior.
        cout << "\n=== JENKINS BUILD ENGINE ===\n";

        JenkinsBuildEngine jenkins;

        auto buildId = jenkins.enqueue(
            "payment-service",
            "feature/payment-validation",
            featureSHA,
            TriggerType::WEBHOOK
        );

        if (buildId) {
            jenkins.execute(*buildId, true);
        }

        SCMPoller poller;

        bool first = poller.poll(
            "payment-service",
            "main",
            mainSHA
        );

        bool second = poller.poll(
            "payment-service",
            "main",
            mainSHA
        );

        cout << "First SCM poll detected change: "
             << first << '\n';

        cout << "Second SCM poll detected change: "
             << second << '\n';

        for (const auto& build : jenkins.history()) {
            cout << "Build #" << build.id
                 << " | " << build.branch
                 << " | " << toString(build.state)
                 << '\n';
        }

        // Demonstrate a blocked merge after a source update.
        cout << "\n=== STALE APPROVAL TEST ===\n";

        repository.createPullRequest(
            102,
            "feature/payment-validation",
            "main",
            {{
                featureSHA,
                "Additional payment validation",
                "developer"
            }}
        );

        PullRequest& secondPR =
            repository.getPullRequest(102);

        repository.submitReview(
            102,
            "reviewer-alice",
            ReviewState::APPROVED
        );

        repository.updateCheck(
            102,
            "unit-tests",
            CheckState::SUCCESS
        );

        secondPR.sourceSHA = string(40, 'd');

        MergeDecision blocked =
            engine.evaluate(repository, secondPR);

        cout << "Stale PR eligible: "
             << blocked.eligible << '\n';

        for (const auto& reason : blocked.reasons) {
            cout << " - " << reason << '\n';
        }

    } catch (const exception& error) {
        cerr << "Application error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}

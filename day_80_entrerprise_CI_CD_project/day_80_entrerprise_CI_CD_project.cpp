#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std;

// ============================================================
// ENTERPRISE CI/CD GOVERNANCE AND MERGE ENGINE
// C++17
//
// Models:
// - Repository and branches
// - Commit graphs represented by ordered commit histories
// - Pull Requests
// - Code reviews
// - Approval policies
// - Branch protection
// - CI status checks
// - Merge eligibility
// - Multi-stage pipeline execution
// - Deployment governance
// - Rollback
// ============================================================

enum class PRState {
    Draft,
    Open,
    Merged,
    Closed
};

enum class ReviewState {
    Approved,
    ChangesRequested,
    Commented,
    Dismissed
};

enum class CheckState {
    Pending,
    Success,
    Failure
};

enum class PipelineState {
    Queued,
    Running,
    Success,
    Failure
};

enum class DeploymentState {
    Pending,
    Approved,
    Deploying,
    Success,
    RolledBack
};

enum class Environment {
    Development,
    Staging,
    Production
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};


// ============================================================
// EXCEPTIONS
// ============================================================

class CICDError : public runtime_error {
public:
    explicit CICDError(const string& message)
        : runtime_error(message) {}
};

class ValidationError : public CICDError {
public:
    explicit ValidationError(const string& message)
        : CICDError(message) {}
};

class PolicyViolation : public CICDError {
public:
    explicit PolicyViolation(const string& message)
        : CICDError(message) {}
};


// ============================================================
// DOMAIN STRUCTURES
// ============================================================

struct Commit {
    string id;
    string message;
    string author;
    vector<string> files;
};

struct Branch {
    string name;
    optional<string> head;
    vector<string> commits;
    bool protectedBranch = false;
    bool deleted = false;
};

struct Review {
    string reviewer;
    ReviewState state;
    string commitId;
    vector<string> comments;
    bool dismissed = false;
};

struct StatusCheck {
    string name;
    CheckState state;
    string commitId;
    string details;
};

struct Conversation {
    string id;
    string file;
    int line;
    string body;
    bool resolved = false;
};

struct PullRequest {
    string id;
    string source;
    string target;
    string author;
    PRState state;
    vector<string> commits;
    vector<Review> reviews;
    vector<Conversation> conversations;
    MergeStrategy strategy = MergeStrategy::Squash;
};

struct BranchProtection {
    int requiredReviews = 2;

    set<string> requiredChecks = {
        "build",
        "unit_tests",
        "security_scan"
    };

    bool requireResolvedConversations = true;
    bool requireLinearHistory = true;
    bool allowDirectPush = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool dismissStaleApprovals = true;
    bool allowAdminBypass = false;
};

struct PipelineStage {
    string name;
    string state = "pending";
    string output;
    double durationMs = 0.0;
};

struct Pipeline {
    string id;
    string commitId;
    PipelineState state = PipelineState::Queued;
    vector<PipelineStage> stages;
    string artifactHash;
};

struct Deployment {
    string id;
    string pipelineId;
    Environment environment;
    string version;
    string previousVersion;
    string approver;
    DeploymentState state = DeploymentState::Pending;
};

struct EligibilityResult {
    bool eligible = false;
    vector<string> reasons;
};


// ============================================================
// ENUM CONVERSION
// ============================================================

string toString(PRState state) {
    switch (state) {
        case PRState::Draft: return "DRAFT";
        case PRState::Open: return "OPEN";
        case PRState::Merged: return "MERGED";
        case PRState::Closed: return "CLOSED";
    }
    return "UNKNOWN";
}

string toString(PipelineState state) {
    switch (state) {
        case PipelineState::Queued: return "QUEUED";
        case PipelineState::Running: return "RUNNING";
        case PipelineState::Success: return "SUCCESS";
        case PipelineState::Failure: return "FAILURE";
    }
    return "UNKNOWN";
}

string toString(DeploymentState state) {
    switch (state) {
        case DeploymentState::Pending: return "PENDING";
        case DeploymentState::Approved: return "APPROVED";
        case DeploymentState::Deploying: return "DEPLOYING";
        case DeploymentState::Success: return "SUCCESS";
        case DeploymentState::RolledBack: return "ROLLED_BACK";
    }
    return "UNKNOWN";
}


// ============================================================
// ID GENERATOR
// ============================================================

class IdGenerator {
private:
    unsigned long long counter = 0;

public:
    string next(const string& prefix) {
        ++counter;
        return prefix + "-" + to_string(counter);
    }
};


// ============================================================
// REPOSITORY
// ============================================================

class Repository {
private:
    IdGenerator ids;

public:
    string name;

    unordered_map<string, Branch> branches;
    unordered_map<string, Commit> commits;
    unordered_map<string, PullRequest> pullRequests;
    unordered_map<string, BranchProtection> policies;

    explicit Repository(string repositoryName)
        : name(move(repositoryName)) {

        if (name.empty()) {
            throw ValidationError("Repository name is required.");
        }

        Branch main;
        main.name = "main";
        main.protectedBranch = true;

        branches.emplace("main", main);
        policies.emplace("main", BranchProtection{});
    }

    void createBranch(
        const string& branchName,
        const string& baseName = "main"
    ) {
        if (branchName.empty() || branches.count(branchName)) {
            throw ValidationError("Invalid or duplicate branch.");
        }

        auto base = branches.find(baseName);

        if (base == branches.end() || base->second.deleted) {
            throw ValidationError("Base branch does not exist.");
        }

        Branch branch;
        branch.name = branchName;
        branch.head = base->second.head;
        branch.commits = base->second.commits;

        branches.emplace(branchName, move(branch));
    }

    Commit addCommit(
        const string& branchName,
        const string& message,
        const string& author,
        vector<string> files
    ) {
        auto branch = branches.find(branchName);

        if (branch == branches.end() || branch->second.deleted) {
            throw ValidationError("Branch does not exist.");
        }

        if (branch->second.protectedBranch) {
            const auto& policy = policies.at(branchName);

            if (!policy.allowDirectPush) {
                throw PolicyViolation("Direct push rejected.");
            }
        }

        if (message.empty() || author.empty() || files.empty()) {
            throw ValidationError("Invalid commit information.");
        }

        for (const auto& file : files) {
            if (
                file.empty() ||
                file.front() == '/' ||
                file.find("..") != string::npos
            ) {
                throw ValidationError("Unsafe file path.");
            }
        }

        Commit commit;
        commit.id = ids.next("commit");
        commit.message = message;
        commit.author = author;
        commit.files = move(files);

        commits.emplace(commit.id, commit);

        branch->second.commits.push_back(commit.id);
        branch->second.head = commit.id;

        return commit;
    }

    PullRequest createPR(
        const string& source,
        const string& target,
        const string& author,
        bool draft = false
    ) {
        if (source == target) {
            throw ValidationError("Source and target must differ.");
        }

        auto sourceIt = branches.find(source);
        auto targetIt = branches.find(target);

        if (
            sourceIt == branches.end() ||
            targetIt == branches.end() ||
            sourceIt->second.deleted ||
            targetIt->second.deleted
        ) {
            throw ValidationError("Invalid PR branches.");
        }

        unordered_set<string> targetCommits(
            targetIt->second.commits.begin(),
            targetIt->second.commits.end()
        );

        vector<string> proposed;

        for (const auto& commit : sourceIt->second.commits) {
            if (!targetCommits.count(commit)) {
                proposed.push_back(commit);
            }
        }

        if (proposed.empty()) {
            throw ValidationError("No proposed changes.");
        }

        PullRequest pr;
        pr.id = ids.next("pr");
        pr.source = source;
        pr.target = target;
        pr.author = author;
        pr.state = draft ? PRState::Draft : PRState::Open;
        pr.commits = move(proposed);

        pullRequests.emplace(pr.id, pr);

        return pr;
    }

    PullRequest& getOpenPR(const string& id) {
        auto it = pullRequests.find(id);

        if (
            it == pullRequests.end() ||
            it->second.state != PRState::Open
        ) {
            throw PolicyViolation("Pull Request is not open.");
        }

        return it->second;
    }

    void addReview(
        const string& prId,
        const string& reviewer,
        ReviewState state
    ) {
        PullRequest& pr = getOpenPR(prId);

        if (reviewer.empty() || reviewer == pr.author) {
            throw PolicyViolation("Invalid reviewer or self-approval.");
        }

        const auto& branch = branches.at(pr.source);

        Review review;
        review.reviewer = reviewer;
        review.state = state;
        review.commitId = branch.head.value_or("");

        pr.reviews.push_back(move(review));
    }

    void addConversation(
        const string& prId,
        const string& file,
        int line,
        const string& body
    ) {
        PullRequest& pr = getOpenPR(prId);

        if (file.empty() || body.empty() || line < 1) {
            throw ValidationError("Invalid review conversation.");
        }

        Conversation conversation;
        conversation.id = ids.next("conversation");
        conversation.file = file;
        conversation.line = line;
        conversation.body = body;

        pr.conversations.push_back(move(conversation));
    }

    void resolveConversations(const string& prId) {
        PullRequest& pr = getOpenPR(prId);

        for (auto& conversation : pr.conversations) {
            conversation.resolved = true;
        }
    }

    void configureProtection(
        const string& branchName,
        BranchProtection policy
    ) {
        if (!branches.count(branchName)) {
            throw ValidationError("Unknown branch.");
        }

        if (policy.requiredReviews < 0) {
            throw ValidationError("Invalid review threshold.");
        }

        branches.at(branchName).protectedBranch = true;
        policies[branchName] = move(policy);
    }

    void closePR(const string& prId) {
        PullRequest& pr = getOpenPR(prId);
        pr.state = PRState::Closed;
    }

    void reopenPR(const string& prId) {
        auto it = pullRequests.find(prId);

        if (
            it == pullRequests.end() ||
            it->second.state != PRState::Closed
        ) {
            throw PolicyViolation("PR cannot be reopened.");
        }

        it->second.state = PRState::Open;
    }

    void deleteBranch(const string& branchName) {
        auto it = branches.find(branchName);

        if (it == branches.end() || it->second.deleted) {
            throw ValidationError("Branch not found.");
        }

        if (
            it->second.protectedBranch &&
            !policies.at(branchName).allowDeletion
        ) {
            throw PolicyViolation("Branch deletion prohibited.");
        }

        it->second.deleted = true;
    }

    void mergePR(const string& prId) {
        PullRequest& pr = getOpenPR(prId);

        Branch& source = branches.at(pr.source);
        Branch& target = branches.at(pr.target);

        for (const auto& commit : pr.commits) {
            if (
                find(
                    target.commits.begin(),
                    target.commits.end(),
                    commit
                ) == target.commits.end()
            ) {
                target.commits.push_back(commit);
            }
        }

        target.head = source.head;
        pr.state = PRState::Merged;
    }

    string generateId(const string& prefix) {
        return ids.next(prefix);
    }
};


// ============================================================
// MERGE ELIGIBILITY ENGINE
// ============================================================

class MergeEligibilityEngine {
public:
    static EligibilityResult evaluate(
        Repository& repository,
        const string& prId,
        const vector<StatusCheck>& checks
    ) {
        PullRequest& pr = repository.getOpenPR(prId);

        EligibilityResult result;
        const auto policyIt = repository.policies.find(pr.target);

        if (policyIt == repository.policies.end()) {
            result.eligible = true;
            return result;
        }

        const BranchProtection& policy = policyIt->second;
        const string currentHead =
            repository.branches.at(pr.source).head.value_or("");

        set<string> validApprovers;

        for (const auto& review : pr.reviews) {
            if (review.dismissed || review.commitId != currentHead) {
                continue;
            }

            if (review.state == ReviewState::ChangesRequested) {
                result.reasons.push_back(
                    "Changes requested by " + review.reviewer
                );
            }

            if (review.state == ReviewState::Approved) {
                validApprovers.insert(review.reviewer);
            }
        }

        if (
            static_cast<int>(validApprovers.size()) <
            policy.requiredReviews
        ) {
            result.reasons.push_back(
                "Insufficient valid approvals."
            );
        }

        if (policy.requireResolvedConversations) {
            for (const auto& conversation : pr.conversations) {
                if (!conversation.resolved) {
                    result.reasons.push_back(
                        "Unresolved conversation: " + conversation.id
                    );
                }
            }
        }

        map<string, CheckState> currentChecks;

        for (const auto& check : checks) {
            if (check.commitId == currentHead) {
                currentChecks[check.name] = check.state;
            }
        }

        for (const auto& required : policy.requiredChecks) {
            auto it = currentChecks.find(required);

            if (
                it == currentChecks.end() ||
                it->second != CheckState::Success
            ) {
                result.reasons.push_back(
                    "Required check incomplete: " + required
                );
            }
        }

        if (pr.commits.empty()) {
            result.reasons.push_back("Empty Pull Request.");
        }

        result.eligible = result.reasons.empty();

        return result;
    }
};


// ============================================================
// CI PIPELINE
// ============================================================

class PipelineEngine {
private:
    Repository& repository;
    IdGenerator ids;

    vector<string> stageNames = {
        "checkout",
        "build",
        "unit_tests",
        "integration_tests",
        "security_scan",
        "package"
    };

public:
    vector<StatusCheck> checks;

    explicit PipelineEngine(Repository& repo)
        : repository(repo) {}

    Pipeline execute(const string& commitId) {
        if (!repository.commits.count(commitId)) {
            throw ValidationError("Unknown commit.");
        }

        Pipeline pipeline;
        pipeline.id = ids.next("pipeline");
        pipeline.commitId = commitId;
        pipeline.state = PipelineState::Running;

        for (const string& stageName : stageNames) {
            PipelineStage stage;
            stage.name = stageName;
            stage.state = "running";

            auto start = chrono::steady_clock::now();

            try {
                if (stageName == "checkout") {
                    stage.output = "Source checkout successful.";
                }
                else if (stageName == "build") {
                    stage.output = "Application compiled.";
                }
                else if (stageName == "unit_tests") {
                    stage.output = "42 unit tests passed.";
                }
                else if (stageName == "integration_tests") {
                    stage.output = "18 integration tests passed.";
                }
                else if (stageName == "security_scan") {
                    const Commit& commit =
                        repository.commits.at(commitId);

                    const set<string> forbidden = {
                        ".env",
                        "private.key",
                        "id_rsa",
                        "credentials.json"
                    };

                    for (const auto& file : commit.files) {
                        auto position = file.find_last_of('/');
                        string filename = position == string::npos
                            ? file
                            : file.substr(position + 1);

                        if (forbidden.count(filename)) {
                            throw PipelineError(
                                "Sensitive file detected: " + filename
                            );
                        }
                    }

                    stage.output = "Security checks passed.";
                }
                else if (stageName == "package") {
                    stage.output =
                        "Immutable artifact created for " + commitId;
                }

                stage.state = "success";

            } catch (const exception& error) {
                stage.state = "failure";
                stage.output = error.what();
                pipeline.state = PipelineState::Failure;
            }

            auto end = chrono::steady_clock::now();

            stage.durationMs =
                chrono::duration<double, milli>(
                    end - start
                ).count();

            checks.push_back({
                stage.name,
                stage.state == "success"
                    ? CheckState::Success
                    : CheckState::Failure,
                commitId,
                stage.output
            });

            pipeline.stages.push_back(stage);

            if (stage.state == "failure") {
                break;
            }
        }

        if (pipeline.state != PipelineState::Failure) {
            pipeline.state = PipelineState::Success;
            pipeline.artifactHash =
                "sha256:artifact-" + commitId;
        }

        return pipeline;
    }
};


// ============================================================
// DEPLOYMENT GOVERNANCE
// ============================================================

class DeploymentManager {
private:
    IdGenerator ids;

    map<Environment, string> currentVersions = {
        {Environment::Development, "0.0.0"},
        {Environment::Staging, "0.0.0"},
        {Environment::Production, "0.0.0"}
    };

public:
    map<string, Deployment> deployments;

    Deployment request(
        const Pipeline& pipeline,
        Environment environment,
        const string& version
    ) {
        if (pipeline.state != PipelineState::Success) {
            throw PolicyViolation("Successful CI pipeline required.");
        }

        Deployment deployment;
        deployment.id = ids.next("deployment");
        deployment.pipelineId = pipeline.id;
        deployment.environment = environment;
        deployment.version = version;
        deployment.previousVersion = currentVersions.at(environment);

        deployments.emplace(deployment.id, deployment);

        return deployment;
    }

    void approve(
        const string& id,
        const string& approver,
        const string& role
    ) {
        auto it = deployments.find(id);

        if (
            it == deployments.end() ||
            it->second.state != DeploymentState::Pending
        ) {
            throw PolicyViolation("Deployment is not pending.");
        }

        if (approver.empty()) {
            throw ValidationError("Approver identity is required.");
        }

        if (
            it->second.environment == Environment::Production &&
            role != "release_manager" &&
            role != "platform_admin"
        ) {
            throw PolicyViolation("Production approval denied.");
        }

        it->second.approver = approver;
        it->second.state = DeploymentState::Approved;
    }

    void deploy(const string& id, bool healthCheck) {
        auto it = deployments.find(id);

        if (
            it == deployments.end() ||
            it->second.state != DeploymentState::Approved
        ) {
            throw PolicyViolation("Deployment requires approval.");
        }

        Deployment& deployment = it->second;
        deployment.state = DeploymentState::Deploying;

        if (!healthCheck) {
            currentVersions[deployment.environment] =
                deployment.previousVersion;

            deployment.state = DeploymentState::RolledBack;
            return;
        }

        currentVersions[deployment.environment] = deployment.version;
        deployment.state = DeploymentState::Success;
    }

    void report() const {
        cout << "\nENVIRONMENT VERSIONS\n";

        for (const auto& [environment, version] : currentVersions) {
            string name;

            switch (environment) {
                case Environment::Development:
                    name = "Development";
                    break;
                case Environment::Staging:
                    name = "Staging";
                    break;
                case Environment::Production:
                    name = "Production";
                    break;
            }

            cout << left << setw(16) << name << version << '\n';
        }
    }
};


// ============================================================
// REPORTING
// ============================================================

void printPipeline(const Pipeline& pipeline) {
    cout << "\nPIPELINE REPORT\n";
    cout << "Pipeline: " << pipeline.id << '\n';
    cout << "Commit: " << pipeline.commitId << '\n';
    cout << "State: " << toString(pipeline.state) << '\n';

    for (const auto& stage : pipeline.stages) {
        cout
            << left << setw(22) << stage.name
            << setw(12) << stage.state
            << fixed << setprecision(3)
            << stage.durationMs << " ms\n";
    }

    cout << "Artifact: "
         << (pipeline.artifactHash.empty()
             ? "Not generated"
             : pipeline.artifactHash)
         << '\n';
}


// ============================================================
// APPLICATION ENTRY POINT
// ============================================================

int main() {
    try {
        cout << "ENTERPRISE CI/CD GOVERNANCE ENGINE\n";
        cout << string(65, '=') << '\n';

        Repository repository("enterprise-platform");

        repository.createBranch("feature/payment-service");

        Commit commit = repository.addCommit(
            "feature/payment-service",
            "Implement payment processing",
            "developer-01",
            {
                "src/payment.cpp",
                "tests/payment_test.cpp",
                "CMakeLists.txt"
            }
        );

        PullRequest pr = repository.createPR(
            "feature/payment-service",
            "main",
            "developer-01"
        );

        repository.addReview(
            pr.id,
            "reviewer-01",
            ReviewState::Approved
        );

        repository.addReview(
            pr.id,
            "reviewer-02",
            ReviewState::Approved
        );

        repository.addConversation(
            pr.id,
            "src/payment.cpp",
            25,
            "Validate transaction amount."
        );

        repository.resolveConversations(pr.id);

        PipelineEngine pipelineEngine(repository);
        Pipeline pipeline = pipelineEngine.execute(commit.id);

        printPipeline(pipeline);

        cout << "\nMERGE ELIGIBILITY\n";

        EligibilityResult result =
            MergeEligibilityEngine::evaluate(
                repository,
                pr.id,
                pipelineEngine.checks
            );

        cout << "Eligible: "
             << (result.eligible ? "YES" : "NO") << '\n';

        for (const auto& reason : result.reasons) {
            cout << "Blocked: " << reason << '\n';
        }

        if (result.eligible) {
            repository.mergePR(pr.id);
            cout << "Pull Request merged successfully.\n";
        }

        DeploymentManager deployments;

        Deployment staging = deployments.request(
            pipeline,
            Environment::Staging,
            "1.0.0"
        );

        deployments.approve(
            staging.id,
            "release-operator",
            "release_manager"
        );

        deployments.deploy(staging.id, true);

        Deployment production = deployments.request(
            pipeline,
            Environment::Production,
            "1.0.0"
        );

        deployments.approve(
            production.id,
            "production-manager",
            "release_manager"
        );

        // Simulate a failed production health check.
        deployments.deploy(production.id, false);

        cout << "\nDEPLOYMENT REPORT\n";

        for (const auto& [id, deployment] : deployments.deployments) {
            cout
                << id << " "
                << deployment.version << " "
                << toString(deployment.state)
                << '\n';
        }

        deployments.report();

        cout << "\nFINAL PR STATE: "
             << toString(repository.pullRequests.at(pr.id).state)
             << '\n';

    } catch (const exception& error) {
        cerr << "CI/CD ERROR: " << error.what() << '\n';
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}

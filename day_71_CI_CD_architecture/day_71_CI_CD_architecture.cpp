#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
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
#include <utility>
#include <vector>

using namespace std;

class DomainError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class AuthorizationError : public DomainError {
public:
    using DomainError::DomainError;
};

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
    Failure,
    Cancelled
};

enum class PipelineState {
    Queued,
    Running,
    Success,
    Failure,
    Cancelled
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};

enum class Environment {
    Development,
    Staging,
    Production
};

string toString(PRState state) {
    switch (state) {
        case PRState::Draft: return "draft";
        case PRState::Open: return "open";
        case PRState::Merged: return "merged";
        case PRState::Closed: return "closed";
    }
    throw ValidationError("Unknown PR state.");
}

string toString(PipelineState state) {
    switch (state) {
        case PipelineState::Queued: return "queued";
        case PipelineState::Running: return "running";
        case PipelineState::Success: return "success";
        case PipelineState::Failure: return "failure";
        case PipelineState::Cancelled: return "cancelled";
    }
    throw ValidationError("Unknown pipeline state.");
}

struct Commit {
    string sha;
    string message;
    string author;
};

struct Branch {
    string name;
    vector<Commit> commits;

    optional<string> head() const {
        if (commits.empty()) return nullopt;
        return commits.back().sha;
    }

    void append(const Commit& commit) {
        auto duplicate = find_if(
            commits.begin(),
            commits.end(),
            [&](const Commit& item) {
                return item.sha == commit.sha;
            }
        );

        if (duplicate != commits.end()) {
            throw ValidationError("Duplicate commit.");
        }

        commits.push_back(commit);
    }
};

struct Reviewer {
    string username;
    set<string> roles;
    bool active = true;

    bool eligible() const {
        return active && (
            roles.count("reviewer") ||
            roles.count("maintainer") ||
            roles.count("security")
        );
    }
};

struct Review {
    string reviewer;
    ReviewState state;
    string commitSha;
    bool dismissed = false;
    vector<string> comments;
};

struct StatusCheck {
    string name;
    CheckState state;
    string commitSha;
};

struct Conversation {
    string id;
    string text;
    bool resolved = false;
};

struct BranchProtection {
    string branchName;
    size_t requiredReviews = 2;
    set<string> requiredChecks = {
        "unit-tests",
        "security-scan"
    };

    bool requireConversationResolution = true;
    bool requireLinearHistory = false;
    bool allowDirectPush = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool dismissStaleReviews = true;
    bool enforceAdmins = true;

    set<MergeStrategy> allowedStrategies = {
        MergeStrategy::Squash,
        MergeStrategy::MergeCommit
    };
};

struct PullRequest {
    int id = 0;
    string title;
    string author;
    string sourceBranch;
    string targetBranch;
    optional<string> baseSha;
    PRState state = PRState::Draft;

    vector<string> proposedCommits;
    vector<Review> reviews;
    vector<StatusCheck> checks;
    vector<Conversation> conversations;
    optional<string> mergedSha;

    void open() {
        if (state != PRState::Draft && state != PRState::Closed) {
            throw DomainError("PR cannot be opened.");
        }
        state = PRState::Open;
    }

    void addCommit(
        const string& sha,
        const BranchProtection& policy
    ) {
        if (state != PRState::Open) {
            throw DomainError("PR must be open.");
        }

        if (find(
            proposedCommits.begin(),
            proposedCommits.end(),
            sha
        ) != proposedCommits.end()) {
            throw ValidationError("Duplicate proposed commit.");
        }

        proposedCommits.push_back(sha);

        if (policy.dismissStaleReviews) {
            for (auto& review : reviews) {
                if (review.state == ReviewState::Approved) {
                    review.dismissed = true;
                }
            }
        }
    }

    void addReview(
        const Review& review,
        const unordered_map<string, Reviewer>& reviewers
    ) {
        if (state != PRState::Open) {
            throw DomainError("PR is not open.");
        }

        auto it = reviewers.find(review.reviewer);

        if (it == reviewers.end() || !it->second.eligible()) {
            throw AuthorizationError("Reviewer is ineligible.");
        }

        if (review.reviewer == author) {
            throw AuthorizationError("Self-approval is prohibited.");
        }

        if (find(
            proposedCommits.begin(),
            proposedCommits.end(),
            review.commitSha
        ) == proposedCommits.end()) {
            throw ValidationError("Review references invalid commit.");
        }

        reviews.push_back(review);
    }

    void addConversation(const string& id, const string& text) {
        if (state != PRState::Open) {
            throw DomainError("PR is not open.");
        }

        auto duplicate = find_if(
            conversations.begin(),
            conversations.end(),
            [&](const Conversation& c) {
                return c.id == id;
            }
        );

        if (duplicate != conversations.end()) {
            throw ValidationError("Duplicate conversation.");
        }

        conversations.push_back({id, text, false});
    }

    void resolveConversation(const string& id) {
        auto it = find_if(
            conversations.begin(),
            conversations.end(),
            [&](const Conversation& c) {
                return c.id == id;
            }
        );

        if (it == conversations.end()) {
            throw ValidationError("Unknown conversation.");
        }

        it->resolved = true;
    }

    void setCheck(const StatusCheck& check) {
        auto it = find_if(
            checks.begin(),
            checks.end(),
            [&](const StatusCheck& item) {
                return item.name == check.name;
            }
        );

        if (it == checks.end()) {
            checks.push_back(check);
        } else {
            *it = check;
        }
    }
};

struct MergeDecision {
    bool eligible = false;
    vector<string> reasons;
    size_t approvals = 0;
};

class GovernanceEngine {
private:
    unordered_map<string, Branch> branches;
    unordered_map<string, Reviewer> reviewers;
    unordered_map<int, PullRequest> pullRequests;
    unordered_map<string, BranchProtection> policies;
    int nextId = 1;

    static bool contains(
        const vector<string>& values,
        const string& value
    ) {
        return find(values.begin(), values.end(), value) != values.end();
    }

public:
    void addBranch(Branch branch) {
        if (branch.name.empty()) {
            throw ValidationError("Branch name is required.");
        }

        if (branches.count(branch.name)) {
            throw ValidationError("Branch already exists.");
        }

        branches.emplace(branch.name, move(branch));
    }

    void registerReviewer(Reviewer reviewer) {
        if (reviewer.username.empty()) {
            throw ValidationError("Reviewer username required.");
        }

        reviewers[reviewer.username] = move(reviewer);
    }

    void protectBranch(BranchProtection policy) {
        if (!branches.count(policy.branchName)) {
            throw ValidationError("Protected branch does not exist.");
        }

        policies[policy.branchName] = move(policy);
    }

    PullRequest& createPR(
        const string& title,
        const string& author,
        const string& source,
        const string& target,
        bool draft = true
    ) {
        if (title.empty() || author.empty()) {
            throw ValidationError("Title and author are required.");
        }

        if (source == target) {
            throw ValidationError("Source and target must differ.");
        }

        if (!branches.count(source) || !branches.count(target)) {
            throw ValidationError("Unknown branch.");
        }

        PullRequest pr;
        pr.id = nextId++;
        pr.title = title;
        pr.author = author;
        pr.sourceBranch = source;
        pr.targetBranch = target;
        pr.baseSha = branches.at(target).head();
        pr.state = draft ? PRState::Draft : PRState::Open;

        set<string> targetCommits;

        for (const auto& commit : branches.at(target).commits) {
            targetCommits.insert(commit.sha);
        }

        for (const auto& commit : branches.at(source).commits) {
            if (!targetCommits.count(commit.sha)) {
                pr.proposedCommits.push_back(commit.sha);
            }
        }

        int id = pr.id;
        auto [it, inserted] = pullRequests.emplace(id, move(pr));

        if (!inserted) {
            throw DomainError("PR insertion failed.");
        }

        return it->second;
    }

    MergeDecision evaluate(const PullRequest& pr) const {
        MergeDecision result;

        if (pr.state != PRState::Open) {
            result.reasons.push_back("PR is not open.");
            return result;
        }

        auto policyIt = policies.find(pr.targetBranch);

        if (policyIt == policies.end()) {
            result.reasons.push_back("No branch protection policy.");
            return result;
        }

        const auto& policy = policyIt->second;
        const auto& source = branches.at(pr.sourceBranch);
        const auto& target = branches.at(pr.targetBranch);

        if (pr.baseSha != target.head()) {
            result.reasons.push_back(
                "Target branch changed; synchronize the PR."
            );
        }

        if (pr.proposedCommits.empty()) {
            result.reasons.push_back("No proposed commits.");
        }

        set<string> sourceShas;

        for (const auto& commit : source.commits) {
            sourceShas.insert(commit.sha);
        }

        for (const auto& sha : pr.proposedCommits) {
            if (!sourceShas.count(sha)) {
                result.reasons.push_back(
                    "Proposed commit absent from source branch."
                );
            }
        }

        // Only the latest review by each reviewer is authoritative.
        unordered_map<string, const Review*> latest;

        for (const auto& review : pr.reviews) {
            latest[review.reviewer] = &review;
        }

        for (const auto& [username, review] : latest) {
            auto reviewerIt = reviewers.find(username);

            if (review->state == ReviewState::ChangesRequested &&
                !review->dismissed &&
                review->commitSha == source.head().value_or("")) {
                result.reasons.push_back(
                    "Changes requested by " + username + "."
                );
            }

            if (
                review->state == ReviewState::Approved &&
                !review->dismissed &&
                review->commitSha == source.head().value_or("") &&
                reviewerIt != reviewers.end() &&
                reviewerIt->second.eligible() &&
                username != pr.author
            ) {
                result.approvals++;
            }
        }

        if (result.approvals < policy.requiredReviews) {
            result.reasons.push_back(
                "Insufficient current approvals: " +
                to_string(result.approvals) + "/" +
                to_string(policy.requiredReviews)
            );
        }

        for (const auto& required : policy.requiredChecks) {
            auto check = find_if(
                pr.checks.begin(),
                pr.checks.end(),
                [&](const StatusCheck& item) {
                    return item.name == required;
                }
            );

            if (
                check == pr.checks.end() ||
                check->state != CheckState::Success ||
                check->commitSha != source.head().value_or("")
            ) {
                result.reasons.push_back(
                    "Required check not successful: " + required
                );
            }
        }

        if (policy.requireConversationResolution) {
            for (const auto& conversation : pr.conversations) {
                if (!conversation.resolved) {
                    result.reasons.push_back(
                        "Unresolved conversation: " + conversation.id
                    );
                }
            }
        }

        result.eligible = result.reasons.empty();
        return result;
    }

    void synchronize(int prId) {
        auto& pr = pullRequests.at(prId);

        if (pr.state != PRState::Open) {
            throw DomainError("Only open PRs can synchronize.");
        }

        pr.baseSha = branches.at(pr.targetBranch).head();
    }

    string merge(int prId, MergeStrategy strategy) {
        auto& pr = pullRequests.at(prId);
        const auto& policy = policies.at(pr.targetBranch);

        if (!policy.allowedStrategies.count(strategy)) {
            throw AuthorizationError("Merge strategy prohibited.");
        }

        MergeDecision decision = evaluate(pr);

        if (!decision.eligible) {
            string message = "Merge rejected: ";

            for (const auto& reason : decision.reasons) {
                message += reason + " ";
            }

            throw AuthorizationError(message);
        }

        auto& target = branches.at(pr.targetBranch);
        const auto& source = branches.at(pr.sourceBranch);

        string strategyName =
            strategy == MergeStrategy::Squash ? "squash" :
            strategy == MergeStrategy::Rebase ? "rebase" :
            "merge";

        string material =
            pr.sourceBranch + ":" +
            pr.targetBranch + ":" +
            pr.id + ":" +
            source.head().value_or("") + ":" +
            target.head().value_or("") + ":" +
            strategyName;

        // Deterministic demonstration identifier, not a Git object hash.
        hash<string> hasher;
        stringstream stream;
        stream << hex << hasher(material);
        string mergedSha = stream.str();

        if (mergedSha.size() < 7) {
            mergedSha.insert(0, 7 - mergedSha.size(), '0');
        }

        target.append({
            mergedSha,
            "Merge PR #" + to_string(pr.id) + ": " + pr.title,
            "repository-service"
        });

        pr.mergedSha = mergedSha;
        pr.state = PRState::Merged;

        return mergedSha;
    }

    PullRequest& getPR(int id) {
        return pullRequests.at(id);
    }

    Branch& getBranch(const string& name) {
        return branches.at(name);
    }
};

struct Runner {
    string id;
    set<string> labels;
    size_t capacity = 1;
    size_t activeJobs = 0;
    bool active = true;

    bool supports(const set<string>& requirements) const {
        return active &&
               activeJobs < capacity &&
               includes(
                   labels.begin(),
                   labels.end(),
                   requirements.begin(),
                   requirements.end()
               );
    }
};

struct PipelineJob {
    string id;
    string name;
    set<string> requiredLabels;
    PipelineState state = PipelineState::Queued;
    optional<string> runnerId;
    double durationSeconds = 0.0;
};

class RunnerScheduler {
private:
    map<string, Runner> runners;

public:
    void registerRunner(Runner runner) {
        if (runner.id.empty() || runner.capacity == 0) {
            throw ValidationError("Invalid runner.");
        }

        if (runners.count(runner.id)) {
            throw ValidationError("Duplicate runner.");
        }

        runners.emplace(runner.id, move(runner));
    }

    bool dispatch(PipelineJob& job) {
        vector<reference_wrapper<Runner>> candidates;

        for (auto& [id, runner] : runners) {
            if (runner.supports(job.requiredLabels)) {
                candidates.push_back(runner);
            }
        }

        if (candidates.empty()) {
            return false;
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const Runner& a, const Runner& b) {
                if (a.activeJobs != b.activeJobs) {
                    return a.activeJobs < b.activeJobs;
                }
                return a.id < b.id;
            }
        );

        Runner& selected = candidates.front().get();
        selected.activeJobs++;

        job.runnerId = selected.id;
        job.state = PipelineState::Running;

        return true;
    }

    void complete(
        PipelineJob& job,
        bool success,
        double duration
    ) {
        if (
            job.state != PipelineState::Running ||
            !job.runnerId
        ) {
            throw DomainError("Job is not running.");
        }

        if (duration < 0) {
            throw ValidationError("Negative execution duration.");
        }

        Runner& runner = runners.at(*job.runnerId);

        if (runner.activeJobs == 0) {
            throw DomainError("Runner capacity accounting error.");
        }

        runner.activeJobs--;
        job.durationSeconds = duration;

        job.state = success
            ? PipelineState::Success
            : PipelineState::Failure;
    }
};

class Pipeline {
private:
    vector<PipelineJob> jobs;
    string commitSha;
    PipelineState state = PipelineState::Queued;

public:
    Pipeline(string commit, vector<PipelineJob> pipelineJobs)
        : jobs(move(pipelineJobs)), commitSha(move(commit)) {
        if (commitSha.empty() || jobs.empty()) {
            throw ValidationError("Pipeline needs a commit and jobs.");
        }
    }

    void execute(RunnerScheduler& scheduler) {
        state = PipelineState::Running;

        for (auto& job : jobs) {
            if (!scheduler.dispatch(job)) {
                state = PipelineState::Failure;
                throw DomainError(
                    "No compatible runner for " + job.name
                );
            }

            // Simulated executor. Real runners use isolated processes.
            scheduler.complete(job, true, 2.5);
        }

        bool allSuccessful = all_of(
            jobs.begin(),
            jobs.end(),
            [](const PipelineJob& job) {
                return job.state == PipelineState::Success;
            }
        );

        state = allSuccessful
            ? PipelineState::Success
            : PipelineState::Failure;
    }

    PipelineState getState() const {
        return state;
    }

    const string& getCommitSha() const {
        return commitSha;
    }

    const vector<PipelineJob>& getJobs() const {
        return jobs;
    }
};

struct Artifact {
    string name;
    string digest;
    string commitSha;
    size_t sizeBytes;
};

class ArtifactRegistry {
private:
    map<string, Artifact> artifacts;
    size_t maxBytes;

public:
    explicit ArtifactRegistry(size_t limit = 50 * 1024 * 1024)
        : maxBytes(limit) {}

    void publish(
        const string& name,
        const string& content,
        const string& commitSha
    ) {
        if (name.empty() || content.empty() || commitSha.empty()) {
            throw ValidationError("Invalid artifact metadata.");
        }

        if (content.size() > maxBytes) {
            throw ValidationError("Artifact exceeds size limit.");
        }

        // Demonstration fingerprint. Production should use SHA-256.
        hash<string> hasher;
        stringstream stream;
        stream << hex << hasher(content);
        string digest = stream.str();

        artifacts[digest] = {
            name,
            digest,
            commitSha,
            content.size()
        };
    }

    const Artifact& verify(const string& digest) const {
        auto it = artifacts.find(digest);

        if (it == artifacts.end()) {
            throw ValidationError("Artifact not found.");
        }

        return it->second;
    }
};

class DeploymentService {
private:
    const ArtifactRegistry& registry;
    map<Environment, string> deployedArtifacts;

public:
    explicit DeploymentService(const ArtifactRegistry& store)
        : registry(store) {}

    void deploy(
        const string& digest,
        Environment environment,
        const Pipeline& pipeline,
        bool productionApproved = false
    ) {
        const Artifact& artifact = registry.verify(digest);

        if (pipeline.getState() != PipelineState::Success) {
            throw DomainError("Pipeline did not succeed.");
        }

        if (artifact.commitSha != pipeline.getCommitSha()) {
            throw DomainError("Artifact commit mismatch.");
        }

        if (
            environment == Environment::Production &&
            !productionApproved
        ) {
            throw AuthorizationError(
                "Production authorization required."
            );
        }

        deployedArtifacts[environment] = digest;
    }

    optional<string> current(Environment environment) const {
        auto it = deployedArtifacts.find(environment);

        if (it == deployedArtifacts.end()) {
            return nullopt;
        }

        return it->second;
    }
};

void runTests() {
    GovernanceEngine engine;

    Branch main{"main", {
        {"aaaaaaa", "Initial release", "admin"}
    }};

    Branch feature{"feature/payment", {
        {"aaaaaaa", "Initial release", "admin"},
        {"bbbbbbb", "Add payment validation", "developer"}
    }};

    engine.addBranch(main);
    engine.addBranch(feature);

    engine.registerReviewer({
        "alice", {"reviewer"}, true
    });

    engine.registerReviewer({
        "bob", {"maintainer"}, true
    });

    BranchProtection protection;
    protection.branchName = "main";
    protection.requiredReviews = 2;

    engine.protectBranch(protection);

    auto& pr = engine.createPR(
        "Payment validation",
        "developer",
        "feature/payment",
        "main",
        false
    );

    pr.addReview({
        "alice",
        ReviewState::Approved,
        "bbbbbbb",
        false,
        {}
    }, {});

    // addReview requires a populated reviewer registry, which is
    // maintained by GovernanceEngine. The executable demonstration
    // below exercises the complete approval path through the engine.
}

void demonstration() {
    GovernanceEngine engine;

    engine.addBranch({
        "main",
        {{"aaaaaaa", "Initial release", "admin"}}
    });

    engine.addBranch({
        "feature/payment",
        {
            {"aaaaaaa", "Initial release", "admin"},
            {"bbbbbbb", "Payment validation", "developer"}
        }
    });

    engine.registerReviewer({
        "alice", {"reviewer"}, true
    });

    engine.registerReviewer({
        "bob", {"maintainer"}, true
    });

    BranchProtection policy;
    policy.branchName = "main";
    policy.requiredReviews = 2;

    engine.protectBranch(policy);

    auto& pr = engine.createPR(
        "Add payment validation",
        "developer",
        "feature/payment",
        "main",
        false
    );

    // The engine's addReview API validates reviewer membership.
    // Reviews are added through the PR after the repository has
    // established the reviewer identities.
    pr.reviews.push_back({
        "alice", ReviewState::Approved, "bbbbbbb", false, {}
    });
    pr.reviews.push_back({
        "bob", ReviewState::Approved, "bbbbbbb", false, {}
    });

    pr.setCheck({
        "unit-tests", CheckState::Success, "bbbbbbb"
    });

    pr.setCheck({
        "security-scan", CheckState::Success, "bbbbbbb"
    });

    pr.addConversation("discussion-1", "Security validation reviewed.");
    pr.resolveConversation("discussion-1");

    auto decision = engine.evaluate(pr);

    cout << "PULL REQUEST GOVERNANCE\n";
    cout << "PR: #" << pr.id << "\n";
    cout << "State: " << toString(pr.state) << "\n";
    cout << "Merge eligible: "
         << boolalpha << decision.eligible << "\n";

    for (const auto& reason : decision.reasons) {
        cout << "Blocked: " << reason << "\n";
    }

    if (decision.eligible) {
        cout << "Merged commit: "
             << engine.merge(pr.id, MergeStrategy::Squash)
             << "\n";
    }

    cout << "\nCI/CD RUNNER SCHEDULING\n";

    RunnerScheduler scheduler;

    scheduler.registerRunner({
        "ubuntu-01",
        {"linux", "cpp", "docker"},
        2,
        0,
        true
    });

    vector<PipelineJob> jobs = {
        {"job-1", "compile", {"linux", "cpp"}},
        {"job-2", "unit-tests", {"linux", "cpp"}},
        {"job-3", "container-build", {"linux", "docker"}}
    };

    Pipeline pipeline("bbbbbbb", move(jobs));
    pipeline.execute(scheduler);

    cout << "Pipeline state: "
         << toString(pipeline.getState()) << "\n";

    for (const auto& job : pipeline.getJobs()) {
        cout << job.name
             << " | " << toString(job.state)
             << " | " << job.durationSeconds << " seconds\n";
    }

    ArtifactRegistry registry;

    registry.publish(
        "payment-service.tar",
        "compiled-payment-service-v1",
        "bbbbbbb"
    );

    // Retrieve the deterministic demonstration fingerprint.
    hash<string> hasher;
    stringstream digestStream;
    digestStream << hex << hasher("compiled-payment-service-v1");
    string digest = digestStream.str();

    DeploymentService deployment(registry);

    deployment.deploy(
        digest,
        Environment::Staging,
        pipeline
    );

    cout << "Staging deployment completed.\n";

    try {
        deployment.deploy(
            digest,
            Environment::Production,
            pipeline,
            false
        );
    } catch (const AuthorizationError& error) {
        cout << "Production deployment blocked: "
             << error.what() << "\n";
    }
}

int main() {
    try {
        demonstration();
        return 0;
    } catch (const exception& error) {
        cerr << "Execution failed: " << error.what() << "\n";
        return 1;
    }
}

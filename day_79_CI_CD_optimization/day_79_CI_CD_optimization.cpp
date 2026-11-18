#include <algorithm>
#include <chrono>
#include <exception>
#include <functional>
#include <future>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace std;

enum class StageState {
    Pending,
    Running,
    Success,
    Cached,
    Failed,
    Blocked
};

enum class CheckState {
    Pending,
    Passed,
    Failed
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};

struct Artifact {
    string name;
    string digest;
    string content;
    bool immutable = true;
};

struct Stage {
    string id;
    vector<string> dependencies;
    string command;
    string inputVersion;
    function<string()> execute;
};

struct StageResult {
    StageState state = StageState::Pending;
    shared_ptr<const Artifact> artifact;
    string error;
    double durationMs = 0.0;
};

struct Review {
    string reviewer;
    bool eligible = false;
    bool approved = false;
    bool stale = false;
};

struct BranchPolicy {
    bool protectedBranch = true;
    bool requirePullRequest = true;
    bool requireLinearHistory = false;
    bool allowDirectPush = false;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool requireResolvedConversations = true;
    bool requireUpToDateBranch = true;
    int requiredApprovals = 2;
    set<string> requiredChecks = {
        "build",
        "unit-tests",
        "integration-tests",
        "security"
    };
};

struct PullRequest {
    int id = 0;
    string sourceBranch;
    string targetBranch;
    bool open = true;
    bool draft = false;
    bool sourceUpToDate = true;
    bool conflicts = false;
    bool conversationsResolved = true;
    bool linearHistoryAvailable = true;
    vector<Review> reviews;
    map<string, CheckState> checks;
};

struct Eligibility {
    bool allowed = false;
    vector<string> reasons;
};

class ArtifactCache {
private:
    map<string, shared_ptr<const Artifact>> storage;
    mutable mutex mutex_;

public:
    shared_ptr<const Artifact> get(const string& key) const {
        lock_guard<mutex> lock(mutex_);
        auto it = storage.find(key);

        return it == storage.end() ? nullptr : it->second;
    }

    void put(
        const string& key,
        shared_ptr<const Artifact> artifact
    ) {
        if (!artifact || !artifact->immutable) {
            throw invalid_argument("Artifact must be immutable");
        }

        lock_guard<mutex> lock(mutex_);
        storage[key] = move(artifact);
    }

    size_t size() const {
        lock_guard<mutex> lock(mutex_);
        return storage.size();
    }
};

class PipelineEngine {
private:
    vector<Stage> stages;
    map<string, StageResult> results;
    ArtifactCache& cache;
    size_t maxWorkers;

    static string hashString(const string& input) {
        // Stable FNV-1a demonstration hash.
        // Production systems should use SHA-256 or stronger.
        uint64_t hash = 14695981039346656037ULL;

        for (unsigned char c : input) {
            hash ^= c;
            hash *= 1099511628211ULL;
        }

        stringstream stream;
        stream << hex << setw(16) << setfill('0') << hash;
        return stream.str();
    }

    string cacheKey(const Stage& stage) const {
        stringstream data;

        data << stage.id << '|'
             << stage.command << '|'
             << stage.inputVersion;

        vector<string> dependencies = stage.dependencies;
        sort(dependencies.begin(), dependencies.end());

        for (const auto& dependency : dependencies) {
            const auto& result = results.at(dependency);

            if (!result.artifact) {
                throw runtime_error(
                    "Dependency artifact unavailable"
                );
            }

            data << '|' << dependency
                 << ':' << result.artifact->digest;
        }

        return hashString(data.str());
    }

    StageResult executeStage(const Stage& stage) {
        auto start = chrono::steady_clock::now();

        try {
            const string key = cacheKey(stage);

            auto cached = cache.get(key);

            if (cached) {
                StageResult result;
                result.state = StageState::Cached;
                result.artifact = cached;
                return result;
            }

            if (!stage.execute) {
                throw runtime_error("Missing stage operation");
            }

            string content = stage.execute();

            auto artifact = make_shared<Artifact>();
            artifact->name = stage.id;
            artifact->content = content;
            artifact->digest = hashString(content);

            cache.put(key, artifact);

            StageResult result;
            result.state = StageState::Success;
            result.artifact = artifact;

            auto end = chrono::steady_clock::now();

            result.durationMs =
                chrono::duration<double, milli>(
                    end - start
                ).count();

            return result;

        } catch (const exception& error) {
            StageResult result;
            result.state = StageState::Failed;
            result.error = error.what();

            return result;
        }
    }

    void validate() {
        map<string, Stage> indexed;

        for (const auto& stage : stages) {
            if (stage.id.empty() || stage.command.empty()) {
                throw invalid_argument("Invalid stage definition");
            }

            if (!indexed.emplace(stage.id, stage).second) {
                throw invalid_argument("Duplicate stage ID");
            }
        }

        for (const auto& stage : stages) {
            for (const auto& dependency : stage.dependencies) {
                if (!indexed.count(dependency)) {
                    throw invalid_argument("Unknown dependency");
                }

                if (dependency == stage.id) {
                    throw invalid_argument("Self-dependency");
                }
            }
        }

        set<string> visiting;
        set<string> visited;

        function<void(const string&)> visit =
            [&](const string& id) {
                if (visiting.count(id)) {
                    throw invalid_argument(
                        "Dependency cycle detected"
                    );
                }

                if (visited.count(id)) return;

                visiting.insert(id);

                for (const auto& dependency :
                     indexed.at(id).dependencies) {
                    visit(dependency);
                }

                visiting.erase(id);
                visited.insert(id);
            };

        for (const auto& stage : stages) {
            visit(stage.id);
        }
    }

public:
    PipelineEngine(
        vector<Stage> input,
        ArtifactCache& artifactCache,
        size_t workers = 4
    )
        : stages(move(input)),
          cache(artifactCache),
          maxWorkers(workers) {

        if (workers == 0) {
            throw invalid_argument("Worker count must be positive");
        }

        validate();
    }

    const map<string, StageResult>& run() {
        results.clear();

        for (const auto& stage : stages) {
            results[stage.id] = StageResult{};
        }

        while (true) {
            vector<string> ready;

            for (const auto& stage : stages) {
                auto& result = results.at(stage.id);

                if (result.state != StageState::Pending) {
                    continue;
                }

                bool failed = false;
                bool complete = true;

                for (const auto& dependency : stage.dependencies) {
                    StageState state =
                        results.at(dependency).state;

                    if (
                        state == StageState::Failed ||
                        state == StageState::Blocked
                    ) {
                        failed = true;
                        break;
                    }

                    if (
                        state != StageState::Success &&
                        state != StageState::Cached
                    ) {
                        complete = false;
                    }
                }

                if (failed) {
                    result.state = StageState::Blocked;
                } else if (complete) {
                    ready.push_back(stage.id);
                }
            }

            if (ready.empty()) {
                bool unfinished = false;

                for (const auto& entry : results) {
                    if (entry.second.state == StageState::Pending) {
                        unfinished = true;
                    }
                }

                if (unfinished) {
                    throw runtime_error(
                        "Scheduler cannot make progress"
                    );
                }

                break;
            }

            vector<future<StageResult>> futures;
            vector<string> names;

            for (size_t i = 0; i < ready.size();) {
                futures.clear();
                names.clear();

                size_t batch = min(
                    maxWorkers,
                    ready.size() - i
                );

                for (size_t j = 0; j < batch; ++j) {
                    const string id = ready[i + j];

                    auto stageIt = find_if(
                        stages.begin(),
                        stages.end(),
                        [&](const Stage& stage) {
                            return stage.id == id;
                        }
                    );

                    results[id].state = StageState::Running;

                    names.push_back(id);

                    futures.push_back(
                        async(
                            launch::async,
                            [this, stage = *stageIt]() {
                                return executeStage(stage);
                            }
                        )
                    );
                }

                for (size_t j = 0; j < futures.size(); ++j) {
                    results[names[j]] = futures[j].get();
                }

                i += batch;
            }
        }

        return results;
    }

    void printReport() const {
        cout << "\nPIPELINE REPORT\n";

        for (const auto& entry : results) {
            cout << left << setw(20) << entry.first
                 << setw(12)
                 << static_cast<int>(entry.second.state);

            if (!entry.second.error.empty()) {
                cout << " Error: " << entry.second.error;
            }

            cout << '\n';
        }

        cout << "Cached artifacts: " << cache.size() << '\n';
    }
};

class GovernanceEngine {
private:
    BranchPolicy policy;

public:
    explicit GovernanceEngine(BranchPolicy branchPolicy)
        : policy(move(branchPolicy)) {}

    Eligibility evaluate(const PullRequest& pr) const {
        Eligibility result;

        auto reject = [&](const string& reason) {
            result.reasons.push_back(reason);
        };

        if (!pr.open) {
            reject("Pull Request is closed");
        }

        if (pr.draft) {
            reject("Draft Pull Request cannot be merged");
        }

        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            reject("Source or target branch missing");
        }

        if (pr.sourceBranch == pr.targetBranch) {
            reject("Source and target branches must differ");
        }

        if (pr.conflicts) {
            reject("Merge conflicts must be resolved");
        }

        if (
            policy.requireUpToDateBranch &&
            !pr.sourceUpToDate
        ) {
            reject("Source branch is behind target");
        }

        if (
            policy.requireResolvedConversations &&
            !pr.conversationsResolved
        ) {
            reject("Review conversations remain unresolved");
        }

        if (
            policy.requireLinearHistory &&
            !pr.linearHistoryAvailable
        ) {
            reject("Linear history requirement not satisfied");
        }

        int approvals = 0;

        for (const auto& review : pr.reviews) {
            if (
                review.eligible &&
                review.approved &&
                !review.stale
            ) {
                approvals++;
            }
        }

        if (approvals < policy.requiredApprovals) {
            reject("Insufficient current eligible approvals");
        }

        for (const auto& check : policy.requiredChecks) {
            auto it = pr.checks.find(check);

            if (
                it == pr.checks.end() ||
                it->second != CheckState::Passed
            ) {
                reject("Required check not passed: " + check);
            }
        }

        result.allowed = result.reasons.empty();
        return result;
    }

    bool authorizeDirectPush(bool administrator) const {
        if (!policy.protectedBranch) return true;

        if (administrator) return true;

        return policy.allowDirectPush;
    }

    bool authorizeForcePush(bool administrator) const {
        if (!policy.protectedBranch) return true;

        if (administrator) return true;

        return policy.allowForcePush;
    }
};

class MergeService {
private:
    GovernanceEngine& governance;

public:
    explicit MergeService(GovernanceEngine& engine)
        : governance(engine) {}

    bool merge(
        const PullRequest& pr,
        MergeStrategy strategy
    ) const {
        Eligibility eligibility = governance.evaluate(pr);

        if (!eligibility.allowed) {
            cout << "\nMERGE REJECTED\n";

            for (const auto& reason : eligibility.reasons) {
                cout << "- " << reason << '\n';
            }

            return false;
        }

        cout << "\nMERGE AUTHORIZED: PR #" << pr.id << '\n';

        switch (strategy) {
            case MergeStrategy::MergeCommit:
                cout << "Strategy: Merge commit\n";
                break;

            case MergeStrategy::Squash:
                cout << "Strategy: Squash merge\n";
                break;

            case MergeStrategy::Rebase:
                cout << "Strategy: Rebase merge\n";
                break;
        }

        return true;
    }
};

vector<Stage> createPipeline() {
    auto task = [](string output) {
        return [output]() {
            this_thread::sleep_for(
                chrono::milliseconds(100)
            );
            return output;
        };
    };

    return {
        {"checkout", {}, "git checkout", "commit-a", task("source")},
        {"build", {"checkout"}, "compile", "gcc-release", task("binary")},
        {"lint", {"checkout"}, "static analysis", "strict", task("clean")},
        {"unit-tests", {"build"}, "unit tests", "suite-v1", task("passed")},
        {"integration-tests", {"build"}, "integration tests", "suite-v1", task("passed")},
        {"security", {"checkout"}, "security scan", "scanner-v1", task("passed")},
        {"package",
         {"unit-tests", "integration-tests", "lint", "security"},
         "package artifact", "tar-v1", task("package-v1")},
        {"deploy",
         {"package"},
         "deploy staging", "staging", task("deployment-success")}
    };
}

int main() {
    try {
        cout << "CI/CD PARALLEL EXECUTION AND GOVERNANCE ENGINE\n";

        ArtifactCache cache;

        PipelineEngine first(
            createPipeline(),
            cache,
            4
        );

        cout << "\nFIRST EXECUTION\n";
        const auto& firstResults = first.run();
        first.printReport();

        for (const auto& entry : firstResults) {
            if (
                entry.second.state != StageState::Success &&
                entry.second.state != StageState::Cached
            ) {
                throw runtime_error("Initial pipeline failed");
            }
        }

        PipelineEngine second(
            createPipeline(),
            cache,
            4
        );

        cout << "\nSECOND EXECUTION\n";
        second.run();
        second.printReport();

        BranchPolicy policy;
        policy.requiredApprovals = 2;

        GovernanceEngine governance(policy);
        MergeService merger(governance);

        PullRequest pr;
        pr.id = 104;
        pr.sourceBranch = "feature/parallel-build";
        pr.targetBranch = "main";
        pr.open = true;
        pr.draft = false;
        pr.sourceUpToDate = true;
        pr.conflicts = false;
        pr.conversationsResolved = true;
        pr.linearHistoryAvailable = true;

        pr.reviews = {
            {"reviewer-1", true, true, false},
            {"reviewer-2", true, true, false},
            {"author", false, true, false}
        };

        pr.checks = {
            {"build", CheckState::Passed},
            {"unit-tests", CheckState::Passed},
            {"integration-tests", CheckState::Passed},
            {"security", CheckState::Passed}
        };

        cout << "\nGOVERNANCE EVALUATION\n";

        Eligibility eligibility = governance.evaluate(pr);

        cout << "Eligible: "
             << boolalpha << eligibility.allowed << '\n';

        if (eligibility.allowed) {
            merger.merge(pr, MergeStrategy::Squash);
        }

        cout << "\nDIRECT PUSH AUTHORIZED: "
             << governance.authorizeDirectPush(false)
             << '\n';

        cout << "\nCI/CD governance validation completed.\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

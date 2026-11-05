#include <algorithm>
#include <chrono>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class AgentType {
    STATIC,
    DYNAMIC
};

enum class AgentStatus {
    ONLINE,
    BUSY,
    OFFLINE,
    TERMINATED
};

enum class BuildStatus {
    QUEUED,
    RUNNING,
    SUCCESS,
    FAILED,
    CANCELLED
};

string toString(AgentType type) {
    return type == AgentType::STATIC ? "STATIC" : "DYNAMIC";
}

string toString(AgentStatus status) {
    switch (status) {
        case AgentStatus::ONLINE: return "ONLINE";
        case AgentStatus::BUSY: return "BUSY";
        case AgentStatus::OFFLINE: return "OFFLINE";
        case AgentStatus::TERMINATED: return "TERMINATED";
    }
    return "UNKNOWN";
}

string toString(BuildStatus status) {
    switch (status) {
        case BuildStatus::QUEUED: return "QUEUED";
        case BuildStatus::RUNNING: return "RUNNING";
        case BuildStatus::SUCCESS: return "SUCCESS";
        case BuildStatus::FAILED: return "FAILED";
        case BuildStatus::CANCELLED: return "CANCELLED";
    }
    return "UNKNOWN";
}

struct Build {
    int id;
    string jobName;
    set<string> labels;
    int estimatedSeconds;
    BuildStatus status = BuildStatus::QUEUED;
    string assignedAgent;
    string error;
};

struct Agent {
    string id;
    AgentType type;
    set<string> labels;
    int executors;
    int maxBuilds;
    int completedBuilds = 0;
    AgentStatus status = AgentStatus::ONLINE;
    set<int> activeBuilds;

    int availableExecutors() const {
        return executors - static_cast<int>(activeBuilds.size());
    }

    bool available() const {
        return status == AgentStatus::ONLINE &&
               availableExecutors() > 0 &&
               completedBuilds +
                   static_cast<int>(activeBuilds.size()) < maxBuilds;
    }

    bool supports(const set<string>& required) const {
        return includes(
            labels.begin(), labels.end(),
            required.begin(), required.end()
        );
    }
};

class JenkinsScheduler {
private:
    map<string, Agent> agents;
    map<int, Build> builds;
    vector<int> queue;

    int dynamicLimit;
    int dynamicSequence = 1;

    int provisioned = 0;
    int successful = 0;
    int failed = 0;

    Agent* findAgent(const Build& build) {
        vector<Agent*> candidates;

        for (auto& [id, agent] : agents) {
            if (agent.available() && agent.supports(build.labels)) {
                candidates.push_back(&agent);
            }
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const Agent* a, const Agent* b) {
                if (a->type != b->type) {
                    return a->type == AgentType::STATIC;
                }

                return a->availableExecutors() >
                       b->availableExecutors();
            }
        );

        return candidates.empty() ? nullptr : candidates.front();
    }

    int activeDynamicAgents() const {
        int count = 0;

        for (const auto& [id, agent] : agents) {
            if (
                agent.type == AgentType::DYNAMIC &&
                agent.status != AgentStatus::TERMINATED
            ) {
                count++;
            }
        }

        return count;
    }

    Agent* provisionDynamic(const Build& build) {
        if (activeDynamicAgents() >= dynamicLimit) {
            return nullptr;
        }

        string id = "cloud-agent-" +
                    to_string(dynamicSequence++);

        set<string> labels = build.labels;
        labels.insert("ephemeral");

        Agent agent{
            id,
            AgentType::DYNAMIC,
            labels,
            1,
            1
        };

        auto result = agents.emplace(id, std::move(agent));

        if (!result.second) {
            throw runtime_error("Agent ID collision.");
        }

        provisioned++;
        cout << "[PROVISIONED] " << id << '\n';

        return &result.first->second;
    }

public:
    explicit JenkinsScheduler(int dynamicLimit)
        : dynamicLimit(dynamicLimit) {
        if (dynamicLimit < 0) {
            throw invalid_argument(
                "Dynamic agent limit cannot be negative."
            );
        }
    }

    void registerAgent(Agent agent) {
        if (agent.id.empty()) {
            throw invalid_argument("Agent ID cannot be empty.");
        }

        if (agent.executors <= 0) {
            throw invalid_argument("Invalid executor count.");
        }

        if (agent.maxBuilds <= 0) {
            throw invalid_argument("Maximum builds must be positive.");
        }

        if (agents.count(agent.id)) {
            throw invalid_argument("Duplicate agent ID.");
        }

        agents.emplace(agent.id, std::move(agent));
    }

    void submitBuild(Build build) {
        if (build.id <= 0 || build.jobName.empty()) {
            throw invalid_argument("Invalid build details.");
        }

        if (build.labels.empty()) {
            throw invalid_argument("Build labels cannot be empty.");
        }

        if (build.estimatedSeconds <= 0) {
            throw invalid_argument("Invalid estimated duration.");
        }

        if (builds.count(build.id)) {
            throw invalid_argument("Duplicate build ID.");
        }

        queue.push_back(build.id);
        builds.emplace(build.id, std::move(build));
    }

    int schedule() {
        int assigned = 0;
        vector<int> remaining;

        for (int id : queue) {
            Build& build = builds.at(id);

            Agent* agent = findAgent(build);

            if (!agent) {
                agent = provisionDynamic(build);
            }

            if (!agent) {
                remaining.push_back(id);
                continue;
            }

            agent->activeBuilds.insert(id);
            agent->status = AgentStatus::BUSY;

            build.assignedAgent = agent->id;
            build.status = BuildStatus::RUNNING;

            cout << "[ASSIGNED] Build #" << id
                 << " -> " << agent->id << '\n';

            assigned++;
        }

        queue.swap(remaining);
        return assigned;
    }

    void completeBuild(
        int buildId,
        bool success,
        const string& error = ""
    ) {
        auto it = builds.find(buildId);

        if (it == builds.end()) {
            throw out_of_range("Unknown build ID.");
        }

        Build& build = it->second;

        if (build.status != BuildStatus::RUNNING) {
            throw logic_error("Build is not running.");
        }

        Agent& agent = agents.at(build.assignedAgent);

        if (agent.activeBuilds.erase(buildId) == 0) {
            throw logic_error("Agent assignment is inconsistent.");
        }

        agent.completedBuilds++;

        if (agent.activeBuilds.empty()) {
            agent.status = AgentStatus::ONLINE;
        }

        if (success) {
            build.status = BuildStatus::SUCCESS;
            successful++;
        } else {
            build.status = BuildStatus::FAILED;
            build.error = error.empty()
                ? "Execution failed."
                : error;
            failed++;
        }

        cout << "[COMPLETED] Build #" << buildId
             << " status=" << toString(build.status)
             << " agent=" << agent.id << '\n';
    }

    void setAgentOffline(const string& id) {
        auto it = agents.find(id);

        if (it == agents.end()) {
            throw out_of_range("Unknown agent.");
        }

        Agent& agent = it->second;

        if (!agent.activeBuilds.empty()) {
            throw logic_error(
                "Cannot offline an agent with running builds."
            );
        }

        if (agent.status == AgentStatus::TERMINATED) {
            throw logic_error("Agent has been terminated.");
        }

        agent.status = AgentStatus::OFFLINE;
    }

    void terminateDynamicAgent(const string& id) {
        auto it = agents.find(id);

        if (it == agents.end()) {
            throw out_of_range("Unknown agent.");
        }

        Agent& agent = it->second;

        if (agent.type != AgentType::DYNAMIC) {
            throw logic_error(
                "Static agents cannot use dynamic termination."
            );
        }

        if (!agent.activeBuilds.empty()) {
            throw logic_error("Agent still has active builds.");
        }

        agent.status = AgentStatus::TERMINATED;
        cout << "[TERMINATED] " << id << '\n';
    }

    void printReport() const {
        cout << "\n========== DISTRIBUTED BUILD REPORT ==========\n";

        for (const auto& [id, agent] : agents) {
            cout << id
                 << " type=" << toString(agent.type)
                 << " status=" << toString(agent.status)
                 << " executors=" << agent.executors
                 << " active=" << agent.activeBuilds.size()
                 << " labels={";

            bool first = true;

            for (const string& label : agent.labels) {
                if (!first) cout << ",";
                cout << label;
                first = false;
            }

            cout << "}\n";
        }

        cout << "\nBuild statistics\n";
        cout << "Submitted: " << builds.size() << '\n';
        cout << "Successful: " << successful << '\n';
        cout << "Failed: " << failed << '\n';
        cout << "Provisioned: " << provisioned << '\n';
        cout << "Queued: " << queue.size() << '\n';

        cout << "\nBuild details\n";

        for (const auto& [id, build] : builds) {
            cout << "#" << id
                 << " " << build.jobName
                 << " " << toString(build.status)
                 << " agent=" << build.assignedAgent;

            if (!build.error.empty()) {
                cout << " error=" << build.error;
            }

            cout << '\n';
        }
    }

    void validateInvariants() const {
        for (const auto& [id, agent] : agents) {
            if (agent.activeBuilds.size() >
                static_cast<size_t>(agent.executors)) {
                throw logic_error("Executor capacity exceeded.");
            }

            for (int buildId : agent.activeBuilds) {
                const Build& build = builds.at(buildId);

                if (
                    build.status != BuildStatus::RUNNING ||
                    build.assignedAgent != id
                ) {
                    throw logic_error(
                        "Build-agent assignment inconsistency."
                    );
                }
            }
        }
    }
};

int main() {
    try {
        JenkinsScheduler scheduler(3);

        scheduler.registerAgent(Agent{
            "linux-static-01",
            AgentType::STATIC,
            {"linux", "python", "docker"},
            2,
            1000
        });

        scheduler.registerAgent(Agent{
            "windows-static-01",
            AgentType::STATIC,
            {"windows", "dotnet"},
            1,
            1000
        });

        scheduler.submitBuild({
            1, "Python Tests", {"linux", "python"}, 15
        });

        scheduler.submitBuild({
            2, "Docker Build", {"linux", "docker"}, 20
        });

        scheduler.submitBuild({
            3, "Windows Integration", {"windows", "dotnet"}, 30
        });

        scheduler.submitBuild({
            4, "Security Scan", {"linux", "security"}, 25
        });

        scheduler.submitBuild({
            5, "Deployment", {"linux", "deployment"}, 35
        });

        scheduler.submitBuild({
            6, "Integration Tests", {"linux", "integration"}, 40
        });

        cout << "--- Scheduling builds ---\n";

        scheduler.schedule();
        scheduler.validateInvariants();

        cout << "\n--- Completing builds ---\n";

        scheduler.completeBuild(1, true);
        scheduler.completeBuild(2, true);
        scheduler.completeBuild(3, false, "Integration test failure");

        scheduler.validateInvariants();

        cout << "\n--- Scheduling remaining builds ---\n";

        scheduler.schedule();
        scheduler.validateInvariants();

        scheduler.completeBuild(4, true);
        scheduler.completeBuild(5, true);
        scheduler.completeBuild(6, true);

        scheduler.validateInvariants();

        scheduler.printReport();

        cout << "\n--- Dynamic infrastructure cleanup ---\n";

        scheduler.terminateDynamicAgent("cloud-agent-1");
        scheduler.printReport();

    } catch (const exception& error) {
        cerr << "Jenkins scheduler error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}

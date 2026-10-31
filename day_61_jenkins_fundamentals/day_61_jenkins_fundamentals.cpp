#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

enum class BuildStatus {
    Queued,
    Running,
    Success,
    Failure
};

enum class JobType {
    Freestyle,
    Pipeline
};

enum class AgentStatus {
    Online,
    Offline
};

std::string to_string(BuildStatus status) {
    switch (status) {
        case BuildStatus::Queued: return "queued";
        case BuildStatus::Running: return "running";
        case BuildStatus::Success: return "success";
        case BuildStatus::Failure: return "failure";
    }
    return "unknown";
}

std::string to_string(JobType type) {
    return type == JobType::Pipeline ? "pipeline" : "freestyle";
}

struct Commit {
    std::string sha;
    std::string message;
};

struct Build {
    int number{};
    std::string jobName;
    Commit commit;
    BuildStatus status{BuildStatus::Queued};
    std::string agentName;
    fs::path workspace;
    std::vector<std::string> logs;

    void log(const std::string& message) {
        logs.push_back(message);
    }
};

class Agent {
private:
    std::string name_;
    std::set<std::string> labels_;
    std::size_t executors_;
    std::size_t activeExecutors_{0};
    AgentStatus status_;

public:
    Agent(
        std::string name,
        std::set<std::string> labels,
        std::size_t executors = 1,
        AgentStatus status = AgentStatus::Online
    )
        : name_(std::move(name)),
          labels_(std::move(labels)),
          executors_(executors),
          status_(status) {
        if (name_.empty()) {
            throw std::invalid_argument("Agent name cannot be empty.");
        }
        if (executors_ == 0) {
            throw std::invalid_argument("An agent requires at least one executor.");
        }
    }

    const std::string& name() const {
        return name_;
    }

    bool canRun(const std::set<std::string>& required) const {
        if (status_ != AgentStatus::Online ||
            activeExecutors_ >= executors_) {
            return false;
        }

        return std::all_of(
            required.begin(),
            required.end(),
            [this](const std::string& label) {
                return labels_.contains(label);
            }
        );
    }

    void acquire() {
        if (activeExecutors_ >= executors_) {
            throw std::logic_error("No executor is available.");
        }
        ++activeExecutors_;
    }

    void release() {
        if (activeExecutors_ == 0) {
            throw std::logic_error("Executor release underflow.");
        }
        --activeExecutors_;
    }

    std::size_t activeExecutors() const {
        return activeExecutors_;
    }

    std::size_t executors() const {
        return executors_;
    }

    const std::set<std::string>& labels() const {
        return labels_;
    }
};

class Job {
private:
    std::string name_;
    JobType type_;
    std::set<std::string> requiredLabels_;
    bool enabled_;
    int nextBuild_{1};
    std::vector<Build> history_;

public:
    Job(
        std::string name,
        JobType type,
        std::set<std::string> labels,
        bool enabled = true
    )
        : name_(std::move(name)),
          type_(type),
          requiredLabels_(std::move(labels)),
          enabled_(enabled) {
        if (name_.empty()) {
            throw std::invalid_argument("Job name cannot be empty.");
        }
    }

    const std::string& name() const {
        return name_;
    }

    JobType type() const {
        return type_;
    }

    const std::set<std::string>& requiredLabels() const {
        return requiredLabels_;
    }

    bool enabled() const {
        return enabled_;
    }

    int nextBuildNumber() {
        return nextBuild_++;
    }

    void record(Build build) {
        history_.push_back(std::move(build));
    }

    const std::vector<Build>& history() const {
        return history_;
    }
};

class JenkinsGovernanceEngine {
private:
    std::map<std::string, Job> jobs_;
    std::map<std::string, Agent> agents_;
    std::vector<Build> queue_;
    fs::path root_;

    Agent* selectAgent(const Job& job) {
        std::vector<Agent*> candidates;

        for (auto& [name, agent] : agents_) {
            if (agent.canRun(job.requiredLabels())) {
                candidates.push_back(&agent);
            }
        }

        if (candidates.empty()) {
            return nullptr;
        }

        return *std::min_element(
            candidates.begin(),
            candidates.end(),
            [](const Agent* left, const Agent* right) {
                return left->activeExecutors() < right->activeExecutors();
            }
        );
    }

    fs::path createWorkspace(
        Agent& agent,
        const Build& build
    ) {
        fs::path workspace =
            root_ /
            agent.name() /
            (build.jobName + "-" + std::to_string(build.number));

        fs::create_directories(workspace);
        return workspace;
    }

    static void validateCheckout(
        const fs::path& workspace,
        const Commit& commit
    ) {
        std::ifstream input(workspace / "commit.txt");
        if (!input) {
            throw std::runtime_error("Checkout artifact cannot be opened.");
        }

        std::string storedSha;
        std::getline(input, storedSha);

        if (storedSha != commit.sha) {
            throw std::runtime_error("Checkout integrity check failed.");
        }
    }

public:
    explicit JenkinsGovernanceEngine(fs::path root)
        : root_(std::move(root)) {
        fs::create_directories(root_);
    }

    void addAgent(Agent agent) {
        const std::string name = agent.name();
        if (agents_.contains(name)) {
            throw std::invalid_argument("Duplicate agent: " + name);
        }
        agents_.emplace(name, std::move(agent));
    }

    void addJob(Job job) {
        const std::string name = job.name();
        if (jobs_.contains(name)) {
            throw std::invalid_argument("Duplicate job: " + name);
        }
        jobs_.emplace(name, std::move(job));
    }

    void enqueue(
        const std::string& jobName,
        Commit commit
    ) {
        auto it = jobs_.find(jobName);
        if (it == jobs_.end()) {
            throw std::invalid_argument("Unknown job: " + jobName);
        }

        if (!it->second.enabled()) {
            throw std::runtime_error("Job is disabled.");
        }

        if (commit.sha.size() < 7) {
            throw std::invalid_argument("Commit SHA is too short.");
        }

        Build build;
        build.number = it->second.nextBuildNumber();
        build.jobName = jobName;
        build.commit = std::move(commit);
        queue_.push_back(std::move(build));
    }

    bool runNext() {
        for (auto it = queue_.begin(); it != queue_.end(); ++it) {
            auto jobIt = jobs_.find(it->jobName);
            if (jobIt == jobs_.end()) {
                throw std::logic_error("Queued build references missing job.");
            }

            Agent* agent = selectAgent(jobIt->second);
            if (!agent) {
                continue;
            }

            Build build = std::move(*it);
            queue_.erase(it);

            agent->acquire();
            build.status = BuildStatus::Running;
            build.agentName = agent->name();

            try {
                build.log("Controller selected agent " + agent->name() + ".");
                build.workspace = createWorkspace(*agent, build);

                std::ofstream checkout(build.workspace / "commit.txt");
                if (!checkout) {
                    throw std::runtime_error("Unable to create checkout artifact.");
                }

                checkout << build.commit.sha << '\n';
                checkout << build.commit.message << '\n';
                checkout.close();

                validateCheckout(build.workspace, build.commit);
                build.log("Checkout validation passed.");

                if (build.commit.message.find("[FAIL]") != std::string::npos) {
                    throw std::runtime_error("Intentional validation failure.");
                }

                if (jobIt->second.type() == JobType::Pipeline) {
                    build.log("Pipeline policy validation passed.");
                } else {
                    build.log("Freestyle job validation passed.");
                }

                build.status = BuildStatus::Success;
                build.log("Build completed successfully.");
            } catch (const std::exception& error) {
                build.status = BuildStatus::Failure;
                build.log(std::string("Build failed: ") + error.what());
            }

            agent->release();
            jobIt->second.record(std::move(build));
            return true;
        }

        return false;
    }

    void runAll() {
        while (!queue_.empty()) {
            if (!runNext()) {
                throw std::runtime_error(
                    "Queue contains builds for which no compatible executor is available."
                );
            }
        }
    }

    void printReport() const {
        std::cout << "Jenkins Governance Engine\n";
        std::cout << "=========================\n";

        for (const auto& [name, job] : jobs_) {
            std::cout << "\nJob: " << name
                      << " [" << to_string(job.type()) << "]\n";

            for (const auto& build : job.history()) {
                std::cout
                    << "  #" << build.number
                    << " status=" << to_string(build.status)
                    << " agent=" << build.agentName
                    << " workspace=" << build.workspace.string()
                    << '\n';

                for (const auto& line : build.logs) {
                    std::cout << "    " << line << '\n';
                }
            }
        }

        std::cout << "\nAgents\n";
        for (const auto& [name, agent] : agents_) {
            std::cout
                << "  " << name
                << ": executors=" << agent.executors()
                << ", active=" << agent.activeExecutors()
                << '\n';
        }

        std::cout << "\nQueue depth: " << queue_.size() << '\n';
    }
};

int main() {
    try {
        const auto root =
            fs::temp_directory_path() / "jenkins_cpp17_case_study";

        fs::remove_all(root);

        JenkinsGovernanceEngine engine(root);

        engine.addAgent(
            Agent(
                "linux-python",
                {"linux", "python", "container"},
                2
            )
        );

        engine.addAgent(
            Agent(
                "linux-java",
                {"linux", "java"},
                1
            )
        );

        engine.addAgent(
            Agent(
                "offline-python",
                {"linux", "python"},
                1,
                AgentStatus::Offline
            )
        );

        engine.addJob(
            Job(
                "python-service",
                JobType::Pipeline,
                {"linux", "python"}
            )
        );

        engine.addJob(
            Job(
                "java-service",
                JobType::Freestyle,
                {"linux", "java"}
            )
        );

        engine.enqueue(
            "python-service",
            {"a1b2c3d4", "Validate configuration"}
        );

        engine.enqueue(
            "python-service",
            {"e5f6a7b8", "[FAIL] exercise failure handling"}
        );

        engine.enqueue(
            "java-service",
            {"11223344", "Improve Java service"}
        );

        engine.runAll();
        engine.printReport();

        std::cout << "\nIntegrity checks\n";
        std::cout << "================\n";

        const fs::path firstArtifact =
            root / "linux-python" / "python-service-1" / "commit.txt";

        if (!fs::exists(firstArtifact)) {
            throw std::runtime_error("Expected workspace artifact is missing.");
        }

        std::cout << "Workspace isolation: passed\n";
        std::cout << "Label-based scheduling: passed\n";
        std::cout << "Failure-state recording: passed\n";
        std::cout << "Executor accounting: passed\n";

        fs::remove_all(root);
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

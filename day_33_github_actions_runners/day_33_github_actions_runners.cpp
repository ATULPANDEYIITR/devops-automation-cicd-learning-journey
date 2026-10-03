#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace std;

enum class RunnerKind {
    Hosted,
    SelfHosted
};

enum class RunnerState {
    Offline,
    Idle,
    Busy,
    Draining
};

enum class JobState {
    Queued,
    Running,
    Succeeded,
    Failed,
    Cancelled
};

string to_string(RunnerKind kind) {
    return kind == RunnerKind::Hosted ? "github-hosted" : "self-hosted";
}

string to_string(RunnerState state) {
    switch (state) {
        case RunnerState::Offline: return "offline";
        case RunnerState::Idle: return "idle";
        case RunnerState::Busy: return "busy";
        case RunnerState::Draining: return "draining";
    }
    return "unknown";
}

string to_string(JobState state) {
    switch (state) {
        case JobState::Queued: return "queued";
        case JobState::Running: return "running";
        case JobState::Succeeded: return "succeeded";
        case JobState::Failed: return "failed";
        case JobState::Cancelled: return "cancelled";
    }
    return "unknown";
}

struct RunnerImage {
    string name;
    string operatingSystem;
    string architecture;
    set<string> tools;
    bool ephemeral{true};
};

struct WorkflowJob {
    int id;
    string name;
    set<string> requiredLabels;
    set<string> requiredTools;
    int simulatedDurationMs{20};
    bool shouldFail{false};
    bool requiresTrustedRunner{false};

    JobState state{JobState::Queued};
    optional<string> assignedRunner;
    string failureReason;
};

struct Runner {
    string name;
    RunnerKind kind;
    set<string> labels;
    RunnerImage image;

    RunnerState state{RunnerState::Idle};
    bool online{true};
    bool trusted{false};
    string group{"default"};
    optional<int> currentJob;

    bool supports(const WorkflowJob& job, string& reason) const {
        if (!online || state == RunnerState::Offline) {
            reason = "runner is offline";
            return false;
        }

        if (state != RunnerState::Idle) {
            reason = "runner is not idle";
            return false;
        }

        for (const auto& label : job.requiredLabels) {
            if (!labels.contains(label)) {
                reason = "missing required label: " + label;
                return false;
            }
        }

        for (const auto& tool : job.requiredTools) {
            if (!image.tools.contains(tool)) {
                reason = "missing required tool: " + tool;
                return false;
            }
        }

        if (job.requiresTrustedRunner && !trusted) {
            reason = "job requires a trusted runner";
            return false;
        }

        reason = "compatible";
        return true;
    }
};

struct RoutingDecision {
    optional<string> runnerName;
    vector<string> diagnostics;
};

class RunnerGovernanceEngine {
private:
    map<string, Runner> runners;
    queue<WorkflowJob> jobs;
    vector<WorkflowJob> history;
    int nextJobId{1};

public:
    void registerRunner(Runner runner) {
        if (runner.name.empty()) {
            throw invalid_argument("runner name cannot be empty");
        }

        if (runners.contains(runner.name)) {
            throw invalid_argument("runner already registered: " + runner.name);
        }

        validateRunnerConfiguration(runner);
        runners.emplace(runner.name, move(runner));
    }

    static void validateRunnerConfiguration(const Runner& runner) {
        if (runner.kind == RunnerKind::SelfHosted &&
            !runner.labels.contains("self-hosted")) {
            throw invalid_argument(
                "self-hosted runner must expose the self-hosted label"
            );
        }

        if (runner.labels.contains("linux") &&
            runner.image.operatingSystem != "Linux") {
            throw invalid_argument("linux label conflicts with operating system");
        }

        if (runner.labels.contains("windows") &&
            runner.image.operatingSystem != "Windows") {
            throw invalid_argument("windows label conflicts with operating system");
        }

        if (runner.labels.contains("x64") &&
            runner.image.architecture != "x64") {
            throw invalid_argument("x64 label conflicts with architecture");
        }

        if (runner.labels.contains("arm64") &&
            runner.image.architecture != "arm64") {
            throw invalid_argument("arm64 label conflicts with architecture");
        }

        if (runner.trusted && runner.kind == RunnerKind::Hosted) {
            throw invalid_argument(
                "this case study reserves explicit trusted infrastructure "
                "classification for self-hosted runners"
            );
        }
    }

    int submitJob(
        string name,
        set<string> labels,
        set<string> tools,
        int durationMs = 20,
        bool shouldFail = false,
        bool requiresTrustedRunner = false
    ) {
        WorkflowJob job{
            nextJobId++,
            move(name),
            move(labels),
            move(tools),
            durationMs,
            shouldFail,
            requiresTrustedRunner
        };

        jobs.push(move(job));
        return nextJobId - 1;
    }

    RoutingDecision route(const WorkflowJob& job) const {
        RoutingDecision decision;

        for (const auto& [name, runner] : runners) {
            string reason;

            if (runner.supports(job, reason)) {
                decision.runnerName = name;
                decision.diagnostics.push_back(
                    name + ": " + reason
                );
                return decision;
            }

            decision.diagnostics.push_back(
                name + ": " + reason
            );
        }

        return decision;
    }

    bool executeNext() {
        if (jobs.empty()) {
            return false;
        }

        WorkflowJob job = jobs.front();
        jobs.pop();

        RoutingDecision decision = route(job);

        if (!decision.runnerName.has_value()) {
            cout << "[QUEUE] " << job.name
                 << " remains queued because no compatible runner exists\n";

            for (const auto& diagnostic : decision.diagnostics) {
                cout << "        " << diagnostic << '\n';
            }

            jobs.push(move(job));
            return false;
        }

        Runner& runner = runners.at(*decision.runnerName);

        job.assignedRunner = runner.name;
        job.state = JobState::Running;
        runner.state = RunnerState::Busy;
        runner.currentJob = job.id;

        cout << "[RUN ] " << job.name
             << " -> " << runner.name
             << " [" << to_string(runner.kind)
             << ", " << runner.image.name << "]\n";

        this_thread::sleep_for(
            chrono::milliseconds(job.simulatedDurationMs)
        );

        if (job.shouldFail) {
            job.state = JobState::Failed;
            job.failureReason = "simulated build or test failure";

            cout << "[FAIL] " << job.name
                 << ": " << job.failureReason << '\n';
        } else {
            job.state = JobState::Succeeded;
            cout << "[DONE] " << job.name << ": succeeded\n";
        }

        runner.state = RunnerState::Idle;
        runner.currentJob.reset();

        history.push_back(move(job));
        return true;
    }

    void drainRunner(const string& runnerName) {
        Runner& runner = runners.at(runnerName);

        if (runner.state == RunnerState::Busy) {
            throw runtime_error(
                "cannot drain a busy runner without handling its current job"
            );
        }

        runner.state = RunnerState::Draining;

        cout << "[DRAIN] " << runnerName
             << " will not receive new jobs\n";
    }

    void restoreRunner(const string& runnerName) {
        Runner& runner = runners.at(runnerName);

        if (!runner.online) {
            throw runtime_error(
                "cannot restore an offline runner without bringing it online"
            );
        }

        runner.state = RunnerState::Idle;
        cout << "[READY] " << runnerName << " is accepting jobs\n";
    }

    void takeOffline(const string& runnerName) {
        Runner& runner = runners.at(runnerName);

        if (runner.state == RunnerState::Busy) {
            throw runtime_error(
                "busy runner cannot be abruptly taken offline in this model"
            );
        }

        runner.online = false;
        runner.state = RunnerState::Offline;

        cout << "[OFFLINE] " << runnerName << '\n';
    }

    void printFleet() const {
        cout << "\nFleet inventory\n";
        cout << "---------------\n";

        for (const auto& [name, runner] : runners) {
            cout << left
                 << setw(24) << name
                 << setw(16) << to_string(runner.kind)
                 << setw(12) << to_string(runner.state)
                 << "OS=" << runner.image.operatingSystem
                 << " arch=" << runner.image.architecture
                 << " group=" << runner.group
                 << " ephemeral=" << boolalpha
                 << runner.image.ephemeral
                 << " trusted=" << runner.trusted
                 << '\n';
        }
    }

    void printHistory() const {
        cout << "\nExecution history\n";
        cout << "-----------------\n";

        for (const auto& job : history) {
            cout << "Job " << job.id
                 << " " << job.name
                 << ": " << to_string(job.state)
                 << ", runner="
                 << (job.assignedRunner.has_value()
                         ? *job.assignedRunner
                         : "none");

            if (!job.failureReason.empty()) {
                cout << ", reason=" << job.failureReason;
            }

            cout << '\n';
        }
    }

    size_t queuedJobs() const {
        return jobs.size();
    }

    size_t completedJobs() const {
        return history.size();
    }

    void printRoutingAnalysis(const WorkflowJob& job) const {
        RoutingDecision decision = route(job);

        cout << "\nRouting analysis for: " << job.name << '\n';

        if (decision.runnerName.has_value()) {
            cout << "Selected runner: "
                 << *decision.runnerName << '\n';
        } else {
            cout << "Selected runner: none\n";
        }

        for (const auto& diagnostic : decision.diagnostics) {
            cout << "  " << diagnostic << '\n';
        }
    }
};

Runner makeHostedLinuxRunner() {
    return Runner{
        "hosted-ubuntu-x64",
        RunnerKind::Hosted,
        {"linux", "x64", "docker"},
        RunnerImage{
            "ubuntu-latest",
            "Linux",
            "x64",
            {"git", "python", "node", "docker"},
            true
        },
        RunnerState::Idle,
        true,
        false,
        "github-hosted",
        nullopt
    };
}

Runner makeSelfHostedInternalRunner() {
    return Runner{
        "internal-linux-builder",
        RunnerKind::SelfHosted,
        {"self-hosted", "linux", "x64", "internal"},
        RunnerImage{
            "company-linux-builder",
            "Linux",
            "x64",
            {"git", "python", "node", "internal-sdk"},
            false
        },
        RunnerState::Idle,
        true,
        true,
        "internal-builders",
        nullopt
    };
}

Runner makeGpuRunner() {
    return Runner{
        "gpu-linux-builder",
        RunnerKind::SelfHosted,
        {"self-hosted", "linux", "x64", "gpu"},
        RunnerImage{
            "gpu-linux",
            "Linux",
            "x64",
            {"git", "python", "cuda"},
            false
        },
        RunnerState::Idle,
        true,
        true,
        "accelerated-builders",
        nullopt
    };
}

void demonstrateHostedAndSelfHosted() {
    cout << "Hosted and self-hosted architecture\n";
    cout << "-----------------------------------\n";

    Runner hosted = makeHostedLinuxRunner();
    Runner selfHosted = makeSelfHostedInternalRunner();

    cout << hosted.name
         << ": managed image lifecycle, ephemeral="
         << boolalpha << hosted.image.ephemeral << '\n';

    cout << selfHosted.name
         << ": organization-managed host, ephemeral="
         << boolalpha << selfHosted.image.ephemeral
         << ", trusted=" << selfHosted.trusted << '\n';

    cout
        << "The architectural distinction is responsibility. Hosted runners "
           "provide managed compute environments, while self-hosted runners "
           "require the organization to operate the host, software, network "
           "access, patching, credentials, and cleanup."
        << '\n';
}

void demonstrateLabelRouting(RunnerGovernanceEngine& engine) {
    cout << "\nLabel routing\n";
    cout << "-------------\n";

    WorkflowJob gpuProbe{
        0,
        "gpu-integration",
        {"self-hosted", "linux", "x64", "gpu"},
        {"cuda"},
        20,
        false,
        true
    };

    engine.printRoutingAnalysis(gpuProbe);

    WorkflowJob internalProbe{
        0,
        "internal-sdk-build",
        {"self-hosted", "linux", "x64", "internal"},
        {"internal-sdk"},
        20,
        false,
        true
    };

    engine.printRoutingAnalysis(internalProbe);
}

void demonstrateQueueBehavior(RunnerGovernanceEngine& engine) {
    cout << "\nQueue and execution behavior\n";
    cout << "----------------------------\n";

    engine.submitJob(
        "web-unit-tests",
        {"linux", "x64"},
        {"node"},
        25
    );

    engine.submitJob(
        "internal-sdk-build",
        {"self-hosted", "linux", "x64", "internal"},
        {"internal-sdk"},
        30,
        false,
        true
    );

    engine.submitJob(
        "failing-integration-test",
        {"linux", "x64"},
        {"node"},
        20,
        true
    );

    engine.submitJob(
        "unsupported-arm-gpu",
        {"self-hosted", "linux", "arm64", "gpu"},
        {"cuda"},
        20
    );

    while (engine.queuedJobs() > 0) {
        size_t before = engine.queuedJobs();
        bool executed = engine.executeNext();

        if (!executed && engine.queuedJobs() == before) {
            cout
                << "No progress is possible because the remaining job "
                   "has no currently eligible runner."
                << '\n';
            break;
        }
    }
}

void demonstrateLifecycle(RunnerGovernanceEngine& engine) {
    cout << "\nRunner lifecycle\n";
    cout << "----------------\n";

    engine.drainRunner("internal-linux-builder");
    engine.takeOffline("gpu-linux-builder");

    WorkflowJob internalJob{
        0,
        "maintenance-sensitive-build",
        {"self-hosted", "linux", "x64", "internal"},
        {"internal-sdk"},
        20,
        false,
        true
    };

    engine.printRoutingAnalysis(internalJob);

    engine.restoreRunner("internal-linux-builder");
    engine.printRoutingAnalysis(internalJob);

    cout
        << "Draining is useful during maintenance because it separates "
           "operational state from registration. An operator can stop new "
           "work before changing or shutting down the host."
        << '\n';
}

void demonstrateGovernance() {
    cout << "\nRepository governance implications\n";
    cout << "----------------------------------\n";

    cout
        << "Runner groups can separate infrastructure by purpose and trust. "
           "A production deployment runner should not automatically be "
           "treated as equivalent to an ordinary test runner."
        << '\n';

    cout
        << "Labels express capabilities such as operating system, CPU "
           "architecture, GPU availability, or specialized software. "
           "Labels should not be treated as a substitute for authorization."
        << '\n';

    cout
        << "Authorization and trust must be designed separately from "
           "routing. A job requiring sensitive credentials needs a runner "
           "boundary appropriate for those credentials."
        << '\n';
}

void demonstrateSecurityTradeoffs() {
    cout << "\nSecurity trade-offs\n";
    cout << "-------------------\n";

    vector<string> controls{
        "Use least-privilege service accounts on self-hosted hosts.",
        "Restrict network access from privileged runners.",
        "Keep runner software and operating-system packages patched.",
        "Separate untrusted workloads from sensitive production runners.",
        "Prefer ephemeral execution when persistent state is not required.",
        "Remove credentials and sensitive artifacts after execution.",
        "Treat runner labels as routing metadata, not as a security boundary."
    };

    for (const auto& control : controls) {
        cout << "- " << control << '\n';
    }
}

void demonstrateCapacityModel() {
    cout << "\nCapacity model\n";
    cout << "--------------\n";

    constexpr int jobs = 30;
    constexpr int averageMinutes = 5;
    constexpr int concurrentRunners = 6;

    const int totalRunnerMinutes = jobs * averageMinutes;
    const double estimatedWallClock =
        static_cast<double>(totalRunnerMinutes) / concurrentRunners;

    cout << "Jobs: " << jobs << '\n';
    cout << "Average job duration: "
         << averageMinutes << " minutes\n";
    cout << "Concurrent compatible runners: "
         << concurrentRunners << '\n';
    cout << "Total runner-minutes: "
         << totalRunnerMinutes << '\n';
    cout << fixed << setprecision(1)
         << "Approximate full-utilization wall time: "
         << estimatedWallClock << " minutes\n";

    cout
        << "This estimate assumes independent jobs and full utilization. "
           "Real queues also depend on runner labels, startup time, job "
           "dependencies, cache behavior, workload variability, and "
           "availability of specialized hardware."
        << '\n';
}

int main() {
    try {
        cout << "GitHub Actions Runner Governance Engine\n";
        cout << "=======================================\n";

        demonstrateHostedAndSelfHosted();

        RunnerGovernanceEngine engine;

        engine.registerRunner(makeHostedLinuxRunner());
        engine.registerRunner(makeSelfHostedInternalRunner());
        engine.registerRunner(makeGpuRunner());

        demonstrateLabelRouting(engine);
        demonstrateQueueBehavior(engine);
        demonstrateLifecycle(engine);
        demonstrateGovernance();
        demonstrateSecurityTradeoffs();
        demonstrateCapacityModel();

        engine.printFleet();
        engine.printHistory();

        cout << "\nCase study result\n";
        cout << "-----------------\n";
        cout << "Completed jobs: " << engine.completedJobs() << '\n';
        cout << "Remaining queued jobs: " << engine.queuedJobs() << '\n';

        cout
            << "The engine demonstrates the core runner architecture: "
               "a workflow job carries execution constraints, routing "
               "selects an eligible runner, the runner owns execution of "
               "the job steps, and runner lifecycle plus infrastructure "
               "trust determine what workloads can safely execute there."
            << '\n';

        return 0;
    } catch (const exception& error) {
        cerr << "Fatal configuration or execution error: "
             << error.what() << '\n';
        return 1;
    }
}

#include <algorithm>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class JobStatus {
    Pending,
    Running,
    Success,
    Failure,
    Skipped,
    Cancelled
};

std::string toString(JobStatus status) {
    switch (status) {
        case JobStatus::Pending: return "pending";
        case JobStatus::Running: return "running";
        case JobStatus::Success: return "success";
        case JobStatus::Failure: return "failure";
        case JobStatus::Skipped: return "skipped";
        case JobStatus::Cancelled: return "cancelled";
    }
    return "unknown";
}

struct JobResult {
    std::string name;
    JobStatus status;
    std::string message;
    std::map<std::string, std::string> outputs;

    bool successful() const {
        return status == JobStatus::Success;
    }

    bool failed() const {
        return status == JobStatus::Failure;
    }
};

struct RepositoryEvent {
    std::string branch;
    std::string event;
    bool releaseEnabled;
};

struct JobDefinition {
    std::string name;
    std::vector<std::string> needs;

    /*
     * The condition receives the complete result set. This makes conditional
     * execution explicit rather than hiding policy decisions inside a job.
     */
    std::function<bool(
        const std::map<std::string, JobResult>&,
        const RepositoryEvent&
    )> condition;

    std::function<JobResult(
        const std::map<std::string, JobResult>&
    )> action;
};

class DependencyGraph {
private:
    std::map<std::string, JobDefinition> jobs;

public:
    void addJob(const JobDefinition& job) {
        if (jobs.contains(job.name)) {
            throw std::runtime_error(
                "Duplicate job: " + job.name
            );
        }

        if (std::find(
                job.needs.begin(),
                job.needs.end(),
                job.name
            ) != job.needs.end()) {
            throw std::runtime_error(
                "Self dependency: " + job.name
            );
        }

        jobs.emplace(job.name, job);
    }

    void validate() const {
        for (const auto& [name, job] : jobs) {
            for (const auto& dependency : job.needs) {
                if (!jobs.contains(dependency)) {
                    throw std::runtime_error(
                        "Job '" + name +
                        "' depends on unknown job '" +
                        dependency + "'"
                    );
                }
            }
        }

        std::map<std::string, int> state;

        for (const auto& [name, _] : jobs) {
            state[name] = 0;
        }

        std::function<void(const std::string&)> visit =
            [&](const std::string& name) {
                if (state[name] == 1) {
                    throw std::runtime_error(
                        "Dependency cycle detected at '" + name + "'"
                    );
                }

                if (state[name] == 2) {
                    return;
                }

                state[name] = 1;

                for (const auto& dependency : jobs.at(name).needs) {
                    visit(dependency);
                }

                state[name] = 2;
            };

        for (const auto& [name, _] : jobs) {
            visit(name);
        }
    }

    std::vector<std::string> topologicalOrder() const {
        std::map<std::string, int> indegree;
        std::map<std::string, std::vector<std::string>> dependents;

        for (const auto& [name, _] : jobs) {
            indegree[name] = 0;
            dependents[name] = {};
        }

        for (const auto& [name, job] : jobs) {
            for (const auto& dependency : job.needs) {
                ++indegree[name];
                dependents[dependency].push_back(name);
            }
        }

        std::queue<std::string> ready;

        for (const auto& [name, degree] : indegree) {
            if (degree == 0) {
                ready.push(name);
            }
        }

        std::vector<std::string> order;

        while (!ready.empty()) {
            auto current = ready.front();
            ready.pop();

            order.push_back(current);

            for (const auto& dependent : dependents[current]) {
                --indegree[dependent];

                if (indegree[dependent] == 0) {
                    ready.push(dependent);
                }
            }
        }

        if (order.size() != jobs.size()) {
            throw std::runtime_error(
                "Graph cannot be topologically ordered."
            );
        }

        return order;
    }

    const std::map<std::string, JobDefinition>& definitions() const {
        return jobs;
    }
};

class RepositoryGovernanceEngine {
private:
    DependencyGraph graph;

public:
    void addJob(const JobDefinition& job) {
        graph.addJob(job);
    }

    std::map<std::string, JobResult> execute(
        const RepositoryEvent& event
    ) {
        graph.validate();

        std::map<std::string, JobResult> results;
        auto order = graph.topologicalOrder();

        for (const auto& name : order) {
            const auto& job = graph.definitions().at(name);

            bool dependenciesSuccessful = true;

            for (const auto& dependency : job.needs) {
                if (!results.at(dependency).successful()) {
                    dependenciesSuccessful = false;
                    break;
                }
            }

            bool eligible = dependenciesSuccessful;

            if (job.condition) {
                eligible = job.condition(results, event);
            }

            if (!eligible) {
                results[name] = {
                    name,
                    JobStatus::Skipped,
                    "Job was not eligible to execute.",
                    {}
                };
                continue;
            }

            try {
                results[name] = job.action(results);
            } catch (const std::exception& error) {
                results[name] = {
                    name,
                    JobStatus::Failure,
                    error.what(),
                    {}
                };
            }
        }

        return results;
    }
};

JobDefinition simpleJob(
    const std::string& name,
    const std::vector<std::string>& needs,
    const std::string& message
) {
    return {
        name,
        needs,
        nullptr,
        [name, message](
            const std::map<std::string, JobResult>&
        ) {
            return JobResult{
                name,
                JobStatus::Success,
                message,
                {}
            };
        }
    };
}

void printResults(
    const std::map<std::string, JobResult>& results
) {
    std::cout << "\nJob execution report\n";
    std::cout << std::left
              << std::setw(24) << "Job"
              << std::setw(12) << "Status"
              << "Message\n";

    std::cout << std::string(70, '-') << '\n';

    for (const auto& [name, result] : results) {
        std::cout << std::left
                  << std::setw(24) << name
                  << std::setw(12) << toString(result.status)
                  << result.message
                  << '\n';
    }
}

void buildReleaseWorkflow(
    RepositoryGovernanceEngine& engine
) {
    engine.addJob(
        simpleJob(
            "checkout",
            {},
            "Repository source prepared."
        )
    );

    engine.addJob(
        simpleJob(
            "build",
            {"checkout"},
            "Application compiled and artifact generated."
        )
    );

    engine.addJob(
        simpleJob(
            "lint",
            {"build"},
            "Static analysis passed."
        )
    );

    engine.addJob(
        simpleJob(
            "unit-tests",
            {"build"},
            "Unit test suite passed."
        )
    );

    engine.addJob(
        simpleJob(
            "security-scan",
            {"build"},
            "Dependency and security checks passed."
        )
    );

    /*
     * The package job demonstrates fan-in: it is not eligible until every
     * independent validation branch succeeds.
     */
    engine.addJob(
        simpleJob(
            "package",
            {"lint", "unit-tests", "security-scan"},
            "Release package assembled."
        )
    );

    engine.addJob({
        "production-deploy",
        {"package"},
        [](const auto& results, const auto& event) {
            return event.branch == "main" &&
                   event.event == "push" &&
                   event.releaseEnabled &&
                   results.at("package").successful();
        },
        [](const auto&) {
            return JobResult{
                "production-deploy",
                JobStatus::Success,
                "Production deployment executed.",
                {}
            };
        }
    });

    /*
     * Diagnostics intentionally use an unconditional condition. This is the
     * direct analogue of an always-run diagnostic path: the job can execute
     * even if the deployment dependency failed or was skipped.
     */
    engine.addJob({
        "diagnostics",
        {"production-deploy"},
        [](const auto&, const auto&) {
            return true;
        },
        [](const auto& results) {
            const auto& deployment =
                results.at("production-deploy");

            return JobResult{
                "diagnostics",
                JobStatus::Success,
                "Deployment diagnostics recorded; observed state: " +
                    toString(deployment.status),
                {}
            };
        }
    });
}

void demonstrateSuccessfulRelease() {
    std::cout << "\n=== Successful production path ===\n";

    RepositoryGovernanceEngine engine;
    buildReleaseWorkflow(engine);

    RepositoryEvent event{
        "main",
        "push",
        true
    };

    auto results = engine.execute(event);
    printResults(results);
}

void demonstrateNonProductionBranch() {
    std::cout << "\n=== Feature branch path ===\n";

    RepositoryGovernanceEngine engine;
    buildReleaseWorkflow(engine);

    RepositoryEvent event{
        "feature/observability",
        "push",
        true
    };

    auto results = engine.execute(event);
    printResults(results);
}

void demonstrateGraphFailure() {
    std::cout << "\n=== Dependency graph validation ===\n";

    DependencyGraph graph;

    graph.addJob({
        "build",
        {"test"},
        nullptr,
        [](const auto&) {
            return JobResult{
                "build",
                JobStatus::Success,
                "Build complete.",
                {}
            };
        }
    });

    graph.addJob({
        "test",
        {"build"},
        nullptr,
        [](const auto&) {
            return JobResult{
                "test",
                JobStatus::Success,
                "Tests complete.",
                {}
            };
        }
    });

    try {
        graph.validate();
    } catch (const std::exception& error) {
        std::cout << "Rejected invalid workflow: "
                  << error.what()
                  << '\n';
    }
}

void demonstrateMatrixPolicy() {
    std::cout << "\n=== Matrix-style aggregate policy ===\n";

    struct MatrixResult {
        std::string runtime;
        bool passed;
    };

    std::vector<MatrixResult> matrix = {
        {"ubuntu-node-20", true},
        {"ubuntu-node-22", true},
        {"windows-node-22", true},
        {"macos-node-22", false}
    };

    bool releaseEligible = std::all_of(
        matrix.begin(),
        matrix.end(),
        [](const MatrixResult& result) {
            return result.passed;
        }
    );

    for (const auto& result : matrix) {
        std::cout << std::left
                  << std::setw(22)
                  << result.runtime
                  << (result.passed ? "PASS" : "FAIL")
                  << '\n';
    }

    std::cout << "Aggregate release eligibility: "
              << (releaseEligible ? "ALLOWED" : "BLOCKED")
              << '\n';
}

int main() {
    try {
        std::cout
            << "GitHub Actions Dependency and Conditional Execution Engine\n"
            << "==========================================================\n";

        demonstrateSuccessfulRelease();
        demonstrateNonProductionBranch();
        demonstrateGraphFailure();
        demonstrateMatrixPolicy();

        std::cout << "\nDesign rule: `needs` establishes the dependency graph; "
                     "conditions establish eligibility after dependencies "
                     "reach a terminal state.\n";
    } catch (const std::exception& error) {
        std::cerr << "Fatal workflow error: "
                  << error.what()
                  << '\n';
        return 1;
    }

    return 0;
}

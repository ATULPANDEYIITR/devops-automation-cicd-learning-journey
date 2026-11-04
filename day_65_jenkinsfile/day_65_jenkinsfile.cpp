#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Jenkinsfile Pipeline Execution and Governance Engine
 *
 * Models:
 * - Declarative pipeline
 * - Stages and steps
 * - Global and stage environment
 * - Conditional stage execution
 * - Stage dependencies
 * - Post conditions
 * - Failure propagation
 * - Execution history
 * - Build reports
 *
 * Standard: C++17
 */

using Clock = std::chrono::steady_clock;

enum class BuildStatus {
    Created,
    Running,
    Success,
    Failure,
    Unstable,
    Aborted
};

enum class StageStatus {
    Pending,
    Running,
    Success,
    Failure,
    Skipped
};

enum class PostCondition {
    Always,
    Success,
    Failure,
    Unstable,
    Cleanup
};

std::string toString(BuildStatus status) {
    switch (status) {
        case BuildStatus::Created: return "CREATED";
        case BuildStatus::Running: return "RUNNING";
        case BuildStatus::Success: return "SUCCESS";
        case BuildStatus::Failure: return "FAILURE";
        case BuildStatus::Unstable: return "UNSTABLE";
        case BuildStatus::Aborted: return "ABORTED";
    }

    return "UNKNOWN";
}

std::string toString(StageStatus status) {
    switch (status) {
        case StageStatus::Pending: return "PENDING";
        case StageStatus::Running: return "RUNNING";
        case StageStatus::Success: return "SUCCESS";
        case StageStatus::Failure: return "FAILURE";
        case StageStatus::Skipped: return "SKIPPED";
    }

    return "UNKNOWN";
}

using Environment = std::map<std::string, std::string>;

class PipelineException : public std::runtime_error {
public:
    explicit PipelineException(const std::string& message)
        : std::runtime_error(message) {}
};

struct ExecutionContext {
    Environment environment;
    std::map<std::string, std::string> artifacts;
};

struct Step {
    std::string name;
    bool continueOnError = false;
    std::function<void(ExecutionContext&)> execute;
};

struct Stage {
    std::string name;
    std::vector<Step> steps;
    Environment environment;
    std::vector<std::string> dependencies;
    std::function<bool(const Environment&)> condition;

    StageStatus status = StageStatus::Pending;
    std::string error;
    double durationMs = 0.0;
};

struct PostAction {
    PostCondition condition;
    std::string name;
    std::function<void(ExecutionContext&)> execute;
};

struct HistoryEntry {
    std::string stage;
    std::string event;
    std::string details;
};

class JenkinsPipeline {
private:
    std::string name;
    Environment environment;
    std::vector<Stage> stages;
    std::vector<PostAction> postActions;
    std::vector<HistoryEntry> history;
    BuildStatus status = BuildStatus::Created;

    ExecutionContext context;

    static bool validIdentifier(const std::string& value) {
        if (value.empty()) return false;

        auto validFirst = [](char c) {
            return (c >= 'A' && c <= 'Z') ||
                   (c >= 'a' && c <= 'z') ||
                   c == '_';
        };

        auto validRest = [&](char c) {
            return validFirst(c) ||
                   (c >= '0' && c <= '9');
        };

        if (!validFirst(value.front())) return false;

        return std::all_of(
            value.begin() + 1,
            value.end(),
            validRest
        );
    }

    void validate() {
        if (name.empty()) {
            throw PipelineException(
                "Pipeline name cannot be empty."
            );
        }

        if (stages.empty()) {
            throw PipelineException(
                "Pipeline requires at least one stage."
            );
        }

        std::set<std::string> names;

        for (const auto& [key, value] : environment) {
            if (!validIdentifier(key)) {
                throw PipelineException(
                    "Invalid environment key: " + key
                );
            }
        }

        for (const auto& stage : stages) {
            if (stage.name.empty() || stage.steps.empty()) {
                throw PipelineException(
                    "Every stage requires a name and steps."
                );
            }

            if (!names.insert(stage.name).second) {
                throw PipelineException(
                    "Duplicate stage: " + stage.name
                );
            }

            for (const auto& step : stage.steps) {
                if (step.name.empty() || !step.execute) {
                    throw PipelineException(
                        "Invalid step in stage " + stage.name
                    );
                }
            }
        }

        for (const auto& stage : stages) {
            for (const auto& dependency : stage.dependencies) {
                if (!names.count(dependency)) {
                    throw PipelineException(
                        "Unknown dependency: " + dependency
                    );
                }
            }
        }

        validateDependencyGraph();
    }

    void validateDependencyGraph() {
        std::unordered_map<std::string, std::size_t> indexes;

        for (std::size_t i = 0; i < stages.size(); ++i) {
            indexes[stages[i].name] = i;
        }

        std::set<std::string> visiting;
        std::set<std::string> visited;

        std::function<void(const std::string&)> visit =
            [&](const std::string& name) {
                if (visiting.count(name)) {
                    throw PipelineException(
                        "Circular dependency detected: " + name
                    );
                }

                if (visited.count(name)) return;

                visiting.insert(name);

                const Stage& stage = stages[indexes.at(name)];

                for (const auto& dependency : stage.dependencies) {
                    visit(dependency);
                }

                visiting.erase(name);
                visited.insert(name);
            };

        for (const auto& stage : stages) {
            visit(stage.name);
        }
    }

    void record(
        const std::string& stage,
        const std::string& event,
        const std::string& details = ""
    ) {
        history.push_back({stage, event, details});

        std::cout
            << "[PIPELINE] "
            << std::left << std::setw(12) << event
            << " | " << stage;

        if (!details.empty()) {
            std::cout << " | " << details;
        }

        std::cout << '\n';
    }

    bool dependenciesSuccessful(const Stage& stage) const {
        for (const auto& dependency : stage.dependencies) {
            auto found = std::find_if(
                stages.begin(),
                stages.end(),
                [&](const Stage& item) {
                    return item.name == dependency;
                }
            );

            if (found == stages.end() ||
                found->status != StageStatus::Success) {
                return false;
            }
        }

        return true;
    }

    void executeStage(Stage& stage) {
        if (!dependenciesSuccessful(stage)) {
            stage.status = StageStatus::Skipped;

            record(
                stage.name,
                "STAGE_SKIPPED",
                "Dependency did not succeed"
            );

            return;
        }

        Environment stageEnvironment = environment;

        for (const auto& [key, value] : stage.environment) {
            stageEnvironment[key] = value;
        }

        if (stage.condition && !stage.condition(stageEnvironment)) {
            stage.status = StageStatus::Skipped;
            record(stage.name, "STAGE_SKIPPED", "Condition false");
            return;
        }

        stage.status = StageStatus::Running;
        context.environment = stageEnvironment;

        auto start = Clock::now();

        record(stage.name, "STAGE_STARTED");

        try {
            for (const auto& step : stage.steps) {
                record(stage.name, "STEP_STARTED", step.name);

                try {
                    step.execute(context);

                    record(
                        stage.name,
                        "STEP_SUCCESS",
                        step.name
                    );
                } catch (const std::exception& exception) {
                    record(
                        stage.name,
                        "STEP_FAILURE",
                        exception.what()
                    );

                    if (!step.continueOnError) {
                        throw;
                    }
                }
            }

            stage.status = StageStatus::Success;
            record(stage.name, "STAGE_SUCCESS");

        } catch (const std::exception& exception) {
            stage.status = StageStatus::Failure;
            stage.error = exception.what();

            record(
                stage.name,
                "STAGE_FAILURE",
                stage.error
            );

            throw PipelineException(
                "Stage " + stage.name + " failed: " +
                stage.error
            );
        }

        auto finish = Clock::now();

        stage.durationMs =
            std::chrono::duration<double, std::milli>(
                finish - start
            ).count();
    }

    void executePostActions() {
        for (const auto& action : postActions) {
            bool shouldRun = false;

            switch (action.condition) {
                case PostCondition::Always:
                case PostCondition::Cleanup:
                    shouldRun = true;
                    break;

                case PostCondition::Success:
                    shouldRun = status == BuildStatus::Success;
                    break;

                case PostCondition::Failure:
                    shouldRun = status == BuildStatus::Failure;
                    break;

                case PostCondition::Unstable:
                    shouldRun = status == BuildStatus::Unstable;
                    break;
            }

            if (!shouldRun) continue;

            try {
                action.execute(context);

                record(
                    "POST",
                    "POST_SUCCESS",
                    action.name
                );
            } catch (const std::exception& exception) {
                record(
                    "POST",
                    "POST_FAILURE",
                    exception.what()
                );

                if (status == BuildStatus::Success) {
                    status = BuildStatus::Failure;
                }
            }
        }
    }

public:
    JenkinsPipeline(
        std::string pipelineName,
        Environment globalEnvironment,
        std::vector<Stage> pipelineStages,
        std::vector<PostAction> actions
    )
        : name(std::move(pipelineName)),
          environment(std::move(globalEnvironment)),
          stages(std::move(pipelineStages)),
          postActions(std::move(actions)) {
        validate();
    }

    BuildStatus run() {
        if (status != BuildStatus::Created) {
            throw PipelineException(
                "Pipeline can only run once."
            );
        }

        auto start = Clock::now();
        status = BuildStatus::Running;

        record(name, "PIPELINE_STARTED");

        try {
            for (auto& stage : stages) {
                executeStage(stage);
            }

            status = BuildStatus::Success;

        } catch (const std::exception& exception) {
            status = BuildStatus::Failure;

            record(
                name,
                "PIPELINE_FAILURE",
                exception.what()
            );

            for (auto& stage : stages) {
                if (stage.status == StageStatus::Pending) {
                    stage.status = StageStatus::Skipped;
                }
            }
        }

        executePostActions();

        auto finish = Clock::now();

        const double duration =
            std::chrono::duration<double, std::milli>(
                finish - start
            ).count();

        record(
            name,
            "PIPELINE_COMPLETED",
            toString(status)
        );

        printReport(duration);

        return status;
    }

    void printReport(double duration) const {
        std::cout << "\n========== PIPELINE REPORT ==========\n";
        std::cout << "Pipeline: " << name << '\n';
        std::cout << "Status: " << toString(status) << '\n';

        std::cout << std::fixed << std::setprecision(2);
        std::cout << "Duration: " << duration << " ms\n";

        std::cout << "\nStage results:\n";

        for (const auto& stage : stages) {
            std::cout
                << "  " << std::setw(16) << std::left
                << stage.name
                << " | " << std::setw(8)
                << toString(stage.status)
                << " | " << stage.durationMs << " ms";

            if (!stage.error.empty()) {
                std::cout << " | " << stage.error;
            }

            std::cout << '\n';
        }

        std::cout << "\nArtifacts:\n";

        for (const auto& [name, value] : context.artifacts) {
            std::cout << "  " << name << " = " << value << '\n';
        }

        std::cout << "=====================================\n";
    }
};

int main() {
    try {
        std::vector<Stage> stages = {
            {
                "Checkout",
                {
                    {
                        "Validate Git branch",
                        false,
                        [](ExecutionContext& context) {
                            const auto& branch =
                                context.environment.at("GIT_BRANCH");

                            if (branch.empty()) {
                                throw PipelineException(
                                    "Branch is empty"
                                );
                            }

                            std::cout
                                << "Checked out: " << branch << '\n';
                        }
                    }
                },
                {},
                {},
                nullptr
            },

            {
                "Build",
                {
                    {
                        "Compile application",
                        false,
                        [](ExecutionContext& context) {
                            context.artifacts["application"] =
                                "inventory-service.jar";

                            std::cout << "Application compiled.\n";
                        }
                    }
                },
                {},
                {"Checkout"},
                nullptr
            },

            {
                "Test",
                {
                    {
                        "Execute unit tests",
                        false,
                        [](ExecutionContext& context) {
                            if (context.environment.at("TEST_RESULT")
                                == "FAIL") {
                                throw PipelineException(
                                    "Unit tests failed"
                                );
                            }

                            std::cout << "Unit tests passed.\n";
                        }
                    }
                },
                {},
                {"Build"},
                nullptr
            },

            {
                "Deploy",
                {
                    {
                        "Deploy artifact",
                        false,
                        [](ExecutionContext& context) {
                            const auto target =
                                context.environment.at("DEPLOY_TARGET");

                            if (!context.artifacts.count("application")) {
                                throw PipelineException(
                                    "Application artifact unavailable"
                                );
                            }

                            std::cout
                                << "Deployed to " << target << '\n';
                        }
                    }
                },
                {
                    {"DEPLOY_TARGET", "staging"}
                },
                {"Test"},
                [](const Environment& environment) {
                    return environment.at("GIT_BRANCH") == "main";
                }
            }
        };

        std::vector<PostAction> postActions = {
            {
                PostCondition::Always,
                "Build notification",
                [](ExecutionContext& context) {
                    std::cout << "Build notification processed.\n";
                }
            },
            {
                PostCondition::Success,
                "Archive artifacts",
                [](ExecutionContext& context) {
                    std::cout << "Artifacts archived.\n";
                }
            },
            {
                PostCondition::Failure,
                "Failure notification",
                [](ExecutionContext& context) {
                    std::cout << "Failure notification processed.\n";
                }
            },
            {
                PostCondition::Cleanup,
                "Workspace cleanup",
                [](ExecutionContext& context) {
                    std::cout << "Workspace cleanup completed.\n";
                }
            }
        };

        JenkinsPipeline pipeline(
            "Inventory CI/CD",
            {
                {"GIT_BRANCH", "main"},
                {"TEST_RESULT", "PASS"},
                {"DEPLOY_TARGET", "production"}
            },
            std::move(stages),
            std::move(postActions)
        );

        BuildStatus result = pipeline.run();

        // Validate expected behavior.
        if (result != BuildStatus::Success) {
            return 1;
        }

        std::cout << "\nPipeline validation passed.\n";

        return 0;

    } catch (const std::exception& exception) {
        std::cerr
            << "Fatal error: "
            << exception.what()
            << '\n';

        return 1;
    }
}

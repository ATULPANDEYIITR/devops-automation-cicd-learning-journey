#include <algorithm>
#include <atomic>
#include <exception>
#include <functional>
#include <future>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class PipelineStyle {
    Declarative,
    Scripted
};

enum class StageState {
    Pending,
    Running,
    Success,
    Failed,
    Skipped,
    Unstable
};

enum class BuildState {
    Success,
    Failure,
    Unstable
};

std::string toString(StageState state) {
    switch (state) {
        case StageState::Pending: return "PENDING";
        case StageState::Running: return "RUNNING";
        case StageState::Success: return "SUCCESS";
        case StageState::Failed: return "FAILED";
        case StageState::Skipped: return "SKIPPED";
        case StageState::Unstable: return "UNSTABLE";
    }
    throw std::logic_error("Unknown stage state");
}

std::string toString(BuildState state) {
    switch (state) {
        case BuildState::Success: return "SUCCESS";
        case BuildState::Failure: return "FAILURE";
        case BuildState::Unstable: return "UNSTABLE";
    }
    throw std::logic_error("Unknown build state");
}

struct PipelineContext {
    std::string branch = "main";
    bool deploymentApproved = false;
    std::map<std::string, std::string> artifacts;
    std::mutex mutex;

    void addArtifact(const std::string& name,
                     const std::string& checksum) {
        if (name.empty() || checksum.empty()) {
            throw std::invalid_argument(
                "Artifact name and checksum are required"
            );
        }

        std::lock_guard<std::mutex> lock(mutex);
        if (artifacts.count(name) != 0) {
            throw std::runtime_error(
                "Artifact already exists: " + name
            );
        }
        artifacts.emplace(name, checksum);
    }

    void log(const std::string& message) const {
        std::lock_guard<std::mutex> lock(outputMutex());
        std::cout << message << '\n';
    }

private:
    static std::mutex& outputMutex() {
        static std::mutex instance;
        return instance;
    }
};

using Condition = std::function<bool(const PipelineContext&)>;
using StageAction = std::function<void(PipelineContext&, int)>;

struct StageSpec {
    std::string name;
    std::vector<std::string> dependencies;
    std::string agent;
    int retries = 0;
    bool optional = false;
    Condition condition;
    StageAction action;
};

struct StageResult {
    std::string name;
    StageState state = StageState::Pending;
    int attempts = 0;
    std::string message;
};

struct BuildReport {
    std::string pipelineName;
    BuildState state = BuildState::Success;
    std::vector<StageResult> stages;
};

class Pipeline {
public:
    Pipeline(std::string name, PipelineStyle style)
        : name_(std::move(name)), style_(style) {
        if (name_.empty()) {
            throw std::invalid_argument("Pipeline name cannot be empty");
        }
    }

    void addStage(StageSpec stage) {
        if (stage.name.empty()) {
            throw std::invalid_argument("Stage name cannot be empty");
        }
        if (stage.agent.empty()) {
            throw std::invalid_argument("Agent label cannot be empty");
        }
        if (stage.retries < 0) {
            throw std::invalid_argument("Retries cannot be negative");
        }
        if (!stage.action) {
            throw std::invalid_argument(
                "Stage action must be executable"
            );
        }
        if (index_.count(stage.name) != 0) {
            throw std::invalid_argument(
                "Duplicate stage: " + stage.name
            );
        }

        index_[stage.name] = stages_.size();
        stages_.push_back(std::move(stage));
    }

    BuildReport run(PipelineContext& context) const {
        validate();

        std::unordered_map<std::string, StageState> states;
        std::unordered_map<std::string, StageResult> results;

        for (const auto& stage : stages_) {
            states.emplace(stage.name, StageState::Pending);
        }

        std::size_t completed = 0;

        while (completed < stages_.size()) {
            std::vector<std::size_t> ready;

            for (std::size_t i = 0; i < stages_.size(); ++i) {
                const auto& stage = stages_[i];
                if (states.at(stage.name) != StageState::Pending) {
                    continue;
                }

                bool dependenciesFinished = true;
                for (const auto& dependency : stage.dependencies) {
                    const StageState dependencyState = states.at(dependency);
                    if (dependencyState == StageState::Pending ||
                        dependencyState == StageState::Running) {
                        dependenciesFinished = false;
                        break;
                    }
                }

                if (dependenciesFinished) {
                    ready.push_back(i);
                }
            }

            if (ready.empty()) {
                throw std::logic_error(
                    "No ready stage exists; dependency graph is invalid"
                );
            }

            std::vector<std::size_t> runnable;

            // A stage is skipped when a dependency did not succeed.
            for (const std::size_t index : ready) {
                const auto& stage = stages_[index];

                bool dependencyFailed = false;
                for (const auto& dependency : stage.dependencies) {
                    if (states.at(dependency) != StageState::Success) {
                        dependencyFailed = true;
                        break;
                    }
                }

                if (dependencyFailed) {
                    StageResult result{
                        stage.name,
                        StageState::Skipped,
                        0,
                        "A dependency did not succeed"
                    };
                    states[stage.name] = result.state;
                    results.emplace(stage.name, result);
                    ++completed;
                    continue;
                }

                bool shouldRun = true;
                if (stage.condition) {
                    shouldRun = stage.condition(context);
                }

                if (!shouldRun) {
                    StageResult result{
                        stage.name,
                        StageState::Skipped,
                        0,
                        "Stage condition evaluated to false"
                    };
                    states[stage.name] = result.state;
                    results.emplace(stage.name, result);
                    ++completed;
                    continue;
                }

                states[stage.name] = StageState::Running;
                runnable.push_back(index);
            }

            // Independent stages in the same dependency layer execute
            // concurrently. Results are collected on the calling thread.
            std::vector<std::future<StageResult>> futures;
            futures.reserve(runnable.size());

            for (const std::size_t index : runnable) {
                futures.push_back(std::async(
                    std::launch::async,
                    [this, index, &context]() {
                        return executeStage(stages_[index], context);
                    }
                ));
            }

            for (auto& future : futures) {
                StageResult result = future.get();
                states[result.name] = result.state;
                results.emplace(result.name, std::move(result));
                ++completed;
            }
        }

        BuildReport report;
        report.pipelineName = name_;

        bool hasFailure = false;
        bool hasUnstable = false;

        for (const auto& stage : stages_) {
            const auto& result = results.at(stage.name);
            report.stages.push_back(result);

            hasFailure = hasFailure ||
                result.state == StageState::Failed;
            hasUnstable = hasUnstable ||
                result.state == StageState::Unstable;
        }

        if (hasFailure) {
            report.state = BuildState::Failure;
        } else if (hasUnstable) {
            report.state = BuildState::Unstable;
        } else {
            report.state = BuildState::Success;
        }

        return report;
    }

    PipelineStyle style() const {
        return style_;
    }

private:
    std::string name_;
    PipelineStyle style_;
    std::vector<StageSpec> stages_;
    std::unordered_map<std::string, std::size_t> index_;

    void validate() const {
        if (stages_.empty()) {
            throw std::invalid_argument(
                "Pipeline must contain at least one stage"
            );
        }

        std::vector<int> indegree(stages_.size(), 0);
        std::vector<std::vector<std::size_t>> outgoing(stages_.size());

        for (std::size_t i = 0; i < stages_.size(); ++i) {
            std::set<std::string> uniqueDependencies;

            for (const auto& dependency : stages_[i].dependencies) {
                const auto found = index_.find(dependency);
                if (found == index_.end()) {
                    throw std::invalid_argument(
                        "Unknown dependency '" + dependency +
                        "' in stage '" + stages_[i].name + "'"
                    );
                }
                if (dependency == stages_[i].name) {
                    throw std::invalid_argument(
                        "A stage cannot depend on itself"
                    );
                }
                if (!uniqueDependencies.insert(dependency).second) {
                    throw std::invalid_argument(
                        "Duplicate dependency in stage '" +
                        stages_[i].name + "'"
                    );
                }

                outgoing[found->second].push_back(i);
                ++indegree[i];
            }
        }

        std::vector<std::size_t> queue;
        for (std::size_t i = 0; i < indegree.size(); ++i) {
            if (indegree[i] == 0) {
                queue.push_back(i);
            }
        }

        std::size_t visited = 0;
        for (std::size_t cursor = 0; cursor < queue.size(); ++cursor) {
            const std::size_t current = queue[cursor];
            ++visited;

            for (const std::size_t dependent : outgoing[current]) {
                --indegree[dependent];
                if (indegree[dependent] == 0) {
                    queue.push_back(dependent);
                }
            }
        }

        if (visited != stages_.size()) {
            throw std::invalid_argument(
                "Pipeline dependency graph contains a cycle"
            );
        }
    }

    StageResult executeStage(
        const StageSpec& stage,
        PipelineContext& context
    ) const {
        context.log(
            "[" + stage.name + "] allocated agent '" +
            stage.agent + "'"
        );

        std::string lastError;

        for (int attempt = 1; attempt <= stage.retries + 1; ++attempt) {
            try {
                context.log(
                    "[" + stage.name + "] attempt " +
                    std::to_string(attempt)
                );

                stage.action(context, attempt);

                context.log(
                    "[" + stage.name + "] completed successfully"
                );

                return {
                    stage.name,
                    StageState::Success,
                    attempt,
                    "Completed"
                };
            } catch (const std::exception& error) {
                lastError = error.what();
                context.log(
                    "[" + stage.name + "] attempt failed: " +
                    lastError
                );
            } catch (...) {
                lastError = "Unknown non-standard exception";
                context.log(
                    "[" + stage.name + "] " + lastError
                );
            }
        }

        const StageState finalState = stage.optional
            ? StageState::Unstable
            : StageState::Failed;

        return {
            stage.name,
            finalState,
            stage.retries + 1,
            lastError
        };
    }
};

void printReport(const BuildReport& report) {
    std::cout << "\nPipeline: " << report.pipelineName << '\n';
    std::cout << "Build status: " << toString(report.state) << '\n';

    for (const auto& stage : report.stages) {
        std::cout << "  " << stage.name
                  << ": " << toString(stage.state)
                  << ", attempts=" << stage.attempts
                  << ", message=" << stage.message << '\n';
    }
}

StageSpec makeStage(
    std::string name,
    std::vector<std::string> dependencies,
    std::string agent,
    StageAction action,
    int retries = 0,
    Condition condition = {},
    bool optional = false
) {
    return {
        std::move(name),
        std::move(dependencies),
        std::move(agent),
        retries,
        optional,
        std::move(condition),
        std::move(action)
    };
}

Pipeline createDeclarativePipeline() {
    Pipeline pipeline("payments-declarative", PipelineStyle::Declarative);

    pipeline.addStage(makeStage(
        "Checkout", {}, "linux",
        [](PipelineContext& context, int) {
            context.log("Checking out payments-service");
        }
    ));

    pipeline.addStage(makeStage(
        "Compile", {"Checkout"}, "linux-docker",
        [](PipelineContext& context, int) {
            context.addArtifact("application.jar", "sha256:abc123");
            context.log("Application compiled");
        }
    ));

    pipeline.addStage(makeStage(
        "Unit Tests", {"Compile"}, "linux",
        [](PipelineContext& context, int) {
            context.log("Unit tests passed");
        }
    ));

    auto integrationAttempts = std::make_shared<std::atomic<int>>(0);

    pipeline.addStage(makeStage(
        "Integration Tests", {"Compile"}, "linux-docker",
        [integrationAttempts](PipelineContext& context, int) {
            const int current = ++(*integrationAttempts);
            if (current == 1) {
                throw std::runtime_error("Temporary test service unavailable");
            }
            context.log("Integration tests passed");
        },
        1
    ));

    pipeline.addStage(makeStage(
        "Package", {"Unit Tests", "Integration Tests"}, "linux-docker",
        [](PipelineContext& context, int) {
            context.addArtifact(
                "payments-release.tar.gz",
                "sha256:def456"
            );
            context.log("Release package created");
        }
    ));

    pipeline.addStage(makeStage(
        "Deploy Production", {"Package"}, "linux-deploy",
        [](PipelineContext& context, int) {
            if (!context.deploymentApproved) {
                throw std::runtime_error(
                    "Production deployment approval is missing"
                );
            }
            context.log("Production deployment completed");
        },
        0,
        [](const PipelineContext& context) {
            return context.branch == "main" &&
                   context.deploymentApproved;
        }
    ));

    return pipeline;
}

Pipeline createScriptedPipeline() {
    Pipeline pipeline("payments-scripted", PipelineStyle::Scripted);

    // The stage list is constructed imperatively. A scripted Jenkins
    // pipeline can use loops and ordinary Groovy control flow similarly.
    pipeline.addStage(makeStage(
        "Checkout", {}, "linux",
        [](PipelineContext& context, int) {
            context.log("Scripted checkout completed");
        }
    ));

    pipeline.addStage(makeStage(
        "Build", {"Checkout"}, "linux-docker",
        [](PipelineContext& context, int) {
            context.addArtifact("scripted-app.jar", "sha256:xyz789");
        }
    ));

    const std::vector<std::string> qualityChecks = {
        "Unit Tests",
        "Security Scan",
        "License Scan"
    };

    for (const auto& check : qualityChecks) {
        pipeline.addStage(makeStage(
            check, {"Build"}, "linux",
            [check](PipelineContext& context, int) {
                context.log(check + " passed");
            }
        ));
    }

    pipeline.addStage(makeStage(
        "Package",
        qualityChecks,
        "linux-docker",
        [](PipelineContext& context, int) {
            context.addArtifact(
                "scripted-release.tar.gz",
                "sha256:scripted"
            );
        }
    ));

    pipeline.addStage(makeStage(
        "Deploy Production", {"Package"}, "linux-deploy",
        [](PipelineContext& context, int) {
            context.log("Scripted production deployment");
        },
        0,
        [](const PipelineContext& context) {
            return context.branch == "main";
        }
    ));

    return pipeline;
}

int main() {
    try {
        PipelineContext declarativeContext;
        declarativeContext.branch = "main";
        declarativeContext.deploymentApproved = true;

        Pipeline declarative = createDeclarativePipeline();
        BuildReport declarativeReport =
            declarative.run(declarativeContext);

        printReport(declarativeReport);

        PipelineContext scriptedContext;
        scriptedContext.branch = "feature/reporting";

        Pipeline scripted = createScriptedPipeline();
        BuildReport scriptedReport = scripted.run(scriptedContext);

        printReport(scriptedReport);

        std::cout << "\nDeclarative artifacts:\n";
        for (const auto& [name, checksum] : declarativeContext.artifacts) {
            std::cout << "  " << name << " -> " << checksum << '\n';
        }

        std::cout << "\nScripted artifacts:\n";
        for (const auto& [name, checksum] : scriptedContext.artifacts) {
            std::cout << "  " << name << " -> " << checksum << '\n';
        }

        return (
            declarativeReport.state == BuildState::Failure ||
            scriptedReport.state == BuildState::Failure
        ) ? 1 : 0;

    } catch (const std::exception& error) {
        std::cerr << "Pipeline engine error: " << error.what() << '\n';
        return 1;
    }
}

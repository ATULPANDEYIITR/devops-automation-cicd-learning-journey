#include <algorithm>
#include <cctype>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Repository automation governance engine.
 *
 * This case study models a CI platform in which application teams call a
 * shared reusable workflow. The workflow delegates step-level packaging and
 * verification to a composite action. The engine evaluates inputs, job
 * dependencies, action outputs, secret declarations, and deployment policy.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic governance.cpp -o governance
 */

enum class JobState {
    Pending,
    Running,
    Succeeded,
    Failed,
    Skipped
};

std::string to_string(JobState state) {
    switch (state) {
        case JobState::Pending: return "pending";
        case JobState::Running: return "running";
        case JobState::Succeeded: return "succeeded";
        case JobState::Failed: return "failed";
        case JobState::Skipped: return "skipped";
    }
    throw std::logic_error("Unknown job state");
}

class GovernanceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct InputDefinition {
    std::string name;
    bool required;
    std::string default_value;
    std::set<std::string> allowed_values;
};

struct JobResult {
    JobState state = JobState::Pending;
    std::string error;
};

struct ExecutionContext {
    std::map<std::string, std::string> inputs;
    std::map<std::string, std::string> secrets;
    std::map<std::string, std::string> environment;
    std::map<std::string, std::string> outputs;
    std::vector<std::string> logs;

    void log(std::string message) {
        // Prevent credential values from entering ordinary diagnostic logs.
        for (const auto& [name, secret] : secrets) {
            (void)name;
            if (!secret.empty()) {
                std::size_t position = 0;
                while ((position = message.find(secret, position)) !=
                       std::string::npos) {
                    message.replace(position, secret.size(), "***");
                    position += 3;
                }
            }
        }
        logs.push_back(std::move(message));
    }
};

class InputValidator {
public:
    static std::map<std::string, std::string> resolve(
        const std::vector<InputDefinition>& definitions,
        const std::map<std::string, std::string>& supplied) {

        std::set<std::string> known;
        for (const auto& definition : definitions) {
            known.insert(definition.name);
        }

        for (const auto& [name, value] : supplied) {
            (void)value;
            if (!known.count(name)) {
                throw GovernanceError("Undeclared input: " + name);
            }
        }

        std::map<std::string, std::string> resolved;

        for (const auto& definition : definitions) {
            auto found = supplied.find(definition.name);
            std::string value = found == supplied.end()
                ? definition.default_value
                : found->second;

            if (definition.required && value.empty()) {
                throw GovernanceError(
                    "Required input is empty: " + definition.name);
            }

            if (!definition.allowed_values.empty() &&
                !definition.allowed_values.count(value)) {
                throw GovernanceError(
                    "Input value is outside the permitted set: " +
                    definition.name);
            }

            resolved.emplace(definition.name, value);
        }

        return resolved;
    }
};

struct CompositeStep {
    std::string name;
    void (*execute)(ExecutionContext&);
};

class CompositeAction {
private:
    std::string name_;
    std::vector<InputDefinition> definitions_;
    std::vector<CompositeStep> steps_;

public:
    CompositeAction(
        std::string name,
        std::vector<InputDefinition> definitions,
        std::vector<CompositeStep> steps)
        : name_(std::move(name)),
          definitions_(std::move(definitions)),
          steps_(std::move(steps)) {}

    void execute(
        const std::map<std::string, std::string>& supplied,
        ExecutionContext& context) const {

        auto resolved = InputValidator::resolve(definitions_, supplied);

        // Action inputs are passed explicitly. The action does not receive
        // arbitrary values from a caller's process unless they are supplied.
        for (const auto& [name, value] : resolved) {
            context.inputs["action." + name] = value;
        }

        for (const auto& step : steps_) {
            context.log("Composite action " + name_ + ": " + step.name);

            try {
                step.execute(context);
            } catch (const std::exception& error) {
                throw GovernanceError(
                    "Composite action step '" + step.name +
                    "' failed: " + error.what());
            }
        }
    }
};

struct JobDefinition {
    std::string name;
    std::vector<std::string> needs;
    void (*execute)(ExecutionContext&, const CompositeAction&);
};

class WorkflowEngine {
private:
    std::vector<JobDefinition> jobs_;
    std::map<std::string, JobResult> results_;
    const CompositeAction& action_;

    void validate_graph() const {
        std::map<std::string, int> color;

        for (const auto& job : jobs_) {
            for (const auto& dependency : job.needs) {
                if (!results_.count(dependency)) {
                    throw GovernanceError(
                        "Unknown dependency '" + dependency +
                        "' in job '" + job.name + "'");
                }
            }
        }

        std::function<void(const std::string&)> visit =
            [&](const std::string& name) {
                if (color[name] == 1) {
                    throw GovernanceError(
                        "Dependency cycle detected at " + name);
                }
                if (color[name] == 2) return;

                color[name] = 1;

                auto found = std::find_if(
                    jobs_.begin(), jobs_.end(),
                    [&](const JobDefinition& job) {
                        return job.name == name;
                    });

                for (const auto& dependency : found->needs) {
                    visit(dependency);
                }

                color[name] = 2;
            };

        for (const auto& job : jobs_) visit(job.name);
    }

public:
    WorkflowEngine(
        std::vector<JobDefinition> jobs,
        const CompositeAction& action)
        : jobs_(std::move(jobs)), action_(action) {

        for (const auto& job : jobs_) {
            if (!results_.emplace(job.name, JobResult{}).second) {
                throw GovernanceError("Duplicate job name: " + job.name);
            }
        }
        validate_graph();
    }

    void run(ExecutionContext& context) {
        std::set<std::string> remaining;
        for (const auto& job : jobs_) remaining.insert(job.name);

        while (!remaining.empty()) {
            bool progressed = false;

            for (auto iterator = remaining.begin();
                 iterator != remaining.end();) {

                const std::string name = *iterator;
                auto definition = std::find_if(
                    jobs_.begin(), jobs_.end(),
                    [&](const JobDefinition& job) {
                        return job.name == name;
                    });

                bool dependency_failed = false;
                bool dependencies_complete = true;

                for (const auto& dependency : definition->needs) {
                    JobState state = results_.at(dependency).state;
                    if (state == JobState::Failed ||
                        state == JobState::Skipped) {
                        dependency_failed = true;
                    }
                    if (state != JobState::Succeeded) {
                        dependencies_complete = false;
                    }
                }

                if (dependency_failed) {
                    results_[name].state = JobState::Skipped;
                    context.log("Skipped job " + name +
                                " because a dependency failed.");
                    iterator = remaining.erase(iterator);
                    progressed = true;
                    continue;
                }

                if (!dependencies_complete) {
                    ++iterator;
                    continue;
                }

                results_[name].state = JobState::Running;
                context.log("Starting job " + name);

                try {
                    definition->execute(context, action_);
                    results_[name].state = JobState::Succeeded;
                    context.log("Completed job " + name);
                } catch (const std::exception& error) {
                    results_[name].state = JobState::Failed;
                    results_[name].error = error.what();
                    context.log("Job " + name + " failed: " + error.what());
                }

                iterator = remaining.erase(iterator);
                progressed = true;
            }

            if (!progressed) {
                throw GovernanceError(
                    "Scheduler cannot make progress with pending jobs.");
            }
        }
    }

    const std::map<std::string, JobResult>& results() const {
        return results_;
    }
};

void validate_revision(ExecutionContext& context) {
    auto found = context.environment.find("GITHUB_SHA");

    if (found == context.environment.end() ||
        found->second.size() < 7 ||
        found->second.size() > 64 ||
        !std::all_of(found->second.begin(), found->second.end(),
            [](unsigned char character) {
                return std::isxdigit(character) != 0;
            })) {
        throw GovernanceError("Invalid GITHUB_SHA.");
    }

    context.log("Commit revision format validated.");
}

void package_release(ExecutionContext& context) {
    const auto version = context.inputs.at("action.version");

    bool valid = false;
    std::size_t start = 0;
    int components = 0;

    while (start <= version.size()) {
        std::size_t end = version.find('.', start);
        if (end == std::string::npos) end = version.size();

        std::string part = version.substr(start, end - start);

        if (part.empty() ||
            !std::all_of(part.begin(), part.end(),
                [](unsigned char character) {
                    return std::isdigit(character) != 0;
                })) {
            valid = false;
            components = 0;
            break;
        }

        ++components;
        valid = components == 3;

        if (end == version.size()) break;
        start = end + 1;
    }

    if (!valid) {
        throw GovernanceError("Release version must be MAJOR.MINOR.PATCH.");
    }

    const std::string revision =
        context.environment.at("GITHUB_SHA").substr(0, 12);

    context.outputs["artifact"] =
        "service-" + version + "-" + revision + ".tar";

    context.log("Prepared immutable release artifact metadata.");
}

void verify_deployment(ExecutionContext& context) {
    const auto target = context.inputs.at("action.target");

    if (target == "production" &&
        context.environment.at("PRODUCTION_APPROVED") != "true") {
        throw GovernanceError(
            "Production deployment lacks an approval signal.");
    }

    const auto token = context.secrets.find("DEPLOY_TOKEN");
    if (token == context.secrets.end() || token->second.size() < 16) {
        throw GovernanceError("Deployment credential is absent or too short.");
    }

    context.outputs["deployment-target"] = target;
    context.log("Deployment authorization checks passed.");
}

void test_job(ExecutionContext& context, const CompositeAction&) {
    context.log("Release metadata tests passed.");
}

void release_job(ExecutionContext& context, const CompositeAction& action) {
    action.execute(
        {
            {"version", context.inputs.at("version")},
            {"target", context.inputs.at("target")}
        },
        context);
}

void audit_job(ExecutionContext& context, const CompositeAction&) {
    if (!context.outputs.count("artifact")) {
        throw GovernanceError("Cannot audit a release without an artifact.");
    }
    context.outputs["audit"] = "recorded:" + context.outputs.at("artifact");
    context.log("Release audit record prepared.");
}

int main() {
    try {
        CompositeAction deploy_action(
            "deploy-service",
            {
                {"version", true, "", {}},
                {"target", true, "", {"staging", "production"}}
            },
            {
                {"validate revision", validate_revision},
                {"package release", package_release},
                {"authorize deployment", verify_deployment}
            });

        ExecutionContext context;
        context.inputs = {
            {"version", "3.2.0"},
            {"target", "staging"}
        };
        context.secrets = {
            {"DEPLOY_TOKEN", "local-example-secret-12345"}
        };
        context.environment = {
            {"GITHUB_SHA",
             "b712af45cdef0123456789abcdef0123456789ab"},
            {"PRODUCTION_APPROVED", "false"}
        };

        WorkflowEngine workflow(
            {
                {"test", {}, test_job},
                {"release", {"test"}, release_job},
                {"audit", {"release"}, audit_job}
            },
            deploy_action);

        workflow.run(context);

        std::cout << "Repository automation workflow\n";
        for (const auto& [name, result] : workflow.results()) {
            std::cout << "  " << name << ": "
                      << to_string(result.state);
            if (!result.error.empty()) {
                std::cout << " (" << result.error << ")";
            }
            std::cout << '\n';
        }

        std::cout << "\nExecution logs\n";
        for (const auto& entry : context.logs) {
            std::cout << "  " << entry << '\n';
        }

        std::cout << "\nOutputs\n";
        for (const auto& [name, value] : context.outputs) {
            std::cout << "  " << name << " = " << value << '\n';
        }

        // Re-run with a production target to exercise the policy failure path.
        ExecutionContext blocked;
        blocked.inputs = {
            {"version", "3.2.0"},
            {"target", "production"}
        };
        blocked.secrets = context.secrets;
        blocked.environment = context.environment;

        WorkflowEngine production_workflow(
            {
                {"test", {}, test_job},
                {"release", {"test"}, release_job},
                {"audit", {"release"}, audit_job}
            },
            deploy_action);

        production_workflow.run(blocked);

        std::cout << "\nProduction policy evaluation\n";
        for (const auto& [name, result] : production_workflow.results()) {
            std::cout << "  " << name << ": "
                      << to_string(result.state) << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal configuration error: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

enum class JobStatus {
    Enabled,
    Disabled
};

enum class BuildStatus {
    Success,
    Failure,
    Aborted
};

enum class TriggerType {
    Manual,
    Timer,
    SCM,
    Upstream
};

std::string toString(BuildStatus status) {
    switch (status) {
        case BuildStatus::Success: return "SUCCESS";
        case BuildStatus::Failure: return "FAILURE";
        case BuildStatus::Aborted: return "ABORTED";
    }
    return "UNKNOWN";
}

std::string toString(TriggerType trigger) {
    switch (trigger) {
        case TriggerType::Manual: return "manual";
        case TriggerType::Timer: return "timer";
        case TriggerType::SCM: return "scm";
        case TriggerType::Upstream: return "upstream";
    }
    return "unknown";
}

class JobError : public std::runtime_error {
public:
    explicit JobError(const std::string& message)
        : std::runtime_error(message) {}
};

struct ParameterDefinition {
    std::string name;
    std::string defaultValue;
    bool required{true};
    std::set<std::string> choices;

    std::string validate(const std::string& value) const {
        if (required && value.empty()) {
            throw JobError("Parameter " + name + " cannot be empty");
        }

        if (!choices.empty() &&
            choices.find(value) == choices.end()) {
            throw JobError(
                "Invalid value for parameter " + name + ": " + value
            );
        }

        return value;
    }
};

struct Build {
    int number{};
    std::map<std::string, std::string> parameters;
    BuildStatus status{BuildStatus::Success};
    fs::path workspace;
    std::vector<std::string> log;
};

class FreestyleJob {
private:
    std::string name_;
    std::string description_;
    fs::path workspaceRoot_;
    JobStatus status_{JobStatus::Enabled};

    std::map<std::string, ParameterDefinition> parameters_;
    std::set<TriggerType> triggers_;
    std::vector<Build> builds_;

    using Builder = void (*)(
        const std::map<std::string, std::string>&,
        const fs::path&,
        std::vector<std::string>&
    );

    std::vector<Builder> builders_;

public:
    FreestyleJob(
        std::string name,
        std::string description,
        fs::path workspaceRoot
    )
        : name_(std::move(name)),
          description_(std::move(description)),
          workspaceRoot_(std::move(workspaceRoot)) {}

    void addParameter(ParameterDefinition definition) {
        if (parameters_.contains(definition.name)) {
            throw JobError(
                "Duplicate parameter: " + definition.name
            );
        }

        parameters_.emplace(
            definition.name,
            std::move(definition)
        );
    }

    void addTrigger(TriggerType trigger) {
        triggers_.insert(trigger);
    }

    void addBuilder(Builder builder) {
        if (builder == nullptr) {
            throw JobError("Builder cannot be null");
        }

        builders_.push_back(builder);
    }

    std::map<std::string, std::string> resolveParameters(
        const std::map<std::string, std::string>& supplied
    ) const {
        for (const auto& [name, value] : supplied) {
            if (!parameters_.contains(name)) {
                throw JobError("Unknown parameter: " + name);
            }
        }

        std::map<std::string, std::string> result;

        for (const auto& [name, definition] : parameters_) {
            auto it = supplied.find(name);
            const std::string value =
                it == supplied.end()
                    ? definition.defaultValue
                    : it->second;

            result[name] = definition.validate(value);
        }

        return result;
    }

    Build run(
        const std::map<std::string, std::string>& supplied,
        TriggerType trigger
    ) {
        if (status_ != JobStatus::Enabled) {
            throw JobError("Job is disabled");
        }

        if (trigger != TriggerType::Manual &&
            !triggers_.contains(trigger)) {
            throw JobError(
                "Requested trigger is not configured"
            );
        }

        auto parameters = resolveParameters(supplied);
        const int number =
            static_cast<int>(builds_.size()) + 1;

        const fs::path workspace =
            workspaceRoot_ /
            name_ /
            ("build-" + std::to_string(number));

        fs::create_directories(workspace);

        Build build;
        build.number = number;
        build.parameters = parameters;
        build.workspace = workspace;
        build.status = BuildStatus::Success;

        build.log.push_back(
            "BUILD #" + std::to_string(number) +
            " started by " + toString(trigger) + " trigger"
        );
        build.log.push_back(
            "Workspace: " + workspace.string()
        );

        try {
            for (const auto builder : builders_) {
                builder(
                    parameters,
                    workspace,
                    build.log
                );
            }

            build.log.push_back(
                "Build completed successfully"
            );
        } catch (const std::exception& error) {
            build.status = BuildStatus::Failure;
            build.log.push_back(
                "Build failed: " +
                std::string(error.what())
            );
        }

        builds_.push_back(build);
        return build;
    }

    const std::vector<Build>& builds() const {
        return builds_;
    }

    const std::string& name() const {
        return name_;
    }

    const std::set<TriggerType>& triggers() const {
        return triggers_;
    }
};

void createManifest(
    const std::map<std::string, std::string>& parameters,
    const fs::path& workspace,
    std::vector<std::string>& log
) {
    std::ofstream output(workspace / "manifest.txt");

    if (!output) {
        throw JobError("Cannot create build manifest");
    }

    output << "Freestyle build manifest\n";

    for (const auto& [name, value] : parameters) {
        output << name << "=" << value << '\n';
    }

    log.push_back("Created manifest.txt");
}

void validateRelease(
    const std::map<std::string, std::string>& parameters,
    const fs::path&,
    std::vector<std::string>& log
) {
    const auto environment = parameters.at("ENVIRONMENT");
    const auto version = parameters.at("VERSION");

    if (environment == "production" &&
        version.rfind("dev-", 0) == 0) {
        throw JobError(
            "Production builds cannot use development versions"
        );
    }

    log.push_back(
        "Release validation passed for " + environment
    );
}

void createArtifact(
    const std::map<std::string, std::string>& parameters,
    const fs::path& workspace,
    std::vector<std::string>& log
) {
    const auto environment = parameters.at("ENVIRONMENT");
    const auto version = parameters.at("VERSION");

    const fs::path artifact =
        workspace /
        ("application-" + version + "-" +
         environment + ".txt");

    std::ofstream output(artifact);

    if (!output) {
        throw JobError("Cannot create build artifact");
    }

    output << "Freestyle build artifact\n";
    output << "version=" << version << '\n';
    output << "environment=" << environment << '\n';

    log.push_back(
        "Created artifact: " + artifact.filename().string()
    );
}

void printBuild(const Build& build) {
    std::cout
        << "\nBuild #" << build.number
        << ": " << toString(build.status)
        << '\n';

    for (const auto& [name, value] : build.parameters) {
        std::cout << "  " << name << "=" << value << '\n';
    }

    for (const auto& line : build.log) {
        std::cout << "  " << line << '\n';
    }
}

int main() {
    try {
        const fs::path root =
            fs::temp_directory_path() /
            "jenkins-freestyle-cpp";

        fs::remove_all(root);
        fs::create_directories(root);

        FreestyleJob job(
            "release-application",
            "Parameterized Freestyle release workflow",
            root
        );

        job.addParameter({
            "ENVIRONMENT",
            "staging",
            true,
            {"development", "staging", "production"}
        });

        job.addParameter({
            "VERSION",
            "1.0.0",
            true,
            {}
        });

        job.addTrigger(TriggerType::Timer);
        job.addTrigger(TriggerType::SCM);
        job.addTrigger(TriggerType::Upstream);

        job.addBuilder(createManifest);
        job.addBuilder(validateRelease);
        job.addBuilder(createArtifact);

        const auto first = job.run(
            {
                {"ENVIRONMENT", "staging"},
                {"VERSION", "1.4.0"}
            },
            TriggerType::SCM
        );

        if (first.status != BuildStatus::Success) {
            throw JobError("First build should succeed");
        }

        const auto second = job.run(
            {
                {"ENVIRONMENT", "production"},
                {"VERSION", "dev-2.0.0"}
            },
            TriggerType::Upstream
        );

        if (second.status != BuildStatus::Failure) {
            throw JobError(
                "Invalid production build should fail"
            );
        }

        const auto third = job.run(
            {
                {"ENVIRONMENT", "production"},
                {"VERSION", "2.0.0"}
            },
            TriggerType::Manual
        );

        if (third.status != BuildStatus::Success) {
            throw JobError(
                "Valid production build should succeed"
            );
        }

        std::cout << "Jenkins Freestyle Job Simulation\n";
        std::cout << "================================\n";
        std::cout << "Job: " << job.name() << '\n';
        std::cout << "Build count: "
                  << job.builds().size() << '\n';

        for (const auto& build : job.builds()) {
            printBuild(build);
        }

        fs::remove_all(root);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: "
                  << error.what() << '\n';
        return 1;
    }
}

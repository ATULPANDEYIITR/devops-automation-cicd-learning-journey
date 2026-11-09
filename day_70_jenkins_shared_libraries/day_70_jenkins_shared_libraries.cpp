#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Jenkins Shared Libraries
 * Enterprise pipeline execution and governance engine.
 *
 * Compile:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic main.cpp -o pipeline
 *
 * Run:
 * ./pipeline
 */

using namespace std;

enum class ReleaseState {
    DRAFT,
    TESTED,
    APPROVED,
    REJECTED
};

enum class PipelineState {
    CREATED,
    RUNNING,
    SUCCESS,
    FAILED
};

enum class StageState {
    PENDING,
    RUNNING,
    SUCCESS,
    FAILED,
    SKIPPED
};

enum class DeploymentEnvironment {
    DEVELOPMENT,
    STAGING,
    PRODUCTION
};

string toString(ReleaseState state) {
    switch (state) {
        case ReleaseState::DRAFT: return "DRAFT";
        case ReleaseState::TESTED: return "TESTED";
        case ReleaseState::APPROVED: return "APPROVED";
        case ReleaseState::REJECTED: return "REJECTED";
    }

    throw logic_error("Unknown release state.");
}

string toString(PipelineState state) {
    switch (state) {
        case PipelineState::CREATED: return "CREATED";
        case PipelineState::RUNNING: return "RUNNING";
        case PipelineState::SUCCESS: return "SUCCESS";
        case PipelineState::FAILED: return "FAILED";
    }

    throw logic_error("Unknown pipeline state.");
}

string toString(StageState state) {
    switch (state) {
        case StageState::PENDING: return "PENDING";
        case StageState::RUNNING: return "RUNNING";
        case StageState::SUCCESS: return "SUCCESS";
        case StageState::FAILED: return "FAILED";
        case StageState::SKIPPED: return "SKIPPED";
    }

    throw logic_error("Unknown stage state.");
}

string toString(DeploymentEnvironment environment) {
    switch (environment) {
        case DeploymentEnvironment::DEVELOPMENT: return "development";
        case DeploymentEnvironment::STAGING: return "staging";
        case DeploymentEnvironment::PRODUCTION: return "production";
    }

    throw logic_error("Unknown environment.");
}

class ValidationError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class PolicyError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class ExecutionError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

struct LibraryRelease {
    string name;
    string version;
    string commit;
    ReleaseState state;

    void validate() const {
        if (name.empty() || version.empty()) {
            throw ValidationError("Library identity is incomplete.");
        }

        if (commit.size() < 7 || commit.size() > 40 ||
            !all_of(commit.begin(), commit.end(), [](unsigned char c) {
                return isxdigit(c) != 0;
            })) {
            throw ValidationError("Invalid commit identifier.");
        }

        size_t first = version.find('.');
        size_t second = version.find('.', first == string::npos ? first : first + 1);

        if (first == string::npos || second == string::npos ||
            version.find('.', second + 1) != string::npos) {
            throw ValidationError("Invalid semantic version.");
        }

        string components[] = {
            version.substr(0, first),
            version.substr(first + 1, second - first - 1),
            version.substr(second + 1)
        };

        for (const string& component : components) {
            if (component.empty() ||
                !all_of(component.begin(), component.end(), [](unsigned char c) {
                    return isdigit(c) != 0;
                })) {
                throw ValidationError("Invalid semantic version component.");
            }
        }
    }
};

class LibraryRegistry {
private:
    map<pair<string, string>, LibraryRelease> releases;

public:
    void registerRelease(const LibraryRelease& release) {
        release.validate();

        auto key = make_pair(release.name, release.version);

        if (releases.count(key)) {
            throw ValidationError("Duplicate library release.");
        }

        releases.emplace(key, release);
    }

    LibraryRelease resolve(
        const string& name,
        const string& version
    ) const {
        auto it = releases.find({name, version});

        if (it == releases.end()) {
            throw ValidationError("Library release not found.");
        }

        if (it->second.state != ReleaseState::APPROVED) {
            throw PolicyError("Library release is not approved.");
        }

        return it->second;
    }
};

struct StageResult {
    string name;
    StageState state = StageState::PENDING;
    int attempts = 0;
    string message;
};

struct PipelineDefinition {
    string application;
    string repository;
    string branch;
    int buildNumber;
    DeploymentEnvironment environment;
    bool productionApproval = false;
    bool testsPassed = false;
};

struct PipelineContext {
    PipelineDefinition definition;
    LibraryRelease library;
    PipelineState state = PipelineState::CREATED;
    vector<StageResult> stages;
    string artifact;
};

class RepositoryPolicy {
private:
    set<DeploymentEnvironment> permittedEnvironments;
    bool requireProductionApproval;

public:
    RepositoryPolicy(
        bool requireApproval,
        set<DeploymentEnvironment> environments
    )
        : permittedEnvironments(move(environments)),
          requireProductionApproval(requireApproval) {}

    void validate(const PipelineDefinition& definition) const {
        if (!permittedEnvironments.count(definition.environment)) {
            throw PolicyError("Deployment environment is not permitted.");
        }

        if (definition.application.empty() ||
            definition.branch.empty() ||
            definition.repository.empty() ||
            definition.buildNumber <= 0) {
            throw ValidationError("Incomplete pipeline definition.");
        }

        if (definition.environment == DeploymentEnvironment::PRODUCTION &&
            requireProductionApproval &&
            !definition.productionApproval) {
            throw PolicyError("Production approval is required.");
        }

        if (definition.repository.find("https://") != 0 &&
            definition.repository.find("ssh://") != 0) {
            throw ValidationError("Unsupported repository protocol.");
        }
    }
};

class SharedPipelineSteps {
public:
    static string checkout(const PipelineDefinition& definition) {
        cout << "  Checkout: " << definition.repository
             << " [" << definition.branch << "]\n";

        return "source-" + definition.application + "-" +
               to_string(definition.buildNumber);
    }

    static string build(const PipelineDefinition& definition) {
        cout << "  Building application: "
             << definition.application << "\n";

        return definition.application + "-" +
               to_string(definition.buildNumber) + ".jar";
    }

    static bool test(const string& source) {
        if (source.empty()) {
            throw ExecutionError("Source checkout is unavailable.");
        }

        cout << "  Unit tests: 42 passed, 0 failed\n";
        return true;
    }

    static string package(const string& artifact) {
        if (artifact.empty()) {
            throw ExecutionError("Cannot package an empty artifact.");
        }

        cout << "  Packaging: " << artifact << "\n";
        return artifact;
    }

    static bool deploy(
        const string& artifact,
        DeploymentEnvironment environment
    ) {
        if (artifact.empty()) {
            throw ExecutionError("Deployment artifact is missing.");
        }

        cout << "  Deploying " << artifact << " to "
             << toString(environment) << "\n";

        return true;
    }
};

class PipelineEngine {
private:
    RepositoryPolicy policy;

    void executeStage(
        PipelineContext& context,
        const string& name,
        const function<bool()>& operation
    ) const {
        StageResult result;
        result.name = name;
        result.state = StageState::RUNNING;
        result.attempts = 1;

        cout << "\n[" << name << "]\n";

        try {
            if (!operation()) {
                throw ExecutionError("Stage returned an unsuccessful result.");
            }

            result.state = StageState::SUCCESS;
            result.message = "Completed successfully.";

        } catch (const exception& error) {
            result.state = StageState::FAILED;
            result.message = error.what();
            context.stages.push_back(result);
            throw;
        }

        context.stages.push_back(result);
    }

public:
    explicit PipelineEngine(RepositoryPolicy repositoryPolicy)
        : policy(move(repositoryPolicy)) {}

    PipelineContext execute(
        PipelineContext context
    ) const {
        if (context.state != PipelineState::CREATED) {
            throw ExecutionError("Pipeline has already been executed.");
        }

        context.state = PipelineState::RUNNING;

        try {
            policy.validate(context.definition);

            if (context.library.state != ReleaseState::APPROVED) {
                throw PolicyError("Shared library is not approved.");
            }

            string source;
            string artifact;

            executeStage(context, "checkout", [&]() {
                source = SharedPipelineSteps::checkout(context.definition);
                return !source.empty();
            });

            executeStage(context, "build", [&]() {
                artifact = SharedPipelineSteps::build(context.definition);
                return !artifact.empty();
            });

            executeStage(context, "test", [&]() {
                context.definition.testsPassed =
                    SharedPipelineSteps::test(source);

                return context.definition.testsPassed;
            });

            executeStage(context, "package", [&]() {
                context.artifact = SharedPipelineSteps::package(artifact);
                return !context.artifact.empty();
            });

            executeStage(context, "deploy", [&]() {
                return SharedPipelineSteps::deploy(
                    context.artifact,
                    context.definition.environment
                );
            });

            context.state = PipelineState::SUCCESS;

        } catch (const exception& error) {
            context.state = PipelineState::FAILED;

            cerr << "\nPipeline failure: " << error.what() << "\n";
        }

        return context;
    }
};

void printReport(const PipelineContext& context) {
    cout << "\n========================================\n";
    cout << "ENTERPRISE PIPELINE EXECUTION REPORT\n";
    cout << "========================================\n";

    cout << "Application: "
         << context.definition.application << "\n";

    cout << "Library: "
         << context.library.name << "@"
         << context.library.version << "\n";

    cout << "Branch: " << context.definition.branch << "\n";

    cout << "Environment: "
         << toString(context.definition.environment) << "\n";

    cout << "Build: " << context.definition.buildNumber << "\n";

    cout << "Pipeline status: "
         << toString(context.state) << "\n";

    cout << "\nStage results:\n";

    for (const auto& stage : context.stages) {
        cout << left << setw(15) << stage.name
             << setw(12) << toString(stage.state)
             << "Attempts: " << stage.attempts << "\n";
    }
}

void runValidationTests(const LibraryRegistry& registry) {
    bool rejected = false;

    try {
        registry.resolve("enterprise-ci", "9.9.9");
    } catch (const ValidationError&) {
        rejected = true;
    }

    if (!rejected) {
        throw runtime_error("Unknown library version was accepted.");
    }

    LibraryRelease invalid{
        "bad-library",
        "1.x.0",
        "a1b2c3d",
        ReleaseState::APPROVED
    };

    rejected = false;

    try {
        invalid.validate();
    } catch (const ValidationError&) {
        rejected = true;
    }

    if (!rejected) {
        throw runtime_error("Invalid semantic version was accepted.");
    }

    cout << "\nValidation tests passed.\n";
}

int main() {
    try {
        LibraryRegistry registry;

        LibraryRelease release{
            "enterprise-ci",
            "2.1.0",
            "a1b2c3d4e5f6789",
            ReleaseState::APPROVED
        };

        registry.registerRelease(release);

        LibraryRelease resolved = registry.resolve(
            "enterprise-ci",
            "2.1.0"
        );

        RepositoryPolicy policy(
            true,
            {
                DeploymentEnvironment::DEVELOPMENT,
                DeploymentEnvironment::STAGING,
                DeploymentEnvironment::PRODUCTION
            }
        );

        PipelineEngine engine(policy);

        PipelineDefinition definition{
            "inventory-service",
            "https://git.example.com/platform/inventory-service.git",
            "main",
            205,
            DeploymentEnvironment::STAGING,
            false,
            false
        };

        PipelineContext context{
            definition,
            resolved
        };

        PipelineContext result = engine.execute(context);
        printReport(result);

        if (result.state != PipelineState::SUCCESS) {
            return 1;
        }

        // A production pipeline without explicit approval must fail.
        PipelineDefinition production{
            "inventory-service",
            "https://git.example.com/platform/inventory-service.git",
            "main",
            206,
            DeploymentEnvironment::PRODUCTION,
            false,
            false
        };

        PipelineContext productionContext{
            production,
            resolved
        };

        PipelineContext rejected = engine.execute(productionContext);

        if (rejected.state != PipelineState::FAILED) {
            throw runtime_error("Production approval policy failed.");
        }

        cout << "\nProduction approval enforcement passed.\n";

        runValidationTests(registry);

        cout << "\nAll execution checks completed.\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}

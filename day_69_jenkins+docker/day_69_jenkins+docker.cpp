#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Jenkins + Docker pipeline governance engine.
 *
 * Models:
 * - Repository and source revision
 * - Jenkins pipeline stages
 * - Docker image lifecycle
 * - Build and test results
 * - Registry publishing
 * - Deployment eligibility
 * - Failure handling
 * - Protected production deployment
 *
 * Compile:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic main.cpp -o pipeline
 */

using namespace std;

enum class Stage {
    CHECKOUT,
    BUILD,
    TEST,
    IMAGE_SCAN,
    PUSH,
    DEPLOY
};

enum class State {
    PENDING,
    RUNNING,
    SUCCESS,
    FAILED,
    SKIPPED
};

enum class Environment {
    DEVELOPMENT,
    STAGING,
    PRODUCTION
};

string toString(State state) {
    switch (state) {
        case State::PENDING: return "PENDING";
        case State::RUNNING: return "RUNNING";
        case State::SUCCESS: return "SUCCESS";
        case State::FAILED: return "FAILED";
        case State::SKIPPED: return "SKIPPED";
    }

    return "UNKNOWN";
}

string toString(Stage stage) {
    switch (stage) {
        case Stage::CHECKOUT: return "CHECKOUT";
        case Stage::BUILD: return "BUILD";
        case Stage::TEST: return "TEST";
        case Stage::IMAGE_SCAN: return "IMAGE_SCAN";
        case Stage::PUSH: return "PUSH";
        case Stage::DEPLOY: return "DEPLOY";
    }

    return "UNKNOWN";
}

struct DockerImage {
    string repository;
    string tag;
    string digest;
    bool built = false;
    bool scanned = false;
    bool published = false;

    string fullName() const {
        return repository + ":" + tag;
    }

    void validate() const {
        if (repository.empty() || tag.empty()) {
            throw invalid_argument("Invalid Docker image.");
        }

        if (repository.find(' ') != string::npos ||
            tag.find(' ') != string::npos) {
            throw invalid_argument("Docker image contains whitespace.");
        }
    }
};

struct StageResult {
    Stage stage;
    State state = State::PENDING;
    string message;
};

struct PipelinePolicy {
    bool requireTests = true;
    bool requireSecurityScan = true;
    bool requireRegistryPush = true;
    bool allowProductionDeployment = false;
    int maximumFailures = 0;
};

class PipelineEngine {
private:
    string application;
    string commit;
    string branch;

    DockerImage image;
    PipelinePolicy policy;
    Environment environment;

    map<Stage, StageResult> results;

    int failureCount = 0;
    bool cancelled = false;

public:
    PipelineEngine(
        string app,
        string revision,
        string sourceBranch,
        DockerImage dockerImage,
        PipelinePolicy pipelinePolicy,
        Environment target
    )
        : application(move(app)),
          commit(move(revision)),
          branch(move(sourceBranch)),
          image(move(dockerImage)),
          policy(pipelinePolicy),
          environment(target) {

        validateConfiguration();

        for (Stage stage : {
            Stage::CHECKOUT,
            Stage::BUILD,
            Stage::TEST,
            Stage::IMAGE_SCAN,
            Stage::PUSH,
            Stage::DEPLOY
        }) {
            results.emplace(
                stage,
                StageResult{stage, State::PENDING, "Awaiting execution"}
            );
        }
    }

    void validateConfiguration() const {
        if (application.empty() || commit.empty() || branch.empty()) {
            throw invalid_argument("Missing repository metadata.");
        }

        image.validate();

        if (policy.maximumFailures < 0) {
            throw invalid_argument("Invalid failure threshold.");
        }

        if (
            environment == Environment::PRODUCTION &&
            !policy.allowProductionDeployment
        ) {
            throw invalid_argument(
                "Production deployment is not authorized."
            );
        }
    }

    void complete(
        Stage stage,
        bool success,
        const string& message
    ) {
        auto& result = results.at(stage);

        if (result.state != State::RUNNING) {
            throw logic_error("Invalid stage state transition.");
        }

        result.state = success ? State::SUCCESS : State::FAILED;
        result.message = message;

        if (!success) {
            failureCount++;
        }

        cout << "[" << toString(stage) << "] "
             << toString(result.state)
             << ": " << message << '\n';
    }

    bool execute(
        Stage stage,
        const string& description,
        bool success
    ) {
        if (cancelled) {
            return false;
        }

        auto& result = results.at(stage);

        if (result.state != State::PENDING) {
            throw logic_error("Stage already executed.");
        }

        result.state = State::RUNNING;

        cout << "\nExecuting " << description << '\n';

        complete(
            stage,
            success,
            success ? "Validation passed" : "Validation failed"
        );

        return success;
    }

    bool checkout() {
        return execute(
            Stage::CHECKOUT,
            "Source checkout",
            commit.size() >= 7
        );
    }

    bool build() {
        bool success = execute(
            Stage::BUILD,
            "Docker image build",
            !image.repository.empty()
        );

        image.built = success;
        image.digest = success ? "sha256:demo-build-digest" : "";

        return success;
    }

    bool test() {
        if (!policy.requireTests) {
            results.at(Stage::TEST).state = State::SKIPPED;
            return true;
        }

        return execute(
            Stage::TEST,
            "Container test validation",
            image.built
        );
    }

    bool scan() {
        if (!policy.requireSecurityScan) {
            results.at(Stage::IMAGE_SCAN).state = State::SKIPPED;
            return true;
        }

        bool success = execute(
            Stage::IMAGE_SCAN,
            "Docker image security scan",
            image.built
        );

        image.scanned = success;

        return success;
    }

    bool push() {
        if (!policy.requireRegistryPush) {
            results.at(Stage::PUSH).state = State::SKIPPED;
            return true;
        }

        bool success = execute(
            Stage::PUSH,
            "Docker registry publishing",
            image.built && image.scanned
        );

        image.published = success;

        return success;
    }

    bool deploy() {
        bool prerequisites =
            image.built &&
            (!policy.requireTests ||
             results.at(Stage::TEST).state == State::SUCCESS) &&
            (!policy.requireSecurityScan || image.scanned) &&
            (!policy.requireRegistryPush || image.published);

        if (!prerequisites) {
            results.at(Stage::DEPLOY).state = State::SKIPPED;
            results.at(Stage::DEPLOY).message =
                "Deployment prerequisites not satisfied.";

            return false;
        }

        return execute(
            Stage::DEPLOY,
            "Application deployment",
            true
        );
    }

    bool run() {
        cout << "\n====================================\n";
        cout << "JENKINS + DOCKER PIPELINE\n";
        cout << "Application: " << application << '\n';
        cout << "Branch: " << branch << '\n';
        cout << "Commit: " << commit << '\n';
        cout << "Image: " << image.fullName() << '\n';
        cout << "====================================\n";

        vector<bool (PipelineEngine::*)()> stages = {
            &PipelineEngine::checkout,
            &PipelineEngine::build,
            &PipelineEngine::test,
            &PipelineEngine::scan,
            &PipelineEngine::push,
            &PipelineEngine::deploy
        };

        for (auto stage : stages) {
            if (!(this->*stage)()) {
                cancelled = true;
                break;
            }
        }

        return results.at(Stage::DEPLOY).state == State::SUCCESS;
    }

    void report() const {
        cout << "\n========== PIPELINE REPORT ==========\n";

        for (const auto& [stage, result] : results) {
            cout << left << setw(16)
                 << toString(stage)
                 << setw(12)
                 << toString(result.state)
                 << result.message << '\n';
        }

        cout << "\nImage: " << image.fullName() << '\n';
        cout << "Digest: " << image.digest << '\n';
        cout << "Published: "
             << (image.published ? "YES" : "NO") << '\n';
        cout << "Failures: " << failureCount << '\n';
        cout << "Deployment: "
             << (results.at(Stage::DEPLOY).state == State::SUCCESS
                    ? "SUCCESS"
                    : "NOT COMPLETED")
             << '\n';
    }
};

int main() {
    try {
        DockerImage image{
            "inventory-api",
            "1.0.0",
            "",
            false,
            false,
            false
        };

        PipelinePolicy policy{
            true,
            true,
            true,
            true,
            0
        };

        PipelineEngine pipeline(
            "Inventory Management",
            "a83f9c2",
            "main",
            image,
            policy,
            Environment::PRODUCTION
        );

        bool success = pipeline.run();

        pipeline.report();

        return success ? EXIT_SUCCESS : EXIT_FAILURE;

    } catch (const exception& error) {
        cerr << "Pipeline error: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}

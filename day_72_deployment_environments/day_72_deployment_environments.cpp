#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class Environment {
    Development,
    QA,
    Staging,
    Production
};

enum class DeploymentStatus {
    Pending,
    Succeeded,
    Failed,
    RolledBack
};

enum class MergeStrategy {
    Rolling,
    BlueGreen,
    Canary
};

string toString(Environment environment) {
    switch (environment) {
        case Environment::Development: return "development";
        case Environment::QA: return "qa";
        case Environment::Staging: return "staging";
        case Environment::Production: return "production";
    }
    throw invalid_argument("Unknown environment.");
}

string toString(DeploymentStatus status) {
    switch (status) {
        case DeploymentStatus::Pending: return "pending";
        case DeploymentStatus::Succeeded: return "succeeded";
        case DeploymentStatus::Failed: return "failed";
        case DeploymentStatus::RolledBack: return "rolled_back";
    }
    throw invalid_argument("Unknown status.");
}

struct Artifact {
    string name;
    string version;
    string checksum;
    string commit;

    string identity() const {
        return name + ":" + version + ":" + checksum;
    }

    void validate() const {
        if (name.empty() || version.empty() || checksum.empty()) {
            throw invalid_argument("Artifact fields cannot be empty.");
        }

        if (commit.size() < 7 || commit.size() > 40) {
            throw invalid_argument("Invalid commit identifier.");
        }

        if (!all_of(commit.begin(), commit.end(), [](unsigned char c) {
            return isxdigit(c);
        })) {
            throw invalid_argument("Commit identifier must be hexadecimal.");
        }
    }
};

struct EnvironmentPolicy {
    Environment environment;
    int replicas;
    bool approvalRequired;
    set<string> requiredChecks;
    set<string> authorizedDeployers;
    MergeStrategy strategy;

    void validate() const {
        if (replicas < 1 || replicas > 100) {
            throw invalid_argument("Replica count outside allowed range.");
        }

        if (authorizedDeployers.empty()) {
            throw invalid_argument("At least one deployer is required.");
        }
    }
};

struct DeploymentRecord {
    int id;
    Environment environment;
    Artifact artifact;
    DeploymentStatus status;
    string deployer;
    string approver;
    string error;
    string timestamp;
    optional<Artifact> previousArtifact;
};

class RepositoryGovernanceEngine {
private:
    vector<Environment> order = {
        Environment::Development,
        Environment::QA,
        Environment::Staging,
        Environment::Production
    };

    map<Environment, EnvironmentPolicy> policies;
    map<Environment, Artifact> activeArtifacts;
    map<string, set<string>> completedChecks;
    vector<DeploymentRecord> history;
    int nextId = 1;

    static string timestamp() {
        auto now = chrono::system_clock::now();
        time_t value = chrono::system_clock::to_time_t(now);
        tm utc = *gmtime(&value);

        ostringstream output;
        output << put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
        return output.str();
    }

    int position(Environment environment) const {
        auto it = find(order.begin(), order.end(), environment);

        if (it == order.end()) {
            throw invalid_argument("Unknown environment.");
        }

        return static_cast<int>(distance(order.begin(), it));
    }

    void validatePromotion(
        Environment environment,
        const Artifact& artifact,
        const string& deployer,
        const string& approver
    ) const {
        auto policyIt = policies.find(environment);

        if (policyIt == policies.end()) {
            throw invalid_argument("Environment policy not found.");
        }

        const auto& policy = policyIt->second;

        if (!policy.authorizedDeployers.count(deployer)) {
            throw runtime_error("Unauthorized deployment actor.");
        }

        if (policy.approvalRequired) {
            if (approver.empty()) {
                throw runtime_error("Required approval is missing.");
            }

            if (approver == deployer) {
                throw runtime_error("Self-approval is prohibited.");
            }
        }

        int currentPosition = position(environment);

        if (currentPosition > 0) {
            Environment previousEnvironment =
                order[currentPosition - 1];

            auto previous = activeArtifacts.find(previousEnvironment);

            if (previous == activeArtifacts.end()) {
                throw runtime_error(
                    "Previous environment has no successful deployment."
                );
            }

            if (previous->second.identity() != artifact.identity()) {
                throw runtime_error(
                    "Artifact identity mismatch during promotion."
                );
            }
        }

        auto checks = completedChecks.find(artifact.identity());

        if (checks == completedChecks.end()) {
            throw runtime_error("Artifact has no recorded checks.");
        }

        for (const auto& required : policy.requiredChecks) {
            if (!checks->second.count(required)) {
                throw runtime_error("Missing check: " + required);
            }
        }
    }

public:
    void addPolicy(const EnvironmentPolicy& policy) {
        policy.validate();

        if (policies.count(policy.environment)) {
            throw invalid_argument("Duplicate environment policy.");
        }

        policies.emplace(policy.environment, policy);
    }

    void registerChecks(
        const Artifact& artifact,
        const set<string>& checks
    ) {
        artifact.validate();
        completedChecks[artifact.identity()] = checks;
    }

    DeploymentRecord deploy(
        Environment environment,
        const Artifact& artifact,
        const string& deployer,
        const string& approver = "",
        bool simulateFailure = false
    ) {
        artifact.validate();

        if (deployer.empty()) {
            throw invalid_argument("Deployment actor is required.");
        }

        validatePromotion(environment, artifact, deployer, approver);

        optional<Artifact> previous;

        auto active = activeArtifacts.find(environment);

        if (active != activeArtifacts.end()) {
            previous = active->second;
        }

        DeploymentRecord record{
            nextId++,
            environment,
            artifact,
            DeploymentStatus::Pending,
            deployer,
            approver,
            "",
            timestamp(),
            previous
        };

        history.push_back(record);
        DeploymentRecord& stored = history.back();

        try {
            if (simulateFailure) {
                throw runtime_error("Readiness verification failed.");
            }

            // Update active state only after deployment verification.
            activeArtifacts[environment] = artifact;
            stored.status = DeploymentStatus::Succeeded;

        } catch (const exception& error) {
            stored.status = DeploymentStatus::Failed;
            stored.error = error.what();
        }

        return stored;
    }

    DeploymentRecord rollback(
        Environment environment,
        const string& deployer
    ) {
        auto policy = policies.find(environment);

        if (policy == policies.end() ||
            !policy->second.authorizedDeployers.count(deployer)) {
            throw runtime_error("Unauthorized rollback.");
        }

        auto active = activeArtifacts.find(environment);

        if (active == activeArtifacts.end()) {
            throw runtime_error("No active deployment to roll back.");
        }

        Artifact current = active->second;
        optional<Artifact> previous;

        for (auto it = history.rbegin(); it != history.rend(); ++it) {
            if (
                it->environment == environment &&
                it->status == DeploymentStatus::Succeeded &&
                it->artifact.identity() != current.identity()
            ) {
                previous = it->artifact;
                break;
            }
        }

        if (!previous) {
            throw runtime_error("No previous successful version exists.");
        }

        DeploymentRecord record{
            nextId++,
            environment,
            *previous,
            DeploymentStatus::Succeeded,
            deployer,
            "",
            "",
            timestamp(),
            current
        };

        activeArtifacts[environment] = *previous;

        for (auto it = history.rbegin(); it != history.rend(); ++it) {
            if (
                it->environment == environment &&
                it->artifact.identity() == current.identity() &&
                it->status == DeploymentStatus::Succeeded
            ) {
                it->status = DeploymentStatus::RolledBack;
                break;
            }
        }

        history.push_back(record);
        return record;
    }

    bool isEligible(
        Environment environment,
        const Artifact& artifact,
        const string& deployer,
        const string& approver,
        string& reason
    ) const {
        try {
            artifact.validate();
            validatePromotion(
                environment,
                artifact,
                deployer,
                approver
            );

            reason = "All deployment policies satisfied.";
            return true;

        } catch (const exception& error) {
            reason = error.what();
            return false;
        }
    }

    void printReport() const {
        cout << "\nDEPLOYMENT ENVIRONMENT REPORT\n";
        cout << "=============================\n";

        for (const auto& environment : order) {
            cout << left << setw(15) << toString(environment);

            auto it = activeArtifacts.find(environment);

            if (it == activeArtifacts.end()) {
                cout << "Not deployed\n";
            } else {
                cout << it->second.identity() << '\n';
            }
        }

        cout << "\nDEPLOYMENT HISTORY\n";

        for (const auto& record : history) {
            cout
                << "#" << record.id
                << " | " << toString(record.environment)
                << " | " << record.artifact.identity()
                << " | " << toString(record.status);

            if (!record.error.empty()) {
                cout << " | " << record.error;
            }

            cout << '\n';
        }
    }
};

int main() {
    try {
        RepositoryGovernanceEngine engine;

        const set<string> deployers = {
            "developer",
            "qa-bot",
            "release-bot",
            "operator"
        };

        engine.addPolicy({
            Environment::Development,
            1,
            false,
            {"build", "unit_tests"},
            deployers,
            MergeStrategy::Rolling
        });

        engine.addPolicy({
            Environment::QA,
            2,
            false,
            {"build", "unit_tests", "integration_tests", "security_scan"},
            deployers,
            MergeStrategy::Rolling
        });

        engine.addPolicy({
            Environment::Staging,
            3,
            true,
            {
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests"
            },
            deployers,
            MergeStrategy::BlueGreen
        });

        engine.addPolicy({
            Environment::Production,
            5,
            true,
            {
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests",
                "acceptance_tests"
            },
            deployers,
            MergeStrategy::Canary
        });

        Artifact release{
            "customer-api",
            "1.0.0",
            string(64, 'a'),
            string(40, 'b')
        };

        engine.registerChecks(
            release,
            {
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests",
                "acceptance_tests"
            }
        );

        vector<Environment> environments = {
            Environment::Development,
            Environment::QA,
            Environment::Staging,
            Environment::Production
        };

        for (Environment environment : environments) {
            string approver =
                environment == Environment::Staging ||
                environment == Environment::Production
                    ? "release-manager"
                    : "";

            auto result = engine.deploy(
                environment,
                release,
                "release-bot",
                approver
            );

            if (result.status != DeploymentStatus::Succeeded) {
                throw runtime_error("Environment promotion failed.");
            }
        }

        // A new artifact fails readiness checks and is not activated.
        Artifact nextRelease{
            "customer-api",
            "1.1.0",
            string(64, 'c'),
            string(40, 'd')
        };

        engine.registerChecks(
            nextRelease,
            {
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests",
                "acceptance_tests"
            }
        );

        auto failed = engine.deploy(
            Environment::Development,
            nextRelease,
            "developer",
            "",
            true
        );

        cout << "\nSimulated deployment failure: "
             << toString(failed.status) << '\n';

        // Missing production approval is rejected before execution.
        string reason;

        bool eligible = engine.isEligible(
            Environment::Production,
            release,
            "release-bot",
            "",
            reason
        );

        cout << "Production eligible without approval: "
             << boolalpha << eligible << '\n';

        cout << "Policy result: " << reason << '\n';

        engine.rollback(
            Environment::Development,
            "operator"
        );

        engine.printReport();

        return 0;

    } catch (const exception& error) {
        cerr << "Deployment engine error: "
             << error.what() << '\n';

        return 1;
    }
}

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class ReleaseState {
    Created,
    Deploying,
    Active,
    Failed,
    RollingBack,
    RolledBack,
    Recovered
};

enum class Strategy {
    Immediate,
    BlueGreen,
    Canary,
    Progressive
};

string stateName(ReleaseState state) {
    switch (state) {
        case ReleaseState::Created: return "CREATED";
        case ReleaseState::Deploying: return "DEPLOYING";
        case ReleaseState::Active: return "ACTIVE";
        case ReleaseState::Failed: return "FAILED";
        case ReleaseState::RollingBack: return "ROLLING_BACK";
        case ReleaseState::RolledBack: return "ROLLED_BACK";
        case ReleaseState::Recovered: return "RECOVERED";
    }
    return "UNKNOWN";
}

struct HealthMetrics {
    double errorRate;
    double latencyMs;
    double availability;
    int failedChecks;
};

struct RollbackPolicy {
    double maxErrorRate = 0.05;
    double maxLatencyMs = 500.0;
    double minAvailability = 0.99;
    int maxFailedChecks = 2;
};

struct Release {
    int id;
    string version;
    string artifactDigest;
};

struct Deployment {
    Release release;
    ReleaseState state = ReleaseState::Created;
    int traffic = 0;
    vector<HealthMetrics> observations;
    string failureReason;
};

struct Decision {
    bool eligible;
    vector<string> failures;
};

class GovernanceEngine {
private:
    RollbackPolicy policy;
    map<int, Deployment> deployments;
    optional<int> activeRelease;
    optional<int> previousRelease;
    int nextId = 1;

    void validateMetrics(const HealthMetrics& metrics) const {
        if (!isfinite(metrics.errorRate) ||
            metrics.errorRate < 0 || metrics.errorRate > 1) {
            throw invalid_argument("Invalid error rate");
        }

        if (!isfinite(metrics.latencyMs) || metrics.latencyMs < 0) {
            throw invalid_argument("Invalid latency");
        }

        if (!isfinite(metrics.availability) ||
            metrics.availability < 0 || metrics.availability > 1) {
            throw invalid_argument("Invalid availability");
        }

        if (metrics.failedChecks < 0) {
            throw invalid_argument("Invalid failed check count");
        }
    }

    void setTraffic(int id, int percentage) {
        if (percentage < 0 || percentage > 100) {
            throw invalid_argument("Traffic must be 0-100");
        }

        deployments.at(id).traffic = percentage;

        cout << "Traffic routing: release "
             << id << " -> " << percentage << "%\n";
    }

    void recordMetrics(int id, const HealthMetrics& metrics) {
        validateMetrics(metrics);
        deployments.at(id).observations.push_back(metrics);
    }

    void validateObservation(
        int id,
        const HealthMetrics& metrics
    ) {
        recordMetrics(id, metrics);
        Decision decision = evaluate(metrics);

        if (!decision.eligible) {
            string message = "Health gate failed: ";

            for (const auto& failure : decision.failures) {
                message += failure + " ";
            }

            throw runtime_error(message);
        }
    }

public:
    explicit GovernanceEngine(RollbackPolicy p) : policy(p) {
        if (p.maxErrorRate < 0 || p.maxErrorRate > 1 ||
            p.maxLatencyMs <= 0 ||
            p.minAvailability <= 0 ||
            p.minAvailability > 1 ||
            p.maxFailedChecks < 0) {
            throw invalid_argument("Invalid rollback policy");
        }
    }

    int registerRelease(
        const string& version,
        const string& digest
    ) {
        if (version.empty()) {
            throw invalid_argument("Version cannot be empty");
        }

        if (digest.size() != 71 ||
            digest.substr(0, 7) != "sha256:") {
            throw invalid_argument("Invalid artifact digest");
        }

        if (!all_of(digest.begin() + 7, digest.end(),
            [](unsigned char c) {
                return isxdigit(c);
            })) {
            throw invalid_argument("Invalid digest characters");
        }

        int id = nextId++;

        Release release{id, version, digest};

        deployments.emplace(
            id,
            Deployment{release}
        );

        cout << "Registered release " << version
             << " [ID=" << id << "]\n";

        return id;
    }

    Decision evaluate(const HealthMetrics& m) const {
        validateMetrics(m);

        Decision result{true, {}};

        if (m.errorRate > policy.maxErrorRate) {
            result.failures.push_back("ERROR_RATE");
        }

        if (m.latencyMs > policy.maxLatencyMs) {
            result.failures.push_back("LATENCY");
        }

        if (m.availability < policy.minAvailability) {
            result.failures.push_back("AVAILABILITY");
        }

        if (m.failedChecks > policy.maxFailedChecks) {
            result.failures.push_back("FAILED_CHECKS");
        }

        result.eligible = result.failures.empty();
        return result;
    }

    void deploy(
        int id,
        Strategy strategy,
        const vector<HealthMetrics>& windows
    ) {
        auto& deployment = deployments.at(id);

        if (deployment.state != ReleaseState::Created &&
            deployment.state != ReleaseState::RolledBack) {
            throw runtime_error("Invalid deployment transition");
        }

        vector<int> stages;

        switch (strategy) {
            case Strategy::Immediate:
                stages = {100};
                break;
            case Strategy::BlueGreen:
                stages = {100};
                break;
            case Strategy::Canary:
                stages = {5, 25, 50, 100};
                break;
            case Strategy::Progressive:
                stages = {10, 30, 60, 100};
                break;
        }

        if (windows.size() < stages.size()) {
            throw runtime_error("Insufficient health windows");
        }

        deployment.state = ReleaseState::Deploying;

        cout << "\nStarting deployment: "
             << deployment.release.version << "\n";

        try {
            if (strategy == Strategy::BlueGreen) {
                // Inactive environment is tested before traffic switching.
                for (const auto& metrics : windows) {
                    validateObservation(id, metrics);
                }

                setTraffic(id, 100);

            } else {
                for (size_t i = 0; i < stages.size(); ++i) {
                    setTraffic(id, stages[i]);
                    validateObservation(id, windows[i]);
                }
            }

            if (activeRelease && *activeRelease != id) {
                previousRelease = activeRelease;
            }

            activeRelease = id;
            deployment.state = ReleaseState::Active;

            cout << "Release activated successfully\n";

        } catch (const exception& e) {
            deployment.state = ReleaseState::Failed;
            deployment.failureReason = e.what();

            cout << "Deployment failure: " << e.what() << "\n";

            if (previousRelease) {
                rollback(id, *previousRelease);
            }

            throw;
        }
    }

    void rollback(int failedId, int targetId) {
        auto& failed = deployments.at(failedId);
        auto& target = deployments.at(targetId);

        if (target.state != ReleaseState::Active &&
            target.state != ReleaseState::Recovered &&
            target.state != ReleaseState::RolledBack) {
            throw runtime_error("Target release is not validated");
        }

        failed.state = ReleaseState::RollingBack;

        cout << "\nRollback initiated\n";

        // Stop traffic to the failed deployment before restoration.
        setTraffic(failedId, 0);
        setTraffic(targetId, 100);

        activeRelease = targetId;
        failed.state = ReleaseState::RolledBack;

        cout << "Restored version: "
             << target.release.version << "\n";
    }

    int recoverForward(
        int failedId,
        const string& version,
        const string& digest,
        const vector<HealthMetrics>& windows
    ) {
        auto& failed = deployments.at(failedId);

        if (failed.state != ReleaseState::Failed &&
            failed.state != ReleaseState::RolledBack) {
            throw runtime_error("Invalid forward recovery state");
        }

        int newId = registerRelease(version, digest);

        try {
            deploy(newId, Strategy::Canary, windows);
            deployments.at(newId).state = ReleaseState::Recovered;

            cout << "Forward recovery completed\n";
            return newId;

        } catch (...) {
            cout << "Forward recovery failed\n";
            throw;
        }
    }

    void report() const {
        cout << "\nRELEASE GOVERNANCE REPORT\n";
        cout << left << setw(12) << "VERSION"
             << setw(18) << "STATE"
             << setw(12) << "TRAFFIC"
             << "OBSERVATIONS\n";

        for (const auto& [id, d] : deployments) {
            cout << left << setw(12) << d.release.version
                 << setw(18) << stateName(d.state)
                 << setw(12) << to_string(d.traffic) + "%"
                 << d.observations.size() << "\n";
        }

        if (activeRelease) {
            cout << "Active release ID: " << *activeRelease << "\n";
        }
    }

    optional<int> getActiveRelease() const {
        return activeRelease;
    }

    ReleaseState getState(int id) const {
        return deployments.at(id).state;
    }
};

int main() {
    try {
        RollbackPolicy policy;
        GovernanceEngine engine(policy);

        vector<HealthMetrics> healthy = {
            {0.01, 120, 0.999, 0},
            {0.02, 150, 0.998, 0},
            {0.015, 140, 0.999, 0},
            {0.01, 130, 0.999, 0}
        };

        int v1 = engine.registerRelease(
            "1.0.0",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        );

        engine.deploy(v1, Strategy::Immediate, {
            healthy[0], healthy[1]
        });

        int v2 = engine.registerRelease(
            "2.0.0",
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        );

        vector<HealthMetrics> degraded = {
            healthy[0],
            healthy[1],
            {0.25, 1200, 0.90, 5},
            healthy[3]
        };

        try {
            engine.deploy(v2, Strategy::Canary, degraded);
        } catch (const exception& e) {
            cout << "Automatic rollback handled failure: "
                 << e.what() << "\n";
        }

        if (engine.getActiveRelease() != v1) {
            throw runtime_error("Rollback verification failed");
        }

        int v3 = engine.recoverForward(
            v2,
            "2.0.1",
            "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            healthy
        );

        if (engine.getState(v3) != ReleaseState::Recovered) {
            throw runtime_error("Forward recovery verification failed");
        }

        engine.report();

    } catch (const exception& e) {
        cerr << "Fatal error: " << e.what() << "\n";
        return 1;
    }

    return 0;
}

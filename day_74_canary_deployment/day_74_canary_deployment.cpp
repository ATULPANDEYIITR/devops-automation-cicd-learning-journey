#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class DeploymentState {
    Created,
    Canary,
    Promoted,
    RolledBack,
    Failed
};

enum class CheckResult {
    Passed,
    Failed
};

struct Metrics {
    uint64_t requests;
    uint64_t errors;
    double p95LatencyMs;

    double errorRate() const {
        return requests == 0
            ? 1.0
            : static_cast<double>(errors) / requests;
    }

    void validate() const {
        if (errors > requests) {
            throw invalid_argument("Errors exceed request count.");
        }

        if (!isfinite(p95LatencyMs) || p95LatencyMs < 0) {
            throw invalid_argument("Invalid latency measurement.");
        }
    }
};

struct Policy {
    vector<int> trafficStages{5, 10, 25, 50, 100};
    double maximumErrorRate = 0.02;
    double maximumLatencyMs = 500.0;
    double maximumRegression = 0.015;
    uint64_t minimumRequests = 100;

    void validate() const {
        if (trafficStages.empty() || trafficStages.back() != 100) {
            throw invalid_argument("Traffic stages must end at 100.");
        }

        if (!is_sorted(
                trafficStages.begin(),
                trafficStages.end()) ||
            adjacent_find(
                trafficStages.begin(),
                trafficStages.end()) != trafficStages.end()) {
            throw invalid_argument("Stages must be strictly increasing.");
        }

        for (int stage : trafficStages) {
            if (stage < 1 || stage > 100) {
                throw invalid_argument("Invalid traffic percentage.");
            }
        }

        if (maximumErrorRate <= 0 ||
            maximumErrorRate >= 1 ||
            maximumLatencyMs <= 0 ||
            maximumRegression < 0 ||
            minimumRequests == 0) {
            throw invalid_argument("Invalid deployment policy.");
        }
    }
};

struct ReviewEvent {
    string event;
    string details;
    size_t revision;
};

struct Deployment {
    string id;
    string version;
    string previousVersion;
    DeploymentState state = DeploymentState::Created;
    int trafficPercent = 0;
    size_t stageIndex = 0;
    vector<ReviewEvent> history;
    size_t revision = 0;

    void record(const string& event, const string& details) {
        history.push_back({
            event,
            details,
            ++revision
        });
    }
};

class TrafficRouter {
private:
    string activeVersion;

    static uint64_t stableHash(const string& value) {
        // FNV-1a provides deterministic routing across executions.
        uint64_t hash = 14695981039346656037ULL;

        for (unsigned char c : value) {
            hash ^= c;
            hash *= 1099511628211ULL;
        }

        return hash;
    }

public:
    explicit TrafficRouter(string initialVersion)
        : activeVersion(move(initialVersion)) {}

    string route(
        const string& requestKey,
        const Deployment& deployment
    ) const {
        if (requestKey.empty()) {
            throw invalid_argument("Request key cannot be empty.");
        }

        if (deployment.state != DeploymentState::Canary) {
            return activeVersion;
        }

        int bucket = static_cast<int>(stableHash(requestKey) % 100);

        return bucket < deployment.trafficPercent
            ? deployment.version
            : activeVersion;
    }

    void promote(const Deployment& deployment) {
        if (deployment.state != DeploymentState::Promoted) {
            throw logic_error("Cannot promote inactive deployment.");
        }

        activeVersion = deployment.version;
    }

    void restore(const Deployment& deployment) {
        if (deployment.state != DeploymentState::RolledBack) {
            throw logic_error("Deployment is not rolled back.");
        }

        activeVersion = deployment.previousVersion;
    }

    const string& currentVersion() const {
        return activeVersion;
    }
};

class GovernanceEngine {
private:
    Policy policy;
    TrafficRouter router;
    Metrics baseline;
    map<string, Deployment> deployments;

    Deployment& findDeployment(const string& id) {
        auto iterator = deployments.find(id);

        if (iterator == deployments.end()) {
            throw out_of_range("Unknown deployment ID.");
        }

        return iterator->second;
    }

    vector<string> evaluate(const Metrics& metrics) const {
        vector<string> failures;

        metrics.validate();

        if (metrics.requests < policy.minimumRequests) {
            failures.push_back("insufficient_requests");
        }

        if (metrics.errorRate() > policy.maximumErrorRate) {
            failures.push_back("error_rate");
        }

        if (metrics.p95LatencyMs > policy.maximumLatencyMs) {
            failures.push_back("latency");
        }

        if (metrics.errorRate() - baseline.errorRate() >
            policy.maximumRegression) {
            failures.push_back("baseline_regression");
        }

        return failures;
    }

    void rollbackInternal(
        Deployment& deployment,
        const string& reason
    ) {
        deployment.state = DeploymentState::RolledBack;
        deployment.trafficPercent = 0;

        deployment.record("rollback", reason);
        router.restore(deployment);
    }

public:
    GovernanceEngine(
        Policy configuredPolicy,
        Metrics referenceMetrics,
        string initialVersion
    )
        : policy(move(configuredPolicy)),
          router(move(initialVersion)),
          baseline(referenceMetrics) {

        policy.validate();
        baseline.validate();

        if (baseline.requests < policy.minimumRequests) {
            throw invalid_argument("Baseline sample is insufficient.");
        }
    }

    void registerDeployment(
        const string& id,
        const string& version
    ) {
        if (id.empty() || version.empty()) {
            throw invalid_argument("Deployment identity is required.");
        }

        if (deployments.count(id)) {
            throw invalid_argument("Duplicate deployment ID.");
        }

        Deployment deployment;
        deployment.id = id;
        deployment.version = version;
        deployment.previousVersion = router.currentVersion();
        deployment.record("registered", version);

        deployments.emplace(id, move(deployment));
    }

    void start(const string& id) {
        Deployment& deployment = findDeployment(id);

        if (deployment.state != DeploymentState::Created) {
            throw logic_error("Invalid deployment transition.");
        }

        deployment.state = DeploymentState::Canary;
        deployment.stageIndex = 0;
        deployment.trafficPercent = policy.trafficStages[0];

        deployment.record(
            "started",
            to_string(deployment.trafficPercent) + "%"
        );
    }

    CheckResult processObservation(
        const string& id,
        const Metrics& metrics
    ) {
        Deployment& deployment = findDeployment(id);

        if (deployment.state != DeploymentState::Canary) {
            throw logic_error("Deployment is not active.");
        }

        vector<string> failures = evaluate(metrics);

        if (!failures.empty()) {
            string reason;

            for (const auto& failure : failures) {
                if (!reason.empty()) reason += ",";
                reason += failure;
            }

            rollbackInternal(deployment, reason);
            return CheckResult::Failed;
        }

        deployment.record(
            "health_passed",
            "error_rate=" + to_string(metrics.errorRate())
        );

        ++deployment.stageIndex;

        if (deployment.stageIndex >= policy.trafficStages.size()) {
            deployment.state = DeploymentState::Promoted;
            deployment.trafficPercent = 100;

            deployment.record("promoted", deployment.version);
            router.promote(deployment);
        } else {
            deployment.trafficPercent =
                policy.trafficStages[deployment.stageIndex];

            deployment.record(
                "traffic_increased",
                to_string(deployment.trafficPercent) + "%"
            );
        }

        return CheckResult::Passed;
    }

    void rollback(const string& id, const string& reason) {
        Deployment& deployment = findDeployment(id);

        if (deployment.state != DeploymentState::Canary) {
            throw logic_error("Only active canaries can roll back.");
        }

        rollbackInternal(deployment, reason);
    }

    string route(
        const string& requestKey,
        const string& deploymentId
    ) {
        return router.route(
            requestKey,
            findDeployment(deploymentId)
        );
    }

    void report() const {
        cout << "\nActive version: "
             << router.currentVersion() << "\n\n";

        for (const auto& [id, deployment] : deployments) {
            cout << "Deployment: " << id << "\n"
                 << "Version: " << deployment.version << "\n"
                 << "State: " << static_cast<int>(deployment.state) << "\n"
                 << "Traffic: " << deployment.trafficPercent << "%\n"
                 << "Events:\n";

            for (const auto& event : deployment.history) {
                cout << "  #" << event.revision
                     << " " << event.event
                     << " : " << event.details << "\n";
            }

            cout << "\n";
        }
    }

    const string& activeVersion() const {
        return router.currentVersion();
    }
};

void runTests() {
    Policy policy;
    policy.minimumRequests = 100;

    Metrics baseline{5000, 50, 180};

    GovernanceEngine engine(policy, baseline, "v1.0.0");

    engine.registerDeployment("release-001", "v2.0.0");
    engine.start("release-001");

    for (int i = 0; i < 5; ++i) {
        auto result = engine.processObservation(
            "release-001",
            Metrics{1000, 12, 200}
        );

        if (result != CheckResult::Passed) {
            throw runtime_error("Unexpected canary failure.");
        }
    }

    if (engine.activeVersion() != "v2.0.0") {
        throw runtime_error("Promotion test failed.");
    }

    engine.registerDeployment("release-002", "v3.0.0");
    engine.start("release-002");

    auto result = engine.processObservation(
        "release-002",
        Metrics{1000, 200, 900}
    );

    if (result != CheckResult::Failed ||
        engine.activeVersion() != "v2.0.0") {
        throw runtime_error("Rollback test failed.");
    }

    bool rejected = false;

    try {
        engine.processObservation(
            "release-002",
            Metrics{1000, 0, 100}
        );
    } catch (const logic_error&) {
        rejected = true;
    }

    if (!rejected) {
        throw runtime_error("Invalid transition was accepted.");
    }

    cout << "All C++17 tests passed.\n";
}

int main() {
    try {
        runTests();

        Policy policy;
        Metrics baseline{10000, 100, 190};

        GovernanceEngine engine(policy, baseline, "v1.0.0");

        engine.registerDeployment(
            "production-2026-11",
            "v2.1.0"
        );

        engine.start("production-2026-11");

        vector<Metrics> observations = {
            {1000, 12, 210},
            {1000, 14, 220},
            {1000, 13, 225},
            {1000, 11, 230},
            {1000, 15, 240}
        };

        for (const auto& metrics : observations) {
            auto result = engine.processObservation(
                "production-2026-11",
                metrics
            );

            if (result == CheckResult::Failed) {
                break;
            }

            cout << "Health passed. Active version: "
                 << engine.activeVersion() << "\n";
        }

        cout << "\nTraffic routing:\n";

        for (const string& client : {
            "customer-001",
            "customer-002",
            "customer-003"
        }) {
            cout << client << " -> "
                 << engine.route(
                     client,
                     "production-2026-11"
                 ) << "\n";
        }

        engine.report();

    } catch (const exception& error) {
        cerr << "Governance engine failure: "
             << error.what() << "\n";

        return 1;
    }

    return 0;
}

/*
 * Deployment Governance and Merge Engine
 *
 * C++17
 *
 * Models:
 * - Recreate deployments
 * - Rolling deployments
 * - Blue-green deployments
 * - Infrastructure capacity
 * - Health checks
 * - Traffic allocation
 * - Deployment eligibility
 * - Rollback
 *
 * Standard library only.
 */

#include <algorithm>
#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

enum class Strategy {
    Recreate,
    Rolling,
    BlueGreen
};

enum class InstanceState {
    Healthy,
    Unhealthy,
    Stopped
};

enum class DeploymentState {
    Pending,
    Running,
    Succeeded,
    Failed,
    RolledBack
};

struct Instance {
    int id;
    std::string version;
    InstanceState state;
};

struct DeploymentPolicy {
    int maximumCapacity = 12;
    int maxSurge = 1;
    int maxUnavailable = 1;
    int batchSize = 1;
    double minimumHealthyRatio = 1.0;
    bool allowRecreate = true;
    bool allowBlueGreen = true;
};

struct DeploymentRequest {
    std::string application;
    std::string version;
    Strategy strategy;
    int desiredReplicas = 4;
};

struct DeploymentResult {
    int deploymentId;
    std::string version;
    DeploymentState state;
    std::string message;
};

class DeploymentException : public std::runtime_error {
public:
    explicit DeploymentException(const std::string& message)
        : std::runtime_error(message) {}
};

class DeploymentEngine {
private:
    std::vector<Instance> instances;

    DeploymentPolicy policy;

    std::string activeVersion;
    std::string previousVersion;

    std::map<std::string, int> traffic;

    int nextInstanceId = 1;
    int nextDeploymentId = 1;

    std::mt19937 randomEngine{42};

    double startupFailureRate = 0.0;
    double healthFailureRate = 0.0;

    std::vector<DeploymentResult> history;

    void validatePolicy() const {
        if (policy.maximumCapacity < 1) {
            throw DeploymentException("Invalid infrastructure capacity");
        }

        if (policy.maxSurge < 0 ||
            policy.maxUnavailable < 0) {
            throw DeploymentException("Invalid availability policy");
        }

        if (policy.maxSurge + policy.maxUnavailable < 1) {
            throw DeploymentException(
                "Rolling deployment cannot make progress"
            );
        }

        if (policy.minimumHealthyRatio < 0.0 ||
            policy.minimumHealthyRatio > 1.0) {
            throw DeploymentException("Invalid health threshold");
        }
    }

    void validateRequest(const DeploymentRequest& request) const {
        if (request.application.empty() ||
            request.version.empty()) {
            throw DeploymentException(
                "Application and version are required"
            );
        }

        if (request.desiredReplicas < 1) {
            throw DeploymentException(
                "Desired replica count must be positive"
            );
        }

        if (request.version == activeVersion) {
            throw DeploymentException(
                "Requested version is already active"
            );
        }

        if (request.desiredReplicas > policy.maximumCapacity) {
            throw DeploymentException(
                "Desired replicas exceed maximum capacity"
            );
        }

        if (request.strategy == Strategy::Recreate &&
            !policy.allowRecreate) {
            throw DeploymentException(
                "Recreate strategy is prohibited"
            );
        }

        if (request.strategy == Strategy::BlueGreen &&
            !policy.allowBlueGreen) {
            throw DeploymentException(
                "Blue-green strategy is prohibited"
            );
        }

        if (request.strategy == Strategy::BlueGreen &&
            static_cast<int>(instances.size()) +
            request.desiredReplicas > policy.maximumCapacity) {
            throw DeploymentException(
                "Blue-green capacity requirement not satisfied"
            );
        }
    }

    bool failureOccurs(double probability) {
        std::bernoulli_distribution distribution(probability);
        return distribution(randomEngine);
    }

    Instance createInstance(const std::string& version) {
        Instance instance{
            nextInstanceId++,
            version,
            InstanceState::Healthy
        };

        if (failureOccurs(startupFailureRate)) {
            instance.state = InstanceState::Unhealthy;
        }

        return instance;
    }

    bool checkHealth(const std::vector<Instance>& group) {
        if (group.empty()) {
            return false;
        }

        const int healthy = static_cast<int>(
            std::count_if(
                group.begin(),
                group.end(),
                [](const Instance& instance) {
                    return instance.state == InstanceState::Healthy;
                }
            )
        );

        const double ratio =
            static_cast<double>(healthy) / group.size();

        std::cout
            << "Health check: "
            << healthy << "/" << group.size()
            << " (" << std::fixed << std::setprecision(2)
            << ratio * 100 << "%)\n";

        return ratio >= policy.minimumHealthyRatio &&
            healthy == static_cast<int>(group.size());
    }

    void enforceCapacity(int required) const {
        if (required > policy.maximumCapacity) {
            throw DeploymentException(
                "Infrastructure capacity exceeded"
            );
        }
    }

    void recreate(const DeploymentRequest& request) {
        const auto original = instances;

        std::cout << "Stopping old environment\n";

        instances.clear();

        try {
            enforceCapacity(request.desiredReplicas);

            std::vector<Instance> replacement;

            for (int i = 0; i < request.desiredReplicas; ++i) {
                replacement.push_back(
                    createInstance(request.version)
                );
            }

            if (!checkHealth(replacement)) {
                throw DeploymentException(
                    "Recreate health validation failed"
                );
            }

            instances = replacement;

        } catch (...) {
            instances = original;
            throw;
        }
    }

    void rolling(const DeploymentRequest& request) {
        const auto original = instances;

        try {
            int position = 0;
            const int originalSize =
                static_cast<int>(original.size());

            while (position < originalSize) {
                const int count = std::min(
                    policy.batchSize,
                    originalSize - position
                );

                const int replaceCount = std::min(
                    count,
                    policy.maxSurge + policy.maxUnavailable
                );

                if (replaceCount < 1) {
                    throw DeploymentException(
                        "Rolling deployment cannot progress"
                    );
                }

                std::vector<int> ids;

                for (int i = 0; i < replaceCount; ++i) {
                    ids.push_back(original[position + i].id);
                }

                instances.erase(
                    std::remove_if(
                        instances.begin(),
                        instances.end(),
                        [&ids](const Instance& instance) {
                            return std::find(
                                ids.begin(),
                                ids.end(),
                                instance.id
                            ) != ids.end();
                        }
                    ),
                    instances.end()
                );

                std::vector<Instance> replacements;

                for (int i = 0; i < replaceCount; ++i) {
                    enforceCapacity(
                        static_cast<int>(instances.size()) + 1
                    );

                    replacements.push_back(
                        createInstance(request.version)
                    );

                    instances.push_back(replacements.back());
                }

                if (!checkHealth(replacements)) {
                    throw DeploymentException(
                        "Rolling batch health validation failed"
                    );
                }

                std::cout
                    << "Rolling batch completed at position "
                    << position << "\n";

                position += replaceCount;
            }

            if (static_cast<int>(instances.size()) !=
                request.desiredReplicas) {
                throw DeploymentException(
                    "Final replica count mismatch"
                );
            }

            if (!checkHealth(instances)) {
                throw DeploymentException(
                    "Final rolling health check failed"
                );
            }

        } catch (...) {
            instances = original;
            throw;
        }
    }

    void blueGreen(const DeploymentRequest& request) {
        const auto original = instances;

        enforceCapacity(
            static_cast<int>(instances.size()) +
            request.desiredReplicas
        );

        try {
            std::vector<Instance> green;

            std::cout << "Provisioning green environment\n";

            for (int i = 0; i < request.desiredReplicas; ++i) {
                green.push_back(createInstance(request.version));
            }

            if (!checkHealth(green)) {
                throw DeploymentException(
                    "Green environment validation failed"
                );
            }

            // Traffic is switched only after green validation.
            traffic.clear();
            traffic[request.version] = 100;

            instances = green;

            std::cout << "Traffic switched to green environment\n";

        } catch (...) {
            instances = original;
            throw;
        }
    }

    void updateVersion(const std::string& version) {
        previousVersion = activeVersion;
        activeVersion = version;

        traffic.clear();
        traffic[activeVersion] = 100;
    }

public:
    explicit DeploymentEngine(
        std::string initialVersion,
        DeploymentPolicy configuration = {}
    )
        : policy(configuration),
          activeVersion(std::move(initialVersion)) {

        validatePolicy();

        if (activeVersion.empty()) {
            throw DeploymentException(
                "Initial version cannot be empty"
            );
        }

        for (int i = 0; i < 4; ++i) {
            instances.push_back({
                nextInstanceId++,
                activeVersion,
                InstanceState::Healthy
            });
        }

        enforceCapacity(static_cast<int>(instances.size()));

        traffic[activeVersion] = 100;
    }

    void configureFailureRates(
        double startup,
        double health
    ) {
        if (startup < 0 || startup > 1 ||
            health < 0 || health > 1) {
            throw DeploymentException(
                "Failure probabilities must be between 0 and 1"
            );
        }

        startupFailureRate = startup;
        healthFailureRate = health;
    }

    void injectHealthFailure(std::vector<Instance>& group) {
        if (!group.empty() && failureOccurs(healthFailureRate)) {
            group.front().state = InstanceState::Unhealthy;
        }
    }

    DeploymentResult deploy(const DeploymentRequest& request) {
        validateRequest(request);

        DeploymentResult result{
            nextDeploymentId++,
            request.version,
            DeploymentState::Running,
            "Deployment in progress"
        };

        history.push_back(result);

        const auto originalInstances = instances;
        const auto originalTraffic = traffic;
        const std::string originalVersion = activeVersion;
        const std::string originalPrevious = previousVersion;

        try {
            std::cout
                << "\nDeployment " << result.deploymentId
                << " started: " << request.version << "\n";

            switch (request.strategy) {
                case Strategy::Recreate:
                    recreate(request);
                    break;

                case Strategy::Rolling:
                    rolling(request);
                    break;

                case Strategy::BlueGreen:
                    blueGreen(request);
                    break;
            }

            updateVersion(request.version);

            result.state = DeploymentState::Succeeded;
            result.message = "Deployment completed successfully";

        } catch (const std::exception& error) {
            instances = originalInstances;
            traffic = originalTraffic;
            activeVersion = originalVersion;
            previousVersion = originalPrevious;

            result.state = DeploymentState::Failed;
            result.message = error.what();

            std::cerr
                << "Deployment failed: "
                << error.what() << "\n";
        }

        history.back() = result;

        return result;
    }

    void rollback() {
        if (previousVersion.empty()) {
            throw DeploymentException(
                "No previous version available"
            );
        }

        const std::string target = previousVersion;

        std::vector<Instance> replacement;

        for (int i = 0; i < 4; ++i) {
            replacement.push_back(createInstance(target));
        }

        if (!checkHealth(replacement)) {
            throw DeploymentException(
                "Rollback environment failed health validation"
            );
        }

        previousVersion = activeVersion;
        activeVersion = target;
        instances = replacement;

        traffic.clear();
        traffic[target] = 100;

        std::cout << "Rollback completed: " << target << "\n";
    }

    void printReport() const {
        std::cout << "\n========== DEPLOYMENT REPORT ==========\n";

        std::cout << "Active version: " << activeVersion << "\n";
        std::cout << "Previous version: " << previousVersion << "\n";
        std::cout << "Instance count: " << instances.size() << "\n";

        std::cout << "\nTraffic distribution:\n";

        for (const auto& [version, weight] : traffic) {
            std::cout << version << ": " << weight << "%\n";
        }

        std::cout << "\nInstances:\n";

        for (const auto& instance : instances) {
            std::cout
                << instance.id << " | "
                << instance.version << " | "
                << (
                    instance.state == InstanceState::Healthy
                    ? "HEALTHY"
                    : "UNHEALTHY"
                )
                << "\n";
        }

        std::cout << "\nDeployment history:\n";

        for (const auto& record : history) {
            std::cout
                << record.deploymentId << " | "
                << record.version << " | "
                << (
                    record.state == DeploymentState::Succeeded
                    ? "SUCCEEDED"
                    : "FAILED"
                )
                << " | "
                << record.message << "\n";
        }
    }

    const std::string& getActiveVersion() const {
        return activeVersion;
    }

    std::size_t instanceCount() const {
        return instances.size();
    }
};

int main() {
    try {
        DeploymentPolicy policy;

        policy.maximumCapacity = 12;
        policy.maxSurge = 1;
        policy.maxUnavailable = 1;
        policy.batchSize = 1;
        policy.minimumHealthyRatio = 1.0;

        DeploymentEngine engine("1.0.0", policy);

        DeploymentRequest rollingRequest{
            "inventory-service",
            "1.1.0",
            Strategy::Rolling,
            4
        };

        DeploymentResult rollingResult =
            engine.deploy(rollingRequest);

        if (rollingResult.state != DeploymentState::Succeeded) {
            std::cerr << rollingResult.message << "\n";
        }

        DeploymentRequest blueGreenRequest{
            "inventory-service",
            "1.2.0",
            Strategy::BlueGreen,
            4
        };

        engine.deploy(blueGreenRequest);

        DeploymentRequest recreateRequest{
            "inventory-service",
            "1.3.0",
            Strategy::Recreate,
            4
        };

        engine.deploy(recreateRequest);

        engine.printReport();

        if (engine.getActiveVersion() != "1.3.0") {
            throw DeploymentException(
                "Unexpected active deployment version"
            );
        }

        engine.rollback();

        engine.printReport();

        std::cout << "\nAll C++ deployment checks completed.\n";

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}

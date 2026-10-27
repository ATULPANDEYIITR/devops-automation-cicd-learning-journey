#include <algorithm>
#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

enum class HealthStatus {
    Starting,
    Healthy,
    Unhealthy
};

enum class ContainerState {
    Created,
    Running,
    Stopped,
    Restarting
};

enum class RestartPolicy {
    No,
    OnFailure,
    Always,
    UnlessStopped
};

struct ResourceLimits {
    int cpuMillicores;
    int memoryMb;

    void validate() const {
        if (cpuMillicores <= 0) {
            throw std::invalid_argument("CPU limit must be positive");
        }
        if (memoryMb <= 0) {
            throw std::invalid_argument("Memory limit must be positive");
        }
    }
};

struct HealthCheckConfig {
    int intervalSeconds;
    int timeoutSeconds;
    int retries;
    int startPeriodSeconds;

    void validate() const {
        if (intervalSeconds <= 0 || timeoutSeconds <= 0) {
            throw std::invalid_argument(
                "Health-check timing must be positive"
            );
        }

        if (timeoutSeconds > intervalSeconds) {
            throw std::invalid_argument(
                "Health-check timeout cannot exceed interval"
            );
        }

        if (retries < 1) {
            throw std::invalid_argument(
                "Health-check retries must be at least one"
            );
        }

        if (startPeriodSeconds < 0) {
            throw std::invalid_argument(
                "Start period cannot be negative"
            );
        }
    }
};

struct HealthResult {
    bool success;
    double latencyMs;
    std::string message;
};

struct StatusCheck {
    std::string name;
    bool passed;
};

class Container {
private:
    std::string name_;
    std::string image_;
    ResourceLimits limits_;
    HealthCheckConfig healthCheck_;
    RestartPolicy restartPolicy_;
    ContainerState state_{ContainerState::Created};
    HealthStatus health_{HealthStatus::Starting};
    int failureCount_{0};
    int restartCount_{0};
    int maxRestarts_{5};
    bool manuallyStopped_{false};

public:
    Container(
        std::string name,
        std::string image,
        ResourceLimits limits,
        HealthCheckConfig healthCheck,
        RestartPolicy restartPolicy,
        int maxRestarts
    )
        : name_(std::move(name)),
          image_(std::move(image)),
          limits_(limits),
          healthCheck_(healthCheck),
          restartPolicy_(restartPolicy),
          maxRestarts_(maxRestarts) {

        if (name_.empty()) {
            throw std::invalid_argument("Container name is required");
        }

        if (image_.empty()) {
            throw std::invalid_argument("Container image is required");
        }

        if (maxRestarts < 0) {
            throw std::invalid_argument(
                "Maximum restart count cannot be negative"
            );
        }

        limits_.validate();
        healthCheck_.validate();
    }

    void start() {
        state_ = ContainerState::Running;
        health_ = HealthStatus::Starting;
        failureCount_ = 0;
        manuallyStopped_ = false;
    }

    void stop(bool manual = true) {
        state_ = ContainerState::Stopped;
        manuallyStopped_ = manual;
    }

    void applyHealthResult(
        const HealthResult& result,
        int elapsedSeconds
    ) {
        if (state_ != ContainerState::Running) {
            throw std::logic_error(
                "Cannot check a stopped container"
            );
        }

        if (elapsedSeconds < healthCheck_.startPeriodSeconds) {
            health_ = HealthStatus::Starting;
            failureCount_ = 0;
            return;
        }

        const bool passed =
            result.success &&
            result.latencyMs <= healthCheck_.timeoutSeconds * 1000.0;

        if (passed) {
            health_ = HealthStatus::Healthy;
            failureCount_ = 0;
            return;
        }

        ++failureCount_;

        if (failureCount_ >= healthCheck_.retries) {
            health_ = HealthStatus::Unhealthy;
        }
    }

    bool shouldRestart(int exitCode) const {
        if (manuallyStopped_ || restartCount_ >= maxRestarts_) {
            return false;
        }

        switch (restartPolicy_) {
            case RestartPolicy::No:
                return false;

            case RestartPolicy::Always:
                return true;

            case RestartPolicy::UnlessStopped:
                return true;

            case RestartPolicy::OnFailure:
                return exitCode != 0;
        }

        return false;
    }

    bool restart(int exitCode) {
        if (!shouldRestart(exitCode)) {
            return false;
        }

        state_ = ContainerState::Restarting;
        ++restartCount_;
        start();
        return true;
    }

    const std::string& name() const {
        return name_;
    }

    ContainerState state() const {
        return state_;
    }

    HealthStatus health() const {
        return health_;
    }

    int restartCount() const {
        return restartCount_;
    }

    const ResourceLimits& limits() const {
        return limits_;
    }
};

class GovernanceEngine {
private:
    std::map<std::string, Container> containers_;

public:
    void add(Container container) {
        const std::string name = container.name();

        if (containers_.contains(name)) {
            throw std::invalid_argument(
                "Duplicate container: " + name
            );
        }

        containers_.emplace(name, std::move(container));
    }

    Container& get(const std::string& name) {
        auto it = containers_.find(name);

        if (it == containers_.end()) {
            throw std::out_of_range(
                "Unknown container: " + name
            );
        }

        return it->second;
    }

    void startAll() {
        for (auto& [name, container] : containers_) {
            container.start();
        }
    }

    void evaluateHealth(
        const std::string& name,
        const HealthResult& result,
        int elapsedSeconds
    ) {
        Container& container = get(name);

        container.applyHealthResult(result, elapsedSeconds);

        if (container.health() == HealthStatus::Unhealthy) {
            // An unhealthy application is treated as a recoverable
            // service failure. The runtime still enforces the restart
            // policy and restart budget.
            container.restart(1);
        }
    }

    void printStatus() const {
        std::cout << "\nContainer governance status\n";
        std::cout << std::left
                  << std::setw(12) << "Container"
                  << std::setw(14) << "State"
                  << std::setw(14) << "Health"
                  << std::setw(10) << "Restarts"
                  << "Resources\n";

        for (const auto& [name, container] : containers_) {
            std::cout << std::left
                      << std::setw(12) << name
                      << std::setw(
                             14,
                             container.state() == ContainerState::Running
                                 ? "running"
                                 : "stopped"
                         )
                      << std::setw(
                             14,
                             container.health() == HealthStatus::Healthy
                                 ? "healthy"
                                 : container.health() ==
                                           HealthStatus::Unhealthy
                                       ? "unhealthy"
                                       : "starting"
                         )
                      << std::setw(10)
                      << container.restartCount()
                      << container.limits().cpuMillicores
                      << "m / "
                      << container.limits().memoryMb
                      << " MB\n";
        }
    }
};

int main() {
    try {
        GovernanceEngine engine;

        engine.add(Container(
            "api",
            "example/api:2.4",
            ResourceLimits{500, 512},
            HealthCheckConfig{5, 2, 3, 5},
            RestartPolicy::UnlessStopped,
            5
        ));

        engine.add(Container(
            "worker",
            "example/worker:4.1",
            ResourceLimits{750, 1024},
            HealthCheckConfig{10, 3, 2, 0},
            RestartPolicy::OnFailure,
            2
        ));

        engine.startAll();

        engine.evaluateHealth(
            "api",
            HealthResult{
                true,
                45.0,
                "HTTP 200 /health"
            },
            8
        );

        // Three failures are required before the worker becomes
        // unhealthy. The restart policy then controls recovery.
        for (int i = 0; i < 6; ++i) {
            engine.evaluateHealth(
                "worker",
                HealthResult{
                    false,
                    4000.0,
                    "database dependency unavailable"
                },
                20
            );
        }

        engine.printStatus();

        // Manual intervention has priority over automatic recovery.
        Container& api = engine.get("api");
        api.stop(true);

        if (!api.shouldRestart(1)) {
            std::cout
                << "\nManual stop prevents automatic restart.\n";
        }

        // Validation example.
        try {
            ResourceLimits invalid{0, 512};
            invalid.validate();
        } catch (const std::exception& ex) {
            std::cout
                << "Rejected resource configuration: "
                << ex.what() << '\n';
        }

        // A runtime resource limit is different from a health check:
        // limits constrain consumption; health checks observe behavior.
        std::cout
            << "\nGovernance evaluation completed successfully.\n";

        return 0;
    } catch (const std::exception& ex) {
        std::cerr
            << "Fatal configuration/runtime error: "
            << ex.what() << '\n';
        return 1;
    }
}

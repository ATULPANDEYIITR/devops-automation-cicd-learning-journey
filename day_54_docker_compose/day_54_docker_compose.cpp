#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class ServiceState {
    Created,
    Starting,
    Healthy,
    Unhealthy,
    Stopped,
    Failed
};

enum class DependencyCondition {
    Started,
    Healthy
};

enum class RestartPolicy {
    Never,
    OnFailure,
    Always,
    UnlessStopped
};

enum class MergeDecision {
    Allowed,
    BlockedByDependency,
    BlockedByHealth,
    BlockedByNetwork,
    BlockedByConfiguration
};

std::string toString(ServiceState state) {
    switch (state) {
        case ServiceState::Created: return "created";
        case ServiceState::Starting: return "starting";
        case ServiceState::Healthy: return "healthy";
        case ServiceState::Unhealthy: return "unhealthy";
        case ServiceState::Stopped: return "stopped";
        case ServiceState::Failed: return "failed";
    }
    return "unknown";
}

struct Network {
    std::string name;
    bool internal = false;
    std::string driver = "bridge";
};

struct Dependency {
    std::string service;
    DependencyCondition condition = DependencyCondition::Healthy;
};

struct Service {
    std::string name;
    std::string image;
    std::set<std::string> networks;
    std::vector<Dependency> dependencies;
    RestartPolicy restartPolicy = RestartPolicy::Never;
    ServiceState state = ServiceState::Created;
    bool healthcheckConfigured = false;
    bool healthProbeResult = true;
};

class ComposeEngine {
private:
    std::map<std::string, Network> networks_;
    std::map<std::string, Service> services_;

    static void requireName(const std::string& name, const std::string& type) {
        if (name.empty()) {
            throw std::invalid_argument(type + " name cannot be empty");
        }

        for (unsigned char c : name) {
            if (!(std::isalnum(c) || c == '_' || c == '.' || c == '-')) {
                throw std::invalid_argument("Invalid " + type + " name: " + name);
            }
        }
    }

public:
    void addNetwork(Network network) {
        requireName(network.name, "network");

        if (network.driver != "bridge" && network.driver != "overlay") {
            throw std::invalid_argument("Unsupported network driver");
        }

        if (!networks_.emplace(network.name, network).second) {
            throw std::invalid_argument("Duplicate network: " + network.name);
        }
    }

    void addService(Service service) {
        requireName(service.name, "service");

        if (service.image.empty() || service.networks.empty()) {
            throw std::invalid_argument(
                "Service requires an image and at least one network"
            );
        }

        if (!services_.emplace(service.name, service).second) {
            throw std::invalid_argument("Duplicate service: " + service.name);
        }
    }

    void validate() const {
        if (services_.empty()) {
            throw std::invalid_argument("Project has no services");
        }

        for (const auto& [name, service] : services_) {
            for (const auto& network : service.networks) {
                if (networks_.find(network) == networks_.end()) {
                    throw std::invalid_argument(
                        name + " references unknown network " + network
                    );
                }
            }

            for (const auto& dependency : service.dependencies) {
                auto found = services_.find(dependency.service);

                if (found == services_.end() || dependency.service == name) {
                    throw std::invalid_argument(
                        "Invalid dependency for " + name
                    );
                }

                if (
                    dependency.condition == DependencyCondition::Healthy &&
                    !found->second.healthcheckConfigured
                ) {
                    throw std::invalid_argument(
                        dependency.service + " requires a health check"
                    );
                }
            }
        }

        startupOrder();
    }

    std::vector<std::string> startupOrder() const {
        std::map<std::string, int> indegree;
        std::map<std::string, std::vector<std::string>> dependents;

        for (const auto& [name, service] : services_) {
            indegree[name] = 0;
            dependents[name] = {};
        }

        for (const auto& [name, service] : services_) {
            for (const auto& dependency : service.dependencies) {
                ++indegree[name];
                dependents[dependency.service].push_back(name);
            }
        }

        std::set<std::string> ready;

        for (const auto& [name, degree] : indegree) {
            if (degree == 0) ready.insert(name);
        }

        std::vector<std::string> order;

        while (!ready.empty()) {
            auto current = *ready.begin();
            ready.erase(ready.begin());
            order.push_back(current);

            for (const auto& dependent : dependents[current]) {
                if (--indegree[dependent] == 0) {
                    ready.insert(dependent);
                }
            }
        }

        if (order.size() != services_.size()) {
            throw std::invalid_argument("Circular dependency detected");
        }

        return order;
    }

    bool canCommunicate(
        const std::string& first,
        const std::string& second
    ) const {
        auto left = services_.find(first);
        auto right = services_.find(second);

        if (left == services_.end() || right == services_.end()) {
            return false;
        }

        for (const auto& network : left->second.networks) {
            if (right->second.networks.count(network)) {
                return true;
            }
        }

        return false;
    }

    void start() {
        validate();
        std::vector<std::string> started;

        try {
            for (const auto& name : startupOrder()) {
                Service& service = services_.at(name);

                for (const auto& dependency : service.dependencies) {
                    const Service& parent = services_.at(dependency.service);

                    if (
                        dependency.condition == DependencyCondition::Healthy &&
                        parent.state != ServiceState::Healthy
                    ) {
                        throw std::runtime_error(
                            name + " requires healthy " + parent.name
                        );
                    }

                    if (
                        dependency.condition == DependencyCondition::Started &&
                        parent.state == ServiceState::Created
                    ) {
                        throw std::runtime_error(
                            name + " requires started " + parent.name
                        );
                    }
                }

                service.state = ServiceState::Starting;
                started.push_back(name);
                std::cout << name << ": starting\n";

                if (!service.healthProbeResult) {
                    service.state = ServiceState::Unhealthy;
                    std::cout << name << ": unhealthy\n";
                    throw std::runtime_error(
                        "Health probe failed for " + name
                    );
                }

                service.state = ServiceState::Healthy;
                std::cout << name << ": healthy\n";
            }
        } catch (...) {
            for (auto it = started.rbegin(); it != started.rend(); ++it) {
                services_.at(*it).state = ServiceState::Stopped;
                std::cout << *it << ": stopped after startup failure\n";
            }
            throw;
        }
    }

    void stop() {
        auto order = startupOrder();

        for (auto it = order.rbegin(); it != order.rend(); ++it) {
            services_.at(*it).state = ServiceState::Stopped;
            std::cout << *it << ": stopped\n";
        }
    }

    void printStatus() const {
        for (const auto& [name, service] : services_) {
            std::cout << name << " = " << toString(service.state) << '\n';
        }
    }

    void setHealthProbe(const std::string& name, bool result) {
        auto found = services_.find(name);

        if (found == services_.end()) {
            throw std::invalid_argument("Unknown service: " + name);
        }

        found->second.healthProbeResult = result;
    }
};

Service makeService(
    const std::string& name,
    const std::string& image,
    std::set<std::string> networks,
    bool healthcheck,
    std::vector<Dependency> dependencies = {}
) {
    Service service;
    service.name = name;
    service.image = image;
    service.networks = std::move(networks);
    service.healthcheckConfigured = healthcheck;
    service.dependencies = std::move(dependencies);
    service.restartPolicy = RestartPolicy::UnlessStopped;
    return service;
}

ComposeEngine buildProject() {
    ComposeEngine engine;

    engine.addNetwork({"frontend", false, "bridge"});
    engine.addNetwork({"backend", true, "bridge"});

    engine.addService(makeService(
        "db", "postgres:18", {"backend"}, true
    ));

    engine.addService(makeService(
        "api",
        "python:3.13-slim",
        {"frontend", "backend"},
        true,
        {{"db", DependencyCondition::Healthy}}
    ));

    engine.addService(makeService(
        "web",
        "nginx:alpine",
        {"frontend"},
        true,
        {{"api", DependencyCondition::Healthy}}
    ));

    return engine;
}

int main() {
    try {
        ComposeEngine engine = buildProject();
        engine.validate();

        std::cout << "Startup order:";
        for (const auto& name : engine.startupOrder()) {
            std::cout << ' ' << name;
        }
        std::cout << "\n";

        std::cout << "API can reach DB: "
                  << std::boolalpha
                  << engine.canCommunicate("api", "db") << '\n';

        std::cout << "Web can reach DB directly: "
                  << engine.canCommunicate("web", "db") << '\n';

        engine.start();
        engine.printStatus();
        engine.stop();

        std::cout << "\nTesting unhealthy database:\n";
        ComposeEngine failing = buildProject();
        failing.setHealthProbe("db", false);

        try {
            failing.start();
        } catch (const std::exception& error) {
            std::cout << "Expected failure: " << error.what() << '\n';
            failing.printStatus();
        }

        std::cout << "\nTesting invalid configuration:\n";
        ComposeEngine invalid;
        invalid.addNetwork({"backend", true, "bridge"});
        invalid.addService(makeService(
            "broken", "postgres:18", {"missing-network"}, true
        ));

        try {
            invalid.validate();
        } catch (const std::exception& error) {
            std::cout << "Expected configuration error: "
                      << error.what() << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

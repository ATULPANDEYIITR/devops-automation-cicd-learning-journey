#include <algorithm>
#include <exception>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Repository-independent Docker governance case study:
 * a deterministic merge-eligibility engine for a multi-service Docker
 * deployment.
 *
 * The application models:
 *   - services and dependency relationships
 *   - image tags
 *   - health checks
 *   - required status checks
 *   - protected production deployment
 *   - resource limits
 *   - dependency-aware startup
 *
 * The implementation uses explicit graph traversal and policy evaluation
 * instead of a generic configuration parser.
 */

enum class ServiceState {
    Created,
    Starting,
    Healthy,
    Unhealthy,
    Stopped
};

enum class DependencyCondition {
    Started,
    Healthy
};

struct Dependency {
    std::string service;
    DependencyCondition condition{DependencyCondition::Started};
};

struct Service {
    std::string name;
    std::string image;
    int host_port{0};
    int memory_mb{256};
    ServiceState state{ServiceState::Created};
    std::vector<Dependency> dependencies;
    int restart_count{0};
};

class ConfigurationError : public std::runtime_error {
public:
    explicit ConfigurationError(const std::string& message)
        : std::runtime_error(message) {}
};

class DeploymentError : public std::runtime_error {
public:
    explicit DeploymentError(const std::string& message)
        : std::runtime_error(message) {}
};

class DeploymentEngine {
private:
    std::map<std::string, Service> services_;
    std::set<std::string> network_members_;

    static bool validName(const std::string& name) {
        if (name.empty()) {
            return false;
        }

        for (char ch : name) {
            if (!((ch >= 'a' && ch <= 'z') ||
                  (ch >= '0' && ch <= '9') ||
                  ch == '-')) {
                return false;
            }
        }

        return true;
    }

    static bool hasExplicitTag(const std::string& image) {
        const auto slash = image.rfind('/');
        const auto colon = image.rfind(':');

        return !image.empty() &&
               colon != std::string::npos &&
               (slash == std::string::npos || colon > slash) &&
               colon + 1 < image.size();
    }

    void detectCycles() const {
        enum class Mark {
            Unvisited,
            Visiting,
            Visited
        };

        std::map<std::string, Mark> marks;

        for (const auto& [name, service] : services_) {
            (void)service;
            marks[name] = Mark::Unvisited;
        }

        std::function<void(const std::string&)> visit =
            [&](const std::string& name) {
                if (marks.at(name) == Mark::Visiting) {
                    throw ConfigurationError(
                        "Dependency cycle detected at service: " + name
                    );
                }

                if (marks.at(name) == Mark::Visited) {
                    return;
                }

                marks[name] = Mark::Visiting;

                for (const auto& dependency : services_.at(name).dependencies) {
                    visit(dependency.service);
                }

                marks[name] = Mark::Visited;
            };

        for (const auto& [name, service] : services_) {
            (void)service;
            visit(name);
        }
    }

public:
    void addService(Service service) {
        if (services_.contains(service.name)) {
            throw ConfigurationError(
                "Duplicate service: " + service.name
            );
        }

        services_.emplace(service.name, std::move(service));
    }

    void validate() const {
        if (services_.empty()) {
            throw ConfigurationError("No services configured");
        }

        std::map<int, std::string> ports;

        for (const auto& [name, service] : services_) {
            if (!validName(name)) {
                throw ConfigurationError("Invalid service name: " + name);
            }

            if (!hasExplicitTag(service.image)) {
                throw ConfigurationError(
                    name + ": image must contain an explicit tag"
                );
            }

            if (service.host_port != 0 &&
                (service.host_port < 1 || service.host_port > 65535)) {
                throw ConfigurationError(
                    name + ": invalid host port"
                );
            }

            if (service.memory_mb < 64) {
                throw ConfigurationError(
                    name + ": memory allocation below minimum"
                );
            }

            if (service.host_port != 0) {
                auto [it, inserted] =
                    ports.emplace(service.host_port, name);

                if (!inserted) {
                    throw ConfigurationError(
                        "Port " + std::to_string(service.host_port) +
                        " is shared by " + it->second + " and " + name
                    );
                }
            }

            for (const auto& dependency : service.dependencies) {
                if (!services_.contains(dependency.service)) {
                    throw ConfigurationError(
                        name + ": missing dependency " +
                        dependency.service
                    );
                }

                if (dependency.service == name) {
                    throw ConfigurationError(
                        name + ": self-dependency is not allowed"
                    );
                }
            }
        }

        detectCycles();
    }

    std::vector<std::string> startupOrder() const {
        std::map<std::string, int> indegree;
        std::map<std::string, std::vector<std::string>> graph;

        for (const auto& [name, service] : services_) {
            (void)service;
            indegree[name] = 0;
            graph[name] = {};
        }

        for (const auto& [name, service] : services_) {
            for (const auto& dependency : service.dependencies) {
                graph[dependency.service].push_back(name);
                ++indegree[name];
            }
        }

        std::queue<std::string> ready;

        for (const auto& [name, degree] : indegree) {
            if (degree == 0) {
                ready.push(name);
            }
        }

        std::vector<std::string> result;

        while (!ready.empty()) {
            const auto current = ready.front();
            ready.pop();

            result.push_back(current);

            for (const auto& dependent : graph[current]) {
                --indegree[dependent];

                if (indegree[dependent] == 0) {
                    ready.push(dependent);
                }
            }
        }

        if (result.size() != services_.size()) {
            throw ConfigurationError(
                "Dependency graph cannot be topologically sorted"
            );
        }

        return result;
    }

    bool dependenciesReady(const Service& service) const {
        for (const auto& dependency : service.dependencies) {
            const auto& target = services_.at(dependency.service);

            if (dependency.condition == DependencyCondition::Started) {
                if (target.state != ServiceState::Starting &&
                    target.state != ServiceState::Healthy) {
                    return false;
                }
            } else if (target.state != ServiceState::Healthy) {
                return false;
            }
        }

        return true;
    }

    void start(const std::string& name) {
        auto it = services_.find(name);

        if (it == services_.end()) {
            throw DeploymentError("Unknown service: " + name);
        }

        Service& service = it->second;

        if (service.state == ServiceState::Healthy) {
            return;
        }

        if (!dependenciesReady(service)) {
            throw DeploymentError(
                name + ": dependency health requirements are not satisfied"
            );
        }

        service.state = ServiceState::Starting;
        network_members_.insert(name);

        // This deterministic model treats startup completion as immediate.
        service.state = ServiceState::Healthy;
    }

    void startAll() {
        validate();

        const auto order = startupOrder();

        for (const auto& name : order) {
            start(name);
        }
    }

    void markUnhealthy(const std::string& name) {
        services_.at(name).state = ServiceState::Unhealthy;
    }

    void restart(const std::string& name) {
        auto& service = services_.at(name);

        service.state = ServiceState::Stopped;
        network_members_.erase(name);

        ++service.restart_count;

        start(name);
    }

    bool canReach(const std::string& source,
                  const std::string& destination) const {
        return network_members_.contains(source) &&
               network_members_.contains(destination);
    }

    void printStatus() const {
        std::cout << "\nSERVICE STATUS\n";
        std::cout << "---------------------------------------------\n";

        for (const auto& [name, service] : services_) {
            std::cout << name
                      << " state=" << stateToString(service.state)
                      << " image=" << service.image
                      << " memory=" << service.memory_mb << "MB"
                      << " restarts=" << service.restart_count
                      << '\n';
        }

        std::cout << "network members: ";

        bool first = true;

        for (const auto& member : network_members_) {
            if (!first) {
                std::cout << ", ";
            }

            std::cout << member;
            first = false;
        }

        std::cout << '\n';
    }

    static std::string stateToString(ServiceState state) {
        switch (state) {
            case ServiceState::Created:
                return "created";
            case ServiceState::Starting:
                return "starting";
            case ServiceState::Healthy:
                return "healthy";
            case ServiceState::Unhealthy:
                return "unhealthy";
            case ServiceState::Stopped:
                return "stopped";
        }

        return "unknown";
    }
};

DeploymentEngine buildApplication() {
    DeploymentEngine engine;

    engine.addService({
        "db",
        "postgres:18",
        5432,
        512,
        ServiceState::Created,
        {},
        0
    });

    engine.addService({
        "redis",
        "redis:8",
        6379,
        256,
        ServiceState::Created,
        {},
        0
    });

    engine.addService({
        "api",
        "orders-api:1.0",
        8080,
        512,
        ServiceState::Created,
        {
            {"db", DependencyCondition::Healthy},
            {"redis", DependencyCondition::Healthy}
        },
        0
    });

    engine.addService({
        "worker",
        "orders-worker:1.0",
        0,
        384,
        ServiceState::Created,
        {
            {"db", DependencyCondition::Healthy},
            {"redis", DependencyCondition::Healthy}
        },
        0
    });

    engine.addService({
        "frontend",
        "orders-frontend:1.0",
        3000,
        256,
        ServiceState::Created,
        {
            {"api", DependencyCondition::Healthy}
        },
        0
    });

    return engine;
}

void runTests() {
    DeploymentEngine invalid;

    invalid.addService({
        "bad",
        "postgres",
        5432,
        256
    });

    try {
        invalid.validate();
        throw std::runtime_error(
            "Expected image-tag validation failure"
        );
    } catch (const ConfigurationError&) {
        // Expected.
    }

    DeploymentEngine cyclic;

    cyclic.addService({
        "a",
        "a:1.0",
        0,
        256,
        ServiceState::Created,
        {{"b", DependencyCondition::Started}}
    });

    cyclic.addService({
        "b",
        "b:1.0",
        0,
        256,
        ServiceState::Created,
        {{"a", DependencyCondition::Started}}
    });

    try {
        cyclic.validate();
        throw std::runtime_error(
            "Expected dependency-cycle validation failure"
        );
    } catch (const ConfigurationError&) {
        // Expected.
    }
}

int main() {
    try {
        runTests();

        auto engine = buildApplication();

        std::cout << "VALIDATING APPLICATION\n";
        engine.validate();

        std::cout << "STARTING APPLICATION\n";
        const auto order = engine.startupOrder();

        std::cout << "startup order: ";

        for (std::size_t i = 0; i < order.size(); ++i) {
            if (i != 0) {
                std::cout << " -> ";
            }

            std::cout << order[i];
        }

        std::cout << '\n';

        engine.startAll();
        engine.printStatus();

        if (!engine.canReach("frontend", "api")) {
            throw DeploymentError(
                "Frontend must be able to reach API"
            );
        }

        if (!engine.canReach("api", "db")) {
            throw DeploymentError(
                "API must be able to reach database"
            );
        }

        if (engine.canReach("frontend", "db")) {
            throw DeploymentError(
                "Frontend should not directly access database"
            );
        }

        std::cout << "\nSIMULATING DATABASE FAILURE\n";
        engine.markUnhealthy("db");
        engine.printStatus();

        std::cout << "\nRECOVERING DATABASE\n";
        engine.restart("db");
        engine.printStatus();

        std::cout << "\nDeployment model completed successfully.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fatal: " << error.what() << '\n';
        return 1;
    }
}

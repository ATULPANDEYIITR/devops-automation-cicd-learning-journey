#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

enum class TaskStatus {
    OK,
    CHANGED,
    SKIPPED,
    FAILED
};

enum class Environment {
    DEVELOPMENT,
    STAGING,
    PRODUCTION
};

std::string toString(TaskStatus status) {
    switch (status) {
        case TaskStatus::OK: return "OK";
        case TaskStatus::CHANGED: return "CHANGED";
        case TaskStatus::SKIPPED: return "SKIPPED";
        case TaskStatus::FAILED: return "FAILED";
    }

    return "UNKNOWN";
}

std::string toString(Environment environment) {
    switch (environment) {
        case Environment::DEVELOPMENT: return "development";
        case Environment::STAGING: return "staging";
        case Environment::PRODUCTION: return "production";
    }

    return "unknown";
}

struct Variables {
    std::string applicationName = "inventory-api";
    std::string applicationVersion = "1.0.0";
    std::string applicationDirectory = "/opt/inventory";
    std::string serviceName = "inventory-api";
    Environment environment = Environment::PRODUCTION;
    int applicationPort = 8080;

    void validate() const {
        if (applicationName.empty()) {
            throw std::invalid_argument(
                "Application name cannot be empty"
            );
        }

        if (applicationVersion.empty()) {
            throw std::invalid_argument(
                "Application version cannot be empty"
            );
        }

        if (applicationDirectory.empty() ||
            applicationDirectory.front() != '/') {
            throw std::invalid_argument(
                "Application directory must be absolute"
            );
        }

        if (applicationPort < 1 || applicationPort > 65535) {
            throw std::invalid_argument(
                "Application port must be between 1 and 65535"
            );
        }

        if (serviceName.empty()) {
            throw std::invalid_argument(
                "Service name cannot be empty"
            );
        }
    }
};

struct Host {
    std::string name;
    std::set<std::string> groups;
    Variables variables;

    std::set<std::string> directories;
    std::map<std::string, std::string> files;
    std::map<std::string, std::string> services;
    std::string deployedVersion;
    std::string lastRestart;
    bool failed = false;
};

struct TaskResult {
    std::string host;
    std::string task;
    TaskStatus status;
    std::string message;
};

using Action = std::function<bool(Host&)>;

struct Task {
    std::string name;
    Action action;
    std::function<bool(const Host&)> condition;
    std::vector<std::string> notifications;
};

struct Handler {
    std::string name;
    Action action;
    std::set<std::string> listen;
};

class RepositoryAutomationEngine {
private:
    std::vector<Host> hosts;
    std::vector<Task> tasks;
    std::vector<Handler> handlers;
    std::map<std::string, std::set<std::string>> pending;
    std::vector<TaskResult> results;

    void record(
        const Host& host,
        const std::string& task,
        TaskStatus status,
        const std::string& message
    ) {
        results.push_back({
            host.name,
            task,
            status,
            message
        });
    }

    void notify(Host& host, const std::string& event) {
        bool found = false;

        for (const auto& handler : handlers) {
            if (handler.name == event ||
                handler.listen.count(event) > 0) {

                pending[host.name].insert(handler.name);
                found = true;
            }
        }

        if (!found) {
            throw std::runtime_error(
                "Unknown handler notification: " + event
            );
        }
    }

    void executeTask(const Task& task, Host& host) {
        if (host.failed) return;

        try {
            if (task.condition && !task.condition(host)) {
                record(
                    host,
                    task.name,
                    TaskStatus::SKIPPED,
                    "Conditional expression evaluated to false"
                );
                return;
            }

            const bool changed = task.action(host);

            record(
                host,
                task.name,
                changed ? TaskStatus::CHANGED : TaskStatus::OK,
                "Task completed"
            );

            if (changed) {
                for (const auto& event : task.notifications) {
                    notify(host, event);
                }
            }
        }
        catch (const std::exception& error) {
            host.failed = true;

            record(
                host,
                task.name,
                TaskStatus::FAILED,
                error.what()
            );
        }
    }

    void flushHandlers(Host& host) {
        auto queue = pending.find(host.name);

        if (queue == pending.end() || host.failed) {
            return;
        }

        const auto notifications = queue->second;
        pending.erase(queue);

        // Registration order controls execution order.
        // A set prevents duplicate handler execution.
        for (const auto& handler : handlers) {
            if (notifications.count(handler.name) == 0) {
                continue;
            }

            try {
                const bool changed = handler.action(host);

                record(
                    host,
                    "Handler: " + handler.name,
                    changed ? TaskStatus::CHANGED : TaskStatus::OK,
                    "Handler executed"
                );
            }
            catch (const std::exception& error) {
                host.failed = true;

                record(
                    host,
                    "Handler: " + handler.name,
                    TaskStatus::FAILED,
                    error.what()
                );

                break;
            }
        }
    }

public:
    void addHost(Host host) {
        host.variables.validate();

        const auto duplicate = std::find_if(
            hosts.begin(),
            hosts.end(),
            [&](const Host& existing) {
                return existing.name == host.name;
            }
        );

        if (duplicate != hosts.end()) {
            throw std::invalid_argument(
                "Duplicate host: " + host.name
            );
        }

        hosts.push_back(std::move(host));
    }

    void addTask(Task task) {
        if (task.name.empty() || !task.action) {
            throw std::invalid_argument(
                "Task requires a name and action"
            );
        }

        tasks.push_back(std::move(task));
    }

    void addHandler(Handler handler) {
        const auto duplicate = std::find_if(
            handlers.begin(),
            handlers.end(),
            [&](const Handler& existing) {
                return existing.name == handler.name;
            }
        );

        if (duplicate != handlers.end()) {
            throw std::invalid_argument(
                "Duplicate handler: " + handler.name
            );
        }

        handlers.push_back(std::move(handler));
    }

    void run() {
        for (const auto& task : tasks) {
            for (auto& host : hosts) {
                executeTask(task, host);
            }

            for (auto& host : hosts) {
                flushHandlers(host);
            }
        }
    }

    void printReport() const {
        std::cout << "\nANSIBLE AUTOMATION REPORT\n";
        std::cout << "=========================\n";

        for (const auto& host : hosts) {
            std::cout << "\nHost: " << host.name << '\n';
            std::cout << "Environment: "
                      << toString(host.variables.environment)
                      << '\n';
            std::cout << "Application version: "
                      << (host.deployedVersion.empty()
                          ? "not deployed"
                          : host.deployedVersion)
                      << '\n';

            std::map<std::string, int> counts;

            for (const auto& result : results) {
                if (result.host == host.name) {
                    counts[toString(result.status)]++;
                }
            }

            std::cout << "Status: "
                      << (host.failed ? "FAILED" : "SUCCESS")
                      << '\n';

            for (const auto& result : results) {
                if (result.host != host.name) continue;

                std::cout
                    << "  [" << toString(result.status) << "] "
                    << result.task << " - "
                    << result.message << '\n';
            }

            std::cout << "Statistics: ";

            for (const auto& entry : counts) {
                std::cout << entry.first << '='
                          << entry.second << ' ';
            }

            std::cout << '\n';
        }
    }

    bool hasFailures() const {
        return std::any_of(
            hosts.begin(),
            hosts.end(),
            [](const Host& host) {
                return host.failed;
            }
        );
    }
};

bool createDirectory(Host& host) {
    return host.directories.insert(
        host.variables.applicationDirectory
    ).second;
}

bool deployApplication(Host& host) {
    if (host.deployedVersion ==
        host.variables.applicationVersion) {
        return false;
    }

    host.deployedVersion =
        host.variables.applicationVersion;

    return true;
}

bool renderConfiguration(Host& host) {
    const Variables& variables = host.variables;

    const std::string destination =
        variables.applicationDirectory + "/application.conf";

    const std::string content =
        "server {\n"
        "    listen " + std::to_string(
            variables.applicationPort
        ) + ";\n"
        "    server_name " + variables.applicationName + ";\n"
        "    environment " +
        toString(variables.environment) + ";\n"
        "}\n";

    auto existing = host.files.find(destination);

    if (existing != host.files.end() &&
        existing->second == content) {
        return false;
    }

    host.files[destination] = content;
    return true;
}

bool restartApplication(Host& host) {
    host.services[host.variables.serviceName] = "running";
    host.lastRestart = host.variables.serviceName;

    return true;
}

bool verifyApplication(Host& host) {
    if (host.deployedVersion.empty()) {
        throw std::runtime_error(
            "Application version is not deployed"
        );
    }

    auto service = host.services.find(
        host.variables.serviceName
    );

    if (service == host.services.end() ||
        service->second != "running") {
        throw std::runtime_error(
            "Application service is not running"
        );
    }

    return false;
}

int main() {
    try {
        RepositoryAutomationEngine engine;

        Variables production;
        production.validate();

        Host first;
        first.name = "web01.example.internal";
        first.groups = {"web"};
        first.variables = production;

        Host second;
        second.name = "web02.example.internal";
        second.groups = {"web", "canary"};
        second.variables = production;
        second.variables.applicationPort = 8081;

        engine.addHost(first);
        engine.addHost(second);

        engine.addHandler({
            "restart application",
            restartApplication,
            {"application configuration changed"}
        });

        engine.addTask({
            "Create application directory",
            createDirectory,
            nullptr,
            {}
        });

        engine.addTask({
            "Deploy application",
            deployApplication,
            nullptr,
            {"application configuration changed"}
        });

        engine.addTask({
            "Render configuration",
            renderConfiguration,
            [](const Host& host) {
                return host.variables.environment ==
                    Environment::PRODUCTION;
            },
            {"restart application"}
        });

        engine.addTask({
            "Verify application",
            verifyApplication,
            [](const Host& host) {
                return host.groups.count("web") > 0;
            },
            {}
        });

        engine.run();
        engine.printReport();

        return engine.hasFailures() ? 1 : 0;
    }
    catch (const std::exception& error) {
        std::cerr << "Automation error: "
                  << error.what() << '\n';

        return 1;
    }
}

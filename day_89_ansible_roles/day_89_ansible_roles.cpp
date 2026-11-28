#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

enum class TaskStatus {
    OK,
    CHANGED,
    FAILED,
    SKIPPED
};

enum class MergePolicy {
    STOP_ON_FAILURE,
    CONTINUE_INDEPENDENT_HOSTS
};

string statusName(TaskStatus status) {
    switch (status) {
        case TaskStatus::OK: return "OK";
        case TaskStatus::CHANGED: return "CHANGED";
        case TaskStatus::FAILED: return "FAILED";
        case TaskStatus::SKIPPED: return "SKIPPED";
    }
    return "UNKNOWN";
}

struct TaskResult {
    string host;
    string role;
    string task;
    TaskStatus status;
    string message;
};

struct Host {
    string name;
    set<string> packages;
    map<string, string> services;
    map<string, string> files;
    map<string, int> restartCounts;
    bool failed = false;
};

struct Variables {
    map<string, string> values;

    string get(
        const string& key,
        const string& fallback = ""
    ) const {
        auto it = values.find(key);

        if (it == values.end()) {
            return fallback;
        }

        return it->second;
    }
};

struct ActionResult {
    bool changed;
    string message;
};

using Action = function<ActionResult(Host&, const Variables&)>;

struct Handler {
    string name;
    Action action;
};

struct Task {
    string name;
    Action action;
    set<string> tags;
    vector<string> notifications;
    function<bool(const Host&, const Variables&)> condition;

    Task(
        string taskName,
        Action taskAction,
        set<string> taskTags = {},
        vector<string> notify = {},
        function<bool(const Host&, const Variables&)> predicate =
            [](const Host&, const Variables&) { return true; }
    ) :
        name(move(taskName)),
        action(move(taskAction)),
        tags(move(taskTags)),
        notifications(move(notify)),
        condition(move(predicate)) {

        if (name.empty() || !action) {
            throw invalid_argument(
                "Task requires a name and an action."
            );
        }
    }
};

struct Role {
    string name;
    Variables defaults;
    Variables variables;
    vector<string> dependencies;
    vector<Task> tasks;
    map<string, Handler> handlers;
};

class RoleRegistry {
private:
    unordered_map<string, Role> roles;

public:
    void registerRole(Role role) {
        if (role.name.empty()) {
            throw invalid_argument("Role name cannot be empty.");
        }

        if (roles.count(role.name)) {
            throw invalid_argument(
                "Duplicate role: " + role.name
            );
        }

        for (const auto& task : role.tasks) {
            for (const auto& handler : task.notifications) {
                if (!role.handlers.count(handler)) {
                    throw invalid_argument(
                        "Unknown handler: " + handler
                    );
                }
            }
        }

        roles.emplace(role.name, move(role));
    }

    vector<const Role*> resolve(
        const vector<string>& requested
    ) const {
        vector<const Role*> ordered;

        unordered_set<string> visited;
        unordered_set<string> active;

        function<void(const string&)> visit =
            [&](const string& name) {

            auto it = roles.find(name);

            if (it == roles.end()) {
                throw runtime_error(
                    "Unknown role: " + name
                );
            }

            if (active.count(name)) {
                throw runtime_error(
                    "Circular dependency: " + name
                );
            }

            if (visited.count(name)) return;

            active.insert(name);

            for (const string& dependency :
                 it->second.dependencies) {
                visit(dependency);
            }

            active.erase(name);
            visited.insert(name);

            ordered.push_back(&it->second);
        };

        for (const string& role : requested) {
            visit(role);
        }

        return ordered;
    }
};

class RoleEngine {
private:
    const RoleRegistry& registry;
    bool checkMode;
    set<string> selectedTags;

    vector<TaskResult> results;

    struct PendingHandler {
        const Role* role;
        string name;
        Host* host;
    };

    vector<PendingHandler> pending;

    void record(
        const Host& host,
        const Role& role,
        const string& task,
        TaskStatus status,
        const string& message
    ) {
        results.push_back({
            host.name,
            role.name,
            task,
            status,
            message
        });

        cout
            << "[" << statusName(status) << "] "
            << host.name << " / "
            << role.name << " / "
            << task << " : "
            << message << '\n';
    }

    Variables resolveVariables(
        const Role& role,
        const Host& host,
        const Variables& playVariables,
        const Variables& extraVariables
    ) const {

        Variables result = role.defaults;

        // Host inventory overrides role defaults.
        for (const auto& item : playVariables.values) {
            result.values[item.first] = item.second;
        }

        for (const auto& item : role.variables.values) {
            result.values[item.first] = item.second;
        }

        // Extra variables have the highest precedence here.
        for (const auto& item : extraVariables.values) {
            result.values[item.first] = item.second;
        }

        // Host variables are stored separately in this example.
        // Host-specific overrides are applied explicitly.
        (void)host;

        return result;
    }

    void executeTask(
        Host& host,
        const Role& role,
        const Task& task,
        const Variables& variables
    ) {

        if (host.failed) return;

        if (!selectedTags.empty()) {
            bool matches = task.tags.count("always") > 0;

            for (const auto& tag : selectedTags) {
                if (task.tags.count(tag)) {
                    matches = true;
                    break;
                }
            }

            if (!matches) {
                record(
                    host, role, task.name,
                    TaskStatus::SKIPPED,
                    "Tag mismatch."
                );
                return;
            }
        }

        try {
            if (!task.condition(host, variables)) {
                record(
                    host, role, task.name,
                    TaskStatus::SKIPPED,
                    "Condition evaluated to false."
                );
                return;
            }

            if (checkMode) {
                record(
                    host, role, task.name,
                    TaskStatus::OK,
                    "Check mode: no mutation performed."
                );
                return;
            }

            ActionResult outcome = task.action(
                host, variables
            );

            record(
                host,
                role,
                task.name,
                outcome.changed
                    ? TaskStatus::CHANGED
                    : TaskStatus::OK,
                outcome.message
            );

            if (outcome.changed) {
                for (const auto& handler : task.notifications) {
                    pending.push_back({
                        &role,
                        handler,
                        &host
                    });
                }
            }

        } catch (const exception& error) {
            host.failed = true;

            record(
                host,
                role,
                task.name,
                TaskStatus::FAILED,
                error.what()
            );
        }
    }

    void flushHandlers() {
        set<pair<string, string>> executed;

        for (const auto& notification : pending) {
            Host& host = *notification.host;
            const Role& role = *notification.role;

            if (host.failed) continue;

            const string& handlerName = notification.name;

            auto key = make_pair(host.name, role.name + ":" + handlerName);

            // A handler is notified only once per host and role
            // during a flush cycle.
            if (!executed.insert(key).second) {
                continue;
            }

            try {
                auto it = role.handlers.find(handlerName);

                if (it == role.handlers.end()) {
                    throw runtime_error(
                        "Handler not found: " + handlerName
                    );
                }

                Variables variables = role.defaults;

                ActionResult outcome = it->second.action(
                    host, variables
                );

                record(
                    host,
                    role,
                    "handler:" + handlerName,
                    outcome.changed
                        ? TaskStatus::CHANGED
                        : TaskStatus::OK,
                    outcome.message
                );

            } catch (const exception& error) {
                host.failed = true;

                record(
                    host,
                    role,
                    "handler:" + handlerName,
                    TaskStatus::FAILED,
                    error.what()
                );
            }
        }

        pending.clear();
    }

public:
    RoleEngine(
        const RoleRegistry& roleRegistry,
        bool dryRun = false,
        set<string> tags = {}
    ) :
        registry(roleRegistry),
        checkMode(dryRun),
        selectedTags(move(tags)) {}

    const vector<TaskResult>& run(
        vector<Host>& hosts,
        const vector<string>& requestedRoles,
        const Variables& playVariables = {},
        const Variables& extraVariables = {}
    ) {

        if (hosts.empty()) {
            throw invalid_argument(
                "Inventory must contain at least one host."
            );
        }

        vector<const Role*> roles = registry.resolve(
            requestedRoles
        );

        for (const Role* role : roles) {
            for (Host& host : hosts) {
                if (host.failed) continue;

                Variables variables = resolveVariables(
                    *role,
                    host,
                    playVariables,
                    extraVariables
                );

                for (const Task& task : role->tasks) {
                    executeTask(
                        host,
                        *role,
                        task,
                        variables
                    );
                }
            }

            flushHandlers();
        }

        return results;
    }

    void report() const {
        map<TaskStatus, int> counts;

        for (const auto& result : results) {
            counts[result.status]++;
        }

        cout << "\nExecution report\n";

        for (const auto& item : counts) {
            cout
                << statusName(item.first)
                << ": "
                << item.second
                << '\n';
        }
    }

    const vector<TaskResult>& getResults() const {
        return results;
    }
};

// Resource-management operations.

Action installPackage(const string& packageName) {
    return [packageName](
        Host& host,
        const Variables&
    ) -> ActionResult {

        if (packageName.empty()) {
            throw runtime_error("Package name is empty.");
        }

        if (host.packages.count(packageName)) {
            return {
                false,
                packageName + " already installed."
            };
        }

        host.packages.insert(packageName);

        return {
            true,
            "Installed " + packageName
        };
    };
}

Action ensureService(
    const string& serviceName,
    const string& desiredState = "running"
) {
    return [serviceName, desiredState](
        Host& host,
        const Variables&
    ) -> ActionResult {

        if (
            desiredState != "running" &&
            desiredState != "stopped"
        ) {
            throw runtime_error("Invalid service state.");
        }

        auto it = host.services.find(serviceName);

        if (
            it != host.services.end() &&
            it->second == desiredState
        ) {
            return {
                false,
                serviceName + " already " + desiredState
            };
        }

        host.services[serviceName] = desiredState;

        return {
            true,
            serviceName + " set to " + desiredState
        };
    };
}

Action deployConfiguration(
    const string& path,
    const string& variable
) {
    return [path, variable](
        Host& host,
        const Variables& variables
    ) -> ActionResult {

        if (path.rfind("/etc/", 0) != 0) {
            throw runtime_error(
                "Configuration must be under /etc/."
            );
        }

        string content = variables.get(variable);

        if (content.empty()) {
            throw runtime_error(
                "Missing configuration variable: " + variable
            );
        }

        auto it = host.files.find(path);

        if (
            it != host.files.end() &&
            it->second == content
        ) {
            return {
                false,
                "Configuration unchanged."
            };
        }

        host.files[path] = content;

        return {
            true,
            "Configuration deployed to " + path
        };
    };
}

Action restartService(const string& serviceName) {
    return [serviceName](
        Host& host,
        const Variables&
    ) -> ActionResult {

        auto it = host.services.find(serviceName);

        if (
            it == host.services.end() ||
            it->second != "running"
        ) {
            throw runtime_error(
                "Cannot restart an inactive service."
            );
        }

        host.restartCounts[serviceName]++;

        return {
            true,
            "Restarted " + serviceName
        };
    };
}

Role buildBaseRole() {
    Role role;

    role.name = "base";

    role.defaults.values = {
        {"timezone", "UTC"}
    };

    role.tasks.emplace_back(
        "Install curl",
        installPackage("curl"),
        set<string>{"base", "packages"}
    );

    return role;
}

Role buildWebRole() {
    Role role;

    role.name = "webserver";

    role.dependencies = {"base"};

    role.defaults.values = {
        {
            "nginx_config",
            "server { listen 8080; server_name app.internal; }"
        }
    };

    role.handlers.emplace(
        "restart nginx",
        Handler{
            "restart nginx",
            restartService("nginx")
        }
    );

    role.tasks.emplace_back(
        "Install nginx",
        installPackage("nginx"),
        set<string>{"web", "packages"}
    );

    role.tasks.emplace_back(
        "Deploy nginx configuration",
        deployConfiguration(
            "/etc/nginx/nginx.conf",
            "nginx_config"
        ),
        set<string>{"web", "configuration"},
        vector<string>{"restart nginx"}
    );

    role.tasks.emplace_back(
        "Start nginx",
        ensureService("nginx"),
        set<string>{"web", "services"}
    );

    return role;
}

Role buildMonitoringRole() {
    Role role;

    role.name = "monitoring";

    role.defaults.values = {
        {"monitoring_enabled", "true"}
    };

    role.tasks.emplace_back(
        "Install node exporter",
        installPackage("node-exporter"),
        set<string>{"monitoring"},
        vector<string>{},
        [](const Host& host, const Variables& variables) {
            auto it = host.files.find(
                "/etc/monitoring-disabled"
            );

            return it == host.files.end() &&
                variables.get("monitoring_enabled", "true")
                    == "true";
        }
    );

    return role;
}

int main() {
    try {
        RoleRegistry registry;

        registry.registerRole(buildBaseRole());
        registry.registerRole(buildWebRole());
        registry.registerRole(buildMonitoringRole());

        vector<Host> inventory = {
            {"web-01"},
            {"web-02"}
        };

        Variables playVariables;

        playVariables.values = {
            {
                "nginx_config",
                "server { listen 8080; server_name production.internal; }"
            }
        };

        RoleEngine engine(registry);

        engine.run(
            inventory,
            {"webserver", "monitoring"},
            playVariables
        );

        engine.report();

        cout << "\nFinal infrastructure state\n";

        for (const Host& host : inventory) {
            cout << "\nHost: " << host.name << '\n';

            cout << "Packages: ";

            for (const auto& package : host.packages) {
                cout << package << " ";
            }

            cout << "\nServices:\n";

            for (const auto& service : host.services) {
                cout
                    << service.first
                    << " = "
                    << service.second
                    << '\n';
            }

            cout << "Restart counts:\n";

            for (const auto& item : host.restartCounts) {
                cout
                    << item.first
                    << " = "
                    << item.second
                    << '\n';
            }
        }

        // Execute the same desired configuration again.
        // No package or configuration changes should occur.
        RoleEngine secondRun(registry);

        secondRun.run(
            inventory,
            {"webserver", "monitoring"},
            playVariables
        );

        for (const auto& result : secondRun.getResults()) {
            if (result.status == TaskStatus::CHANGED) {
                throw runtime_error(
                    "Idempotence verification failed."
                );
            }
        }

        cout << "\nIdempotence verification passed.\n";

        // Validate dependency cycle detection.
        RoleRegistry cyclicRegistry;

        Role alpha;
        alpha.name = "alpha";
        alpha.dependencies = {"beta"};

        Role beta;
        beta.name = "beta";
        beta.dependencies = {"alpha"};

        cyclicRegistry.registerRole(move(alpha));
        cyclicRegistry.registerRole(move(beta));

        try {
            cyclicRegistry.resolve({"alpha"});
            throw runtime_error(
                "Expected circular dependency failure."
            );
        } catch (const runtime_error& error) {
            if (
                string(error.what()).find(
                    "Circular dependency"
                ) == string::npos
            ) {
                throw;
            }

            cout << "Circular dependency validation passed.\n";
        }

    } catch (const exception& error) {
        cerr << "Execution error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

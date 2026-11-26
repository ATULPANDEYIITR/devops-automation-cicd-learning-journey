#include <algorithm>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace std;

enum class TaskStatus {
    OK,
    CHANGED,
    FAILED,
    SKIPPED
};

string statusName(TaskStatus status) {
    switch (status) {
        case TaskStatus::OK: return "ok";
        case TaskStatus::CHANGED: return "changed";
        case TaskStatus::FAILED: return "failed";
        case TaskStatus::SKIPPED: return "skipped";
    }

    return "unknown";
}

struct Host {
    string name;
    string address;
    string username = "ansible";
    int port = 22;
    bool reachable = true;

    map<string, string> variables;
    set<string> packages;
    map<string, string> services;
    map<string, string> files;
};

class Inventory {
private:
    map<string, Host> hosts;
    map<string, set<string>> groups;
    map<string, map<string, string>> groupVariables;

    static void validateIdentifier(const string& value) {
        if (value.empty()) {
            throw invalid_argument("Identifier cannot be empty.");
        }

        for (char c : value) {
            if (
                !isalnum(static_cast<unsigned char>(c)) &&
                c != '_' && c != '-' && c != '.'
            ) {
                throw invalid_argument("Invalid identifier.");
            }
        }
    }

public:
    void addHost(const Host& host, const vector<string>& groupNames) {
        validateIdentifier(host.name);

        if (host.address.empty()) {
            throw invalid_argument("Host address is required.");
        }

        if (host.port < 1 || host.port > 65535) {
            throw invalid_argument("Invalid SSH port.");
        }

        if (hosts.count(host.name)) {
            throw invalid_argument("Duplicate host: " + host.name);
        }

        hosts.emplace(host.name, host);

        for (const auto& group : groupNames) {
            validateIdentifier(group);
            groups[group].insert(host.name);
        }
    }

    void setGroupVariables(
        const string& group,
        const map<string, string>& variables
    ) {
        if (!groups.count(group)) {
            throw invalid_argument("Unknown group.");
        }

        groupVariables[group] = variables;
    }

    vector<Host*> select(const string& pattern) {
        vector<Host*> selected;
        set<string> names;

        if (pattern == "all") {
            for (const auto& [name, host] : hosts) {
                names.insert(name);
            }
        } else if (groups.count(pattern)) {
            names = groups.at(pattern);
        } else if (hosts.count(pattern)) {
            names.insert(pattern);
        } else {
            throw invalid_argument(
                "Inventory pattern not found: " + pattern
            );
        }

        for (const auto& name : names) {
            selected.push_back(&hosts.at(name));
        }

        return selected;
    }

    map<string, string> effectiveVariables(const Host& host) const {
        map<string, string> result;

        for (const auto& [group, members] : groups) {
            if (
                members.count(host.name) &&
                groupVariables.count(group)
            ) {
                for (const auto& [key, value] :
                     groupVariables.at(group)) {
                    result[key] = value;
                }
            }
        }

        for (const auto& [key, value] : host.variables) {
            result[key] = value;
        }

        return result;
    }
};

struct Task {
    string name;
    string module;
    map<string, string> arguments;
    vector<string> notify;
    bool condition = true;
    bool ignoreErrors = false;
};

struct Play {
    string name;
    string hosts;
    vector<Task> tasks;
    map<string, string> variables;
    map<string, Task> handlers;
};

struct Result {
    string host;
    string task;
    TaskStatus status;
    string message;
};

class ModuleRegistry {
public:
    using ModuleFunction = function<
        pair<TaskStatus, string>(
            Host&,
            const map<string, string>&,
            bool
        )
    >;

private:
    map<string, ModuleFunction> modules;

    static string getArgument(
        const map<string, string>& arguments,
        const string& key,
        const string& defaultValue = ""
    ) {
        auto it = arguments.find(key);

        return it == arguments.end()
            ? defaultValue
            : it->second;
    }

    static void validatePath(const string& path) {
        if (path.empty() || path.front() != '/') {
            throw invalid_argument(
                "An absolute path is required."
            );
        }

        if (
            path.find("/../") != string::npos ||
            path.ends_with("/..")
        ) {
            throw invalid_argument("Path traversal detected.");
        }
    }

public:
    ModuleRegistry() {
        registerModule(
            "package",
            [](Host& host, const auto& args, bool check) {
                string name = getArgument(args, "name");
                string state = getArgument(
                    args, "state", "present"
                );

                if (name.empty()) {
                    throw invalid_argument(
                        "Package name is required."
                    );
                }

                if (
                    state != "present" &&
                    state != "absent"
                ) {
                    throw invalid_argument(
                        "Invalid package state."
                    );
                }

                bool exists = host.packages.count(name);

                if (
                    (state == "present" && exists) ||
                    (state == "absent" && !exists)
                ) {
                    return make_pair(
                        TaskStatus::OK,
                        name + " already compliant"
                    );
                }

                if (!check) {
                    if (state == "present") {
                        host.packages.insert(name);
                    } else {
                        host.packages.erase(name);
                    }
                }

                return make_pair(
                    TaskStatus::CHANGED,
                    "Package " + name + ": " + state
                );
            }
        );

        registerModule(
            "service",
            [](Host& host, const auto& args, bool check) {
                string name = getArgument(args, "name");
                string state = getArgument(
                    args, "state", "started"
                );

                string enabled = getArgument(
                    args, "enabled", "true"
                );

                if (name.empty()) {
                    throw invalid_argument(
                        "Service name is required."
                    );
                }

                if (
                    state != "started" &&
                    state != "stopped"
                ) {
                    throw invalid_argument(
                        "Invalid service state."
                    );
                }

                if (
                    enabled != "true" &&
                    enabled != "false"
                ) {
                    throw invalid_argument(
                        "enabled must be true or false."
                    );
                }

                string desired = state + ":" + enabled;

                if (
                    host.services.count(name) &&
                    host.services.at(name) == desired
                ) {
                    return make_pair(
                        TaskStatus::OK,
                        "Service already compliant: " + name
                    );
                }

                if (!check) {
                    host.services[name] = desired;
                }

                return make_pair(
                    TaskStatus::CHANGED,
                    "Service " + name + ": " + state
                );
            }
        );

        registerModule(
            "file",
            [](Host& host, const auto& args, bool check) {
                string path = getArgument(args, "path");
                string state = getArgument(
                    args, "state", "file"
                );

                string mode = getArgument(
                    args, "mode", "0644"
                );

                validatePath(path);

                if (
                    state != "file" &&
                    state != "directory" &&
                    state != "absent"
                ) {
                    throw invalid_argument(
                        "Invalid file state."
                    );
                }

                string desired = state + ":" + mode;

                if (
                    state != "absent" &&
                    host.files.count(path) &&
                    host.files.at(path) == desired
                ) {
                    return make_pair(
                        TaskStatus::OK,
                        "File already compliant: " + path
                    );
                }

                if (
                    state == "absent" &&
                    !host.files.count(path)
                ) {
                    return make_pair(
                        TaskStatus::OK,
                        "File already absent: " + path
                    );
                }

                if (!check) {
                    if (state == "absent") {
                        host.files.erase(path);
                    } else {
                        host.files[path] = desired;
                    }
                }

                return make_pair(
                    TaskStatus::CHANGED,
                    "File evaluated: " + path
                );
            }
        );

        registerModule(
            "command",
            [](Host&, const auto& args, bool) {
                string command = getArgument(args, "command");

                static const map<string, string> allowed = {
                    {"check_http", "HTTP configuration verified"},
                    {"check_disk", "Disk capacity verified"},
                    {"check_service", "Service availability verified"}
                };

                auto it = allowed.find(command);

                if (it == allowed.end()) {
                    throw invalid_argument(
                        "Command is not permitted."
                    );
                }

                return make_pair(
                    TaskStatus::OK,
                    it->second
                );
            }
        );
    }

    void registerModule(
        const string& name,
        ModuleFunction function
    ) {
        if (modules.count(name)) {
            throw invalid_argument(
                "Duplicate module: " + name
            );
        }

        modules.emplace(name, move(function));
    }

    pair<TaskStatus, string> execute(
        const string& name,
        Host& host,
        const map<string, string>& arguments,
        bool checkMode
    ) const {
        auto it = modules.find(name);

        if (it == modules.end()) {
            throw invalid_argument(
                "Unknown module: " + name
            );
        }

        return it->second(host, arguments, checkMode);
    }
};

class PlaybookEngine {
private:
    Inventory& inventory;
    ModuleRegistry registry;
    vector<Result> results;

    static map<string, string> resolveArguments(
        const map<string, string>& arguments,
        const map<string, string>& variables
    ) {
        map<string, string> resolved = arguments;

        for (auto& [key, value] : resolved) {
            if (
                value.size() >= 4 &&
                value.substr(0, 2) == "{{" &&
                value.substr(value.size() - 2) == "}}"
            ) {
                string variable = value.substr(
                    2, value.size() - 4
                );

                variable.erase(
                    remove_if(
                        variable.begin(),
                        variable.end(),
                        ::isspace
                    ),
                    variable.end()
                );

                if (!variables.count(variable)) {
                    throw invalid_argument(
                        "Undefined variable: " + variable
                    );
                }

                value = variables.at(variable);
            }
        }

        return resolved;
    }

    void record(const Result& result) {
        results.push_back(result);

        cout << left
             << setw(12) << result.host
             << setw(25) << result.task
             << setw(10) << statusName(result.status)
             << result.message << '\n';
    }

    void executeHandler(
        Host& host,
        const string& name,
        const Task& handler,
        const map<string, string>& variables,
        bool checkMode
    ) {
        try {
            auto arguments = resolveArguments(
                handler.arguments,
                variables
            );

            auto [status, message] = registry.execute(
                handler.module,
                host,
                arguments,
                checkMode
            );

            record({
                host.name,
                "handler:" + name,
                status,
                message
            });
        } catch (const exception& error) {
            record({
                host.name,
                "handler:" + name,
                TaskStatus::FAILED,
                error.what()
            });
        }
    }

public:
    explicit PlaybookEngine(Inventory& inv)
        : inventory(inv) {}

    void executePlay(const Play& play, bool checkMode = false) {
        if (play.name.empty() || play.tasks.empty()) {
            throw invalid_argument(
                "Play requires a name and tasks."
            );
        }

        auto hosts = inventory.select(play.hosts);

        for (Host* host : hosts) {
            if (!host->reachable) {
                record({
                    host->name,
                    "connection",
                    TaskStatus::FAILED,
                    "Host unreachable"
                });

                continue;
            }

            auto variables = inventory.effectiveVariables(*host);

            for (const auto& [key, value] : play.variables) {
                variables[key] = value;
            }

            set<string> notified;
            bool failed = false;

            for (const Task& task : play.tasks) {
                if (failed) {
                    break;
                }

                if (!task.condition) {
                    record({
                        host->name,
                        task.name,
                        TaskStatus::SKIPPED,
                        "Condition evaluated to false"
                    });

                    continue;
                }

                try {
                    auto arguments = resolveArguments(
                        task.arguments,
                        variables
                    );

                    auto [status, message] = registry.execute(
                        task.module,
                        *host,
                        arguments,
                        checkMode
                    );

                    record({
                        host->name,
                        task.name,
                        status,
                        message
                    });

                    if (status == TaskStatus::CHANGED) {
                        notified.insert(
                            task.notify.begin(),
                            task.notify.end()
                        );
                    }
                } catch (const exception& error) {
                    record({
                        host->name,
                        task.name,
                        TaskStatus::FAILED,
                        error.what()
                    });

                    if (!task.ignoreErrors) {
                        failed = true;
                    }
                }
            }

            if (!failed) {
                for (const auto& handlerName : notified) {
                    auto handler = play.handlers.find(handlerName);

                    if (handler == play.handlers.end()) {
                        record({
                            host->name,
                            "handler:" + handlerName,
                            TaskStatus::FAILED,
                            "Handler not defined"
                        });

                        continue;
                    }

                    executeHandler(
                        *host,
                        handlerName,
                        handler->second,
                        variables,
                        checkMode
                    );
                }
            }
        }
    }

    void printReport() const {
        map<string, map<string, int>> report;

        for (const auto& result : results) {
            report[result.host][
                statusName(result.status)
            ]++;
        }

        cout << "\nExecution report\n";

        for (const auto& [host, counts] : report) {
            cout << host << '\n';

            for (const auto& [status, count] : counts) {
                cout << "  "
                     << setw(10) << status
                     << count << '\n';
            }
        }
    }
};

int main(int argc, char* argv[]) {
    try {
        bool checkMode = false;

        for (int i = 1; i < argc; ++i) {
            if (string(argv[i]) == "--check") {
                checkMode = true;
            }
        }

        Inventory inventory;

        Host web01;
        web01.name = "web01";
        web01.address = "192.168.10.11";
        web01.variables["environment"] = "production";

        Host web02;
        web02.name = "web02";
        web02.address = "192.168.10.12";

        Host db01;
        db01.name = "db01";
        db01.address = "192.168.10.21";

        inventory.addHost(web01, {"web"});
        inventory.addHost(web02, {"web"});
        inventory.addHost(db01, {"database"});

        inventory.setGroupVariables(
            "web",
            {{"package_name", "nginx"}}
        );

        inventory.setGroupVariables(
            "database",
            {{"package_name", "postgresql"}}
        );

        Task installWeb{
            "Install nginx",
            "package",
            {
                {"name", "{{ package_name }}"},
                {"state", "present"}
            },
            {},
            true,
            false
        };

        Task createDirectory{
            "Create application directory",
            "file",
            {
                {"path", "/srv/application"},
                {"state", "directory"},
                {"mode", "0755"}
            }
        };

        Task startWeb{
            "Start nginx",
            "service",
            {
                {"name", "nginx"},
                {"state", "started"},
                {"enabled", "true"}
            },
            {"reload_nginx"}
        };

        Task validateHTTP{
            "Validate HTTP",
            "command",
            {{"command", "check_http"}}
        };

        Task reloadHandler{
            "Reload nginx",
            "service",
            {
                {"name", "nginx"},
                {"state", "started"},
                {"enabled", "true"}
            }
        };

        Play webPlay{
            "Configure web infrastructure",
            "web",
            {
                installWeb,
                createDirectory,
                startWeb,
                validateHTTP
            },
            {},
            {{"reload_nginx", reloadHandler}}
        };

        Play databasePlay{
            "Configure database infrastructure",
            "database",
            {
                Task{
                    "Install PostgreSQL",
                    "package",
                    {
                        {"name", "{{ package_name }}"},
                        {"state", "present"}
                    }
                },
                Task{
                    "Start PostgreSQL",
                    "service",
                    {
                        {"name", "postgresql"},
                        {"state", "started"},
                        {"enabled", "true"}
                    }
                }
            }
        };

        PlaybookEngine engine(inventory);

        cout << "Ansible Fundamentals Simulator\n";
        cout << "Mode: "
             << (checkMode ? "CHECK" : "NORMAL")
             << "\n\n";

        engine.executePlay(webPlay, checkMode);
        engine.executePlay(databasePlay, checkMode);
        engine.printReport();

        return 0;
    } catch (const exception& error) {
        cerr << "Execution error: "
             << error.what() << '\n';

        return 1;
    }
}

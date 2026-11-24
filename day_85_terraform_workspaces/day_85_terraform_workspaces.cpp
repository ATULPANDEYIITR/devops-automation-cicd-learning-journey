#include <algorithm>
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

/*
 * Terraform Workspaces: Environment Separation and Workspace Strategies
 *
 * C++17 repository-style infrastructure state management engine.
 */

enum class Environment {
    Development,
    Staging,
    Production
};

enum class Action {
    Create,
    Update,
    Destroy,
    NoChange
};

enum class DeploymentStatus {
    Planned,
    Applied,
    Rejected
};

string toString(Environment environment) {
    switch (environment) {
        case Environment::Development: return "development";
        case Environment::Staging: return "staging";
        case Environment::Production: return "production";
    }
    throw runtime_error("Unknown environment.");
}

string toString(Action action) {
    switch (action) {
        case Action::Create: return "CREATE";
        case Action::Update: return "UPDATE";
        case Action::Destroy: return "DESTROY";
        case Action::NoChange: return "NO_CHANGE";
    }
    throw runtime_error("Unknown action.");
}

struct Resource {
    string address;
    map<string, string> attributes;

    bool operator==(const Resource& other) const {
        return address == other.address &&
               attributes == other.attributes;
    }
};

struct EnvironmentPolicy {
    Environment environment;
    string region;
    set<string> allowedInstanceTypes;
    int maximumInstances;
    bool approvalRequired;
    double monthlyBudget;
};

struct Workspace {
    string name;
    Environment environment;
    EnvironmentPolicy policy;
    map<string, Resource> resources;
    unsigned long long serial = 0;
    bool active = true;
};

struct Operation {
    Action action;
    string address;
    optional<Resource> desired;
};

struct Plan {
    string workspace;
    unsigned long long expectedSerial;
    vector<Operation> operations;
    bool approvalRequired;
};

class WorkspaceException : public runtime_error {
public:
    explicit WorkspaceException(const string& message)
        : runtime_error(message) {}
};

class GovernanceEngine {
private:
    map<string, Workspace> workspaces;
    string currentWorkspace = "default";

    static bool validName(const string& name) {
        if (name.empty() || name.size() > 63) {
            return false;
        }

        if (name.front() < 'a' || name.front() > 'z') {
            return false;
        }

        return all_of(name.begin(), name.end(), [](unsigned char c) {
            return (c >= 'a' && c <= 'z') ||
                   (c >= '0' && c <= '9') ||
                   c == '_' || c == '-';
        });
    }

    static bool validAddress(const string& address) {
        if (address.empty() || address.size() > 128) {
            return false;
        }

        return all_of(address.begin(), address.end(),
            [](unsigned char c) {
                return (c >= 'a' && c <= 'z') ||
                       (c >= 'A' && c <= 'Z') ||
                       (c >= '0' && c <= '9') ||
                       c == '_' || c == '.' || c == '-';
            });
    }

    Workspace& current() {
        auto it = workspaces.find(currentWorkspace);

        if (it == workspaces.end()) {
            throw WorkspaceException("Current workspace unavailable.");
        }

        return it->second;
    }

    const Workspace& current() const {
        return workspaces.at(currentWorkspace);
    }

    static void validateResource(
        const Resource& resource,
        const EnvironmentPolicy& policy
    ) {
        if (!validAddress(resource.address)) {
            throw WorkspaceException("Invalid resource address.");
        }

        auto type = resource.attributes.find("instance_type");

        if (type != resource.attributes.end()) {
            if (!policy.allowedInstanceTypes.count(type->second)) {
                throw WorkspaceException(
                    "Instance type violates environment policy."
                );
            }
        }

        auto count = resource.attributes.find("count");

        if (count != resource.attributes.end()) {
            int value;

            try {
                size_t position = 0;
                value = stoi(count->second, &position);

                if (position != count->second.size()) {
                    throw invalid_argument("Invalid count.");
                }
            } catch (...) {
                throw WorkspaceException("Instance count must be an integer.");
            }

            if (value < 0 || value > policy.maximumInstances) {
                throw WorkspaceException(
                    "Instance count exceeds policy."
                );
            }
        }
    }

public:
    GovernanceEngine() {
        EnvironmentPolicy policy{
            Environment::Development,
            "ap-south-1",
            {"t3.micro", "t3.small"},
            2,
            false,
            100.0
        };

        workspaces.emplace(
            "default",
            Workspace{
                "default",
                Environment::Development,
                policy,
                {},
                0,
                true
            }
        );
    }

    void createWorkspace(
        const string& name,
        EnvironmentPolicy policy
    ) {
        if (!validName(name)) {
            throw WorkspaceException("Invalid workspace name.");
        }

        if (workspaces.count(name)) {
            throw WorkspaceException("Workspace already exists.");
        }

        if (policy.monthlyBudget <= 0 ||
            policy.maximumInstances < 0) {
            throw WorkspaceException("Invalid environment policy.");
        }

        if (policy.environment == Environment::Production &&
            !policy.approvalRequired) {
            throw WorkspaceException(
                "Production requires deployment approval."
            );
        }

        workspaces.emplace(
            name,
            Workspace{
                name,
                policy.environment,
                policy,
                {},
                0,
                true
            }
        );
    }

    void selectWorkspace(const string& name) {
        auto it = workspaces.find(name);

        if (it == workspaces.end() || !it->second.active) {
            throw WorkspaceException("Workspace unavailable.");
        }

        currentWorkspace = name;
    }

    Plan generatePlan(
        const map<string, optional<Resource>>& desired
    ) const {
        const Workspace& workspace = current();

        if (desired.empty()) {
            throw WorkspaceException("Empty changeset.");
        }

        Plan plan{
            workspace.name,
            workspace.serial,
            {},
            workspace.policy.approvalRequired
        };

        for (const auto& [address, resource] : desired) {
            if (!validAddress(address)) {
                throw WorkspaceException("Invalid resource address.");
            }

            auto existing = workspace.resources.find(address);

            if (!resource.has_value()) {
                if (existing != workspace.resources.end()) {
                    plan.operations.push_back({
                        Action::Destroy,
                        address,
                        nullopt
                    });
                }
                continue;
            }

            if (resource->address != address) {
                throw WorkspaceException(
                    "Resource key and address do not match."
                );
            }

            validateResource(*resource, workspace.policy);

            if (existing == workspace.resources.end()) {
                plan.operations.push_back({
                    Action::Create,
                    address,
                    resource
                });
            } else if (!(existing->second == resource.value())) {
                plan.operations.push_back({
                    Action::Update,
                    address,
                    resource
                });
            } else {
                plan.operations.push_back({
                    Action::NoChange,
                    address,
                    resource
                });
            }
        }

        return plan;
    }

    void printPlan(const Plan& plan) const {
        cout << "\nPlan for " << plan.workspace << ":\n";

        for (const auto& operation : plan.operations) {
            cout << "  "
                 << setw(10) << left << toString(operation.action)
                 << operation.address << '\n';
        }

        cout << "Expected state serial: "
             << plan.expectedSerial << '\n';
    }

    void applyPlan(const Plan& plan, bool approved = false) {
        Workspace& workspace = current();

        if (workspace.name != plan.workspace) {
            throw WorkspaceException(
                "Plan belongs to another workspace."
            );
        }

        if (workspace.serial != plan.expectedSerial) {
            throw WorkspaceException(
                "Stale plan. Refresh infrastructure state."
            );
        }

        if (plan.approvalRequired && !approved) {
            throw WorkspaceException(
                "Production approval is required."
            );
        }

        // Apply against a copy. The live state changes only after
        // every operation succeeds.
        auto nextResources = workspace.resources;

        for (const auto& operation : plan.operations) {
            switch (operation.action) {
                case Action::Create:
                case Action::Update:
                    if (!operation.desired.has_value()) {
                        throw WorkspaceException(
                            "Missing resource configuration."
                        );
                    }
                    nextResources[operation.address] =
                        operation.desired.value();
                    break;

                case Action::Destroy:
                    nextResources.erase(operation.address);
                    break;

                case Action::NoChange:
                    break;
            }
        }

        workspace.resources.swap(nextResources);
        ++workspace.serial;

        cout << "Deployment applied: "
             << workspace.name
             << ", serial=" << workspace.serial << '\n';
    }

    void destroyResources(const string& name) {
        auto it = workspaces.find(name);

        if (it == workspaces.end()) {
            throw WorkspaceException("Workspace does not exist.");
        }

        it->second.resources.clear();
        ++it->second.serial;
    }

    void deleteWorkspace(const string& name) {
        if (name == "default") {
            throw WorkspaceException("Cannot delete default workspace.");
        }

        if (name == currentWorkspace) {
            throw WorkspaceException(
                "Select another workspace before deletion."
            );
        }

        auto it = workspaces.find(name);

        if (it == workspaces.end()) {
            throw WorkspaceException("Workspace not found.");
        }

        if (!it->second.resources.empty()) {
            throw WorkspaceException(
                "Resources must be destroyed before workspace deletion."
            );
        }

        workspaces.erase(it);
    }

    void report() const {
        cout << "\nINFRASTRUCTURE WORKSPACE REPORT\n";
        cout << "--------------------------------------\n";

        for (const auto& [name, workspace] : workspaces) {
            cout << "Workspace: " << name << '\n'
                 << "Environment: "
                 << toString(workspace.environment) << '\n'
                 << "Resources: "
                 << workspace.resources.size() << '\n'
                 << "State serial: "
                 << workspace.serial << "\n\n";
        }
    }
};

EnvironmentPolicy developmentPolicy() {
    return {
        Environment::Development,
        "ap-south-1",
        {"t3.micro", "t3.small"},
        2,
        false,
        100.0
    };
}

EnvironmentPolicy stagingPolicy() {
    return {
        Environment::Staging,
        "ap-south-1",
        {"t3.small", "t3.medium"},
        5,
        false,
        500.0
    };
}

EnvironmentPolicy productionPolicy() {
    return {
        Environment::Production,
        "ap-south-1",
        {"t3.medium", "t3.large"},
        10,
        true,
        2000.0
    };
}

Resource makeResource(
    const string& address,
    const string& instanceType,
    int count
) {
    return {
        address,
        {
            {"instance_type", instanceType},
            {"count", to_string(count)}
        }
    };
}

int main() {
    try {
        GovernanceEngine engine;

        engine.createWorkspace(
            "development", developmentPolicy()
        );
        engine.createWorkspace(
            "staging", stagingPolicy()
        );
        engine.createWorkspace(
            "production", productionPolicy()
        );

        engine.selectWorkspace("development");

        auto developmentPlan = engine.generatePlan({
            {
                "aws_instance.application",
                makeResource(
                    "aws_instance.application",
                    "t3.micro",
                    1
                )
            }
        });

        engine.printPlan(developmentPlan);
        engine.applyPlan(developmentPlan);

        engine.selectWorkspace("staging");

        auto stagingPlan = engine.generatePlan({
            {
                "aws_instance.application",
                makeResource(
                    "aws_instance.application",
                    "t3.small",
                    2
                )
            }
        });

        engine.printPlan(stagingPlan);
        engine.applyPlan(stagingPlan);

        engine.selectWorkspace("production");

        auto productionPlan = engine.generatePlan({
            {
                "aws_instance.application",
                makeResource(
                    "aws_instance.application",
                    "t3.medium",
                    3
                )
            }
        });

        engine.printPlan(productionPlan);

        try {
            engine.applyPlan(productionPlan, false);
        } catch (const WorkspaceException& error) {
            cout << "Rejected: " << error.what() << '\n';
        }

        engine.applyPlan(productionPlan, true);

        // An outdated plan must not overwrite newer state.
        engine.selectWorkspace("development");

        auto stalePlan = engine.generatePlan({
            {
                "aws_instance.application",
                makeResource(
                    "aws_instance.application",
                    "t3.small",
                    2
                )
            }
        });

        engine.applyPlan(engine.generatePlan({
            {
                "aws_instance.application",
                makeResource(
                    "aws_instance.application",
                    "t3.micro",
                    2
                )
            }
        }));

        try {
            engine.applyPlan(stalePlan);
        } catch (const WorkspaceException& error) {
            cout << "Stale plan rejected: "
                 << error.what() << '\n';
        }

        engine.report();

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

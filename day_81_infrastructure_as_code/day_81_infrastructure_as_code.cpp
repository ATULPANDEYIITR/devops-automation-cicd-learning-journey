#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

/*
 * Infrastructure as Code: C++17 Infrastructure Governance Engine
 *
 * Models:
 * - Declarative resource specifications
 * - Resource dependency graphs
 * - Topological deployment ordering
 * - Desired and actual infrastructure states
 * - Infrastructure planning
 * - Create, update, delete, and no-op actions
 * - Protected infrastructure
 * - Security policy evaluation
 * - Required deployment checks
 * - Merge-like deployment eligibility decisions
 * - State reconciliation
 */

enum class ResourceType {
    NETWORK,
    SERVER,
    STORAGE,
    FIREWALL
};

enum class Action {
    CREATE,
    UPDATE,
    DELETE,
    NO_OP
};

enum class ResourceStatus {
    DECLARED,
    ACTIVE,
    FAILED
};

struct Resource {
    string id;
    ResourceType type;
    map<string, string> properties;
    vector<string> dependencies;
    bool protectedResource = false;
    ResourceStatus status = ResourceStatus::DECLARED;
};

struct PlanItem {
    string resourceId;
    Action action;
    string reason;
};

struct PolicyResult {
    bool allowed;
    vector<string> violations;
};

class InfrastructureError : public runtime_error {
public:
    explicit InfrastructureError(const string& message)
        : runtime_error(message) {}
};

string actionName(Action action) {
    switch (action) {
        case Action::CREATE: return "CREATE";
        case Action::UPDATE: return "UPDATE";
        case Action::DELETE: return "DELETE";
        case Action::NO_OP: return "NO_OP";
    }

    return "UNKNOWN";
}

string typeName(ResourceType type) {
    switch (type) {
        case ResourceType::NETWORK: return "NETWORK";
        case ResourceType::SERVER: return "SERVER";
        case ResourceType::STORAGE: return "STORAGE";
        case ResourceType::FIREWALL: return "FIREWALL";
    }

    return "UNKNOWN";
}

class InfrastructureDefinition {
private:
    map<string, Resource> resources;

public:
    void addResource(const Resource& resource) {
        if (resource.id.empty()) {
            throw InfrastructureError("Resource ID cannot be empty");
        }

        if (resources.count(resource.id)) {
            throw InfrastructureError(
                "Duplicate resource: " + resource.id
            );
        }

        if (resource.type == ResourceType::SERVER) {
            auto cpu = resource.properties.find("cpu");
            auto memory = resource.properties.find("memory_gb");

            if (
                cpu == resource.properties.end() ||
                memory == resource.properties.end() ||
                stoi(cpu->second) <= 0 ||
                stoi(memory->second) <= 0
            ) {
                throw InfrastructureError(
                    "Invalid server capacity: " + resource.id
                );
            }
        }

        if (resource.type == ResourceType::STORAGE) {
            auto encryption = resource.properties.find("encrypted");

            if (
                encryption == resource.properties.end() ||
                encryption->second != "true"
            ) {
                throw InfrastructureError(
                    "Storage must be encrypted: " + resource.id
                );
            }
        }

        set<string> uniqueDependencies;

        for (const string& dependency : resource.dependencies) {
            if (dependency == resource.id) {
                throw InfrastructureError("Self-dependency detected");
            }

            if (!uniqueDependencies.insert(dependency).second) {
                throw InfrastructureError(
                    "Duplicate dependency detected"
                );
            }
        }

        resources.emplace(resource.id, resource);
    }

    const map<string, Resource>& getResources() const {
        return resources;
    }

    vector<string> deploymentOrder() const {
        map<string, int> indegree;
        map<string, vector<string>> dependents;

        for (const auto& [id, resource] : resources) {
            indegree[id] = 0;
        }

        for (const auto& [id, resource] : resources) {
            for (const string& dependency : resource.dependencies) {
                if (!resources.count(dependency)) {
                    throw InfrastructureError(
                        "Missing dependency: " + dependency
                    );
                }

                indegree[id]++;
                dependents[dependency].push_back(id);
            }
        }

        priority_queue<
            string,
            vector<string>,
            greater<string>
        > ready;

        for (const auto& [id, degree] : indegree) {
            if (degree == 0) {
                ready.push(id);
            }
        }

        vector<string> order;

        while (!ready.empty()) {
            string current = ready.top();
            ready.pop();

            order.push_back(current);

            for (const string& dependent : dependents[current]) {
                indegree[dependent]--;

                if (indegree[dependent] == 0) {
                    ready.push(dependent);
                }
            }
        }

        if (order.size() != resources.size()) {
            throw InfrastructureError(
                "Circular infrastructure dependency"
            );
        }

        return order;
    }
};

class InfrastructureState {
private:
    map<string, Resource> resources;
    unsigned long long revision = 0;

public:
    const map<string, Resource>& getResources() const {
        return resources;
    }

    unsigned long long getRevision() const {
        return revision;
    }

    void setResource(const Resource& resource) {
        resources[resource.id] = resource;
    }

    void removeResource(const string& id) {
        resources.erase(id);
    }

    void incrementRevision() {
        revision++;
    }

    void restore(
        const map<string, Resource>& snapshot,
        unsigned long long previousRevision
    ) {
        resources = snapshot;
        revision = previousRevision;
    }

    void externallyModify(
        const string& id,
        const string& property,
        const string& value
    ) {
        auto iterator = resources.find(id);

        if (iterator == resources.end()) {
            throw InfrastructureError("Unknown resource: " + id);
        }

        iterator->second.properties[property] = value;
    }
};

class SecurityPolicy {
public:
    PolicyResult evaluate(
        const InfrastructureDefinition& definition
    ) const {
        PolicyResult result{true, {}};

        for (const auto& [id, resource] :
             definition.getResources()) {

            if (resource.type == ResourceType::STORAGE) {
                auto encryption =
                    resource.properties.find("encrypted");

                if (
                    encryption == resource.properties.end() ||
                    encryption->second != "true"
                ) {
                    result.violations.push_back(
                        id + ": storage encryption required"
                    );
                }
            }

            if (resource.type == ResourceType::FIREWALL) {
                auto action =
                    resource.properties.find("default_action");

                if (
                    action == resource.properties.end() ||
                    action->second != "DENY"
                ) {
                    result.violations.push_back(
                        id + ": default firewall action must be DENY"
                    );
                }
            }

            if (resource.type == ResourceType::SERVER) {
                auto ssh =
                    resource.properties.find("public_ssh");

                if (
                    ssh != resource.properties.end() &&
                    ssh->second == "true"
                ) {
                    result.violations.push_back(
                        id + ": public SSH access is prohibited"
                    );
                }
            }
        }

        result.allowed = result.violations.empty();
        return result;
    }
};

class InfrastructurePlanner {
private:
    const InfrastructureDefinition& definition;
    const InfrastructureState& state;

    static bool sameProperties(
        const map<string, string>& first,
        const map<string, string>& second
    ) {
        return first == second;
    }

public:
    InfrastructurePlanner(
        const InfrastructureDefinition& definition,
        const InfrastructureState& state
    )
        : definition(definition), state(state) {}

    vector<PlanItem> createPlan() const {
        vector<PlanItem> plan;
        const auto& desired = definition.getResources();
        const auto& actual = state.getResources();

        for (const string& id : definition.deploymentOrder()) {
            const Resource& target = desired.at(id);

            auto current = actual.find(id);

            if (current == actual.end()) {
                plan.push_back({
                    id,
                    Action::CREATE,
                    "Resource does not exist"
                });
            } else if (!sameProperties(
                           target.properties,
                           current->second.properties
                       )) {
                plan.push_back({
                    id,
                    Action::UPDATE,
                    "Desired properties differ from actual state"
                });
            } else {
                plan.push_back({
                    id,
                    Action::NO_OP,
                    "Resource already matches desired state"
                });
            }
        }

        for (const auto& [id, resource] : actual) {
            if (!desired.count(id)) {
                if (resource.protectedResource) {
                    throw InfrastructureError(
                        "Protected resource cannot be deleted: " + id
                    );
                }

                plan.push_back({
                    id,
                    Action::DELETE,
                    "Resource absent from desired configuration"
                });
            }
        }

        set<string> deleting;

        for (const auto& item : plan) {
            if (item.action == Action::DELETE) {
                deleting.insert(item.resourceId);
            }
        }

        for (const string& id : deleting) {
            for (const auto& [dependentId, resource] : actual) {
                if (
                    dependentId != id &&
                    find(
                        resource.dependencies.begin(),
                        resource.dependencies.end(),
                        id
                    ) != resource.dependencies.end() &&
                    !deleting.count(dependentId)
                ) {
                    throw InfrastructureError(
                        "Cannot delete dependency " + id +
                        "; required by " + dependentId
                    );
                }
            }
        }

        return plan;
    }
};

class DeploymentEngine {
private:
    InfrastructureState& state;

public:
    explicit DeploymentEngine(InfrastructureState& state)
        : state(state) {}

    void apply(
        const vector<PlanItem>& plan,
        const InfrastructureDefinition& definition,
        const SecurityPolicy& policy
    ) {
        PolicyResult result = policy.evaluate(definition);

        if (!result.allowed) {
            string message = "Security policy rejected deployment:";

            for (const string& violation : result.violations) {
                message += "\n - " + violation;
            }

            throw InfrastructureError(message);
        }

        const auto snapshot = state.getResources();
        const auto previousRevision = state.getRevision();

        try {
            // Forward order provisions dependencies first.
            for (const auto& item : plan) {
                if (
                    item.action == Action::CREATE ||
                    item.action == Action::UPDATE
                ) {
                    Resource resource =
                        definition.getResources().at(item.resourceId);

                    resource.status = ResourceStatus::ACTIVE;

                    state.setResource(resource);
                }
            }

            // Reverse order removes dependent resources first.
            for (auto iterator = plan.rbegin();
                 iterator != plan.rend();
                 ++iterator) {

                if (iterator->action == Action::DELETE) {
                    state.removeResource(iterator->resourceId);
                }
            }

            bool changed = any_of(
                plan.begin(),
                plan.end(),
                [](const PlanItem& item) {
                    return item.action != Action::NO_OP;
                }
            );

            if (changed) {
                state.incrementRevision();
            }

        } catch (...) {
            state.restore(snapshot, previousRevision);
            throw;
        }
    }
};

InfrastructureDefinition buildInfrastructure() {
    InfrastructureDefinition definition;

    definition.addResource({
        "production-network",
        ResourceType::NETWORK,
        {
            {"cidr", "10.20.0.0/16"},
            {"region", "ap-south-1"}
        },
        {},
        true
    });

    definition.addResource({
        "application-server",
        ResourceType::SERVER,
        {
            {"cpu", "4"},
            {"memory_gb", "16"},
            {"public_ssh", "false"},
            {"image", "ubuntu-24.04"}
        },
        {"production-network"},
        false
    });

    definition.addResource({
        "application-storage",
        ResourceType::STORAGE,
        {
            {"size_gb", "100"},
            {"encrypted", "true"},
            {"versioning", "true"}
        },
        {},
        true
    });

    definition.addResource({
        "application-firewall",
        ResourceType::FIREWALL,
        {
            {"default_action", "DENY"},
            {"allow_https", "true"}
        },
        {"production-network"},
        false
    });

    return definition;
}

void printPlan(const vector<PlanItem>& plan) {
    cout << "\nINFRASTRUCTURE PLAN\n";
    cout << "---------------------------------------------\n";

    for (const auto& item : plan) {
        cout << actionName(item.action)
             << "  " << item.resourceId
             << "  " << item.reason << '\n';
    }
}

void runTests() {
    auto definition = buildInfrastructure();

    InfrastructureState state;
    SecurityPolicy policy;

    InfrastructurePlanner planner(definition, state);

    auto plan = planner.createPlan();

    if (plan.size() != 4) {
        throw InfrastructureError("Initial planning test failed");
    }

    DeploymentEngine engine(state);
    engine.apply(plan, definition, policy);

    if (state.getResources().size() != 4) {
        throw InfrastructureError("Deployment test failed");
    }

    auto secondPlan = planner.createPlan();

    if (!all_of(
        secondPlan.begin(),
        secondPlan.end(),
        [](const PlanItem& item) {
            return item.action == Action::NO_OP;
        }
    )) {
        throw InfrastructureError("Idempotency test failed");
    }

    // Simulate configuration drift outside the deployment engine.
    state.externallyModify(
        "application-server",
        "cpu",
        "8"
    );

    auto driftPlan = planner.createPlan();

    auto changed = find_if(
        driftPlan.begin(),
        driftPlan.end(),
        [](const PlanItem& item) {
            return item.resourceId == "application-server";
        }
    );

    if (
        changed == driftPlan.end() ||
        changed->action != Action::UPDATE
    ) {
        throw InfrastructureError("Drift detection failed");
    }

    engine.apply(driftPlan, definition, policy);

    auto repairedPlan = planner.createPlan();

    if (!all_of(
        repairedPlan.begin(),
        repairedPlan.end(),
        [](const PlanItem& item) {
            return item.action == Action::NO_OP;
        }
    )) {
        throw InfrastructureError("Reconciliation failed");
    }

    // Invalid firewall configuration must fail policy evaluation.
    InfrastructureDefinition invalid;

    invalid.addResource({
        "unsafe-firewall",
        ResourceType::FIREWALL,
        {
            {"default_action", "ALLOW"}
        },
        {},
        false
    });

    auto invalidResult = policy.evaluate(invalid);

    if (invalidResult.allowed) {
        throw InfrastructureError("Security policy test failed");
    }

    cout << "\nAll C++17 tests passed.\n";
}

int main() {
    try {
        auto definition = buildInfrastructure();

        InfrastructureState state;
        SecurityPolicy policy;

        InfrastructurePlanner planner(definition, state);
        DeploymentEngine engine(state);

        auto plan = planner.createPlan();

        printPlan(plan);

        engine.apply(plan, definition, policy);

        cout << "\nDeployment successful.\n";
        cout << "Resources: "
             << state.getResources().size() << '\n';

        cout << "State revision: "
             << state.getRevision() << '\n';

        cout << "\nSECOND DEPLOYMENT PLAN\n";

        auto secondPlan = planner.createPlan();
        printPlan(secondPlan);

        runTests();

    } catch (const exception& error) {
        cerr << "Infrastructure error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}

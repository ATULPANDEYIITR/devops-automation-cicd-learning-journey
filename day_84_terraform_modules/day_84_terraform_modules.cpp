#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

/*
 * Terraform Modules: Repository-independent infrastructure governance.
 *
 * This program implements a module release and deployment eligibility
 * engine using C++17.
 *
 * Capabilities:
 * - Module version management
 * - Module input contracts
 * - Source integrity
 * - Dependency validation
 * - Protected module releases
 * - Reviewer approval requirements
 * - Automated validation checks
 * - Deployment eligibility
 * - Atomic state updates
 */

using namespace std;

class ModuleException : public runtime_error {
public:
    explicit ModuleException(const string& message)
        : runtime_error(message) {}
};

struct Version {
    int major;
    int minor;
    int patch;

    bool operator<(const Version& other) const {
        return tie(major, minor, patch) <
               tie(other.major, other.minor, other.patch);
    }

    bool operator==(const Version& other) const {
        return tie(major, minor, patch) ==
               tie(other.major, other.minor, other.patch);
    }

    string str() const {
        return to_string(major) + "." +
               to_string(minor) + "." +
               to_string(patch);
    }
};

enum class InputType {
    STRING,
    INTEGER,
    BOOLEAN
};

enum class ResourceAction {
    CREATE,
    UPDATE,
    NO_CHANGE
};

enum class ReviewDecision {
    APPROVED,
    CHANGES_REQUESTED,
    COMMENTED
};

struct ModuleInput {
    string name;
    InputType type;
    bool required;
};

struct ModuleResource {
    string name;
    string type;
    map<string, string> configuration;
};

struct ModuleRelease {
    string name;
    Version version;
    string source;
    string checksum;
    bool immutable = true;
    vector<ModuleInput> inputs;
    vector<ModuleResource> resources;
    vector<string> dependencies;
};

struct ModuleCall {
    string instance;
    string module;
    Version requestedVersion;
    map<string, string> inputs;
};

struct Review {
    string reviewer;
    ReviewDecision decision;
};

struct StatusCheck {
    string name;
    bool passed;
};

struct BranchPolicy {
    int requiredApprovals = 2;
    bool requireChecks = true;
    bool requireImmutableSource = true;
    bool restrictDirectDeployment = true;
    bool requireResolvedDiscussions = true;
};

struct DeploymentRequest {
    string identifier;
    string targetEnvironment;
    vector<Review> reviews;
    vector<StatusCheck> checks;
    int unresolvedDiscussions = 0;
    bool sourceIsPinned = true;
    bool deploymentAuthorized = true;
};

struct PlannedResource {
    string address;
    map<string, string> configuration;
    ResourceAction action;
};

class ModuleRegistry {
private:
    map<string, map<Version, ModuleRelease>> releases;

public:
    void registerRelease(const ModuleRelease& release) {
        if (release.name.empty() || release.source.empty()) {
            throw ModuleException("Invalid module identity.");
        }

        if (release.checksum.size() != 64) {
            throw ModuleException("Module checksum must be SHA-256.");
        }

        auto& versions = releases[release.name];

        if (versions.count(release.version)) {
            throw ModuleException("Duplicate module release.");
        }

        versions.emplace(release.version, release);
    }

    const ModuleRelease& resolve(
        const string& name,
        const Version& version
    ) const {
        auto module = releases.find(name);

        if (module == releases.end()) {
            throw ModuleException("Module does not exist: " + name);
        }

        auto release = module->second.find(version);

        if (release == module->second.end()) {
            throw ModuleException(
                "Requested module version is unavailable."
            );
        }

        return release->second;
    }
};

class DependencyManager {
public:
    static vector<string> topologicalSort(
        const map<string, vector<string>>& graph
    ) {
        set<string> visited;
        set<string> active;
        vector<string> result;

        function<void(const string&)> visit =
            [&](const string& node) {
                if (active.count(node)) {
                    throw ModuleException(
                        "Circular module dependency: " + node
                    );
                }

                if (visited.count(node)) {
                    return;
                }

                active.insert(node);

                auto dependencies = graph.find(node);

                if (dependencies != graph.end()) {
                    for (const auto& dependency : dependencies->second) {
                        if (!graph.count(dependency)) {
                            throw ModuleException(
                                "Unknown dependency: " + dependency
                            );
                        }

                        visit(dependency);
                    }
                }

                active.erase(node);
                visited.insert(node);
                result.push_back(node);
            };

        for (const auto& entry : graph) {
            visit(entry.first);
        }

        return result;
    }
};

class GovernanceEngine {
private:
    const ModuleRegistry& registry;
    BranchPolicy policy;

public:
    GovernanceEngine(
        const ModuleRegistry& moduleRegistry,
        BranchPolicy branchPolicy
    ) : registry(moduleRegistry), policy(branchPolicy) {}

    bool eligible(const DeploymentRequest& request) const {
        if (!request.deploymentAuthorized) {
            return false;
        }

        if (request.targetEnvironment.empty()) {
            return false;
        }

        if (
            policy.requireImmutableSource &&
            !request.sourceIsPinned
        ) {
            return false;
        }

        if (
            policy.requireResolvedDiscussions &&
            request.unresolvedDiscussions > 0
        ) {
            return false;
        }

        set<string> approvedReviewers;

        for (const auto& review : request.reviews) {
            if (review.decision == ReviewDecision::APPROVED) {
                approvedReviewers.insert(review.reviewer);
            } else if (
                review.decision == ReviewDecision::CHANGES_REQUESTED
            ) {
                // A reviewer cannot simultaneously count as approved
                // and have an outstanding change request.
                approvedReviewers.erase(review.reviewer);
            }
        }

        if (
            static_cast<int>(approvedReviewers.size()) <
            policy.requiredApprovals
        ) {
            return false;
        }

        if (policy.requireChecks) {
            if (request.checks.empty()) {
                return false;
            }

            for (const auto& check : request.checks) {
                if (!check.passed) {
                    return false;
                }
            }
        }

        return true;
    }
};

class InfrastructureEngine {
private:
    const ModuleRegistry& registry;

    map<string, map<string, string>> state;

    static void validateInput(
        const ModuleInput& definition,
        const map<string, string>& supplied
    ) {
        auto found = supplied.find(definition.name);

        if (found == supplied.end()) {
            if (definition.required) {
                throw ModuleException(
                    "Missing required input: " + definition.name
                );
            }
            return;
        }

        if (
            definition.type == InputType::INTEGER &&
            found->second.find_first_not_of("-0123456789") !=
                string::npos
        ) {
            throw ModuleException(
                "Input must be an integer: " + definition.name
            );
        }

        if (
            definition.type == InputType::BOOLEAN &&
            found->second != "true" &&
            found->second != "false"
        ) {
            throw ModuleException(
                "Input must be boolean: " + definition.name
            );
        }
    }

public:
    explicit InfrastructureEngine(const ModuleRegistry& moduleRegistry)
        : registry(moduleRegistry) {}

    vector<PlannedResource> plan(
        const vector<ModuleCall>& calls
    ) const {
        map<string, const ModuleRelease*> resolved;
        map<string, vector<string>> graph;

        for (const auto& call : calls) {
            if (resolved.count(call.instance)) {
                throw ModuleException(
                    "Duplicate module instance: " + call.instance
                );
            }

            const auto& release = registry.resolve(
                call.module,
                call.requestedVersion
            );

            resolved[call.instance] = &release;
            graph[call.instance] = release.dependencies;

            set<string> allowedInputs;

            for (const auto& input : release.inputs) {
                allowedInputs.insert(input.name);
                validateInput(input, call.inputs);
            }

            for (const auto& input : call.inputs) {
                if (!allowedInputs.count(input.first)) {
                    throw ModuleException(
                        "Unexpected module input: " + input.first
                    );
                }
            }
        }

        const auto order = DependencyManager::topologicalSort(graph);

        vector<PlannedResource> plans;

        for (const auto& instance : order) {
            const auto& release = *resolved.at(instance);

            for (const auto& resource : release.resources) {
                const string address =
                    "module." + instance + "." +
                    resource.type + "." + resource.name;

                auto configuration = resource.configuration;

                const auto current = state.find(address);

                ResourceAction action = ResourceAction::CREATE;

                if (current != state.end()) {
                    action = current->second == configuration
                        ? ResourceAction::NO_CHANGE
                        : ResourceAction::UPDATE;
                }

                plans.push_back({
                    address,
                    configuration,
                    action
                });
            }
        }

        return plans;
    }

    void apply(const vector<PlannedResource>& plans) {
        // Use a staged copy to avoid partial state changes.
        auto staged = state;

        for (const auto& plan : plans) {
            if (plan.action == ResourceAction::NO_CHANGE) {
                continue;
            }

            staged[plan.address] = plan.configuration;
        }

        state.swap(staged);
    }

    vector<string> detectDrift(
        const map<string, map<string, string>>& actual
    ) const {
        vector<string> drift;

        for (const auto& resource : state) {
            auto current = actual.find(resource.first);

            if (
                current == actual.end() ||
                current->second != resource.second
            ) {
                drift.push_back(resource.first);
            }
        }

        return drift;
    }

    size_t resourceCount() const {
        return state.size();
    }
};

string actionName(ResourceAction action) {
    switch (action) {
        case ResourceAction::CREATE:
            return "CREATE";
        case ResourceAction::UPDATE:
            return "UPDATE";
        case ResourceAction::NO_CHANGE:
            return "NO_CHANGE";
    }

    return "UNKNOWN";
}

int main() {
    try {
        ModuleRegistry registry;

        ModuleRelease network{
            "network",
            {1, 2, 0},
            "registry.example.com/platform/network",
            string(64, 'a'),
            true,
            {
                {"environment", InputType::STRING, true},
                {"cidr", InputType::STRING, true}
            },
            {
                {
                    "main",
                    "aws_vpc",
                    {
                        {"enable_dns_support", "true"},
                        {"enable_dns_hostnames", "true"}
                    }
                }
            },
            {}
        };

        ModuleRelease application{
            "application",
            {2, 1, 0},
            "registry.example.com/platform/application",
            string(64, 'b'),
            true,
            {
                {"environment", InputType::STRING, true},
                {"instance_count", InputType::INTEGER, true}
            },
            {
                {
                    "web",
                    "aws_instance",
                    {
                        {"encrypted_volume", "true"},
                        {"monitoring", "true"}
                    }
                }
            },
            {"network"}
        };

        registry.registerRelease(network);
        registry.registerRelease(application);

        cout << "TERRAFORM MODULE GOVERNANCE ENGINE\n";
        cout << "===================================\n\n";

        BranchPolicy policy;
        policy.requiredApprovals = 2;
        policy.requireChecks = true;

        GovernanceEngine governance(registry, policy);

        DeploymentRequest deployment{
            "deploy-001",
            "production",
            {
                {"reviewer-alice", ReviewDecision::APPROVED},
                {"reviewer-bob", ReviewDecision::APPROVED}
            },
            {
                {"terraform_validate", true},
                {"terraform_plan", true},
                {"security_scan", true}
            },
            0,
            true,
            true
        };

        cout << "Deployment eligibility: "
             << (governance.eligible(deployment) ? "APPROVED" : "BLOCKED")
             << "\n\n";

        InfrastructureEngine engine(registry);

        vector<ModuleCall> calls = {
            {
                "network",
                "network",
                {1, 2, 0},
                {
                    {"environment", "production"},
                    {"cidr", "10.40.0.0/16"}
                }
            },
            {
                "application",
                "application",
                {2, 1, 0},
                {
                    {"environment", "production"},
                    {"instance_count", "3"}
                }
            }
        };

        auto plans = engine.plan(calls);

        cout << "Infrastructure plan:\n";

        for (const auto& plan : plans) {
            cout << actionName(plan.action)
                 << " " << plan.address << "\n";
        }

        if (governance.eligible(deployment)) {
            engine.apply(plans);
            cout << "\nDeployment applied.\n";
        } else {
            cout << "\nDeployment blocked by policy.\n";
        }

        cout << "Managed resources: "
             << engine.resourceCount() << "\n";

        deployment.checks[1].passed = false;

        cout << "\nAfter failed Terraform plan check: "
             << (governance.eligible(deployment)
                     ? "APPROVED"
                     : "BLOCKED")
             << "\n";

        deployment.checks[1].passed = true;
        deployment.unresolvedDiscussions = 1;

        cout << "After unresolved discussion: "
             << (governance.eligible(deployment)
                     ? "APPROVED"
                     : "BLOCKED")
             << "\n";

        // Test circular dependencies.
        try {
            DependencyManager::topologicalSort({
                {"network", {"application"}},
                {"application", {"network"}}
            });
        } catch (const ModuleException& error) {
            cout << "\nDependency validation: "
                 << error.what() << "\n";
        }

    } catch (const exception& error) {
        cerr << "Execution error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}

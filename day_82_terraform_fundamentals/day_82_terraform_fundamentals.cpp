#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Terraform Fundamentals: C++17 Infrastructure Engine.
 *
 * Implements:
 * - Provider configuration
 * - Typed variable definitions
 * - Resource declarations
 * - Dependency graph traversal
 * - Infrastructure planning
 * - Resource lifecycle management
 * - State storage
 * - Output references
 * - Failure recovery
 *
 * Compile:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic terraform.cpp -o terraform
 */

class TerraformError : public std::runtime_error {
public:
    explicit TerraformError(const std::string& message)
        : std::runtime_error(message) {}
};

enum class ResourceAction {
    Create,
    Update,
    NoChange,
    Destroy
};

enum class ResourceStatus {
    Pending,
    Planned,
    Created,
    Updated,
    Destroyed,
    Failed
};

std::string actionName(ResourceAction action) {
    switch (action) {
        case ResourceAction::Create: return "CREATE";
        case ResourceAction::Update: return "UPDATE";
        case ResourceAction::NoChange: return "NO_CHANGE";
        case ResourceAction::Destroy: return "DESTROY";
    }

    throw TerraformError("Unknown resource action.");
}

struct Provider {
    std::string name;
    std::string region;
    std::string version;
    bool workloadIdentity = false;

    void validate() const {
        if (name.empty() || region.empty() || version.empty()) {
            throw TerraformError("Incomplete provider configuration.");
        }

        if (region.find(' ') != std::string::npos) {
            throw TerraformError("Invalid provider region.");
        }

        const auto firstDot = version.find('.');
        const auto secondDot = version.find('.', firstDot + 1);

        if (firstDot == std::string::npos ||
            secondDot == std::string::npos) {
            throw TerraformError("Provider version must be major.minor.patch.");
        }
    }
};

struct Variable {
    std::string name;
    std::string defaultValue;
    bool required = false;
    bool sensitive = false;
    std::function<bool(const std::string&)> validator;
};

class VariableManager {
private:
    std::map<std::string, Variable> definitions;

public:
    void define(Variable variable) {
        if (variable.name.empty()) {
            throw TerraformError("Variable name cannot be empty.");
        }

        if (definitions.count(variable.name)) {
            throw TerraformError("Duplicate variable definition.");
        }

        definitions.emplace(variable.name, std::move(variable));
    }

    std::map<std::string, std::string> resolve(
        const std::map<std::string, std::string>& supplied
    ) const {
        for (const auto& [name, value] : supplied) {
            (void)value;

            if (!definitions.count(name)) {
                throw TerraformError("Unknown variable: " + name);
            }
        }

        std::map<std::string, std::string> resolved;

        for (const auto& [name, definition] : definitions) {
            auto it = supplied.find(name);
            std::string value;

            if (it != supplied.end()) {
                value = it->second;
            } else if (definition.required) {
                throw TerraformError("Missing required variable: " + name);
            } else {
                value = definition.defaultValue;
            }

            if (definition.validator && !definition.validator(value)) {
                throw TerraformError("Invalid variable: " + name);
            }

            resolved[name] = value;
        }

        return resolved;
    }

    void printSafe(
        const std::map<std::string, std::string>& values
    ) const {
        for (const auto& [name, value] : values) {
            const auto& definition = definitions.at(name);

            std::cout << name << " = "
                      << (definition.sensitive ? "[REDACTED]" : value)
                      << '\n';
        }
    }
};

struct Resource {
    std::string name;
    std::string type;
    std::string provider;
    std::map<std::string, std::string> attributes;
    std::vector<std::string> dependencies;
    ResourceStatus status = ResourceStatus::Pending;

    std::string address() const {
        return type + "." + name;
    }

    void validate() const {
        if (name.empty() || type.empty() || provider.empty()) {
            throw TerraformError("Resource identity is incomplete.");
        }

        if (std::find(
                dependencies.begin(),
                dependencies.end(),
                address()
            ) != dependencies.end()) {
            throw TerraformError("Resource cannot depend on itself.");
        }
    }
};

struct StateRecord {
    std::string id;
    std::string address;
    std::string provider;
    std::map<std::string, std::string> attributes;
};

struct PlanEntry {
    std::string address;
    ResourceAction action;
    std::map<std::string, std::string> desired;
};

class InfrastructureState {
private:
    std::map<std::string, StateRecord> records;

public:
    const StateRecord* get(const std::string& address) const {
        auto it = records.find(address);

        if (it == records.end()) {
            return nullptr;
        }

        return &it->second;
    }

    void save(const StateRecord& record) {
        records[record.address] = record;
    }

    void erase(const std::string& address) {
        records.erase(address);
    }

    const std::map<std::string, StateRecord>& all() const {
        return records;
    }

    void restore(
        const std::map<std::string, StateRecord>& snapshot
    ) {
        records = snapshot;
    }

    void print() const {
        for (const auto& [address, record] : records) {
            std::cout << address << "\n"
                      << "  ID: " << record.id << "\n"
                      << "  Provider: " << record.provider << "\n";

            for (const auto& [key, value] : record.attributes) {
                std::cout << "  " << key << " = " << value << "\n";
            }
        }
    }
};

class InfrastructureEngine {
private:
    Provider provider;
    std::map<std::string, std::string> variables;
    std::map<std::string, Resource> resources;
    InfrastructureState state;

    std::string interpolate(const std::string& input) const {
        const std::string prefix = "${var.";
        std::string result = input;
        std::size_t position = 0;

        while ((position = result.find(prefix, position)) !=
               std::string::npos) {
            const std::size_t end = result.find('}', position);

            if (end == std::string::npos) {
                throw TerraformError("Unclosed variable reference.");
            }

            const std::size_t start = position + prefix.size();
            const std::string variableName =
                result.substr(start, end - start);

            auto it = variables.find(variableName);

            if (it == variables.end()) {
                throw TerraformError(
                    "Unknown variable reference: " + variableName
                );
            }

            result.replace(
                position,
                end - position + 1,
                it->second
            );

            position += it->second.size();
        }

        return result;
    }

    std::map<std::string, std::string> resolveAttributes(
        const Resource& resource
    ) const {
        std::map<std::string, std::string> result;

        for (const auto& [key, value] : resource.attributes) {
            result[key] = interpolate(value);
        }

        return result;
    }

    static std::string makeId(
        const std::string& address,
        const std::map<std::string, std::string>& attributes
    ) {
        std::ostringstream serialized;
        serialized << address;

        for (const auto& [key, value] : attributes) {
            serialized << "|" << key << "=" << value;
        }

        // Stable demonstration identifier. A production provider must
        // return the actual identifier assigned by its API.
        return "tf-" + std::to_string(
            std::hash<std::string>{}(serialized.str())
        );
    }

public:
    InfrastructureEngine(
        Provider providerConfig,
        std::map<std::string, std::string> resolvedVariables
    )
        : provider(std::move(providerConfig)),
          variables(std::move(resolvedVariables)) {
        provider.validate();
    }

    void addResource(Resource resource) {
        resource.validate();

        if (resource.provider != provider.name) {
            throw TerraformError(
                "Resource references an unconfigured provider."
            );
        }

        const std::string address = resource.address();

        if (resources.count(address)) {
            throw TerraformError("Duplicate resource: " + address);
        }

        resources.emplace(address, std::move(resource));
    }

    std::vector<std::string> dependencyOrder() const {
        std::set<std::string> visited;
        std::set<std::string> active;
        std::vector<std::string> order;

        std::function<void(const std::string&)> visit =
            [&](const std::string& address) {
                if (active.count(address)) {
                    throw TerraformError(
                        "Circular dependency at " + address
                    );
                }

                if (visited.count(address)) {
                    return;
                }

                auto it = resources.find(address);

                if (it == resources.end()) {
                    throw TerraformError(
                        "Unknown dependency: " + address
                    );
                }

                active.insert(address);

                for (const auto& dependency :
                     it->second.dependencies) {
                    visit(dependency);
                }

                active.erase(address);
                visited.insert(address);
                order.push_back(address);
            };

        for (const auto& [address, resource] : resources) {
            (void)resource;
            visit(address);
        }

        return order;
    }

    std::vector<PlanEntry> plan() {
        std::vector<PlanEntry> result;

        for (const auto& address : dependencyOrder()) {
            Resource& resource = resources.at(address);
            auto desired = resolveAttributes(resource);

            const StateRecord* existing = state.get(address);

            ResourceAction action;

            if (!existing) {
                action = ResourceAction::Create;
            } else if (existing->attributes == desired) {
                action = ResourceAction::NoChange;
            } else {
                action = ResourceAction::Update;
            }

            resource.status = ResourceStatus::Planned;

            result.push_back({
                address,
                action,
                std::move(desired)
            });
        }

        for (const auto& [address, record] : state.all()) {
            (void)record;

            if (!resources.count(address)) {
                result.push_back({
                    address,
                    ResourceAction::Destroy,
                    {}
                });
            }
        }

        return result;
    }

    void apply(const std::vector<PlanEntry>& planEntries) {
        const auto snapshot = state.all();

        try {
            for (const auto& entry : planEntries) {
                if (entry.action == ResourceAction::Destroy) {
                    state.erase(entry.address);
                    std::cout << "Destroyed " << entry.address << '\n';
                    continue;
                }

                if (entry.action == ResourceAction::NoChange) {
                    std::cout << "Unchanged " << entry.address << '\n';
                    continue;
                }

                auto it = resources.find(entry.address);

                if (it == resources.end()) {
                    throw TerraformError(
                        "Missing resource configuration."
                    );
                }

                if (entry.desired.count("simulate_failure") &&
                    entry.desired.at("simulate_failure") == "true") {
                    throw TerraformError(
                        "Simulated provider failure at " + entry.address
                    );
                }

                auto attributes = entry.desired;
                attributes.erase("simulate_failure");

                StateRecord record{
                    makeId(entry.address, attributes),
                    entry.address,
                    provider.name,
                    attributes
                };

                state.save(record);

                it->second.status =
                    entry.action == ResourceAction::Create
                    ? ResourceStatus::Created
                    : ResourceStatus::Updated;

                std::cout << actionName(entry.action)
                          << " " << entry.address << '\n';
            }
        } catch (...) {
            state.restore(snapshot);

            for (auto& [address, resource] : resources) {
                (void)address;
                resource.status = ResourceStatus::Failed;
            }

            throw;
        }
    }

    std::map<std::string, std::string> outputs(
        const std::map<
            std::string,
            std::pair<std::string, std::string>
        >& definitions
    ) const {
        std::map<std::string, std::string> result;

        for (const auto& [outputName, reference] : definitions) {
            const auto* record = state.get(reference.first);

            if (!record) {
                throw TerraformError(
                    "Output references a missing resource: " +
                    reference.first
                );
            }

            auto attribute = record->attributes.find(reference.second);

            if (attribute == record->attributes.end()) {
                throw TerraformError(
                    "Unknown output attribute: " + reference.second
                );
            }

            result[outputName] = attribute->second;
        }

        return result;
    }

    void printState() const {
        state.print();
    }

    std::size_t resourceCount() const {
        return state.all().size();
    }
};

int main() {
    try {
        VariableManager manager;

        manager.define({
            "environment",
            "development",
            false,
            false,
            [](const std::string& value) {
                return value == "development" ||
                       value == "staging" ||
                       value == "production";
            }
        });

        manager.define({
            "instance_type",
            "t3.small",
            false,
            false,
            [](const std::string& value) {
                return value.find('.') != std::string::npos;
            }
        });

        manager.define({
            "instance_count",
            "2",
            false,
            false,
            [](const std::string& value) {
                try {
                    const int count = std::stoi(value);
                    return count >= 1 && count <= 10;
                } catch (...) {
                    return false;
                }
            }
        });

        manager.define({
            "database_password",
            "",
            true,
            true,
            [](const std::string& value) {
                return value.size() >= 12;
            }
        });

        auto variables = manager.resolve({
            {"environment", "development"},
            {"instance_type", "t3.small"},
            {"instance_count", "2"},
            {"database_password", "SecurePassword123!"}
        });

        std::cout << "=== PROVIDER CONFIGURATION ===\n";

        Provider aws{
            "aws",
            "ap-south-1",
            "5.80.0",
            false
        };

        aws.validate();

        std::cout << "Provider: " << aws.name << '\n';
        std::cout << "Region: " << aws.region << '\n';
        std::cout << "Version: " << aws.version << '\n';

        std::cout << "\n=== INPUT VARIABLES ===\n";
        manager.printSafe(variables);

        InfrastructureEngine engine(aws, variables);

        engine.addResource({
            "network",
            "aws_vpc",
            "aws",
            {
                {"cidr_block", "10.0.0.0/16"},
                {"environment", "${var.environment}"}
            },
            {}
        });

        engine.addResource({
            "application",
            "aws_instance",
            "aws",
            {
                {"instance_type", "${var.instance_type}"},
                {"instance_count", "${var.instance_count}"},
                {"environment", "${var.environment}"}
            },
            {"aws_vpc.network"}
        });

        engine.addResource({
            "database",
            "aws_db_instance",
            "aws",
            {
                {"engine", "postgres"},
                {"environment", "${var.environment}"},
                {"password_configured", "true"}
            },
            {"aws_vpc.network"}
        });

        std::cout << "\n=== DEPENDENCY ORDER ===\n";

        for (const auto& address : engine.dependencyOrder()) {
            std::cout << "-> " << address << '\n';
        }

        std::cout << "\n=== INFRASTRUCTURE PLAN ===\n";

        const auto plan = engine.plan();

        for (const auto& entry : plan) {
            std::cout << actionName(entry.action)
                      << " " << entry.address << '\n';
        }

        std::cout << "\n=== APPLY ===\n";
        engine.apply(plan);

        std::cout << "\n=== STATE ===\n";
        engine.printState();

        std::cout << "\n=== OUTPUTS ===\n";

        const auto result = engine.outputs({
            {
                "network_cidr",
                {"aws_vpc.network", "cidr_block"}
            },
            {
                "application_instance_type",
                {"aws_instance.application", "instance_type"}
            }
        });

        for (const auto& [name, value] : result) {
            std::cout << name << " = " << value << '\n';
        }

        std::cout << "\n=== SECOND PLAN ===\n";

        for (const auto& entry : engine.plan()) {
            std::cout << actionName(entry.action)
                      << " " << entry.address << '\n';
        }

        std::cout << "\n=== VALIDATION FAILURE ===\n";

        try {
            manager.resolve({
                {"environment", "invalid"},
                {"instance_type", "t3.small"},
                {"instance_count", "20"},
                {"database_password", "short"}
            });
        } catch (const TerraformError& error) {
            std::cout << "Expected error: " << error.what() << '\n';
        }

        std::cout << "\n=== FAILURE ROLLBACK ===\n";

        InfrastructureEngine failingEngine(aws, variables);

        failingEngine.addResource({
            "valid",
            "aws_vpc",
            "aws",
            {{"cidr_block", "10.1.0.0/16"}},
            {}
        });

        failingEngine.addResource({
            "invalid",
            "aws_instance",
            "aws",
            {{"simulate_failure", "true"}},
            {}
        });

        try {
            failingEngine.apply(failingEngine.plan());
        } catch (const TerraformError& error) {
            std::cout << "Expected provider error: "
                      << error.what() << '\n';
        }

        std::cout << "Resources after rollback: "
                  << failingEngine.resourceCount() << '\n';

        std::cout << "\nExecution completed.\n";

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

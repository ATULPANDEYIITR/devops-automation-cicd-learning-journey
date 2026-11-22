#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Terraform State Governance Engine
 *
 * C++17 implementation.
 *
 * Capabilities:
 * - Terraform resource state modeling
 * - State lineage and serial validation
 * - Local and remote backend simulation
 * - Workspace-specific state
 * - Exclusive state locking
 * - State snapshots
 * - Optimistic concurrency
 * - Plan generation
 * - Apply operations
 * - Infrastructure drift detection
 * - State migration
 * - Sensitive attribute redaction
 *
 * Compile:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic terraform_state.cpp -o terraform_state
 */

namespace terraform {


// ============================================================
// EXCEPTIONS
// ============================================================

class StateException : public std::runtime_error {
public:
    explicit StateException(const std::string& message)
        : std::runtime_error(message) {}
};

class LockException : public StateException {
public:
    explicit LockException(const std::string& message)
        : StateException(message) {}
};

class ConflictException : public StateException {
public:
    explicit ConflictException(const std::string& message)
        : StateException(message) {}
};

class ValidationException : public StateException {
public:
    explicit ValidationException(const std::string& message)
        : StateException(message) {}
};


// ============================================================
// ENUMERATIONS
// ============================================================

enum class BackendType {
    Local,
    Remote
};

enum class Operation {
    Plan,
    Apply,
    Refresh,
    Migration
};

enum class Action {
    Create,
    Update,
    Delete
};

std::string toString(Action action) {

    switch (action) {
        case Action::Create:
            return "CREATE";

        case Action::Update:
            return "UPDATE";

        case Action::Delete:
            return "DELETE";
    }

    throw ValidationException("Unknown action.");
}


// ============================================================
// UTILITY FUNCTIONS
// ============================================================

std::string generateId() {

    static std::uint64_t counter = 1000;

    return "state-" + std::to_string(++counter);
}

std::string currentTimestamp() {

    auto now = std::chrono::system_clock::now();

    auto time = std::chrono::system_clock::to_time_t(now);

    std::tm utc{};

#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif

    std::ostringstream output;

    output << std::put_time(
        &utc,
        "%Y-%m-%dT%H:%M:%SZ"
    );

    return output.str();
}

void validateWorkspace(const std::string& workspace) {

    if (workspace.empty()) {
        throw ValidationException(
            "Workspace name cannot be empty."
        );
    }

    for (char c : workspace) {

        if (
            !std::isalnum(static_cast<unsigned char>(c)) &&
            c != '_' &&
            c != '-'
        ) {
            throw ValidationException(
                "Invalid workspace name."
            );
        }
    }
}


// ============================================================
// RESOURCE
// ============================================================

struct Resource {

    std::string address;
    std::string type;
    std::string provider;
    std::string id;

    std::map<std::string, std::string> attributes;

    std::set<std::string> sensitiveAttributes;

    void validate() const {

        if (
            address.empty() ||
            address.find('.') == std::string::npos
        ) {
            throw ValidationException(
                "Invalid resource address."
            );
        }

        if (
            type.empty() ||
            provider.empty() ||
            id.empty()
        ) {
            throw ValidationException(
                "Resource metadata is incomplete."
            );
        }

        for (const auto& key : sensitiveAttributes) {

            if (attributes.find(key) == attributes.end()) {
                throw ValidationException(
                    "Unknown sensitive attribute."
                );
            }
        }
    }

    void display() const {

        std::cout << "  " << address
                  << " [" << type << "]"
                  << " ID=" << id << "\n";

        for (const auto& [key, value] : attributes) {

            std::cout << "    " << key << " = ";

            if (sensitiveAttributes.count(key)) {
                std::cout << "[REDACTED]";
            } else {
                std::cout << value;
            }

            std::cout << "\n";
        }
    }

    bool equivalent(const Resource& other) const {

        return address == other.address &&
               type == other.type &&
               provider == other.provider &&
               id == other.id &&
               attributes == other.attributes;
    }
};


// ============================================================
// OUTPUT
// ============================================================

struct StateOutput {

    std::string name;
    std::string value;
    bool sensitive = false;

    void display() const {

        std::cout << name << " = ";

        if (sensitive) {
            std::cout << "[REDACTED]";
        } else {
            std::cout << value;
        }

        std::cout << "\n";
    }
};


// ============================================================
// TERRAFORM STATE
// ============================================================

struct TerraformState {

    int version = 4;

    std::string terraformVersion = "1.10.0";

    std::string lineage = generateId();

    std::uint64_t serial = 0;

    std::string workspace = "default";

    std::map<std::string, Resource> resources;

    std::map<std::string, StateOutput> outputs;

    std::string updatedAt = currentTimestamp();

    void validate() const {

        if (version != 4) {
            throw ValidationException(
                "Unsupported state format version."
            );
        }

        validateWorkspace(workspace);

        if (lineage.empty()) {
            throw ValidationException(
                "State lineage cannot be empty."
            );
        }

        for (const auto& [address, resource] : resources) {

            resource.validate();

            if (address != resource.address) {
                throw ValidationException(
                    "Resource address mismatch."
                );
            }
        }
    }

    void display() const {

        std::cout << "\nSTATE DETAILS\n";

        std::cout << "Workspace: " << workspace << "\n";
        std::cout << "Lineage: " << lineage << "\n";
        std::cout << "Serial: " << serial << "\n";
        std::cout << "Resources: " << resources.size() << "\n";
        std::cout << "Updated: " << updatedAt << "\n";

        for (const auto& [address, resource] : resources) {
            resource.display();
        }
    }
};


// ============================================================
// STATE LOCK
// ============================================================

struct StateLock {

    std::string id;
    std::string workspace;
    std::string owner;
    std::string operation;
    std::string createdAt;
};


// ============================================================
// BACKEND INTERFACE
// ============================================================

class StateBackend {

public:

    virtual ~StateBackend() = default;

    virtual TerraformState read(
        const std::string& workspace
    ) = 0;

    virtual void write(
        const std::string& workspace,
        const TerraformState& state,
        std::uint64_t expectedSerial
    ) = 0;

    virtual StateLock acquireLock(
        const std::string& workspace,
        const std::string& operation,
        const std::string& owner
    ) = 0;

    virtual void releaseLock(
        const std::string& workspace,
        const std::string& lockId
    ) = 0;
};


// ============================================================
// REMOTE STATE BACKEND
// ============================================================

class RemoteStateBackend : public StateBackend {

private:

    mutable std::mutex mutex;

    std::unordered_map<
        std::string,
        TerraformState
    > states;

    std::unordered_map<
        std::string,
        StateLock
    > locks;

    std::unordered_map<
        std::string,
        std::vector<TerraformState>
    > history;

public:

    TerraformState read(
        const std::string& workspace
    ) override {

        validateWorkspace(workspace);

        std::lock_guard<std::mutex> guard(mutex);

        auto iterator = states.find(workspace);

        if (iterator == states.end()) {

            TerraformState state;
            state.workspace = workspace;

            return state;
        }

        return iterator->second;
    }

    void write(
        const std::string& workspace,
        const TerraformState& state,
        std::uint64_t expectedSerial
    ) override {

        state.validate();

        std::lock_guard<std::mutex> guard(mutex);

        auto iterator = states.find(workspace);

        TerraformState current;

        if (iterator != states.end()) {
            current = iterator->second;
        } else {
            current.workspace = workspace;
        }

        if (current.serial != expectedSerial) {
            throw ConflictException(
                "Remote state serial conflict."
            );
        }

        if (current.lineage != state.lineage) {
            throw ConflictException(
                "Remote state lineage conflict."
            );
        }

        if (state.serial != expectedSerial + 1) {
            throw ValidationException(
                "Invalid serial transition."
            );
        }

        if (state.workspace != workspace) {
            throw ValidationException(
                "Workspace mismatch."
            );
        }

        TerraformState published = state;

        published.updatedAt = currentTimestamp();

        states[workspace] = published;

        history[workspace].push_back(published);
    }

    StateLock acquireLock(
        const std::string& workspace,
        const std::string& operation,
        const std::string& owner
    ) override {

        validateWorkspace(workspace);

        if (owner.empty()) {
            throw ValidationException(
                "Lock owner is required."
            );
        }

        std::lock_guard<std::mutex> guard(mutex);

        if (locks.count(workspace)) {

            throw LockException(
                "Workspace already locked by " +
                locks.at(workspace).owner
            );
        }

        StateLock lock{
            generateId(),
            workspace,
            owner,
            operation,
            currentTimestamp()
        };

        locks[workspace] = lock;

        return lock;
    }

    void releaseLock(
        const std::string& workspace,
        const std::string& lockId
    ) override {

        std::lock_guard<std::mutex> guard(mutex);

        auto iterator = locks.find(workspace);

        if (iterator == locks.end()) {
            throw LockException(
                "No active workspace lock."
            );
        }

        if (iterator->second.id != lockId) {
            throw LockException(
                "Lock identifier mismatch."
            );
        }

        locks.erase(iterator);
    }

    std::vector<TerraformState> getHistory(
        const std::string& workspace
    ) {

        std::lock_guard<std::mutex> guard(mutex);

        auto iterator = history.find(workspace);

        if (iterator == history.end()) {
            return {};
        }

        return iterator->second;
    }
};


// ============================================================
// INFRASTRUCTURE INVENTORY
// ============================================================

class InfrastructureInventory {

private:

    std::map<std::string, Resource> resources;

public:

    void create(const Resource& resource) {

        resource.validate();

        if (resources.count(resource.address)) {
            throw StateException(
                "Infrastructure resource already exists."
            );
        }

        resources[resource.address] = resource;
    }

    void update(
        const std::string& address,
        const std::map<std::string, std::string>& attributes
    ) {

        auto iterator = resources.find(address);

        if (iterator == resources.end()) {
            throw StateException(
                "Infrastructure resource not found."
            );
        }

        for (const auto& [key, value] : attributes) {
            iterator->second.attributes[key] = value;
        }
    }

    void erase(const std::string& address) {

        if (resources.erase(address) == 0) {
            throw StateException(
                "Cannot delete missing infrastructure resource."
            );
        }
    }

    std::optional<Resource> find(
        const std::string& address
    ) const {

        auto iterator = resources.find(address);

        if (iterator == resources.end()) {
            return std::nullopt;
        }

        return iterator->second;
    }

    const std::map<std::string, Resource>& all() const {
        return resources;
    }
};


// ============================================================
// PLAN
// ============================================================

struct PlannedChange {

    std::string address;

    Action action;

    std::optional<Resource> before;

    std::optional<Resource> after;
};

struct TerraformPlan {

    std::string workspace;

    std::string lineage;

    std::uint64_t baseSerial = 0;

    std::vector<PlannedChange> changes;
};


// ============================================================
// PLAN ENGINE
// ============================================================

class PlanEngine {

public:

    static TerraformPlan generate(
        const TerraformState& state,
        const std::map<std::string, Resource>& desired
    ) {

        state.validate();

        TerraformPlan plan;

        plan.workspace = state.workspace;
        plan.lineage = state.lineage;
        plan.baseSerial = state.serial;

        for (const auto& [address, target] : desired) {

            target.validate();

            auto existing = state.resources.find(address);

            if (existing == state.resources.end()) {

                plan.changes.push_back({
                    address,
                    Action::Create,
                    std::nullopt,
                    target
                });

            } else if (
                !existing->second.equivalent(target)
            ) {

                plan.changes.push_back({
                    address,
                    Action::Update,
                    existing->second,
                    target
                });
            }
        }

        for (const auto& [address, current] : state.resources) {

            if (!desired.count(address)) {

                plan.changes.push_back({
                    address,
                    Action::Delete,
                    current,
                    std::nullopt
                });
            }
        }

        return plan;
    }
};


// ============================================================
// STATE MANAGEMENT SERVICE
// ============================================================

class StateManagementService {

private:

    StateBackend& backend;

    InfrastructureInventory& infrastructure;

public:

    StateManagementService(
        StateBackend& backendReference,
        InfrastructureInventory& inventoryReference
    )
        : backend(backendReference),
          infrastructure(inventoryReference) {}

    TerraformState apply(
        const TerraformPlan& plan,
        const std::string& owner
    ) {

        StateLock lock = backend.acquireLock(
            plan.workspace,
            "apply",
            owner
        );

        try {

            TerraformState current = backend.read(
                plan.workspace
            );

            if (
                current.serial != plan.baseSerial ||
                current.lineage != plan.lineage
            ) {
                throw ConflictException(
                    "Stale plan. Generate a new plan."
                );
            }

            TerraformState next = current;

            for (const auto& change : plan.changes) {

                switch (change.action) {

                    case Action::Create: {

                        const Resource& resource = *change.after;

                        infrastructure.create(resource);

                        next.resources[change.address] = resource;

                        break;
                    }

                    case Action::Update: {

                        const Resource& resource = *change.after;

                        infrastructure.update(
                            change.address,
                            resource.attributes
                        );

                        next.resources[change.address] = resource;

                        break;
                    }

                    case Action::Delete: {

                        infrastructure.erase(change.address);

                        next.resources.erase(change.address);

                        break;
                    }
                }
            }

            if (!plan.changes.empty()) {

                next.serial = current.serial + 1;

                next.updatedAt = currentTimestamp();

                backend.write(
                    plan.workspace,
                    next,
                    current.serial
                );
            }

            backend.releaseLock(
                plan.workspace,
                lock.id
            );

            return next;

        } catch (...) {

            backend.releaseLock(
                plan.workspace,
                lock.id
            );

            throw;
        }
    }

    TerraformState refresh(
        const std::string& workspace
    ) {

        StateLock lock = backend.acquireLock(
            workspace,
            "refresh",
            "refresh-service"
        );

        try {

            TerraformState current = backend.read(workspace);

            TerraformState next = current;

            for (auto& [address, resource] : next.resources) {

                auto actual = infrastructure.find(address);

                if (!actual.has_value()) {
                    throw ConflictException(
                        "Infrastructure resource missing: " + address
                    );
                }

                resource.id = actual->id;
                resource.attributes = actual->attributes;
            }

            next.serial++;

            backend.write(
                workspace,
                next,
                current.serial
            );

            backend.releaseLock(
                workspace,
                lock.id
            );

            return next;

        } catch (...) {

            backend.releaseLock(
                workspace,
                lock.id
            );

            throw;
        }
    }

    void detectDrift(
        const std::string& workspace
    ) {

        TerraformState state = backend.read(workspace);

        std::cout << "\nDRIFT REPORT\n";

        for (const auto& [address, resource] : state.resources) {

            auto actual = infrastructure.find(address);

            if (!actual.has_value()) {

                std::cout << "MISSING: " << address << "\n";

            } else if (
                resource.id != actual->id ||
                resource.attributes != actual->attributes
            ) {

                std::cout << "MODIFIED: " << address << "\n";
            }
        }

        for (const auto& [address, actual] :
             infrastructure.all()) {

            if (!state.resources.count(address)) {

                std::cout << "UNTRACKED: " << address << "\n";
            }
        }
    }
};


// ============================================================
// WORKSPACE REGISTRY
// ============================================================

class WorkspaceRegistry {

private:

    std::set<std::string> workspaces{"default"};

public:

    void create(const std::string& name) {

        validateWorkspace(name);

        if (!workspaces.insert(name).second) {
            throw ValidationException(
                "Workspace already exists."
            );
        }
    }

    void display() const {

        std::cout << "\nWORKSPACES\n";

        for (const auto& workspace : workspaces) {
            std::cout << "  " << workspace << "\n";
        }
    }
};


// ============================================================
// STATE MIGRATION
// ============================================================

class StateMigrationService {

public:

    static void migrate(
        StateBackend& source,
        StateBackend& destination,
        const std::string& workspace
    ) {

        StateLock sourceLock = source.acquireLock(
            workspace,
            "migration",
            "migration-service"
        );

        try {

            TerraformState sourceState = source.read(workspace);

            TerraformState destinationState =
                destination.read(workspace);

            if (
                destinationState.serial != 0 ||
                !destinationState.resources.empty()
            ) {
                throw ConflictException(
                    "Destination backend is not empty."
                );
            }

            if (
                sourceState.lineage != destinationState.lineage
            ) {
                throw ConflictException(
                    "State lineage mismatch."
                );
            }

            StateLock destinationLock =
                destination.acquireLock(
                    workspace,
                    "migration",
                    "migration-service"
                );

            try {

                TerraformState migrated = sourceState;

                migrated.serial = destinationState.serial + 1;

                migrated.updatedAt = currentTimestamp();

                destination.write(
                    workspace,
                    migrated,
                    destinationState.serial
                );

                destination.releaseLock(
                    workspace,
                    destinationLock.id
                );

            } catch (...) {

                destination.releaseLock(
                    workspace,
                    destinationLock.id
                );

                throw;
            }

            source.releaseLock(
                workspace,
                sourceLock.id
            );

        } catch (...) {

            source.releaseLock(
                workspace,
                sourceLock.id
            );

            throw;
        }
    }
};


// ============================================================
// DEMONSTRATION
// ============================================================

Resource makeResource(
    const std::string& address,
    const std::string& type,
    const std::string& id,
    const std::map<std::string, std::string>& attributes
) {

    Resource resource;

    resource.address = address;
    resource.type = type;
    resource.provider = "hashicorp/aws";
    resource.id = id;
    resource.attributes = attributes;

    resource.validate();

    return resource;
}

int main() {

    try {

        std::cout << "TERRAFORM STATE GOVERNANCE ENGINE\n";
        std::cout << "=================================\n";

        RemoteStateBackend remoteBackend;

        InfrastructureInventory infrastructure;

        StateManagementService service(
            remoteBackend,
            infrastructure
        );

        WorkspaceRegistry workspaces;

        const std::string workspace = "production";

        workspaces.create("staging");
        workspaces.display();

        // Define desired infrastructure.
        std::map<std::string, Resource> desired;

        desired["aws_instance.api"] = makeResource(
            "aws_instance.api",
            "aws_instance",
            "i-api-001",
            {
                {"instance_type", "t3.medium"},
                {"region", "ap-south-1"}
            }
        );

        desired["aws_s3_bucket.assets"] = makeResource(
            "aws_s3_bucket.assets",
            "aws_s3_bucket",
            "assets-001",
            {
                {"versioning", "true"},
                {"encryption", "AES256"}
            }
        );

        // Initialize the backend with a consistent lineage.
        TerraformState initial;

        initial.workspace = workspace;

        StateLock initializationLock =
            remoteBackend.acquireLock(
                workspace,
                "initialization",
                "system"
            );

        remoteBackend.write(
            workspace,
            initial,
            0
        );

        remoteBackend.releaseLock(
            workspace,
            initializationLock.id
        );

        // Generate a plan.
        TerraformPlan plan = PlanEngine::generate(
            remoteBackend.read(workspace),
            desired
        );

        std::cout << "\nPLAN\n";

        for (const auto& change : plan.changes) {

            std::cout
                << toString(change.action)
                << " "
                << change.address
                << "\n";
        }

        // Apply changes.
        TerraformState applied = service.apply(
            plan,
            "deployment-pipeline"
        );

        applied.display();

        // Introduce infrastructure drift.
        infrastructure.update(
            "aws_instance.api",
            {{"instance_type", "t3.large"}}
        );

        service.detectDrift(workspace);

        // Refresh state.
        TerraformState refreshed = service.refresh(
            workspace
        );

        std::cout << "\nAFTER REFRESH\n";

        refreshed.display();

        // Demonstrate state locking.
        std::cout << "\nLOCK TEST\n";

        StateLock firstLock = remoteBackend.acquireLock(
            workspace,
            "apply",
            "pipeline-A"
        );

        try {

            remoteBackend.acquireLock(
                workspace,
                "apply",
                "pipeline-B"
            );

            throw StateException(
                "Concurrent lock was unexpectedly granted."
            );

        } catch (const LockException& error) {

            std::cout << "REJECTED: "
                      << error.what()
                      << "\n";
        }

        remoteBackend.releaseLock(
            workspace,
            firstLock.id
        );

        // Demonstrate stale plan rejection.
        TerraformPlan stalePlan = PlanEngine::generate(
            remoteBackend.read(workspace),
            {
                {
                    "aws_instance.api",
                    makeResource(
                        "aws_instance.api",
                        "aws_instance",
                        "i-api-001",
                        {
                            {"instance_type", "t3.small"},
                            {"region", "ap-south-1"}
                        }
                    )
                },
                {
                    "aws_s3_bucket.assets",
                    desired.at("aws_s3_bucket.assets")
                }
            }
        );

        service.refresh(workspace);

        try {

            service.apply(
                stalePlan,
                "stale-runner"
            );

        } catch (const ConflictException& error) {

            std::cout << "\nSTALE PLAN REJECTED: "
                      << error.what()
                      << "\n";
        }

        // Demonstrate backend migration.
        RemoteStateBackend destinationBackend;

        StateMigrationService::migrate(
            remoteBackend,
            destinationBackend,
            workspace
        );

        std::cout << "\nMIGRATED STATE\n";

        destinationBackend.read(workspace).display();

        std::cout << "\nSTATE SNAPSHOTS: "
                  << remoteBackend.getHistory(workspace).size()
                  << "\n";

        std::cout << "\nEXECUTION COMPLETED\n";

    } catch (const std::exception& error) {

        std::cerr << "ERROR: "
                  << error.what()
                  << "\n";

        return 1;
    }

    return 0;
}

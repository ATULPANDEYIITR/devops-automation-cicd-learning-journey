#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Repository governance case study: secure Actions configuration.
 *
 * The system represents a CI/CD control plane in which:
 * - repositories have protected environments,
 * - secrets have explicit scopes,
 * - deployment jobs request named credentials,
 * - access is evaluated before a credential is released,
 * - secret values are never included in audit records,
 * - credential rotation and expiration affect deployment eligibility.
 *
 * The C++ implementation deliberately treats secrets as runtime data and
 * keeps their lifecycle separate from ordinary repository configuration.
 */

enum class Scope {
    Organization,
    Repository,
    Environment
};

enum class Role {
    Developer,
    Maintainer,
    SecurityAdmin,
    Runner
};

enum class SecretState {
    Active,
    Disabled
};

struct Actor {
    std::string username;
    Role role;
    std::set<std::string> repositories;
    std::set<std::string> environments;
};

struct SecretKey {
    Scope scope;
    std::string name;
    std::string repository;
    std::string environment;

    bool operator<(const SecretKey& other) const {
        if (scope != other.scope) {
            return scope < other.scope;
        }
        if (name != other.name) {
            return name < other.name;
        }
        if (repository != other.repository) {
            return repository < other.repository;
        }
        return environment < other.environment;
    }
};

struct Secret {
    std::string name;
    Scope scope;
    std::string value;
    std::string repository;
    std::string environment;
    std::chrono::system_clock::time_point createdAt;
    std::chrono::system_clock::time_point rotatedAt;
    std::chrono::system_clock::time_point expiresAt;
    SecretState state;
};

struct AuditEvent {
    std::chrono::system_clock::time_point timestamp;
    std::string actor;
    std::string action;
    std::string secretName;
    std::string repository;
    std::string environment;
    std::string result;
};

class SecureConfigurationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class AuthorizationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class SecretStore {
private:
    std::map<SecretKey, Secret> secrets_;
    std::vector<AuditEvent> audit_;

    static std::string scopeName(Scope scope) {
        switch (scope) {
            case Scope::Organization:
                return "organization";
            case Scope::Repository:
                return "repository";
            case Scope::Environment:
                return "environment";
        }
        return "unknown";
    }

    bool canManage(
        const Actor& actor,
        const std::string& repository
    ) const {
        if (actor.role == Role::SecurityAdmin) {
            return true;
        }

        if (actor.role != Role::Maintainer &&
            actor.role != Role::Developer) {
            return false;
        }

        return actor.repositories.count(repository) > 0;
    }

    bool canRead(
        const Actor& actor,
        const std::string& repository,
        const std::string& environment
    ) const {
        if (actor.role == Role::SecurityAdmin) {
            return true;
        }

        if (!actor.repositories.count(repository)) {
            return false;
        }

        if (!environment.empty() &&
            !actor.environments.empty() &&
            !actor.environments.count(environment)) {
            return false;
        }

        return actor.role == Role::Runner ||
               actor.role == Role::Developer ||
               actor.role == Role::Maintainer;
    }

    void audit(
        const Actor& actor,
        const std::string& action,
        const Secret& secret,
        const std::string& result
    ) {
        audit_.push_back({
            std::chrono::system_clock::now(),
            actor.username,
            action,
            secret.name,
            secret.repository,
            secret.environment,
            result
        });
    }

    static bool isUsable(const Secret& secret) {
        if (secret.state != SecretState::Active) {
            return false;
        }

        return std::chrono::system_clock::now() < secret.expiresAt;
    }

public:
    static void validateName(const std::string& name) {
        if (name.size() < 2 || name.size() > 100) {
            throw SecureConfigurationError(
                "Secret name must contain between 2 and 100 characters."
            );
        }

        if (name.front() < 'A' || name.front() > 'Z') {
            throw SecureConfigurationError(
                "Secret name must begin with an uppercase letter."
            );
        }

        for (char character : name) {
            const bool valid =
                (character >= 'A' && character <= 'Z') ||
                (character >= '0' && character <= '9') ||
                character == '_';

            if (!valid) {
                throw SecureConfigurationError(
                    "Secret name contains an invalid character."
                );
            }
        }

        if (name == "PASSWORD" ||
            name == "SECRET" ||
            name == "TOKEN" ||
            name == "KEY") {
            throw SecureConfigurationError(
                "Generic credential names make configuration ambiguous."
            );
        }
    }

    static void validateValue(const std::string& value) {
        if (value.size() < 16) {
            throw SecureConfigurationError(
                "Credential is too short for this policy."
            );
        }

        if (value.find('\n') != std::string::npos ||
            value.find('\r') != std::string::npos) {
            throw SecureConfigurationError(
                "Unexpected newline in credential."
            );
        }
    }

    static std::string generateCredential(const std::string& prefix) {
        std::random_device device;
        std::mt19937_64 generator(device());

        std::ostringstream stream;
        stream << prefix << "_";

        for (int i = 0; i < 32; ++i) {
            const std::uint64_t value = generator();
            stream << std::hex << (value & 0x0f);
        }

        return stream.str();
    }

    void put(
        const Actor& actor,
        const std::string& name,
        const std::string& value,
        Scope scope,
        const std::string& repository,
        const std::string& environment,
        std::chrono::hours lifetime
    ) {
        validateName(name);
        validateValue(value);

        if (scope == Scope::Repository && repository.empty()) {
            throw SecureConfigurationError(
                "Repository-scoped secret requires a repository."
            );
        }

        if (scope == Scope::Environment &&
            (repository.empty() || environment.empty())) {
            throw SecureConfigurationError(
                "Environment-scoped secret requires repository and environment."
            );
        }

        if (!canManage(actor, repository)) {
            throw AuthorizationError(
                actor.username + " cannot manage this repository's secrets."
            );
        }

        SecretKey key{
            scope,
            name,
            repository,
            environment
        };

        const auto currentTime = std::chrono::system_clock::now();

        auto found = secrets_.find(key);

        if (found == secrets_.end()) {
            Secret secret{
                name,
                scope,
                value,
                repository,
                environment,
                currentTime,
                currentTime,
                currentTime + lifetime,
                SecretState::Active
            };

            secrets_.emplace(key, std::move(secret));

            audit(actor, "create", secrets_.at(key), "allowed");
            return;
        }

        found->second.value = value;
        found->second.rotatedAt = currentTime;
        found->second.expiresAt = currentTime + lifetime;
        found->second.state = SecretState::Active;

        audit(actor, "rotate", found->second, "allowed");
    }

    std::optional<Secret> metadata(
        const std::string& name,
        Scope scope,
        const std::string& repository,
        const std::string& environment
    ) const {
        const SecretKey key{
            scope,
            name,
            repository,
            environment
        };

        auto found = secrets_.find(key);

        if (found == secrets_.end()) {
            return std::nullopt;
        }

        Secret result = found->second;
        result.value = "[REDACTED]";
        return result;
    }

    std::string resolve(
        const Actor& actor,
        const std::string& name,
        const std::string& repository,
        const std::string& environment
    ) {
        /*
         * Scope precedence is explicit:
         * environment > repository > organization.
         * This allows a production deployment to override a repository
         * default without changing the repository's source configuration.
         */
        const std::vector<SecretKey> candidates{
            {
                Scope::Environment,
                name,
                repository,
                environment
            },
            {
                Scope::Repository,
                name,
                repository,
                ""
            },
            {
                Scope::Organization,
                name,
                "",
                ""
            }
        };

        for (const auto& key : candidates) {
            auto found = secrets_.find(key);

            if (found == secrets_.end() || !isUsable(found->second)) {
                continue;
            }

            if (!canRead(actor, repository, environment)) {
                audit(actor, "read", found->second, "denied");
                throw AuthorizationError(
                    actor.username + " is not authorized to read " + name
                );
            }

            audit(actor, "read", found->second, "allowed");
            return found->second.value;
        }

        throw SecureConfigurationError(
            "No active, non-expired secret is available."
        );
    }

    void disable(
        const Actor& actor,
        Scope scope,
        const std::string& name,
        const std::string& repository,
        const std::string& environment
    ) {
        SecretKey key{
            scope,
            name,
            repository,
            environment
        };

        auto found = secrets_.find(key);

        if (found == secrets_.end()) {
            throw SecureConfigurationError("Secret does not exist.");
        }

        if (!canManage(actor, repository)) {
            throw AuthorizationError(
                actor.username + " cannot disable this secret."
            );
        }

        found->second.state = SecretState::Disabled;
        audit(actor, "disable", found->second, "allowed");
    }

    const std::vector<AuditEvent>& audit() const {
        return audit_;
    }
};

class DeploymentPolicy {
private:
    std::set<std::string> requiredSecrets_;

public:
    DeploymentPolicy(std::set<std::string> requiredSecrets)
        : requiredSecrets_(std::move(requiredSecrets)) {}

    bool evaluate(
        SecretStore& store,
        const Actor& runner,
        const std::string& repository,
        const std::string& environment,
        std::vector<std::string>& findings
    ) const {
        bool valid = true;

        for (const auto& secretName : requiredSecrets_) {
            try {
                const std::string credential = store.resolve(
                    runner,
                    secretName,
                    repository,
                    environment
                );

                /*
                 * The deployment policy can confirm that a credential exists
                 * without logging its value.
                 */
                findings.push_back(
                    secretName + " available, length=" +
                    std::to_string(credential.size())
                );
            } catch (const std::exception& error) {
                valid = false;
                findings.push_back(
                    secretName + " unavailable: " + error.what()
                );
            }
        }

        return valid;
    }
};

static std::string stateName(SecretState state) {
    return state == SecretState::Active ? "active" : "disabled";
}

int main() {
    std::cout << "=== Secure Actions Configuration Engine ===\n\n";

    SecretStore store;

    const Actor securityAdmin{
        "security-admin",
        Role::SecurityAdmin,
        {"acme/payments"},
        {"development", "staging", "production"}
    };

    const Actor developer{
        "developer",
        Role::Developer,
        {"acme/payments"},
        {"development", "staging"}
    };

    const Actor productionRunner{
        "actions-production-runner",
        Role::Runner,
        {"acme/payments"},
        {"production"}
    };

    std::cout << "Creating organization-level credential...\n";

    store.put(
        securityAdmin,
        "PACKAGE_REGISTRY_TOKEN",
        SecretStore::generateCredential("package"),
        Scope::Organization,
        "",
        "",
        std::chrono::hours(24 * 90)
    );

    std::cout << "Creating repository-level database credential...\n";

    store.put(
        securityAdmin,
        "DATABASE_PASSWORD",
        SecretStore::generateCredential("database"),
        Scope::Repository,
        "acme/payments",
        "",
        std::chrono::hours(24 * 60)
    );

    std::cout << "Creating production-only deployment credential...\n";

    store.put(
        securityAdmin,
        "DEPLOY_TOKEN",
        SecretStore::generateCredential("production"),
        Scope::Environment,
        "acme/payments",
        "production",
        std::chrono::hours(24 * 14)
    );

    std::cout << "\n=== Production policy evaluation ===\n";

    DeploymentPolicy policy({
        "DATABASE_PASSWORD",
        "DEPLOY_TOKEN",
        "PACKAGE_REGISTRY_TOKEN"
    });

    std::vector<std::string> findings;

    const bool deploymentAllowed = policy.evaluate(
        store,
        productionRunner,
        "acme/payments",
        "production",
        findings
    );

    for (const auto& finding : findings) {
        std::cout << finding << '\n';
    }

    std::cout
        << "Deployment eligibility: "
        << (deploymentAllowed ? "allowed" : "blocked")
        << "\n";

    std::cout << "\n=== Scope separation ===\n";

    const std::string stagingDatabase = store.resolve(
        developer,
        "DATABASE_PASSWORD",
        "acme/payments",
        "staging"
    );

    std::cout
        << "Staging database credential length: "
        << stagingDatabase.size()
        << '\n';

    const std::string productionDeployment = store.resolve(
        productionRunner,
        "DEPLOY_TOKEN",
        "acme/payments",
        "production"
    );

    std::cout
        << "Production deployment credential length: "
        << productionDeployment.size()
        << '\n';

    std::cout << "\n=== Metadata never exposes secret values ===\n";

    auto metadata = store.metadata(
        "DEPLOY_TOKEN",
        Scope::Environment,
        "acme/payments",
        "production"
    );

    if (metadata) {
        std::cout
            << "Name: " << metadata->name << '\n'
            << "Scope: environment\n"
            << "Repository: " << metadata->repository << '\n'
            << "Environment: " << metadata->environment << '\n'
            << "State: " << stateName(metadata->state) << '\n'
            << "Stored value: " << metadata->value << '\n';
    }

    std::cout << "\n=== Unauthorized read ===\n";

    const Actor externalContributor{
        "external-contributor",
        Role::Developer,
        {},
        {}
    };

    try {
        store.resolve(
            externalContributor,
            "DEPLOY_TOKEN",
            "acme/payments",
            "production"
        );

        std::cout << "Unexpected authorization success.\n";
    } catch (const std::exception& error) {
        std::cout << "Blocked: " << error.what() << '\n';
    }

    std::cout << "\n=== Rotation ===\n";

    store.put(
        securityAdmin,
        "DEPLOY_TOKEN",
        SecretStore::generateCredential("production-rotated"),
        Scope::Environment,
        "acme/payments",
        "production",
        std::chrono::hours(24 * 14)
    );

    std::cout << "Production deployment credential rotated successfully.\n";

    std::cout << "\n=== Disable emergency credential ===\n";

    store.disable(
        securityAdmin,
        Scope::Environment,
        "DEPLOY_TOKEN",
        "acme/payments",
        "production"
    );

    try {
        store.resolve(
            productionRunner,
            "DEPLOY_TOKEN",
            "acme/payments",
            "production"
        );

        std::cout << "Unexpected resolution of disabled credential.\n";
    } catch (const std::exception& error) {
        std::cout << "Disabled credential rejected: "
                  << error.what() << '\n';
    }

    std::cout << "\n=== Audit records ===\n";

    for (const auto& event : store.audit()) {
        std::time_t timestamp =
            std::chrono::system_clock::to_time_t(event.timestamp);

        std::cout
            << std::put_time(std::localtime(&timestamp), "%F %T")
            << " actor=" << event.actor
            << " action=" << event.action
            << " secret=" << event.secretName
            << " repository=" << event.repository
            << " environment=" << event.environment
            << " result=" << event.result
            << '\n';
    }

    std::cout << "\n=== Case-study design properties ===\n";
    std::cout
        << "Secret values remain separate from metadata and audit events.\n"
        << "Environment scope provides production-specific credential isolation.\n"
        << "Authorization is evaluated before runtime credential release.\n"
        << "Expiration and disabled states block credential resolution.\n"
        << "Rotation changes the credential while retaining lifecycle history.\n"
        << "A deployment policy can verify required credentials without printing them.\n";

    return 0;
}

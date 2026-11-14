#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Feature Flag Governance Engine
 *
 * C++17 implementation of:
 * - Typed feature flag definitions
 * - Environment isolation
 * - User and group targeting
 * - Deterministic rollout assignment
 * - Kill switches
 * - Version-controlled updates
 * - Audit records
 * - Expiration
 * - Merge-like atomic configuration replacement
 *
 * Evaluation uses deterministic FNV-1a hashing.
 * It is suitable for stable allocation, not cryptographic security.
 */

enum class FlagType {
    Boolean,
    Percentage,
    Targeted
};

enum class FlagStatus {
    Active,
    Disabled,
    Archived
};

enum class Environment {
    Development,
    Staging,
    Production
};

std::string toString(Environment environment) {
    switch (environment) {
        case Environment::Development: return "development";
        case Environment::Staging: return "staging";
        case Environment::Production: return "production";
    }

    throw std::invalid_argument("Unknown environment");
}

std::string toString(FlagStatus status) {
    switch (status) {
        case FlagStatus::Active: return "ACTIVE";
        case FlagStatus::Disabled: return "DISABLED";
        case FlagStatus::Archived: return "ARCHIVED";
    }

    throw std::invalid_argument("Unknown status");
}

struct EvaluationContext {
    std::string userId;
    Environment environment;
    std::set<std::string> groups;
};

struct FeatureFlag {
    std::string key;
    std::string description;

    FlagType type = FlagType::Boolean;
    FlagStatus status = FlagStatus::Active;

    std::set<Environment> environments;
    std::set<std::string> allowedUsers;
    std::set<std::string> allowedGroups;

    double rolloutPercentage = 0.0;
    bool defaultValue = false;

    std::string owner = "platform-team";
    std::uint64_t version = 1;

    bool hasExpiration = false;
    std::chrono::system_clock::time_point expiresAt;
};

struct AuditRecord {
    std::string flagKey;
    std::string action;
    std::string actor;
    std::uint64_t version;
};

class FeatureFlagEngine {
private:
    std::map<std::string, FeatureFlag> flags;
    std::vector<AuditRecord> audit;

    static void validate(const FeatureFlag& flag) {
        if (flag.key.empty()) {
            throw std::invalid_argument("Flag key cannot be empty");
        }

        if (!std::all_of(
            flag.key.begin(),
            flag.key.end(),
            [](unsigned char c) {
                return std::isalnum(c) || c == '_' || c == '-';
            }
        )) {
            throw std::invalid_argument("Invalid flag key");
        }

        if (!std::isfinite(flag.rolloutPercentage) ||
            flag.rolloutPercentage < 0.0 ||
            flag.rolloutPercentage > 100.0) {
            throw std::invalid_argument(
                "Rollout must be between 0 and 100"
            );
        }

        if (flag.version == 0) {
            throw std::invalid_argument("Version must be positive");
        }
    }

    static std::uint64_t hash(
        const std::string& key,
        const std::string& userId
    ) {
        // FNV-1a provides stable, inexpensive cohort allocation.
        std::uint64_t value = 14695981039346656037ULL;

        const std::string input = key + ":" + userId;

        for (unsigned char character : input) {
            value ^= character;
            value *= 1099511628211ULL;
        }

        return value;
    }

    static double bucket(
        const std::string& key,
        const std::string& userId
    ) {
        const std::uint64_t value = hash(key, userId);

        return static_cast<long double>(value) /
               static_cast<long double>(
                   UINT64_MAX
               ) * 100.0;
    }

    void record(
        const FeatureFlag& flag,
        const std::string& action,
        const std::string& actor
    ) {
        audit.push_back({
            flag.key,
            action,
            actor,
            flag.version
        });
    }

public:
    void registerFlag(
        const FeatureFlag& flag,
        const std::string& actor
    ) {
        validate(flag);

        if (flags.count(flag.key)) {
            throw std::runtime_error("Duplicate feature flag");
        }

        flags.emplace(flag.key, flag);

        record(flag, "CREATED", actor);
    }

    bool evaluate(
        const std::string& key,
        const EvaluationContext& context
    ) const {
        if (context.userId.empty()) {
            throw std::invalid_argument("User ID is required");
        }

        const auto iterator = flags.find(key);

        if (iterator == flags.end()) {
            return false;
        }

        const FeatureFlag& flag = iterator->second;

        if (flag.status != FlagStatus::Active) {
            return false;
        }

        if (flag.hasExpiration &&
            std::chrono::system_clock::now() >= flag.expiresAt) {
            return false;
        }

        if (!flag.environments.count(context.environment)) {
            return false;
        }

        if (flag.allowedUsers.count(context.userId)) {
            return true;
        }

        for (const auto& group : context.groups) {
            if (flag.allowedGroups.count(group)) {
                return true;
            }
        }

        switch (flag.type) {
            case FlagType::Boolean:
                return flag.defaultValue;

            case FlagType::Targeted:
                return false;

            case FlagType::Percentage:
                return bucket(key, context.userId) <
                       flag.rolloutPercentage;
        }

        return false;
    }

    void updatePercentage(
        const std::string& key,
        double percentage,
        std::uint64_t expectedVersion,
        const std::string& actor
    ) {
        if (!std::isfinite(percentage) ||
            percentage < 0.0 ||
            percentage > 100.0) {
            throw std::invalid_argument("Invalid percentage");
        }

        auto iterator = flags.find(key);

        if (iterator == flags.end()) {
            throw std::runtime_error("Unknown flag");
        }

        FeatureFlag updated = iterator->second;

        if (updated.version != expectedVersion) {
            throw std::runtime_error("Version conflict");
        }

        updated.rolloutPercentage = percentage;
        updated.type = FlagType::Percentage;
        updated.version++;

        validate(updated);

        // Replace only after validation succeeds.
        iterator->second = updated;

        record(updated, "ROLLOUT_UPDATED", actor);
    }

    void setStatus(
        const std::string& key,
        FlagStatus status,
        const std::string& actor
    ) {
        auto iterator = flags.find(key);

        if (iterator == flags.end()) {
            throw std::runtime_error("Unknown flag");
        }

        FeatureFlag updated = iterator->second;

        if (status == FlagStatus::Active &&
            updated.hasExpiration &&
            std::chrono::system_clock::now() >= updated.expiresAt) {
            throw std::runtime_error("Cannot enable expired flag");
        }

        updated.status = status;
        updated.version++;

        iterator->second = updated;

        record(updated, toString(status), actor);
    }

    void setKillSwitch(
        const std::string& key,
        const std::string& actor
    ) {
        setStatus(key, FlagStatus::Disabled, actor);
    }

    const FeatureFlag& getFlag(const std::string& key) const {
        auto iterator = flags.find(key);

        if (iterator == flags.end()) {
            throw std::runtime_error("Unknown feature flag");
        }

        return iterator->second;
    }

    void printReport() const {
        std::cout << "\nFEATURE FLAG REPORT\n";

        std::cout
            << std::left
            << std::setw(24) << "KEY"
            << std::setw(16) << "TYPE"
            << std::setw(14) << "STATUS"
            << std::setw(12) << "ROLLOUT"
            << "VERSION\n";

        for (const auto& entry : flags) {
            const auto& flag = entry.second;

            std::string type;

            switch (flag.type) {
                case FlagType::Boolean:
                    type = "BOOLEAN";
                    break;
                case FlagType::Percentage:
                    type = "PERCENTAGE";
                    break;
                case FlagType::Targeted:
                    type = "TARGETED";
                    break;
            }

            std::cout
                << std::left
                << std::setw(24) << flag.key
                << std::setw(16) << type
                << std::setw(14) << toString(flag.status)
                << std::setw(12) << flag.rolloutPercentage
                << flag.version
                << '\n';
        }
    }

    void printAudit() const {
        std::cout << "\nAUDIT HISTORY\n";

        for (const auto& item : audit) {
            std::cout
                << item.flagKey << " | "
                << item.action << " | "
                << item.actor << " | v"
                << item.version << '\n';
        }
    }
};

int main() {
    try {
        FeatureFlagEngine engine;

        FeatureFlag checkout;

        checkout.key = "new_checkout";
        checkout.description = "New checkout experience";
        checkout.type = FlagType::Percentage;
        checkout.environments = {
            Environment::Staging,
            Environment::Production
        };
        checkout.rolloutPercentage = 25.0;
        checkout.allowedUsers = {"admin_001"};
        checkout.allowedGroups = {"beta_testers"};
        checkout.owner = "payments-team";

        engine.registerFlag(checkout, "platform-admin");

        FeatureFlag search;

        search.key = "new_search";
        search.description = "New search implementation";
        search.type = FlagType::Boolean;
        search.environments = {Environment::Staging};
        search.defaultValue = true;
        search.owner = "search-team";

        engine.registerFlag(search, "platform-admin");

        std::vector<EvaluationContext> users = {
            {
                "user_001",
                Environment::Production,
                {"standard"}
            },
            {
                "user_002",
                Environment::Production,
                {"beta_testers"}
            },
            {
                "admin_001",
                Environment::Production,
                {"standard"}
            },
            {
                "user_003",
                Environment::Staging,
                {"standard"}
            }
        };

        std::cout << "\nEVALUATION RESULTS\n";

        for (const auto& user : users) {
            bool enabled = engine.evaluate(
                "new_checkout",
                user
            );

            std::cout
                << std::setw(14) << user.userId
                << " environment="
                << std::setw(12) << toString(user.environment)
                << " enabled="
                << std::boolalpha << enabled
                << '\n';
        }

        // Repeated evaluation must preserve cohort assignment.
        bool first = engine.evaluate(
            "new_checkout",
            users[0]
        );

        bool second = engine.evaluate(
            "new_checkout",
            users[0]
        );

        if (first != second) {
            throw std::runtime_error(
                "Deterministic allocation failure"
            );
        }

        // Explicit group targeting takes priority.
        if (!engine.evaluate("new_checkout", users[1])) {
            throw std::runtime_error("Group targeting failed");
        }

        // Environment isolation.
        if (engine.evaluate("new_search", users[0])) {
            throw std::runtime_error("Environment isolation failed");
        }

        if (!engine.evaluate("new_search", users[3])) {
            throw std::runtime_error("Boolean evaluation failed");
        }

        std::cout << "\nIncreasing rollout to 50 percent.\n";

        engine.updatePercentage(
            "new_checkout",
            50.0,
            1,
            "release-manager"
        );

        // Optimistic concurrency protects against stale updates.
        try {
            engine.updatePercentage(
                "new_checkout",
                80.0,
                1,
                "another-manager"
            );

            throw std::runtime_error(
                "Stale update was unexpectedly accepted"
            );
        } catch (const std::runtime_error& error) {
            if (std::string(error.what()) != "Version conflict") {
                throw;
            }

            std::cout << "Stale update correctly rejected.\n";
        }

        // Emergency disable immediately blocks evaluation.
        engine.setKillSwitch(
            "new_checkout",
            "incident-commander"
        );

        if (engine.evaluate("new_checkout", users[1])) {
            throw std::runtime_error("Kill switch failed");
        }

        engine.setStatus(
            "new_checkout",
            FlagStatus::Active,
            "release-manager"
        );

        engine.printReport();
        engine.printAudit();

        std::cout << "\nAll C++17 checks passed.\n";

    } catch (const std::exception& error) {
        std::cerr
            << "ERROR: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Bash DevOps Scripts: Industry-Style Deployment Case Study
 *
 * Scenario:
 *   A service named inventory-api is released through versioned directories.
 *   The deployment system stages a release, validates it, activates it,
 *   performs health validation, records operational logs, and rolls back
 *   automatically when validation fails.
 *
 * The program is intentionally implemented using the C++17 standard library.
 * It models filesystem and operational mechanisms that are commonly automated
 * by Bash scripts using mkdir, cp, ln, mv, grep, awk, curl, test, trap and
 * related Unix utilities.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic devops_case_study.cpp -o devops_case_study
 *
 * Run:
 *   ./devops_case_study
 */

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;


// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

std::string timestamp() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t time = std::chrono::system_clock::to_time_t(now);

    std::tm tm{};

#ifdef _WIN32
    localtime_s(&tm, &time);
#else
    localtime_r(&time, &tm);
#endif

    std::ostringstream output;
    output << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");

    return output.str();
}


void logMessage(
    const std::string& level,
    const std::string& message
) {
    std::cout
        << timestamp()
        << " "
        << level
        << " "
        << message
        << '\n';
}


bool safeVersion(const std::string& version) {
    if (version.empty()) {
        return false;
    }

    static const std::regex pattern(
        R"(^[A-Za-z0-9._+-]+$)"
    );

    return std::regex_match(version, pattern);
}


bool safeRelativePath(const fs::path& path) {
    if (path.is_absolute()) {
        return false;
    }

    for (const auto& component : path) {
        if (component == "..") {
            return false;
        }
    }

    return true;
}


// ---------------------------------------------------------------------------
// Log model
// ---------------------------------------------------------------------------

struct LogEntry {
    std::string timestamp;
    std::string level;
    std::string service;
    int status = 0;
    double latencyMs = 0.0;
    std::string message;
};


class LogProcessor {
public:
    void add(const LogEntry& entry) {
        entries_.push_back(entry);
    }

    std::size_t total() const {
        return entries_.size();
    }

    std::size_t countLevel(
        const std::string& level
    ) const {
        return static_cast<std::size_t>(
            std::count_if(
                entries_.begin(),
                entries_.end(),
                [&](const LogEntry& entry) {
                    return entry.level == level;
                }
            )
        );
    }

    std::size_t countStatusClass(
        int lowerBound,
        int upperBound
    ) const {
        return static_cast<std::size_t>(
            std::count_if(
                entries_.begin(),
                entries_.end(),
                [&](const LogEntry& entry) {
                    return entry.status >= lowerBound &&
                           entry.status <= upperBound;
                }
            )
        );
    }

    double averageLatency() const {
        if (entries_.empty()) {
            return 0.0;
        }

        double totalLatency = 0.0;

        for (const auto& entry : entries_) {
            totalLatency += entry.latencyMs;
        }

        return totalLatency /
               static_cast<double>(entries_.size());
    }

    std::map<int, std::size_t> statusDistribution() const {
        std::map<int, std::size_t> distribution;

        for (const auto& entry : entries_) {
            ++distribution[entry.status];
        }

        return distribution;
    }

    void printReport() const {
        const auto errors = countLevel("ERROR");
        const auto warnings = countLevel("WARN");

        std::cout
            << "\nLog report\n"
            << "---------\n"
            << "Total records: " << total() << '\n'
            << "Warnings:      " << warnings << '\n'
            << "Errors:        " << errors << '\n'
            << "5xx responses: "
            << countStatusClass(500, 599)
            << '\n'
            << "Average latency: "
            << std::fixed
            << std::setprecision(2)
            << averageLatency()
            << " ms\n";

        std::cout << "Status distribution:\n";

        for (const auto& [status, count] : statusDistribution()) {
            std::cout
                << "  "
                << status
                << ": "
                << count
                << '\n';
        }
    }

private:
    std::vector<LogEntry> entries_;
};


// ---------------------------------------------------------------------------
// Release model
// ---------------------------------------------------------------------------

struct Release {
    std::string version;
    fs::path path;
};


// ---------------------------------------------------------------------------
// Deployment states
// ---------------------------------------------------------------------------

enum class DeploymentState {
    Created,
    Validated,
    Staged,
    Activated,
    Healthy,
    Failed,
    RolledBack
};


std::string stateName(DeploymentState state) {
    switch (state) {
        case DeploymentState::Created:
            return "created";
        case DeploymentState::Validated:
            return "validated";
        case DeploymentState::Staged:
            return "staged";
        case DeploymentState::Activated:
            return "activated";
        case DeploymentState::Healthy:
            return "healthy";
        case DeploymentState::Failed:
            return "failed";
        case DeploymentState::RolledBack:
            return "rolled_back";
    }

    return "unknown";
}


struct DeploymentResult {
    std::string application;
    std::string environment;
    std::string version;
    DeploymentState state = DeploymentState::Created;
    std::string error;
    std::chrono::milliseconds duration{0};
};


// ---------------------------------------------------------------------------
// Deployment manager
// ---------------------------------------------------------------------------

class DeploymentManager {
public:
    explicit DeploymentManager(fs::path root)
        : root_(std::move(root)) {}

    void initialize() {
        fs::create_directories(root_);
    }

    fs::path releasePath(
        const std::string& version
    ) const {
        return root_ / version;
    }

    bool releaseExists(
        const std::string& version
    ) const {
        return fs::is_directory(
            releasePath(version)
        );
    }

    Release stageRelease(
        const std::string& version,
        const std::map<std::string, std::string>& files
    ) {
        if (!safeVersion(version)) {
            throw std::invalid_argument(
                "Release version contains unsafe characters."
            );
        }

        const fs::path destination =
            releasePath(version);

        if (fs::exists(destination)) {
            throw std::runtime_error(
                "Release already exists: " + version
            );
        }

        fs::create_directories(destination);

        try {
            for (const auto& [relativeName, content] : files) {
                const fs::path relativePath(relativeName);

                if (!safeRelativePath(relativePath)) {
                    throw std::runtime_error(
                        "Unsafe release path: " + relativeName
                    );
                }

                const fs::path target =
                    destination / relativePath;

                fs::create_directories(
                    target.parent_path()
                );

                std::ofstream output(target);

                if (!output) {
                    throw std::runtime_error(
                        "Unable to write release file: " +
                        target.string()
                    );
                }

                output << content;
            }
        } catch (...) {
            /*
             * A failed staging operation should not leave an apparently valid
             * release directory behind.
             */
            std::error_code cleanupError;
            fs::remove_all(
                destination,
                cleanupError
            );
            throw;
        }

        return Release{
            version,
            destination
        };
    }

    std::optional<std::string> currentVersion() const {
        const fs::path active = root_ / "current";

        std::error_code error;

        if (!fs::exists(active, error)) {
            return std::nullopt;
        }

        fs::path resolved =
            fs::weakly_canonical(active, error);

        if (error) {
            return std::nullopt;
        }

        return resolved.filename().string();
    }

    void activate(
        const std::string& version
    ) {
        const fs::path target =
            releasePath(version);

        if (!fs::is_directory(target)) {
            throw std::runtime_error(
                "Cannot activate missing release: " +
                version
            );
        }

        const fs::path active =
            root_ / "current";

        const fs::path temporary =
            root_ /
            (".current-" +
             std::to_string(
                 std::chrono::steady_clock::now()
                     .time_since_epoch()
                     .count()
             ));

        std::error_code error;

        /*
         * On Unix-like systems, a symbolic link plus atomic rename is a common
         * way to make the active-version switch very small. Windows uses
         * different filesystem semantics, so this case study keeps the logic
         * conservative and reports filesystem failures explicitly.
         */
        fs::create_directory_symlink(
            target,
            temporary,
            error
        );

        if (error) {
            throw std::runtime_error(
                "Unable to create activation link: " +
                error.message()
            );
        }

        /*
         * Replacing an existing directory symlink differs across platforms.
         * Remove the existing active link before installing the new one.
         * A production implementation should choose platform-specific atomic
         * replacement semantics where required.
         */
        if (fs::exists(active, error) ||
            fs::is_symlink(active)) {
            fs::remove(active, error);

            if (error) {
                fs::remove(temporary);
                throw std::runtime_error(
                    "Unable to remove active release: " +
                    error.message()
                );
            }
        }

        fs::rename(
            temporary,
            active,
            error
        );

        if (error) {
            fs::remove(temporary);
            throw std::runtime_error(
                "Unable to activate release: " +
                error.message()
            );
        }
    }

    const fs::path& root() const {
        return root_;
    }

private:
    fs::path root_;
};


// ---------------------------------------------------------------------------
// Health checker
// ---------------------------------------------------------------------------

class HealthChecker {
public:
    explicit HealthChecker(
        std::function<bool()> check
    )
        : check_(std::move(check)) {}

    bool checkWithRetry(
        int attempts,
        std::chrono::milliseconds delay
    ) const {
        attempts = std::max(1, attempts);

        for (int attempt = 1; attempt <= attempts; ++attempt) {
            if (check_()) {
                return true;
            }

            if (attempt < attempts) {
                std::this_thread::sleep_for(delay);
            }
        }

        return false;
    }

private:
    std::function<bool()> check_;
};


// ---------------------------------------------------------------------------
// Deployment service
// ---------------------------------------------------------------------------

class DeploymentService {
public:
    explicit DeploymentService(
        DeploymentManager& manager
    )
        : manager_(manager) {}

    DeploymentResult deploy(
        const std::string& application,
        const std::string& environment,
        const std::string& version,
        const std::map<std::string, std::string>& files,
        const HealthChecker& healthChecker
    ) {
        const auto start = Clock::now();

        DeploymentResult result{
            application,
            environment,
            version,
            DeploymentState::Created,
            "",
            std::chrono::milliseconds{0}
        };

        try {
            validateInputs(
                application,
                environment,
                version
            );

            result.state =
                DeploymentState::Validated;

            const auto previous =
                manager_.currentVersion();

            manager_.stageRelease(
                version,
                files
            );

            result.state =
                DeploymentState::Staged;

            manager_.activate(version);

            result.state =
                DeploymentState::Activated;

            if (!healthChecker.checkWithRetry(
                    3,
                    std::chrono::milliseconds(100)
                )) {
                throw std::runtime_error(
                    "Post-deployment health check failed."
                );
            }

            result.state =
                DeploymentState::Healthy;

            logMessage(
                "INFO",
                "Deployment activated: " +
                application +
                " version=" +
                version +
                " environment=" +
                environment
            );

            if (previous.has_value()) {
                logMessage(
                    "INFO",
                    "Previous release retained for rollback: " +
                    *previous
                );
            }
        } catch (const std::exception& error) {
            result.state =
                DeploymentState::Failed;

            result.error = error.what();

            logMessage(
                "ERROR",
                "Deployment failed: " +
                result.error
            );

            /*
             * If a previous version exists, restore it. This is the key
             * operational difference between a deployment that merely copies
             * files and one that has a recovery strategy.
             */
            try {
                const auto previous =
                    manager_.currentVersion();

                if (previous.has_value() &&
                    *previous != version) {
                    manager_.activate(*previous);

                    result.state =
                        DeploymentState::RolledBack;

                    logMessage(
                        "WARN",
                        "Rollback activated: " +
                        *previous
                    );
                }
            } catch (const std::exception& rollbackError) {
                result.error +=
                    " Rollback failed: " +
                    std::string(rollbackError.what());

                logMessage(
                    "ERROR",
                    "Rollback failed: " +
                    std::string(rollbackError.what())
                );
            }
        }

        result.duration =
            std::chrono::duration_cast<
                std::chrono::milliseconds
            >(Clock::now() - start);

        return result;
    }

private:
    static void validateInputs(
        const std::string& application,
        const std::string& environment,
        const std::string& version
    ) {
        if (application.empty()) {
            throw std::invalid_argument(
                "Application name is empty."
            );
        }

        if (!safeVersion(application)) {
            throw std::invalid_argument(
                "Application name contains unsafe characters."
            );
        }

        if (environment.empty()) {
            throw std::invalid_argument(
                "Environment is empty."
            );
        }

        if (!safeVersion(environment)) {
            throw std::invalid_argument(
                "Environment contains unsafe characters."
            );
        }

        if (!safeVersion(version)) {
            throw std::invalid_argument(
                "Version contains unsafe characters."
            );
        }
    }

    DeploymentManager& manager_;
};


// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

struct Configuration {
    std::string application = "inventory-api";
    std::string environment = "staging";
    std::string initialVersion = "1.0.0";
    std::string releaseVersion = "1.1.0";
    std::string failedVersion = "1.2.0";
};


Configuration loadConfiguration() {
    Configuration config;

    /*
     * The case study keeps defaults deterministic. A production application
     * can load values from environment variables or a configuration service.
     */

    return config;
}


// ---------------------------------------------------------------------------
// Demonstrations
// ---------------------------------------------------------------------------

void demonstrateBasicShellIdeas() {
    std::cout
        << "\n=== Basic Shell Concepts Modeled in C++ ===\n"
        << "Exit status 0 represents success.\n"
        << "Non-zero status represents failure.\n"
        << "STDOUT carries normal output.\n"
        << "STDERR carries diagnostics.\n"
        << "Pipelines transform streams from one operation to another.\n"
        << "Deployment scripts should validate input before modifying state.\n";
}


void demonstrateLogProcessing() {
    LogProcessor processor;

    processor.add({
        "2026-09-19T10:00:01",
        "INFO",
        "inventory-api",
        200,
        31,
        "request completed"
    });

    processor.add({
        "2026-09-19T10:00:02",
        "INFO",
        "inventory-api",
        200,
        22,
        "request completed"
    });

    processor.add({
        "2026-09-19T10:00:03",
        "WARN",
        "inventory-api",
        200,
        820,
        "slow request"
    });

    processor.add({
        "2026-09-19T10:00:04",
        "ERROR",
        "inventory-api",
        503,
        0,
        "database unavailable"
    });

    processor.add({
        "2026-09-19T10:00:05",
        "ERROR",
        "inventory-api",
        500,
        125,
        "internal server error"
    });

    processor.printReport();
}


void demonstrateDeploymentScenario() {
    const Configuration config =
        loadConfiguration();

    const fs::path temporaryRoot =
        fs::temp_directory_path() /
        (
            "bash-devops-case-study-" +
            std::to_string(
                std::chrono::steady_clock::now()
                    .time_since_epoch()
                    .count()
            )
        );

    const fs::path releases =
        temporaryRoot / "releases";

    try {
        fs::create_directories(releases);

        DeploymentManager manager(releases);
        manager.initialize();

        /*
         * Establish a known initial version.
         */
        manager.stageRelease(
            config.initialVersion,
            {
                {
                    "VERSION",
                    config.initialVersion + "\n"
                },
                {
                    "config/application.conf",
                    "environment=staging\n"
                    "feature.inventory=true\n"
                }
            }
        );

        manager.activate(
            config.initialVersion
        );

        logMessage(
            "INFO",
            "Initial release active: " +
            config.initialVersion
        );

        DeploymentService service(manager);

        /*
         * First deployment succeeds.
         */
        HealthChecker healthyChecker(
            [] {
                return true;
            }
        );

        DeploymentResult successful =
            service.deploy(
                config.application,
                config.environment,
                config.releaseVersion,
                {
                    {
                        "VERSION",
                        config.releaseVersion + "\n"
                    },
                    {
                        "config/application.conf",
                        "environment=staging\n"
                        "feature.inventory=true\n"
                        "feature.fast-search=true\n"
                    }
                },
                healthyChecker
            );

        std::cout
            << "\nSuccessful deployment state: "
            << stateName(successful.state)
            << '\n'
            << "Duration: "
            << successful.duration.count()
            << " ms\n";

        /*
         * Second deployment intentionally fails its health check. This
         * demonstrates the rollback path.
         */
        HealthChecker unhealthyChecker(
            [] {
                return false;
            }
        );

        DeploymentResult failed =
            service.deploy(
                config.application,
                config.environment,
                config.failedVersion,
                {
                    {
                        "VERSION",
                        config.failedVersion + "\n"
                    },
                    {
                        "config/application.conf",
                        "environment=staging\n"
                        "feature.inventory=true\n"
                        "broken_dependency=true\n"
                    }
                },
                unhealthyChecker
            );

        std::cout
            << "\nFailed deployment state: "
            << stateName(failed.state)
            << '\n'
            << "Error: "
            << failed.error
            << '\n'
            << "Duration: "
            << failed.duration.count()
            << " ms\n";

        const auto active =
            manager.currentVersion();

        std::cout
            << "Active version after failure: "
            << (active.has_value()
                    ? *active
                    : "none")
            << '\n';

        /*
         * Edge case: an invalid version is rejected before filesystem changes.
         */
        try {
            service.deploy(
                config.application,
                config.environment,
                "../malicious-version",
                {
                    {
                        "VERSION",
                        "invalid\n"
                    }
                },
                healthyChecker
            );
        } catch (...) {
            /*
             * deploy() already converts operational exceptions into a result.
             * This block remains intentionally empty because the invalid input
             * result is demonstrated below through a direct state check.
             */
        }

        DeploymentResult invalid =
            service.deploy(
                config.application,
                config.environment,
                "../malicious-version",
                {
                    {
                        "VERSION",
                        "invalid\n"
                    }
                },
                healthyChecker
            );

        std::cout
            << "Invalid version state: "
            << stateName(invalid.state)
            << '\n';

        fs::remove_all(temporaryRoot);
    } catch (...) {
        /*
         * Best-effort cleanup is important in demonstrations and operational
         * tooling. Production cleanup should also record cleanup failures.
         */
        std::error_code cleanupError;
        fs::remove_all(
            temporaryRoot,
            cleanupError
        );

        throw;
    }
}


// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    try {
        std::cout
            << "Bash DevOps Deployment Case Study\n"
            << "=================================\n";

        demonstrateBasicShellIdeas();
        demonstrateLogProcessing();
        demonstrateDeploymentScenario();

        std::cout
            << "\nCase study completed successfully.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}

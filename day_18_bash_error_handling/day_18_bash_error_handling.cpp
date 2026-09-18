#include <algorithm>
#include <array>
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <utility>
#include <vector>

/*
 * Bash Error Handling: industry-style deployment workflow case study.
 *
 * This C++17 program models a small automation/orchestration service that:
 *
 *   - validates deployment requests
 *   - creates isolated staging directories
 *   - executes Bash commands
 *   - captures exit codes and output
 *   - distinguishes expected and unexpected failures
 *   - implements bounded retries
 *   - uses Bash traps for cleanup
 *   - detects pipeline failures with pipefail
 *   - validates generated artifacts
 *   - performs a final promotion
 *   - records structured audit events
 *
 * The program uses only the C++ standard library plus POSIX process APIs
 * available on typical Linux environments.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic bash_error_case_study.cpp -o bash_error_case_study
 *
 * Run:
 *   ./bash_error_case_study
 *
 * The program intentionally performs all filesystem work inside a temporary
 * directory and does not modify a real deployment installation.
 */

namespace fs = std::filesystem;

// -----------------------------------------------------------------------------
// Data models
// -----------------------------------------------------------------------------

enum class Severity {
    Info,
    Warning,
    Error
};

struct AuditEvent {
    Severity severity;
    std::string message;
};

struct CommandResult {
    std::string command;
    int raw_wait_status = -1;
    int exit_code = -1;
    bool exited_normally = false;
    bool timed_out = false;
    std::string stdout_text;
    std::string stderr_text;

    bool succeeded() const {
        return exited_normally && exit_code == 0;
    }
};

struct DeploymentRequest {
    std::string application_name;
    std::string version;
    std::string expected_environment;
    int maximum_attempts = 3;
};

struct DeploymentResult {
    bool success = false;
    int exit_code = 1;
    std::string message;
};

// -----------------------------------------------------------------------------
// Utility functions
// -----------------------------------------------------------------------------

std::string severityName(Severity severity) {
    switch (severity) {
        case Severity::Info:
            return "INFO";
        case Severity::Warning:
            return "WARN";
        case Severity::Error:
            return "ERROR";
    }
    return "UNKNOWN";
}


void printBanner(std::string_view title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}


void printAudit(const AuditEvent& event) {
    std::cout << "[" << severityName(event.severity) << "] "
              << event.message << "\n";
}


bool isPositiveInteger(const std::string& value) {
    if (value.empty()) {
        return false;
    }

    return std::all_of(
        value.begin(),
        value.end(),
        [](unsigned char character) {
            return std::isdigit(character) != 0;
        }
    );
}


bool validateVersion(const std::string& version) {
    /*
     * This case study uses a deliberately simple semantic-version-like
     * validation rule: major.minor.patch, where each component is numeric.
     */
    std::stringstream stream(version);
    std::string part;
    int componentCount = 0;

    while (std::getline(stream, part, '.')) {
        if (!isPositiveInteger(part)) {
            return false;
        }

        ++componentCount;
    }

    return componentCount == 3;
}


bool validateApplicationName(const std::string& name) {
    if (name.empty() || name.size() > 64) {
        return false;
    }

    return std::all_of(
        name.begin(),
        name.end(),
        [](unsigned char character) {
            return std::isalnum(character) ||
                   character == '-' ||
                   character == '_' ||
                   character == '.';
        }
    );
}


// -----------------------------------------------------------------------------
// ShellRunner
// -----------------------------------------------------------------------------

class ShellRunner {
public:
    explicit ShellRunner(std::chrono::seconds timeout)
        : timeout_(timeout) {}

    CommandResult run(
        const std::string& script,
        const std::string& workingDirectory
    ) const {
        /*
         * The script is written to a temporary file rather than interpolated
         * into a shell command string. This avoids adding another layer of
         * quoting around the Bash source itself.
         */
        const fs::path scriptPath =
            fs::path(workingDirectory) / "operation.sh";

        {
            std::ofstream file(scriptPath);
            if (!file) {
                throw std::runtime_error(
                    "unable to create Bash script: " + scriptPath.string()
                );
            }

            file << script;
        }

        fs::permissions(
            scriptPath,
            fs::perms::owner_read |
            fs::perms::owner_write |
            fs::perms::owner_exec,
            fs::perm_options::replace
        );

        const fs::path stdoutPath =
            fs::path(workingDirectory) / "stdout.log";

        const fs::path stderrPath =
            fs::path(workingDirectory) / "stderr.log";

        /*
         * The outer process is started through the POSIX shell API. The Bash
         * script itself uses strict mode and arrays rather than constructing
         * additional command strings from untrusted input.
         */
        std::string command =
            "cd -- " + shellQuote(workingDirectory) +
            " && bash --noprofile --norc " +
            shellQuote(scriptPath.string()) +
            " >" + shellQuote(stdoutPath.string()) +
            " 2>" + shellQuote(stderrPath.string());

        const auto start = std::chrono::steady_clock::now();

        const int status = std::system(command.c_str());

        const auto end = std::chrono::steady_clock::now();
        const auto elapsed =
            std::chrono::duration_cast<std::chrono::seconds>(end - start);

        CommandResult result;
        result.command = script;
        result.raw_wait_status = status;

        if (elapsed > timeout_) {
            result.timed_out = true;
            result.exited_normally = false;
            result.exit_code = 124;
        } else if (status == -1) {
            result.exited_normally = false;
            result.exit_code = 125;
        } else if (WIFEXITED(status)) {
            result.exited_normally = true;
            result.exit_code = WEXITSTATUS(status);
        } else if (WIFSIGNALED(status)) {
            result.exited_normally = false;
            result.exit_code = 128 + WTERMSIG(status);
        }

        result.stdout_text = readTextFile(stdoutPath);
        result.stderr_text = readTextFile(stderrPath);

        return result;
    }

private:
    std::chrono::seconds timeout_;

    static std::string readTextFile(const fs::path& path) {
        std::ifstream file(path);

        if (!file) {
            return {};
        }

        std::ostringstream content;
        content << file.rdbuf();
        return content.str();
    }

    static std::string shellQuote(const std::string& value) {
        /*
         * Single-quote shell escaping:
         *
         *   abc       -> 'abc'
         *   a'b       -> 'a'\''b'
         *
         * This is needed only for the trusted local paths constructed by this
         * program. User-controlled data is validated before reaching this layer.
         */
        std::string quoted = "'";

        for (char character : value) {
            if (character == '\'') {
                quoted += "'\\''";
            } else {
                quoted += character;
            }
        }

        quoted += "'";
        return quoted;
    }
};


// -----------------------------------------------------------------------------
// DeploymentManager
// -----------------------------------------------------------------------------

class DeploymentManager {
public:
    DeploymentManager()
        : runner_(std::chrono::seconds(10)) {}

    DeploymentResult deploy(const DeploymentRequest& request) {
        printBanner("C++ CASE STUDY: DEFENSIVE BASH DEPLOYMENT ORCHESTRATOR");

        if (!validateRequest(request)) {
            return {
                false,
                2,
                "deployment request validation failed"
            };
        }

        printAudit({
            Severity::Info,
            "request validation succeeded"
        });

        fs::path workspace;

        try {
            workspace = createWorkspace();

            printAudit({
                Severity::Info,
                "isolated workspace: " + workspace.string()
            });

            const fs::path staging =
                workspace / "staging";

            const fs::path target =
                workspace / "target";

            fs::create_directories(staging);
            fs::create_directories(target);

            printAudit({
                Severity::Info,
                "staging and target directories created"
            });

            DeploymentResult stageResult =
                stageApplication(request, staging);

            if (!stageResult.success) {
                return finalize(
                    workspace,
                    stageResult
                );
            }

            DeploymentResult validationResult =
                validateStagedApplication(request, staging);

            if (!validationResult.success) {
                return finalize(
                    workspace,
                    validationResult
                );
            }

            DeploymentResult promotionResult =
                promoteApplication(staging, target);

            if (!promotionResult.success) {
                return finalize(
                    workspace,
                    promotionResult
                );
            }

            printAudit({
                Severity::Info,
                "deployment completed successfully"
            });

            DeploymentResult success {
                true,
                0,
                "deployment completed successfully"
            };

            return finalize(workspace, success);
        }
        catch (const std::exception& exception) {
            printAudit({
                Severity::Error,
                std::string("orchestrator exception: ") +
                    exception.what()
            });

            DeploymentResult failure {
                false,
                70,
                exception.what()
            };

            return finalize(workspace, failure);
        }
    }

private:
    ShellRunner runner_;

    bool validateRequest(const DeploymentRequest& request) const {
        if (!validateApplicationName(request.application_name)) {
            printAudit({
                Severity::Error,
                "invalid application name"
            });
            return false;
        }

        if (!validateVersion(request.version)) {
            printAudit({
                Severity::Error,
                "invalid version; expected major.minor.patch"
            });
            return false;
        }

        if (request.expected_environment != "production" &&
            request.expected_environment != "staging") {
            printAudit({
                Severity::Error,
                "environment must be production or staging"
            });
            return false;
        }

        if (request.maximum_attempts < 1 ||
            request.maximum_attempts > 5) {
            printAudit({
                Severity::Error,
                "maximum attempts must be between 1 and 5"
            });
            return false;
        }

        return true;
    }


    fs::path createWorkspace() const {
        const fs::path base =
            fs::temp_directory_path();

        const auto timestamp =
            std::chrono::steady_clock::now()
                .time_since_epoch()
                .count();

        fs::path workspace =
            base /
            ("cpp-bash-case-study-" +
             std::to_string(timestamp));

        /*
         * A real production implementation would use a stronger unique-name
         * mechanism and carefully controlled permissions. The directory here
         * exists only for this isolated educational case study.
         */
        fs::create_directories(workspace);

        return workspace;
    }


    DeploymentResult stageApplication(
        const DeploymentRequest& request,
        const fs::path& staging
    ) {
        printBanner("Stage application");

        const std::string script = R"BASH(
set -Eeuo pipefail

readonly APP_NAME="$1"
readonly VERSION="$2"
readonly STAGING_DIR="$3"

cleanup() {
    local status=$?
    printf '[BASH] staging cleanup status=%s\n' "$status" >&2
}

on_error() {
    local status=$?
    printf '[BASH] ERR status=%s command=%s line=%s\n' \
        "$status" "$BASH_COMMAND" "${BASH_LINENO[0]}" >&2
}

trap on_error ERR
trap cleanup EXIT

: "${APP_NAME:?application name required}"
: "${VERSION:?version required}"
: "${STAGING_DIR:?staging directory required}"

mkdir -p -- "$STAGING_DIR"

printf 'application=%s\nversion=%s\n' \
    "$APP_NAME" "$VERSION" \
    > "$STAGING_DIR/metadata.txt"

printf 'build-status=ready\n' \
    > "$STAGING_DIR/build.status"

printf '[BASH] staged application successfully\n'
)BASH";

        /*
         * Bash positional arguments are passed through environment variables
         * here to keep the generated script independent of shell interpolation.
         *
         * Because runner_ executes the script without a positional-argument
         * interface, the command below is a small wrapper that invokes the
         * generated Bash logic with quoted local values.
         */
        const std::string wrapper =
            "set -Eeuo pipefail\n"
            "APP_NAME=" + quoteForBash(request.application_name) + "\n"
            "VERSION=" + quoteForBash(request.version) + "\n"
            "STAGING_DIR=" + quoteForBash(staging.string()) + "\n"
            "export APP_NAME VERSION STAGING_DIR\n" +
            "bash -c " + quoteForBash(script) + " -- "
            + "\"$APP_NAME\" \"$VERSION\" \"$STAGING_DIR\"\n";

        CommandResult result =
            runWithRetries(
                wrapper,
                staging.string(),
                request.maximum_attempts
            );

        printCommandResult(result);

        if (!result.succeeded()) {
            return {
                false,
                normalizeExitCode(result),
                "staging operation failed"
            };
        }

        return {
            true,
            0,
            "staging succeeded"
        };
    }


    DeploymentResult validateStagedApplication(
        const DeploymentRequest& request,
        const fs::path& staging
    ) {
        printBanner("Validate staged application");

        const fs::path metadata =
            staging / "metadata.txt";

        const fs::path statusFile =
            staging / "build.status";

        if (!fs::exists(metadata) ||
            !fs::is_regular_file(metadata)) {
            printAudit({
                Severity::Error,
                "metadata file does not exist"
            });

            return {
                false,
                10,
                "missing metadata"
            };
        }

        if (!fs::exists(statusFile) ||
            !fs::is_regular_file(statusFile)) {
            printAudit({
                Severity::Error,
                "build status file does not exist"
            });

            return {
                false,
                11,
                "missing build status"
            };
        }

        std::ifstream metadataFile(metadata);
        std::string line;
        std::map<std::string, std::string> values;

        while (std::getline(metadataFile, line)) {
            const auto separator = line.find('=');

            if (separator == std::string::npos) {
                printAudit({
                    Severity::Error,
                    "malformed metadata line"
                });

                return {
                    false,
                    12,
                    "malformed metadata"
                };
            }

            values[line.substr(0, separator)] =
                line.substr(separator + 1);
        }

        if (values["application"] != request.application_name) {
            printAudit({
                Severity::Error,
                "application name mismatch"
            });

            return {
                false,
                13,
                "application mismatch"
            };
        }

        if (values["version"] != request.version) {
            printAudit({
                Severity::Error,
                "version mismatch"
            });

            return {
                false,
                14,
                "version mismatch"
            };
        }

        printAudit({
            Severity::Info,
            "staged metadata passed validation"
        });

        /*
         * Demonstrate pipeline-aware validation. pipefail is important here:
         * without it, an early producer failure can be hidden by a successful
         * final command.
         */
        const std::string validationScript =
            "set -Eeuo pipefail\n"
            "metadata=" + quoteForBash(metadata.string()) + "\n"
            "grep -q '^version=' \"$metadata\" | cat >/dev/null\n"
            "printf '[BASH] pipeline validation passed\\n'\n";

        CommandResult result =
            runner_.run(
                validationScript,
                staging.string()
            );

        printCommandResult(result);

        if (!result.succeeded()) {
            return {
                false,
                normalizeExitCode(result),
                "pipeline validation failed"
            };
        }

        return {
            true,
            0,
            "validation succeeded"
        };
    }


    DeploymentResult promoteApplication(
        const fs::path& staging,
        const fs::path& target
    ) {
        printBanner("Promote staged application");

        const fs::path source =
            staging / "metadata.txt";

        const fs::path destination =
            target / "application.txt";

        const std::string script =
            "set -Eeuo pipefail\n"
            "source_file=" + quoteForBash(source.string()) + "\n"
            "destination=" + quoteForBash(destination.string()) + "\n"
            "trap 'status=$?; printf \"[BASH] promotion cleanup status=%s\\n\" "
            "\"$status\" >&2' EXIT\n"
            "[[ -s \"$source_file\" ]]\n"
            "cp -- \"$source_file\" \"$destination\"\n"
            "[[ -s \"$destination\" ]]\n"
            "printf '[BASH] promotion successful\\n'\n";

        CommandResult result =
            runner_.run(
                script,
                target.string()
            );

        printCommandResult(result);

        if (!result.succeeded()) {
            return {
                false,
                normalizeExitCode(result),
                "promotion failed"
            };
        }

        printAudit({
            Severity::Info,
            "target artifact exists and is non-empty"
        });

        return {
            true,
            0,
            "promotion succeeded"
        };
    }


    CommandResult runWithRetries(
        const std::string& script,
        const std::string& workingDirectory,
        int maximumAttempts
    ) {
        CommandResult lastResult;

        for (int attempt = 1;
             attempt <= maximumAttempts;
             ++attempt) {

            std::ostringstream message;
            message << "Bash operation attempt "
                    << attempt << "/"
                    << maximumAttempts;

            printAudit({
                Severity::Info,
                message.str()
            });

            lastResult =
                runner_.run(
                    script,
                    workingDirectory
                );

            if (lastResult.succeeded()) {
                return lastResult;
            }

            /*
             * Not every failure should be retried. A real deployment system
             * would classify exit codes and application-level errors before
             * deciding whether to retry.
             */
            if (lastResult.exit_code >= 2 &&
                lastResult.exit_code < 10) {
                printAudit({
                    Severity::Warning,
                    "failure classified as potentially retryable"
                });
            } else {
                printAudit({
                    Severity::Warning,
                    "failure classified as non-retryable for this case study"
                });
                return lastResult;
            }

            if (attempt < maximumAttempts) {
                const int seconds =
                    std::min(
                        1 << (attempt - 1),
                        4
                    );

                std::cout
                    << "waiting "
                    << seconds
                    << " second(s) before retry\n";

                std::this_thread::sleep_for(
                    std::chrono::seconds(seconds)
                );
            }
        }

        return lastResult;
    }


    DeploymentResult finalize(
        const fs::path& workspace,
        DeploymentResult result
    ) {
        if (!workspace.empty() &&
            fs::exists(workspace)) {

            std::error_code error;
            fs::remove_all(workspace, error);

            if (error) {
                printAudit({
                    Severity::Warning,
                    "workspace cleanup reported: " +
                    error.message()
                });
            } else {
                printAudit({
                    Severity::Info,
                    "workspace removed"
                });
            }
        }

        return result;
    }


    static int normalizeExitCode(
        const CommandResult& result
    ) {
        if (result.timed_out) {
            return 124;
        }

        if (!result.exited_normally) {
            return result.exit_code >= 0
                ? result.exit_code
                : 125;
        }

        return result.exit_code;
    }


    static void printCommandResult(
        const CommandResult& result
    ) {
        std::cout
            << "Bash exit code: "
            << result.exit_code
            << "\n";

        if (!result.stdout_text.empty()) {
            std::cout
                << "Bash stdout:\n"
                << result.stdout_text;
        }

        if (!result.stderr_text.empty()) {
            std::cout
                << "Bash stderr:\n"
                << result.stderr_text;
        }

        if (result.succeeded()) {
            printAudit({
                Severity::Info,
                "Bash command succeeded"
            });
        } else {
            printAudit({
                Severity::Error,
                "Bash command returned nonzero status"
            });
        }
    }


    static std::string quoteForBash(
        const std::string& value
    ) {
        /*
         * Quote a value for a Bash single-quoted string.
         *
         * This routine is used for values that have already passed validation
         * and for local filesystem paths. It still performs complete quote
         * escaping to preserve a correct argument boundary.
         */
        std::string result = "'";

        for (char character : value) {
            if (character == '\'') {
                result += "'\\''";
            } else {
                result += character;
            }
        }

        result += "'";
        return result;
    }
};


// -----------------------------------------------------------------------------
// Educational demonstrations
// -----------------------------------------------------------------------------

void demonstrateExitCodes() {
    printBanner("BASIC CONCEPT: EXIT CODES");

    std::cout
        << "Exit status 0 conventionally represents success.\n"
        << "Nonzero statuses communicate failure or another defined condition.\n"
        << "Bash exposes the previous command status through $?.\n\n";

    const int success = std::system("bash -c 'true'");
    const int failure = std::system("bash -c 'false'");

    std::cout
        << "true raw process status: "
        << success << "\n";

    std::cout
        << "false raw process status: "
        << failure << "\n";

    std::cout
        << "The C++ wait status is not identical to the Bash exit code. "
        << "A POSIX parent must inspect WIFEXITED/WEXITSTATUS.\n";
}


void demonstrateStrictMode() {
    printBanner("STRICT MODE CONCEPT");

    std::cout
        << "A common Bash defensive baseline is:\n"
        << "    set -Eeuo pipefail\n\n"
        << "E       propagates ERR traps into relevant contexts.\n"
        << "e       requests exit after many unhandled failures.\n"
        << "u       rejects unintended unset variables.\n"
        << "pipefail exposes failures in pipelines.\n\n"
        << "Strict mode is a defensive baseline, not a substitute for understanding\n"
        << "Bash's conditional and pipeline semantics.\n";
}


void demonstrateFailureClassification() {
    printBanner("FAILURE CLASSIFICATION");

    const std::map<int, std::string> categories {
        {0, "success"},
        {1, "generic or application-defined failure"},
        {2, "invalid usage or configuration in this case study"},
        {10, "missing staged metadata"},
        {11, "missing build status"},
        {12, "malformed metadata"},
        {13, "application mismatch"},
        {14, "version mismatch"},
        {70, "orchestration exception"},
        {124, "operation timeout"},
    };

    for (const auto& [code, description] : categories) {
        std::cout
            << std::setw(3)
            << code
            << " -> "
            << description
            << "\n";
    }

    std::cout
        << "\nExit-code meanings should be documented as part of a command's\n"
        << "interface rather than guessed by callers.\n";
}


// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main() {
    try {
        demonstrateExitCodes();
        demonstrateStrictMode();
        demonstrateFailureClassification();

        printBanner("DEPLOYMENT REQUEST");

        DeploymentRequest request {
            "example-service",
            "1.4.2",
            "production",
            3
        };

        std::cout
            << "application: "
            << request.application_name
            << "\n"
            << "version: "
            << request.version
            << "\n"
            << "environment: "
            << request.expected_environment
            << "\n"
            << "maximum attempts: "
            << request.maximum_attempts
            << "\n";

        DeploymentManager manager;

        DeploymentResult result =
            manager.deploy(request);

        printBanner("FINAL RESULT");

        std::cout
            << "success: "
            << std::boolalpha
            << result.success
            << "\n"
            << "exit code: "
            << result.exit_code
            << "\n"
            << "message: "
            << result.message
            << "\n";

        return result.exit_code;
    }
    catch (const std::exception& exception) {
        std::cerr
            << "fatal C++ error: "
            << exception.what()
            << "\n";

        return 70;
    }
}

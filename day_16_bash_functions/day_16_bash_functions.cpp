#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

/*
 * Bash Functions: C++17 technical case study
 *
 * Scenario
 * --------
 * A deployment-oriented command runner is modeled as a reusable command-line
 * system. The architecture mirrors a robust Bash automation script:
 *
 *   CLI arguments
 *        |
 *        v
 *   argument parser
 *        |
 *        v
 *   command dispatcher
 *        |
 *        v
 *   reusable functions
 *        |
 *        +---- validation
 *        +---- filesystem operations
 *        +---- retries
 *        +---- status codes
 *        +---- logging
 *
 * The C++ program deliberately uses explicit return/status objects because
 * C++ return values and Unix process exit codes are distinct concepts.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic main.cpp -o bash_case_study
 */

namespace app {

// ---------------------------------------------------------------------------
// Status model
// ---------------------------------------------------------------------------
//
// Bash functions conventionally communicate success/failure through an exit
// status. This case study models that concept explicitly.
//
// 0   success
// 1   general failure
// 2   invalid usage
// 3   validation failure
// 127 command not found

struct Result {
    int status = 0;
    std::string output;

    static Result success(std::string value = {}) {
        return {0, std::move(value)};
    }

    static Result failure(int code, std::string message) {
        return {code, std::move(message)};
    }

    bool ok() const {
        return status == 0;
    }
};


// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

void logInfo(const std::string& message) {
    std::cerr << "[INFO] " << message << '\n';
}

void logWarning(const std::string& message) {
    std::cerr << "[WARN] " << message << '\n';
}

void logError(const std::string& message) {
    std::cerr << "[ERROR] " << message << '\n';
}


// ---------------------------------------------------------------------------
// Basic reusable functions
// ---------------------------------------------------------------------------

std::string greet(const std::string& name) {
    return "Hello, " + name;
}

Result validateUsername(const std::string& username) {
    if (username.empty()) {
        return Result::failure(
            2,
            "username is required"
        );
    }

    for (unsigned char character : username) {
        if (!std::isalnum(character) && character != '_') {
            return Result::failure(
                3,
                "username contains invalid characters"
            );
        }
    }

    std::string normalized = username;

    std::transform(
        normalized.begin(),
        normalized.end(),
        normalized.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        }
    );

    return Result::success(normalized);
}


// ---------------------------------------------------------------------------
// Argument parser
// ---------------------------------------------------------------------------
//
// Bash commonly processes arguments using $1, shift, case, and $#.
// C++ uses argc/argv. The same logical design can be implemented with an
// explicit parser.
//
// Supported:
//
//   --verbose
//   --name VALUE
//   --
//   positional files
//
// Unknown options fail with status 2.

struct Options {
    bool verbose = false;
    std::string name = "Guest";
    std::vector<std::string> files;
};

struct ParseResult {
    int status = 0;
    std::optional<Options> options;
    std::string error;
};

ParseResult parseArguments(
    const std::vector<std::string>& arguments
) {
    Options options;

    std::size_t index = 0;

    while (index < arguments.size()) {
        const std::string& current = arguments[index];

        if (current == "--verbose") {
            options.verbose = true;
            ++index;
        }
        else if (current == "--name") {
            if (index + 1 >= arguments.size()) {
                return {
                    2,
                    std::nullopt,
                    "--name requires a value"
                };
            }

            options.name = arguments[index + 1];
            index += 2;
        }
        else if (current == "--") {
            for (++index; index < arguments.size(); ++index) {
                options.files.push_back(arguments[index]);
            }
            break;
        }
        else if (!current.empty() && current.front() == '-') {
            return {
                2,
                std::nullopt,
                "unknown option: " + current
            };
        }
        else {
            options.files.push_back(current);
            ++index;
        }
    }

    return {0, options, {}};
}


// ---------------------------------------------------------------------------
// File validation
// ---------------------------------------------------------------------------

Result validateInputFile(const fs::path& file) {
    if (!fs::exists(file)) {
        return Result::failure(
            1,
            "file does not exist: " + file.string()
        );
    }

    if (!fs::is_regular_file(file)) {
        return Result::failure(
            1,
            "path is not a regular file: " + file.string()
        );
    }

    return Result::success(file.string());
}


// ---------------------------------------------------------------------------
// Idempotent filesystem operation
// ---------------------------------------------------------------------------
//
// A robust automation function often behaves safely when executed multiple
// times. Bash's mkdir -p is a common example.
//
// C++17's create_directories behaves similarly for an existing directory.

Result ensureDirectory(const fs::path& directory) {
    std::error_code error;

    fs::create_directories(directory, error);

    if (error) {
        return Result::failure(
            1,
            "cannot create directory '" +
            directory.string() +
            "': " +
            error.message()
        );
    }

    return Result::success(directory.string());
}


// ---------------------------------------------------------------------------
// Retry abstraction
// ---------------------------------------------------------------------------
//
// Bash automation often wraps a command in a retry function.
//
// Important engineering considerations:
//   - only retry transient failures
//   - cap attempts
//   - use a timeout
//   - consider exponential backoff
//   - ensure the operation is safe to repeat
//
// The C++ function accepts a callable, making the policy reusable.

using Operation = std::function<Result()>;

Result retry(
    const Operation& operation,
    int attempts,
    std::chrono::milliseconds delay
) {
    if (attempts <= 0) {
        return Result::failure(
            2,
            "attempt count must be positive"
        );
    }

    Result last = Result::failure(
        1,
        "operation did not execute"
    );

    for (int attempt = 1; attempt <= attempts; ++attempt) {
        last = operation();

        if (last.ok()) {
            return last;
        }

        if (attempt < attempts) {
            std::this_thread::sleep_for(delay);
        }
    }

    return last;
}


// ---------------------------------------------------------------------------
// Task abstraction
// ---------------------------------------------------------------------------
//
// Bash functions naturally form a small command library:
//
//   status() { ...; }
//   version() { ...; }
//   echo_command() { ...; }
//
// A C++ command table provides a structured equivalent.

using CommandHandler =
    std::function<int(const std::vector<std::string>&)>;

struct Task {
    std::string name;
    std::string description;
    CommandHandler handler;
};

class TaskRunner {
public:
    explicit TaskRunner(std::vector<Task> tasks) {
        for (auto& task : tasks) {
            tasks_.emplace(task.name, std::move(task));
        }
    }

    void listTasks() const {
        for (const auto& [name, task] : tasks_) {
            std::cout
                << std::left
                << std::setw(12)
                << name
                << " "
                << task.description
                << '\n';
        }
    }

    int run(
        const std::string& name,
        const std::vector<std::string>& arguments
    ) const {
        const auto iterator = tasks_.find(name);

        if (iterator == tasks_.end()) {
            logError("unknown task: " + name);
            return 127;
        }

        logInfo("starting task: " + name);

        const int status = iterator->second.handler(arguments);

        if (status == 0) {
            logInfo("task completed: " + name);
        }
        else {
            logError(
                "task failed: " +
                name +
                ", status=" +
                std::to_string(status)
            );
        }

        return status;
    }

private:
    std::map<std::string, Task> tasks_;
};


// ---------------------------------------------------------------------------
// Command implementations
// ---------------------------------------------------------------------------

int commandStatus(
    const std::vector<std::string>&
) {
    std::cout << "status: system is operational\n";
    return 0;
}

int commandVersion(
    const std::vector<std::string>&
) {
    std::cout << "version: 1.0.0\n";
    return 0;
}

int commandEcho(
    const std::vector<std::string>& arguments
) {
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        if (index != 0) {
            std::cout << ' ';
        }

        std::cout << arguments[index];
    }

    std::cout << '\n';
    return 0;
}

int commandValidate(
    const std::vector<std::string>& arguments
) {
    if (arguments.size() != 1) {
        logError("validate requires exactly one username");
        return 2;
    }

    const Result result = validateUsername(arguments.front());

    if (!result.ok()) {
        logError(result.output);
        return result.status;
    }

    std::cout
        << "valid username: "
        << result.output
        << '\n';

    return 0;
}


// ---------------------------------------------------------------------------
// Deployment-style task
// ---------------------------------------------------------------------------
//
// The task models a small automation workflow:
//
//   1. validate application name
//   2. create an output directory
//   3. perform an operation
//   4. retry transient failure
//   5. return a shell-compatible status
//
// This is intentionally self-contained and does not perform a real deployment.

class DeploymentService {
public:
    explicit DeploymentService(fs::path root)
        : root_(std::move(root)) {}

    Result prepare() const {
        if (root_.empty()) {
            return Result::failure(
                2,
                "deployment root is empty"
            );
        }

        const Result directoryResult =
            ensureDirectory(root_);

        if (!directoryResult.ok()) {
            return directoryResult;
        }

        const fs::path releases = root_ / "releases";

        return ensureDirectory(releases);
    }

    Result deploy(const std::string& applicationName) {
        const Result validation =
            validateUsername(applicationName);

        if (!validation.ok()) {
            return validation;
        }

        const Result preparation = prepare();

        if (!preparation.ok()) {
            return preparation;
        }

        const fs::path releaseDirectory =
            root_ / "releases" / validation.output;

        const Result directoryResult =
            ensureDirectory(releaseDirectory);

        if (!directoryResult.ok()) {
            return directoryResult;
        }

        int operationAttempts = 0;

        const Result deployment =
            retry(
                [&]() -> Result {
                    ++operationAttempts;

                    /*
                     * A real deployment would perform a carefully validated
                     * idempotent operation here. The simulation succeeds on
                     * the third attempt to demonstrate retry behavior.
                     */
                    if (operationAttempts < 3) {
                        return Result::failure(
                            1,
                            "simulated transient deployment failure"
                        );
                    }

                    const fs::path marker =
                        releaseDirectory / "DEPLOYED";

                    std::ofstream markerFile(marker);

                    if (!markerFile) {
                        return Result::failure(
                            1,
                            "cannot create deployment marker"
                        );
                    }

                    markerFile
                        << "application="
                        << validation.output
                        << '\n'
                        << "attempts="
                        << operationAttempts
                        << '\n';

                    return Result::success(
                        "deployment completed"
                    );
                },
                4,
                std::chrono::milliseconds(25)
            );

        if (!deployment.ok()) {
            return deployment;
        }

        return Result::success(
            deployment.output +
            " after " +
            std::to_string(operationAttempts) +
            " attempts"
        );
    }

private:
    fs::path root_;
};


// ---------------------------------------------------------------------------
// Task runner construction
// ---------------------------------------------------------------------------

TaskRunner buildTaskRunner() {
    return TaskRunner({
        {
            "status",
            "display service status",
            commandStatus
        },
        {
            "version",
            "display application version",
            commandVersion
        },
        {
            "echo",
            "print supplied arguments",
            commandEcho
        },
        {
            "validate",
            "validate a username",
            commandValidate
        }
    });
}


// ---------------------------------------------------------------------------
// Unit-style tests
// ---------------------------------------------------------------------------

void require(
    bool condition,
    const std::string& message
) {
    if (!condition) {
        throw std::runtime_error(
            "test failure: " + message
        );
    }
}

void runSelfTests() {
    std::cout << "\n=== SELF-TESTS ===\n";

    require(
        greet("Atul") == "Hello, Atul",
        "greet"
    );

    const Result valid =
        validateUsername("Atul_123");

    require(
        valid.ok() &&
        valid.output == "atul_123",
        "valid username"
    );

    const Result invalid =
        validateUsername("bad-name");

    require(
        invalid.status == 3,
        "invalid username status"
    );

    const ParseResult parsed =
        parseArguments({
            "--verbose",
            "--name",
            "Atul",
            "report.txt"
        });

    require(
        parsed.status == 0 &&
        parsed.options.has_value(),
        "argument parser"
    );

    require(
        parsed.options->verbose,
        "verbose option"
    );

    require(
        parsed.options->name == "Atul",
        "name option"
    );

    require(
        parsed.options->files.size() == 1,
        "file argument"
    );

    const Result firstDirectory =
        ensureDirectory(
            fs::temp_directory_path() /
            "bash-functions-cpp-study" /
            "nested"
        );

    require(
        firstDirectory.ok(),
        "directory creation"
    );

    const Result secondDirectory =
        ensureDirectory(
            fs::temp_directory_path() /
            "bash-functions-cpp-study" /
            "nested"
        );

    require(
        secondDirectory.ok(),
        "idempotent directory creation"
    );

    std::cout << "All self-tests passed.\n";
}


// ---------------------------------------------------------------------------
// Demonstration of the conceptual Bash mapping
// ---------------------------------------------------------------------------

void printBashConceptMapping() {
    std::cout << "\n=== BASH TO C++ CONCEPT MAPPING ===\n";

    std::cout
        << "$1, $2, ...      -> function parameters / argv elements\n"
        << "$#               -> arguments.size()\n"
        << '\"$@\"             -> vector<string> containing each argument\n'
        << "return 0         -> return 0 from a command handler\n"
        << "$?               -> captured integer status\n"
        << "local variable   -> local C++ variable / object scope\n"
        << "case dispatch    -> map<string, CommandHandler>\n"
        << "source library   -> reusable C++ functions/classes\n"
        << "trap cleanup     -> RAII/destructor or explicit cleanup\n"
        << "mkdir -p         -> filesystem::create_directories\n"
        << "stderr           -> std::cerr\n";
}


// ---------------------------------------------------------------------------
// Main application
// ---------------------------------------------------------------------------

int applicationMain(
    const std::vector<std::string>& arguments
) {
    const ParseResult parsed =
        parseArguments(arguments);

    if (parsed.status != 0 ||
        !parsed.options.has_value()) {
        logError(parsed.error);
        return parsed.status;
    }

    const Options& options = *parsed.options;

    std::cout
        << greet(options.name)
        << '\n';

    if (options.verbose) {
        std::cout
            << "Files received: "
            << options.files.size()
            << '\n';
    }

    for (const std::string& file : options.files) {
        std::cout
            << "Processing: "
            << file
            << '\n';
    }

    return 0;
}

} // namespace app


int main(int argc, char* argv[]) {
    try {
        std::cout
            << "BASH FUNCTIONS: C++17 TECHNICAL CASE STUDY\n";

        std::vector<std::string> arguments;

        for (int index = 1; index < argc; ++index) {
            arguments.emplace_back(argv[index]);
        }

        if (!arguments.empty()) {
            const int cliStatus =
                app::applicationMain(arguments);

            if (cliStatus != 0) {
                return cliStatus;
            }
        }

        std::cout << "\n=== BASIC FUNCTIONS ===\n";
        std::cout << app::greet("Atul") << '\n';

        std::cout << "\n=== ARGUMENT VALIDATION ===\n";

        const app::Result username =
            app::validateUsername("Developer_01");

        std::cout
            << "Status: "
            << username.status
            << "\nValue: "
            << username.output
            << '\n';

        std::cout << "\n=== COMMAND RUNNER ===\n";

        app::TaskRunner runner =
            app::buildTaskRunner();

        std::cout << "Available commands:\n";
        runner.listTasks();

        std::cout << "\nRunning status:\n";
        int status =
            runner.run("status", {});

        std::cout
            << "Exit-style status: "
            << status
            << '\n';

        std::cout << "\nRunning echo:\n";

        status =
            runner.run(
                "echo",
                {"hello", "reusable", "functions"}
            );

        std::cout
            << "Exit-style status: "
            << status
            << '\n';

        std::cout << "\nRunning invalid command:\n";

        status =
            runner.run(
                "missing",
                {}
            );

        std::cout
            << "Exit-style status: "
            << status
            << '\n';

        std::cout << "\n=== RETRY CASE STUDY ===\n";

        int attempts = 0;

        const app::Result retryResult =
            app::retry(
                [&]() -> app::Result {
                    ++attempts;

                    if (attempts < 3) {
                        return app::Result::failure(
                            1,
                            "transient failure"
                        );
                    }

                    return app::Result::success(
                        "operation succeeded"
                    );
                },
                4,
                std::chrono::milliseconds(20)
            );

        std::cout
            << "Attempts: "
            << attempts
            << '\n'
            << "Status: "
            << retryResult.status
            << '\n'
            << "Output: "
            << retryResult.output
            << '\n';

        std::cout << "\n=== DEPLOYMENT CASE STUDY ===\n";

        const fs::path temporaryRoot =
            fs::temp_directory_path() /
            "bash-functions-deployment-study";

        std::error_code cleanupError;
        fs::remove_all(temporaryRoot, cleanupError);

        app::DeploymentService deployment(
            temporaryRoot
        );

        const app::Result deploymentResult =
            deployment.deploy("analytics_service");

        std::cout
            << "Status: "
            << deploymentResult.status
            << '\n'
            << "Output: "
            << deploymentResult.output
            << '\n';

        if (deploymentResult.ok()) {
            const fs::path marker =
                temporaryRoot /
                "releases" /
                "analytics_service" /
                "DEPLOYED";

            std::cout
                << "Deployment marker exists: "
                << std::boolalpha
                << fs::exists(marker)
                << '\n';
        }

        std::cout << "\n=== TESTS ===\n";
        app::runSelfTests();

        app::printBashConceptMapping();

        std::cout << "\n=== ENGINEERING CONSIDERATIONS ===\n";
        std::cout
            << "1. Keep functions focused on one responsibility.\n"
            << "2. Validate arguments before using them.\n"
            << "3. Preserve argument boundaries.\n"
            << "4. Treat status codes as part of the function contract.\n"
            << "5. Keep diagnostics separate from machine-readable output.\n"
            << "6. Make automation operations idempotent where possible.\n"
            << "7. Retry only failures that are plausibly transient.\n"
            << "8. Avoid turning untrusted data into executable commands.\n"
            << "9. Test success and failure paths.\n"
            << "10. Separate reusable logic from the CLI entry point.\n";

        fs::remove_all(
            temporaryRoot,
            cleanupError
        );

        return 0;
    }
    catch (const std::exception& error) {
        std::cerr
            << "[FATAL] "
            << error.what()
            << '\n';

        return 1;
    }
}

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <future>
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

namespace fs = std::filesystem;

/*
 * Bash Fundamentals: C++ Technical Case Study
 *
 * Scenario:
 *     A production-style deployment validation and log-audit utility.
 *
 * The program demonstrates how concepts commonly handled by Bash scripts can
 * be represented in a structured systems program:
 *
 *     - command execution
 *     - exit statuses
 *     - arguments
 *     - environment/configuration
 *     - conditions
 *     - loops
 *     - functions
 *     - filesystem validation
 *     - log processing
 *     - retry logic
 *     - concurrency
 *     - security boundaries
 *     - error handling
 *     - performance considerations
 *
 * Compile:
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic bash_case_study.cpp -o bash_case_study
 *
 * Run:
 *     ./bash_case_study
 *
 * The program uses only the C++ standard library.
 */

// ============================================================================
// 1. OUTPUT HELPERS
// ============================================================================

void section(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}

void subsection(const std::string& title) {
    std::cout << "\n--- " << title << " ---\n";
}

// ============================================================================
// 2. RESULT TYPE
// ============================================================================

struct OperationResult {
    bool success{};
    int exit_code{};
    std::string message;
};

void print_result(const OperationResult& result) {
    std::cout
        << "success=" << std::boolalpha << result.success
        << ", exit_code=" << result.exit_code
        << ", message=" << result.message
        << "\n";
}

// ============================================================================
// 3. CONFIGURATION
// ============================================================================

struct DeploymentConfig {
    std::string application;
    std::string version;
    std::string environment;
    fs::path log_directory;
    int maximum_retries{3};
};

class ConfigurationError : public std::runtime_error {
public:
    explicit ConfigurationError(const std::string& message)
        : std::runtime_error(message) {}
};

// ============================================================================
// 4. VALIDATOR
// ============================================================================

class ConfigurationValidator {
public:
    static std::vector<std::string> validate(
        const DeploymentConfig& config
    ) {
        std::vector<std::string> errors;

        if (config.application.empty()) {
            errors.emplace_back("application is required");
        }

        if (config.version.empty()) {
            errors.emplace_back("version is required");
        } else if (!is_semantic_version(config.version)) {
            errors.emplace_back(
                "version must have the form major.minor.patch"
            );
        }

        if (!is_allowed_environment(config.environment)) {
            errors.emplace_back(
                "environment must be development, staging, or production"
            );
        }

        if (config.maximum_retries < 1) {
            errors.emplace_back(
                "maximum_retries must be at least 1"
            );
        }

        return errors;
    }

private:
    static bool is_semantic_version(const std::string& version) {
        static const std::regex pattern(R"(^[0-9]+\.[0-9]+\.[0-9]+$)");
        return std::regex_match(version, pattern);
    }

    static bool is_allowed_environment(
        const std::string& environment
    ) {
        return environment == "development"
            || environment == "staging"
            || environment == "production";
    }
};

// ============================================================================
// 5. LOG DATA
// ============================================================================

struct LogStatistics {
    std::size_t files{};
    std::size_t lines{};
    std::size_t errors{};
    std::size_t warnings{};

    void merge(const LogStatistics& other) {
        files += other.files;
        lines += other.lines;
        errors += other.errors;
        warnings += other.warnings;
    }
};

class LogAuditor {
public:
    LogStatistics analyze_directory(const fs::path& directory) const {
        if (!fs::exists(directory)) {
            throw std::runtime_error(
                "Log directory does not exist: " + directory.string()
            );
        }

        if (!fs::is_directory(directory)) {
            throw std::runtime_error(
                "Path is not a directory: " + directory.string()
            );
        }

        LogStatistics total;

        for (const auto& entry : fs::directory_iterator(directory)) {
            if (!entry.is_regular_file()) {
                continue;
            }

            if (entry.path().extension() != ".log") {
                continue;
            }

            total.merge(analyze_file(entry.path()));
        }

        return total;
    }

private:
    LogStatistics analyze_file(const fs::path& file) const {
        std::ifstream input(file);

        if (!input) {
            throw std::runtime_error(
                "Unable to open log file: " + file.string()
            );
        }

        LogStatistics statistics;
        statistics.files = 1;

        std::string line;

        while (std::getline(input, line)) {
            ++statistics.lines;

            if (line.find("ERROR") != std::string::npos) {
                ++statistics.errors;
            }

            if (line.find("WARNING") != std::string::npos) {
                ++statistics.warnings;
            }
        }

        return statistics;
    }
};

// ============================================================================
// 6. LOG AUDIT REPORT
// ============================================================================

class ReportPrinter {
public:
    static void print(const LogStatistics& statistics) {
        std::cout << "Files:    " << statistics.files << "\n";
        std::cout << "Lines:    " << statistics.lines << "\n";
        std::cout << "Errors:   " << statistics.errors << "\n";
        std::cout << "Warnings: " << statistics.warnings << "\n";
    }
};

// ============================================================================
// 7. EXIT STATUS MODEL
// ============================================================================

enum class ExitCode : int {
    Success = 0,
    ConfigurationError = 2,
    ValidationError = 3,
    OperationalError = 4,
    SecurityError = 5
};

int to_int(ExitCode code) {
    return static_cast<int>(code);
}

// ============================================================================
// 8. SAFE PATH VALIDATION
// ============================================================================

class PathValidator {
public:
    static bool is_regular_file(const fs::path& path) {
        std::error_code error;
        const bool regular = fs::is_regular_file(path, error);
        return !error && regular;
    }

    static bool is_directory(const fs::path& path) {
        std::error_code error;
        const bool directory = fs::is_directory(path, error);
        return !error && directory;
    }
};

// ============================================================================
// 9. COMMAND ARGUMENT MODEL
// ============================================================================

struct Command {
    std::string executable;
    std::vector<std::string> arguments;
};

/*
 * This class deliberately does NOT concatenate arguments into shell source.
 *
 * A Bash command such as:
 *
 *     grep -- "$pattern" "$file"
 *
 * relies on correct quoting and argument boundaries.
 *
 * A C++ application can represent the same idea structurally:
 *
 *     Command{
 *         "grep",
 *         {"--", pattern, file}
 *     };
 *
 * Actual process creation is platform-specific and is intentionally kept
 * separate from this data model.
 */
class CommandBuilder {
public:
    static Command build_log_search(
        const std::string& pattern,
        const fs::path& file
    ) {
        if (pattern.empty()) {
            throw std::invalid_argument(
                "Search pattern cannot be empty"
            );
        }

        return Command{
            "grep",
            {
                "--",
                pattern,
                file.string()
            }
        };
    }
};

// ============================================================================
// 10. COMMAND DESCRIPTION
// ============================================================================

void print_command(const Command& command) {
    std::cout << "Executable: " << command.executable << "\n";
    std::cout << "Arguments:\n";

    for (std::size_t index = 0; index < command.arguments.size(); ++index) {
        std::cout
            << "  [" << index << "] "
            << std::quoted(command.arguments[index])
            << "\n";
    }
}

// ============================================================================
// 11. RETRY ENGINE
// ============================================================================

class RetryEngine {
public:
    using Operation = std::function<bool(int)>;

    explicit RetryEngine(
        int maximum_attempts,
        std::chrono::milliseconds base_delay
    )
        : maximum_attempts_(maximum_attempts),
          base_delay_(base_delay) {
        if (maximum_attempts_ < 1) {
            throw std::invalid_argument(
                "maximum_attempts must be positive"
            );
        }
    }

    bool run(const Operation& operation) const {
        for (int attempt = 1;
             attempt <= maximum_attempts_;
             ++attempt) {

            std::cout
                << "Attempt "
                << attempt
                << "/"
                << maximum_attempts_
                << "\n";

            if (operation(attempt)) {
                return true;
            }

            if (attempt < maximum_attempts_) {
                const auto multiplier =
                    static_cast<int>(1u << (attempt - 1));

                const auto delay =
                    base_delay_ * multiplier;

                std::cout
                    << "Retrying after "
                    << delay.count()
                    << " ms\n";

                std::this_thread::sleep_for(delay);
            }
        }

        return false;
    }

private:
    int maximum_attempts_;
    std::chrono::milliseconds base_delay_;
};

// ============================================================================
// 12. CONCURRENCY
// ============================================================================

struct ConcurrentAuditResult {
    std::string filename;
    LogStatistics statistics;
};

ConcurrentAuditResult analyze_file_concurrently(
    const fs::path& file
) {
    LogStatistics statistics;

    std::ifstream input(file);

    if (!input) {
        throw std::runtime_error(
            "Cannot open " + file.string()
        );
    }

    statistics.files = 1;

    std::string line;

    while (std::getline(input, line)) {
        ++statistics.lines;

        if (line.find("ERROR") != std::string::npos) {
            ++statistics.errors;
        }

        if (line.find("WARNING") != std::string::npos) {
            ++statistics.warnings;
        }
    }

    return {
        file.filename().string(),
        statistics
    };
}

LogStatistics analyze_directory_concurrently(
    const fs::path& directory
) {
    std::vector<fs::path> files;

    for (const auto& entry : fs::directory_iterator(directory)) {
        if (entry.is_regular_file()
            && entry.path().extension() == ".log") {
            files.push_back(entry.path());
        }
    }

    std::vector<std::future<ConcurrentAuditResult>> futures;

    for (const auto& file : files) {
        futures.push_back(
            std::async(
                std::launch::async,
                analyze_file_concurrently,
                file
            )
        );
    }

    LogStatistics total;

    for (auto& future : futures) {
        const ConcurrentAuditResult result = future.get();
        total.merge(result.statistics);
    }

    return total;
}

// ============================================================================
// 13. TEMPORARY TEST ENVIRONMENT
// ============================================================================

class TemporaryDeploymentEnvironment {
public:
    TemporaryDeploymentEnvironment() {
        root_ = fs::temp_directory_path()
            / ("bash_case_study_" + std::to_string(
                std::chrono::steady_clock::now()
                    .time_since_epoch()
                    .count()
            ));

        fs::create_directories(root_);
        log_directory_ = root_ / "logs";
        fs::create_directories(log_directory_);

        create_log(
            "application.log",
            {
                "INFO application started",
                "WARNING response latency increased",
                "ERROR database unavailable",
                "INFO retry initiated",
                "ERROR database timeout"
            }
        );

        create_log(
            "worker.log",
            {
                "INFO worker started",
                "WARNING queue depth increased",
                "INFO worker completed",
                "ERROR worker timeout"
            }
        );

        create_log(
            "security.log",
            {
                "INFO authentication successful",
                "WARNING repeated login attempt",
                "ERROR authorization failure"
            }
        );
    }

    ~TemporaryDeploymentEnvironment() {
        std::error_code error;
        fs::remove_all(root_, error);
    }

    const fs::path& root() const {
        return root_;
    }

    const fs::path& logs() const {
        return log_directory_;
    }

private:
    fs::path root_;
    fs::path log_directory_;

    void create_log(
        const std::string& filename,
        const std::vector<std::string>& lines
    ) {
        const fs::path file = log_directory_ / filename;
        std::ofstream output(file);

        if (!output) {
            throw std::runtime_error(
                "Unable to create test log: " + file.string()
            );
        }

        for (const auto& line : lines) {
            output << line << "\n";
        }
    }
};

// ============================================================================
// 14. CONFIGURATION DEMONSTRATION
// ============================================================================

void demonstrate_configuration() {
    subsection("Configuration validation");

    DeploymentConfig valid{
        "market-api",
        "2.4.1",
        "production",
        "/var/log/market-api",
        3
    };

    const auto errors =
        ConfigurationValidator::validate(valid);

    if (errors.empty()) {
        std::cout << "Configuration is valid.\n";
    } else {
        for (const auto& error : errors) {
            std::cout << "ERROR: " << error << "\n";
        }
    }

    DeploymentConfig invalid{
        "",
        "2",
        "unknown",
        "/invalid",
        0
    };

    const auto invalid_errors =
        ConfigurationValidator::validate(invalid);

    std::cout << "\nInvalid configuration:\n";

    for (const auto& error : invalid_errors) {
        std::cout << "ERROR: " << error << "\n";
    }
}

// ============================================================================
// 15. CONDITIONAL LOGIC
// ============================================================================

void demonstrate_conditions() {
    subsection("Conditions");

    const int error_count = 3;

    if (error_count == 0) {
        std::cout << "No errors detected.\n";
    } else if (error_count < 5) {
        std::cout << "Small number of errors detected.\n";
    } else {
        std::cout << "High error count detected.\n";
    }

    std::cout
        << "Production threshold exceeded: "
        << std::boolalpha
        << (error_count >= 5)
        << "\n";
}

// ============================================================================
// 16. LOOPING
// ============================================================================

void demonstrate_loops() {
    subsection("Loops");

    std::vector<std::string> stages{
        "validate",
        "prepare",
        "deploy",
        "verify"
    };

    for (const auto& stage : stages) {
        std::cout << "Stage: " << stage << "\n";
    }

    std::cout << "\nNumeric loop:\n";

    for (int attempt = 1; attempt <= 3; ++attempt) {
        std::cout << "Attempt: " << attempt << "\n";
    }

    std::cout << "\nWhile loop:\n";

    int counter = 0;

    while (counter < 3) {
        std::cout << "counter=" << counter << "\n";
        ++counter;
    }
}

// ============================================================================
// 17. STRING PROCESSING
// ============================================================================

void demonstrate_string_processing() {
    subsection("String processing");

    const std::string path =
        "/var/log/market-api/application.log";

    const auto separator =
        path.find_last_of('/');

    const std::string filename =
        separator == std::string::npos
            ? path
            : path.substr(separator + 1);

    std::cout << "Path: " << path << "\n";
    std::cout << "Filename: " << filename << "\n";

    const bool is_log =
        filename.size() >= 4
        && filename.substr(filename.size() - 4) == ".log";

    std::cout
        << "Is log file: "
        << std::boolalpha
        << is_log
        << "\n";
}

// ============================================================================
// 18. BASH CONCEPT MAPPING
// ============================================================================

void demonstrate_bash_concepts() {
    subsection("Bash concept mapping");

    const std::map<std::string, std::string> concepts{
        {"Variable", "C++ variable"},
        {"Condition", "if / else"},
        {"for loop", "range-based or indexed for"},
        {"while loop", "while"},
        {"Function", "function"},
        {"Array", "std::vector"},
        {"Associative array", "std::map or std::unordered_map"},
        {"Exit status", "return value / process exit code"},
        {"File test", "std::filesystem"},
        {"Command arguments", "structured vector of strings"},
        {"Pipeline", "explicit process/stream composition"},
        {"Environment", "configuration or OS environment APIs"}
    };

    for (const auto& [bash_concept, cpp_concept] : concepts) {
        std::cout
            << std::left
            << std::setw(24)
            << bash_concept
            << " -> "
            << cpp_concept
            << "\n";
    }
}

// ============================================================================
// 19. COMMAND INJECTION SECURITY
// ============================================================================

void demonstrate_command_injection_security() {
    subsection("Command injection security model");

    const std::string untrusted_input =
        "report; rm -rf /";

    Command command =
        CommandBuilder::build_log_search(
            untrusted_input,
            "/tmp/application.log"
        );

    std::cout
        << "Untrusted value stored as an argument:\n";

    print_command(command);

    std::cout << R"(
The semicolon above is data in the Command representation.

A dangerous shell-oriented design would concatenate:

    "grep " + input + " file"

and then pass that complete string to a shell.

The safer architectural boundary is:

    executable
    +
    separate arguments

rather than:

    executable
    +
    shell source

This principle is especially important for automation, deployment tools,
CI/CD systems, server administration, and applications that accept external
input.
)";
}

// ============================================================================
// 20. LOG AUDIT
// ============================================================================

void demonstrate_log_audit(
    const fs::path& log_directory
) {
    subsection("Sequential log audit");

    LogAuditor auditor;

    const LogStatistics statistics =
        auditor.analyze_directory(log_directory);

    ReportPrinter::print(statistics);
}

// ============================================================================
// 21. CONCURRENT LOG AUDIT
// ============================================================================

void demonstrate_concurrent_audit(
    const fs::path& log_directory
) {
    subsection("Concurrent log audit");

    const LogStatistics statistics =
        analyze_directory_concurrently(log_directory);

    ReportPrinter::print(statistics);
}

// ============================================================================
// 22. RETRY DEMONSTRATION
// ============================================================================

void demonstrate_retry() {
    subsection("Retry engine");

    RetryEngine retry_engine(
        5,
        std::chrono::milliseconds(10)
    );

    const bool success =
        retry_engine.run(
            [](int attempt) {
                // Simulate an operation that becomes successful
                // on its third attempt.
                return attempt >= 3;
            }
        );

    std::cout
        << "Operation succeeded: "
        << std::boolalpha
        << success
        << "\n";
}

// ============================================================================
// 23. PERFORMANCE DEMONSTRATION
// ============================================================================

void demonstrate_performance(
    const fs::path& log_directory
) {
    subsection("Performance comparison");

    LogAuditor sequential_auditor;

    const auto sequential_start =
        std::chrono::steady_clock::now();

    const LogStatistics sequential =
        sequential_auditor.analyze_directory(log_directory);

    const auto sequential_end =
        std::chrono::steady_clock::now();

    const auto sequential_duration =
        std::chrono::duration_cast<
            std::chrono::microseconds
        >(sequential_end - sequential_start);

    const auto concurrent_start =
        std::chrono::steady_clock::now();

    const LogStatistics concurrent =
        analyze_directory_concurrently(log_directory);

    const auto concurrent_end =
        std::chrono::steady_clock::now();

    const auto concurrent_duration =
        std::chrono::duration_cast<
            std::chrono::microseconds
        >(concurrent_end - concurrent_start);

    std::cout
        << "Sequential files: "
        << sequential.files
        << "\n";

    std::cout
        << "Concurrent files: "
        << concurrent.files
        << "\n";

    std::cout
        << "Sequential duration: "
        << sequential_duration.count()
        << " microseconds\n";

    std::cout
        << "Concurrent duration: "
        << concurrent_duration.count()
        << " microseconds\n";

    std::cout << R"(
Concurrency is not automatically faster.

For very small files, thread and scheduling overhead can dominate.

For many independent I/O operations, concurrency may improve wall-clock time.

Production decisions should be based on measurement and workload characteristics.
)";
}

// ============================================================================
// 24. FAILURE CONDITIONS
// ============================================================================

void demonstrate_failure_conditions(
    const fs::path& root
) {
    subsection("Failure conditions");

    const std::vector<fs::path> invalid_paths{
        root / "does-not-exist",
        root
    };

    for (const auto& invalid_path : invalid_paths) {
        try {
            if (!PathValidator::is_directory(invalid_path)) {
                throw std::runtime_error(
                    "Not a valid directory: "
                    + invalid_path.string()
                );
            }

            std::cout
                << "Directory accepted: "
                << invalid_path
                << "\n";
        } catch (const std::exception& error) {
            std::cout
                << "Handled failure: "
                << error.what()
                << "\n";
        }
    }
}

// ============================================================================
// 25. FILE EDGE CASES
// ============================================================================

void demonstrate_edge_cases(
    const fs::path& root
) {
    subsection("Filesystem edge cases");

    const fs::path unusual_filename =
        root / "file with spaces.txt";

    {
        std::ofstream output(unusual_filename);

        if (!output) {
            throw std::runtime_error(
                "Could not create unusual filename"
            );
        }

        output << "safe content\n";
    }

    std::cout
        << "Filename with spaces exists: "
        << std::boolalpha
        << fs::exists(unusual_filename)
        << "\n";

    std::error_code error;
    fs::remove(unusual_filename, error);

    if (error) {
        throw std::runtime_error(
            "Unable to remove test file: "
            + error.message()
        );
    }
}

// ============================================================================
// 26. PIPELINE ARCHITECTURE
// ============================================================================

class PipelineStage {
public:
    using Processor =
        std::function<std::vector<std::string>(
            const std::vector<std::string>&
        )>;

    explicit PipelineStage(Processor processor)
        : processor_(std::move(processor)) {}

    std::vector<std::string> run(
        const std::vector<std::string>& input
    ) const {
        return processor_(input);
    }

private:
    Processor processor_;
};

void demonstrate_pipeline_architecture() {
    subsection("Pipeline architecture");

    const std::vector<std::string> records{
        "INFO startup",
        "WARNING slow response",
        "ERROR database failure",
        "INFO retry",
        "ERROR timeout"
    };

    PipelineStage error_filter(
        [](const std::vector<std::string>& input) {
            std::vector<std::string> output;

            for (const auto& record : input) {
                if (record.find("ERROR") != std::string::npos) {
                    output.push_back(record);
                }
            }

            return output;
        }
    );

    PipelineStage formatter(
        [](const std::vector<std::string>& input) {
            std::vector<std::string> output;

            for (const auto& record : input) {
                output.push_back("[ALERT] " + record);
            }

            return output;
        }
    );

    const auto filtered =
        error_filter.run(records);

    const auto formatted =
        formatter.run(filtered);

    for (const auto& record : formatted) {
        std::cout << record << "\n";
    }

    std::cout << R"(
This models the conceptual structure of:

    producer | grep ERROR | transform

In Bash, the shell connects process streams.

In C++, a pipeline can instead be represented as explicit data transformations.
)";
}

// ============================================================================
// 27. EXIT STATUS DISCUSSION
// ============================================================================

void demonstrate_exit_status() {
    subsection("Exit-status design");

    const std::vector<OperationResult> results{
        {true, 0, "operation completed"},
        {false, 2, "invalid configuration"},
        {false, 4, "operational failure"},
        {false, 5, "security validation failure"}
    };

    for (const auto& result : results) {
        print_result(result);
    }

    std::cout << R"(
Unix conventions normally treat exit status 0 as success and nonzero values
as failure or special conditions.

A production automation system should document the meanings of its nonzero
statuses so callers can respond appropriately.
)";
}

// ============================================================================
// 28. SECURITY CHECKLIST
// ============================================================================

void print_security_checklist() {
    subsection("Security checklist");

    const std::vector<std::string> checklist{
        "Do not concatenate untrusted input into shell commands.",
        "Prefer structured argument lists.",
        "Quote Bash expansions.",
        "Validate file paths and identifiers.",
        "Use option terminators where supported.",
        "Do not expose secrets in diagnostic output.",
        "Use secure temporary resources.",
        "Avoid unsafe PATH manipulation.",
        "Use least privilege.",
        "Validate configuration before destructive operations.",
        "Treat retry behavior as a security and reliability concern.",
        "Handle cleanup on failure."
    };

    for (const auto& item : checklist) {
        std::cout << "[ ] " << item << "\n";
    }
}

// ============================================================================
// 29. ARCHITECTURAL COMPARISON
// ============================================================================

void print_architectural_comparison() {
    subsection("Bash versus C++");

    std::cout << R"(
Bash is strong for:
    * command orchestration
    * filesystem automation
    * pipelines
    * deployment scripts
    * environment setup
    * short operational utilities

C++ is strong for:
    * complex algorithms
    * explicit data structures
    * memory-sensitive systems
    * high-performance processing
    * concurrency
    * large applications
    * strongly structured architectures

A useful engineering boundary is to let Bash coordinate existing programs
while moving substantial application logic into a language better suited to
that complexity.
)";
}

// ============================================================================
// 30. PRODUCTION DESIGN
// ============================================================================

void print_production_design() {
    subsection("Production design");

    std::cout << R"(
A maintainable Bash automation program commonly has:

    shebang
    configuration
    validation
    helper functions
    argument parsing
    main workflow
    error handling
    cleanup
    explicit exit status

The same conceptual layers appear in this C++ case study:

    DeploymentConfig
    ConfigurationValidator
    PathValidator
    LogAuditor
    RetryEngine
    PipelineStage
    reporting
    main orchestration

The language syntax changes, but the engineering concerns remain similar.
)";
}

// ============================================================================
// 31. MAIN CASE STUDY
// ============================================================================

int main() {
    try {
        section(
            "BASH FUNDAMENTALS: "
            "SHELL SYNTAX, VARIABLES, CONDITIONS, LOOPS"
        );

        std::cout << R"(
This program models a realistic deployment-support workflow.

The system validates deployment configuration, creates a temporary log
environment, audits application logs, demonstrates pipeline-style data
processing, exercises retry logic, handles failures, and discusses secure
command execution.

The Bash concepts represented include:

    variables
    conditions
    loops
    functions
    arrays
    exit statuses
    file tests
    command arguments
    pipelines
    environment/configuration
    error handling
    defensive programming
)";

        section("1. CONFIGURATION");
        demonstrate_configuration();

        section("2. CONTROL FLOW");
        demonstrate_conditions();
        demonstrate_loops();

        section("3. DATA AND STRING PROCESSING");
        demonstrate_string_processing();
        demonstrate_bash_concepts();

        section("4. TEMPORARY LOG ENVIRONMENT");

        TemporaryDeploymentEnvironment environment;

        std::cout
            << "Temporary environment: "
            << environment.root()
            << "\n";

        std::cout
            << "Log directory: "
            << environment.logs()
            << "\n";

        section("5. LOG AUDIT");
        demonstrate_log_audit(environment.logs());

        section("6. CONCURRENT LOG AUDIT");
        demonstrate_concurrent_audit(environment.logs());

        section("7. PIPELINE-STYLE PROCESSING");
        demonstrate_pipeline_architecture();

        section("8. RETRY LOGIC");
        demonstrate_retry();

        section("9. PERFORMANCE");
        demonstrate_performance(environment.logs());

        section("10. ERROR HANDLING");
        demonstrate_failure_conditions(environment.root());

        section("11. EDGE CASES");
        demonstrate_edge_cases(environment.root());

        section("12. SECURITY");
        demonstrate_command_injection_security();
        print_security_checklist();

        section("13. EXIT STATUS");
        demonstrate_exit_status();

        section("14. ARCHITECTURAL DECISIONS");
        print_architectural_comparison();
        print_production_design();

        section("15. IMPORTANT BASH DETAILS");

        std::cout << R"(
Bash variable:
    name="Atul"

Variable expansion:
    echo "$name"

Arithmetic:
    total=$((10 + 20))

Command substitution:
    current=$(date)

Conditional:
    if [[ "$name" == "Atul" ]]; then
        ...
    fi

For loop:
    for item in "$@"; do
        ...
    done

While loop:
    while IFS= read -r line; do
        ...
    done < file

Case:
    case "$action" in
        start) ... ;;
        stop)  ... ;;
        *)     ... ;;
    esac

Function:
    validate() {
        ...
    }

Exit status:
    command
    status=$?

Pipeline:
    producer | consumer

These constructs form the foundation of Bash automation.
)";

        section("16. FINAL ENGINEERING CHECKLIST");

        const std::vector<std::string> checklist{
            "Use the correct Bash interpreter.",
            "Quote variables unless splitting or globbing is intentional.",
            "Validate external input.",
            "Understand exit statuses.",
            "Use functions to separate responsibilities.",
            "Use safe file-processing patterns.",
            "Handle expected failures explicitly.",
            "Use traps for cleanup when appropriate.",
            "Avoid unsafe shell command construction.",
            "Use secure temporary files.",
            "Do not leak secrets through logs or xtrace.",
            "Measure before optimizing.",
            "Control concurrency deliberately.",
            "Prefer idempotent automation.",
            "Use static analysis and tests.",
            "Move complex application logic to an appropriate language."
        };

        for (const auto& item : checklist) {
            std::cout << "[ ] " << item << "\n";
        }

        section("17. CASE STUDY COMPLETED");

        std::cout << R"(
The completed case study demonstrates the engineering boundary between shell
automation and a compiled application.

Bash provides concise syntax for command composition, expansion, conditions,
loops, variables, pipelines, redirection, and operational automation.

C++ provides explicit data structures, type checking, filesystem abstractions,
concurrency, modular classes, detailed error handling, and predictable
application architecture.

The most important shell mental model is:

    parse shell syntax
        -> perform expansions
        -> construct command arguments
        -> apply redirections
        -> execute process
        -> inspect exit status

Understanding this sequence makes Bash scripts significantly easier to
design, debug, secure, and maintain.
)";

        return to_int(ExitCode::Success);
    }
    catch (const ConfigurationError& error) {
        std::cerr
            << "Configuration error: "
            << error.what()
            << "\n";

        return to_int(ExitCode::ConfigurationError);
    }
    catch (const std::invalid_argument& error) {
        std::cerr
            << "Validation error: "
            << error.what()
            << "\n";

        return to_int(ExitCode::ValidationError);
    }
    catch (const std::exception& error) {
        std::cerr
            << "Operational error: "
            << error.what()
            << "\n";

        return to_int(ExitCode::OperationalError);
    }
}

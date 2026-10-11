#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

enum class StageState {
    Pending,
    Running,
    Passed,
    Failed,
    Skipped
};

struct BuildStage {
    std::string name;
    StageState state = StageState::Pending;
    std::string details;
    double elapsed_ms = 0.0;
};

struct BuildConfig {
    std::string project = "telemetry-processor";
    std::string version = "2.4.0";
    fs::path workspace = "build_workspace_cpp";
    bool execute_compiler = false;
    bool run_tests = true;
};

class RepositoryBuild {
private:
    BuildConfig config_;
    std::vector<BuildStage> stages_;
    fs::path source_dir_;
    fs::path build_dir_;
    fs::path dist_dir_;
    bool failed_ = false;

    static std::string quoteForShell(const std::string& value) {
        // This example only accepts compiler arguments from the controlled
        // build configuration, not arbitrary untrusted user input.
        if (value.find_first_of("'\";&|`$<>") != std::string::npos) {
            throw std::invalid_argument("Unsafe shell argument");
        }
        return "'" + value + "'";
    }

    void executeStage(
        const std::string& name,
        const std::function<std::string()>& operation
    ) {
        BuildStage stage;
        stage.name = name;
        stage.state = StageState::Running;
        const auto start = std::chrono::steady_clock::now();

        try {
            stage.details = operation();
            stage.state = StageState::Passed;
        } catch (const std::exception& error) {
            stage.state = StageState::Failed;
            stage.details = error.what();
            failed_ = true;
        }

        stage.elapsed_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - start
        ).count();

        std::cout << '['
                  << (stage.state == StageState::Passed ? "PASS" : "FAIL")
                  << "] " << stage.name << ": " << stage.details << '\n';

        stages_.push_back(stage);
        if (stage.state == StageState::Failed) {
            throw std::runtime_error(stage.name + " failed");
        }
    }

    std::string initializeProject() {
        if (fs::exists(config_.workspace)) {
            const auto marker = config_.workspace / ".cpp-build-demo";
            if (!fs::exists(marker)) {
                if (!fs::is_empty(config_.workspace)) {
                    throw std::runtime_error(
                        "Refusing to overwrite a non-demo workspace"
                    );
                }
            } else {
                fs::remove_all(config_.workspace);
            }
        }

        source_dir_ = config_.workspace / "src";
        build_dir_ = config_.workspace / "build";
        dist_dir_ = config_.workspace / "dist";
        fs::create_directories(source_dir_);
        fs::create_directories(build_dir_);
        fs::create_directories(dist_dir_);

        std::ofstream marker(config_.workspace / ".cpp-build-demo");
        if (!marker) throw std::runtime_error("Cannot write workspace marker");
        marker << "Managed build workspace\n";

        std::ofstream source(source_dir_ / "telemetry.cpp");
        if (!source) throw std::runtime_error("Cannot write source file");
        source << R"CPP(
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Reading {
    std::string sensor;
    double value;
};

int main() {
    const std::vector<Reading> readings = {
        {"temperature-east", 22.4},
        {"temperature-west", 23.1},
        {"pressure-main", 101.3}
    };

    for (const auto& reading : readings) {
        if (reading.sensor.empty()) return 2;
        std::cout << reading.sensor << '=' << reading.value << '\n';
    }
    return 0;
}
)CPP";
        source.close();

        std::ofstream tests(config_.workspace / "test-plan.txt");
        tests << "Expected sensors: 3\n";
        tests << "Expected successful process exit: 0\n";
        tests.close();

        std::ofstream manifest(config_.workspace / "dependencies.txt");
        manifest << "# No third-party libraries; C++ standard library only\n";
        manifest.close();

        return "Initialized telemetry source, test plan, and dependency manifest";
    }

    std::string validateToolchain() {
        if (__cplusplus < 201703L) {
            throw std::runtime_error("C++17 or later is required");
        }
        if (!fs::is_regular_file(source_dir_ / "telemetry.cpp")) {
            throw std::runtime_error("Source file is missing");
        }
        return "C++17 language features and required source files are available";
    }

    std::string installDependencies() {
        std::ifstream manifest(config_.workspace / "dependencies.txt");
        if (!manifest) throw std::runtime_error("Dependency manifest is missing");

        std::string line;
        std::size_t count = 0;
        while (std::getline(manifest, line)) {
            const auto first = line.find_first_not_of(" \t\r");
            if (first == std::string::npos || line[first] == '#') continue;
            ++count;
        }

        if (count != 0) {
            throw std::runtime_error(
                "This standalone example has no package-manager integration "
                "for non-standard dependencies"
            );
        }
        return "Validated dependency manifest; no external packages required";
    }

    std::string compile() {
        const auto source = source_dir_ / "telemetry.cpp";
#ifdef _WIN32
        const auto executable = build_dir_ / "telemetry.exe";
#else
        const auto executable = build_dir_ / "telemetry";
#endif

        // The default mode models the compilation contract without assuming
        // a compiler exists. Set execute_compiler to true to invoke CXX.
        if (!config_.execute_compiler) {
            std::ofstream command(build_dir_ / "compile-command.txt");
            command << "c++ -std=c++17 -Wall -Wextra -Werror "
                    << source.string() << " -o " << executable.string() << '\n';
            command.close();
            return "Recorded reproducible compiler command; execution disabled";
        }

        const char* compiler_env = std::getenv("CXX");
        const std::string compiler = compiler_env ? compiler_env : "c++";

        // Arguments are quoted and validated because std::system invokes a
        // shell. A production runner should prefer an argument-vector process
        // API where the operating system supports one.
        const std::string command =
            quoteForShell(compiler) + " -std=c++17 -Wall -Wextra -Werror " +
            quoteForShell(source.string()) + " -o " +
            quoteForShell(executable.string());

        const int result = std::system(command.c_str());
        if (result != 0) {
            throw std::runtime_error("Compiler command failed");
        }

        compiled_binary_ = executable;
        return "Compiled telemetry processor with " + compiler;
    }

    std::optional<fs::path> compiled_binary_;

    std::string verifyTests() {
        if (!config_.run_tests) return "Tests disabled by configuration";

        if (!config_.execute_compiler || !compiled_binary_) {
            std::ofstream results(build_dir_ / "test-results.txt");
            results << "Compile execution disabled; runtime tests not executed\n";
            results.close();
            return "Recorded test plan; runtime execution disabled";
        }

        const std::string command = quoteForShell(compiled_binary_->string()) +
            " > " + quoteForShell((build_dir_ / "telemetry-output.txt").string());
        const int status = std::system(command.c_str());
        if (status != 0) {
            throw std::runtime_error("Telemetry executable returned a failure status");
        }

        std::ifstream output(build_dir_ / "telemetry-output.txt");
        std::string line;
        int count = 0;
        while (std::getline(output, line)) {
            if (line.find('=') == std::string::npos) {
                throw std::runtime_error("Unexpected telemetry output format");
            }
            ++count;
        }
        if (count != 3) {
            throw std::runtime_error("Expected exactly three sensor readings");
        }

        std::ofstream results(build_dir_ / "test-results.txt");
        results << "PASS: process exit code 0\n";
        results << "PASS: three sensor readings emitted\n";
        return "Validated process exit status and three output records";
    }

    std::string stageRelease() {
        const auto stage_dir = build_dir_ / (config_.project + "-" + config_.version);
        fs::remove_all(stage_dir);
        fs::create_directories(stage_dir);

        fs::copy_file(
            source_dir_ / "telemetry.cpp",
            stage_dir / "telemetry.cpp"
        );
        fs::copy_file(
            config_.workspace / "dependencies.txt",
            stage_dir / "dependencies.txt"
        );
        fs::copy_file(
            config_.workspace / "test-plan.txt",
            stage_dir / "test-plan.txt"
        );

        if (compiled_binary_) {
            fs::copy_file(
                *compiled_binary_,
                stage_dir / compiled_binary_->filename()
            );
        }

        std::ofstream metadata(stage_dir / "release.txt");
        metadata << "project=" << config_.project << '\n';
        metadata << "version=" << config_.version << '\n';
        metadata << "language=c++17\n";
        metadata << "packaging=directory archive input\n";

        return "Staged source, dependency declaration, test plan, and metadata";
    }

    static std::string stateName(StageState state) {
        switch (state) {
            case StageState::Pending: return "pending";
            case StageState::Running: return "running";
            case StageState::Passed: return "passed";
            case StageState::Failed: return "failed";
            case StageState::Skipped: return "skipped";
        }
        return "unknown";
    }

    std::string writeBuildReport() {
        const auto report_path = dist_dir_ / "build-report.txt";
        std::ofstream report(report_path);
        if (!report) throw std::runtime_error("Cannot write build report");

        report << "Build report: " << config_.project << '\n';
        report << "Version: " << config_.version << '\n';
        report << "Platform: " << fs::path(".").root_name().string() << '\n';

        for (const auto& stage : stages_) {
            report << stage.name << " | " << stateName(stage.state)
                   << " | " << std::fixed << std::setprecision(2)
                   << stage.elapsed_ms << " ms | " << stage.details << '\n';
        }
        return "Wrote stage states and durations to build-report.txt";
    }

public:
    explicit RepositoryBuild(BuildConfig config)
        : config_(std::move(config)) {}

    int execute() {
        try {
            executeStage("project initialization", [this] {
                return initializeProject();
            });
            executeStage("toolchain validation", [this] {
                return validateToolchain();
            });
            executeStage("dependency installation", [this] {
                return installDependencies();
            });
            executeStage("source compilation", [this] {
                return compile();
            });
            executeStage("runtime verification", [this] {
                return verifyTests();
            });
            executeStage("release staging", [this] {
                return stageRelease();
            });
            executeStage("build reporting", [this] {
                return writeBuildReport();
            });
        } catch (const std::exception& error) {
            std::cerr << "Build terminated: " << error.what() << '\n';
            try {
                if (fs::exists(dist_dir_)) writeBuildReport();
            } catch (...) {
                std::cerr << "Could not persist the final build report\n";
            }
            return 1;
        }
        return 0;
    }
};

int main(int argc, char* argv[]) {
    BuildConfig config;
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        if (argument == "--compile") {
            config.execute_compiler = true;
        } else if (argument == "--skip-tests") {
            config.run_tests = false;
        } else if (argument == "--workspace" && i + 1 < argc) {
            config.workspace = argv[++i];
        } else {
            std::cerr << "Usage: build_automation [--compile] "
                         "[--skip-tests] [--workspace PATH]\n";
            return 2;
        }
    }

    RepositoryBuild build(config);
    return build.execute();
}

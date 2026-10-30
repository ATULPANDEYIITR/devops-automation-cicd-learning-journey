#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

namespace fs = std::filesystem;

enum class StageStatus {
    Pending,
    Running,
    Succeeded,
    Failed,
    Skipped
};

struct StageResult {
    std::string name;
    StageStatus status;
    double duration_ms;
    std::string detail;
};

struct PipelineConfig {
    fs::path workspace = "ci_cd_cpp_workspace";
    bool build_docker_image = false;
};

class PipelineError : public std::runtime_error {
public:
    explicit PipelineError(const std::string& message)
        : std::runtime_error(message) {}
};

std::string status_name(StageStatus status) {
    switch (status) {
        case StageStatus::Pending: return "pending";
        case StageStatus::Running: return "running";
        case StageStatus::Succeeded: return "succeeded";
        case StageStatus::Failed: return "failed";
        case StageStatus::Skipped: return "skipped";
    }
    return "unknown";
}

std::string read_file(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw PipelineError("Cannot read file: " + path.string());
    }

    std::ostringstream contents;
    contents << input.rdbuf();
    return contents.str();
}

void write_file(const fs::path& path, const std::string& contents) {
    fs::create_directories(path.parent_path());

    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw PipelineError("Cannot write file: " + path.string());
    }

    output << contents;
    if (!output) {
        throw PipelineError("Write failed: " + path.string());
    }
}

void ensure_workspace(const fs::path& root) {
    if (fs::is_symlink(root)) {
        throw PipelineError("Workspace must not be a symbolic link.");
    }

    fs::create_directories(root);
    const fs::path marker = root / ".ci_cd_cpp_workspace";

    if (fs::exists(marker)) {
        if (!fs::is_regular_file(marker)) {
            throw PipelineError("Workspace marker must be a regular file.");
        }
        return;
    }

    if (fs::directory_iterator(root) != fs::directory_iterator()) {
        throw PipelineError(
            "Refusing to use a non-empty directory without a workspace marker."
        );
    }

    write_file(marker, "Managed by the C++17 CI/CD demonstration pipeline.\n");
}

void recreate_directory(const fs::path& path) {
    if (fs::is_symlink(path)) {
        throw PipelineError("Refusing to remove symbolic link: " + path.string());
    }

    std::error_code error;
    fs::remove_all(path, error);
    if (error) {
        throw PipelineError("Cannot clean directory: " + error.message());
    }

    fs::create_directories(path);
}

const std::string SERVICE_SOURCE = R"cpp(
#include <cctype>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

class Inventory {
private:
    std::map<std::string, int> items_;

public:
    void add(const std::string& sku, int quantity) {
        if (sku.empty() || sku.size() > 32) {
            throw std::invalid_argument("SKU length is invalid");
        }

        for (unsigned char character : sku) {
            if (!std::isalnum(character) && character != '-') {
                throw std::invalid_argument("SKU contains an invalid character");
            }
        }

        if (quantity <= 0) {
            throw std::invalid_argument("Quantity must be positive");
        }

        const auto result = items_.emplace(sku, quantity);
        if (!result.second) {
            throw std::invalid_argument("Duplicate SKU");
        }
    }

    int quantity_of(const std::string& sku) const {
        const auto found = items_.find(sku);
        if (found == items_.end()) {
            throw std::out_of_range("Unknown SKU");
        }
        return found->second;
    }

    std::size_t size() const noexcept {
        return items_.size();
    }

    void print() const {
        for (const auto& [sku, quantity] : items_) {
            std::cout << sku << "," << quantity << "\n";
        }
    }
};

void run_self_tests() {
    Inventory inventory;
    inventory.add("SKU-100", 25);
    inventory.add("SKU-200", 12);

    if (inventory.size() != 2 || inventory.quantity_of("SKU-100") != 25) {
        throw std::runtime_error("Inventory assertion failed");
    }

    bool duplicate_rejected = false;
    try {
        inventory.add("SKU-100", 5);
    } catch (const std::invalid_argument&) {
        duplicate_rejected = true;
    }

    if (!duplicate_rejected) {
        throw std::runtime_error("Duplicate SKU was accepted");
    }

    bool invalid_quantity_rejected = false;
    try {
        inventory.add("SKU-300", 0);
    } catch (const std::invalid_argument&) {
        invalid_quantity_rejected = true;
    }

    if (!invalid_quantity_rejected) {
        throw std::runtime_error("Invalid quantity was accepted");
    }

    std::cout << "SELF_TESTS_PASSED\n";
}

int main(int argc, char* argv[]) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--self-test") {
            run_self_tests();
            return 0;
        }

        Inventory inventory;
        inventory.add("SKU-100", 25);
        inventory.add("SKU-200", 12);
        inventory.print();
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Inventory service error: " << error.what() << "\n";
        return 1;
    }
}
)cpp";


std::uint64_t fnv1a64(const std::string& data) {
    // FNV-1a is useful for demonstration-level integrity checks.
    // It is not a cryptographic signature or a replacement for SHA-256.
    std::uint64_t hash = 14695981039346656037ULL;
    for (unsigned char character : data) {
        hash ^= character;
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string hex64(std::uint64_t value) {
    std::ostringstream output;
    output << std::hex << std::setfill('0') << std::setw(16) << value;
    return output.str();
}

std::string lower_copy(std::string value) {
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        }
    );
    return value;
}

void prepare_project(const fs::path& root) {
    recreate_directory(root / "build");
    recreate_directory(root / "package");
    recreate_directory(root / "src");

    write_file(root / "src" / "service.cpp", SERVICE_SOURCE);
}

int run_build(const fs::path& root) {
#ifdef _WIN32
    const std::string executable = "build/service.exe";
#else
    const std::string executable = "build/service";
#endif

    const std::string command =
        "g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic "
        "\"src/service.cpp\" -o \"" + executable + "\"";

    // The command is composed from fixed arguments and a fixed workspace
    // name. No user-supplied value is interpolated into a shell command.
    return std::system(command.c_str());
}

int run_tests(const fs::path& root) {
    (void)root;
#ifdef _WIN32
    const std::string command = "\"build/service.exe\" --self-test";
#else
    const std::string command = "\"build/service\" --self-test";
#endif
    return std::system(command.c_str());
}

std::string scan_source(const fs::path& source_path) {
    const std::string source = read_file(source_path);
    const std::string lowered = lower_copy(source);

    const std::vector<std::string> forbidden = {
        "eval(",
        "popen(",
        "strcpy(",
        "gets("
    };

    std::vector<std::string> findings;

    for (const auto& rule : forbidden) {
        if (lowered.find(rule) != std::string::npos) {
            findings.push_back(rule);
        }
    }

    const std::vector<std::string> credential_markers = {
        "password=\"",
        "secret=\"",
        "api_key=\""
    };

    for (const auto& marker : credential_markers) {
        if (lowered.find(marker) != std::string::npos) {
            findings.push_back("possible hard-coded credential");
        }
    }

    if (!findings.empty()) {
        std::ostringstream message;
        message << "Static security policy failed:";
        for (const auto& finding : findings) {
            message << " " << finding;
        }
        throw PipelineError(message.str());
    }

    return "C++ source passed configured static security rules.";
}

std::string package_application(const fs::path& root) {
#ifdef _WIN32
    const fs::path executable = root / "build" / "service.exe";
#else
    const fs::path executable = root / "build" / "service";
#endif

    const fs::path package = root / "package";
    const fs::path packaged_executable = package / "service";

    fs::copy_file(
        executable,
        packaged_executable,
        fs::copy_options::overwrite_existing
    );

    fs::copy_file(
        root / "src" / "service.cpp",
        package / "service.cpp",
        fs::copy_options::overwrite_existing
    );

    const std::string binary_data = read_file(packaged_executable);
    const std::string source_data = read_file(package / "service.cpp");

    std::ostringstream manifest;
    manifest
        << "{\n"
        << "  \"application\": \"inventory-validation-worker\",\n"
        << "  \"version\": \"1.0.0\",\n"
        << "  \"files\": [\n"
        << "    {\"path\": \"service\", \"fnv1a64\": \""
        << hex64(fnv1a64(binary_data)) << "\"},\n"
        << "    {\"path\": \"service.cpp\", \"fnv1a64\": \""
        << hex64(fnv1a64(source_data)) << "\"}\n"
        << "  ]\n"
        << "}\n";

    write_file(package / "manifest.json", manifest.str());

    return "Created package directory with binary, source and integrity manifest.";
}

std::string dockerfile_contents() {
    return
        "FROM gcc:14-bookworm AS build\n"
        "WORKDIR /source\n"
        "COPY service.cpp ./service.cpp\n"
        "RUN g++ -std=c++17 -O2 -Wall -Wextra -pedantic "
        "service.cpp -o /service\n"
        "\n"
        "FROM debian:bookworm-slim\n"
        "COPY --from=build /service /usr/local/bin/service\n"
        "USER 65532:65532\n"
        "ENTRYPOINT [\"/usr/local/bin/service\"]\n";
}

std::string dockerize(const fs::path& root, bool build_image) {
    const fs::path package = root / "package";
    write_file(package / "Dockerfile", dockerfile_contents());

    if (!build_image) {
        return "Dockerfile and build context created; image build not requested.";
    }

    const std::string command =
        "docker build --tag inventory-validation-worker:1.0.0 "
        "ci_cd_cpp_workspace/package";

    const int result = std::system(command.c_str());
    if (result != 0) {
        throw PipelineError("Docker image build failed or Docker is unavailable.");
    }

    return "Built Docker image inventory-validation-worker:1.0.0.";
}

class Pipeline {
private:
    PipelineConfig config_;
    std::vector<StageResult> results_;

    template <typename Action>
    bool execute_stage(const std::string& name, Action action) {
        const auto started = std::chrono::steady_clock::now();
        StageStatus status = StageStatus::Running;
        std::string detail;

        try {
            detail = action();
            status = StageStatus::Succeeded;
        } catch (const std::exception& error) {
            status = StageStatus::Failed;
            detail = error.what();
        }

        const auto finished = std::chrono::steady_clock::now();
        const double duration = std::chrono::duration<double, std::milli>(
            finished - started
        ).count();

        results_.push_back({name, status, duration, detail});

        std::cout
            << "[" << status_name(status) << "] "
            << name << ": " << detail
            << " (" << std::fixed << std::setprecision(2)
            << duration << " ms)\n";

        return status == StageStatus::Succeeded;
    }

    void mark_remaining_skipped(std::size_t completed_count) {
        const std::vector<std::string> names = {
            "Build", "Test", "Scan", "Package", "Dockerize"
        };

        for (std::size_t index = completed_count; index < names.size(); ++index) {
            results_.push_back({
                names[index],
                StageStatus::Skipped,
                0.0,
                "A preceding required stage failed."
            });

            std::cout
                << "[skipped] " << names[index]
                << ": preceding stage failed.\n";
        }
    }

public:
    explicit Pipeline(PipelineConfig config)
        : config_(std::move(config)) {}

    bool run() {
        if (!execute_stage("Build", [&]() {
            const int result = run_build(config_.workspace);
            if (result != 0) {
                throw PipelineError("Compiler returned a non-zero exit code.");
            }
            return "Compiled C++17 inventory worker with warnings treated as errors.";
        })) {
            mark_remaining_skipped(1);
            return false;
        }

        if (!execute_stage("Test", [&]() {
            const int result = run_tests(config_.workspace);
            if (result != 0) {
                throw PipelineError("Inventory self-tests failed.");
            }
            return "Inventory behavior and input validation tests passed.";
        })) {
            mark_remaining_skipped(2);
            return false;
        }

        if (!execute_stage("Scan", [&]() {
            return scan_source(config_.workspace / "src" / "service.cpp");
        })) {
            mark_remaining_skipped(3);
            return false;
        }

        if (!execute_stage("Package", [&]() {
            return package_application(config_.workspace);
        })) {
            mark_remaining_skipped(4);
            return false;
        }

        if (!execute_stage("Dockerize", [&]() {
            return dockerize(config_.workspace, config_.build_docker_image);
        })) {
            return false;
        }

        write_report();
        return true;
    }

    void write_report() const {
        const fs::path report = config_.workspace / "pipeline-report.json";
        std::ostringstream output;

        output
            << "{\n"
            << "  \"pipeline\": \"Build -> Test -> Scan -> Package -> Dockerize\",\n"
            << "  \"status\": \"succeeded\",\n"
            << "  \"stages\": [\n";

        for (std::size_t index = 0; index < results_.size(); ++index) {
            const auto& result = results_[index];

            output
                << "    {\"name\": \"" << result.name
                << "\", \"status\": \"" << status_name(result.status)
                << "\", \"duration_ms\": " << result.duration_ms
                << ", \"detail\": \"" << result.detail << "\"}";

            if (index + 1 < results_.size()) {
                output << ",";
            }
            output << "\n";
        }

        output << "  ]\n}\n";
        write_file(report, output.str());

        std::cout << "Pipeline report: " << report.string() << "\n";
    }
};

int main(int argc, char* argv[]) {
    try {
        PipelineConfig config;

        for (int index = 1; index < argc; ++index) {
            const std::string argument = argv[index];

            if (argument == "--docker") {
                config.build_docker_image = true;
            } else {
                throw PipelineError("Unknown argument: " + argument);
            }
        }

        ensure_workspace(config.workspace);
        prepare_project(config.workspace);

        Pipeline pipeline(config);
        return pipeline.run() ? 0 : 1;

    } catch (const std::exception& error) {
        std::cerr << "CI/CD pipeline failed: " << error.what() << "\n";
        return 1;
    }
}

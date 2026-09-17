#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

/*
    C++17 Bash Automation Case Study
    ---------------------------------

    Scenario:
        An organization needs a local maintenance service that:

        1. discovers application files,
        2. creates verified backups,
        3. removes expired temporary files,
        4. records an audit log,
        5. supports dry-run behavior,
        6. prevents unsafe source/destination configuration,
        7. reports failures clearly.

    The program uses only the C++17 standard library.

    This is intentionally a case study rather than a collection of unrelated
    syntax demonstrations. The architecture models the same operational
    concerns that a production Bash automation script would face.
*/

struct FileRecord {
    fs::path path;
    std::uintmax_t size;
};

struct BackupRecord {
    fs::path relativePath;
    std::uintmax_t size;
    std::string fingerprint;
};

struct AutomationConfig {
    fs::path sourceDirectory;
    fs::path backupDirectory;
    fs::path temporaryDirectory;

    int retentionDays = 7;
    bool dryRun = false;
};

class AuditLogger {
private:
    fs::path logFile;

public:
    explicit AuditLogger(fs::path path)
        : logFile(std::move(path)) {}

    void log(const std::string& level, const std::string& message) {
        const auto now = std::chrono::system_clock::now();
        const std::time_t currentTime =
            std::chrono::system_clock::to_time_t(now);

        std::ofstream output(logFile, std::ios::app);

        if (!output) {
            throw std::runtime_error(
                "Unable to open audit log: " + logFile.string()
            );
        }

        output << std::put_time(
            std::localtime(&currentTime),
            "%Y-%m-%d %H:%M:%S"
        );

        output << " [" << level << "] " << message << '\n';
    }
};

class MaintenanceSystem {
private:
    AutomationConfig config;
    AuditLogger& logger;

    static std::string fingerprint(const fs::path& file) {
        /*
            This is a lightweight deterministic content fingerprint for the
            case study. It is not presented as a cryptographic checksum.

            Production backup verification should use a cryptographic hash
            such as SHA-256 when cryptographic integrity is required.
        */
        std::ifstream input(file, std::ios::binary);

        if (!input) {
            throw std::runtime_error(
                "Unable to read file: " + file.string()
            );
        }

        std::string contents(
            (std::istreambuf_iterator<char>(input)),
            std::istreambuf_iterator<char>()
        );

        std::size_t hashValue = std::hash<std::string>{}(contents);

        std::ostringstream output;
        output << std::hex << hashValue;
        return output.str();
    }

    static bool hasExtension(
        const fs::path& path,
        const std::string& extension
    ) {
        return path.extension() == extension;
    }

    void validateConfiguration() const {
        if (config.retentionDays < 0) {
            throw std::invalid_argument(
                "Retention period cannot be negative."
            );
        }

        if (!fs::exists(config.sourceDirectory)) {
            throw std::invalid_argument(
                "Source directory does not exist."
            );
        }

        if (!fs::is_directory(config.sourceDirectory)) {
            throw std::invalid_argument(
                "Source path is not a directory."
            );
        }

        if (config.sourceDirectory == config.backupDirectory) {
            throw std::invalid_argument(
                "Source and backup directories must differ."
            );
        }

        /*
            The backup must not be located inside the source tree.

            Otherwise, repeated backup runs could recursively copy the backup
            into itself.
        */
        const fs::path source =
            fs::weakly_canonical(config.sourceDirectory);

        const fs::path backup =
            fs::weakly_canonical(config.backupDirectory);

        auto sourceIterator = source.begin();
        auto backupIterator = backup.begin();

        while (
            sourceIterator != source.end() &&
            backupIterator != backup.end() &&
            *sourceIterator == *backupIterator
        ) {
            ++sourceIterator;
            ++backupIterator;
        }

        if (sourceIterator == source.end()) {
            throw std::invalid_argument(
                "Backup directory cannot be inside source directory."
            );
        }
    }

public:
    MaintenanceSystem(
        AutomationConfig configuration,
        AuditLogger& auditLogger
    )
        : config(std::move(configuration)),
          logger(auditLogger) {}

    std::vector<FileRecord> discoverFiles() {
        std::vector<FileRecord> files;

        for (
            const auto& entry :
            fs::recursive_directory_iterator(config.sourceDirectory)
        ) {
            if (!entry.is_regular_file()) {
                continue;
            }

            files.push_back({
                entry.path(),
                entry.file_size()
            });
        }

        return files;
    }

    void printInventory(
        const std::vector<FileRecord>& files
    ) {
        logger.log(
            "INFO",
            "Discovered " + std::to_string(files.size()) +
            " source files."
        );

        std::cout << "\nSource inventory:\n";

        for (const auto& record : files) {
            std::cout
                << "  "
                << fs::relative(
                       record.path,
                       config.sourceDirectory
                   ).string()
                << " | "
                << record.size
                << " bytes\n";
        }
    }

    std::vector<BackupRecord> createBackup() {
        validateConfiguration();

        std::vector<BackupRecord> records;
        const auto files = discoverFiles();

        if (config.dryRun) {
            logger.log("INFO", "Backup running in dry-run mode.");
        }

        for (const auto& file : files) {
            const fs::path relative =
                fs::relative(
                    file.path,
                    config.sourceDirectory
                );

            const fs::path destination =
                config.backupDirectory / relative;

            if (config.dryRun) {
                std::cout
                    << "WOULD COPY: "
                    << relative.string()
                    << '\n';

                records.push_back({
                    relative,
                    file.size,

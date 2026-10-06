#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

enum class ArtifactState {
    Staged,
    Uploaded,
    Verified,
    Expired,
    Deleted
};

std::string toString(ArtifactState state) {
    switch (state) {
        case ArtifactState::Staged: return "staged";
        case ArtifactState::Uploaded: return "uploaded";
        case ArtifactState::Verified: return "verified";
        case ArtifactState::Expired: return "expired";
        case ArtifactState::Deleted: return "deleted";
    }
    return "unknown";
}

struct ArtifactFile {
    std::string relativePath;
    std::uintmax_t sizeBytes{};
    std::string checksum;
};

struct StatusCheck {
    std::string name;
    bool passed{};
};

struct Artifact {
    std::string id;
    std::string repository;
    std::string commitSha;
    int buildNumber{};
    std::vector<ArtifactFile> files;
    std::vector<StatusCheck> checks;
    std::uintmax_t totalBytes{};
    std::string archiveChecksum;
    ArtifactState state{ArtifactState::Staged};
    int retentionDays{30};
};

class GovernanceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

/*
 * This case study models a release pipeline that produces a build artifact,
 * validates its quality gates, uploads it to immutable storage, and later
 * downloads it for deployment.
 *
 * The artifact itself is represented as domain data because portable C++17
 * has no standard tar, SHA-256, or object-storage client. The storage engine
 * therefore focuses on the governance and lifecycle rules surrounding the
 * artifact.
 */
class ArtifactRepository {
private:
    fs::path root_;
    std::map<std::string, Artifact> artifacts_;

    static std::string pseudoSha256(const std::string& value) {
        /*
         * This is a deterministic demonstration fingerprint, not a cryptographic
         * SHA-256 implementation. Production artifact integrity must use a real
         * SHA-256 implementation or the checksum supplied by the storage system.
         */
        std::uint64_t hash = 14695981039346656037ULL;
        for (unsigned char character : value) {
            hash ^= character;
            hash *= 1099511628211ULL;
        }

        std::ostringstream output;
        output << std::hex << std::setw(16) << std::setfill('0') << hash;
        return output.str();
    }

    static bool allChecksPassed(const Artifact& artifact) {
        return std::all_of(
            artifact.checks.begin(),
            artifact.checks.end(),
            [](const StatusCheck& check) {
                return check.passed;
            }
        );
    }

public:
    explicit ArtifactRepository(fs::path root) : root_(std::move(root)) {
        fs::create_directories(root_);
    }

    void stage(Artifact artifact) {
        if (artifact.id.empty()) {
            throw GovernanceError("Artifact ID cannot be empty.");
        }

        if (artifact.files.empty()) {
            throw GovernanceError("An artifact must contain at least one file.");
        }

        if (artifacts_.contains(artifact.id)) {
            throw GovernanceError("An artifact with this ID already exists.");
        }

        artifact.totalBytes = 0;
        for (const auto& file : artifact.files) {
            if (file.relativePath.empty()) {
                throw GovernanceError("Artifact file path cannot be empty.");
            }

            if (file.relativePath.starts_with("/") ||
                file.relativePath.find("..") != std::string::npos) {
                throw GovernanceError("Unsafe artifact path: " + file.relativePath);
            }

            artifact.totalBytes += file.sizeBytes;
        }

        if (artifact.archiveChecksum.empty()) {
            artifact.archiveChecksum = pseudoSha256(
                artifact.id + ":" + artifact.commitSha + ":" +
                std::to_string(artifact.totalBytes)
            );
        }

        artifacts_.emplace(artifact.id, std::move(artifact));
    }

    void upload(const std::string& artifactId) {
        auto iterator = artifacts_.find(artifactId);
        if (iterator == artifacts_.end()) {
            throw GovernanceError("Cannot upload an unknown artifact.");
        }

        Artifact& artifact = iterator->second;

        if (artifact.state != ArtifactState::Staged) {
            throw GovernanceError("Only staged artifacts can be uploaded.");
        }

        if (!allChecksPassed(artifact)) {
            throw GovernanceError(
                "Artifact cannot be uploaded because a quality check failed."
            );
        }

        /*
         * An immutable artifact is not silently replaced. Replacing an artifact
         * under an existing identifier would make deployment provenance ambiguous.
         */
        artifact.state = ArtifactState::Uploaded;

        fs::path marker = root_ / (artifact.id + ".artifact");
        std::ofstream output(marker);
        if (!output) {
            throw GovernanceError("Unable to persist artifact marker.");
        }

        output << "artifact_id=" << artifact.id << '\n';
        output << "commit=" << artifact.commitSha << '\n';
        output << "checksum=" << artifact.archiveChecksum << '\n';
    }

    void verify(const std::string& artifactId, const std::string& checksum) {
        auto iterator = artifacts_.find(artifactId);
        if (iterator == artifacts_.end()) {
            throw GovernanceError("Unknown artifact.");
        }

        Artifact& artifact = iterator->second;

        if (artifact.state != ArtifactState::Uploaded) {
            throw GovernanceError("Only uploaded artifacts can be verified.");
        }

        if (checksum != artifact.archiveChecksum) {
            throw GovernanceError("Artifact integrity verification failed.");
        }

        artifact.state = ArtifactState::Verified;
    }

    const Artifact& download(const std::string& artifactId) const {
        auto iterator = artifacts_.find(artifactId);
        if (iterator == artifacts_.end()) {
            throw GovernanceError("Artifact does not exist.");
        }

        const Artifact& artifact = iterator->second;

        if (artifact.state != ArtifactState::Verified) {
            throw GovernanceError(
                "Deployment download requires a verified artifact."
            );
        }

        return artifact;
    }

    void expire(const std::string& artifactId) {
        auto iterator = artifacts_.find(artifactId);
        if (iterator == artifacts_.end()) {
            throw GovernanceError("Unknown artifact.");
        }

        if (iterator->second.state != ArtifactState::Verified) {
            throw GovernanceError("Only verified artifacts can expire.");
        }

        iterator->second.state = ArtifactState::Expired;
    }

    void removeExpired(const std::string& artifactId) {
        auto iterator = artifacts_.find(artifactId);
        if (iterator == artifacts_.end()) {
            throw GovernanceError("Unknown artifact.");
        }

        if (iterator->second.state != ArtifactState::Expired) {
            throw GovernanceError(
                "Storage cleanup is restricted to expired artifacts."
            );
        }

        fs::remove(root_ / (artifactId + ".artifact"));
        iterator->second.state = ArtifactState::Deleted;
    }

    void printInventory() const {
        std::cout << "\nArtifact inventory\n";
        for (const auto& [id, artifact] : artifacts_) {
            std::cout
                << "  " << id
                << " | state=" << toString(artifact.state)
                << " | commit=" << artifact.commitSha
                << " | bytes=" << artifact.totalBytes
                << " | checksum=" << artifact.archiveChecksum
                << '\n';
        }
    }
};

int main() {
    try {
        fs::path repositoryPath =
            fs::temp_directory_path() / "cpp-artifact-governance";

        fs::remove_all(repositoryPath);
        ArtifactRepository repository(repositoryPath);

        Artifact releaseArtifact{
            .id = "payments-api-build-184",
            .repository = "platform/payments-api",
            .commitSha = "7f3d8a2b91c4",
            .buildNumber = 184,
            .files = {
                {"bin/payments-api", 4821032, ""},
                {"config/runtime.json", 1290, ""},
                {"docs/release-notes.txt", 4811, ""}
            },
            .checks = {
                {"unit-tests", true},
                {"security-scan", true},
                {"package-validation", true},
                {"integration-tests", true}
            },
            .retentionDays = 30
        };

        repository.stage(releaseArtifact);
        std::cout << "Staged artifact: " << releaseArtifact.id << '\n';

        repository.upload(releaseArtifact.id);
        std::cout << "Uploaded artifact: " << releaseArtifact.id << '\n';

        const std::string checksum =
            releaseArtifact.archiveChecksum.empty()
                ? "calculated-after-staging"
                : releaseArtifact.archiveChecksum;

        /*
         * stage() calculates the checksum on the stored domain object. The local
         * releaseArtifact copy remains unchanged, so a production caller would
         * obtain metadata from the repository before verification.
         */
        repository.verify(
            releaseArtifact.id,
            "f4b9a8c9d0e1f234"
        );

    } catch (const GovernanceError& error) {
        /*
         * A failed verification is intentionally demonstrated below using a
         * controlled recovery path rather than terminating the case study.
         */
        std::cout << "Expected validation event: "
                  << error.what() << '\n';
    }

    try {
        fs::path repositoryPath =
            fs::temp_directory_path() / "cpp-artifact-governance";

        ArtifactRepository repository(repositoryPath);

        Artifact productionArtifact{
            .id = "catalog-api-build-207",
            .repository = "platform/catalog-api",
            .commitSha = "a81f03c6de91",
            .buildNumber = 207,
            .files = {
                {"bin/catalog-api", 6234112, ""},
                {"config/production.json", 1840, ""},
                {"docs/schema.json", 9210, ""}
            },
            .checks = {
                {"unit-tests", true},
                {"security-scan", true},
                {"dependency-audit", true}
            },
            .retentionDays = 14
        };

        repository.stage(productionArtifact);
        repository.upload(productionArtifact.id);

        /*
         * The checksum used here is computed by the repository's deterministic
         * demonstration algorithm. The actual production system must expose
         * cryptographic checksum metadata instead of using this teaching hash.
         */
        std::string checksum =
            "replace-with-repository-checksum";

        try {
            repository.verify(productionArtifact.id, checksum);
        } catch (const GovernanceError&) {
            /*
             * Demonstrate a safe failure: a checksum mismatch blocks download
             * rather than allowing potentially corrupted content to deploy.
             */
            std::cout << "Integrity check correctly blocked deployment.\n";
        }

        /*
         * For the successful path, create another artifact and obtain its exact
         * calculated checksum from a second repository lookup by reading the
         * lifecycle through the domain model.
         */
        Artifact verifiedArtifact{
            .id = "web-frontend-build-208",
            .repository = "platform/web-frontend",
            .commitSha = "d20c9f13b8aa",
            .buildNumber = 208,
            .files = {
                {"dist/index.html", 8032, ""},
                {"dist/app.js", 184203, ""},
                {"dist/app.css", 22810, ""}
            },
            .checks = {
                {"unit-tests", true},
                {"lint", true},
                {"security-scan", true},
                {"asset-validation", true}
            },
            .retentionDays = 7
        };

        repository.stage(verifiedArtifact);
        repository.upload(verifiedArtifact.id);

        /*
         * Calculate the same deterministic demonstration fingerprint used by
         * stage(). This avoids exposing mutable internal repository state.
         */
        std::uintmax_t totalBytes = 8032 + 184203 + 22810;
        std::uint64_t hash = 14695981039346656037ULL;
        const std::string seed =
            verifiedArtifact.id + ":" +
            verifiedArtifact.commitSha + ":" +
            std::to_string(totalBytes);

        for (unsigned char character : seed) {
            hash ^= character;
            hash *= 1099511628211ULL;
        }

        std::ostringstream checksumStream;
        checksumStream << std::hex << std::setw(16)
                       << std::setfill('0') << hash;

        repository.verify(
            verifiedArtifact.id,
            checksumStream.str()
        );

        const Artifact& deployable =
            repository.download(verifiedArtifact.id);

        std::cout
            << "Verified artifact ready for deployment: "
            << deployable.id << '\n';

        repository.expire(verifiedArtifact.id);
        repository.removeExpired(verifiedArtifact.id);

        repository.printInventory();

        fs::remove_all(repositoryPath);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected failure: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}

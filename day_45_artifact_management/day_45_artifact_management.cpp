#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Repository governance case study: immutable build artifacts for a
 * regulated infrastructure deployment platform.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic artifact_management.cpp -o artifacts
 *
 * The demonstration uses deterministic identifiers for its sample payloads.
 * Production systems must use a vetted SHA-256 implementation rather than
 * the educational digest function included here.
 */

class ArtifactError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ValidationError : public ArtifactError {
public:
    using ArtifactError::ArtifactError;
};

class ImmutableVersionError : public ArtifactError {
public:
    using ArtifactError::ArtifactError;
};

class IntegrityError : public ArtifactError {
public:
    using ArtifactError::ArtifactError;
};

struct Version {
    int major;
    int minor;
    int patch;
    std::string prerelease;

    static Version parse(const std::string& value) {
        Version result{};
        std::string core = value;
        const auto dash = core.find('-');

        if (dash != std::string::npos) {
            result.prerelease = core.substr(dash + 1);
            core = core.substr(0, dash);
            if (result.prerelease.empty()) {
                throw ValidationError("Prerelease identifier cannot be empty.");
            }
        }

        std::stringstream stream(core);
        std::string part;
        std::vector<int> values;

        while (std::getline(stream, part, '.')) {
            if (part.empty() ||
                (part.size() > 1 && part.front() == '0') ||
                !std::all_of(part.begin(), part.end(), [](unsigned char ch) {
                    return ch >= '0' && ch <= '9';
                })) {
                throw ValidationError("Invalid semantic version: " + value);
            }

            try {
                std::size_t consumed = 0;
                long long parsed = std::stoll(part, &consumed);
                if (consumed != part.size() || parsed > 2147483647LL) {
                    throw ValidationError("Version component is out of range.");
                }
                values.push_back(static_cast<int>(parsed));
            } catch (const std::exception&) {
                throw ValidationError("Version component is out of range.");
            }
        }

        if (values.size() != 3) {
            throw ValidationError("Version must contain major, minor, and patch.");
        }

        result.major = values[0];
        result.minor = values[1];
        result.patch = values[2];
        return result;
    }

    std::string str() const {
        std::string result = std::to_string(major) + "." +
                             std::to_string(minor) + "." +
                             std::to_string(patch);
        if (!prerelease.empty()) result += "-" + prerelease;
        return result;
    }

    auto core() const {
        return std::tie(major, minor, patch);
    }
};

bool operator<(const Version& left, const Version& right) {
    if (left.core() != right.core()) return left.core() < right.core();

    if (left.prerelease.empty() != right.prerelease.empty()) {
        return !left.prerelease.empty();
    }

    return left.prerelease < right.prerelease;
}

struct ArtifactManifest {
    std::string name;
    Version version;
    std::string digest;
    std::size_t sizeBytes;
    std::string mediaType;
    std::string publisher;
    std::string sourceRevision;
};

struct ArtifactBlob {
    std::string content;
    std::string digest;
};

struct PublicationEvent {
    std::string action;
    std::string artifact;
    std::string actor;
    std::string detail;
};

struct ReleaseChannel {
    std::string artifactKey;
    std::string actor;
};

class ArtifactRegistry {
private:
    std::map<std::string, ArtifactManifest> manifests_;
    std::unordered_map<std::string, ArtifactBlob> blobs_;
    std::map<std::string, ReleaseChannel> channels_;
    std::vector<PublicationEvent> audit_;

    static bool validName(const std::string& name) {
        if (name.empty() || name.size() > 100) return false;

        return std::all_of(name.begin(), name.end(), [](unsigned char ch) {
            return (ch >= 'a' && ch <= 'z') ||
                   (ch >= 'A' && ch <= 'Z') ||
                   (ch >= '0' && ch <= '9') ||
                   ch == '.' || ch == '_' || ch == '-';
        }) && std::isalnum(static_cast<unsigned char>(name.front()));
    }

    static std::string key(const std::string& name, const Version& version) {
        return name + "@" + version.str();
    }

    // Stable demonstration fingerprint, not a cryptographic integrity digest.
    // A production registry must use SHA-256 or stronger approved hashing.
    static std::string demonstrationDigest(const std::string& content) {
        std::uint64_t value = 14695981039346656037ULL;
        for (unsigned char ch : content) {
            value ^= ch;
            value *= 1099511628211ULL;
        }

        std::ostringstream output;
        output << std::hex << std::setfill('0') << std::setw(16) << value;
        return output.str();
    }

    void record(
        const std::string& action,
        const std::string& artifact,
        const std::string& actor,
        const std::string& detail
    ) {
        audit_.push_back({action, artifact, actor, detail});
    }

public:
    ArtifactManifest publish(
        const std::string& name,
        const std::string& versionText,
        const std::string& content,
        const std::string& publisher,
        const std::string& sourceRevision,
        const std::string& mediaType
    ) {
        if (!validName(name)) {
            throw ValidationError("Artifact name contains invalid characters.");
        }

        if (publisher.empty() || sourceRevision.empty()) {
            throw ValidationError("Publisher and source revision are required.");
        }

        if (mediaType.find('/') == std::string::npos) {
            throw ValidationError("Media type must contain a slash.");
        }

        Version version = Version::parse(versionText);
        const std::string artifactKey = key(name, version);
        const std::string digest = demonstrationDigest(content);

        const auto existing = manifests_.find(artifactKey);
        if (existing != manifests_.end()) {
            const auto& manifest = existing->second;

            if (manifest.digest == digest &&
                manifest.publisher == publisher &&
                manifest.sourceRevision == sourceRevision &&
                manifest.mediaType == mediaType &&
                manifest.sizeBytes == content.size()) {
                return manifest;
            }

            throw ImmutableVersionError(
                "A published version cannot be replaced: " + artifactKey
            );
        }

        // Deduplicate identical bytes across different versions and packages.
        auto blob = blobs_.find(digest);
        if (blob != blobs_.end()) {
            if (blob->second.content != content) {
                throw IntegrityError(
                    "Digest collision or corrupted content-addressed storage."
                );
            }
        } else {
            blobs_.emplace(digest, ArtifactBlob{content, digest});
        }

        ArtifactManifest manifest{
            name,
            version,
            digest,
            content.size(),
            mediaType,
            publisher,
            sourceRevision
        };

        manifests_.emplace(artifactKey, manifest);
        record("publish", artifactKey, publisher, digest);
        return manifest;
    }

    const ArtifactManifest& get(
        const std::string& name,
        const std::string& versionText
    ) const {
        const Version version = Version::parse(versionText);
        const auto found = manifests_.find(key(name, version));

        if (found == manifests_.end()) {
            throw ArtifactError("Artifact version does not exist.");
        }

        return found->second;
    }

    std::string download(
        const std::string& name,
        const std::string& versionText
    ) const {
        const ArtifactManifest& manifest = get(name, versionText);
        const auto blob = blobs_.find(manifest.digest);

        if (blob == blobs_.end()) {
            throw IntegrityError("Published manifest references a missing blob.");
        }

        if (blob->second.content.size() != manifest.sizeBytes ||
            demonstrationDigest(blob->second.content) != manifest.digest) {
            throw IntegrityError("Stored artifact failed integrity verification.");
        }

        return blob->second.content;
    }

    void promote(
        const std::string& channel,
        const std::string& name,
        const std::string& versionText,
        const std::string& actor
    ) {
        if (channel.empty() || actor.empty()) {
            throw ValidationError("Release channel and actor are required.");
        }

        const auto& manifest = get(name, versionText);
        const std::string artifactKey = key(name, manifest.version);
        const auto previous = channels_.find(channel);
        const std::string oldTarget =
            previous == channels_.end() ? "<unassigned>" : previous->second.artifactKey;

        channels_[channel] = ReleaseChannel{artifactKey, actor};

        // The channel pointer is mutable and audited; the version is not.
        record("promote", channel, actor, oldTarget + " -> " + artifactKey);
    }

    std::vector<ArtifactManifest> versions(const std::string& name) const {
        std::vector<ArtifactManifest> result;

        for (const auto& [artifactKey, manifest] : manifests_) {
            (void)artifactKey;
            if (manifest.name == name) result.push_back(manifest);
        }

        std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
            return left.version < right.version;
        });

        return result;
    }

    void verifyAll() const {
        for (const auto& [artifactKey, manifest] : manifests_) {
            const auto blob = blobs_.find(manifest.digest);

            if (blob == blobs_.end() ||
                blob->second.content.size() != manifest.sizeBytes ||
                demonstrationDigest(blob->second.content) != manifest.digest) {
                throw IntegrityError("Verification failed for " + artifactKey);
            }

            std::cout << "Verified " << artifactKey
                      << " digest=" << manifest.digest << '\n';
        }
    }

    void printAudit() const {
        std::cout << "\nRepository audit trail\n";

        for (const auto& event : audit_) {
            std::cout << event.action << " | " << event.artifact
                      << " | actor=" << event.actor
                      << " | " << event.detail << '\n';
        }
    }
};

int main() {
    try {
        ArtifactRegistry registry;

        const auto candidate = registry.publish(
            "bridge-inspection-engine",
            "3.4.0-rc.1",
            "model=inspection-v3\nthreshold=0.92\n",
            "ci-release",
            "c81a2f9",
            "text/plain"
        );

        const auto stable = registry.publish(
            "bridge-inspection-engine",
            "3.4.0",
            "model=inspection-v3\nthreshold=0.94\n",
            "ci-release",
            "d45b771",
            "text/plain"
        );

        std::cout << "Candidate digest: " << candidate.digest << '\n';
        std::cout << "Stable digest: " << stable.digest << '\n';

        registry.promote(
            "production",
            "bridge-inspection-engine",
            "3.4.0",
            "release-manager"
        );

        const std::string retrieved = registry.download(
            "bridge-inspection-engine",
            "3.4.0"
        );

        std::cout << "Retrieved production artifact:\n" << retrieved;

        try {
            registry.publish(
                "bridge-inspection-engine",
                "3.4.0",
                "altered model bytes",
                "ci-release",
                "e991b0a",
                "text/plain"
            );
        } catch (const ImmutableVersionError& error) {
            std::cout << "\nRejected replacement: " << error.what() << '\n';
        }

        try {
            registry.get("bridge-inspection-engine", "9.0.0");
        } catch (const ArtifactError& error) {
            std::cout << "Missing version handled: " << error.what() << '\n';
        }

        std::cout << "\nPublished versions:\n";
        for (const auto& manifest : registry.versions("bridge-inspection-engine")) {
            std::cout << manifest.version.str()
                      << " (" << manifest.sizeBytes << " bytes)\n";
        }

        registry.verifyAll();
        registry.printAudit();

        // Production considerations:
        // A durable registry needs transactional persistence, authenticated
        // publishers, cryptographic signatures, access control, concurrent
        // writer coordination, retention policy, and independent audit storage.
    } catch (const std::exception& error) {
        std::cerr << "Artifact registry failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

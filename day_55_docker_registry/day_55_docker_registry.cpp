#include <algorithm>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class Role { Reader, Publisher, Admin };
enum class CheckState { Pass, Fail, Unknown };
enum class ImageState { Built, Published, Retired };

string roleName(Role role) {
    switch (role) {
        case Role::Reader: return "reader";
        case Role::Publisher: return "publisher";
        case Role::Admin: return "admin";
    }
    throw logic_error("Unknown role");
}

struct Principal {
    string username;
    Role role;
};

struct Artifact {
    string repository;
    string tag;
    string digest;
    size_t sizeBytes;
    string platform;
    ImageState state = ImageState::Built;

    string reference() const {
        return repository + ":" + tag;
    }
};

struct PublishPolicy {
    set<string> allowedRegistries;
    size_t maximumSizeBytes = 500000000;
    bool requireScanPass = true;
    bool requireSignature = true;
    bool immutableReleaseTags = true;
};

struct ReviewEvidence {
    CheckState vulnerabilityScan = CheckState::Unknown;
    bool signatureVerified = false;
    bool provenanceVerified = false;
};

struct EligibilityResult {
    bool eligible;
    vector<string> reasons;
};

class RegistryError : public runtime_error {
public:
    explicit RegistryError(const string& message) : runtime_error(message) {}
};

class Registry {
private:
    string name_;
    bool private_;
    map<string, Artifact> images_;
    map<string, Principal> principals_;
    vector<string> audit_;

    void audit(const string& action, const string& actor,
               const string& reference) {
        audit_.push_back(action + " | " + actor + " | " + reference);
    }

public:
    Registry(string name, bool privateRegistry)
        : name_(std::move(name)), private_(privateRegistry) {
        if (name_.empty()) {
            throw RegistryError("Registry name cannot be empty.");
        }
    }

    const string& name() const {
        return name_;
    }

    void addPrincipal(const Principal& principal) {
        if (principal.username.empty()) {
            throw RegistryError("Principal username cannot be empty.");
        }
        principals_[principal.username] = principal;
    }

    Principal authenticate(const string& username, const string& token) {
        // This simulation uses explicit demo tokens; production credentials
        // must be verified against a secure identity provider.
        auto found = principals_.find(username);
        const string expected = "demo-" + username + "-token";
        if (found == principals_.end() || token != expected) {
            audit("authentication_failed", username, "");
            throw RegistryError("Invalid credentials.");
        }
        audit("authenticated", username, "");
        return found->second;
    }

    static void validateArtifact(const Artifact& artifact) {
        static const regex repositoryPattern(
            R"(^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$)"
        );
        static const regex tagPattern(
            R"(^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$)"
        );
        static const regex digestPattern(R"(^sha256:[0-9a-f]{64}$)");

        if (!regex_match(artifact.repository, repositoryPattern)) {
            throw RegistryError("Invalid lowercase repository path.");
        }
        if (!regex_match(artifact.tag, tagPattern)) {
            throw RegistryError("Invalid image tag.");
        }
        if (!regex_match(artifact.digest, digestPattern)) {
            throw RegistryError("Invalid image digest.");
        }
        if (artifact.sizeBytes == 0) {
            throw RegistryError("Image size must be positive.");
        }
        if (artifact.platform != "linux/amd64" &&
            artifact.platform != "linux/arm64" &&
            artifact.platform != "linux/arm/v7") {
            throw RegistryError("Unsupported demonstration platform.");
        }
    }

    static bool isReleaseTag(const string& tag) {
        static const regex releasePattern(R"(^v[0-9]+\.[0-9]+\.[0-9]+$)");
        return regex_match(tag, releasePattern);
    }

    Artifact push(const Principal& principal, Artifact artifact,
                  const PublishPolicy& policy, const ReviewEvidence& evidence) {
        if (principal.role != Role::Publisher && principal.role != Role::Admin) {
            throw RegistryError("Push requires publisher or admin role.");
        }
        if (policy.allowedRegistries.count(name_) == 0) {
            throw RegistryError("Registry is not approved by policy.");
        }

        validateArtifact(artifact);

        if (artifact.sizeBytes > policy.maximumSizeBytes) {
            throw RegistryError("Image exceeds maximum size.");
        }
        if (policy.requireScanPass &&
            evidence.vulnerabilityScan != CheckState::Pass) {
            throw RegistryError("Vulnerability scan has not passed.");
        }
        if (policy.requireSignature && !evidence.signatureVerified) {
            throw RegistryError("Signature verification is required.");
        }
        if (!evidence.provenanceVerified) {
            throw RegistryError("Build provenance verification is required.");
        }

        const string key = artifact.reference();
        auto existing = images_.find(key);
        if (existing != images_.end()) {
            if (existing->second.digest == artifact.digest) {
                audit("push_idempotent", principal.username, key);
                return existing->second;
            }
            if (policy.immutableReleaseTags && isReleaseTag(artifact.tag)) {
                throw RegistryError("Release tag overwrite is prohibited.");
            }
        }

        artifact.state = ImageState::Published;
        images_[key] = artifact;
        audit("push", principal.username, key);
        return artifact;
    }

    Artifact pull(const Principal* principal, const string& reference) {
        if (private_ && principal == nullptr) {
            throw RegistryError("Private registry login required.");
        }

        auto found = images_.find(reference);
        if (found == images_.end() ||
            found->second.state != ImageState::Published) {
            throw RegistryError("Published image not found.");
        }

        const string actor = principal ? principal->username : "anonymous";
        audit("pull", actor, reference);
        return found->second;
    }

    EligibilityResult canPublish(const Principal& principal,
                                 const Artifact& artifact,
                                 const PublishPolicy& policy,
                                 const ReviewEvidence& evidence) const {
        vector<string> reasons;
        try {
            if (principal.role != Role::Publisher && principal.role != Role::Admin) {
                throw RegistryError("Publisher role required.");
            }
            if (policy.allowedRegistries.count(name_) == 0) {
                throw RegistryError("Registry not allowed.");
            }
            validateArtifact(artifact);
            if (artifact.sizeBytes > policy.maximumSizeBytes) {
                throw RegistryError("Image exceeds size limit.");
            }
            if (policy.requireScanPass &&
                evidence.vulnerabilityScan != CheckState::Pass) {
                throw RegistryError("Scan must pass.");
            }
            if (policy.requireSignature && !evidence.signatureVerified) {
                throw RegistryError("Signature must be verified.");
            }
            if (!evidence.provenanceVerified) {
                throw RegistryError("Provenance must be verified.");
            }

            auto existing = images_.find(artifact.reference());
            if (existing != images_.end() &&
                existing->second.digest != artifact.digest &&
                policy.immutableReleaseTags && isReleaseTag(artifact.tag)) {
                throw RegistryError("Release tag already points to another digest.");
            }
        } catch (const exception& error) {
            reasons.push_back(error.what());
        }
        return {!reasons.empty() ? false : true, reasons};
    }

    void printReport() const {
        size_t totalBytes = 0;
        cout << "\nRegistry: " << name_ << '\n'
             << "Visibility: " << (private_ ? "private" : "public") << '\n'
             << "Published images:\n";

        for (const auto& entry : images_) {
            const auto& image = entry.second;
            totalBytes += image.sizeBytes;
            cout << "  " << image.reference()
                 << " | " << image.digest
                 << " | " << image.platform
                 << " | " << image.sizeBytes << " bytes\n";
        }

        cout << "Image count: " << images_.size() << '\n'
             << "Total manifest bytes: " << totalBytes << '\n'
             << "Audit events: " << audit_.size() << '\n';
    }
};

string makeDigest(const string& suffix) {
    // A fixed-width digest is sufficient for validation examples. It is not a
    // cryptographic hash implementation and must not be used for real images.
    return "sha256:" + string(64 - min<size_t>(suffix.size(), 64), '0') +
           suffix.substr(0, 64);
}

int main() {
    try {
        Registry registry("registry.example.com", true);
        Principal publisher{"release-bot", Role::Publisher};
        Principal reader{"deployment-bot", Role::Reader};

        registry.addPrincipal(publisher);
        registry.addPrincipal(reader);

        const Principal authenticatedPublisher =
            registry.authenticate("release-bot", "demo-release-bot-token");

        PublishPolicy policy{
            {"registry.example.com"},
            1000000,
            true,
            true,
            true
        };

        Artifact image{
            "commerce/orders-api",
            "v2.4.1",
            makeDigest("a241"),
            125000,
            "linux/amd64",
            ImageState::Built
        };

        ReviewEvidence evidence{
            CheckState::Pass,
            true,
            true
        };

        EligibilityResult eligibility = registry.canPublish(
            authenticatedPublisher, image, policy, evidence
        );

        cout << "Publication eligibility: "
             << (eligibility.eligible ? "eligible" : "blocked") << '\n';

        if (!eligibility.eligible) {
            for (const string& reason : eligibility.reasons) {
                cout << "  - " << reason << '\n';
            }
            return 1;
        }

        registry.push(authenticatedPublisher, image, policy, evidence);
        Artifact pulled = registry.pull(&reader, image.reference());

        cout << "Deployment resolved: " << pulled.reference()
             << " -> " << pulled.digest << '\n';

        // A failed scan prevents publication even when the publisher is trusted.
        Artifact unsafeImage{
            "commerce/orders-api",
            "v2.4.2",
            makeDigest("a242"),
            125000,
            "linux/amd64",
            ImageState::Built
        };

        ReviewEvidence failedEvidence{
            CheckState::Fail,
            true,
            true
        };

        EligibilityResult rejected = registry.canPublish(
            authenticatedPublisher, unsafeImage, policy, failedEvidence
        );

        cout << "\nUnsafe image eligibility: "
             << (rejected.eligible ? "eligible" : "blocked") << '\n';
        for (const string& reason : rejected.reasons) {
            cout << "  - " << reason << '\n';
        }

        registry.printReport();
    } catch (const exception& error) {
        cerr << "Registry operation failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}

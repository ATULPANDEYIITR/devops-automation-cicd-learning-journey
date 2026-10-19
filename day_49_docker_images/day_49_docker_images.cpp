#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using Digest = std::string;

static Digest makeDigest(const std::string& value) {
    // A deterministic stand-in for a content digest keeps this C++ case study
    // dependency-free. Production Docker content addressing uses cryptographic
    // digests such as SHA-256.
    std::hash<std::string> hasher;
    const std::size_t first = hasher(value);
    const std::size_t second = hasher("docker|" + value);

    std::ostringstream out;
    out << "sha256:" << std::hex
        << std::setw(16) << std::setfill('0') << first
        << std::setw(16) << std::setfill('0') << second;
    return out.str();
}

static std::string shortDigest(const Digest& digest) {
    return digest.substr(0, std::min<std::size_t>(19, digest.size()));
}

struct Layer {
    Digest digest;
    std::optional<Digest> parent;
    std::string instruction;
    std::uint64_t sizeBytes;
};

struct PullRequestBuild {
    std::string repository;
    std::string sourceBranch;
    std::string targetBranch;
    std::vector<std::string> changedFiles;
};

struct ProtectedBranchPolicy {
    std::string branch;
    unsigned requiredApprovals;
    bool requirePassingChecks;
    bool requireLinearHistory;
    bool allowForcePush;
    bool allowDeletion;
};

struct ReviewDecision {
    std::string reviewer;
    std::string state;
};

class ImageGovernanceEngine {
private:
    std::unordered_map<Digest, Layer> layers_;
    std::unordered_map<Digest, std::vector<Digest>> images_;
    std::unordered_map<std::string, Digest> tags_;
    std::unordered_map<std::string, Digest> buildCache_;
    std::unordered_map<std::string, bool> checks_;

    static std::string cacheKey(
        const std::optional<Digest>& parent,
        const std::string& instruction,
        const std::string& context
    ) {
        return makeDigest(
            (parent ? *parent : "EMPTY") +
            "|" + instruction +
            "|" + context
        );
    }

    Layer createLayer(
        const std::optional<Digest>& parent,
        const std::string& instruction,
        const std::string& context,
        std::uint64_t sizeBytes
    ) {
        const std::string key = cacheKey(parent, instruction, context);

        auto cacheIt = buildCache_.find(key);
        if (cacheIt != buildCache_.end()) {
            return layers_.at(cacheIt->second);
        }

        const Digest layerDigest = makeDigest(key);
        Layer layer{
            layerDigest,
            parent,
            instruction,
            sizeBytes
        };

        layers_[layerDigest] = layer;
        buildCache_[key] = layerDigest;
        return layer;
    }

public:
    struct BuildOutcome {
        Digest imageId;
        unsigned cacheHits{};
        unsigned cacheMisses{};
    };

    BuildOutcome build(
        const std::string& repository,
        const std::vector<
            std::tuple<std::string, std::string, std::uint64_t>
        >& steps,
        const std::unordered_map<std::string, std::string>& context
    ) {
        if (repository.empty()) {
            throw std::invalid_argument("repository cannot be empty");
        }
        if (steps.empty()) {
            throw std::invalid_argument("image must contain build steps");
        }

        std::optional<Digest> parent;
        std::vector<Digest> selected;
        unsigned hits = 0;
        unsigned misses = 0;

        for (const auto& [instruction, contextName, sizeBytes] : steps) {
            auto input = context.find(contextName);
            if (input == context.end()) {
                throw std::invalid_argument(
                    "missing build context: " + contextName
                );
            }

            const std::string key = cacheKey(
                parent,
                instruction,
                input->second
            );

            const bool wasCached = buildCache_.contains(key);

            Layer layer = createLayer(
                parent,
                instruction,
                input->second,
                sizeBytes
            );

            if (wasCached) {
                ++hits;
            } else {
                ++misses;
            }

            selected.push_back(layer.digest);
            parent = layer.digest;
        }

        std::ostringstream manifest;
        for (const auto& digest : selected) {
            manifest << digest << "|";
        }

        const Digest imageId = makeDigest(manifest.str());
        images_[imageId] = selected;

        // A tag is a movable reference to an immutable image identity.
        tags_[repository + ":latest"] = imageId;

        return {imageId, hits, misses};
    }

    void setTag(
        const std::string& imageReference,
        const std::string& repository,
        const std::string& tag
    ) {
        Digest imageId = resolve(imageReference);
        tags_[repository + ":" + tag] = imageId;
    }

    Digest resolve(const std::string& reference) const {
        auto tagIt = tags_.find(reference);
        if (tagIt != tags_.end()) {
            return tagIt->second;
        }

        if (images_.contains(reference)) {
            return reference;
        }

        throw std::out_of_range(
            "unknown image reference: " + reference
        );
    }

    std::uint64_t imageSize(const std::string& reference) const {
        const Digest imageId = resolve(reference);
        const auto& imageLayers = images_.at(imageId);

        std::uint64_t total = 0;

        for (const auto& layerDigest : imageLayers) {
            total += layers_.at(layerDigest).sizeBytes;
        }

        return total;
    }

    void configureCheck(
        const std::string& branch,
        bool passing
    ) {
        checks_[branch] = passing;
    }

    bool canMerge(
        const PullRequestBuild& pullRequest,
        const ProtectedBranchPolicy& policy,
        const std::vector<ReviewDecision>& reviews,
        bool hasMergeConflict
    ) const {
        if (pullRequest.targetBranch != policy.branch) {
            return false;
        }

        if (hasMergeConflict) {
            return false;
        }

        if (policy.requirePassingChecks) {
            auto check = checks_.find(policy.branch);
            if (check == checks_.end() || !check->second) {
                return false;
            }
        }

        unsigned approvals = 0;
        for (const auto& review : reviews) {
            if (review.state == "APPROVED") {
                ++approvals;
            }
        }

        return approvals >= policy.requiredApprovals;
    }

    void printLayers(const std::string& reference) const {
        const Digest imageId = resolve(reference);
        const auto& imageLayers = images_.at(imageId);

        std::cout << "Image " << shortDigest(imageId) << "\n";

        for (const auto& layerDigest : imageLayers) {
            const auto& layer = layers_.at(layerDigest);

            std::cout
                << "  "
                << shortDigest(layer.digest)
                << "  "
                << layer.sizeBytes
                << " bytes  "
                << layer.instruction
                << "\n";
        }
    }
};

int main() {
    try {
        ImageGovernanceEngine engine;

        const std::unordered_map<std::string, std::string> buildContext{
            {"base", "ubuntu-24.04-base-digest"},
            {"dependencies", "libssl-v3|libcurl-v8"},
            {"application", "gateway-v1"}
        };

        const std::vector<
            std::tuple<std::string, std::string, std::uint64_t>
        > steps{
            {
                "FROM ubuntu:24.04",
                "base",
                78ULL * 1024ULL * 1024ULL
            },
            {
                "RUN apt-get install runtime dependencies",
                "dependencies",
                31ULL * 1024ULL * 1024ULL
            },
            {
                "COPY gateway /usr/local/bin/gateway",
                "application",
                3ULL * 1024ULL * 1024ULL
            }
        };

        auto first = engine.build(
            "gateway",
            steps,
            buildContext
        );

        std::cout << "=== Initial image build ===\n";
        std::cout << "image: "
                  << shortDigest(first.imageId) << "\n";
        std::cout << "cache hits: "
                  << first.cacheHits << "\n";
        std::cout << "cache misses: "
                  << first.cacheMisses << "\n";

        engine.setTag(
            first.imageId,
            "gateway",
            "1.0"
        );

        engine.setTag(
            "gateway:1.0",
            "gateway",
            "production"
        );

        engine.printLayers("gateway:production");

        std::cout << "logical image size: "
                  << engine.imageSize("gateway:production")
                  << " bytes\n\n";

        std::unordered_map<std::string, std::string> changedContext =
            buildContext;

        changedContext["application"] = "gateway-v2";

        auto second = engine.build(
            "gateway",
            steps,
            changedContext
        );

        std::cout << "=== Application-only rebuild ===\n";
        std::cout << "cache hits: "
                  << second.cacheHits << "\n";
        std::cout << "cache misses: "
                  << second.cacheMisses << "\n";
        std::cout
            << "The stable base and dependency layers remain reusable "
            << "because the changed input occurs at the final COPY step.\n\n";

        const ProtectedBranchPolicy policy{
            "main",
            2,
            true,
            true,
            false,
            false
        };

        const PullRequestBuild pullRequest{
            "gateway",
            "feature/upgrade-runtime",
            "main",
            {"Dockerfile", "gateway.cpp"}
        };

        engine.configureCheck("main", true);

        const std::vector<ReviewDecision> insufficientReviews{
            {"reviewer-a", "APPROVED"}
        };

        std::cout << "=== Repository-style merge gate ===\n";
        std::cout
            << "merge with one approval: "
            << (engine.canMerge(
                    pullRequest,
                    policy,
                    insufficientReviews,
                    false
                ) ? "allowed" : "blocked")
            << "\n";

        const std::vector<ReviewDecision> sufficientReviews{
            {"reviewer-a", "APPROVED"},
            {"reviewer-b", "APPROVED"}
        };

        std::cout
            << "merge with two approvals and passing checks: "
            << (engine.canMerge(
                    pullRequest,
                    policy,
                    sufficientReviews,
                    false
                ) ? "allowed" : "blocked")
            << "\n";

        std::cout
            << "merge with conflict despite approvals: "
            << (engine.canMerge(
                    pullRequest,
                    policy,
                    sufficientReviews,
                    true
                ) ? "allowed" : "blocked")
            << "\n";

        std::cout
            << "\nThe governance example is deliberately separate from "
            << "image construction: Docker tags and layers describe image "
            << "identity, while the protected-branch policy demonstrates "
            << "how an organization can gate the source change that "
            << "produces an image.\n";

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: "
                  << error.what()
                  << "\n";
        return 1;
    }

    return 0;
}

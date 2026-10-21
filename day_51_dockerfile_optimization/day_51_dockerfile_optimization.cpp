#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Repository-style build pipeline case study.
 *
 * The engine evaluates Docker image optimization decisions for a service:
 * - build context reduction
 * - stable dependency layers
 * - BuildKit-style cache reuse
 * - multi-stage separation
 * - final runtime size
 *
 * Docker itself is not invoked. The program models the decisions that should
 * be made before measuring a real image with Docker tooling.
 */

struct Layer {
    std::string name;
    double size_mb{};
    std::string cache_key;
    bool build_only{false};
    bool expensive{false};
};

struct BuildPolicy {
    double maximum_runtime_image_mb{180.0};
    double maximum_context_mb{150.0};
    bool require_stable_dependency_layer{true};
    bool forbid_build_tools_in_runtime{true};
};

class ImageModel {
private:
    std::string name_;
    double context_mb_;
    double ignored_context_mb_;
    std::vector<Layer> layers_;

public:
    ImageModel(
        std::string name,
        double context_mb,
        double ignored_context_mb,
        std::vector<Layer> layers)
        : name_(std::move(name)),
          context_mb_(context_mb),
          ignored_context_mb_(ignored_context_mb),
          layers_(std::move(layers)) {

        if (name_.empty()) {
            throw std::invalid_argument("Image name cannot be empty");
        }

        if (context_mb_ < 0 || ignored_context_mb_ < 0 ||
            ignored_context_mb_ > context_mb_) {
            throw std::invalid_argument("Invalid build-context sizes");
        }

        if (layers_.empty()) {
            throw std::invalid_argument("An image requires at least one layer");
        }

        for (const auto& layer : layers_) {
            if (layer.size_mb < 0 || layer.cache_key.empty()) {
                throw std::invalid_argument("Invalid layer definition");
            }
        }
    }

    const std::string& name() const {
        return name_;
    }

    const std::vector<Layer>& layers() const {
        return layers_;
    }

    double image_size_mb() const {
        double total = 0.0;
        for (const auto& layer : layers_) {
            total += layer.size_mb;
        }
        return total;
    }

    double effective_context_mb() const {
        return context_mb_ - ignored_context_mb_;
    }
};

class CacheIndex {
private:
    std::set<std::string> reusable_keys_;

public:
    explicit CacheIndex(std::set<std::string> keys)
        : reusable_keys_(std::move(keys)) {}

    std::size_t hits(const ImageModel& image) const {
        std::size_t result = 0;

        for (const auto& layer : image.layers()) {
            if (reusable_keys_.contains(layer.cache_key)) {
                ++result;
            }
        }

        return result;
    }
};

struct GovernanceResult {
    bool image_size_ok{false};
    bool context_size_ok{false};
    bool dependencies_before_source{false};
    bool no_build_tools_in_runtime{false};

    bool accepted() const {
        return image_size_ok &&
               context_size_ok &&
               dependencies_before_source &&
               no_build_tools_in_runtime;
    }
};

class MergeEligibilityStyleEngine {
public:
    static GovernanceResult evaluate(
        const ImageModel& image,
        const BuildPolicy& policy) {

        GovernanceResult result;

        result.image_size_ok =
            image.image_size_mb() <= policy.maximum_runtime_image_mb;

        result.context_size_ok =
            image.effective_context_mb() <= policy.maximum_context_mb;

        std::size_t dependency_index = image.layers().size();
        std::size_t source_index = image.layers().size();

        for (std::size_t i = 0; i < image.layers().size(); ++i) {
            const auto& layer = image.layers()[i];

            if (layer.name.find("dependencies") != std::string::npos ||
                layer.name.find("npm") != std::string::npos ||
                layer.name.find("pip") != std::string::npos) {
                dependency_index = std::min(dependency_index, i);
            }

            if (layer.name.find("source") != std::string::npos ||
                layer.name.find("application") != std::string::npos) {
                source_index = std::min(source_index, i);
            }

            if (policy.forbid_build_tools_in_runtime && layer.build_only) {
                result.no_build_tools_in_runtime = false;
            }
        }

        result.dependencies_before_source =
            !policy.require_stable_dependency_layer ||
            (dependency_index < source_index);

        if (policy.forbid_build_tools_in_runtime) {
            bool has_build_only = false;

            for (const auto& layer : image.layers()) {
                if (layer.build_only) {
                    has_build_only = true;
                    break;
                }
            }

            result.no_build_tools_in_runtime = !has_build_only;
        } else {
            result.no_build_tools_in_runtime = true;
        }

        return result;
    }
};

static void print_image(const ImageModel& image) {
    std::cout << "\n" << image.name() << "\n";
    std::cout << std::string(76, '-') << "\n";

    std::size_t index = 1;

    for (const auto& layer : image.layers()) {
        std::cout << std::setw(2) << index++ << ". "
                  << std::left << std::setw(35) << layer.name
                  << std::right << std::setw(8)
                  << std::fixed << std::setprecision(1)
                  << layer.size_mb << " MB  "
                  << "cache=" << layer.cache_key;

        if (layer.expensive) {
            std::cout << " [expensive]";
        }

        std::cout << "\n";
    }

    std::cout << "Image size: "
              << image.image_size_mb() << " MB\n";

    std::cout << "Effective context: "
              << image.effective_context_mb() << " MB\n";
}

static void print_governance(const GovernanceResult& result) {
    std::cout << "\nOPTIMIZATION GOVERNANCE\n";
    std::cout << std::string(76, '-') << "\n";

    const std::map<std::string, bool> checks{
        {"runtime image size within policy", result.image_size_ok},
        {"build context within policy", result.context_size_ok},
        {"dependency layer precedes source layer",
         result.dependencies_before_source},
        {"build-only tooling excluded from runtime",
         result.no_build_tools_in_runtime}
    };

    for (const auto& [name, passed] : checks) {
        std::cout << "[" << (passed ? "PASS" : "FAIL") << "] "
                  << name << "\n";
    }

    std::cout << "Policy result: "
              << (result.accepted() ? "ACCEPTED" : "REJECTED")
              << "\n";
}

int main() {
    try {
        const ImageModel optimized{
            "orders-api-runtime",
            420.0,
            295.0,
            {
                {"runtime base", 92.0, "ubuntu-runtime"},
                {"production dependencies", 46.0, "requirements-lock", false, true},
                {"application source", 19.0, "application-source"},
                {"runtime configuration", 3.0, "runtime-config"}
            }
        };

        const ImageModel poorly_ordered{
            "orders-api-poor-cache-order",
            420.0,
            250.0,
            {
                {"runtime base", 92.0, "ubuntu-runtime"},
                {"application source", 19.0, "application-source"},
                {"production dependencies", 46.0, "requirements-lock", false, true},
                {"runtime configuration", 3.0, "runtime-config"}
            }
        };

        const BuildPolicy policy{
            180.0,
            150.0,
            true,
            true
        };

        const CacheIndex cache{
            {
                "ubuntu-runtime",
                "requirements-lock"
            }
        };

        print_image(optimized);
        print_image(poorly_ordered);

        std::cout << "\nCACHE OBSERVATION\n";
        std::cout << std::string(76, '-') << "\n";

        std::cout << "Optimized reusable layers: "
                  << cache.hits(optimized) << "/"
                  << optimized.layers().size() << "\n";

        std::cout << "Poorly ordered reusable layers: "
                  << cache.hits(poorly_ordered) << "/"
                  << poorly_ordered.layers().size() << "\n";

        const auto optimized_result =
            MergeEligibilityStyleEngine::evaluate(optimized, policy);

        const auto poor_result =
            MergeEligibilityStyleEngine::evaluate(poorly_ordered, policy);

        print_governance(optimized_result);

        std::cout << "\nPOOR CACHE ORDERING POLICY CHECK\n";
        print_governance(poor_result);

        /*
         * A dependency layer should depend on stable dependency metadata,
         * not on frequently changing application source. This keeps source
         * changes from invalidating expensive package installation work.
         */
        if (!optimized_result.dependencies_before_source) {
            std::cerr << "Invalid optimization ordering\n";
            return 1;
        }

        return optimized_result.accepted() ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << "Configuration error: "
                  << error.what() << "\n";
        return 1;
    }
}

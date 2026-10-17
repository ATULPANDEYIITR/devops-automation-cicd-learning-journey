#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Case study: an operations team deploys an inventory API and a web gateway.
 *
 * The engine models content-addressed image layers, local image storage,
 * registry publication, container state transitions, port allocation,
 * resource limits, and deployment eligibility.
 *
 * Compile: g++ -std=c++17 -Wall -Wextra -pedantic docker_case_study.cpp -o docker_case_study
 * Run: ./docker_case_study
 */

class DockerError : public std::runtime_error {
public:
    explicit DockerError(const std::string& message)
        : std::runtime_error(message) {}
};

struct ImageLayer {
    std::string digest;
    std::string instruction;
    double sizeMB;

    ImageLayer(std::string digestValue, std::string instructionValue,
               double size)
        : digest(std::move(digestValue)),
          instruction(std::move(instructionValue)),
          sizeMB(size) {
        if (digest.empty() || instruction.empty() || sizeMB < 0.0) {
            throw DockerError("Invalid image layer metadata.");
        }
    }
};

struct Image {
    std::string repository;
    std::string tag;
    std::vector<ImageLayer> layers;
    std::vector<std::string> entrypoint;
    std::map<std::string, std::string> environment;

    Image(std::string repositoryValue, std::string tagValue,
          std::vector<ImageLayer> layerValues,
          std::vector<std::string> command)
        : repository(std::move(repositoryValue)),
          tag(std::move(tagValue)),
          layers(std::move(layerValues)),
          entrypoint(std::move(command)) {
        if (repository.empty() || tag.empty() || layers.empty() ||
            entrypoint.empty()) {
            throw DockerError("Image requires a name, tag, layers, and command.");
        }
    }

    std::string reference() const {
        return repository + ":" + tag;
    }

    double sizeMB() const {
        double total = 0.0;
        for (const auto& layer : layers) {
            total += layer.sizeMB;
        }
        return total;
    }
};

class ImageStore {
private:
    std::map<std::string, Image> images_;
    std::map<std::string, ImageLayer> uniqueLayers_;

public:
    void add(const Image& image) {
        images_[image.reference()] = image;

        // Deduplicate layers by digest, as a local image store does.
        for (const auto& layer : image.layers) {
            uniqueLayers_.emplace(layer.digest, layer);
        }
    }

    const Image& require(const std::string& reference) const {
        const auto it = images_.find(reference);
        if (it == images_.end()) {
            throw DockerError("Image is not present locally: " + reference);
        }
        return it->second;
    }

    double storageMB() const {
        double total = 0.0;
        for (const auto& item : uniqueLayers_) {
            total += item.second.sizeMB;
        }
        return total;
    }

    void report() const {
        std::cout << "Local images:\n";
        for (const auto& item : images_) {
            std::cout << "  " << item.first << " ("
                      << item.second.sizeMB() << " MB)\n";
        }
        std::cout << "Unique layer storage: " << storageMB() << " MB\n";
    }
};

class ImageRegistry {
private:
    std::string hostname_;
    bool authenticated_ = false;
    std::map<std::string, Image> images_;

public:
    explicit ImageRegistry(std::string hostname)
        : hostname_(std::move(hostname)) {
        if (hostname_.empty() || hostname_.find('/') != std::string::npos) {
            throw DockerError("Registry hostname is invalid.");
        }
    }

    void login(const std::string& token) {
        if (token.empty()) {
            throw DockerError("Registry token cannot be empty.");
        }
        authenticated_ = true;
    }

    std::string push(const Image& image, const std::string& repository,
                     const std::string& tag) {
        if (!authenticated_) {
            throw DockerError("Registry authentication is required.");
        }
        if (repository.empty() || tag.empty()) {
            throw DockerError("Remote repository and tag are required.");
        }

        const std::string remote =
            hostname_ + "/" + repository + ":" + tag;
        images_[remote] = image;
        std::cout << "Published manifest: " << remote << '\n';
        return remote;
    }

    Image pull(const std::string& remoteReference) const {
        const auto it = images_.find(remoteReference);
        if (it == images_.end()) {
            throw DockerError("Registry image not found: " + remoteReference);
        }
        return it->second;
    }
};

enum class ContainerState {
    Created,
    Running,
    Stopped,
    Removed
};

std::string stateName(ContainerState state) {
    switch (state) {
        case ContainerState::Created: return "created";
        case ContainerState::Running: return "running";
        case ContainerState::Stopped: return "stopped";
        case ContainerState::Removed: return "removed";
    }
    return "unknown";
}

struct Container {
    std::string id;
    std::string name;
    std::string imageReference;
    std::vector<std::string> command;
    std::map<int, int> ports; // container port -> host port
    int memoryLimitMB;
    ContainerState state = ContainerState::Created;
    int exitCode = -1;
};

class DockerHost {
private:
    const int memoryCapacityMB_;
    int nextID_ = 1;
    std::map<std::string, Container> containers_;
    std::map<int, std::string> allocatedHostPorts_;

public:
    explicit DockerHost(int memoryCapacityMB)
        : memoryCapacityMB_(memoryCapacityMB) {
        if (memoryCapacityMB_ <= 0) {
            throw DockerError("Host memory capacity must be positive.");
        }
    }

    Container& create(const ImageStore& store, const std::string& imageRef,
                      const std::string& name, const std::map<int, int>& ports,
                      int memoryLimitMB) {
        const Image& image = store.require(imageRef);

        if (name.empty()) {
            throw DockerError("Container name cannot be empty.");
        }
        for (const auto& item : containers_) {
            if (item.second.name == name &&
                item.second.state != ContainerState::Removed) {
                throw DockerError("Container name is already in use: " + name);
            }
        }
        if (memoryLimitMB <= 0 || memoryLimitMB > memoryCapacityMB_) {
            throw DockerError("Container memory limit is invalid.");
        }

        // Validate every binding before reserving any port. This avoids
        // partially allocated resources if a later binding is invalid.
        std::set<int> requestedHostPorts;
        for (const auto& binding : ports) {
            const int containerPort = binding.first;
            const int hostPort = binding.second;

            if (containerPort < 1 || containerPort > 65535 ||
                hostPort < 1 || hostPort > 65535) {
                throw DockerError("Port numbers must be in the valid TCP range.");
            }
            if (allocatedHostPorts_.count(hostPort) ||
                !requestedHostPorts.insert(hostPort).second) {
                throw DockerError("Host port is already allocated: " +
                                  std::to_string(hostPort));
            }
        }

        std::ostringstream id;
        id << "ctr-" << std::setw(4) << std::setfill('0') << nextID_++;

        Container container{
            id.str(), name, imageRef, image.entrypoint, ports, memoryLimitMB
        };
        auto result = containers_.emplace(container.id, container);
        for (const auto& binding : ports) {
            allocatedHostPorts_[binding.second] = container.id;
        }

        std::cout << "Created " << name << " from " << imageRef << '\n';
        return result.first->second;
    }

    void start(const std::string& id) {
        Container& container = require(id);
        if (container.state != ContainerState::Created &&
            container.state != ContainerState::Stopped) {
            throw DockerError("Invalid start transition from " +
                              stateName(container.state));
        }

        container.state = ContainerState::Running;
        container.exitCode = -1;
        std::cout << "Started " << container.name << '\n';
    }

    void stop(const std::string& id, int exitCode = 0) {
        Container& container = require(id);
        if (container.state != ContainerState::Running) {
            throw DockerError("Only running containers can be stopped.");
        }

        container.state = ContainerState::Stopped;
        container.exitCode = exitCode;
        std::cout << "Stopped " << container.name
                  << " with exit code " << exitCode << '\n';
    }

    void remove(const std::string& id) {
        Container& container = require(id);
        if (container.state == ContainerState::Running ||
            container.state == ContainerState::Removed) {
            throw DockerError("Container cannot be removed in its current state.");
        }

        for (const auto& binding : container.ports) {
            allocatedHostPorts_.erase(binding.second);
        }
        container.state = ContainerState::Removed;
        std::cout << "Removed container " << container.name << '\n';
    }

    int configuredRunningMemoryMB() const {
        int total = 0;
        for (const auto& item : containers_) {
            if (item.second.state == ContainerState::Running) {
                total += item.second.memoryLimitMB;
            }
        }
        return total;
    }

    void report() const {
        for (const auto& item : containers_) {
            const Container& c = item.second;
            if (c.state == ContainerState::Removed) {
                continue;
            }

            std::cout << c.name << " | " << c.imageReference << " | "
                      << stateName(c.state) << " | memory limit "
                      << c.memoryLimitMB << " MB\n";

            for (const auto& binding : c.ports) {
                std::cout << "  host:" << binding.second
                          << " -> container:" << binding.first << '\n';
            }
        }
        std::cout << "Configured running memory: "
                  << configuredRunningMemoryMB() << " / "
                  << memoryCapacityMB_ << " MB\n";
    }

private:
    Container& require(const std::string& id) {
        const auto it = containers_.find(id);
        if (it == containers_.end()) {
            throw DockerError("Unknown container ID: " + id);
        }
        return it->second;
    }
};

bool deploymentEligible(const Image& image, const Container& container) {
    if (image.tag == "latest") {
        std::cout << "Rejected: production images require an explicit version.\n";
        return false;
    }
    if (container.state != ContainerState::Running) {
        std::cout << "Rejected: container is not running.\n";
        return false;
    }
    if (container.memoryLimitMB < 128) {
        std::cout << "Rejected: memory limit is below the policy minimum.\n";
        return false;
    }
    return true;
}

int main() {
    try {
        const ImageLayer runtime(
            "sha256:runtime", "Minimal application runtime", 72.0);
        const ImageLayer dependencies(
            "sha256:dependencies", "Pinned production dependencies", 26.0);
        const ImageLayer application(
            "sha256:app", "Inventory API application", 7.5);
        const ImageLayer webServer(
            "sha256:web", "Static web server", 20.0);

        Image api(
            "inventory-api", "2.1.0",
            {runtime, dependencies, application},
            {"./inventory-api", "--port", "8000"});
        api.environment["APP_MODE"] = "production";

        // The API and a web image share a base layer, so the store only
        // charges for that layer once when calculating local storage.
        Image web(
            "inventory-web", "2.1.0",
            {webServer, application},
            {"./web-server", "--port", "8080"});

        ImageStore localImages;
        localImages.add(api);
        localImages.add(web);
        localImages.report();

        ImageRegistry registry("registry.example.com");
        try {
            registry.push(api, "operations/inventory-api", "2.1.0");
        } catch (const DockerError& error) {
            std::cout << "Expected push failure: " << error.what() << '\n';
        }

        registry.login("demo-token");
        const std::string remoteRef =
            registry.push(api, "operations/inventory-api", "2.1.0");

        ImageStore deploymentImages;
        deploymentImages.add(registry.pull(remoteRef));
        std::cout << "Deployment image available: "
                  << deploymentImages.require("inventory-api:2.1.0").reference()
                  << '\n';

        DockerHost host(2048);
        Container& apiContainer = host.create(
            localImages, "inventory-api:2.1.0", "inventory-api",
            {{8000, 18000}}, 512);
        host.start(apiContainer.id);

        try {
            host.create(localImages, "inventory-web:2.1.0", "conflicting-web",
                        {{8080, 18000}}, 256);
        } catch (const DockerError& error) {
            std::cout << "Expected port conflict: " << error.what() << '\n';
        }

        Container& webContainer = host.create(
            localImages, "inventory-web:2.1.0", "inventory-web",
            {{8080, 18080}}, 256);
        host.start(webContainer.id);

        host.report();
        std::cout << "API deployment policy: "
                  << (deploymentEligible(api, apiContainer) ? "PASS" : "FAIL")
                  << '\n';

        try {
            host.remove(apiContainer.id);
        } catch (const DockerError& error) {
            std::cout << "Expected lifecycle failure: " << error.what() << '\n';
        }

        host.stop(apiContainer.id);
        host.remove(apiContainer.id);
        std::cout << "Image remains in the local store after container removal: "
                  << localImages.require("inventory-api:2.1.0").reference()
                  << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Docker case study failed: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

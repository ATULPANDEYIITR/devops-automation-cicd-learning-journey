#include <algorithm>
#include <cassert>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

enum class StorageType {
    NamedVolume,
    BindMount,
    Ephemeral
};

std::string toString(StorageType type) {
    switch (type) {
        case StorageType::NamedVolume:
            return "named-volume";
        case StorageType::BindMount:
            return "bind-mount";
        case StorageType::Ephemeral:
            return "ephemeral";
    }
    return "unknown";
}

struct Mount {
    std::string source;
    std::string destination;
    StorageType type;
    bool readOnly;
};

struct Volume {
    std::string name;
    std::map<std::string, std::string> files;
    std::set<std::string> attachedContainers;
};

struct BindMount {
    std::string hostPath;
    std::map<std::string, std::string> files;
    bool readOnly;
};

struct Container {
    std::string id;
    std::vector<Mount> mounts;
    std::map<std::string, std::string> ephemeralFiles;
    bool running{false};
};

class StorageException : public std::runtime_error {
public:
    explicit StorageException(const std::string& message)
        : std::runtime_error(message) {}
};

class StorageEngine {
private:
    std::map<std::string, Volume> volumes;
    std::map<std::string, BindMount> bindMounts;
    std::map<std::string, Container> containers;

    static void validateName(const std::string& name) {
        if (name.empty() || name.size() > 63) {
            throw StorageException("Invalid storage object name");
        }

        for (char c : name) {
            const bool allowed =
                std::isalnum(static_cast<unsigned char>(c)) ||
                c == '-' || c == '_' || c == '.';

            if (!allowed) {
                throw StorageException("Storage name contains invalid characters");
            }
        }
    }

    static std::string normalizeContainerPath(const std::string& path) {
        if (path.empty() || path.front() != '/') {
            throw StorageException("Container path must be absolute");
        }

        std::vector<std::string> parts;
        std::stringstream stream(path);
        std::string part;

        while (std::getline(stream, part, '/')) {
            if (part.empty() || part == ".") {
                continue;
            }

            if (part == "..") {
                throw StorageException("Parent traversal is forbidden");
            }

            parts.push_back(part);
        }

        std::ostringstream result;
        for (const auto& item : parts) {
            result << '/' << item;
        }

        return result.str().empty() ? "/" : result.str();
    }

    Container& container(const std::string& id) {
        auto it = containers.find(id);
        if (it == containers.end()) {
            throw StorageException("Container not found: " + id);
        }
        return it->second;
    }

    Volume& volume(const std::string& name) {
        auto it = volumes.find(name);
        if (it == volumes.end()) {
            throw StorageException("Named volume not found: " + name);
        }
        return it->second;
    }

    static std::string relativePath(
        const std::string& path,
        const std::string& base = "/"
    ) {
        const auto normalizedPath = normalizeContainerPath(path);
        const auto normalizedBase = normalizeContainerPath(base);

        if (normalizedBase == "/") {
            return normalizedPath.substr(1);
        }

        if (normalizedPath == normalizedBase) {
            return ".";
        }

        const std::string prefix = normalizedBase + "/";
        if (normalizedPath.rfind(prefix, 0) != 0) {
            throw StorageException("Path is outside mounted destination");
        }

        return normalizedPath.substr(prefix.size());
    }

    const Mount* resolveMount(
        const Container& containerRef,
        const std::string& path
    ) const {
        const auto normalized = normalizeContainerPath(path);
        const Mount* selected = nullptr;

        for (const auto& mount : containerRef.mounts) {
            const std::string destination =
                normalizeContainerPath(mount.destination);

            const bool matches =
                normalized == destination ||
                normalized.rfind(destination + "/", 0) == 0;

            if (matches &&
                (selected == nullptr ||
                 destination.size() >
                     normalizeContainerPath(selected->destination).size())) {
                selected = &mount;
            }
        }

        return selected;
    }

    std::map<std::string, std::string>& mountedData(const Mount& mount) {
        if (mount.type == StorageType::NamedVolume) {
            return volume(mount.source).files;
        }

        if (mount.type == StorageType::BindMount) {
            auto it = bindMounts.find(mount.source);
            if (it == bindMounts.end()) {
                throw StorageException("Bind mount not found");
            }
            return it->second.files;
        }

        throw StorageException("Ephemeral storage has no mounted source");
    }

public:
    void createNamedVolume(const std::string& name) {
        validateName(name);

        if (volumes.contains(name)) {
            throw StorageException("Named volume already exists");
        }

        volumes.emplace(name, Volume{name});
    }

    void registerBindMount(
        const std::string& hostPath,
        bool readOnly = false
    ) {
        if (hostPath.empty()) {
            throw StorageException("Host path cannot be empty");
        }

        if (bindMounts.contains(hostPath)) {
            throw StorageException("Bind mount already registered");
        }

        bindMounts.emplace(
            hostPath,
            BindMount{hostPath, {}, readOnly}
        );
    }

    void createContainer(const std::string& id) {
        validateName(id);

        if (containers.contains(id)) {
            throw StorageException("Container already exists");
        }

        containers.emplace(id, Container{id});
    }

    void start(const std::string& id) {
        container(id).running = true;
    }

    void stop(const std::string& id) {
        container(id).running = false;
    }

    void attachNamedVolume(
        const std::string& containerId,
        const std::string& volumeName,
        const std::string& destination,
        bool readOnly = false
    ) {
        auto& targetContainer = container(containerId);
        auto& targetVolume = volume(volumeName);

        addMount(
            targetContainer,
            Mount{
                volumeName,
                normalizeContainerPath(destination),
                StorageType::NamedVolume,
                readOnly
            }
        );

        targetVolume.attachedContainers.insert(containerId);
    }

    void attachBindMount(
        const std::string& containerId,
        const std::string& hostPath,
        const std::string& destination,
        bool readOnly = false
    ) {
        auto& targetContainer = container(containerId);

        if (!bindMounts.contains(hostPath)) {
            throw StorageException("Bind source is not registered");
        }

        addMount(
            targetContainer,
            Mount{
                hostPath,
                normalizeContainerPath(destination),
                StorageType::BindMount,
                readOnly
            }
        );
    }

    void addMount(Container& target, const Mount& mount) {
        for (const auto& existing : target.mounts) {
            if (existing.destination == mount.destination) {
                throw StorageException(
                    "Mount destination conflict: " + mount.destination
                );
            }
        }

        target.mounts.push_back(mount);
    }

    void write(
        const std::string& containerId,
        const std::string& path,
        const std::string& content
    ) {
        auto& targetContainer = container(containerId);
        const Mount* mount = resolveMount(targetContainer, path);

        if (mount == nullptr) {
            targetContainer.ephemeralFiles[relativePath(path)] = content;
            return;
        }

        if (mount->readOnly) {
            throw StorageException(
                "Write rejected by read-only mount: " + mount->destination
            );
        }

        mountedData(*mount)[relativePath(path, mount->destination)] = content;
    }

    std::string read(
        const std::string& containerId,
        const std::string& path
    ) {
        auto& targetContainer = container(containerId);
        const Mount* mount = resolveMount(targetContainer, path);

        if (mount == nullptr) {
            const auto key = relativePath(path);
            auto it = targetContainer.ephemeralFiles.find(key);

            if (it == targetContainer.ephemeralFiles.end()) {
                throw StorageException("Ephemeral file does not exist");
            }

            return it->second;
        }

        auto& files = mountedData(*mount);
        const auto key = relativePath(path, mount->destination);
        auto it = files.find(key);

        if (it == files.end()) {
            throw StorageException("Persistent file does not exist");
        }

        return it->second;
    }

    void removeContainer(const std::string& id) {
        auto& targetContainer = container(id);

        for (const auto& mount : targetContainer.mounts) {
            if (mount.type == StorageType::NamedVolume) {
                volume(mount.source).attachedContainers.erase(id);
            }
        }

        containers.erase(id);
    }

    std::map<std::string, std::string> backupVolume(
        const std::string& volumeName
    ) {
        return volume(volumeName).files;
    }

    void restoreVolume(
        const std::string& volumeName,
        const std::map<std::string, std::string>& backup
    ) {
        volume(volumeName).files = backup;
    }

    void removeVolume(
        const std::string& volumeName,
        bool force = false
    ) {
        auto& targetVolume = volume(volumeName);

        if (!targetVolume.attachedContainers.empty() && !force) {
            throw StorageException(
                "Volume remains attached; detach containers first"
            );
        }

        if (force) {
            for (const auto& containerId :
                 targetVolume.attachedContainers) {
                auto& targetContainer = container(containerId);

                targetContainer.mounts.erase(
                    std::remove_if(
                        targetContainer.mounts.begin(),
                        targetContainer.mounts.end(),
                        [&](const Mount& mount) {
                            return mount.type == StorageType::NamedVolume &&
                                   mount.source == volumeName;
                        }
                    ),
                    targetContainer.mounts.end()
                );
            }

            targetVolume.attachedContainers.clear();
        }

        volumes.erase(volumeName);
    }

    void report() const {
        std::cout << "\nStorage inventory\n";

        for (const auto& [name, volume] : volumes) {
            std::cout << "Named volume: " << name << '\n';
            std::cout << "  files: " << volume.files.size() << '\n';
            std::cout << "  attached containers: "
                      << volume.attachedContainers.size() << '\n';
        }

        for (const auto& [path, bind] : bindMounts) {
            std::cout << "Bind mount: " << path
                      << " read_only=" << std::boolalpha
                      << bind.readOnly << '\n';
        }

        for (const auto& [id, targetContainer] : containers) {
            std::cout << "Container: " << id
                      << " running=" << std::boolalpha
                      << targetContainer.running
                      << " ephemeral_files="
                      << targetContainer.ephemeralFiles.size()
                      << " mounts="
                      << targetContainer.mounts.size()
                      << '\n';
        }
    }
};

int main() {
    try {
        StorageEngine engine;

        engine.createNamedVolume("orders-db");
        engine.registerBindMount("/srv/app/config", true);

        engine.createContainer("orders-v1");
        engine.attachNamedVolume(
            "orders-v1",
            "orders-db",
            "/var/lib/orders"
        );

        engine.start("orders-v1");

        engine.write(
            "orders-v1",
            "/var/lib/orders/orders.dat",
            "orders=250"
        );

        engine.stop("orders-v1");
        engine.removeContainer("orders-v1");

        /*
         * Recreating the container demonstrates that named-volume data
         * belongs to the volume lifecycle rather than the container.
         */
        engine.createContainer("orders-v2");
        engine.attachNamedVolume(
            "orders-v2",
            "orders-db",
            "/var/lib/orders"
        );

        assert(
            engine.read(
                "orders-v2",
                "/var/lib/orders/orders.dat"
            ) == "orders=250"
        );

        std::cout
            << "Named volume survived container replacement: "
            << engine.read(
                "orders-v2",
                "/var/lib/orders/orders.dat"
            )
            << '\n';

        engine.createContainer("config-reader");
        engine.attachBindMount(
            "config-reader",
            "/srv/app/config",
            "/etc/app",
            true
        );

        try {
            engine.write(
                "config-reader",
                "/etc/app/application.conf",
                "production=true"
            );
        } catch (const StorageException& error) {
            std::cout
                << "Read-only bind mount rejected write: "
                << error.what()
                << '\n';
        }

        /*
         * No mount means the file belongs to the container's writable
         * layer and disappears when that container is removed.
         */
        engine.createContainer("temporary-worker");
        engine.write(
            "temporary-worker",
            "/tmp/job.result",
            "completed"
        );

        engine.removeContainer("temporary-worker");
        engine.createContainer("replacement-worker");

        try {
            engine.read(
                "replacement-worker",
                "/tmp/job.result"
            );
        } catch (const StorageException& error) {
            std::cout
                << "Ephemeral data correctly disappeared: "
                << error.what()
                << '\n';
        }

        auto backup = engine.backupVolume("orders-db");

        backup["orders.dat"] = "orders=300";
        engine.restoreVolume("orders-db", backup);

        std::cout
            << "Restored volume content: "
            << engine.read(
                "orders-v2",
                "/var/lib/orders/orders.dat"
            )
            << '\n';

        try {
            engine.removeVolume("orders-db");
        } catch (const StorageException& error) {
            std::cout
                << "Unsafe volume removal rejected: "
                << error.what()
                << '\n';
        }

        engine.removeContainer("orders-v2");
        engine.removeVolume("orders-db");

        engine.report();

        /*
         * Performance:
         * std::map gives predictable O(log n) lookup. A production
         * storage metadata service could use unordered_map for average
         * O(1) lookup while retaining explicit locking and validation.
         *
         * Security:
         * container paths reject parent traversal, read-only mounts
         * prevent mutation, and volume deletion is blocked while
         * dependencies remain attached.
         */
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal storage error: "
            << error.what()
            << '\n';
        return 1;
    }

    return 0;
}

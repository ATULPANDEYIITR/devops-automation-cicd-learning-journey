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
#include <utility>
#include <vector>

/*
 * Repository governance case study:
 *
 * A build platform resolves dependencies from an internal release repository,
 * a remote-cache repository, and a public group endpoint. The program models
 * format compatibility, publishing policy, repository permissions, cache
 * provenance, integrity metadata, and deterministic dependency resolution.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic nexus_case_study.cpp -o nexus_case_study
 *
 * No external libraries are required. The digest field is illustrative:
 * production repositories must use a cryptographic hash implementation such
 * as SHA-256 rather than this deterministic demonstration fingerprint.
 */

enum class RepositoryType {
    Hosted,
    Proxy,
    Group
};

enum class Format {
    Maven,
    Npm,
    PyPI,
    Docker,
    Raw
};

enum class Permission {
    Read,
    Publish,
    Delete,
    Admin
};

enum class ArtifactState {
    Published,
    Cached
};

std::string to_string(RepositoryType type) {
    switch (type) {
        case RepositoryType::Hosted: return "hosted";
        case RepositoryType::Proxy: return "proxy";
        case RepositoryType::Group: return "group";
    }
    throw std::logic_error("Unknown repository type");
}

std::string to_string(Format format) {
    switch (format) {
        case Format::Maven: return "maven";
        case Format::Npm: return "npm";
        case Format::PyPI: return "pypi";
        case Format::Docker: return "docker";
        case Format::Raw: return "raw";
    }
    throw std::logic_error("Unknown artifact format");
}

struct Coordinate {
    Format format;
    std::string name;
    std::string version;
    std::string extension;
    std::string classifier;
    std::string raw_path;

    void validate() const {
        if (name.empty() || version.empty()) {
            throw std::invalid_argument("Name and version are required");
        }

        if (name.find("..") != std::string::npos ||
            name.find('\\') != std::string::npos ||
            version.find('/') != std::string::npos ||
            version.find('\\') != std::string::npos) {
            throw std::invalid_argument("Unsafe artifact coordinate");
        }

        if (format == Format::Maven) {
            const auto separator = name.find(':');
            if (separator == std::string::npos ||
                separator == 0 ||
                separator + 1 == name.size() ||
                name.find(':', separator + 1) != std::string::npos ||
                extension.empty()) {
                throw std::invalid_argument(
                    "Maven coordinates require group:artifact and extension"
                );
            }
        }

        if (format == Format::Raw) {
            if (raw_path.empty() || raw_path.front() == '/' ||
                raw_path.find("/../") != std::string::npos ||
                raw_path == ".." ||
                raw_path.find('\\') != std::string::npos) {
                throw std::invalid_argument("Invalid raw artifact path");
            }
        }

        if (format == Format::Docker &&
            name.find(' ') != std::string::npos) {
            throw std::invalid_argument("Docker image names cannot contain spaces");
        }
    }

    std::string key() const {
        validate();

        if (format == Format::Maven) {
            const auto separator = name.find(':');
            std::string group = name.substr(0, separator);
            const std::string artifact = name.substr(separator + 1);

            std::replace(group.begin(), group.end(), '.', '/');

            std::ostringstream path;
            path << group << '/' << artifact << '/' << version << '/'
                 << artifact << '-' << version;

            if (!classifier.empty()) {
                path << '-' << classifier;
            }

            path << '.' << extension;
            return path.str();
        }

        if (format == Format::Npm) {
            return name + "/-/" + name + "-" + version + ".tgz";
        }

        if (format == Format::PyPI) {
            return name + "/" + version + "/" +
                (extension.empty() ? name + "-" + version + ".whl" :
                                     extension);
        }

        if (format == Format::Docker) {
            return name + "/manifests/" + version;
        }

        return raw_path;
    }

    bool operator<(const Coordinate& other) const {
        return std::tie(format, name, version, extension, classifier, raw_path) <
               std::tie(other.format, other.name, other.version,
                        other.extension, other.classifier, other.raw_path);
    }
};

struct Principal {
    std::string username;
    std::map<std::string, std::set<Permission>> grants;

    bool can(const std::string& repository, Permission permission) const {
        const auto exact = grants.find(repository);
        const auto wildcard = grants.find("*");

        auto contains = [permission](const auto& entry) {
            return entry != std::set<Permission>{} &&
                (entry.count(permission) || entry.count(Permission::Admin));
        };

        return (exact != grants.end() && contains(exact->second)) ||
               (wildcard != grants.end() && contains(wildcard->second));
    }
};

struct Artifact {
    Coordinate coordinate;
    std::string content;
    std::string fingerprint;
    std::string publisher;
    ArtifactState state;
};

struct Repository {
    std::string name;
    RepositoryType type;
    Format format;
    bool allow_redeploy = false;
    std::vector<std::string> members;
    std::map<Coordinate, Artifact> artifacts;
    std::size_t cache_hits = 0;
    std::size_t cache_misses = 0;
};

class RepositoryManager {
public:
    void add_repository(Repository repository) {
        if (repository.name.empty()) {
            throw std::invalid_argument("Repository name cannot be empty");
        }
        if (repositories_.count(repository.name)) {
            throw std::invalid_argument("Duplicate repository name");
        }
        if (repository.type == RepositoryType::Group &&
            repository.members.empty()) {
            throw std::invalid_argument("Group repository requires members");
        }
        if (repository.type != RepositoryType::Hosted &&
            repository.allow_redeploy) {
            throw std::invalid_argument("Redeployment applies only to hosted repositories");
        }

        for (const auto& member : repository.members) {
            if (!repositories_.count(member)) {
                throw std::invalid_argument("Group member must exist before group creation");
            }
        }

        repositories_.emplace(repository.name, std::move(repository));
    }

    Artifact publish(
        const std::string& repository_name,
        const Coordinate& coordinate,
        const std::string& content,
        const Principal& principal
    ) {
        Repository& repository = get(repository_name);
        authorize(repository_name, Permission::Publish, principal);

        if (repository.type != RepositoryType::Hosted) {
            throw std::runtime_error("Only hosted repositories accept artifacts");
        }
        if (repository.format != coordinate.format) {
            throw std::runtime_error("Repository and artifact formats differ");
        }
        if (content.empty()) {
            throw std::invalid_argument("Artifact content cannot be empty");
        }

        coordinate.validate();

        const auto existing = repository.artifacts.find(coordinate);
        if (existing != repository.artifacts.end() && !repository.allow_redeploy) {
            throw std::runtime_error("Release redeployment is forbidden");
        }

        Artifact artifact{
            coordinate,
            content,
            fingerprint(content),
            principal.username,
            ArtifactState::Published
        };

        repository.artifacts[coordinate] = artifact;
        events_.push_back(
            "publish " + repository_name + "/" + coordinate.key() +
            " sha256-demo=" + artifact.fingerprint
        );

        return artifact;
    }

    Artifact retrieve(
        const std::string& repository_name,
        const Coordinate& coordinate,
        const Principal& principal
    ) {
        authorize(repository_name, Permission::Read, principal);
        std::set<std::string> visited;
        return resolve(repository_name, coordinate, visited);
    }

    void remove(
        const std::string& repository_name,
        const Coordinate& coordinate,
        const Principal& principal
    ) {
        Repository& repository = get(repository_name);
        authorize(repository_name, Permission::Delete, principal);

        if (repository.type != RepositoryType::Hosted) {
            throw std::runtime_error("Deletion is restricted to hosted repositories");
        }

        const auto removed = repository.artifacts.erase(coordinate);
        if (!removed) {
            throw std::runtime_error("Artifact does not exist");
        }

        events_.push_back("delete " + repository_name + "/" + coordinate.key());
    }

    void print_inventory(const std::string& repository_name) const {
        const auto iterator = repositories_.find(repository_name);
        if (iterator == repositories_.end()) {
            throw std::runtime_error("Unknown repository");
        }

        const Repository& repository = iterator->second;
        std::cout << "\nRepository: " << repository.name
                  << " [" << to_string(repository.type) << ", "
                  << to_string(repository.format) << "]\n";

        for (const auto& entry : repository.artifacts) {
            std::cout << "  " << entry.first.key()
                      << " | bytes=" << entry.second.content.size()
                      << " | digest=" << entry.second.fingerprint
                      << " | publisher=" << entry.second.publisher
                      << " | state="
                      << (entry.second.state == ArtifactState::Cached ?
                          "cached" : "published")
                      << '\n';
        }

        std::cout << "  cache hits=" << repository.cache_hits
                  << ", misses=" << repository.cache_misses << '\n';
    }

    void print_events() const {
        std::cout << "\nAudit events\n";
        for (const auto& event : events_) {
            std::cout << "  " << event << '\n';
        }
    }

private:
    std::map<std::string, Repository> repositories_;
    std::vector<std::string> events_;

    Repository& get(const std::string& name) {
        const auto iterator = repositories_.find(name);
        if (iterator == repositories_.end()) {
            throw std::runtime_error("Unknown repository: " + name);
        }
        return iterator->second;
    }

    const Repository& get(const std::string& name) const {
        const auto iterator = repositories_.find(name);
        if (iterator == repositories_.end()) {
            throw std::runtime_error("Unknown repository: " + name);
        }
        return iterator->second;
    }

    static void authorize(
        const std::string& repository,
        Permission permission,
        const Principal& principal
    ) {
        if (!principal.can(repository, permission)) {
            throw std::runtime_error(
                "Authorization denied for " + principal.username +
                " on " + repository
            );
        }
    }

    static std::string fingerprint(const std::string& content) {
        // FNV-1a is deliberately used only to keep this program dependency-free.
        // It is not cryptographically secure and must never validate real artifacts.
        std::uint64_t hash = 14695981039346656037ULL;
        for (unsigned char byte : content) {
            hash ^= byte;
            hash *= 1099511628211ULL;
        }

        std::ostringstream output;
        output << std::hex << std::setw(16) << std::setfill('0') << hash;
        return output.str();
    }

    Artifact resolve(
        const std::string& repository_name,
        const Coordinate& coordinate,
        std::set<std::string>& visited
    ) {
        if (visited.count(repository_name)) {
            throw std::runtime_error("Repository resolution cycle detected");
        }

        Repository& repository = get(repository_name);
        if (repository.format != coordinate.format) {
            throw std::runtime_error("Artifact format mismatch");
        }

        const auto cached = repository.artifacts.find(coordinate);
        if (cached != repository.artifacts.end()) {
            ++repository.cache_hits;
            return cached->second;
        }

        ++repository.cache_misses;
        visited.insert(repository_name);

        if (repository.type == RepositoryType::Hosted) {
            throw std::runtime_error(
                "Artifact not found in hosted repository: " + repository_name
            );
        }

        if (repository.type == RepositoryType::Group) {
            for (const auto& member : repository.members) {
                auto member_visited = visited;
                try {
                    return resolve(member, coordinate, member_visited);
                } catch (const std::runtime_error&) {
                    // A group can continue after a missing member. In production,
                    // distinguish not-found responses from authorization and outage
                    // failures instead of treating every error as a cache miss.
                }
            }
            throw std::runtime_error("No group member resolved the artifact");
        }

        // Real proxy repositories make an HTTP request here. This case study
        // models a known public dependency to keep execution deterministic.
        const std::string expected =
            "org.example:metrics-core@1.0.0";
        const std::string actual =
            coordinate.name + "@" + coordinate.version;

        if (actual != expected) {
            throw std::runtime_error("Simulated upstream returned HTTP 404");
        }

        Artifact artifact{
            coordinate,
            "public metrics dependency bytes",
            fingerprint("public metrics dependency bytes"),
            "upstream:" + repository.name,
            ArtifactState::Cached
        };

        repository.artifacts.emplace(coordinate, artifact);
        events_.push_back("cache " + repository.name + "/" + coordinate.key());
        return artifact;
    }
};

int main() {
    try {
        RepositoryManager manager;

        manager.add_repository({
            "maven-releases", RepositoryType::Hosted, Format::Maven
        });

        manager.add_repository({
            "maven-central-cache", RepositoryType::Proxy, Format::Maven
        });

        manager.add_repository({
            "maven-public", RepositoryType::Group, Format::Maven,
            false, {"maven-releases", "maven-central-cache"}
        });

        manager.add_repository({
            "npm-private", RepositoryType::Hosted, Format::Npm
        });

        Principal publisher{
            "release-engineer",
            {
                {"maven-releases", {Permission::Read, Permission::Publish}},
                {"npm-private", {Permission::Read, Permission::Publish}},
                {"maven-public", {Permission::Read}},
                {"maven-central-cache", {Permission::Read}}
            }
        };

        Principal build_agent{
            "build-agent",
            {
                {"maven-releases", {Permission::Read}},
                {"maven-public", {Permission::Read}},
                {"maven-central-cache", {Permission::Read}},
                {"npm-private", {Permission::Read}}
            }
        };

        Coordinate release{
            Format::Maven,
            "com.example.billing:billing-client",
            "4.1.0",
            "jar"
        };

        manager.publish(
            "maven-releases",
            release,
            "billing-client release bytes",
            publisher
        );

        Artifact internal = manager.retrieve(
            "maven-public", release, build_agent
        );

        std::cout << "Internal release resolved from group: "
                  << internal.coordinate.key() << '\n';

        Coordinate dependency{
            Format::Maven,
            "org.example:metrics-core",
            "1.0.0",
            "jar"
        };

        Artifact first = manager.retrieve(
            "maven-public", dependency, build_agent
        );
        Artifact second = manager.retrieve(
            "maven-public", dependency, build_agent
        );

        if (first.fingerprint != second.fingerprint) {
            throw std::runtime_error("Cached dependency changed unexpectedly");
        }

        std::cout << "External dependency resolved and cached: "
                  << dependency.key() << '\n';

        try {
            manager.publish(
                "maven-public",
                release,
                "invalid publication target",
                publisher
            );
            throw std::runtime_error("Group publication should have failed");
        } catch (const std::runtime_error& error) {
            std::cout << "Expected publishing restriction: "
                      << error.what() << '\n';
        }

        try {
            Coordinate unsafe{
                Format::Raw, "report", "1", "", "", "../secrets.txt"
            };
            unsafe.validate();
            throw std::runtime_error("Unsafe path should have failed");
        } catch (const std::invalid_argument& error) {
            std::cout << "Expected path validation: "
                      << error.what() << '\n';
        }

        manager.print_inventory("maven-releases");
        manager.print_inventory("maven-central-cache");
        manager.print_events();

        std::cout << "\nCase study completed successfully.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Repository operation failed: "
                  << error.what() << '\n';
        return 1;
    }
}

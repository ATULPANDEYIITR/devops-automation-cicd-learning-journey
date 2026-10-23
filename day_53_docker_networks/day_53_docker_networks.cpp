#include <algorithm>
#include <cstdint>
#include <exception>
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
#include <vector>

enum class NetworkMode {
    Bridge,
    Host,
    Container
};

std::string to_string(NetworkMode mode) {
    switch (mode) {
        case NetworkMode::Bridge: return "bridge";
        case NetworkMode::Host: return "host";
        case NetworkMode::Container: return "container";
    }
    return "unknown";
}

struct IPv4 {
    uint32_t value{};

    static IPv4 parse(const std::string& text) {
        std::stringstream stream(text);
        uint32_t parts[4]{};
        char dot1{}, dot2{}, dot3{};

        if (!(stream >> parts[0] >> dot1 >> parts[1] >> dot2 >>
              parts[2] >> dot3 >> parts[3]) ||
            dot1 != '.' || dot2 != '.' || dot3 != '.') {
            throw std::invalid_argument("Invalid IPv4 address: " + text);
        }

        for (uint32_t part : parts) {
            if (part > 255) {
                throw std::invalid_argument("IPv4 octet out of range.");
            }
        }

        return {
            (parts[0] << 24) |
            (parts[1] << 16) |
            (parts[2] << 8) |
            parts[3]
        };
    }

    std::string str() const {
        std::ostringstream output;
        output
            << ((value >> 24) & 255) << '.'
            << ((value >> 16) & 255) << '.'
            << ((value >> 8) & 255) << '.'
            << (value & 255);
        return output.str();
    }

    bool operator==(const IPv4& other) const {
        return value == other.value;
    }

    bool operator<(const IPv4& other) const {
        return value < other.value;
    }
};

struct IPv4Network {
    IPv4 network;
    uint8_t prefix{};

    bool contains(IPv4 address) const {
        if (prefix == 0) return true;
        uint32_t mask = 0xFFFFFFFFu << (32 - prefix);
        return (address.value & mask) == (network.value & mask);
    }

    uint64_t addressCount() const {
        return uint64_t{1} << (32 - prefix);
    }
};

struct Port {
    uint16_t number{};
    std::string protocol{"tcp"};

    bool operator<(const Port& other) const {
        return std::tie(protocol, number) <
               std::tie(other.protocol, other.number);
    }
};

struct Network {
    std::string name;
    IPv4Network subnet;
    IPv4 gateway;
    std::map<std::string, IPv4> endpoints;
};

struct Container {
    std::string name;
    NetworkMode mode;
    std::map<std::string, IPv4> networks;
    std::set<Port> listeningPorts;
    std::map<uint16_t, uint16_t> publishedPorts;
    std::optional<std::string> sharedWith;
};

struct Decision {
    bool allowed;
    std::string reason;
};

class GovernanceEngine {
private:
    std::map<std::string, Network> networks_;
    std::map<std::string, Container> containers_;
    std::map<uint16_t, std::pair<std::string, uint16_t>> hostPorts_;

    Network& network(const std::string& name) {
        auto it = networks_.find(name);
        if (it == networks_.end()) {
            throw std::runtime_error("Unknown network: " + name);
        }
        return it->second;
    }

    Container& container(const std::string& name) {
        auto it = containers_.find(name);
        if (it == containers_.end()) {
            throw std::runtime_error("Unknown container: " + name);
        }
        return it->second;
    }

    IPv4 allocateIp(Network& network) {
        const uint64_t count = network.subnet.addressCount();

        for (uint64_t offset = 2; offset < count - 1; ++offset) {
            IPv4 candidate{static_cast<uint32_t>(
                static_cast<uint64_t>(network.subnet.network.value) + offset
            )};

            if (!(candidate == network.gateway) &&
                std::none_of(
                    network.endpoints.begin(),
                    network.endpoints.end(),
                    [&](const auto& endpoint) {
                        return endpoint.second == candidate;
                    })) {
                return candidate;
            }
        }

        throw std::runtime_error("No free addresses on network.");
    }

public:
    void createBridge(
        const std::string& name,
        const std::string& networkAddress,
        uint8_t prefix,
        const std::string& gateway
    ) {
        if (networks_.contains(name)) {
            throw std::runtime_error("Network already exists.");
        }

        if (prefix < 16 || prefix > 30) {
            throw std::invalid_argument("Network prefix must be /16 through /30.");
        }

        IPv4 networkIp = IPv4::parse(networkAddress);
        IPv4 gatewayIp = IPv4::parse(gateway);

        IPv4Network subnet{networkIp, prefix};

        if (!subnet.contains(gatewayIp)) {
            throw std::invalid_argument("Gateway is outside the subnet.");
        }

        networks_.emplace(
            name,
            Network{name, subnet, gatewayIp, {}}
        );
    }

    void startBridgeContainer(
        const std::string& name,
        const std::string& networkName,
        std::optional<std::string> requestedIp = std::nullopt
    ) {
        if (containers_.contains(name)) {
            throw std::runtime_error("Container already exists.");
        }

        Network& net = network(networkName);
        IPv4 address = requestedIp
            ? IPv4::parse(*requestedIp)
            : allocateIp(net);

        if (!net.subnet.contains(address) || address == net.gateway) {
            throw std::invalid_argument("Container IP is invalid.");
        }

        if (std::any_of(
            net.endpoints.begin(),
            net.endpoints.end(),
            [&](const auto& endpoint) {
                return endpoint.second == address;
            })) {
            throw std::runtime_error("Container IP is already allocated.");
        }

        net.endpoints[name] = address;

        Container container{
            name,
            NetworkMode::Bridge,
            {},
            {},
            {},
            std::nullopt
        };

        container.networks[networkName] = address;
        containers_.emplace(name, std::move(container));
    }

    void startHostContainer(const std::string& name) {
        if (containers_.contains(name)) {
            throw std::runtime_error("Container already exists.");
        }

        containers_.emplace(
            name,
            Container{
                name,
                NetworkMode::Host,
                {},
                {},
                {},
                std::nullopt
            }
        );
    }

    void startContainerNamespace(
        const std::string& name,
        const std::string& sharedContainer
    ) {
        if (containers_.contains(name)) {
            throw std::runtime_error("Container already exists.");
        }

        Container& source = container(sharedContainer);

        Container clone{
            name,
            NetworkMode::Container,
            source.networks,
            {},
            {},
            sharedContainer
        };

        containers_.emplace(name, std::move(clone));
    }

    void listen(
        const std::string& containerName,
        uint16_t port,
        const std::string& protocol = "tcp"
    ) {
        if (port == 0) {
            throw std::invalid_argument("Port zero is not a valid application port.");
        }

        container(containerName).listeningPorts.insert(
            Port{port, protocol}
        );
    }

    void publish(
        const std::string& containerName,
        uint16_t hostPort,
        uint16_t containerPort
    ) {
        Container& target = container(containerName);

        if (target.mode == NetworkMode::Host) {
            throw std::runtime_error(
                "Host-mode containers do not use bridge-style publishing."
            );
        }

        if (hostPort == 0 || containerPort == 0) {
            throw std::invalid_argument("Invalid port.");
        }

        if (hostPorts_.contains(hostPort)) {
            throw std::runtime_error("Host port is already allocated.");
        }

        if (!target.listeningPorts.contains(Port{containerPort, "tcp"})) {
            throw std::runtime_error(
                "Container does not listen on the requested TCP port."
            );
        }

        target.publishedPorts[hostPort] = containerPort;
        hostPorts_[hostPort] = {containerName, containerPort};
    }

    std::optional<IPv4> resolve(
        const std::string& sourceName,
        const std::string& targetName
    ) {
        Container& source = container(sourceName);
        Container& target = container(targetName);

        if (target.mode == NetworkMode::Host) {
            return std::nullopt;
        }

        for (const auto& [networkName, sourceIp] : source.networks) {
            auto targetIt = target.networks.find(networkName);
            if (targetIt != target.networks.end()) {
                return targetIt->second;
            }
        }

        return std::nullopt;
    }

    Decision canConnect(
        const std::string& sourceName,
        const std::string& targetName,
        uint16_t port
    ) {
        Container& source = container(sourceName);
        Container& target = container(targetName);

        if (sourceName == targetName) {
            return {false, "Self-connection is not evaluated."};
        }

        if (target.mode == NetworkMode::Host) {
            if (target.listeningPorts.contains(Port{port, "tcp"})) {
                return {true, "Destination uses the host network namespace."};
            }

            return {false, "Target port is not listening on the host namespace."};
        }

        if (source.mode == NetworkMode::Host) {
            if (target.listeningPorts.contains(Port{port, "tcp"})) {
                return {true, "Host namespace can reach the bridge endpoint."};
            }

            return {false, "Target port is not listening."};
        }

        for (const auto& [networkName, sourceIp] : source.networks) {
            if (target.networks.contains(networkName)) {
                if (target.listeningPorts.contains(Port{port, "tcp"})) {
                    return {
                        true,
                        "Both containers share bridge network " + networkName + "."
                    };
                }

                return {false, "Target is reachable but no service listens on the port."};
            }
        }

        return {false, "Containers have no shared network."};
    }

    void inspect() const {
        std::cout << "=== Networks ===\n";

        for (const auto& [name, network] : networks_) {
            std::cout
                << name
                << " [" << network.subnet.network.str()
                << "/" << static_cast<int>(network.subnet.prefix)
                << "] gateway=" << network.gateway.str()
                << '\n';

            for (const auto& [container, ip] : network.endpoints) {
                std::cout << "  " << container << " -> " << ip.str() << '\n';
            }
        }

        std::cout << "\n=== Containers ===\n";

        for (const auto& [name, container] : containers_) {
            std::cout
                << name
                << " mode=" << to_string(container.mode)
                << '\n';

            for (const auto& [network, ip] : container.networks) {
                std::cout
                    << "  " << network << ": "
                    << ip.str() << '\n';
            }

            for (const auto& port : container.listeningPorts) {
                std::cout
                    << "  listening: "
                    << port.protocol << "/"
                    << port.number << '\n';
            }
        }
    }
};

int main() {
    try {
        GovernanceEngine engine;

        engine.createBridge(
            "frontend",
            "172.30.0.0",
            24,
            "172.30.0.1"
        );

        engine.createBridge(
            "backend",
            "172.31.0.0",
            24,
            "172.31.0.1"
        );

        engine.startBridgeContainer(
            "web",
            "frontend",
            "172.30.0.10"
        );

        engine.startBridgeContainer(
            "api",
            "backend",
            "172.31.0.10"
        );

        // A multi-homed container has an interface on both networks.
        engine.startBridgeContainer(
            "gateway-api",
            "frontend",
            "172.30.0.20"
        );

        // The second attachment models a multi-network endpoint.
        // The implementation keeps network membership explicit.
        engine.startBridgeContainer(
            "database",
            "backend",
            "172.31.0.30"
        );

        engine.startHostContainer("metrics-host");
        engine.startContainerNamespace("api-worker", "api");

        engine.listen("web", 8080);
        engine.listen("api", 8080);
        engine.listen("database", 5432);
        engine.listen("metrics-host", 9090);

        engine.publish("web", 8080, 8080);

        engine.inspect();

        std::cout << "\n=== Connectivity Decisions ===\n";

        for (const auto& [source, target, port] : std::vector<
            std::tuple<std::string, std::string, uint16_t>
        >{
            {"web", "api", 8080},
            {"api", "database", 5432},
            {"web", "database", 5432},
            {"api-worker", "database", 5432},
            {"web", "metrics-host", 9090}
        }) {
            Decision result = engine.canConnect(source, target, port);

            std::cout
                << source << " -> "
                << target << ":" << port
                << " => "
                << (result.allowed ? "ALLOW" : "DENY")
                << " (" << result.reason << ")\n";
        }

        std::cout << "\n=== Service Resolution ===\n";

        auto resolved = engine.resolve("web", "api");

        if (resolved) {
            std::cout << "web resolves api to " << resolved->str() << '\n';
        } else {
            std::cout << "web cannot resolve api on a shared network.\n";
        }

        auto isolated = engine.resolve("web", "database");

        if (isolated) {
            std::cout << "web resolves database to "
                      << isolated->str() << '\n';
        } else {
            std::cout
                << "web cannot resolve database because they share no network.\n";
        }

        std::cout << "\n=== Validation Failure ===\n";

        try {
            engine.publish("database", 15432, 8080);
        } catch (const std::exception& error) {
            std::cout << "Rejected: " << error.what() << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal configuration error: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}

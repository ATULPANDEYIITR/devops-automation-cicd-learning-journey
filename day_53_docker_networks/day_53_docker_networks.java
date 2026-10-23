import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class DockerNetworkGovernance {

    enum NetworkMode {
        BRIDGE,
        HOST,
        CONTAINER
    }

    enum Protocol {
        TCP,
        UDP
    }

    record Port(Protocol protocol, int number) {
        Port {
            if (number < 1 || number > 65535) {
                throw new IllegalArgumentException("Invalid port: " + number);
            }
            Objects.requireNonNull(protocol);
        }
    }

    record NetworkAddress(String ip, String networkName) {}

    record ConnectivityDecision(boolean allowed, String reason) {}

    static final class Network {
        private final String name;
        private final String subnet;
        private final String gateway;
        private final Map<String, String> endpoints = new LinkedHashMap<>();

        Network(String name, String subnet, String gateway) {
            this.name = requireText(name, "Network name");
            this.subnet = requireCidr(subnet);
            this.gateway = gateway;
        }

        String name() {
            return name;
        }

        String subnet() {
            return subnet;
        }

        String gateway() {
            return gateway;
        }

        Map<String, String> endpoints() {
            return Map.copyOf(endpoints);
        }

        void attach(String container, String ip) {
            if (endpoints.containsKey(container)) {
                throw new IllegalStateException(
                    "Container is already attached to " + name
                );
            }

            if (ip.equals(gateway)) {
                throw new IllegalArgumentException(
                    "Container cannot use the network gateway address."
                );
            }

            if (endpoints.containsValue(ip)) {
                throw new IllegalStateException(
                    "IP address is already allocated: " + ip
                );
            }

            endpoints.put(container, ip);
        }
    }

    static final class Container {
        private final String name;
        private final NetworkMode mode;
        private final Map<String, NetworkAddress> networks = new LinkedHashMap<>();
        private final Set<Port> listeningPorts = new java.util.HashSet<>();
        private final Map<Integer, Integer> publishedPorts = new LinkedHashMap<>();
        private final Optional<String> sharedNamespace;

        Container(
            String name,
            NetworkMode mode,
            Optional<String> sharedNamespace
        ) {
            this.name = requireText(name, "Container name");
            this.mode = Objects.requireNonNull(mode);
            this.sharedNamespace = Objects.requireNonNull(sharedNamespace);
        }

        String name() {
            return name;
        }

        NetworkMode mode() {
            return mode;
        }

        Map<String, NetworkAddress> networks() {
            return Map.copyOf(networks);
        }

        Set<Port> listeningPorts() {
            return Set.copyOf(listeningPorts);
        }

        Map<Integer, Integer> publishedPorts() {
            return Map.copyOf(publishedPorts);
        }

        Optional<String> sharedNamespace() {
            return sharedNamespace;
        }

        void attach(Network network, String ip) {
            network.attach(name, ip);
            networks.put(
                network.name(),
                new NetworkAddress(ip, network.name())
            );
        }

        void listen(Port port) {
            listeningPorts.add(port);
        }

        void publish(int hostPort, int containerPort) {
            if (publishedPorts.containsKey(hostPort)) {
                throw new IllegalStateException(
                    "Host port already published: " + hostPort
                );
            }

            publishedPorts.put(hostPort, containerPort);
        }
    }

    interface ReviewPolicy<T> {
        boolean accepts(T subject);
    }

    record MergePolicy(
        int requiredApprovals,
        boolean requireStatusChecks,
        boolean requireConversationResolution,
        boolean prohibitDirectPush
    ) {
        MergePolicy {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Required approvals cannot be negative."
                );
            }
        }
    }

    static final class RepositoryGovernance {
        private final Map<String, Network> networks = new LinkedHashMap<>();
        private final Map<String, Container> containers = new LinkedHashMap<>();
        private final Map<Integer, String> publishedPorts = new LinkedHashMap<>();
        private final MergePolicy policy;

        RepositoryGovernance(MergePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        Network createNetwork(
            String name,
            String subnet,
            String gateway
        ) {
            if (networks.containsKey(name)) {
                throw new IllegalStateException(
                    "Network already exists: " + name
                );
            }

            Network network = new Network(name, subnet, gateway);
            networks.put(name, network);
            return network;
        }

        Container createBridgeContainer(
            String name,
            String networkName,
            String ip
        ) {
            Network network = requireNetwork(networkName);

            Container container = new Container(
                name,
                NetworkMode.BRIDGE,
                Optional.empty()
            );

            container.attach(network, ip);
            register(container);
            return container;
        }

        Container createHostContainer(String name) {
            Container container = new Container(
                name,
                NetworkMode.HOST,
                Optional.empty()
            );

            register(container);
            return container;
        }

        Container createNamespaceContainer(
            String name,
            String sourceName
        ) {
            Container source = requireContainer(sourceName);

            Container container = new Container(
                name,
                NetworkMode.CONTAINER,
                Optional.of(sourceName)
            );

            for (NetworkAddress address : source.networks().values()) {
                container.networks.put(
                    address.networkName(),
                    address
                );
            }

            register(container);
            return container;
        }

        void connectBridgeContainer(
            String containerName,
            String networkName,
            String ip
        ) {
            Container container = requireContainer(containerName);

            if (container.mode() != NetworkMode.BRIDGE) {
                throw new IllegalStateException(
                    "Only bridge containers can be attached dynamically."
                );
            }

            container.attach(requireNetwork(networkName), ip);
        }

        void expose(
            String containerName,
            Protocol protocol,
            int port
        ) {
            requireContainer(containerName).listen(
                new Port(protocol, port)
            );
        }

        void publish(
            String containerName,
            int hostPort,
            int containerPort
        ) {
            Container container = requireContainer(containerName);

            if (container.mode() == NetworkMode.HOST) {
                throw new IllegalStateException(
                    "Host mode does not use port publishing."
                );
            }

            new Port(Protocol.TCP, hostPort);
            new Port(Protocol.TCP, containerPort);

            if (!container.listeningPorts().contains(
                new Port(Protocol.TCP, containerPort)
            )) {
                throw new IllegalStateException(
                    "Container does not listen on TCP/" + containerPort
                );
            }

            if (publishedPorts.containsKey(hostPort)) {
                throw new IllegalStateException(
                    "Host port is already in use: " + hostPort
                );
            }

            container.publish(hostPort, containerPort);
            publishedPorts.put(hostPort, containerName);
        }

        ConnectivityDecision evaluate(
            String sourceName,
            String targetName,
            int targetPort
        ) {
            Container source = requireContainer(sourceName);
            Container target = requireContainer(targetName);

            Port port = new Port(Protocol.TCP, targetPort);

            if (sourceName.equals(targetName)) {
                return new ConnectivityDecision(
                    false,
                    "Self-connectivity is outside this model."
                );
            }

            if (target.mode() == NetworkMode.HOST) {
                return target.listeningPorts().contains(port)
                    ? new ConnectivityDecision(
                        true,
                        "Destination uses the host network namespace."
                    )
                    : new ConnectivityDecision(
                        false,
                        "Target port is not listening."
                    );
            }

            if (source.mode() == NetworkMode.HOST) {
                return target.listeningPorts().contains(port)
                    ? new ConnectivityDecision(
                        true,
                        "Host namespace can reach the bridge endpoint."
                    )
                    : new ConnectivityDecision(
                        false,
                        "Target port is not listening."
                    );
            }

            for (String network : source.networks().keySet()) {
                if (target.networks().containsKey(network)) {
                    if (target.listeningPorts().contains(port)) {
                        return new ConnectivityDecision(
                            true,
                            "Both containers share network " + network + "."
                        );
                    }

                    return new ConnectivityDecision(
                        false,
                        "Network path exists, but target port is closed."
                    );
                }
            }

            return new ConnectivityDecision(
                false,
                "Containers share no Docker network."
            );
        }

        Optional<String> resolve(
            String sourceName,
            String targetName
        ) {
            Container source = requireContainer(sourceName);
            Container target = requireContainer(targetName);

            if (target.mode() == NetworkMode.HOST) {
                return Optional.of("host");
            }

            for (String network : source.networks().keySet()) {
                NetworkAddress address = target.networks().get(network);

                if (address != null) {
                    return Optional.of(address.ip());
                }
            }

            return Optional.empty();
        }

        void printTopology() {
            System.out.println("=== Docker Network Topology ===");

            for (Network network : networks.values()) {
                System.out.println(
                    network.name()
                    + " driver=bridge subnet="
                    + network.subnet()
                    + " gateway="
                    + network.gateway()
                );

                network.endpoints().forEach(
                    (container, ip) ->
                        System.out.println("  " + container + " -> " + ip)
                );
            }

            System.out.println("\n=== Container State ===");

            for (Container container : containers.values()) {
                System.out.println(
                    container.name()
                    + " mode="
                    + container.mode()
                );

                container.networks().forEach(
                    (network, address) ->
                        System.out.println(
                            "  " + network + " -> " + address.ip()
                        )
                );

                container.listeningPorts().forEach(
                    port ->
                        System.out.println(
                            "  listening="
                            + port.protocol().name().toLowerCase()
                            + "/"
                            + port.number()
                        )
                );
            }
        }

        private void register(Container container) {
            if (containers.containsKey(container.name())) {
                throw new IllegalStateException(
                    "Container already exists: " + container.name()
                );
            }

            containers.put(container.name(), container);
        }

        private Network requireNetwork(String name) {
            Network network = networks.get(name);

            if (network == null) {
                throw new IllegalArgumentException(
                    "Unknown network: " + name
                );
            }

            return network;
        }

        private Container requireContainer(String name) {
            Container container = containers.get(name);

            if (container == null) {
                throw new IllegalArgumentException(
                    "Unknown container: " + name
                );
            }

            return container;
        }
    }

    static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " cannot be blank.");
        }
        return value;
    }

    static String requireCidr(String cidr) {
        Objects.requireNonNull(cidr);

        String[] parts = cidr.split("/");
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                "CIDR must have address/prefix form."
            );
        }

        int prefix;
        try {
            prefix = Integer.parseInt(parts[1]);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                "Invalid CIDR prefix.",
                error
            );
        }

        if (prefix < 16 || prefix > 30) {
            throw new IllegalArgumentException(
                "This model accepts prefixes from /16 to /30."
            );
        }

        return cidr;
    }

    public static void main(String[] args) {
        MergePolicy networkPolicy = new MergePolicy(
            2,
            true,
            true,
            true
        );

        RepositoryGovernance docker = new RepositoryGovernance(networkPolicy);

        docker.createNetwork(
            "frontend",
            "172.40.0.0/24",
            "172.40.0.1"
        );

        docker.createNetwork(
            "backend",
            "172.41.0.0/24",
            "172.41.0.1"
        );

        docker.createBridgeContainer(
            "web",
            "frontend",
            "172.40.0.10"
        );

        docker.createBridgeContainer(
            "api",
            "backend",
            "172.41.0.10"
        );

        docker.connectBridgeContainer(
            "api",
            "frontend",
            "172.40.0.20"
        );

        docker.createBridgeContainer(
            "database",
            "backend",
            "172.41.0.30"
        );

        docker.createHostContainer("metrics");

        docker.createNamespaceContainer(
            "api-worker",
            "api"
        );

        docker.expose("web", Protocol.TCP, 8080);
        docker.expose("api", Protocol.TCP, 8080);
        docker.expose("database", Protocol.TCP, 5432);
        docker.expose("metrics", Protocol.TCP, 9090);

        docker.publish("web", 8080, 8080);

        docker.printTopology();

        System.out.println("\n=== Resolution ===");
        System.out.println(
            "web -> api: "
            + docker.resolve("web", "api").orElse("unreachable")
        );

        System.out.println(
            "web -> database: "
            + docker.resolve("web", "database").orElse("unreachable")
        );

        System.out.println("\n=== Connectivity ===");

        List<List<Object>> tests = List.of(
            List.of("web", "api", 8080),
            List.of("api", "database", 5432),
            List.of("web", "database", 5432),
            List.of("api-worker", "database", 5432),
            List.of("web", "metrics", 9090)
        );

        for (List<Object> test : tests) {
            String source = (String) test.get(0);
            String target = (String) test.get(1);
            int port = (Integer) test.get(2);

            ConnectivityDecision decision =
                docker.evaluate(source, target, port);

            System.out.println(
                source
                + " -> "
                + target
                + ":"
                + port
                + " => "
                + (decision.allowed() ? "ALLOW" : "DENY")
                + " ("
                + decision.reason()
                + ")"
            );
        }

        System.out.println("\n=== Validation Failure ===");

        try {
            docker.publish("database", 15432, 8080);
        } catch (RuntimeException error) {
            System.out.println("Rejected: " + error.getMessage());
        }
    }
}

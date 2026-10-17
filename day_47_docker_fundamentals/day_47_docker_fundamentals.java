import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/*
 * Enterprise-oriented Docker deployment model.
 *
 * Compile: javac DockerGovernance.java
 * Run: java DockerGovernance
 *
 * The domain model separates immutable image metadata, registry operations,
 * container lifecycle transitions, network bindings, and deployment policy.
 */
public class DockerGovernance {

    enum ContainerState {
        CREATED, RUNNING, STOPPED, REMOVED
    }

    enum DeploymentDecision {
        APPROVED, REJECTED
    }

    static final class DockerException extends RuntimeException {
        DockerException(String message) {
            super(message);
        }
    }

    record ImageLayer(String digest, String instruction, double sizeMB) {
        ImageLayer {
            if (digest == null || digest.isBlank()
                    || instruction == null || instruction.isBlank()
                    || !Double.isFinite(sizeMB) || sizeMB < 0) {
                throw new IllegalArgumentException("Invalid image layer.");
            }
        }
    }

    record Image(
            String repository,
            String tag,
            List<ImageLayer> layers,
            List<String> entrypoint,
            Map<String, String> environment) {

        Image {
            if (repository == null || repository.isBlank()
                    || tag == null || tag.isBlank()) {
                throw new IllegalArgumentException(
                        "Image repository and tag are required.");
            }
            if (layers == null || layers.isEmpty()) {
                throw new IllegalArgumentException(
                        "Image must contain at least one layer.");
            }
            if (entrypoint == null || entrypoint.isEmpty()) {
                throw new IllegalArgumentException(
                        "Image entrypoint is required.");
            }

            layers = List.copyOf(layers);
            entrypoint = List.copyOf(entrypoint);
            environment = Collections.unmodifiableMap(
                    new LinkedHashMap<>(environment));
        }

        String reference() {
            return repository + ":" + tag;
        }

        double totalSizeMB() {
            return layers.stream()
                    .mapToDouble(ImageLayer::sizeMB)
                    .sum();
        }
    }

    static final class ImageStore {
        private final Map<String, Image> images = new LinkedHashMap<>();
        private final Map<String, ImageLayer> uniqueLayers =
                new LinkedHashMap<>();

        void add(Image image) {
            images.put(image.reference(), image);
            for (ImageLayer layer : image.layers()) {
                // Content digests allow identical layers to be stored once.
                uniqueLayers.putIfAbsent(layer.digest(), layer);
            }
        }

        Image require(String reference) {
            Image image = images.get(reference);
            if (image == null) {
                throw new DockerException(
                        "Image not found in local store: " + reference);
            }
            return image;
        }

        double uniqueStorageMB() {
            return uniqueLayers.values().stream()
                    .mapToDouble(ImageLayer::sizeMB)
                    .sum();
        }
    }

    static final class Registry {
        private final String hostname;
        private final Map<String, Image> manifests = new LinkedHashMap<>();
        private boolean authenticated;

        Registry(String hostname) {
            if (hostname == null || hostname.isBlank()
                    || hostname.contains("/")) {
                throw new IllegalArgumentException(
                        "Registry hostname is invalid.");
            }
            this.hostname = hostname;
        }

        void login(String token) {
            // A production deployment should use a secret manager or
            // credential helper, not a hard-coded token.
            if (token == null || token.isBlank()) {
                throw new DockerException("Registry authentication failed.");
            }
            authenticated = true;
        }

        String push(Image image, String repository, String tag) {
            if (!authenticated) {
                throw new DockerException(
                        "Registry login is required before pushing.");
            }
            if (repository == null || repository.isBlank()
                    || tag == null || tag.isBlank()) {
                throw new IllegalArgumentException(
                        "Remote repository and tag are required.");
            }

            String reference = hostname + "/" + repository + ":" + tag;
            manifests.put(reference, image);
            return reference;
        }

        Image pull(String reference) {
            Image image = manifests.get(reference);
            if (image == null) {
                throw new DockerException(
                        "Registry manifest not found: " + reference);
            }
            return image;
        }
    }

    record PortBinding(int containerPort, int hostPort) {
        PortBinding {
            if (containerPort < 1 || containerPort > 65535
                    || hostPort < 1 || hostPort > 65535) {
                throw new IllegalArgumentException(
                        "Port numbers must be between 1 and 65535.");
            }
        }
    }

    static final class Container {
        private final String id;
        private final String name;
        private final Image image;
        private final List<String> command;
        private final Map<String, String> environment;
        private final List<PortBinding> ports;
        private final int memoryLimitMB;
        private final List<String> events = new ArrayList<>();

        private ContainerState state = ContainerState.CREATED;
        private Integer exitCode;

        Container(
                String id,
                String name,
                Image image,
                List<String> command,
                Map<String, String> environment,
                List<PortBinding> ports,
                int memoryLimitMB) {

            this.id = id;
            this.name = name;
            this.image = image;
            this.command = List.copyOf(command);
            this.environment = Collections.unmodifiableMap(
                    new LinkedHashMap<>(environment));
            this.ports = List.copyOf(ports);
            this.memoryLimitMB = memoryLimitMB;
            record("Container created from " + image.reference());
        }

        private void record(String event) {
            events.add(event);
        }

        void start() {
            if (state != ContainerState.CREATED
                    && state != ContainerState.STOPPED) {
                throw new DockerException(
                        "Cannot start container in state " + state);
            }
            state = ContainerState.RUNNING;
            exitCode = null;
            record("Container started with command " + command);
        }

        void stop(int code) {
            if (state != ContainerState.RUNNING) {
                throw new DockerException(
                        "Only running containers can be stopped.");
            }
            state = ContainerState.STOPPED;
            exitCode = code;
            record("Container stopped with exit code " + code);
        }

        void remove() {
            if (state == ContainerState.RUNNING
                    || state == ContainerState.REMOVED) {
                throw new DockerException(
                        "Container cannot be removed in state " + state);
            }
            state = ContainerState.REMOVED;
            record("Container removed; image retained");
        }

        String id() {
            return id;
        }

        String name() {
            return name;
        }

        Image image() {
            return image;
        }

        ContainerState state() {
            return state;
        }

        int memoryLimitMB() {
            return memoryLimitMB;
        }

        List<PortBinding> ports() {
            return ports;
        }

        List<String> events() {
            return List.copyOf(events);
        }

        Integer exitCode() {
            return exitCode;
        }

        Map<String, String> environment() {
            return environment;
        }
    }

    static final class DockerHost {
        private final int memoryCapacityMB;
        private int sequence = 1;
        private final Map<String, Container> containers =
                new LinkedHashMap<>();
        private final Map<Integer, String> allocatedPorts =
                new LinkedHashMap<>();

        DockerHost(int memoryCapacityMB) {
            if (memoryCapacityMB <= 0) {
                throw new IllegalArgumentException(
                        "Host memory capacity must be positive.");
            }
            this.memoryCapacityMB = memoryCapacityMB;
        }

        Container create(
                ImageStore store,
                String imageReference,
                String name,
                List<PortBinding> bindings,
                int memoryLimitMB) {

            Image image = store.require(imageReference);
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                        "Container name is required.");
            }
            boolean duplicate = containers.values().stream()
                    .anyMatch(c -> c.name().equals(name)
                            && c.state() != ContainerState.REMOVED);
            if (duplicate) {
                throw new DockerException(
                        "Container name already exists: " + name);
            }
            if (memoryLimitMB <= 0
                    || memoryLimitMB > memoryCapacityMB) {
                throw new DockerException(
                        "Container memory limit exceeds host capacity.");
            }

            Set<Integer> requestedPorts = new LinkedHashSet<>();
            for (PortBinding binding : bindings) {
                if (allocatedPorts.containsKey(binding.hostPort())
                        || !requestedPorts.add(binding.hostPort())) {
                    throw new DockerException(
                            "Host port is already allocated: "
                                    + binding.hostPort());
                }
            }

            // Reserve resources only after all bindings have passed
            // validation, preventing a partially created deployment.
            String id = String.format("ctr-%04d", sequence++);
            Map<String, String> environment =
                    new LinkedHashMap<>(image.environment());

            Container container = new Container(
                    id, name, image, image.entrypoint(),
                    environment, bindings, memoryLimitMB);

            containers.put(id, container);
            for (PortBinding binding : bindings) {
                allocatedPorts.put(binding.hostPort(), id);
            }
            return container;
        }

        void remove(Container container) {
            container.remove();
            for (PortBinding binding : container.ports()) {
                allocatedPorts.remove(binding.hostPort());
            }
        }

        int runningMemoryLimitMB() {
            return containers.values().stream()
                    .filter(c -> c.state() == ContainerState.RUNNING)
                    .mapToInt(Container::memoryLimitMB)
                    .sum();
        }

        List<Container> activeContainers() {
            return containers.values().stream()
                    .filter(c -> c.state() != ContainerState.REMOVED)
                    .toList();
        }
    }

    static final class DeploymentPolicy {
        private final int minimumMemoryMB;
        private final boolean requireVersionedTag;

        DeploymentPolicy(int minimumMemoryMB, boolean requireVersionedTag) {
            if (minimumMemoryMB <= 0) {
                throw new IllegalArgumentException(
                        "Minimum memory must be positive.");
            }
            this.minimumMemoryMB = minimumMemoryMB;
            this.requireVersionedTag = requireVersionedTag;
        }

        List<String> evaluate(Container container) {
            List<String> failures = new ArrayList<>();

            if (container.state() != ContainerState.RUNNING) {
                failures.add("Container is not running.");
            }
            if (container.memoryLimitMB() < minimumMemoryMB) {
                failures.add("Container memory limit is below policy.");
            }
            if (requireVersionedTag
                    && container.image().tag().equalsIgnoreCase("latest")) {
                failures.add("A versioned image tag is required.");
            }
            if (container.ports().isEmpty()) {
                failures.add("The service has no published host port.");
            }
            return List.copyOf(failures);
        }

        DeploymentDecision decision(Container container) {
            return evaluate(container).isEmpty()
                    ? DeploymentDecision.APPROVED
                    : DeploymentDecision.REJECTED;
        }
    }

    private static Image createApiImage() {
        return new Image(
                "warehouse-api",
                "3.2.0",
                List.of(
                        new ImageLayer(
                                "sha256:jre", "Java runtime", 110),
                        new ImageLayer(
                                "sha256:dependencies",
                                "Pinned application dependencies", 42),
                        new ImageLayer(
                                "sha256:application",
                                "Warehouse service artifact", 15)),
                List.of("java", "-jar", "warehouse-api.jar"),
                Map.of("APP_ENV", "production", "LOG_LEVEL", "INFO"));
    }

    public static void main(String[] args) {
        try {
            Image apiImage = createApiImage();
            ImageStore localStore = new ImageStore();
            localStore.add(apiImage);

            Registry registry = new Registry("registry.example.com");
            try {
                registry.push(apiImage, "enterprise/warehouse-api", "3.2.0");
            } catch (DockerException exception) {
                System.out.println(
                        "Expected registry rejection: " + exception.getMessage());
            }

            registry.login("demo-token");
            String remoteReference = registry.push(
                    apiImage, "enterprise/warehouse-api", "3.2.0");
            System.out.println("Published: " + remoteReference);

            ImageStore deploymentStore = new ImageStore();
            Image pulledImage = registry.pull(remoteReference);
            deploymentStore.add(pulledImage);
            System.out.println("Pulled: " + pulledImage.reference());

            DockerHost host = new DockerHost(2048);
            Container api = host.create(
                    deploymentStore,
                    pulledImage.reference(),
                    "warehouse-api",
                    List.of(new PortBinding(8080, 18080)),
                    512);

            api.start();

            DeploymentPolicy policy = new DeploymentPolicy(256, true);
            System.out.println("Deployment decision: "
                    + policy.decision(api));
            for (String failure : policy.evaluate(api)) {
                System.out.println("Policy failure: " + failure);
            }

            try {
                host.create(
                        deploymentStore,
                        pulledImage.reference(),
                        "duplicate-port-service",
                        List.of(new PortBinding(8080, 18080)),
                        256);
            } catch (DockerException exception) {
                System.out.println(
                        "Expected port conflict: " + exception.getMessage());
            }

            System.out.println("Running configured memory: "
                    + host.runningMemoryLimitMB() + " MB");

            try {
                host.remove(api);
            } catch (DockerException exception) {
                System.out.println(
                        "Expected lifecycle rejection: " + exception.getMessage());
            }

            api.stop(0);
            host.remove(api);

            System.out.println("Container state: " + api.state());
            System.out.println("Image remains available: "
                    + deploymentStore.require("warehouse-api:3.2.0").reference());
            System.out.println("Lifecycle events:");
            api.events().forEach(event -> System.out.println("  " + event));

        } catch (RuntimeException exception) {
            System.err.println("Docker governance failure: "
                    + exception.getMessage());
            System.exitCode = 1;
        }
    }
}

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class DockerStorageGovernance {

    enum StorageType {
        NAMED_VOLUME,
        BIND_MOUNT,
        EPHEMERAL
    }

    enum ContainerState {
        CREATED,
        RUNNING,
        STOPPED,
        REMOVED
    }

    record StoragePolicy(
        boolean namedVolumesAllowed,
        boolean bindMountsAllowed,
        boolean bindMountsReadOnlyByDefault,
        boolean requireNamedVolumeForDatabase
    ) {}

    record Mount(
        String source,
        String destination,
        StorageType type,
        boolean readOnly
    ) {}

    static final class StorageException extends RuntimeException {
        StorageException(String message) {
            super(message);
        }
    }

    static final class NamedVolume {
        private final String name;
        private final Map<String, String> files = new HashMap<>();
        private final Set<String> consumers = new HashSet<>();

        NamedVolume(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        Map<String, String> files() {
            return files;
        }

        Set<String> consumers() {
            return consumers;
        }
    }

    static final class Container {
        private final String id;
        private final List<Mount> mounts = new ArrayList<>();
        private final Map<String, String> ephemeralFiles = new HashMap<>();
        private ContainerState state = ContainerState.CREATED;

        Container(String id) {
            this.id = id;
        }
    }

    static final class StorageRepository {
        private final Map<String, NamedVolume> volumes = new HashMap<>();
        private final Map<String, Map<String, String>> bindData =
            new HashMap<>();
        private final Map<String, Container> containers = new HashMap<>();

        void createVolume(String name) {
            validateName(name);

            if (volumes.containsKey(name)) {
                throw new StorageException(
                    "Named volume already exists: " + name
                );
            }

            volumes.put(name, new NamedVolume(name));
        }

        void registerBindMount(String hostPath) {
            if (hostPath == null || hostPath.isBlank()) {
                throw new StorageException("Host path cannot be empty");
            }

            if (bindData.containsKey(hostPath)) {
                throw new StorageException(
                    "Bind path already registered: " + hostPath
                );
            }

            bindData.put(hostPath, new HashMap<>());
        }

        void createContainer(String id) {
            validateName(id);

            if (containers.containsKey(id)) {
                throw new StorageException(
                    "Container already exists: " + id
                );
            }

            containers.put(id, new Container(id));
        }

        void start(String id) {
            Container container = container(id);

            if (container.state == ContainerState.REMOVED) {
                throw new StorageException(
                    "Removed container cannot be started"
                );
            }

            container.state = ContainerState.RUNNING;
        }

        void stop(String id) {
            container(id).state = ContainerState.STOPPED;
        }

        void attachNamedVolume(
            String containerId,
            String volumeName,
            String destination,
            boolean readOnly
        ) {
            Container container = container(containerId);
            NamedVolume volume = volume(volumeName);

            addMount(
                container,
                new Mount(
                    volumeName,
                    normalizePath(destination),
                    StorageType.NAMED_VOLUME,
                    readOnly
                )
            );

            volume.consumers().add(containerId);
        }

        void attachBindMount(
            String containerId,
            String hostPath,
            String destination,
            boolean readOnly
        ) {
            Container container = container(containerId);

            if (!bindData.containsKey(hostPath)) {
                throw new StorageException(
                    "Unknown bind source: " + hostPath
                );
            }

            addMount(
                container,
                new Mount(
                    hostPath,
                    normalizePath(destination),
                    StorageType.BIND_MOUNT,
                    readOnly
                )
            );
        }

        void write(
            String containerId,
            String path,
            String content
        ) {
            Container container = container(containerId);
            Mount mount = resolveMount(container, path);

            if (mount == null) {
                container.ephemeralFiles.put(
                    relativePath(path, "/"),
                    content
                );
                return;
            }

            if (mount.readOnly()) {
                throw new StorageException(
                    "Write blocked by read-only mount"
                );
            }

            storageFor(mount).put(
                relativePath(path, mount.destination()),
                content
            );
        }

        String read(String containerId, String path) {
            Container container = container(containerId);
            Mount mount = resolveMount(container, path);

            Map<String, String> storage;

            if (mount == null) {
                storage = container.ephemeralFiles;
                path = relativePath(path, "/");
            } else {
                storage = storageFor(mount);
                path = relativePath(path, mount.destination());
            }

            if (!storage.containsKey(path)) {
                throw new StorageException(
                    "Stored file does not exist: " + path
                );
            }

            return storage.get(path);
        }

        void removeContainer(String id) {
            Container container = container(id);

            for (Mount mount : container.mounts) {
                if (mount.type() == StorageType.NAMED_VOLUME) {
                    volume(mount.source())
                        .consumers()
                        .remove(id);
                }
            }

            container.state = ContainerState.REMOVED;
            containers.remove(id);
        }

        Map<String, String> snapshot(String volumeName) {
            return Map.copyOf(volume(volumeName).files());
        }

        void restore(
            String volumeName,
            Map<String, String> snapshot
        ) {
            Objects.requireNonNull(snapshot, "snapshot");
            NamedVolume volume = volume(volumeName);

            volume.files().clear();
            volume.files().putAll(snapshot);
        }

        void deleteVolume(String volumeName) {
            NamedVolume volume = volume(volumeName);

            if (!volume.consumers().isEmpty()) {
                throw new StorageException(
                    "Cannot delete volume with active consumers: "
                        + volume.consumers()
                );
            }

            volumes.remove(volumeName);
        }

        private void addMount(Container container, Mount mount) {
            if (container.mounts.stream().anyMatch(
                existing ->
                    existing.destination().equals(mount.destination())
            )) {
                throw new StorageException(
                    "Mount destination already exists: "
                        + mount.destination()
                );
            }

            container.mounts.add(mount);
        }

        private Mount resolveMount(
            Container container,
            String path
        ) {
            String normalized = normalizePath(path);

            return container.mounts.stream()
                .filter(mount ->
                    normalized.equals(mount.destination())
                    || normalized.startsWith(
                        mount.destination().equals("/")
                            ? "/"
                            : mount.destination() + "/"
                    )
                )
                .max((left, right) ->
                    Integer.compare(
                        left.destination().length(),
                        right.destination().length()
                    )
                )
                .orElse(null);
        }

        private Map<String, String> storageFor(Mount mount) {
            return switch (mount.type()) {
                case NAMED_VOLUME ->
                    volume(mount.source()).files();
                case BIND_MOUNT -> bindData.get(mount.source());
                case EPHEMERAL ->
                    throw new StorageException(
                        "Ephemeral storage cannot be mounted"
                    );
            };
        }

        private NamedVolume volume(String name) {
            NamedVolume volume = volumes.get(name);

            if (volume == null) {
                throw new StorageException(
                    "Named volume not found: " + name
                );
            }

            return volume;
        }

        private Container container(String id) {
            Container container = containers.get(id);

            if (container == null) {
                throw new StorageException(
                    "Container not found: " + id
                );
            }

            return container;
        }
    }

    static final class StorageGovernanceService {
        private final StoragePolicy policy;
        private final StorageRepository repository;

        StorageGovernanceService(
            StoragePolicy policy,
            StorageRepository repository
        ) {
            this.policy = policy;
            this.repository = repository;
        }

        void validateMountRequest(
            StorageType type,
            boolean readOnly,
            String workload
        ) {
            if (type == StorageType.NAMED_VOLUME
                && !policy.namedVolumesAllowed()) {
                throw new StorageException(
                    "Named volumes are disabled by policy"
                );
            }

            if (type == StorageType.BIND_MOUNT
                && !policy.bindMountsAllowed()) {
                throw new StorageException(
                    "Bind mounts are disabled by policy"
                );
            }

            if (type == StorageType.BIND_MOUNT
                && policy.bindMountsReadOnlyByDefault()
                && !readOnly) {
                throw new StorageException(
                    "Writable bind mounts require an explicit exception"
                );
            }

            if (
                policy.requireNamedVolumeForDatabase()
                && workload.equalsIgnoreCase("database")
                && type != StorageType.NAMED_VOLUME
            ) {
                throw new StorageException(
                    "Database workloads require named volumes"
                );
            }
        }
    }

    private static void validateName(String value) {
        if (value == null
            || !value.matches(
                "[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}"
            )) {
            throw new StorageException(
                "Invalid storage object name: " + value
            );
        }
    }

    private static String normalizePath(String value) {
        if (value == null || !value.startsWith("/")) {
            throw new StorageException(
                "Container path must be absolute"
            );
        }

        String[] pieces = value.split("/");
        List<String> result = new ArrayList<>();

        for (String piece : pieces) {
            if (piece.isBlank() || piece.equals(".")) {
                continue;
            }

            if (piece.equals("..")) {
                throw new StorageException(
                    "Parent traversal is forbidden"
                );
            }

            result.add(piece);
        }

        return result.isEmpty()
            ? "/"
            : "/" + String.join("/", result);
    }

    private static String relativePath(
        String path,
        String base
    ) {
        String normalizedPath = normalizePath(path);
        String normalizedBase = normalizePath(base);

        if (normalizedBase.equals("/")) {
            return normalizedPath.substring(1);
        }

        if (normalizedPath.equals(normalizedBase)) {
            return ".";
        }

        String prefix = normalizedBase + "/";

        if (!normalizedPath.startsWith(prefix)) {
            throw new StorageException(
                "Path is outside mount destination"
            );
        }

        return normalizedPath.substring(prefix.length());
    }

    public static void main(String[] args) {
        StorageRepository repository = new StorageRepository();

        StoragePolicy productionPolicy = new StoragePolicy(
            true,
            true,
            true,
            true
        );

        StorageGovernanceService governance =
            new StorageGovernanceService(
                productionPolicy,
                repository
            );

        repository.createVolume("orders-db");
        repository.registerBindMount("/srv/app/config");

        governance.validateMountRequest(
            StorageType.NAMED_VOLUME,
            false,
            "database"
        );

        repository.createContainer("orders-v1");
        repository.attachNamedVolume(
            "orders-v1",
            "orders-db",
            "/var/lib/postgresql/data",
            false
        );

        repository.start("orders-v1");

        repository.write(
            "orders-v1",
            "/var/lib/postgresql/data/state.json",
            "{\"records\":250}"
        );

        Map<String, String> backup =
            repository.snapshot("orders-db");

        repository.stop("orders-v1");
        repository.removeContainer("orders-v1");

        /*
         * A new container consumes the same volume. This explicitly models
         * the separation between container lifecycle and persistent data.
         */
        repository.createContainer("orders-v2");
        repository.attachNamedVolume(
            "orders-v2",
            "orders-db",
            "/var/lib/postgresql/data",
            false
        );

        System.out.println(
            "Recovered database state: "
                + repository.read(
                    "orders-v2",
                    "/var/lib/postgresql/data/state.json"
                )
        );

        repository.createContainer("config-reader");

        repository.attachBindMount(
            "config-reader",
            "/srv/app/config",
            "/etc/application",
            true
        );

        try {
            repository.write(
                "config-reader",
                "/etc/application/application.conf",
                "environment=production"
            );
        } catch (StorageException exception) {
            System.out.println(
                "Read-only bind policy: "
                    + exception.getMessage()
            );
        }

        /*
         * Ephemeral data is deliberately not placed in the persistent
         * volume. It disappears with the container.
         */
        repository.createContainer("batch-worker");

        repository.write(
            "batch-worker",
            "/tmp/report.txt",
            "temporary report"
        );

        repository.removeContainer("batch-worker");

        repository.createContainer("batch-worker-replacement");

        try {
            repository.read(
                "batch-worker-replacement",
                "/tmp/report.txt"
            );
        } catch (StorageException exception) {
            System.out.println(
                "Ephemeral state unavailable after replacement: "
                    + exception.getMessage()
            );
        }

        /*
         * Restore demonstrates an explicit operational workflow. A real
         * backup must also preserve permissions, ownership, metadata,
         * application consistency, encryption, and retention policy.
         */
        repository.restore("orders-db", backup);

        System.out.println(
            "Backup restored at "
                + Instant.now()
        );

        try {
            repository.deleteVolume("orders-db");
        } catch (StorageException exception) {
            System.out.println(
                "Deletion protection: "
                    + exception.getMessage()
            );
        }

        repository.removeContainer("orders-v2");
        repository.deleteVolume("orders-db");

        System.out.println(
            "Storage governance workflow completed."
        );
    }
}

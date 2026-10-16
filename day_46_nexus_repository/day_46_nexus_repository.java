import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;

/*
 * Enterprise artifact repository governance.
 *
 * Compile and run with Java 17:
 *   javac NexusGovernance.java
 *   java NexusGovernance
 *
 * The implementation emphasizes domain modeling, immutable coordinates,
 * explicit publication policies, controlled state transitions, authorization,
 * repository composition, integrity checks, and auditable operations.
 */

public class NexusGovernance {

    enum RepositoryType {
        HOSTED, PROXY, GROUP
    }

    enum ArtifactFormat {
        MAVEN, NPM, PYPI, DOCKER, RAW
    }

    enum Permission {
        READ, PUBLISH, DELETE, ADMIN
    }

    enum ArtifactOrigin {
        INTERNAL_PUBLICATION, UPSTREAM_CACHE
    }

    static final class RepositoryException extends RuntimeException {
        RepositoryException(String message) {
            super(message);
        }

        RepositoryException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record ArtifactCoordinate(
            ArtifactFormat format,
            String name,
            String version,
            String extension,
            String classifier,
            String rawPath) {

        ArtifactCoordinate {
            Objects.requireNonNull(format, "format");
            name = requireText(name, "name");
            version = requireText(version, "version");
            extension = extension == null ? "" : extension;
            classifier = classifier == null ? "" : classifier;
            rawPath = rawPath == null ? "" : rawPath;
            validate();
        }

        private static String requireText(String value, String field) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(field + " is required");
            }
            return value;
        }

        private void validate() {
            if (name.contains("\\") || name.contains("..") ||
                    version.contains("/") || version.contains("\\")) {
                throw new IllegalArgumentException("Unsafe artifact coordinate");
            }

            switch (format) {
                case MAVEN -> {
                    String[] parts = name.split(":", -1);
                    if (parts.length != 2 || parts[0].isBlank() ||
                            parts[1].isBlank() ||
                            !extension.matches("[A-Za-z0-9]+")) {
                        throw new IllegalArgumentException(
                                "Maven requires group:artifact and an extension");
                    }
                }
                case NPM -> {
                    if (!name.matches("(?:@[a-z0-9._-]+/)?[a-z0-9._~-]+")) {
                        throw new IllegalArgumentException("Invalid npm package name");
                    }
                }
                case PYPI -> {
                    if (!name.matches("[A-Za-z0-9._-]+")) {
                        throw new IllegalArgumentException("Invalid PyPI project name");
                    }
                }
                case DOCKER -> {
                    if (!name.matches("[a-z0-9]+(?:[._/-][a-z0-9]+)*")) {
                        throw new IllegalArgumentException("Invalid Docker image name");
                    }
                }
                case RAW -> {
                    if (rawPath.isBlank() || rawPath.startsWith("/") ||
                            List.of(rawPath.split("/", -1)).stream()
                                    .anyMatch(part -> part.isBlank() ||
                                            part.equals(".") || part.equals(".."))) {
                        throw new IllegalArgumentException("Invalid raw artifact path");
                    }
                }
            }
        }

        String storagePath() {
            return switch (format) {
                case MAVEN -> {
                    String[] parts = name.split(":", -1);
                    String groupPath = parts[0].replace('.', '/');
                    String file = parts[1] + "-" + version +
                            (classifier.isBlank() ? "" : "-" + classifier) +
                            "." + extension;
                    yield groupPath + "/" + parts[1] + "/" + version + "/" + file;
                }
                case NPM -> name.replace("/", "%2f") + "/-/" +
                        name.substring(name.lastIndexOf('/') + 1) +
                        "-" + version + ".tgz";
                case PYPI -> name.replaceAll("[-_.]+", "-").toLowerCase(Locale.ROOT)
                        + "/" + version + "/" + extension;
                case DOCKER -> name + "/manifests/" + version;
                case RAW -> rawPath;
            };
        }
    }

    record Artifact(
            ArtifactCoordinate coordinate,
            byte[] content,
            String sha256,
            String publisher,
            Instant publishedAt,
            ArtifactOrigin origin) {

        Artifact {
            Objects.requireNonNull(coordinate);
            content = Objects.requireNonNull(content).clone();
            Objects.requireNonNull(sha256);
            Objects.requireNonNull(publisher);
            Objects.requireNonNull(publishedAt);
            Objects.requireNonNull(origin);

            if (content.length == 0) {
                throw new IllegalArgumentException("Empty artifacts are forbidden");
            }

            if (!digest(content).equalsIgnoreCase(sha256)) {
                throw new IllegalArgumentException("Artifact digest does not match content");
            }
        }

        @Override
        public byte[] content() {
            // A defensive copy prevents callers from modifying stored bytes.
            return content.clone();
        }

        static Artifact create(
                ArtifactCoordinate coordinate,
                byte[] content,
                String publisher,
                ArtifactOrigin origin) {
            return new Artifact(
                    coordinate, content, digest(content), publisher,
                    Instant.now(), origin);
        }
    }

    static final class Principal {
        private final String username;
        private final Map<String, Set<Permission>> grants;

        Principal(String username, Map<String, Set<Permission>> grants) {
            this.username = Objects.requireNonNull(username);
            Map<String, Set<Permission>> copy = new LinkedHashMap<>();
            grants.forEach((repository, permissions) ->
                    copy.put(repository, Set.copyOf(permissions)));
            this.grants = Collections.unmodifiableMap(copy);
        }

        String username() {
            return username;
        }

        boolean can(String repository, Permission permission) {
            Set<Permission> exact = grants.getOrDefault(
                    repository, Collections.emptySet());
            Set<Permission> wildcard = grants.getOrDefault(
                    "*", Collections.emptySet());

            return exact.contains(Permission.ADMIN) ||
                    exact.contains(permission) ||
                    wildcard.contains(Permission.ADMIN) ||
                    wildcard.contains(permission);
        }
    }

    static final class Repository {
        private final String name;
        private final RepositoryType type;
        private final ArtifactFormat format;
        private final boolean allowRedeploy;
        private final List<String> members;
        private final Map<ArtifactCoordinate, Artifact> artifacts = new TreeMap<>(
                (left, right) -> left.storagePath().compareTo(right.storagePath()));

        private long cacheHits;
        private long cacheMisses;

        Repository(
                String name,
                RepositoryType type,
                ArtifactFormat format,
                boolean allowRedeploy,
                List<String> members) {
            if (name == null ||
                    !name.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
                throw new IllegalArgumentException("Invalid repository name");
            }
            this.name = name;
            this.type = Objects.requireNonNull(type);
            this.format = Objects.requireNonNull(format);
            this.allowRedeploy = allowRedeploy;
            this.members = List.copyOf(members);

            if (type == RepositoryType.GROUP && this.members.isEmpty()) {
                throw new IllegalArgumentException("Group repository requires members");
            }
            if (type != RepositoryType.HOSTED && allowRedeploy) {
                throw new IllegalArgumentException(
                        "Redeployment policy belongs to hosted repositories");
            }
        }

        String name() {
            return name;
        }

        RepositoryType type() {
            return type;
        }

        ArtifactFormat format() {
            return format;
        }
    }

    record AuditEvent(
            Instant time,
            String actor,
            String action,
            String repository,
            String artifactPath,
            String digest) {}

    static final class RepositoryService {
        private final Map<String, Repository> repositories = new LinkedHashMap<>();
        private final List<AuditEvent> auditEvents = new ArrayList<>();

        synchronized void addRepository(Repository repository) {
            if (repositories.containsKey(repository.name())) {
                throw new RepositoryException(
                        "Repository already exists: " + repository.name());
            }

            for (String member : repository.members) {
                if (!repositories.containsKey(member)) {
                    throw new RepositoryException(
                            "Group member must be registered first: " + member);
                }

                if (repositories.get(member).format != repository.format) {
                    throw new RepositoryException(
                            "Group members must share the group's format");
                }
            }

            repositories.put(repository.name(), repository);
            auditEvents.add(new AuditEvent(
                    Instant.now(), "system", "REPOSITORY_CREATED",
                    repository.name(), "", ""));
        }

        synchronized Artifact publish(
                String repositoryName,
                ArtifactCoordinate coordinate,
                byte[] content,
                Principal principal) {
            Repository repository = requireRepository(repositoryName);
            authorize(repositoryName, Permission.PUBLISH, principal);

            if (repository.type != RepositoryType.HOSTED) {
                throw new RepositoryException(
                        "Only hosted repositories accept uploads");
            }
            if (coordinate.format() != repository.format) {
                throw new RepositoryException("Artifact format mismatch");
            }

            Artifact candidate = Artifact.create(
                    coordinate, content, principal.username(),
                    ArtifactOrigin.INTERNAL_PUBLICATION);

            Artifact existing = repository.artifacts.get(coordinate);
            if (existing != null && !repository.allowRedeploy) {
                throw new RepositoryException(
                        "Release redeployment is disabled: " + coordinate.storagePath());
            }

            repository.artifacts.put(coordinate, candidate);
            auditEvents.add(new AuditEvent(
                    Instant.now(), principal.username(), "ARTIFACT_PUBLISHED",
                    repositoryName, coordinate.storagePath(), candidate.sha256()));

            return candidate;
        }

        synchronized Artifact retrieve(
                String repositoryName,
                ArtifactCoordinate coordinate,
                Principal principal) {
            authorize(repositoryName, Permission.READ, principal);
            return resolve(repositoryName, coordinate, new java.util.HashSet<>());
        }

        private Artifact resolve(
                String repositoryName,
                ArtifactCoordinate coordinate,
                Set<String> visited) {
            if (!visited.add(repositoryName)) {
                throw new RepositoryException("Repository resolution cycle detected");
            }

            Repository repository = requireRepository(repositoryName);
            if (repository.format != coordinate.format()) {
                throw new RepositoryException("Repository format mismatch");
            }

            Artifact artifact = repository.artifacts.get(coordinate);
            if (artifact != null) {
                repository.cacheHits++;
                if (!digest(artifact.content()).equals(artifact.sha256())) {
                    throw new RepositoryException("Stored artifact integrity failure");
                }
                return artifact;
            }

            repository.cacheMisses++;

            if (repository.type == RepositoryType.HOSTED) {
                throw new RepositoryException(
                        "Artifact not found: " + coordinate.storagePath());
            }

            if (repository.type == RepositoryType.GROUP) {
                for (String member : repository.members) {
                    try {
                        return resolve(member, coordinate, new java.util.HashSet<>(visited));
                    } catch (RepositoryException missing) {
                        // A production implementation must distinguish 404 from
                        // authorization failures and upstream service outages.
                    }
                }
                throw new RepositoryException(
                        "No group member resolved " + coordinate.storagePath());
            }

            throw new RepositoryException(
                    "Proxy miss requires an HTTP transport adapter for " +
                            repository.name + ": " + coordinate.storagePath());
        }

        synchronized void delete(
                String repositoryName,
                ArtifactCoordinate coordinate,
                Principal principal) {
            Repository repository = requireRepository(repositoryName);
            authorize(repositoryName, Permission.DELETE, principal);

            if (repository.type != RepositoryType.HOSTED) {
                throw new RepositoryException(
                        "Only hosted repositories support artifact deletion");
            }

            Artifact removed = repository.artifacts.remove(coordinate);
            if (removed == null) {
                throw new RepositoryException("Artifact does not exist");
            }

            auditEvents.add(new AuditEvent(
                    Instant.now(), principal.username(), "ARTIFACT_DELETED",
                    repositoryName, coordinate.storagePath(), removed.sha256()));
        }

        synchronized List<String> inventory(String repositoryName, Principal principal) {
            authorize(repositoryName, Permission.READ, principal);
            Repository repository = requireRepository(repositoryName);

            return repository.artifacts.values().stream()
                    .map(artifact -> artifact.coordinate().storagePath() +
                            " sha256=" + artifact.sha256())
                    .toList();
        }

        synchronized List<AuditEvent> auditTrail() {
            return List.copyOf(auditEvents);
        }

        private Repository requireRepository(String name) {
            Repository repository = repositories.get(name);
            if (repository == null) {
                throw new RepositoryException("Unknown repository: " + name);
            }
            return repository;
        }

        private void authorize(
                String repository,
                Permission permission,
                Principal principal) {
            Objects.requireNonNull(principal);
            if (!principal.can(repository, permission)) {
                throw new RepositoryException(
                        "Permission denied: " + principal.username() +
                                " cannot " + permission + " on " + repository);
            }
        }
    }

    private static String digest(byte[] content) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256").digest(content);
            StringBuilder output = new StringBuilder(bytes.length * 2);
            for (byte value : bytes) {
                output.append(String.format("%02x", value & 0xff));
            }
            return output.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    public static void main(String[] args) {
        RepositoryService service = new RepositoryService();

        service.addRepository(new Repository(
                "maven-releases", RepositoryType.HOSTED,
                ArtifactFormat.MAVEN, false, List.of()));

        service.addRepository(new Repository(
                "maven-central-cache", RepositoryType.PROXY,
                ArtifactFormat.MAVEN, false, List.of()));

        service.addRepository(new Repository(
                "maven-public", RepositoryType.GROUP,
                ArtifactFormat.MAVEN, false,
                List.of("maven-releases", "maven-central-cache")));

        service.addRepository(new Repository(
                "npm-internal", RepositoryType.HOSTED,
                ArtifactFormat.NPM, false, List.of()));

        Principal publisher = new Principal("release-engineer", Map.of(
                "maven-releases", EnumSet.of(Permission.READ, Permission.PUBLISH),
                "maven-public", EnumSet.of(Permission.READ),
                "maven-central-cache", EnumSet.of(Permission.READ),
                "npm-internal", EnumSet.of(Permission.READ, Permission.PUBLISH)
        ));

        Principal buildAgent = new Principal("build-agent", Map.of(
                "maven-releases", EnumSet.of(Permission.READ),
                "maven-public", EnumSet.of(Permission.READ),
                "maven-central-cache", EnumSet.of(Permission.READ),
                "npm-internal", EnumSet.of(Permission.READ)
        ));

        ArtifactCoordinate coordinate = new ArtifactCoordinate(
                ArtifactFormat.MAVEN,
                "com.example.identity:identity-client",
                "5.0.0",
                "jar",
                "",
                "");

        Artifact published = service.publish(
                "maven-releases",
                coordinate,
                "identity-client release".getBytes(StandardCharsets.UTF_8),
                publisher);

        Artifact retrieved = service.retrieve(
                "maven-public", coordinate, buildAgent);

        if (!published.sha256().equals(retrieved.sha256())) {
            throw new IllegalStateException("Retrieved artifact checksum differs");
        }

        ArtifactCoordinate npmCoordinate = new ArtifactCoordinate(
                ArtifactFormat.NPM,
                "@example/identity-sdk",
                "2.1.0",
                "",
                "",
                "");

        service.publish(
                "npm-internal",
                npmCoordinate,
                "npm package archive".getBytes(StandardCharsets.UTF_8),
                publisher);

        try {
            service.publish(
                    "maven-releases",
                    coordinate,
                    "replacement bytes".getBytes(StandardCharsets.UTF_8),
                    publisher);
            throw new IllegalStateException("Immutable release was redeployed");
        } catch (RepositoryException expected) {
            System.out.println("Redeployment policy enforced: " + expected.getMessage());
        }

        try {
            service.retrieve("npm-internal", npmCoordinate,
                    new Principal("anonymous", Map.of()));
            throw new IllegalStateException("Anonymous retrieval unexpectedly succeeded");
        } catch (RepositoryException expected) {
            System.out.println("Authorization enforced: " + expected.getMessage());
        }

        System.out.println("\nPublished Maven artifact:");
        service.inventory("maven-releases", buildAgent)
                .forEach(System.out::println);

        System.out.println("\nAudit trail:");
        service.auditTrail().forEach(System.out::println);

        System.out.println("\nRepository governance checks completed.");
    }
}

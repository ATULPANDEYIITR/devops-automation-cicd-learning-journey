import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/*
 * Enterprise artifact governance model.
 *
 * Compile and run:
 *   javac ArtifactManagement.java
 *   java ArtifactManagement
 *
 * Java 17 or later is required. The implementation uses immutable records,
 * explicit domain states, typed exceptions, and a service boundary.
 */

public class ArtifactManagement {

    enum ArtifactState {
        PUBLISHED,
        QUARANTINED,
        REVOKED
    }

    enum ReleaseEnvironment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    static final class ArtifactException extends RuntimeException {
        ArtifactException(String message) {
            super(message);
        }
    }

    static final class ImmutableVersionException extends ArtifactException {
        ImmutableVersionException(String message) {
            super(message);
        }
    }

    static final class ValidationException extends ArtifactException {
        ValidationException(String message) {
            super(message);
        }
    }

    static final class IntegrityException extends ArtifactException {
        IntegrityException(String message) {
            super(message);
        }
    }

    record SemanticVersion(
        int major,
        int minor,
        int patch,
        String prerelease,
        String build
    ) implements Comparable<SemanticVersion> {

        private static final Pattern VERSION_PATTERN = Pattern.compile(
            "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)"
            + "(?:-([0-9A-Za-z.-]+))?(?:\\+([0-9A-Za-z.-]+))?$"
        );

        static SemanticVersion parse(String value) {
            Matcher matcher = VERSION_PATTERN.matcher(value);

            if (!matcher.matches()) {
                throw new ValidationException("Invalid semantic version: " + value);
            }

            int major = Integer.parseInt(matcher.group(1));
            int minor = Integer.parseInt(matcher.group(2));
            int patch = Integer.parseInt(matcher.group(3));
            String prerelease = Objects.requireNonNullElse(matcher.group(4), "");
            String build = Objects.requireNonNullElse(matcher.group(5), "");

            if (!prerelease.isEmpty()) {
                for (String identifier : prerelease.split("\\.")) {
                    if (identifier.isEmpty()) {
                        throw new ValidationException("Empty prerelease identifier.");
                    }

                    if (identifier.matches("\\d{2,}") && identifier.startsWith("0")) {
                        throw new ValidationException(
                            "Numeric prerelease identifiers cannot have leading zeroes."
                        );
                    }
                }
            }

            return new SemanticVersion(major, minor, patch, prerelease, build);
        }

        @Override
        public int compareTo(SemanticVersion other) {
            int result = Integer.compare(major, other.major);
            if (result != 0) return result;

            result = Integer.compare(minor, other.minor);
            if (result != 0) return result;

            result = Integer.compare(patch, other.patch);
            if (result != 0) return result;

            // A stable release has higher precedence than its prereleases.
            if (prerelease.isEmpty() && other.prerelease.isEmpty()) return 0;
            if (prerelease.isEmpty()) return 1;
            if (other.prerelease.isEmpty()) return -1;

            String[] left = prerelease.split("\\.");
            String[] right = other.prerelease.split("\\.");

            for (int index = 0; index < Math.min(left.length, right.length); index++) {
                boolean leftNumeric = left[index].matches("\\d+");
                boolean rightNumeric = right[index].matches("\\d+");

                if (leftNumeric && rightNumeric) {
                    result = new java.math.BigInteger(left[index])
                        .compareTo(new java.math.BigInteger(right[index]));
                } else if (leftNumeric != rightNumeric) {
                    result = leftNumeric ? -1 : 1;
                } else {
                    result = left[index].compareTo(right[index]);
                }

                if (result != 0) return result;
            }

            return Integer.compare(left.length, right.length);
        }

        @Override
        public String toString() {
            String result = major + "." + minor + "." + patch;
            if (!prerelease.isEmpty()) result += "-" + prerelease;
            if (!build.isEmpty()) result += "+" + build;
            return result;
        }
    }

    record ArtifactKey(String name, SemanticVersion version) {
        ArtifactKey {
            if (name == null || !name.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
                throw new ValidationException("Invalid artifact name.");
            }
            Objects.requireNonNull(version, "version");
        }

        @Override
        public String toString() {
            return name + "@" + version;
        }
    }

    record ArtifactManifest(
        ArtifactKey key,
        String digest,
        long sizeBytes,
        String mediaType,
        String publisher,
        String sourceRevision,
        Instant publishedAt,
        Map<String, String> metadata
    ) {
        ArtifactManifest {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(publishedAt, "publishedAt");

            if (digest == null || !digest.matches("[a-f0-9]{64}")) {
                throw new ValidationException("Manifest requires a SHA-256 digest.");
            }

            if (sizeBytes < 0) {
                throw new ValidationException("Artifact size cannot be negative.");
            }

            if (mediaType == null || !mediaType.contains("/")) {
                throw new ValidationException("Invalid artifact media type.");
            }

            if (publisher == null || publisher.isBlank()) {
                throw new ValidationException("Publisher identity is required.");
            }

            if (sourceRevision == null || sourceRevision.isBlank()) {
                throw new ValidationException("Source revision is required.");
            }

            metadata = Collections.unmodifiableMap(new TreeMap<>(metadata));
        }
    }

    record Blob(byte[] content, String digest) {
        Blob {
            content = content.clone();
            Objects.requireNonNull(digest, "digest");
        }

        @Override
        public byte[] content() {
            // Defensive copying prevents callers from mutating stored bytes.
            return content.clone();
        }
    }

    record AuditEvent(
        Instant occurredAt,
        String actor,
        String action,
        String target,
        String detail
    ) {}

    record Promotion(
        ReleaseEnvironment environment,
        ArtifactKey target,
        String actor,
        Instant promotedAt
    ) {}

    static final class ArtifactRegistry {
        private final Map<ArtifactKey, ArtifactManifest> manifests = new HashMap<>();
        private final Map<String, Blob> blobs = new HashMap<>();
        private final Map<ReleaseEnvironment, Promotion> promotions = new HashMap<>();
        private final Map<ArtifactKey, ArtifactState> states = new HashMap<>();
        private final List<AuditEvent> audit = new ArrayList<>();

        private static String sha256(byte[] bytes) {
            try {
                byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
                StringBuilder result = new StringBuilder(64);
                for (byte value : digest) {
                    result.append(String.format("%02x", value & 0xff));
                }
                return result.toString();
            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException("SHA-256 is unavailable.", exception);
            }
        }

        private void record(String actor, String action, String target, String detail) {
            audit.add(new AuditEvent(Instant.now(), actor, action, target, detail));
        }

        public synchronized ArtifactManifest publish(
            String name,
            String versionText,
            byte[] content,
            String publisher,
            String sourceRevision,
            String mediaType,
            Map<String, String> metadata
        ) {
            Objects.requireNonNull(content, "content");
            Objects.requireNonNull(metadata, "metadata");

            SemanticVersion version = SemanticVersion.parse(versionText);
            ArtifactKey key = new ArtifactKey(name, version);
            byte[] bytes = content.clone();
            String digest = sha256(bytes);

            ArtifactManifest existing = manifests.get(key);
            if (existing != null) {
                boolean identical =
                    existing.digest().equals(digest)
                    && existing.publisher().equals(publisher)
                    && existing.sourceRevision().equals(sourceRevision)
                    && existing.mediaType().equals(mediaType)
                    && existing.metadata().equals(new TreeMap<>(metadata));

                if (identical) return existing;

                throw new ImmutableVersionException(
                    "Published versions cannot be overwritten: " + key
                );
            }

            Blob blob = blobs.get(digest);
            if (blob != null) {
                if (!sha256(blob.content()).equals(digest)) {
                    throw new IntegrityException("Existing blob failed integrity verification.");
                }
            } else {
                blobs.put(digest, new Blob(bytes, digest));
            }

            ArtifactManifest manifest = new ArtifactManifest(
                key,
                digest,
                bytes.length,
                mediaType,
                publisher,
                sourceRevision,
                Instant.now(),
                metadata
            );

            manifests.put(key, manifest);
            states.put(key, ArtifactState.PUBLISHED);
            record(publisher, "PUBLISH", key.toString(), digest);
            return manifest;
        }

        public synchronized ArtifactManifest requireManifest(
            String name,
            String versionText
        ) {
            ArtifactKey key = new ArtifactKey(name, SemanticVersion.parse(versionText));
            ArtifactManifest manifest = manifests.get(key);

            if (manifest == null) {
                throw new ArtifactException("Artifact not found: " + key);
            }

            return manifest;
        }

        public synchronized byte[] download(String name, String versionText) {
            ArtifactManifest manifest = requireManifest(name, versionText);
            ArtifactKey key = manifest.key();

            if (states.get(key) != ArtifactState.PUBLISHED) {
                throw new ArtifactException(
                    "Artifact is not eligible for download: " + states.get(key)
                );
            }

            Blob blob = blobs.get(manifest.digest());
            if (blob == null) {
                throw new IntegrityException("Artifact blob is missing.");
            }

            byte[] bytes = blob.content();
            if (bytes.length != manifest.sizeBytes()
                || !sha256(bytes).equals(manifest.digest())) {
                throw new IntegrityException("Artifact digest or size mismatch.");
            }

            return bytes;
        }

        public synchronized void setState(
            String name,
            String versionText,
            ArtifactState targetState,
            String actor,
            String reason
        ) {
            ArtifactManifest manifest = requireManifest(name, versionText);
            ArtifactKey key = manifest.key();
            ArtifactState current = states.get(key);

            if (targetState == ArtifactState.PUBLISHED) {
                throw new ValidationException(
                    "Quarantined or revoked versions cannot be silently republished."
                );
            }

            if (current == ArtifactState.REVOKED) {
                throw new ArtifactException("Revoked versions are terminal.");
            }

            if (reason == null || reason.isBlank() || actor == null || actor.isBlank()) {
                throw new ValidationException("Actor and reason are required for state changes.");
            }

            states.put(key, targetState);
            record(actor, targetState.name(), key.toString(), reason);
        }

        public synchronized Promotion promote(
            ReleaseEnvironment environment,
            String name,
            String versionText,
            String actor
        ) {
            ArtifactManifest manifest = requireManifest(name, versionText);

            if (states.get(manifest.key()) != ArtifactState.PUBLISHED) {
                throw new ArtifactException("Only published artifacts may be promoted.");
            }

            if (actor == null || actor.isBlank()) {
                throw new ValidationException("Promotion actor is required.");
            }

            Promotion promotion = new Promotion(
                environment,
                manifest.key(),
                actor,
                Instant.now()
            );

            promotions.put(environment, promotion);
            record(actor, "PROMOTE", environment.name(), manifest.key().toString());
            return promotion;
        }

        public synchronized Optional<Promotion> currentPromotion(
            ReleaseEnvironment environment
        ) {
            return Optional.ofNullable(promotions.get(environment));
        }

        public synchronized List<ArtifactManifest> listVersions(String name) {
            return manifests.values().stream()
                .filter(manifest -> manifest.key().name().equals(name))
                .sorted(Comparator.comparing(manifest -> manifest.key().version()))
                .toList();
        }

        public synchronized List<AuditEvent> auditTrail() {
            return List.copyOf(audit);
        }

        public synchronized Map<ArtifactKey, Boolean> verifyAll() {
            Map<ArtifactKey, Boolean> results = new TreeMap<>(
                Comparator.comparing(ArtifactKey::toString)
            );

            for (ArtifactManifest manifest : manifests.values()) {
                Blob blob = blobs.get(manifest.digest());
                boolean valid = blob != null
                    && blob.content().length == manifest.sizeBytes()
                    && sha256(blob.content()).equals(manifest.digest());

                results.put(manifest.key(), valid);
            }

            return Collections.unmodifiableMap(results);
        }
    }

    public static void main(String[] args) {
        ArtifactRegistry registry = new ArtifactRegistry();

        ArtifactManifest candidate = registry.publish(
            "asset-inspection-model",
            "2.6.0-rc.1",
            "weights=model-rc\nformat=onnx\n".getBytes(StandardCharsets.UTF_8),
            "ci-publisher",
            "8d21ca0",
            "text/plain",
            Map.of("pipeline", "release-candidate", "platform", "linux-amd64")
        );

        ArtifactManifest stable = registry.publish(
            "asset-inspection-model",
            "2.6.0",
            "weights=model-stable\nformat=onnx\n".getBytes(StandardCharsets.UTF_8),
            "ci-publisher",
            "e4f9b61",
            "text/plain",
            Map.of("pipeline", "production-release", "platform", "linux-amd64")
        );

        System.out.println("Candidate: " + candidate.key());
        System.out.println("Stable digest: " + stable.digest());

        registry.promote(
            ReleaseEnvironment.STAGING,
            "asset-inspection-model",
            "2.6.0",
            "release-manager"
        );

        System.out.println(
            "Staging points to: " + registry.currentPromotion(ReleaseEnvironment.STAGING)
                .orElseThrow().target()
        );

        System.out.println(
            "Retrieved payload: " + new String(
                registry.download("asset-inspection-model", "2.6.0"),
                StandardCharsets.UTF_8
            ).trim()
        );

        try {
            registry.publish(
                "asset-inspection-model",
                "2.6.0",
                "substituted payload".getBytes(StandardCharsets.UTF_8),
                "ci-publisher",
                "new-commit",
                "text/plain",
                Map.of("pipeline", "production-release", "platform", "linux-amd64")
            );
        } catch (ImmutableVersionException exception) {
            System.out.println("Overwrite rejected: " + exception.getMessage());
        }

        registry.setState(
            "asset-inspection-model",
            "2.6.0-rc.1",
            ArtifactState.QUARANTINED,
            "security-operator",
            "Unexpected dependency detected during provenance review."
        );

        try {
            registry.download("asset-inspection-model", "2.6.0-rc.1");
        } catch (ArtifactException exception) {
            System.out.println("Quarantined download rejected: " + exception.getMessage());
        }

        System.out.println("Registered versions:");
        registry.listVersions("asset-inspection-model").forEach(
            manifest -> System.out.println(
                manifest.key() + " " + manifest.digest().substring(0, 16)
            )
        );

        System.out.println("Integrity results: " + registry.verifyAll());
        System.out.println("Audit events: " + registry.auditTrail().size());
    }
}

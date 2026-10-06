import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Enterprise-oriented build artifact governance model.
 *
 * The program represents artifacts as immutable domain objects and separates
 * publication policy, integrity verification, retention, and deployment
 * eligibility. It uses Java 17 standard-library features only.
 */
public class ArtifactGovernance {

    enum ArtifactState {
        CREATED,
        UPLOADED,
        VERIFIED,
        RETAINED,
        EXPIRED,
        DELETED
    }

    enum CheckType {
        UNIT_TESTS,
        SECURITY_SCAN,
        DEPENDENCY_AUDIT,
        PACKAGE_VALIDATION
    }

    record ArtifactFile(
        String path,
        long sizeBytes,
        String sha256
    ) {
        ArtifactFile {
            if (path == null || path.isBlank()) {
                throw new IllegalArgumentException("Artifact path is required.");
            }
            if (path.startsWith("/") || path.contains("..")) {
                throw new IllegalArgumentException(
                    "Unsafe artifact path: " + path
                );
            }
            if (sizeBytes < 0) {
                throw new IllegalArgumentException(
                    "Artifact size cannot be negative."
                );
            }
            Objects.requireNonNull(sha256, "Checksum is required.");
        }
    }

    record BuildMetadata(
        String repository,
        String commitSha,
        int buildNumber,
        String pipeline
    ) {
        BuildMetadata {
            if (repository == null || repository.isBlank()) {
                throw new IllegalArgumentException("Repository is required.");
            }
            if (commitSha == null || commitSha.isBlank()) {
                throw new IllegalArgumentException("Commit SHA is required.");
            }
            if (buildNumber <= 0) {
                throw new IllegalArgumentException(
                    "Build number must be positive."
                );
            }
        }
    }

    static final class Artifact {
        private final String id;
        private final BuildMetadata metadata;
        private final List<ArtifactFile> files;
        private final Set<CheckType> passedChecks;
        private final String archiveSha256;
        private final Instant createdAt;
        private final Duration retention;
        private ArtifactState state;

        Artifact(
            String id,
            BuildMetadata metadata,
            List<ArtifactFile> files,
            Set<CheckType> passedChecks,
            String archiveSha256,
            Duration retention
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Artifact ID is required.");
            }
            if (files == null || files.isEmpty()) {
                throw new IllegalArgumentException(
                    "An artifact must contain at least one file."
                );
            }
            if (retention.isNegative() || retention.isZero()) {
                throw new IllegalArgumentException(
                    "Retention must be greater than zero."
                );
            }

            this.id = id;
            this.metadata = Objects.requireNonNull(metadata);
            this.files = List.copyOf(files);
            this.passedChecks = Collections.unmodifiableSet(
                EnumSet.copyOf(passedChecks)
            );
            this.archiveSha256 = Objects.requireNonNull(archiveSha256);
            this.createdAt = Instant.now();
            this.retention = retention;
            this.state = ArtifactState.CREATED;
        }

        String id() {
            return id;
        }

        BuildMetadata metadata() {
            return metadata;
        }

        List<ArtifactFile> files() {
            return files;
        }

        Set<CheckType> passedChecks() {
            return passedChecks;
        }

        String archiveSha256() {
            return archiveSha256;
        }

        ArtifactState state() {
            return state;
        }

        Instant expiresAt() {
            return createdAt.plus(retention);
        }

        void transitionTo(ArtifactState next) {
            boolean valid = switch (state) {
                case CREATED -> next == ArtifactState.UPLOADED;
                case UPLOADED -> next == ArtifactState.VERIFIED;
                case VERIFIED -> next == ArtifactState.RETAINED
                    || next == ArtifactState.EXPIRED;
                case RETAINED -> next == ArtifactState.EXPIRED;
                case EXPIRED -> next == ArtifactState.DELETED;
                case DELETED -> false;
            };

            if (!valid) {
                throw new IllegalStateException(
                    "Invalid artifact transition: " + state + " -> " + next
                );
            }

            state = next;
        }

        long totalBytes() {
            return files.stream()
                .mapToLong(ArtifactFile::sizeBytes)
                .sum();
        }
    }

    interface ArtifactPolicy {
        boolean permitsUpload(Artifact artifact);

        boolean permitsDeployment(Artifact artifact);
    }

    static final class ProductionArtifactPolicy implements ArtifactPolicy {
        private final Set<CheckType> requiredChecks = EnumSet.of(
            CheckType.UNIT_TESTS,
            CheckType.SECURITY_SCAN,
            CheckType.DEPENDENCY_AUDIT,
            CheckType.PACKAGE_VALIDATION
        );

        @Override
        public boolean permitsUpload(Artifact artifact) {
            return artifact.state() == ArtifactState.CREATED
                && artifact.passedChecks().containsAll(requiredChecks);
        }

        @Override
        public boolean permitsDeployment(Artifact artifact) {
            return artifact.state() == ArtifactState.VERIFIED
                || artifact.state() == ArtifactState.RETAINED;
        }
    }

    static final class ArtifactService {
        private final Map<String, Artifact> repository =
            new LinkedHashMap<>();
        private final ArtifactPolicy policy;

        ArtifactService(ArtifactPolicy policy) {
            this.policy = policy;
        }

        void register(Artifact artifact) {
            if (repository.putIfAbsent(artifact.id(), artifact) != null) {
                throw new IllegalArgumentException(
                    "Artifact identifiers are immutable and cannot be reused."
                );
            }
        }

        void upload(String artifactId) {
            Artifact artifact = require(artifactId);

            if (!policy.permitsUpload(artifact)) {
                throw new IllegalStateException(
                    "Artifact failed publication policy."
                );
            }

            artifact.transitionTo(ArtifactState.UPLOADED);
        }

        void verify(String artifactId, String observedSha256) {
            Artifact artifact = require(artifactId);

            if (artifact.state() != ArtifactState.UPLOADED) {
                throw new IllegalStateException(
                    "Integrity verification requires an uploaded artifact."
                );
            }

            if (!artifact.archiveSha256().equals(observedSha256)) {
                throw new SecurityException(
                    "Checksum mismatch. Artifact cannot become deployable."
                );
            }

            artifact.transitionTo(ArtifactState.VERIFIED);
        }

        Artifact requestDeployment(String artifactId) {
            Artifact artifact = require(artifactId);

            if (!policy.permitsDeployment(artifact)) {
                throw new IllegalStateException(
                    "Only verified or retained artifacts can be deployed."
                );
            }

            return artifact;
        }

        void retain(String artifactId) {
            Artifact artifact = require(artifactId);
            artifact.transitionTo(ArtifactState.RETAINED);
        }

        void expire(String artifactId, Instant now) {
            Artifact artifact = require(artifactId);

            if (now.isBefore(artifact.expiresAt())) {
                throw new IllegalStateException(
                    "Artifact retention period has not ended."
                );
            }

            if (artifact.state() != ArtifactState.VERIFIED
                && artifact.state() != ArtifactState.RETAINED) {
                throw new IllegalStateException(
                    "Only active artifacts can expire."
                );
            }

            artifact.transitionTo(ArtifactState.EXPIRED);
        }

        void deleteExpired(String artifactId) {
            Artifact artifact = require(artifactId);

            if (artifact.state() != ArtifactState.EXPIRED) {
                throw new IllegalStateException(
                    "Only expired artifacts can be deleted."
                );
            }

            artifact.transitionTo(ArtifactState.DELETED);
        }

        private Artifact require(String artifactId) {
            Artifact artifact = repository.get(artifactId);
            if (artifact == null) {
                throw new IllegalArgumentException(
                    "Unknown artifact: " + artifactId
                );
            }
            return artifact;
        }

        void printRepository() {
            System.out.println("\nArtifact repository state");

            repository.values().forEach(artifact ->
                System.out.printf(
                    "  %s | %s | commit=%s | bytes=%d | checks=%s%n",
                    artifact.id(),
                    artifact.state(),
                    artifact.metadata().commitSha(),
                    artifact.totalBytes(),
                    artifact.passedChecks()
                )
            );
        }
    }

    private static Artifact createProductionArtifact() {
        BuildMetadata metadata = new BuildMetadata(
            "platform/payments-api",
            "7f3d8a2b91c4",
            184,
            "production-release"
        );

        List<ArtifactFile> files = List.of(
            new ArtifactFile(
                "bin/payments-api",
                4_821_032,
                "sha256:binary-184"
            ),
            new ArtifactFile(
                "config/runtime.json",
                1_290,
                "sha256:config-184"
            ),
            new ArtifactFile(
                "docs/release-notes.txt",
                4_811,
                "sha256:notes-184"
            )
        );

        Set<CheckType> checks = EnumSet.allOf(CheckType.class);

        return new Artifact(
            "payments-api-184",
            metadata,
            files,
            checks,
            "sha256:archive-184",
            Duration.ofDays(30)
        );
    }

    private static Artifact createRejectedArtifact() {
        BuildMetadata metadata = new BuildMetadata(
            "platform/payments-api",
            "broken-build-sha",
            185,
            "production-release"
        );

        return new Artifact(
            "payments-api-185",
            metadata,
            List.of(
                new ArtifactFile(
                    "bin/payments-api",
                    4_812_000,
                    "sha256:binary-185"
                )
            ),
            EnumSet.of(
                CheckType.UNIT_TESTS,
                CheckType.PACKAGE_VALIDATION
            ),
            "sha256:archive-185",
            Duration.ofDays(30)
        );
    }

    public static void main(String[] args) {
        ArtifactService service =
            new ArtifactService(new ProductionArtifactPolicy());

        Artifact productionArtifact = createProductionArtifact();
        service.register(productionArtifact);

        service.upload(productionArtifact.id());
        System.out.println("Uploaded: " + productionArtifact.id());

        try {
            service.verify(
                productionArtifact.id(),
                "sha256:wrong-value"
            );
        } catch (SecurityException error) {
            System.out.println(
                "Integrity failure correctly blocked: "
                    + error.getMessage()
            );
        }

        service.verify(
            productionArtifact.id(),
            productionArtifact.archiveSha256()
        );

        Artifact deployable =
            service.requestDeployment(productionArtifact.id());

        System.out.println(
            "Deployment permitted for commit "
                + deployable.metadata().commitSha()
        );

        service.retain(productionArtifact.id());

        Artifact rejectedArtifact = createRejectedArtifact();
        service.register(rejectedArtifact);

        try {
            service.upload(rejectedArtifact.id());
        } catch (IllegalStateException error) {
            System.out.println(
                "Publication policy correctly rejected artifact: "
                    + error.getMessage()
            );
        }

        /*
         * Retention is enforced independently from deployment eligibility.
         * The service does not delete a valid artifact merely because it is old;
         * expiration must first be reached and the lifecycle state must permit it.
         */
        Instant afterRetention =
            productionArtifact.expiresAt().plusSeconds(1);

        service.expire(productionArtifact.id(), afterRetention);
        service.deleteExpired(productionArtifact.id());

        service.printRepository();
    }
}

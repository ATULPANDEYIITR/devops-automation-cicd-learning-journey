import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Enterprise-oriented Docker Registry governance model.
 * Compile: javac RegistryGovernance.java
 * Run: java RegistryGovernance
 */
public class RegistryGovernance {

    enum Role {
        READER, PUBLISHER, ADMIN
    }

    enum ImageState {
        BUILT, PUBLISHED, RETIRED
    }

    enum CheckState {
        PASS, FAIL, UNKNOWN
    }

    enum Visibility {
        PUBLIC, PRIVATE
    }

    static class RegistryException extends RuntimeException {
        RegistryException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends RegistryException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class PolicyException extends RegistryException {
        PolicyException(String message) {
            super(message);
        }
    }

    static class ConflictException extends RegistryException {
        ConflictException(String message) {
            super(message);
        }
    }

    record Principal(String username, Role role, String token) {
        Principal {
            if (username == null || username.isBlank()) {
                throw new IllegalArgumentException("Username is required.");
            }
            Objects.requireNonNull(role, "Role is required.");
            if (token == null || token.length() < 8) {
                throw new IllegalArgumentException("Credential is too short.");
            }
        }

        @Override
        public String toString() {
            return "Principal[username=" + username + ", role=" + role + "]";
        }
    }

    record ImageArtifact(
            String repository,
            String tag,
            String digest,
            long sizeBytes,
            String platform,
            ImageState state,
            Instant createdAt
    ) {
        private static final Pattern REPOSITORY = Pattern.compile(
                "^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$"
        );
        private static final Pattern TAG = Pattern.compile(
                "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
        );
        private static final Pattern DIGEST = Pattern.compile("^sha256:[0-9a-f]{64}$");

        ImageArtifact {
            if (repository == null || repository.length() > 255 ||
                    !REPOSITORY.matcher(repository).matches()) {
                throw new IllegalArgumentException("Invalid repository path.");
            }
            if (tag == null || !TAG.matcher(tag).matches()) {
                throw new IllegalArgumentException("Invalid image tag.");
            }
            if (digest == null || !DIGEST.matcher(digest).matches()) {
                throw new IllegalArgumentException("Invalid SHA-256 digest.");
            }
            if (sizeBytes <= 0) {
                throw new IllegalArgumentException("Image size must be positive.");
            }
            if (!Set.of("linux/amd64", "linux/arm64", "linux/arm/v7")
                    .contains(platform)) {
                throw new IllegalArgumentException("Unsupported platform.");
            }
            Objects.requireNonNull(state, "Image state is required.");
            Objects.requireNonNull(createdAt, "Creation time is required.");
        }

        String reference() {
            return repository + ":" + tag;
        }

        ImageArtifact withState(ImageState newState) {
            return new ImageArtifact(
                    repository, tag, digest, sizeBytes, platform, newState, createdAt
            );
        }

        boolean isReleaseTag() {
            return tag.matches("^v\\d+\\.\\d+\\.\\d+$");
        }
    }

    record ReviewEvidence(
            CheckState vulnerabilityScan,
            boolean signatureVerified,
            boolean provenanceVerified
    ) {
        ReviewEvidence {
            Objects.requireNonNull(vulnerabilityScan);
        }
    }

    record RegistryPolicy(
            Set<String> allowedRegistries,
            long maximumSizeBytes,
            boolean requireScanPass,
            boolean requireSignature,
            boolean requireProvenance,
            boolean immutableReleaseTags
    ) {
        RegistryPolicy {
            allowedRegistries = Set.copyOf(allowedRegistries);
            if (allowedRegistries.isEmpty()) {
                throw new IllegalArgumentException("Allowed registry list is empty.");
            }
            if (maximumSizeBytes <= 0) {
                throw new IllegalArgumentException("Maximum image size must be positive.");
            }
        }
    }

    record AuditEvent(Instant time, String action, String actor, String reference) {}

    record Eligibility(boolean allowed, List<String> reasons) {
        Eligibility {
            reasons = List.copyOf(reasons);
        }
    }

    interface ImagePolicy {
        List<String> violations(
                Principal principal,
                ImageArtifact image,
                RegistryPolicy policy,
                ReviewEvidence evidence,
                String registryName
        );
    }

    static final class DefaultImagePolicy implements ImagePolicy {
        @Override
        public List<String> violations(
                Principal principal,
                ImageArtifact image,
                RegistryPolicy policy,
                ReviewEvidence evidence,
                String registryName
        ) {
            List<String> failures = new ArrayList<>();

            if (!EnumSet.of(Role.PUBLISHER, Role.ADMIN).contains(principal.role())) {
                failures.add("Publisher or administrator role is required.");
            }
            if (!policy.allowedRegistries().contains(registryName)) {
                failures.add("Registry is not allowed by policy.");
            }
            if (image.sizeBytes() > policy.maximumSizeBytes()) {
                failures.add("Image exceeds the configured size limit.");
            }
            if (policy.requireScanPass() &&
                    evidence.vulnerabilityScan() != CheckState.PASS) {
                failures.add("Vulnerability scan must pass.");
            }
            if (policy.requireSignature() && !evidence.signatureVerified()) {
                failures.add("Image signature is not verified.");
            }
            if (policy.requireProvenance() && !evidence.provenanceVerified()) {
                failures.add("Build provenance is not verified.");
            }

            return failures;
        }
    }

    static final class RegistryService {
        private final String name;
        private final Visibility visibility;
        private final Map<String, Principal> principals = new HashMap<>();
        private final Map<String, ImageArtifact> images = new HashMap<>();
        private final List<AuditEvent> audit = new ArrayList<>();
        private final ImagePolicy imagePolicy;

        RegistryService(String name, Visibility visibility, ImagePolicy imagePolicy) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Registry name is required.");
            }
            this.name = name;
            this.visibility = Objects.requireNonNull(visibility);
            this.imagePolicy = Objects.requireNonNull(imagePolicy);
        }

        void registerPrincipal(Principal principal) {
            principals.put(principal.username(), principal);
        }

        Principal authenticate(String username, String token) {
            Principal principal = principals.get(username);
            boolean valid = principal != null && token != null &&
                    MessageDigest.isEqual(
                            principal.token().getBytes(StandardCharsets.UTF_8),
                            token.getBytes(StandardCharsets.UTF_8)
                    );

            if (!valid) {
                record("authentication_failed", username, "");
                throw new AuthorizationException("Invalid credentials.");
            }

            record("authenticated", username, "");
            return principal;
        }

        Eligibility evaluate(
                Principal principal,
                ImageArtifact image,
                RegistryPolicy policy,
                ReviewEvidence evidence
        ) {
            List<String> failures = imagePolicy.violations(
                    principal, image, policy, evidence, name
            );

            ImageArtifact existing = images.get(image.reference());
            if (existing != null && !existing.digest().equals(image.digest()) &&
                    policy.immutableReleaseTags() && image.isReleaseTag()) {
                failures = new ArrayList<>(failures);
                failures.add("Release tag cannot be reassigned to another digest.");
            }

            return new Eligibility(failures.isEmpty(), failures);
        }

        ImageArtifact publish(
                Principal principal,
                ImageArtifact image,
                RegistryPolicy policy,
                ReviewEvidence evidence
        ) {
            Eligibility result = evaluate(principal, image, policy, evidence);
            if (!result.allowed()) {
                throw new PolicyException(String.join(" ", result.reasons()));
            }

            ImageArtifact existing = images.get(image.reference());
            if (existing != null && existing.digest().equals(image.digest())) {
                record("publish_idempotent", principal.username(), image.reference());
                return existing;
            }

            ImageArtifact published = image.withState(ImageState.PUBLISHED);
            images.put(published.reference(), published);
            record("publish", principal.username(), published.reference());
            return published;
        }

        ImageArtifact pull(Principal principal, String reference) {
            if (visibility == Visibility.PRIVATE && principal == null) {
                throw new AuthorizationException("Private registry login required.");
            }

            if (principal != null && !principals.containsKey(principal.username())) {
                throw new AuthorizationException("Principal is not registered.");
            }

            ImageArtifact image = images.get(reference);
            if (image == null || image.state() != ImageState.PUBLISHED) {
                throw new RegistryException("Published image not found.");
            }

            record("pull", principal == null ? "anonymous" : principal.username(), reference);
            return image;
        }

        List<ImageArtifact> publishedImages() {
            return images.values().stream()
                    .filter(image -> image.state() == ImageState.PUBLISHED)
                    .sorted((a, b) -> a.reference().compareTo(b.reference()))
                    .toList();
        }

        List<AuditEvent> auditEvents() {
            return Collections.unmodifiableList(audit);
        }

        long totalBytes() {
            return publishedImages().stream().mapToLong(ImageArtifact::sizeBytes).sum();
        }

        private void record(String action, String actor, String reference) {
            audit.add(new AuditEvent(Instant.now(), action, actor, reference));
        }
    }

    private static String digest(String content) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8));
            StringBuilder output = new StringBuilder("sha256:");
            for (byte value : hash) {
                output.append(String.format("%02x", value));
            }
            return output.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable.", exception);
        }
    }

    public static void main(String[] args) {
        RegistryService registry = new RegistryService(
                "registry.example.com",
                Visibility.PRIVATE,
                new DefaultImagePolicy()
        );

        Principal publisher = new Principal(
                "release-bot", Role.PUBLISHER, "demo-publisher-token"
        );
        Principal deployer = new Principal(
                "deployment-bot", Role.READER, "demo-reader-token"
        );

        registry.registerPrincipal(publisher);
        registry.registerPrincipal(deployer);

        RegistryPolicy policy = new RegistryPolicy(
                Set.of("registry.example.com"),
                1_000_000,
                true,
                true,
                true,
                true
        );

        ReviewEvidence passedEvidence = new ReviewEvidence(
                CheckState.PASS, true, true
        );

        ImageArtifact image = new ImageArtifact(
                "commerce/orders-api",
                "v2.4.1",
                digest("{\"schemaVersion\":2,\"mediaType\":\"application/vnd.oci.image.manifest.v1+json\"}"),
                125_000,
                "linux/amd64",
                ImageState.BUILT,
                Instant.now()
        );

        Principal authenticatedPublisher = registry.authenticate(
                publisher.username(), publisher.token()
        );
        Principal authenticatedDeployer = registry.authenticate(
                deployer.username(), deployer.token()
        );

        Eligibility eligibility = registry.evaluate(
                authenticatedPublisher, image, policy, passedEvidence
        );
        System.out.println("Release eligibility: " + eligibility.allowed());
        if (!eligibility.allowed()) {
            eligibility.reasons().forEach(reason -> System.out.println("  " + reason));
            return;
        }

        ImageArtifact published = registry.publish(
                authenticatedPublisher, image, policy, passedEvidence
        );
        ImageArtifact deployed = registry.pull(
                authenticatedDeployer, published.reference()
        );

        System.out.println("Published reference: " + published.reference());
        System.out.println("Verified digest: " + deployed.digest());

        ImageArtifact unsafeImage = new ImageArtifact(
                "commerce/orders-api",
                "v2.4.2",
                digest("unsafe build manifest"),
                130_000,
                "linux/amd64",
                ImageState.BUILT,
                Instant.now()
        );

        Eligibility blocked = registry.evaluate(
                authenticatedPublisher,
                unsafeImage,
                policy,
                new ReviewEvidence(CheckState.FAIL, true, true)
        );

        System.out.println("Unsafe release eligibility: " + blocked.allowed());
        blocked.reasons().forEach(reason -> System.out.println("  " + reason));

        System.out.println("Published image count: " + registry.publishedImages().size());
        System.out.println("Total image bytes: " + registry.totalBytes());
        System.out.println("Audit events: " + registry.auditEvents().size());
    }
}

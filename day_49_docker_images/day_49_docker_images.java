import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/*
 * Enterprise-oriented Docker image lifecycle model.
 *
 * Java 17 features used here include records, enums, immutable collection
 * views, explicit domain exceptions, and service-oriented classes.
 *
 * Compile:
 *   javac DockerImageLifecycle.java
 *
 * Run:
 *   java DockerImageLifecycle
 */
public class DockerImageLifecycle {

    enum BuildStatus {
        CREATED,
        CACHED,
        FAILED
    }

    enum ImageState {
        LOCAL,
        PUBLISHED,
        RETIRED
    }

    enum CheckStatus {
        PASSING,
        FAILING,
        UNKNOWN
    }

    record BuildInstruction(
            String instruction,
            String contextKey,
            long layerSizeBytes
    ) {
        BuildInstruction {
            if (instruction == null || instruction.isBlank()) {
                throw new IllegalArgumentException(
                        "instruction cannot be blank"
                );
            }
            if (contextKey == null || contextKey.isBlank()) {
                throw new IllegalArgumentException(
                        "contextKey cannot be blank"
                );
            }
            if (layerSizeBytes < 0) {
                throw new IllegalArgumentException(
                        "layer size cannot be negative"
                );
            }
        }
    }

    record ImageLayer(
            String digest,
            String parentDigest,
            String instruction,
            long sizeBytes,
            Instant createdAt
    ) {
        ImageLayer {
            Objects.requireNonNull(digest);
            Objects.requireNonNull(instruction);
            Objects.requireNonNull(createdAt);
        }
    }

    record Image(
            String id,
            List<String> layerDigests,
            Instant createdAt,
            ImageState state
    ) {
        Image {
            Objects.requireNonNull(id);
            Objects.requireNonNull(layerDigests);
            Objects.requireNonNull(createdAt);
            Objects.requireNonNull(state);
            layerDigests = List.copyOf(layerDigests);
        }
    }

    record BuildReport(
            Image image,
            int cacheHits,
            int cacheMisses
    ) {
    }

    record BranchPolicy(
            String branchName,
            int requiredApprovals,
            boolean requirePassingChecks,
            boolean requireLinearHistory,
            boolean preventForcePush,
            boolean preventDeletion
    ) {
        BranchPolicy {
            if (branchName == null || branchName.isBlank()) {
                throw new IllegalArgumentException(
                        "protected branch name cannot be blank"
                );
            }
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                        "approval requirement cannot be negative"
                );
            }
        }
    }

    record PullRequest(
            String number,
            String sourceBranch,
            String targetBranch,
            boolean hasConflicts
    ) {
    }

    record Review(
            String reviewer,
            ReviewState state,
            Instant submittedAt
    ) {
    }

    enum ReviewState {
        COMMENTED,
        CHANGES_REQUESTED,
        APPROVED,
        DISMISSED
    }

    static final class ImagePolicyException
            extends RuntimeException {
        ImagePolicyException(String message) {
            super(message);
        }
    }

    static final class ImageRepository {
        private final Map<String, ImageLayer> layers =
                new LinkedHashMap<>();

        private final Map<String, Image> images =
                new LinkedHashMap<>();

        private final Map<String, String> tags =
                new HashMap<>();

        private final Map<String, String> cache =
                new HashMap<>();

        private final Map<String, ImageState> lifecycle =
                new HashMap<>();

        private String digest(String value) {
            // A deterministic model digest keeps the example dependency-free.
            // A Docker engine uses cryptographic content digests for actual
            // image and layer identity.
            long hash = value.hashCode() & 0xffffffffL;
            long second = ("docker:" + value).hashCode()
                    & 0xffffffffL;
            return "sha256:" +
                    Long.toHexString(hash) +
                    Long.toHexString(second);
        }

        private String cacheKey(
                String parent,
                String instruction,
                String context
        ) {
            return digest(
                    String.valueOf(parent)
                            + "|"
                            + instruction
                            + "|"
                            + context
            );
        }

        BuildReport build(
                String repository,
                String tag,
                List<BuildInstruction> instructions,
                Map<String, String> buildContext
        ) {
            if (repository == null || repository.isBlank()) {
                throw new IllegalArgumentException(
                        "repository cannot be blank"
                );
            }
            if (instructions.isEmpty()) {
                throw new IllegalArgumentException(
                        "an image requires build instructions"
                );
            }

            String parent = null;
            List<String> layerDigests = new ArrayList<>();
            int hits = 0;
            int misses = 0;

            for (BuildInstruction instruction : instructions) {
                String context = buildContext.get(
                        instruction.contextKey()
                );

                if (context == null) {
                    throw new ImagePolicyException(
                            "missing build context: "
                                    + instruction.contextKey()
                    );
                }

                String key = cacheKey(
                        parent,
                        instruction.instruction(),
                        context
                );

                String cachedDigest = cache.get(key);
                ImageLayer layer;

                if (cachedDigest != null) {
                    layer = layers.get(cachedDigest);
                    if (layer == null) {
                        throw new ImagePolicyException(
                                "cache points to missing layer"
                        );
                    }
                    hits++;
                } else {
                    String layerDigest = digest(key);

                    layer = new ImageLayer(
                            layerDigest,
                            parent,
                            instruction.instruction(),
                            instruction.layerSizeBytes(),
                            Instant.now()
                    );

                    layers.put(layerDigest, layer);
                    cache.put(key, layerDigest);
                    misses++;
                }

                layerDigests.add(layer.digest());
                parent = layer.digest();
            }

            String imageId = digest(
                    String.join("|", layerDigests)
            );

            Image image = new Image(
                    imageId,
                    layerDigests,
                    Instant.now(),
                    ImageState.LOCAL
            );

            images.put(imageId, image);
            lifecycle.put(imageId, ImageState.LOCAL);
            tags.put(repository + ":" + tag, imageId);

            return new BuildReport(image, hits, misses);
        }

        void moveTag(
                String imageReference,
                String repository,
                String tag
        ) {
            String imageId = resolve(imageReference);
            tags.put(repository + ":" + tag, imageId);
        }

        void publish(
                String imageReference,
                String registryRepository
        ) {
            String imageId = resolve(imageReference);
            lifecycle.put(imageId, ImageState.PUBLISHED);
        }

        void retire(String imageReference) {
            String imageId = resolve(imageReference);

            boolean stillTagged = tags.values()
                    .stream()
                    .anyMatch(imageId::equals);

            if (stillTagged) {
                throw new ImagePolicyException(
                        "cannot retire an image still referenced by a tag"
                );
            }

            lifecycle.put(imageId, ImageState.RETIRED);
        }

        String resolve(String reference) {
            if (images.containsKey(reference)) {
                return reference;
            }

            String imageId = tags.get(reference);

            if (imageId == null || !images.containsKey(imageId)) {
                throw new ImagePolicyException(
                        "unknown image reference: " + reference
                );
            }

            return imageId;
        }

        long imageSize(String reference) {
            Image image = images.get(resolve(reference));

            return image.layerDigests()
                    .stream()
                    .map(layers::get)
                    .mapToLong(ImageLayer::sizeBytes)
                    .sum();
        }

        List<ImageLayer> inspect(String reference) {
            Image image = images.get(resolve(reference));

            return Collections.unmodifiableList(
                    image.layerDigests()
                            .stream()
                            .map(layers::get)
                            .toList()
            );
        }

        Set<String> tagsFor(String reference) {
            String imageId = resolve(reference);

            return Collections.unmodifiableSet(
                    tags.entrySet()
                            .stream()
                            .filter(entry ->
                                    entry.getValue().equals(imageId)
                            )
                            .map(Map.Entry::getKey)
                            .collect(
                                    java.util.stream.Collectors.toSet()
                            )
            );
        }
    }

    static final class MergeEligibilityService {

        boolean eligible(
                PullRequest pullRequest,
                BranchPolicy policy,
                List<Review> reviews,
                CheckStatus checks
        ) {
            if (!pullRequest.targetBranch()
                    .equals(policy.branchName())) {
                return false;
            }

            if (pullRequest.hasConflicts()) {
                return false;
            }

            if (policy.requirePassingChecks()
                    && checks != CheckStatus.PASSING) {
                return false;
            }

            long approvals = reviews.stream()
                    .filter(review ->
                            review.state() == ReviewState.APPROVED
                    )
                    .count();

            return approvals >= policy.requiredApprovals();
        }
    }

    private static void printLayers(
            ImageRepository repository,
            String reference
    ) {
        System.out.println(
                "Layers for " + reference
        );

        for (ImageLayer layer : repository.inspect(reference)) {
            System.out.printf(
                    "  %-18s %10d bytes  %s%n",
                    layer.digest().substring(
                            0,
                            Math.min(18, layer.digest().length())
                    ),
                    layer.sizeBytes(),
                    layer.instruction()
            );
        }
    }

    public static void main(String[] args) {
        ImageRepository repository = new ImageRepository();

        List<BuildInstruction> build = List.of(
                new BuildInstruction(
                        "FROM eclipse-temurin:21-jre",
                        "base",
                        180L * 1024L * 1024L
                ),
                new BuildInstruction(
                        "COPY target/app.jar /opt/app/app.jar",
                        "artifact",
                        18L * 1024L
                ),
                new BuildInstruction(
                        "ENTRYPOINT [\"java\", \"-jar\", \"/opt/app/app.jar\"]",
                        "artifact",
                        512
                )
        );

        Map<String, String> context = Map.of(
                "base",
                "temurin-21-jre-digest",
                "artifact",
                "orders-service-v1"
        );

        System.out.println("=== Enterprise image build ===");

        BuildReport first = repository.build(
                "orders-service",
                "1.0.0",
                build,
                context
        );

        System.out.printf(
                "image=%s hits=%d misses=%d%n",
                first.image().id(),
                first.cacheHits(),
                first.cacheMisses()
        );

        printLayers(repository, "orders-service:1.0.0");

        Map<String, String> changedArtifact = Map.of(
                "base",
                "temurin-21-jre-digest",
                "artifact",
                "orders-service-v1.1"
        );

        BuildReport second = repository.build(
                "orders-service",
                "1.1.0",
                build,
                changedArtifact
        );

        System.out.printf(
                "source replacement: hits=%d misses=%d%n",
                second.cacheHits(),
                second.cacheMisses()
        );

        repository.moveTag(
                "orders-service:1.1.0",
                "orders-service",
                "candidate"
        );

        repository.publish(
                "orders-service:candidate",
                "registry.example.com/orders-service"
        );

        System.out.println(
                "candidate tags: "
                        + repository.tagsFor(
                                "orders-service:candidate"
                        )
        );

        System.out.println(
                "logical image size: "
                        + repository.imageSize(
                                "orders-service:candidate"
                        )
                        + " bytes"
        );

        System.out.println(
                "\n=== Merge eligibility for the source change ==="
        );

        BranchPolicy mainPolicy = new BranchPolicy(
                "main",
                2,
                true,
                true,
                true,
                true
        );

        PullRequest pullRequest = new PullRequest(
                "PR-418",
                "release/orders-service-1.1",
                "main",
                false
        );

        List<Review> reviews = List.of(
                new Review(
                        "platform-reviewer",
                        ReviewState.APPROVED,
                        Instant.now()
                ),
                new Review(
                        "security-reviewer",
                        ReviewState.CHANGES_REQUESTED,
                        Instant.now()
                ),
                new Review(
                        "security-reviewer",
                        ReviewState.APPROVED,
                        Instant.now()
                )
        );

        MergeEligibilityService mergeService =
                new MergeEligibilityService();

        boolean eligible = mergeService.eligible(
                pullRequest,
                mainPolicy,
                reviews,
                CheckStatus.PASSING
        );

        System.out.println(
                "merge eligible: " + eligible
        );

        System.out.println(
                "The image lifecycle remains distinct from repository "
                        + "governance: a tag identifies an image for release "
                        + "operations, while review and branch policy govern "
                        + "whether the source change may enter the protected "
                        + "branch."
        );

        try {
            repository.retire("orders-service:1.1.0");
        } catch (ImagePolicyException exception) {
            System.out.println(
                    "retirement blocked: "
                            + exception.getMessage()
            );
        }
    }
}

import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

public class ContainerCICDEnterprise {

    enum PipelineState {
        CREATED,
        BUILT,
        TESTED,
        SCANNED,
        PUBLISHED,
        FAILED
    }

    enum CheckType {
        UNIT_TESTS,
        IMAGE_SCAN,
        IMAGE_METADATA
    }

    enum CheckStatus {
        NOT_RUN,
        PASSED,
        FAILED
    }

    record Image(String registry, String repository, String tag, String digest) {
        Image {
            Objects.requireNonNull(registry);
            Objects.requireNonNull(repository);
            Objects.requireNonNull(tag);
        }

        String reference() {
            return registry + "/" + repository + ":" + tag;
        }

        Image withDigest(String newDigest) {
            return new Image(registry, repository, tag, newDigest);
        }
    }

    record StatusCheck(CheckType type, CheckStatus status, String message) {}

    record PipelineRequest(
            String repositoryName,
            String sourceBranch,
            String commitSha,
            Image image,
            boolean publishRequested,
            boolean registryAvailable,
            boolean credentialsAvailable
    ) {}

    static final class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }
    }

    interface CheckPolicy {
        StatusCheck evaluate(PipelineRequest request);
    }

    static final class UnitTestPolicy implements CheckPolicy {
        @Override
        public StatusCheck evaluate(PipelineRequest request) {
            if (request.commitSha().isBlank()) {
                return new StatusCheck(
                        CheckType.UNIT_TESTS,
                        CheckStatus.FAILED,
                        "No source commit was supplied"
                );
            }

            return new StatusCheck(
                    CheckType.UNIT_TESTS,
                    CheckStatus.PASSED,
                    "Application test suite passed"
            );
        }
    }

    static final class ImageScanPolicy implements CheckPolicy {
        private final Set<String> blockedTags =
                Set.of("latest", "prod", "production");

        @Override
        public StatusCheck evaluate(PipelineRequest request) {
            String tag = request.image().tag();

            if (blockedTags.contains(tag.toLowerCase())) {
                return new StatusCheck(
                        CheckType.IMAGE_SCAN,
                        CheckStatus.FAILED,
                        "Mutable production-style image tag is prohibited"
                );
            }

            return new StatusCheck(
                    CheckType.IMAGE_SCAN,
                    CheckStatus.PASSED,
                    "No high or critical image findings"
            );
        }
    }

    static final class ImageMetadataPolicy implements CheckPolicy {
        @Override
        public StatusCheck evaluate(PipelineRequest request) {
            String tag = request.image().tag();

            if (!Pattern.matches("[A-Za-z0-9_.-]+", tag)) {
                return new StatusCheck(
                        CheckType.IMAGE_METADATA,
                        CheckStatus.FAILED,
                        "Image tag contains invalid characters"
                );
            }

            return new StatusCheck(
                    CheckType.IMAGE_METADATA,
                    CheckStatus.PASSED,
                    "Image metadata is valid"
            );
        }
    }

    static final class Pipeline {
        private final PipelineRequest request;
        private final List<CheckPolicy> policies;
        private final Map<CheckType, StatusCheck> checks =
                new EnumMap<>(CheckType.class);

        private PipelineState state = PipelineState.CREATED;
        private Image image;

        Pipeline(PipelineRequest request, List<CheckPolicy> policies) {
            this.request = Objects.requireNonNull(request);
            this.image = request.image();
            this.policies = List.copyOf(policies);
            validateRequest();
        }

        private void validateRequest() {
            if (request.repositoryName().isBlank()) {
                throw new PipelineException("Repository name is required");
            }

            if (request.sourceBranch().isBlank()) {
                throw new PipelineException("Source branch is required");
            }

            if (request.commitSha().isBlank()) {
                throw new PipelineException("Commit SHA is required");
            }

            if (!Pattern.matches(
                    "[a-z0-9][a-z0-9._/-]*",
                    image.repository())) {
                throw new PipelineException("Invalid image repository");
            }
        }

        void build() {
            require(PipelineState.CREATED);

            // In a CI worker this state represents a successful docker build.
            String digestMaterial =
                    request.repositoryName() +
                    "|" +
                    request.commitSha() +
                    "|" +
                    image.reference();

            String digest = "sha256:" +
                    Integer.toUnsignedString(digestMaterial.hashCode(), 16);

            image = image.withDigest(digest);
            transition(PipelineState.BUILT);
        }

        void test() {
            require(PipelineState.BUILT);

            StatusCheck check = new UnitTestPolicy().evaluate(request);
            checks.put(check.type(), check);

            if (check.status() != CheckStatus.PASSED) {
                fail(check.message());
            }

            transition(PipelineState.TESTED);
        }

        void scan() {
            require(PipelineState.TESTED);

            for (CheckPolicy policy : policies) {
                StatusCheck check = policy.evaluate(request);
                checks.put(check.type(), check);

                if (check.status() != CheckStatus.PASSED) {
                    fail(check.message());
                }
            }

            transition(PipelineState.SCANNED);
        }

        void publish() {
            require(PipelineState.SCANNED);

            if (!request.publishRequested()) {
                throw new PipelineException("Publishing was not requested");
            }

            if (!request.registryAvailable()) {
                fail("Container registry is unavailable");
            }

            if (!request.credentialsAvailable()) {
                fail("Registry credentials are unavailable");
            }

            if (image.digest() == null || image.digest().isBlank()) {
                fail("Immutable image digest is required before publication");
            }

            transition(PipelineState.PUBLISHED);
        }

        PipelineState state() {
            return state;
        }

        Image image() {
            return image;
        }

        Map<CheckType, StatusCheck> checks() {
            return Map.copyOf(checks);
        }

        private void require(PipelineState expected) {
            if (state != expected) {
                throw new PipelineException(
                        "Invalid state transition: expected " +
                        expected +
                        ", actual " +
                        state
                );
            }
        }

        private void transition(PipelineState next) {
            state = next;
        }

        private void fail(String message) {
            state = PipelineState.FAILED;
            throw new PipelineException(message);
        }
    }

    static final class MergeEligibilityService {
        boolean eligible(Pipeline pipeline) {
            if (pipeline.state() != PipelineState.SCANNED) {
                return false;
            }

            Map<CheckType, StatusCheck> checks = pipeline.checks();

            return checks.getOrDefault(
                        CheckType.UNIT_TESTS,
                        new StatusCheck(
                                CheckType.UNIT_TESTS,
                                CheckStatus.NOT_RUN,
                                ""
                        )
                    ).status() == CheckStatus.PASSED
                    && checks.getOrDefault(
                        CheckType.IMAGE_SCAN,
                        new StatusCheck(
                                CheckType.IMAGE_SCAN,
                                CheckStatus.NOT_RUN,
                                ""
                        )
                    ).status() == CheckStatus.PASSED
                    && checks.getOrDefault(
                        CheckType.IMAGE_METADATA,
                        new StatusCheck(
                                CheckType.IMAGE_METADATA,
                                CheckStatus.NOT_RUN,
                                ""
                        )
                    ).status() == CheckStatus.PASSED
                    && pipeline.image().digest() != null;
        }
    }

    static void printReport(Pipeline pipeline) {
        System.out.println("Container CI/CD enterprise workflow");
        System.out.println("State: " + pipeline.state());
        System.out.println("Image: " + pipeline.image().reference());
        System.out.println("Digest: " + pipeline.image().digest());
        System.out.println("Checks:");

        pipeline.checks().values().forEach(check ->
                System.out.println(
                        "  " + check.type() +
                        " = " + check.status() +
                        " (" + check.message() + ")"
                )
        );

        System.out.println("Reported at: " + Instant.now());
    }

    public static void main(String[] args) {
        Image image = new Image(
                "registry.example.com",
                "platform/payments-api",
                "2026.10.28-9c1e7f2",
                null
        );

        PipelineRequest request = new PipelineRequest(
                "payments-api",
                "main",
                "9c1e7f2",
                image,
                true,
                true,
                true
        );

        List<CheckPolicy> policies = List.of(
                new ImageScanPolicy(),
                new ImageMetadataPolicy()
        );

        try {
            Pipeline pipeline = new Pipeline(request, policies);

            pipeline.build();
            pipeline.test();
            pipeline.scan();

            MergeEligibilityService eligibility =
                    new MergeEligibilityService();

            if (!eligibility.eligible(pipeline)) {
                throw new PipelineException(
                        "Pipeline is not eligible for publication"
                );
            }

            pipeline.publish();
            printReport(pipeline);

            // Explicitly demonstrate a policy failure.
            Image unsafeImage = new Image(
                    "registry.example.com",
                    "platform/payments-api",
                    "latest",
                    null
            );

            PipelineRequest unsafeRequest = new PipelineRequest(
                    "payments-api",
                    "main",
                    "9c1e7f2",
                    unsafeImage,
                    true,
                    true,
                    true
            );

            try {
                Pipeline unsafePipeline =
                        new Pipeline(unsafeRequest, policies);
                unsafePipeline.build();
                unsafePipeline.test();
                unsafePipeline.scan();
            } catch (PipelineException expected) {
                System.out.println();
                System.out.println(
                        "Rejected policy scenario: " +
                        expected.getMessage()
                );
            }

        } catch (PipelineException exception) {
            System.err.println(
                    "Pipeline failure: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}

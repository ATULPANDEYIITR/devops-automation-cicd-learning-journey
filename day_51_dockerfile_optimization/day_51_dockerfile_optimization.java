import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/*
 * Enterprise Docker image governance model.
 *
 * The domain deliberately separates:
 * - image layers
 * - build-context policy
 * - dependency-cache policy
 * - runtime-image policy
 * - multi-stage build policy
 *
 * This models governance decisions that can be integrated into a CI build
 * gate before a container image is published.
 */
public class DockerfileOptimizationGovernance {

    enum LayerRole {
        BASE_RUNTIME,
        DEPENDENCIES,
        APPLICATION,
        CONFIGURATION,
        BUILD_TOOLING
    }

    enum Violation {
        IMAGE_TOO_LARGE,
        CONTEXT_TOO_LARGE,
        DEPENDENCIES_AFTER_APPLICATION,
        BUILD_TOOLING_IN_RUNTIME,
        UNSTABLE_DEPENDENCY_INPUT,
        EMPTY_LAYER
    }

    record ImageLayer(
            String name,
            double sizeMb,
            String cacheKey,
            LayerRole role
    ) {
        ImageLayer {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Layer name is required");
            }
            if (cacheKey == null || cacheKey.isBlank()) {
                throw new IllegalArgumentException("Cache key is required");
            }
            if (sizeMb < 0) {
                throw new IllegalArgumentException(
                        "Layer size cannot be negative"
                );
            }
            if (role == null) {
                throw new IllegalArgumentException("Layer role is required");
            }
        }
    }

    record BuildContext(
            double totalMb,
            double ignoredMb
    ) {
        BuildContext {
            if (totalMb < 0 || ignoredMb < 0 || ignoredMb > totalMb) {
                throw new IllegalArgumentException(
                        "Invalid build-context sizes"
                );
            }
        }

        double effectiveMb() {
            return totalMb - ignoredMb;
        }
    }

    record GovernancePolicy(
            double maximumImageMb,
            double maximumContextMb,
            boolean requireStableDependencyCache,
            boolean forbidBuildToolingInRuntime
    ) {
        GovernancePolicy {
            if (maximumImageMb <= 0 || maximumContextMb <= 0) {
                throw new IllegalArgumentException(
                        "Governance limits must be positive"
                );
            }
        }
    }

    record RepositoryImage(
            String repository,
            BuildContext context,
            List<ImageLayer> layers
    ) {
        RepositoryImage {
            if (repository == null || repository.isBlank()) {
                throw new IllegalArgumentException(
                        "Repository name is required"
                );
            }

            if (context == null || layers == null || layers.isEmpty()) {
                throw new IllegalArgumentException(
                        "Context and layers are required"
                );
            }

            layers = List.copyOf(layers);
        }

        double imageSizeMb() {
            return layers.stream()
                    .mapToDouble(ImageLayer::sizeMb)
                    .sum();
        }

        boolean hasBuildTooling() {
            return layers.stream()
                    .anyMatch(layer -> layer.role() == LayerRole.BUILD_TOOLING);
        }
    }

    record GovernanceReport(
            Set<Violation> violations,
            double imageSizeMb,
            double contextSizeMb
    ) {
        boolean accepted() {
            return violations.isEmpty();
        }
    }

    interface ImagePolicy {
        Set<Violation> evaluate(RepositoryImage image);
    }

    static final class EnterpriseImagePolicy implements ImagePolicy {
        private final GovernancePolicy policy;

        EnterpriseImagePolicy(GovernancePolicy policy) {
            this.policy = policy;
        }

        @Override
        public Set<Violation> evaluate(RepositoryImage image) {
            EnumSet<Violation> violations =
                    EnumSet.noneOf(Violation.class);

            if (image.imageSizeMb() > policy.maximumImageMb()) {
                violations.add(Violation.IMAGE_TOO_LARGE);
            }

            if (image.context().effectiveMb()
                    > policy.maximumContextMb()) {
                violations.add(Violation.CONTEXT_TOO_LARGE);
            }

            if (policy.forbidBuildToolingInRuntime()
                    && image.hasBuildTooling()) {
                violations.add(Violation.BUILD_TOOLING_IN_RUNTIME);
            }

            int dependencyIndex = -1;
            int applicationIndex = -1;

            for (int i = 0; i < image.layers().size(); i++) {
                LayerRole role = image.layers().get(i).role();

                if (role == LayerRole.DEPENDENCIES
                        && dependencyIndex == -1) {
                    dependencyIndex = i;
                }

                if (role == LayerRole.APPLICATION
                        && applicationIndex == -1) {
                    applicationIndex = i;
                }
            }

            if (policy.requireStableDependencyCache()
                    && dependencyIndex >= 0
                    && applicationIndex >= 0
                    && dependencyIndex > applicationIndex) {
                violations.add(
                        Violation.DEPENDENCIES_AFTER_APPLICATION
                );
            }

            boolean hasDependencyLayer = image.layers().stream()
                    .anyMatch(layer ->
                            layer.role() == LayerRole.DEPENDENCIES);

            boolean hasStableCacheKey = image.layers().stream()
                    .filter(layer ->
                            layer.role() == LayerRole.DEPENDENCIES)
                    .allMatch(layer ->
                            layer.cacheKey().contains("lock"));

            if (policy.requireStableDependencyCache()
                    && hasDependencyLayer
                    && !hasStableCacheKey) {
                violations.add(Violation.UNSTABLE_DEPENDENCY_INPUT);
            }

            return violations;
        }
    }

    static final class BuildPipeline {
        private final ImagePolicy policy;

        BuildPipeline(ImagePolicy policy) {
            this.policy = policy;
        }

        GovernanceReport validate(RepositoryImage image) {
            Set<Violation> violations = policy.evaluate(image);

            if (image.layers().stream().anyMatch(
                    layer -> layer.name().isBlank())) {
                violations = EnumSet.copyOf(violations);
                violations.add(Violation.EMPTY_LAYER);
            }

            return new GovernanceReport(
                    Set.copyOf(violations),
                    image.imageSizeMb(),
                    image.context().effectiveMb()
            );
        }
    }

    private static void printImage(RepositoryImage image) {
        System.out.println("\n" + image.repository());
        System.out.println("-".repeat(76));

        int index = 1;

        for (ImageLayer layer : image.layers()) {
            System.out.printf(
                    "%2d. %-34s %7.1f MB  role=%s  cache=%s%n",
                    index++,
                    layer.name(),
                    layer.sizeMb(),
                    layer.role(),
                    layer.cacheKey()
            );
        }

        System.out.printf(
                "Runtime image: %.1f MB%n",
                image.imageSizeMb()
        );

        System.out.printf(
                "Build context: %.1f MB%n",
                image.context().effectiveMb()
        );
    }

    private static void printReport(GovernanceReport report) {
        System.out.println("\nGOVERNANCE REPORT");
        System.out.println("-".repeat(76));

        if (report.accepted()) {
            System.out.println("[PASS] Image satisfies policy");
            return;
        }

        report.violations().stream()
                .sorted()
                .forEach(violation ->
                        System.out.println("[FAIL] " + violation));
    }

    public static void main(String[] args) {
        GovernancePolicy policy = new GovernancePolicy(
                180.0,
                150.0,
                true,
                true
        );

        RepositoryImage optimized = new RepositoryImage(
                "billing-service",
                new BuildContext(410.0, 280.0),
                List.of(
                        new ImageLayer(
                                "runtime base",
                                90.0,
                                "runtime-base",
                                LayerRole.BASE_RUNTIME
                        ),
                        new ImageLayer(
                                "locked production dependencies",
                                48.0,
                                "requirements-lock-v3",
                                LayerRole.DEPENDENCIES
                        ),
                        new ImageLayer(
                                "application source",
                                21.0,
                                "application-source",
                                LayerRole.APPLICATION
                        ),
                        new ImageLayer(
                                "runtime configuration",
                                4.0,
                                "runtime-config-v2",
                                LayerRole.CONFIGURATION
                        )
                )
        );

        RepositoryImage poorlyOptimized = new RepositoryImage(
                "billing-service-unsafe",
                new BuildContext(410.0, 80.0),
                List.of(
                        new ImageLayer(
                                "runtime base",
                                90.0,
                                "runtime-base",
                                LayerRole.BASE_RUNTIME
                        ),
                        new ImageLayer(
                                "application source",
                                21.0,
                                "application-source",
                                LayerRole.APPLICATION
                        ),
                        new ImageLayer(
                                "dependencies after source",
                                48.0,
                                "requirements-current",
                                LayerRole.DEPENDENCIES
                        ),
                        new ImageLayer(
                                "compiler and build tooling",
                                70.0,
                                "compiler-toolchain",
                                LayerRole.BUILD_TOOLING
                        )
                )
        );

        BuildPipeline pipeline =
                new BuildPipeline(
                        new EnterpriseImagePolicy(policy)
                );

        Map<String, RepositoryImage> images =
                new LinkedHashMap<>();

        images.put("optimized", optimized);
        images.put("poorly-optimized", poorlyOptimized);

        images.forEach((name, image) -> {
            System.out.println("\nPROFILE: " + name);
            printImage(image);
            printReport(pipeline.validate(image));
        });

        /*
         * Immutable domain records prevent policy evaluation from changing
         * repository image state while a CI gate is evaluating it.
         */
        System.out.println("\nCI GATE RESULT");
        System.out.println("-".repeat(76));

        GovernanceReport optimizedReport =
                pipeline.validate(optimized);

        if (!optimizedReport.accepted()) {
            throw new IllegalStateException(
                    "Optimized image unexpectedly failed governance"
            );
        }

        System.out.println(
                "billing-service is eligible for publication."
        );
    }
}

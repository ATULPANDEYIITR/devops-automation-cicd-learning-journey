import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Enterprise release verification with explicit test classifications,
 * immutable test results, state transitions, and policy-based deployment.
 *
 * Compile: javac TestingAutomation.java
 * Run:     java TestingAutomation
 */
public class TestingAutomation {

    enum TestType {
        UNIT,
        INTEGRATION,
        SMOKE,
        REGRESSION
    }

    enum TestStatus {
        PASSED,
        FAILED,
        SKIPPED
    }

    enum ReleaseState {
        CREATED,
        VALIDATING,
        TESTING,
        APPROVED,
        DEPLOYING,
        DEPLOYED,
        FAILED,
        ROLLED_BACK
    }

    record TestResult(
            String testId,
            TestType type,
            TestStatus status,
            boolean critical,
            String detail,
            long durationMillis,
            Instant completedAt) {

        TestResult {
            Objects.requireNonNull(testId, "testId");
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(status, "status");
            Objects.requireNonNull(detail, "detail");
            Objects.requireNonNull(completedAt, "completedAt");

            if (testId.isBlank()) {
                throw new IllegalArgumentException("Test ID cannot be blank.");
            }
            if (durationMillis < 0) {
                throw new IllegalArgumentException("Duration cannot be negative.");
            }
        }
    }

    record TestDefinition(
            String id,
            TestType type,
            boolean critical,
            Predicate<ReleaseContext> assertion) {

        TestDefinition {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(assertion, "assertion");

            if (id.isBlank()) {
                throw new IllegalArgumentException("Test ID cannot be blank.");
            }
        }

        TestResult execute(ReleaseContext context) {
            long started = System.nanoTime();
            try {
                boolean passed = assertion.test(context);
                return new TestResult(
                        id,
                        type,
                        passed ? TestStatus.PASSED : TestStatus.FAILED,
                        critical,
                        passed ? "Assertion satisfied" : "Assertion returned false",
                        (System.nanoTime() - started) / 1_000_000,
                        Instant.now());
            } catch (RuntimeException exception) {
                return new TestResult(
                        id,
                        type,
                        TestStatus.FAILED,
                        critical,
                        exception.getClass().getSimpleName() + ": "
                                + exception.getMessage(),
                        (System.nanoTime() - started) / 1_000_000,
                        Instant.now());
            }
        }
    }

    static final class ReleaseContext {
        private final String releaseId;
        private final String environment;
        private final Map<String, Object> attributes;

        ReleaseContext(String releaseId, String environment,
                       Map<String, Object> attributes) {
            if (releaseId == null || releaseId.isBlank()) {
                throw new IllegalArgumentException("Release ID is required.");
            }
            if (environment == null || environment.isBlank()) {
                throw new IllegalArgumentException("Environment is required.");
            }
            this.releaseId = releaseId;
            this.environment = environment;
            this.attributes = Map.copyOf(attributes);
        }

        String releaseId() {
            return releaseId;
        }

        String environment() {
            return environment;
        }

        Object attribute(String name) {
            if (!attributes.containsKey(name)) {
                throw new IllegalArgumentException("Missing release attribute: " + name);
            }
            return attributes.get(name);
        }

        boolean booleanAttribute(String name) {
            Object value = attribute(name);
            if (!(value instanceof Boolean result)) {
                throw new IllegalArgumentException(
                        "Release attribute must be boolean: " + name);
            }
            return result;
        }

        long longAttribute(String name) {
            Object value = attribute(name);
            if (!(value instanceof Number number)) {
                throw new IllegalArgumentException(
                        "Release attribute must be numeric: " + name);
            }
            return number.longValue();
        }
    }

    record QualityPolicy(
            Set<TestType> requiredTypes,
            int minimumTestsPerType,
            boolean failOnSkippedCriticalTests) {

        QualityPolicy {
            requiredTypes = Set.copyOf(requiredTypes);
            if (minimumTestsPerType < 1) {
                throw new IllegalArgumentException(
                        "At least one test per required type is necessary.");
            }
        }

        List<String> violations(List<TestResult> results) {
            List<String> problems = new ArrayList<>();

            for (TestType required : requiredTypes) {
                List<TestResult> matching = results.stream()
                        .filter(result -> result.type() == required)
                        .toList();

                if (matching.size() < minimumTestsPerType) {
                    problems.add("Insufficient " + required
                            + " tests: found " + matching.size());
                }

                long passed = matching.stream()
                        .filter(result -> result.status() == TestStatus.PASSED)
                        .count();

                if (passed < minimumTestsPerType) {
                    problems.add("Required " + required
                            + " test threshold not satisfied.");
                }
            }

            for (TestResult result : results) {
                if (result.critical() && result.status() == TestStatus.FAILED) {
                    problems.add("Critical test failed: " + result.testId());
                }
                if (failOnSkippedCriticalTests
                        && result.critical()
                        && result.status() == TestStatus.SKIPPED) {
                    problems.add("Critical test was skipped: " + result.testId());
                }
            }

            return List.copyOf(problems);
        }
    }

    static final class TestCatalog {
        private final Map<String, TestDefinition> definitions = new HashMap<>();

        void register(TestDefinition definition) {
            Objects.requireNonNull(definition, "definition");
            if (definitions.putIfAbsent(definition.id(), definition) != null) {
                throw new IllegalArgumentException(
                        "Duplicate test definition: " + definition.id());
            }
        }

        List<TestResult> executeAll(ReleaseContext context) {
            return definitions.values().stream()
                    .sorted((left, right) -> left.id().compareTo(right.id()))
                    .map(definition -> definition.execute(context))
                    .toList();
        }

        int size() {
            return definitions.size();
        }
    }

    static final class Release {
        private static final Map<ReleaseState, Set<ReleaseState>> TRANSITIONS =
                buildTransitions();

        private final String id;
        private ReleaseState state = ReleaseState.CREATED;
        private final List<String> auditTrail = new ArrayList<>();

        Release(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Release ID cannot be blank.");
            }
            this.id = id;
            auditTrail.add(Instant.now() + " CREATED");
        }

        private static Map<ReleaseState, Set<ReleaseState>> buildTransitions() {
            Map<ReleaseState, Set<ReleaseState>> transitions =
                    new EnumMap<>(ReleaseState.class);

            transitions.put(ReleaseState.CREATED,
                    Set.of(ReleaseState.VALIDATING, ReleaseState.FAILED));
            transitions.put(ReleaseState.VALIDATING,
                    Set.of(ReleaseState.TESTING, ReleaseState.FAILED));
            transitions.put(ReleaseState.TESTING,
                    Set.of(ReleaseState.APPROVED, ReleaseState.FAILED));
            transitions.put(ReleaseState.APPROVED,
                    Set.of(ReleaseState.DEPLOYING, ReleaseState.FAILED));
            transitions.put(ReleaseState.DEPLOYING,
                    Set.of(ReleaseState.DEPLOYED, ReleaseState.FAILED,
                            ReleaseState.ROLLED_BACK));
            transitions.put(ReleaseState.FAILED,
                    Set.of(ReleaseState.ROLLED_BACK));
            transitions.put(ReleaseState.DEPLOYED, Set.of());
            transitions.put(ReleaseState.ROLLED_BACK, Set.of());
            return Map.copyOf(transitions);
        }

        void transition(ReleaseState next) {
            Set<ReleaseState> permitted = TRANSITIONS.getOrDefault(state, Set.of());
            if (!permitted.contains(next)) {
                throw new IllegalStateException(
                        "Invalid release transition: " + state + " -> " + next);
            }
            state = next;
            auditTrail.add(Instant.now() + " " + next);
        }

        ReleaseState state() {
            return state;
        }

        List<String> auditTrail() {
            return List.copyOf(auditTrail);
        }

        String id() {
            return id;
        }
    }

    static final class ReleaseService {
        private final TestCatalog catalog;
        private final QualityPolicy policy;

        ReleaseService(TestCatalog catalog, QualityPolicy policy) {
            this.catalog = Objects.requireNonNull(catalog);
            this.policy = Objects.requireNonNull(policy);
        }

        List<TestResult> verify(ReleaseContext context) {
            return catalog.executeAll(context);
        }

        List<String> evaluate(List<TestResult> results) {
            return policy.violations(results);
        }

        void deploy(Release release, ReleaseContext context,
                    List<TestResult> results) {
            release.transition(ReleaseState.VALIDATING);

            if (!context.environment().equals("staging")) {
                release.transition(ReleaseState.FAILED);
                throw new IllegalStateException(
                        "This release exercise only permits staging deployment.");
            }

            release.transition(ReleaseState.TESTING);
            List<String> violations = policy.violations(results);
            if (!violations.isEmpty()) {
                release.transition(ReleaseState.FAILED);
                throw new IllegalStateException(String.join("; ", violations));
            }

            release.transition(ReleaseState.APPROVED);
            release.transition(ReleaseState.DEPLOYING);

            // Real deployment code would verify the active version after
            // rollout and enter ROLLED_BACK if health checks failed.
            if (!context.booleanAttribute("artifactSigned")) {
                release.transition(ReleaseState.FAILED);
                throw new SecurityException("Release artifact is not signed.");
            }

            release.transition(ReleaseState.DEPLOYED);
        }
    }

    private static TestCatalog createCatalog() {
        TestCatalog catalog = new TestCatalog();

        catalog.register(new TestDefinition(
                "unit:price-calculation",
                TestType.UNIT,
                true,
                context -> context.longAttribute("priceCents") * 3 == 26997L));

        catalog.register(new TestDefinition(
                "unit:input-validation",
                TestType.UNIT,
                true,
                context -> context.longAttribute("minimumQuantity") > 0));

        catalog.register(new TestDefinition(
                "integration:database-migration",
                TestType.INTEGRATION,
                true,
                context -> context.booleanAttribute("migrationVerified")));

        catalog.register(new TestDefinition(
                "smoke:health-endpoint",
                TestType.SMOKE,
                true,
                context -> context.booleanAttribute("healthEndpointResponding")));

        catalog.register(new TestDefinition(
                "regression:duplicate-order",
                TestType.REGRESSION,
                true,
                context -> context.booleanAttribute("duplicateOrderRejected")));

        return catalog;
    }

    private static ReleaseContext validContext() {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("priceCents", 8999L);
        attributes.put("minimumQuantity", 1L);
        attributes.put("migrationVerified", true);
        attributes.put("healthEndpointResponding", true);
        attributes.put("duplicateOrderRejected", true);
        attributes.put("artifactSigned", true);

        return new ReleaseContext(
                "release-" + UUID.randomUUID(),
                "staging",
                attributes);
    }

    public static void main(String[] args) {
        TestCatalog catalog = createCatalog();

        QualityPolicy policy = new QualityPolicy(
                new HashSet<>(Set.of(
                        TestType.UNIT,
                        TestType.INTEGRATION,
                        TestType.SMOKE,
                        TestType.REGRESSION)),
                1,
                true);

        ReleaseService service = new ReleaseService(catalog, policy);
        ReleaseContext context = validContext();
        Release release = new Release(context.releaseId());

        List<TestResult> results = service.verify(context);
        System.out.println("Release: " + context.releaseId());
        System.out.println("Environment: " + context.environment());

        results.forEach(result -> System.out.printf(
                "%-34s %-12s %4d ms  %s%n",
                result.testId(),
                result.status(),
                result.durationMillis(),
                result.detail()));

        List<String> violations = service.evaluate(results);
        if (!violations.isEmpty()) {
            violations.forEach(problem -> System.err.println("BLOCKED: " + problem));
            return;
        }

        try {
            service.deploy(release, context, results);
            System.out.println("Release state: " + release.state());
        } catch (RuntimeException exception) {
            System.err.println("Release blocked: " + exception.getMessage());
            if (release.state() == ReleaseState.FAILED) {
                release.transition(ReleaseState.ROLLED_BACK);
                System.err.println("Release state: " + release.state());
            }
        }

        System.out.println("\nAudit trail");
        release.auditTrail().forEach(System.out::println);

        System.out.println("\nTest classification");
        Map<TestType, Long> totals = results.stream().collect(
                Collectors.groupingBy(
                        TestResult::type,
                        () -> new EnumMap<>(TestType.class),
                        Collectors.counting()));
        totals.forEach((type, count) ->
                System.out.println(type + ": " + count + " executed"));

        // A separate unsigned-artifact scenario demonstrates that passing
        // tests do not override a deployment security control.
        Map<String, Object> unsignedAttributes = new HashMap<>();
        unsignedAttributes.put("priceCents", 8999L);
        unsignedAttributes.put("minimumQuantity", 1L);
        unsignedAttributes.put("migrationVerified", true);
        unsignedAttributes.put("healthEndpointResponding", true);
        unsignedAttributes.put("duplicateOrderRejected", true);
        unsignedAttributes.put("artifactSigned", false);

        ReleaseContext unsigned = new ReleaseContext(
                "release-unsigned",
                "staging",
                unsignedAttributes);
        Release unsignedRelease = new Release(unsigned.releaseId());

        try {
            service.deploy(unsignedRelease, unsigned, service.verify(unsigned));
        } catch (SecurityException expected) {
            System.out.println("\nPASS: unsigned artifact rejected.");
            if (unsignedRelease.state() == ReleaseState.FAILED) {
                unsignedRelease.transition(ReleaseState.ROLLED_BACK);
            }
            System.out.println("Unsigned release state: " + unsignedRelease.state());
        }
    }
}

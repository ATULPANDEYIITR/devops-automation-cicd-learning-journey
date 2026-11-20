import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/*
 * Infrastructure as Code: Enterprise Infrastructure Governance
 *
 * Java 17 implementation.
 *
 * Includes:
 * - Immutable resource specifications
 * - Explicit infrastructure domain types
 * - Dependency validation
 * - Declarative configuration
 * - Policy-based infrastructure governance
 * - Deployment planning
 * - Approval and execution boundaries
 * - Resource lifecycle management
 * - State transitions
 * - Drift detection
 * - Idempotent reconciliation
 * - Failure recovery
 */

public class InfrastructureAsCode {

    enum ResourceType {
        NETWORK,
        SERVER,
        STORAGE,
        FIREWALL
    }

    enum ResourceStatus {
        DECLARED,
        ACTIVE,
        FAILED
    }

    enum DeploymentAction {
        CREATE,
        UPDATE,
        DELETE,
        NO_OP
    }

    record ResourceSpec(
        String id,
        ResourceType type,
        Map<String, String> properties,
        List<String> dependencies,
        boolean protectedResource
    ) {
        ResourceSpec {
            if (id == null || !id.matches("[a-z][a-z0-9-]{2,62}")) {
                throw new ValidationException("Invalid resource ID");
            }

            Objects.requireNonNull(type, "Resource type is required");
            Objects.requireNonNull(properties);
            Objects.requireNonNull(dependencies);

            properties = Collections.unmodifiableMap(
                new LinkedHashMap<>(properties)
            );

            dependencies = List.copyOf(dependencies);

            if (dependencies.contains(id)) {
                throw new ValidationException(
                    "A resource cannot depend on itself"
                );
            }

            if (new HashSet<>(dependencies).size() != dependencies.size()) {
                throw new ValidationException(
                    "Duplicate dependencies detected"
                );
            }

            validateProperties(type, properties);
        }

        private static void validateProperties(
            ResourceType type,
            Map<String, String> properties
        ) {
            switch (type) {
                case SERVER -> {
                    int cpu = parsePositive(properties, "cpu");
                    int memory = parsePositive(properties, "memory_gb");

                    if (cpu > 256 || memory > 4096) {
                        throw new ValidationException(
                            "Server capacity exceeds configured limits"
                        );
                    }
                }

                case STORAGE -> {
                    parsePositive(properties, "size_gb");

                    if (!"true".equals(properties.get("encrypted"))) {
                        throw new ValidationException(
                            "Storage encryption is mandatory"
                        );
                    }
                }

                case NETWORK -> {
                    if (!properties.containsKey("cidr")) {
                        throw new ValidationException(
                            "Network CIDR is required"
                        );
                    }
                }

                case FIREWALL -> {
                    if (!properties.containsKey("default_action")) {
                        throw new ValidationException(
                            "Firewall default action is required"
                        );
                    }
                }
            }
        }

        private static int parsePositive(
            Map<String, String> properties,
            String key
        ) {
            try {
                int value = Integer.parseInt(properties.get(key));

                if (value <= 0) {
                    throw new ValidationException(
                        key + " must be positive"
                    );
                }

                return value;

            } catch (NumberFormatException | NullPointerException exception) {
                throw new ValidationException(
                    "Invalid numeric property: " + key
                );
            }
        }
    }

    record ActualResource(
        ResourceSpec specification,
        ResourceStatus status,
        Instant lastUpdated,
        String providerReference
    ) {}

    record PlanItem(
        String resourceId,
        DeploymentAction action,
        String reason
    ) {}

    record PolicyViolation(
        String resourceId,
        String policyName,
        String explanation
    ) {}

    record DeploymentReport(
        long revision,
        int resourceCount,
        List<PlanItem> actions,
        Instant completedAt
    ) {
        DeploymentReport {
            actions = List.copyOf(actions);
        }
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    static class ValidationException extends InfrastructureException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class PolicyException extends InfrastructureException {
        PolicyException(String message) {
            super(message);
        }
    }

    static class DeploymentException extends InfrastructureException {
        DeploymentException(String message) {
            super(message);
        }
    }

    interface InfrastructurePolicy {
        List<PolicyViolation> evaluate(
            Map<String, ResourceSpec> resources
        );
    }

    static final class SecurityPolicy implements InfrastructurePolicy {

        @Override
        public List<PolicyViolation> evaluate(
            Map<String, ResourceSpec> resources
        ) {
            List<PolicyViolation> violations = new ArrayList<>();

            for (ResourceSpec resource : resources.values()) {
                Map<String, String> properties = resource.properties();

                if (
                    resource.type() == ResourceType.STORAGE &&
                    !"true".equals(properties.get("encrypted"))
                ) {
                    violations.add(new PolicyViolation(
                        resource.id(),
                        "STORAGE_ENCRYPTION",
                        "Storage encryption is required"
                    ));
                }

                if (
                    resource.type() == ResourceType.FIREWALL &&
                    !"DENY".equals(properties.get("default_action"))
                ) {
                    violations.add(new PolicyViolation(
                        resource.id(),
                        "DEFAULT_DENY",
                        "Firewall must deny traffic by default"
                    ));
                }

                if (
                    resource.type() == ResourceType.SERVER &&
                    "true".equals(properties.get("public_ssh"))
                ) {
                    violations.add(new PolicyViolation(
                        resource.id(),
                        "PUBLIC_SSH",
                        "Public SSH access is prohibited"
                    ));
                }

                if (
                    resource.type() == ResourceType.NETWORK &&
                    properties.containsKey("public") &&
                    "true".equals(properties.get("public")) &&
                    !"true".equals(properties.get("internet_gateway"))
                ) {
                    violations.add(new PolicyViolation(
                        resource.id(),
                        "PUBLIC_NETWORK",
                        "Public network requires an explicit gateway"
                    ));
                }
            }

            return List.copyOf(violations);
        }
    }

    static final class InfrastructureDefinition {

        private final Map<String, ResourceSpec> resources =
            new LinkedHashMap<>();

        public void add(ResourceSpec resource) {
            if (resources.containsKey(resource.id())) {
                throw new ValidationException(
                    "Duplicate resource: " + resource.id()
                );
            }

            resources.put(resource.id(), resource);
        }

        public Map<String, ResourceSpec> resources() {
            return Collections.unmodifiableMap(resources);
        }

        public List<String> deploymentOrder() {
            Map<String, Integer> indegree = new HashMap<>();
            Map<String, List<String>> dependents = new HashMap<>();

            for (String id : resources.keySet()) {
                indegree.put(id, 0);
                dependents.put(id, new ArrayList<>());
            }

            for (ResourceSpec resource : resources.values()) {
                for (String dependency : resource.dependencies()) {
                    if (!resources.containsKey(dependency)) {
                        throw new ValidationException(
                            resource.id() +
                            " depends on missing resource " + dependency
                        );
                    }

                    indegree.merge(resource.id(), 1, Integer::sum);
                    dependents.get(dependency).add(resource.id());
                }
            }

            TreeSet<String> ready = new TreeSet<>();

            for (var entry : indegree.entrySet()) {
                if (entry.getValue() == 0) {
                    ready.add(entry.getKey());
                }
            }

            List<String> result = new ArrayList<>();

            while (!ready.isEmpty()) {
                String current = ready.pollFirst();
                result.add(current);

                for (String dependent : dependents.get(current)) {
                    int remaining = indegree.merge(
                        dependent,
                        -1,
                        Integer::sum
                    );

                    if (remaining == 0) {
                        ready.add(dependent);
                    }
                }
            }

            if (result.size() != resources.size()) {
                throw new ValidationException(
                    "Circular dependency detected"
                );
            }

            return List.copyOf(result);
        }
    }

    static final class InfrastructureState {

        private final Map<String, ActualResource> actual =
            new LinkedHashMap<>();

        private long revision;

        public Map<String, ActualResource> snapshot() {
            return new LinkedHashMap<>(actual);
        }

        public long revision() {
            return revision;
        }

        public int size() {
            return actual.size();
        }

        public void externallyModify(
            String resourceId,
            String property,
            String value
        ) {
            ActualResource existing = actual.get(resourceId);

            if (existing == null) {
                throw new ValidationException(
                    "Unknown resource: " + resourceId
                );
            }

            Map<String, String> changedProperties =
                new HashMap<>(existing.specification().properties());

            changedProperties.put(property, value);

            ResourceSpec changed = new ResourceSpec(
                existing.specification().id(),
                existing.specification().type(),
                changedProperties,
                existing.specification().dependencies(),
                existing.specification().protectedResource()
            );

            actual.put(
                resourceId,
                new ActualResource(
                    changed,
                    ResourceStatus.ACTIVE,
                    Instant.now(),
                    existing.providerReference()
                )
            );
        }

        private void restore(
            Map<String, ActualResource> snapshot,
            long oldRevision
        ) {
            actual.clear();
            actual.putAll(snapshot);
            revision = oldRevision;
        }
    }

    static final class InfrastructurePlanner {

        private final InfrastructureDefinition definition;
        private final InfrastructureState state;

        InfrastructurePlanner(
            InfrastructureDefinition definition,
            InfrastructureState state
        ) {
            this.definition = definition;
            this.state = state;
        }

        public List<PlanItem> createPlan() {
            List<PlanItem> plan = new ArrayList<>();

            Map<String, ResourceSpec> desired =
                definition.resources();

            Map<String, ActualResource> actual =
                state.snapshot();

            for (String id : definition.deploymentOrder()) {
                ResourceSpec target = desired.get(id);
                ActualResource current = actual.get(id);

                if (current == null) {
                    plan.add(new PlanItem(
                        id,
                        DeploymentAction.CREATE,
                        "Resource does not exist"
                    ));

                } else if (
                    !target.properties().equals(
                        current.specification().properties()
                    )
                ) {
                    plan.add(new PlanItem(
                        id,
                        DeploymentAction.UPDATE,
                        "Desired and actual properties differ"
                    ));

                } else {
                    plan.add(new PlanItem(
                        id,
                        DeploymentAction.NO_OP,
                        "Resource is already compliant"
                    ));
                }
            }

            for (var entry : actual.entrySet()) {
                if (!desired.containsKey(entry.getKey())) {
                    if (
                        entry.getValue()
                            .specification()
                            .protectedResource()
                    ) {
                        throw new PolicyException(
                            "Protected resource cannot be removed: " +
                            entry.getKey()
                        );
                    }

                    plan.add(new PlanItem(
                        entry.getKey(),
                        DeploymentAction.DELETE,
                        "Resource removed from declaration"
                    ));
                }
            }

            validateDeletionDependencies(plan, actual);

            return List.copyOf(plan);
        }

        private void validateDeletionDependencies(
            List<PlanItem> plan,
            Map<String, ActualResource> actual
        ) {
            Set<String> deleting = new HashSet<>();

            for (PlanItem item : plan) {
                if (item.action() == DeploymentAction.DELETE) {
                    deleting.add(item.resourceId());
                }
            }

            for (String id : deleting) {
                for (var entry : actual.entrySet()) {
                    if (
                        !entry.getKey().equals(id) &&
                        entry.getValue()
                            .specification()
                            .dependencies()
                            .contains(id) &&
                        !deleting.contains(entry.getKey())
                    ) {
                        throw new PolicyException(
                            id + " is still required by " + entry.getKey()
                        );
                    }
                }
            }
        }
    }

    static final class DeploymentService {

        private final InfrastructureState state;
        private boolean deploymentRunning;

        DeploymentService(InfrastructureState state) {
            this.state = state;
        }

        public synchronized DeploymentReport apply(
            List<PlanItem> plan,
            InfrastructureDefinition definition,
            InfrastructurePolicy policy
        ) {
            if (deploymentRunning) {
                throw new DeploymentException(
                    "Concurrent deployment is not permitted"
                );
            }

            deploymentRunning = true;

            Map<String, ActualResource> snapshot = state.snapshot();
            long oldRevision = state.revision();

            try {
                List<PolicyViolation> violations =
                    policy.evaluate(definition.resources());

                if (!violations.isEmpty()) {
                    throw new PolicyException(
                        "Deployment rejected: " + violations
                    );
                }

                // Provision in dependency order.
                for (PlanItem item : plan) {
                    if (
                        item.action() == DeploymentAction.CREATE ||
                        item.action() == DeploymentAction.UPDATE
                    ) {
                        ResourceSpec specification =
                            definition.resources().get(item.resourceId());

                        if (
                            specification.properties()
                                .containsKey("simulate_failure") &&
                            "true".equals(
                                specification.properties()
                                    .get("simulate_failure")
                            )
                        ) {
                            throw new DeploymentException(
                                "Provider failed for " + item.resourceId()
                            );
                        }

                        state.actual.put(
                            item.resourceId(),
                            new ActualResource(
                                specification,
                                ResourceStatus.ACTIVE,
                                Instant.now(),
                                "provider-" + item.resourceId()
                            )
                        );
                    }
                }

                // Delete in reverse dependency order.
                List<PlanItem> reversed = new ArrayList<>(plan);
                Collections.reverse(reversed);

                for (PlanItem item : reversed) {
                    if (item.action() == DeploymentAction.DELETE) {
                        state.actual.remove(item.resourceId());
                    }
                }

                boolean changed = plan.stream().anyMatch(
                    item -> item.action() != DeploymentAction.NO_OP
                );

                if (changed) {
                    state.revision++;
                }

                return new DeploymentReport(
                    state.revision,
                    state.size(),
                    plan,
                    Instant.now()
                );

            } catch (RuntimeException exception) {
                state.restore(snapshot, oldRevision);

                if (exception instanceof InfrastructureException) {
                    throw exception;
                }

                throw new DeploymentException(
                    "Deployment failed: " + exception.getMessage()
                );

            } finally {
                deploymentRunning = false;
            }
        }
    }

    static InfrastructureDefinition buildInfrastructure() {
        InfrastructureDefinition definition =
            new InfrastructureDefinition();

        definition.add(new ResourceSpec(
            "production-network",
            ResourceType.NETWORK,
            Map.of(
                "cidr", "10.20.0.0/16",
                "region", "ap-south-1"
            ),
            List.of(),
            true
        ));

        definition.add(new ResourceSpec(
            "application-server",
            ResourceType.SERVER,
            Map.of(
                "cpu", "4",
                "memory_gb", "16",
                "public_ssh", "false",
                "image", "ubuntu-24.04"
            ),
            List.of("production-network"),
            false
        ));

        definition.add(new ResourceSpec(
            "application-storage",
            ResourceType.STORAGE,
            Map.of(
                "size_gb", "100",
                "encrypted", "true"
            ),
            List.of(),
            true
        ));

        definition.add(new ResourceSpec(
            "application-firewall",
            ResourceType.FIREWALL,
            Map.of(
                "default_action", "DENY",
                "allow_https", "true"
            ),
            List.of("production-network"),
            false
        ));

        return definition;
    }

    static void runTests() {
        InfrastructureDefinition definition = buildInfrastructure();

        InfrastructureState state = new InfrastructureState();
        InfrastructurePlanner planner =
            new InfrastructurePlanner(definition, state);

        InfrastructurePolicy policy = new SecurityPolicy();
        DeploymentService deployment = new DeploymentService(state);

        List<PlanItem> firstPlan = planner.createPlan();

        if (firstPlan.size() != 4) {
            throw new AssertionError("Initial plan test failed");
        }

        deployment.apply(firstPlan, definition, policy);

        if (state.size() != 4) {
            throw new AssertionError("Deployment test failed");
        }

        List<PlanItem> secondPlan = planner.createPlan();

        if (secondPlan.stream().anyMatch(
            item -> item.action() != DeploymentAction.NO_OP
        )) {
            throw new AssertionError("Idempotency test failed");
        }

        state.externallyModify(
            "application-server",
            "cpu",
            "8"
        );

        List<PlanItem> driftPlan = planner.createPlan();

        boolean updateDetected = driftPlan.stream().anyMatch(
            item ->
                item.resourceId().equals("application-server") &&
                item.action() == DeploymentAction.UPDATE
        );

        if (!updateDetected) {
            throw new AssertionError("Drift detection failed");
        }

        deployment.apply(driftPlan, definition, policy);

        if (planner.createPlan().stream().anyMatch(
            item -> item.action() != DeploymentAction.NO_OP
        )) {
            throw new AssertionError("Reconciliation failed");
        }

        // Provider failure must restore the previous state.
        InfrastructureDefinition failing =
            new InfrastructureDefinition();

        failing.add(new ResourceSpec(
            "failed-server",
            ResourceType.SERVER,
            Map.of(
                "cpu", "4",
                "memory_gb", "8",
                "simulate_failure", "true"
            ),
            List.of(),
            false
        ));

        int originalSize = state.size();

        try {
            new DeploymentService(state).apply(
                List.of(new PlanItem(
                    "failed-server",
                    DeploymentAction.CREATE,
                    "Test failure"
                )),
                failing,
                policy
            );

            throw new AssertionError("Failure test did not trigger");

        } catch (DeploymentException expected) {
            if (state.size() != originalSize) {
                throw new AssertionError("Rollback failed");
            }
        }

        System.out.println("All Java 17 tests passed.");
    }

    public static void main(String[] args) {
        try {
            InfrastructureDefinition definition =
                buildInfrastructure();

            InfrastructureState state =
                new InfrastructureState();

            InfrastructurePolicy policy =
                new SecurityPolicy();

            InfrastructurePlanner planner =
                new InfrastructurePlanner(definition, state);

            DeploymentService deployment =
                new DeploymentService(state);

            List<PlanItem> plan = planner.createPlan();

            System.out.println("INFRASTRUCTURE DEPLOYMENT PLAN");

            for (PlanItem item : plan) {
                System.out.printf(
                    "%-8s %-25s %s%n",
                    item.action(),
                    item.resourceId(),
                    item.reason()
                );
            }

            DeploymentReport report =
                deployment.apply(plan, definition, policy);

            System.out.println("\nDEPLOYMENT REPORT");
            System.out.println("Revision: " + report.revision());
            System.out.println("Resources: " + report.resourceCount());
            System.out.println("Completed: " + report.completedAt());

            System.out.println("\nIDEMPOTENCY CHECK");

            for (PlanItem item : planner.createPlan()) {
                System.out.println(
                    item.action() + " " + item.resourceId()
                );
            }

            runTests();

        } catch (InfrastructureException exception) {
            System.err.println(
                "Infrastructure failure: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}

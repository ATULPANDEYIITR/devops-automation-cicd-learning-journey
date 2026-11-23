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
import java.util.TreeMap;

/**
 * Terraform Modules: Enterprise reusable infrastructure governance.
 *
 * Java 17 implementation featuring:
 * - Typed module contracts
 * - Immutable module releases
 * - Semantic version management
 * - Module registry
 * - Dependency resolution
 * - Input validation
 * - Infrastructure planning
 * - Deployment approval policies
 * - Security and automated check enforcement
 * - State transitions
 * - Atomic deployment operations
 */

public class TerraformModules {

    enum DeploymentStatus {
        PENDING,
        VALIDATING,
        PLANNING,
        APPLYING,
        SUCCEEDED,
        FAILED
    }

    enum ReviewDecision {
        APPROVED,
        CHANGES_REQUESTED,
        COMMENTED
    }

    enum ResourceAction {
        CREATE,
        UPDATE,
        NO_CHANGE
    }

    enum InputType {
        STRING,
        INTEGER,
        BOOLEAN
    }

    static class ModuleException extends RuntimeException {
        ModuleException(String message) {
            super(message);
        }
    }

    static class ValidationException extends ModuleException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class GovernanceException extends ModuleException {
        GovernanceException(String message) {
            super(message);
        }
    }

    record Version(int major, int minor, int patch)
            implements Comparable<Version> {

        Version {
            if (major < 0 || minor < 0 || patch < 0) {
                throw new ValidationException(
                    "Version components cannot be negative."
                );
            }
        }

        @Override
        public int compareTo(Version other) {
            int result = Integer.compare(major, other.major);

            if (result != 0) return result;

            result = Integer.compare(minor, other.minor);

            if (result != 0) return result;

            return Integer.compare(patch, other.patch);
        }

        @Override
        public String toString() {
            return major + "." + minor + "." + patch;
        }
    }

    record InputDefinition(
        String name,
        InputType type,
        boolean required,
        Object defaultValue,
        Set<String> allowedValues
    ) {
        InputDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);

            allowedValues = Set.copyOf(allowedValues);
        }

        Object validate(Object value) {
            if (value == null) {
                if (required) {
                    throw new ValidationException(
                        "Missing required input: " + name
                    );
                }

                return defaultValue;
            }

            boolean valid = switch (type) {
                case STRING -> value instanceof String;
                case INTEGER -> value instanceof Integer;
                case BOOLEAN -> value instanceof Boolean;
            };

            if (!valid) {
                throw new ValidationException(
                    "Invalid input type: " + name
                );
            }

            if (
                !allowedValues.isEmpty() &&
                !allowedValues.contains(value.toString())
            ) {
                throw new ValidationException(
                    "Input value is not permitted: " + name
                );
            }

            return value;
        }
    }

    record ResourceDefinition(
        String name,
        String type,
        Map<String, String> configuration
    ) {
        ResourceDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);

            configuration = Map.copyOf(configuration);
        }
    }

    record OutputDefinition(
        String name,
        boolean sensitive
    ) {}

    record ModuleRelease(
        String name,
        Version version,
        String source,
        String checksum,
        Map<String, InputDefinition> inputs,
        Map<String, OutputDefinition> outputs,
        List<ResourceDefinition> resources,
        List<String> dependencies
    ) {
        ModuleRelease {
            Objects.requireNonNull(name);
            Objects.requireNonNull(version);
            Objects.requireNonNull(source);
            Objects.requireNonNull(checksum);

            if (name.isBlank() || source.isBlank()) {
                throw new ValidationException(
                    "Module name and source are required."
                );
            }

            if (!checksum.matches("[a-fA-F0-9]{64}")) {
                throw new ValidationException(
                    "A SHA-256 module checksum is required."
                );
            }

            inputs = Map.copyOf(inputs);
            outputs = Map.copyOf(outputs);
            resources = List.copyOf(resources);
            dependencies = List.copyOf(dependencies);
        }

        Map<String, Object> validateInputs(
            Map<String, Object> supplied
        ) {
            for (String name : supplied.keySet()) {
                if (!inputs.containsKey(name)) {
                    throw new ValidationException(
                        "Unknown module input: " + name
                    );
                }
            }

            Map<String, Object> resolved = new LinkedHashMap<>();

            for (var entry : inputs.entrySet()) {
                resolved.put(
                    entry.getKey(),
                    entry.getValue().validate(
                        supplied.get(entry.getKey())
                    )
                );
            }

            return Collections.unmodifiableMap(resolved);
        }
    }

    record ModuleCall(
        String instance,
        String moduleName,
        Version version,
        Map<String, Object> inputs
    ) {
        ModuleCall {
            Objects.requireNonNull(instance);
            Objects.requireNonNull(moduleName);
            Objects.requireNonNull(version);

            inputs = Map.copyOf(inputs);
        }
    }

    record Review(
        String reviewer,
        ReviewDecision decision
    ) {}

    record StatusCheck(
        String name,
        boolean passed
    ) {}

    record DeploymentRequest(
        String id,
        String environment,
        List<Review> reviews,
        List<StatusCheck> checks,
        int unresolvedDiscussions,
        boolean sourcePinned,
        boolean authorized
    ) {
        DeploymentRequest {
            reviews = List.copyOf(reviews);
            checks = List.copyOf(checks);
        }
    }

    record BranchPolicy(
        int requiredApprovals,
        boolean requireChecks,
        boolean requirePinnedSource,
        boolean requireResolvedDiscussions
    ) {
        BranchPolicy {
            if (requiredApprovals < 1) {
                throw new ValidationException(
                    "At least one approval is required."
                );
            }
        }
    }

    record PlannedResource(
        String address,
        ResourceAction action,
        Map<String, String> configuration
    ) {}

    record DeploymentResult(
        String id,
        DeploymentStatus status,
        int resourceCount,
        Instant completedAt
    ) {}

    static class ModuleRegistry {
        private final Map<String, TreeMap<Version, ModuleRelease>>
            releases = new HashMap<>();

        void register(ModuleRelease release) {
            TreeMap<Version, ModuleRelease> versions =
                releases.computeIfAbsent(
                    release.name(),
                    ignored -> new TreeMap<>()
                );

            if (versions.putIfAbsent(
                release.version(), release
            ) != null) {
                throw new ValidationException(
                    "Module version already registered."
                );
            }
        }

        ModuleRelease resolve(
            String name,
            Version requestedVersion
        ) {
            Map<Version, ModuleRelease> versions = releases.get(name);

            if (versions == null) {
                throw new ValidationException(
                    "Unknown module: " + name
                );
            }

            ModuleRelease release = versions.get(requestedVersion);

            if (release == null) {
                throw new ValidationException(
                    "Requested version is unavailable."
                );
            }

            return release;
        }

        ModuleRelease latest(String name) {
            TreeMap<Version, ModuleRelease> versions = releases.get(name);

            if (versions == null || versions.isEmpty()) {
                throw new ValidationException(
                    "No releases for module: " + name
                );
            }

            return versions.lastEntry().getValue();
        }
    }

    static class DependencyResolver {

        List<String> resolve(Map<String, List<String>> graph) {
            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();
            List<String> result = new ArrayList<>();

            for (String node : graph.keySet()) {
                visit(node, graph, visited, active, result);
            }

            return List.copyOf(result);
        }

        private void visit(
            String node,
            Map<String, List<String>> graph,
            Set<String> visited,
            Set<String> active,
            List<String> result
        ) {
            if (active.contains(node)) {
                throw new GovernanceException(
                    "Circular dependency: " + node
                );
            }

            if (visited.contains(node)) {
                return;
            }

            active.add(node);

            for (String dependency :
                graph.getOrDefault(node, List.of())) {

                if (!graph.containsKey(dependency)) {
                    throw new GovernanceException(
                        "Missing dependency: " + dependency
                    );
                }

                visit(
                    dependency,
                    graph,
                    visited,
                    active,
                    result
                );
            }

            active.remove(node);
            visited.add(node);
            result.add(node);
        }
    }

    static class ApprovalService {

        boolean evaluate(
            DeploymentRequest request,
            BranchPolicy policy
        ) {
            if (!request.authorized()) {
                return false;
            }

            if (request.environment().isBlank()) {
                return false;
            }

            if (
                policy.requirePinnedSource() &&
                !request.sourcePinned()
            ) {
                return false;
            }

            if (
                policy.requireResolvedDiscussions() &&
                request.unresolvedDiscussions() > 0
            ) {
                return false;
            }

            Set<String> approved = new HashSet<>();

            for (Review review : request.reviews()) {
                if (review.reviewer().isBlank()) {
                    continue;
                }

                if (review.decision() == ReviewDecision.APPROVED) {
                    approved.add(review.reviewer());
                } else if (
                    review.decision() ==
                    ReviewDecision.CHANGES_REQUESTED
                ) {
                    approved.remove(review.reviewer());
                }
            }

            if (approved.size() < policy.requiredApprovals()) {
                return false;
            }

            if (policy.requireChecks()) {
                if (request.checks().isEmpty()) {
                    return false;
                }

                if (
                    request.checks().stream()
                        .anyMatch(check -> !check.passed())
                ) {
                    return false;
                }
            }

            return true;
        }
    }

    static class InfrastructureService {
        private final ModuleRegistry registry;
        private final DependencyResolver resolver =
            new DependencyResolver();

        private Map<String, Map<String, String>> state =
            new HashMap<>();

        InfrastructureService(ModuleRegistry registry) {
            this.registry = registry;
        }

        List<PlannedResource> plan(List<ModuleCall> calls) {
            Map<String, ModuleRelease> modules =
                new LinkedHashMap<>();

            Map<String, Map<String, Object>> inputs =
                new HashMap<>();

            Map<String, List<String>> graph =
                new LinkedHashMap<>();

            for (ModuleCall call : calls) {
                if (modules.containsKey(call.instance())) {
                    throw new ValidationException(
                        "Duplicate module instance: " + call.instance()
                    );
                }

                ModuleRelease release = registry.resolve(
                    call.moduleName(),
                    call.version()
                );

                modules.put(call.instance(), release);

                inputs.put(
                    call.instance(),
                    release.validateInputs(call.inputs())
                );

                graph.put(
                    call.instance(),
                    release.dependencies()
                );
            }

            List<String> order = resolver.resolve(graph);

            List<PlannedResource> plans = new ArrayList<>();

            for (String instance : order) {
                ModuleRelease release = modules.get(instance);

                for (ResourceDefinition resource :
                    release.resources()) {

                    String address =
                        "module." + instance + "." +
                        resource.type() + "." + resource.name();

                    Map<String, String> desired =
                        new HashMap<>(resource.configuration());

                    desired.put(
                        "environment",
                        String.valueOf(
                            inputs.get(instance).get("environment")
                        )
                    );

                    Map<String, String> current = state.get(address);

                    ResourceAction action;

                    if (current == null) {
                        action = ResourceAction.CREATE;
                    } else if (current.equals(desired)) {
                        action = ResourceAction.NO_CHANGE;
                    } else {
                        action = ResourceAction.UPDATE;
                    }

                    plans.add(
                        new PlannedResource(
                            address,
                            action,
                            Map.copyOf(desired)
                        )
                    );
                }
            }

            return List.copyOf(plans);
        }

        void apply(List<PlannedResource> plans) {
            Map<String, Map<String, String>> staged =
                new HashMap<>(state);

            for (PlannedResource plan : plans) {
                if (plan.action() != ResourceAction.NO_CHANGE) {
                    staged.put(
                        plan.address(),
                        plan.configuration()
                    );
                }
            }

            state = staged;
        }

        List<String> detectDrift(
            Map<String, Map<String, String>> actual
        ) {
            List<String> drift = new ArrayList<>();

            for (var entry : state.entrySet()) {
                if (!Objects.equals(
                    entry.getValue(),
                    actual.get(entry.getKey())
                )) {
                    drift.add(entry.getKey());
                }
            }

            return drift;
        }

        int resourceCount() {
            return state.size();
        }
    }

    static class DeploymentService {
        private final ApprovalService approvals;
        private final InfrastructureService infrastructure;
        private final BranchPolicy policy;

        private DeploymentStatus status = DeploymentStatus.PENDING;

        DeploymentService(
            ApprovalService approvals,
            InfrastructureService infrastructure,
            BranchPolicy policy
        ) {
            this.approvals = approvals;
            this.infrastructure = infrastructure;
            this.policy = policy;
        }

        DeploymentResult deploy(
            DeploymentRequest request,
            List<ModuleCall> calls
        ) {
            try {
                status = DeploymentStatus.VALIDATING;

                if (!approvals.evaluate(request, policy)) {
                    throw new GovernanceException(
                        "Deployment does not satisfy governance policy."
                    );
                }

                status = DeploymentStatus.PLANNING;

                List<PlannedResource> plans =
                    infrastructure.plan(calls);

                status = DeploymentStatus.APPLYING;

                infrastructure.apply(plans);

                status = DeploymentStatus.SUCCEEDED;

                return new DeploymentResult(
                    request.id(),
                    status,
                    infrastructure.resourceCount(),
                    Instant.now()
                );

            } catch (RuntimeException exception) {
                status = DeploymentStatus.FAILED;
                throw exception;
            }
        }

        DeploymentStatus status() {
            return status;
        }
    }

    private static ModuleRelease createNetworkModule() {
        return new ModuleRelease(
            "network",
            new Version(1, 2, 0),
            "registry.example.com/platform/network",
            "a".repeat(64),
            Map.of(
                "environment",
                new InputDefinition(
                    "environment",
                    InputType.STRING,
                    true,
                    null,
                    Set.of("development", "staging", "production")
                ),
                "cidr",
                new InputDefinition(
                    "cidr",
                    InputType.STRING,
                    true,
                    null,
                    Set.of()
                )
            ),
            Map.of(
                "network_id",
                new OutputDefinition("network_id", false)
            ),
            List.of(
                new ResourceDefinition(
                    "main",
                    "aws_vpc",
                    Map.of(
                        "enable_dns_support", "true",
                        "enable_dns_hostnames", "true"
                    )
                )
            ),
            List.of()
        );
    }

    private static ModuleRelease createApplicationModule() {
        return new ModuleRelease(
            "application",
            new Version(2, 1, 0),
            "registry.example.com/platform/application",
            "b".repeat(64),
            Map.of(
                "environment",
                new InputDefinition(
                    "environment",
                    InputType.STRING,
                    true,
                    null,
                    Set.of("development", "staging", "production")
                ),
                "instance_type",
                new InputDefinition(
                    "instance_type",
                    InputType.STRING,
                    false,
                    "t3.small",
                    Set.of()
                )
            ),
            Map.of(
                "application_id",
                new OutputDefinition("application_id", false)
            ),
            List.of(
                new ResourceDefinition(
                    "web",
                    "aws_instance",
                    Map.of(
                        "encrypted_volume", "true",
                        "monitoring", "true"
                    )
                )
            ),
            List.of("network")
        );
    }

    public static void main(String[] args) {
        try {
            ModuleRegistry registry = new ModuleRegistry();

            registry.register(createNetworkModule());
            registry.register(createApplicationModule());

            BranchPolicy policy = new BranchPolicy(
                2,
                true,
                true,
                true
            );

            ApprovalService approvalService =
                new ApprovalService();

            InfrastructureService infrastructure =
                new InfrastructureService(registry);

            DeploymentService deploymentService =
                new DeploymentService(
                    approvalService,
                    infrastructure,
                    policy
                );

            DeploymentRequest request = new DeploymentRequest(
                "deployment-001",
                "production",
                List.of(
                    new Review("reviewer-alice", ReviewDecision.APPROVED),
                    new Review("reviewer-bob", ReviewDecision.APPROVED)
                ),
                List.of(
                    new StatusCheck("terraform_validate", true),
                    new StatusCheck("terraform_plan", true),
                    new StatusCheck("security_scan", true)
                ),
                0,
                true,
                true
            );

            List<ModuleCall> calls = List.of(
                new ModuleCall(
                    "network",
                    "network",
                    new Version(1, 2, 0),
                    Map.of(
                        "environment", "production",
                        "cidr", "10.50.0.0/16"
                    )
                ),
                new ModuleCall(
                    "application",
                    "application",
                    new Version(2, 1, 0),
                    Map.of(
                        "environment", "production",
                        "instance_type", "t3.medium"
                    )
                )
            );

            System.out.println("TERRAFORM ENTERPRISE MODULE PLATFORM");
            System.out.println("====================================");

            List<PlannedResource> plans =
                infrastructure.plan(calls);

            System.out.println("\nInfrastructure plan:");

            plans.forEach(plan ->
                System.out.println(
                    plan.action() + " " + plan.address()
                )
            );

            DeploymentResult result =
                deploymentService.deploy(request, calls);

            System.out.println("\nDeployment result:");
            System.out.println("ID: " + result.id());
            System.out.println("Status: " + result.status());
            System.out.println(
                "Managed resources: " + result.resourceCount()
            );

            DeploymentRequest blockedRequest =
                new DeploymentRequest(
                    "deployment-002",
                    "production",
                    request.reviews(),
                    List.of(
                        new StatusCheck("security_scan", false)
                    ),
                    0,
                    true,
                    true
                );

            try {
                deploymentService.deploy(blockedRequest, calls);
            } catch (GovernanceException exception) {
                System.out.println(
                    "\nExpected governance rejection: " +
                    exception.getMessage()
                );
            }

            System.out.println(
                "\nCurrent deployment state: " +
                deploymentService.status()
            );

        } catch (ModuleException exception) {
            System.err.println(
                "Module execution failed: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}

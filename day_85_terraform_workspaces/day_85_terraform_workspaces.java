import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Terraform Workspaces: Environment Separation and Workspace Strategies
 *
 * Enterprise infrastructure environment management model.
 * Java 17, no external dependencies.
 */

public class TerraformWorkspaceEnterprise {

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum WorkspaceStatus {
        ACTIVE,
        DELETED
    }

    enum DeploymentStatus {
        PLANNED,
        APPLIED,
        REJECTED
    }

    enum OperationType {
        CREATE,
        UPDATE,
        DESTROY,
        NO_CHANGE
    }

    static class WorkspaceException extends RuntimeException {
        WorkspaceException(String message) {
            super(message);
        }
    }

    static class PolicyViolationException extends WorkspaceException {
        PolicyViolationException(String message) {
            super(message);
        }
    }

    static class StalePlanException extends WorkspaceException {
        StalePlanException(String message) {
            super(message);
        }
    }

    static class ApprovalRequiredException extends WorkspaceException {
        ApprovalRequiredException(String message) {
            super(message);
        }
    }

    record EnvironmentPolicy(
        Environment environment,
        String region,
        Set<String> allowedInstanceTypes,
        int maximumInstances,
        boolean approvalRequired,
        double monthlyBudget,
        boolean databaseEnabled
    ) {
        EnvironmentPolicy {
            Objects.requireNonNull(environment);
            Objects.requireNonNull(region);
            allowedInstanceTypes = Set.copyOf(allowedInstanceTypes);

            if (!region.matches("[a-z]{2}-[a-z]+-\\d+")) {
                throw new WorkspaceException("Invalid cloud region.");
            }

            if (maximumInstances < 0 || monthlyBudget <= 0) {
                throw new WorkspaceException(
                    "Invalid environment limits."
                );
            }

            if (environment == Environment.PRODUCTION
                && !approvalRequired) {
                throw new PolicyViolationException(
                    "Production requires explicit approval."
                );
            }
        }
    }

    record Resource(
        String address,
        Map<String, String> attributes
    ) {
        Resource {
            Objects.requireNonNull(address);
            Objects.requireNonNull(attributes);

            if (!address.matches(
                "[a-zA-Z][a-zA-Z0-9_.-]{0,127}"
            )) {
                throw new WorkspaceException(
                    "Invalid resource address."
                );
            }

            attributes = Map.copyOf(attributes);
        }

        String attribute(String name) {
            return attributes.get(name);
        }
    }

    record StateSnapshot(
        String lineage,
        long serial,
        Map<String, Resource> resources,
        Instant updatedAt
    ) {
        StateSnapshot {
            resources = Map.copyOf(resources);
        }
    }

    record Operation(
        OperationType type,
        String address,
        Resource desired
    ) {}

    record DeploymentPlan(
        UUID id,
        String workspace,
        Environment environment,
        long expectedSerial,
        String expectedFingerprint,
        List<Operation> operations,
        boolean approvalRequired
    ) {
        DeploymentPlan {
            operations = List.copyOf(operations);
        }
    }

    record DeploymentRecord(
        UUID planId,
        String workspace,
        DeploymentStatus status,
        long resultingSerial,
        Instant timestamp,
        String actor
    ) {}

    interface DeploymentAuthorizer {
        boolean authorize(
            String actor,
            Environment environment,
            boolean approved
        );
    }

    static class ApprovalAuthorizer implements DeploymentAuthorizer {

        private final Set<String> authorizedProductionActors;

        ApprovalAuthorizer(Set<String> authorizedActors) {
            this.authorizedProductionActors =
                Set.copyOf(authorizedActors);
        }

        @Override
        public boolean authorize(
            String actor,
            Environment environment,
            boolean approved
        ) {
            if (environment != Environment.PRODUCTION) {
                return true;
            }

            return approved &&
                authorizedProductionActors.contains(actor);
        }
    }

    static class Workspace {

        private final String name;
        private final EnvironmentPolicy policy;
        private final String lineage = UUID.randomUUID().toString();

        private WorkspaceStatus status = WorkspaceStatus.ACTIVE;
        private long serial = 0;

        private Map<String, Resource> resources = new LinkedHashMap<>();

        private final List<DeploymentRecord> history =
            new ArrayList<>();

        Workspace(String name, EnvironmentPolicy policy) {
            this.name = name;
            this.policy = policy;
        }

        String name() {
            return name;
        }

        EnvironmentPolicy policy() {
            return policy;
        }

        long serial() {
            return serial;
        }

        Map<String, Resource> resources() {
            return Collections.unmodifiableMap(resources);
        }

        StateSnapshot snapshot() {
            return new StateSnapshot(
                lineage,
                serial,
                resources,
                history.isEmpty()
                    ? null
                    : history.get(history.size() - 1).timestamp()
            );
        }

        List<DeploymentRecord> history() {
            return List.copyOf(history);
        }

        void requireActive() {
            if (status != WorkspaceStatus.ACTIVE) {
                throw new WorkspaceException(
                    "Workspace is not active."
                );
            }
        }

        void validateResource(Resource resource) {
            Map<String, String> attributes = resource.attributes();

            String instanceType = attributes.get("instance_type");

            if (instanceType != null &&
                !policy.allowedInstanceTypes().contains(instanceType)) {
                throw new PolicyViolationException(
                    "Instance type is not permitted in " + name
                );
            }

            String countValue = attributes.get("count");

            if (countValue != null) {
                int count;

                try {
                    count = Integer.parseInt(countValue);
                } catch (NumberFormatException exception) {
                    throw new WorkspaceException(
                        "Instance count must be an integer."
                    );
                }

                if (count < 0 ||
                    count > policy.maximumInstances()) {
                    throw new PolicyViolationException(
                        "Instance count violates environment limits."
                    );
                }
            }

            if (attributes.containsKey("database") &&
                !policy.databaseEnabled()) {
                throw new PolicyViolationException(
                    "Database resources are disabled."
                );
            }
        }

        void commit(
            Map<String, Resource> nextResources,
            DeploymentPlan plan,
            String actor
        ) {
            if (serial != plan.expectedSerial()) {
                throw new StalePlanException(
                    "Workspace state changed after planning."
                );
            }

            resources = new LinkedHashMap<>(nextResources);
            serial++;

            history.add(new DeploymentRecord(
                plan.id(),
                name,
                DeploymentStatus.APPLIED,
                serial,
                Instant.now(),
                actor
            ));
        }

        void destroyResources() {
            resources.clear();
            serial++;
        }

        void delete() {
            if (!resources.isEmpty()) {
                throw new PolicyViolationException(
                    "Workspace still manages resources."
                );
            }

            status = WorkspaceStatus.DELETED;
        }
    }

    static class WorkspaceRegistry {

        private static final Pattern NAME_PATTERN =
            Pattern.compile("[a-z][a-z0-9_-]{0,62}");

        private final Map<String, Workspace> workspaces =
            new LinkedHashMap<>();

        private String selectedWorkspace = "default";

        WorkspaceRegistry(
            Map<Environment, EnvironmentPolicy> policies
        ) {
            EnvironmentPolicy development =
                policies.get(Environment.DEVELOPMENT);

            if (development == null) {
                throw new WorkspaceException(
                    "Development policy is required."
                );
            }

            workspaces.put(
                "default",
                new Workspace("default", development)
            );
        }

        void create(String name, Environment environment) {
            if (!NAME_PATTERN.matcher(name).matches()) {
                throw new WorkspaceException(
                    "Invalid workspace name."
                );
            }

            if (workspaces.containsKey(name)) {
                throw new WorkspaceException(
                    "Workspace already exists."
                );
            }

            EnvironmentPolicy policy =
                policiesFor(environment);

            workspaces.put(name, new Workspace(name, policy));
        }

        private EnvironmentPolicy policiesFor(
            Environment environment
        ) {
            EnvironmentPolicy policy =
                environmentPolicies.get(environment);

            if (policy == null) {
                throw new WorkspaceException(
                    "Environment policy not found."
                );
            }

            return policy;
        }

        private Map<Environment, EnvironmentPolicy> environmentPolicies =
            new EnumMap<>(Environment.class);

        void registerPolicies(
            Map<Environment, EnvironmentPolicy> policies
        ) {
            environmentPolicies.putAll(policies);
        }

        Workspace select(String name) {
            Workspace workspace = workspaces.get(name);

            if (workspace == null) {
                throw new WorkspaceException(
                    "Workspace does not exist."
                );
            }

            workspace.requireActive();
            selectedWorkspace = name;
            return workspace;
        }

        Workspace current() {
            Workspace workspace = workspaces.get(selectedWorkspace);

            if (workspace == null) {
                throw new WorkspaceException(
                    "Selected workspace unavailable."
                );
            }

            return workspace;
        }

        void delete(String name) {
            if (name.equals("default")) {
                throw new PolicyViolationException(
                    "Default workspace cannot be deleted."
                );
            }

            if (name.equals(selectedWorkspace)) {
                throw new PolicyViolationException(
                    "Select another workspace first."
                );
            }

            Workspace workspace = workspaces.get(name);

            if (workspace == null) {
                throw new WorkspaceException(
                    "Workspace not found."
                );
            }

            workspace.delete();
            workspaces.remove(name);
        }

        List<Workspace> all() {
            return List.copyOf(workspaces.values());
        }
    }

    static class InfrastructurePlanner {

        DeploymentPlan plan(
            Workspace workspace,
            Map<String, Resource> desired,
            Set<String> destroyAddresses
        ) {
            workspace.requireActive();

            if (desired.isEmpty() && destroyAddresses.isEmpty()) {
                throw new WorkspaceException(
                    "Changeset cannot be empty."
                );
            }

            List<Operation> operations = new ArrayList<>();

            for (Map.Entry<String, Resource> entry :
                desired.entrySet()) {

                Resource resource = entry.getValue();

                if (!entry.getKey().equals(resource.address())) {
                    throw new WorkspaceException(
                        "Resource address mismatch."
                    );
                }

                workspace.validateResource(resource);

                Resource existing =
                    workspace.resources().get(entry.getKey());

                OperationType type;

                if (existing == null) {
                    type = OperationType.CREATE;
                } else if (!existing.equals(resource)) {
                    type = OperationType.UPDATE;
                } else {
                    type = OperationType.NO_CHANGE;
                }

                operations.add(new Operation(
                    type,
                    entry.getKey(),
                    resource
                ));
            }

            for (String address : destroyAddresses) {
                if (workspace.resources().containsKey(address)) {
                    operations.add(new Operation(
                        OperationType.DESTROY,
                        address,
                        null
                    ));
                }
            }

            return new DeploymentPlan(
                UUID.randomUUID(),
                workspace.name(),
                workspace.policy().environment(),
                workspace.serial(),
                fingerprint(workspace.resources()),
                operations,
                workspace.policy().approvalRequired()
            );
        }

        private String fingerprint(
            Map<String, Resource> resources
        ) {
            String content = resources.entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .map(entry ->
                    entry.getKey() + "=" + entry.getValue().attributes()
                )
                .collect(Collectors.joining("|"));

            return UUID.nameUUIDFromBytes(
                content.getBytes(java.nio.charset.StandardCharsets.UTF_8)
            ).toString();
        }
    }

    static class DeploymentService {

        private final DeploymentAuthorizer authorizer;

        DeploymentService(DeploymentAuthorizer authorizer) {
            this.authorizer = authorizer;
        }

        DeploymentRecord apply(
            Workspace workspace,
            DeploymentPlan plan,
            String actor,
            boolean approved
        ) {
            if (!workspace.name().equals(plan.workspace())) {
                throw new WorkspaceException(
                    "Plan belongs to a different workspace."
                );
            }

            if (workspace.serial() != plan.expectedSerial()) {
                throw new StalePlanException(
                    "Plan is stale."
                );
            }

            if (!fingerprint(workspace.resources())
                .equals(plan.expectedFingerprint())) {
                throw new StalePlanException(
                    "State fingerprint changed."
                );
            }

            if (!authorizer.authorize(
                actor,
                plan.environment(),
                approved
            )) {
                throw new ApprovalRequiredException(
                    "Deployment approval or actor authorization failed."
                );
            }

            Map<String, Resource> nextResources =
                new LinkedHashMap<>(workspace.resources());

            for (Operation operation : plan.operations()) {
                switch (operation.type()) {
                    case CREATE:
                    case UPDATE:
                        workspace.validateResource(operation.desired());
                        nextResources.put(
                            operation.address(),
                            operation.desired()
                        );
                        break;

                    case DESTROY:
                        nextResources.remove(operation.address());
                        break;

                    case NO_CHANGE:
                        break;
                }
            }

            workspace.commit(nextResources, plan, actor);

            return workspace.history().get(
                workspace.history().size() - 1
            );
        }

        private String fingerprint(
            Map<String, Resource> resources
        ) {
            String content = resources.entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .map(entry ->
                    entry.getKey() + "=" + entry.getValue().attributes()
                )
                .collect(Collectors.joining("|"));

            return UUID.nameUUIDFromBytes(
                content.getBytes(java.nio.charset.StandardCharsets.UTF_8)
            ).toString();
        }
    }

    private static EnvironmentPolicy policy(
        Environment environment,
        Set<String> instanceTypes,
        int maximumInstances,
        boolean approval,
        double budget,
        boolean database
    ) {
        return new EnvironmentPolicy(
            environment,
            "ap-south-1",
            instanceTypes,
            maximumInstances,
            approval,
            budget,
            database
        );
    }

    private static Resource resource(
        String address,
        String instanceType,
        int count
    ) {
        return new Resource(
            address,
            Map.of(
                "instance_type", instanceType,
                "count", String.valueOf(count)
            )
        );
    }

    public static void main(String[] args) {
        try {
            Map<Environment, EnvironmentPolicy> policies =
                new EnumMap<>(Environment.class);

            policies.put(
                Environment.DEVELOPMENT,
                policy(
                    Environment.DEVELOPMENT,
                    Set.of("t3.micro", "t3.small"),
                    2, false, 100, false
                )
            );

            policies.put(
                Environment.STAGING,
                policy(
                    Environment.STAGING,
                    Set.of("t3.small", "t3.medium"),
                    5, false, 500, true
                )
            );

            policies.put(
                Environment.PRODUCTION,
                policy(
                    Environment.PRODUCTION,
                    Set.of("t3.medium", "t3.large"),
                    10, true, 2000, true
                )
            );

            WorkspaceRegistry registry = new WorkspaceRegistry(policies);
            registry.registerPolicies(policies);

            registry.create("development", Environment.DEVELOPMENT);
            registry.create("staging", Environment.STAGING);
            registry.create("production", Environment.PRODUCTION);

            InfrastructurePlanner planner =
                new InfrastructurePlanner();

            DeploymentService deploymentService =
                new DeploymentService(
                    new ApprovalAuthorizer(Set.of("platform-admin"))
                );

            Workspace development = registry.select("development");

            DeploymentPlan developmentPlan = planner.plan(
                development,
                Map.of(
                    "aws_instance.application",
                    resource(
                        "aws_instance.application",
                        "t3.micro",
                        1
                    )
                ),
                Set.of()
            );

            System.out.println(deploymentService.apply(
                development,
                developmentPlan,
                "developer-01",
                false
            ));

            Workspace staging = registry.select("staging");

            DeploymentPlan stagingPlan = planner.plan(
                staging,
                Map.of(
                    "aws_instance.application",
                    resource(
                        "aws_instance.application",
                        "t3.small",
                        2
                    )
                ),
                Set.of()
            );

            System.out.println(deploymentService.apply(
                staging,
                stagingPlan,
                "release-manager",
                false
            ));

            Workspace production = registry.select("production");

            DeploymentPlan productionPlan = planner.plan(
                production,
                Map.of(
                    "aws_instance.application",
                    resource(
                        "aws_instance.application",
                        "t3.medium",
                        3
                    )
                ),
                Set.of()
            );

            try {
                deploymentService.apply(
                    production,
                    productionPlan,
                    "developer-01",
                    true
                );
            } catch (WorkspaceException exception) {
                System.out.println(
                    "Production rejected: " + exception.getMessage()
                );
            }

            System.out.println(deploymentService.apply(
                production,
                productionPlan,
                "platform-admin",
                true
            ));

            System.out.println("\nWORKSPACE REPORT");

            registry.all().stream()
                .forEach(workspace -> System.out.printf(
                    "%-15s %-12s serial=%d resources=%d%n",
                    workspace.name(),
                    workspace.policy().environment(),
                    workspace.serial(),
                    workspace.resources().size()
                ));

            System.out.println("\nState separation verified: " +
                (development.snapshot().lineage()
                    .equals(staging.snapshot().lineage()) == false));

        } catch (WorkspaceException exception) {
            System.err.println(
                "Infrastructure workflow failed: " +
                exception.getMessage()
            );
            System.exit(1);
        }
    }
}

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
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
import java.util.function.Predicate;
import java.util.regex.Pattern;

/*
 * Terraform Fundamentals: Enterprise Infrastructure Configuration.
 *
 * Java 17 implementation of:
 * - Provider configuration
 * - Variable schemas
 * - Resource modeling
 * - Dependency resolution
 * - Infrastructure planning
 * - State management
 * - Output evaluation
 * - Policy validation
 * - Transactional apply simulation
 *
 * Compile: javac TerraformFundamentals.java
 * Run: java TerraformFundamentals
 */

public class TerraformFundamentals {

    enum Action {
        CREATE,
        UPDATE,
        NO_CHANGE,
        DESTROY
    }

    enum Status {
        PENDING,
        PLANNED,
        CREATED,
        UPDATED,
        FAILED,
        DESTROYED
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    static class ConfigurationException extends InfrastructureException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static class ProviderException extends InfrastructureException {
        ProviderException(String message) {
            super(message);
        }
    }

    static class DependencyException extends InfrastructureException {
        DependencyException(String message) {
            super(message);
        }
    }

    record ProviderConfig(
        String name,
        String region,
        String version,
        String authenticationMethod
    ) {
        private static final Pattern NAME =
            Pattern.compile("[a-z][a-z0-9_-]*");

        private static final Pattern VERSION =
            Pattern.compile("\\d+\\.\\d+\\.\\d+");

        ProviderConfig {
            Objects.requireNonNull(name);
            Objects.requireNonNull(region);
            Objects.requireNonNull(version);
            Objects.requireNonNull(authenticationMethod);

            if (!NAME.matcher(name).matches()) {
                throw new ConfigurationException("Invalid provider name.");
            }

            if (!VERSION.matcher(version).matches()) {
                throw new ConfigurationException(
                    "Provider version must be major.minor.patch."
                );
            }

            if (!region.matches("[a-z0-9-]+")) {
                throw new ConfigurationException("Invalid provider region.");
            }

            if (!Set.of("environment", "workload_identity")
                    .contains(authenticationMethod)) {
                throw new ConfigurationException(
                    "Unsupported authentication method."
                );
            }
        }
    }

    record VariableDefinition(
        String name,
        Class<?> type,
        Object defaultValue,
        boolean required,
        boolean sensitive,
        Predicate<Object> validator
    ) {
        VariableDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
            Objects.requireNonNull(validator);

            if (name.isBlank()) {
                throw new ConfigurationException(
                    "Variable name cannot be empty."
                );
            }

            if (defaultValue != null &&
                !type.isInstance(defaultValue)) {
                throw new ConfigurationException(
                    "Default value has incorrect type: " + name
                );
            }
        }
    }

    static class VariableService {
        private final Map<String, VariableDefinition> definitions =
            new LinkedHashMap<>();

        void define(VariableDefinition definition) {
            if (definitions.putIfAbsent(
                    definition.name(), definition) != null) {
                throw new ConfigurationException(
                    "Duplicate variable: " + definition.name()
                );
            }
        }

        Map<String, Object> resolve(Map<String, Object> supplied) {
            for (String key : supplied.keySet()) {
                if (!definitions.containsKey(key)) {
                    throw new ConfigurationException(
                        "Unknown variable: " + key
                    );
                }
            }

            Map<String, Object> result = new LinkedHashMap<>();

            for (VariableDefinition definition : definitions.values()) {
                String name = definition.name();

                Object value = supplied.containsKey(name)
                    ? supplied.get(name)
                    : definition.defaultValue();

                if (value == null && definition.required()) {
                    throw new ConfigurationException(
                        "Required variable missing: " + name
                    );
                }

                if (value != null &&
                    !definition.type().isInstance(value)) {
                    throw new ConfigurationException(
                        "Incorrect variable type: " + name
                    );
                }

                if (value != null && !definition.validator().test(value)) {
                    throw new ConfigurationException(
                        "Variable validation failed: " + name
                    );
                }

                result.put(name, value);
            }

            return Collections.unmodifiableMap(result);
        }

        Map<String, Object> safeView(Map<String, Object> values) {
            Map<String, Object> result = new LinkedHashMap<>();

            for (var entry : values.entrySet()) {
                VariableDefinition definition =
                    definitions.get(entry.getKey());

                result.put(
                    entry.getKey(),
                    definition.sensitive()
                        ? "[REDACTED]"
                        : entry.getValue()
                );
            }

            return result;
        }
    }

    static class Resource {
        private final String name;
        private final String type;
        private final String provider;
        private final Map<String, Object> attributes;
        private final List<String> dependencies;
        private Status status = Status.PENDING;

        Resource(
            String name,
            String type,
            String provider,
            Map<String, Object> attributes,
            List<String> dependencies
        ) {
            this.name = Objects.requireNonNull(name);
            this.type = Objects.requireNonNull(type);
            this.provider = Objects.requireNonNull(provider);
            this.attributes = Map.copyOf(attributes);
            this.dependencies = List.copyOf(dependencies);

            if (!name.matches("[a-z][a-z0-9_]*")) {
                throw new ConfigurationException("Invalid resource name.");
            }

            if (!type.matches(
                    "[a-z][a-z0-9_]*_[a-z][a-z0-9_]*")) {
                throw new ConfigurationException("Invalid resource type.");
            }

            if (this.dependencies.contains(address())) {
                throw new DependencyException(
                    "Resource cannot depend on itself."
                );
            }
        }

        String address() {
            return type + "." + name;
        }

        String provider() {
            return provider;
        }

        Map<String, Object> attributes() {
            return attributes;
        }

        List<String> dependencies() {
            return dependencies;
        }

        void setStatus(Status status) {
            this.status = status;
        }

        Status status() {
            return status;
        }
    }

    record StateRecord(
        String address,
        String id,
        String provider,
        Map<String, Object> attributes
    ) {
        StateRecord {
            attributes = Map.copyOf(attributes);
        }
    }

    record PlanEntry(
        String address,
        Action action,
        Map<String, Object> before,
        Map<String, Object> after
    ) {}

    static class StateRepository {
        private final Map<String, StateRecord> records =
            new LinkedHashMap<>();

        StateRecord get(String address) {
            return records.get(address);
        }

        void save(StateRecord record) {
            records.put(record.address(), record);
        }

        void delete(String address) {
            records.remove(address);
        }

        Map<String, StateRecord> snapshot() {
            return new LinkedHashMap<>(records);
        }

        void restore(Map<String, StateRecord> snapshot) {
            records.clear();
            records.putAll(snapshot);
        }

        Map<String, StateRecord> all() {
            return Collections.unmodifiableMap(records);
        }
    }

    static class InfrastructureService {
        private final ProviderConfig provider;
        private final Map<String, Object> variables;
        private final Map<String, Resource> resources =
            new LinkedHashMap<>();

        private final StateRepository state = new StateRepository();

        InfrastructureService(
            ProviderConfig provider,
            Map<String, Object> variables
        ) {
            this.provider = provider;
            this.variables = variables;
        }

        void register(Resource resource) {
            if (!resource.provider().equals(provider.name())) {
                throw new ProviderException(
                    "Resource provider is not configured."
                );
            }

            if (resources.putIfAbsent(
                    resource.address(), resource) != null) {
                throw new ConfigurationException(
                    "Duplicate resource: " + resource.address()
                );
            }
        }

        private Object interpolate(Object value) {
            if (!(value instanceof String text)) {
                return value;
            }

            Pattern pattern = Pattern.compile(
                "\\$\\{var\\.([a-zA-Z_][a-zA-Z0-9_]*)}"
            );

            var matcher = pattern.matcher(text);
            StringBuffer result = new StringBuffer();

            while (matcher.find()) {
                String variable = matcher.group(1);

                if (!variables.containsKey(variable)) {
                    throw new ConfigurationException(
                        "Unknown variable reference: " + variable
                    );
                }

                String replacement = String.valueOf(
                    variables.get(variable)
                );

                matcher.appendReplacement(
                    result,
                    java.util.regex.Matcher.quoteReplacement(replacement)
                );
            }

            matcher.appendTail(result);
            return result.toString();
        }

        private Map<String, Object> resolvedAttributes(Resource resource) {
            Map<String, Object> result = new LinkedHashMap<>();

            for (var entry : resource.attributes().entrySet()) {
                result.put(
                    entry.getKey(),
                    interpolate(entry.getValue())
                );
            }

            return result;
        }

        List<String> dependencyOrder() {
            List<String> result = new ArrayList<>();
            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();

            for (String address : resources.keySet().stream()
                    .sorted()
                    .toList()) {
                visit(address, visited, active, result);
            }

            return result;
        }

        private void visit(
            String address,
            Set<String> visited,
            Set<String> active,
            List<String> result
        ) {
            if (active.contains(address)) {
                throw new DependencyException(
                    "Circular dependency: " + address
                );
            }

            if (visited.contains(address)) {
                return;
            }

            Resource resource = resources.get(address);

            if (resource == null) {
                throw new DependencyException(
                    "Unknown dependency: " + address
                );
            }

            active.add(address);

            for (String dependency : resource.dependencies()) {
                visit(dependency, visited, active, result);
            }

            active.remove(address);
            visited.add(address);
            result.add(address);
        }

        List<PlanEntry> plan() {
            List<PlanEntry> result = new ArrayList<>();

            for (String address : dependencyOrder()) {
                Resource resource = resources.get(address);

                Map<String, Object> desired =
                    resolvedAttributes(resource);

                StateRecord current = state.get(address);

                Action action;

                if (current == null) {
                    action = Action.CREATE;
                } else if (current.attributes().equals(desired)) {
                    action = Action.NO_CHANGE;
                } else {
                    action = Action.UPDATE;
                }

                resource.setStatus(Status.PLANNED);

                result.add(new PlanEntry(
                    address,
                    action,
                    current == null
                        ? Map.of()
                        : current.attributes(),
                    desired
                ));
            }

            for (String address : state.all().keySet()) {
                if (!resources.containsKey(address)) {
                    result.add(new PlanEntry(
                        address,
                        Action.DESTROY,
                        state.get(address).attributes(),
                        Map.of()
                    ));
                }
            }

            return List.copyOf(result);
        }

        private String generateId(
            String address,
            Map<String, Object> attributes
        ) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                String input = address + new java.util.TreeMap<>(
                    attributes
                );

                byte[] hash = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8)
                );

                StringBuilder result = new StringBuilder("tf-");

                for (int i = 0; i < 8; i++) {
                    result.append(
                        String.format("%02x", hash[i])
                    );
                }

                return result.toString();

            } catch (NoSuchAlgorithmException error) {
                throw new InfrastructureException(
                    "Hash algorithm unavailable."
                );
            }
        }

        void apply(List<PlanEntry> plan) {
            Map<String, StateRecord> snapshot = state.snapshot();

            try {
                for (PlanEntry entry : plan) {
                    if (entry.action() == Action.DESTROY) {
                        state.delete(entry.address());
                        System.out.println(
                            "DESTROY " + entry.address()
                        );
                        continue;
                    }

                    if (entry.action() == Action.NO_CHANGE) {
                        System.out.println(
                            "NO_CHANGE " + entry.address()
                        );
                        continue;
                    }

                    Resource resource = resources.get(entry.address());

                    if (resource == null) {
                        throw new InfrastructureException(
                            "Missing resource configuration."
                        );
                    }

                    if (Boolean.TRUE.equals(
                            entry.after().get("simulateFailure"))) {
                        throw new ProviderException(
                            "Provider failure: " + entry.address()
                        );
                    }

                    Map<String, Object> attributes =
                        new LinkedHashMap<>(entry.after());

                    attributes.remove("simulateFailure");

                    StateRecord record = new StateRecord(
                        entry.address(),
                        generateId(entry.address(), attributes),
                        provider.name(),
                        attributes
                    );

                    state.save(record);

                    resource.setStatus(
                        entry.action() == Action.CREATE
                            ? Status.CREATED
                            : Status.UPDATED
                    );

                    System.out.println(
                        entry.action() + " " + entry.address()
                    );
                }

            } catch (RuntimeException error) {
                state.restore(snapshot);

                resources.values().forEach(
                    resource -> resource.setStatus(Status.FAILED)
                );

                throw error;
            }
        }

        Map<String, Object> evaluateOutputs(
            Map<String, OutputReference> definitions
        ) {
            Map<String, Object> result = new LinkedHashMap<>();

            for (var entry : definitions.entrySet()) {
                OutputReference reference = entry.getValue();
                StateRecord record = state.get(reference.resource());

                if (record == null) {
                    throw new InfrastructureException(
                        "Output references missing resource: " +
                        reference.resource()
                    );
                }

                if (!record.attributes().containsKey(
                        reference.attribute())) {
                    throw new InfrastructureException(
                        "Unknown output attribute: " +
                        reference.attribute()
                    );
                }

                result.put(
                    entry.getKey(),
                    record.attributes().get(reference.attribute())
                );
            }

            return Collections.unmodifiableMap(result);
        }

        void printState() {
            for (StateRecord record : state.all().values()) {
                System.out.println(
                    record.address() +
                    " | ID=" + record.id() +
                    " | Provider=" + record.provider() +
                    " | Attributes=" + record.attributes()
                );
            }
        }

        int stateSize() {
            return state.all().size();
        }
    }

    record OutputReference(String resource, String attribute) {}

    public static void main(String[] args) {
        try {
            VariableService variables = new VariableService();

            variables.define(new VariableDefinition(
                "environment",
                String.class,
                "development",
                false,
                false,
                value -> Set.of(
                    "development", "staging", "production"
                ).contains(value)
            ));

            variables.define(new VariableDefinition(
                "instance_type",
                String.class,
                "t3.small",
                false,
                false,
                value -> ((String) value).matches(
                    "[a-z0-9]+\\.[a-z0-9]+"
                )
            ));

            variables.define(new VariableDefinition(
                "instance_count",
                Integer.class,
                2,
                false,
                false,
                value -> (Integer) value >= 1 &&
                         (Integer) value <= 10
            ));

            variables.define(new VariableDefinition(
                "database_password",
                String.class,
                null,
                true,
                true,
                value -> ((String) value).length() >= 12
            ));

            Map<String, Object> resolved = variables.resolve(
                Map.of(
                    "environment", "development",
                    "instance_type", "t3.small",
                    "instance_count", 2,
                    "database_password", "SecurePassword123!"
                )
            );

            System.out.println("=== PROVIDER ===");

            ProviderConfig aws = new ProviderConfig(
                "aws",
                "ap-south-1",
                "5.80.0",
                "environment"
            );

            System.out.println(aws);

            System.out.println("\n=== VARIABLES ===");
            System.out.println(variables.safeView(resolved));

            InfrastructureService service =
                new InfrastructureService(aws, resolved);

            service.register(new Resource(
                "network",
                "aws_vpc",
                "aws",
                Map.of(
                    "cidr_block", "10.0.0.0/16",
                    "environment", "${var.environment}"
                ),
                List.of()
            ));

            service.register(new Resource(
                "application",
                "aws_instance",
                "aws",
                Map.of(
                    "instance_type", "${var.instance_type}",
                    "instance_count", "${var.instance_count}",
                    "environment", "${var.environment}"
                ),
                List.of("aws_vpc.network")
            ));

            service.register(new Resource(
                "database",
                "aws_db_instance",
                "aws",
                Map.of(
                    "engine", "postgres",
                    "password_configured", true,
                    "environment", "${var.environment}"
                ),
                List.of("aws_vpc.network")
            ));

            System.out.println("\n=== DEPENDENCIES ===");

            service.dependencyOrder().forEach(
                address -> System.out.println("-> " + address)
            );

            System.out.println("\n=== PLAN ===");

            List<PlanEntry> plan = service.plan();

            plan.forEach(entry ->
                System.out.println(
                    entry.action() + " " + entry.address()
                )
            );

            System.out.println("\n=== APPLY ===");
            service.apply(plan);

            System.out.println("\n=== STATE ===");
            service.printState();

            System.out.println("\n=== OUTPUTS ===");

            Map<String, Object> outputs = service.evaluateOutputs(
                Map.of(
                    "network_cidr",
                    new OutputReference(
                        "aws_vpc.network", "cidr_block"
                    ),
                    "application_type",
                    new OutputReference(
                        "aws_instance.application", "instance_type"
                    )
                )
            );

            System.out.println(outputs);

            System.out.println("\n=== SECOND PLAN ===");

            service.plan().forEach(entry ->
                System.out.println(
                    entry.action() + " " + entry.address()
                )
            );

            System.out.println("\n=== INVALID CONFIGURATION ===");

            try {
                variables.resolve(
                    Map.of(
                        "environment", "invalid",
                        "instance_type", "t3.small",
                        "instance_count", 100,
                        "database_password", "short"
                    )
                );
            } catch (ConfigurationException error) {
                System.out.println(
                    "Expected validation error: " + error.getMessage()
                );
            }

            System.out.println("\n=== ROLLBACK TEST ===");

            InfrastructureService failing =
                new InfrastructureService(aws, resolved);

            failing.register(new Resource(
                "valid_network",
                "aws_vpc",
                "aws",
                Map.of("cidr_block", "10.1.0.0/16"),
                List.of()
            ));

            failing.register(new Resource(
                "failing_instance",
                "aws_instance",
                "aws",
                Map.of(
                    "instance_type", "t3.small",
                    "simulateFailure", true
                ),
                List.of()
            ));

            try {
                failing.apply(failing.plan());
            } catch (ProviderException error) {
                System.out.println(
                    "Expected provider error: " + error.getMessage()
                );
            }

            System.out.println(
                "Resources remaining after rollback: " +
                failing.stateSize()
            );

            System.out.println("\nExecution completed.");

        } catch (InfrastructureException error) {
            System.err.println(
                "Infrastructure error: " + error.getMessage()
            );

            System.exitCode = 1;
        }
    }
}

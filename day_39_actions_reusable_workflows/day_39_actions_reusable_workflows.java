import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Consumer;

/*
 * Enterprise repository automation model.
 *
 * Reusable workflows expose a job-level interface through workflow_call.
 * Composite actions expose a step-level interface through action.yml.
 * This program models their contracts, execution contexts, output propagation,
 * dependency rules, and deployment authorization without external libraries.
 *
 * Compile and run:
 *   javac AutomationGovernance.java
 *   java AutomationGovernance
 */

public class AutomationGovernance {

    enum ExecutionState {
        PENDING, RUNNING, SUCCEEDED, FAILED, SKIPPED
    }

    static final class AutomationException extends RuntimeException {
        AutomationException(String message) {
            super(message);
        }

        AutomationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record InputDefinition(
            String name,
            boolean required,
            String defaultValue,
            Set<String> allowedValues) {

        InputDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(defaultValue);
            allowedValues = Set.copyOf(allowedValues);
        }

        String resolve(Map<String, String> supplied) {
            String value = supplied.getOrDefault(name, defaultValue);

            if (required && value.isBlank()) {
                throw new AutomationException(
                        "Required input is empty: " + name);
            }

            if (!allowedValues.isEmpty() && !allowedValues.contains(value)) {
                throw new AutomationException(
                        "Unsupported value for " + name + ": " + value);
            }

            return value;
        }
    }

    static final class InputContract {
        private final Map<String, InputDefinition> definitions;

        InputContract(List<InputDefinition> definitions) {
            Map<String, InputDefinition> index = new LinkedHashMap<>();

            for (InputDefinition definition : definitions) {
                if (index.putIfAbsent(definition.name(), definition) != null) {
                    throw new AutomationException(
                            "Duplicate input definition: " + definition.name());
                }
            }

            this.definitions = Map.copyOf(index);
        }

        Map<String, String> resolve(Map<String, String> supplied) {
            Set<String> unknown = new HashSet<>(supplied.keySet());
            unknown.removeAll(definitions.keySet());

            if (!unknown.isEmpty()) {
                throw new AutomationException(
                        "Undeclared inputs: " + unknown);
            }

            Map<String, String> resolved = new LinkedHashMap<>();

            definitions.forEach((name, definition) ->
                    resolved.put(name, definition.resolve(supplied)));

            return Map.copyOf(resolved);
        }
    }

    static final class ExecutionContext {
        private final Map<String, String> inputs;
        private final Map<String, String> secrets;
        private final Map<String, String> environment;
        private final Map<String, String> outputs = new LinkedHashMap<>();
        private final List<String> logs = new ArrayList<>();

        ExecutionContext(
                Map<String, String> inputs,
                Map<String, String> secrets,
                Map<String, String> environment) {
            this.inputs = Map.copyOf(inputs);
            this.secrets = Map.copyOf(secrets);
            this.environment = Map.copyOf(environment);
        }

        String input(String name) {
            String value = inputs.get(name);
            if (value == null) {
                throw new AutomationException("Missing input: " + name);
            }
            return value;
        }

        String environment(String name) {
            String value = environment.get(name);
            if (value == null) {
                throw new AutomationException(
                        "Missing environment value: " + name);
            }
            return value;
        }

        String secret(String name) {
            String value = secrets.get(name);
            if (value == null || value.isBlank()) {
                throw new AutomationException("Missing secret: " + name);
            }
            return value;
        }

        void output(String name, String value) {
            outputs.put(name, value);
        }

        String output(String name) {
            return outputs.get(name);
        }

        Map<String, String> outputs() {
            return Map.copyOf(outputs);
        }

        void log(String message) {
            String safe = message;
            for (String secret : secrets.values()) {
                if (!secret.isEmpty()) {
                    safe = safe.replace(secret, "***");
                }
            }
            logs.add(safe);
        }

        List<String> logs() {
            return List.copyOf(logs);
        }
    }

    @FunctionalInterface
    interface ActionStep {
        void execute(ExecutionContext context);
    }

    record NamedStep(String name, ActionStep operation) {
        NamedStep {
            Objects.requireNonNull(name);
            Objects.requireNonNull(operation);
        }
    }

    static final class CompositeAction {
        private final String name;
        private final InputContract contract;
        private final List<NamedStep> steps;
        private final Set<String> declaredOutputs;

        CompositeAction(
                String name,
                InputContract contract,
                List<NamedStep> steps,
                Set<String> declaredOutputs) {
            this.name = name;
            this.contract = contract;
            this.steps = List.copyOf(steps);
            this.declaredOutputs = Set.copyOf(declaredOutputs);
        }

        Map<String, String> execute(
                Map<String, String> suppliedInputs,
                ExecutionContext parent) {

            Map<String, String> resolved = contract.resolve(suppliedInputs);

            // The child action sees its declared inputs and inherited execution
            // facilities. Its output map is collected and returned explicitly.
            ExecutionContext child = new ExecutionContext(
                    resolved,
                    Map.of(),
                    Map.of(
                            "GITHUB_SHA",
                            parent.environment("GITHUB_SHA"),
                            "PRODUCTION_APPROVED",
                            parent.environment("PRODUCTION_APPROVED"),
                            "DEPLOY_TOKEN",
                            parent.secret("DEPLOY_TOKEN")
                    ));

            for (NamedStep step : steps) {
                child.log("Action " + name + ": " + step.name());

                try {
                    step.operation().execute(child);
                } catch (RuntimeException error) {
                    throw new AutomationException(
                            "Action step failed: " + step.name(), error);
                }
            }

            Map<String, String> outputs = child.outputs();
            Set<String> missing = new HashSet<>(declaredOutputs);
            missing.removeAll(outputs.keySet());

            if (!missing.isEmpty()) {
                throw new AutomationException(
                        "Action did not produce declared outputs: " + missing);
            }

            child.logs().forEach(parent::log);
            outputs.forEach(parent::output);
            return outputs;
        }
    }

    record JobDefinition(
            String name,
            List<String> needs,
            Consumer<ExecutionContext> operation) {
        JobDefinition {
            needs = List.copyOf(needs);
            Objects.requireNonNull(operation);
        }
    }

    static final class WorkflowReport {
        private final Map<String, ExecutionState> states;
        private final Map<String, String> errors;
        private final Map<String, String> outputs;
        private final List<String> logs;

        WorkflowReport(
                Map<String, ExecutionState> states,
                Map<String, String> errors,
                Map<String, String> outputs,
                List<String> logs) {
            this.states = Map.copyOf(states);
            this.errors = Map.copyOf(errors);
            this.outputs = Map.copyOf(outputs);
            this.logs = List.copyOf(logs);
        }

        Map<String, ExecutionState> states() {
            return states;
        }

        Map<String, String> errors() {
            return errors;
        }

        Map<String, String> outputs() {
            return outputs;
        }

        List<String> logs() {
            return logs;
        }
    }

    static final class ReusableWorkflow {
        private final String name;
        private final InputContract contract;
        private final Set<String> requiredSecrets;
        private final List<JobDefinition> jobs;

        ReusableWorkflow(
                String name,
                InputContract contract,
                Set<String> requiredSecrets,
                List<JobDefinition> jobs) {
            this.name = name;
            this.contract = contract;
            this.requiredSecrets = Set.copyOf(requiredSecrets);
            this.jobs = List.copyOf(jobs);
            validateGraph();
        }

        private void validateGraph() {
            Map<String, JobDefinition> index = new HashMap<>();

            for (JobDefinition job : jobs) {
                if (index.putIfAbsent(job.name(), job) != null) {
                    throw new AutomationException(
                            "Duplicate job name: " + job.name());
                }
            }

            for (JobDefinition job : jobs) {
                for (String dependency : job.needs()) {
                    if (!index.containsKey(dependency)) {
                        throw new AutomationException(
                                "Unknown dependency " + dependency);
                    }
                }
            }

            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();

            for (String jobName : index.keySet()) {
                visit(jobName, index, visited, active);
            }
        }

        private void visit(
                String name,
                Map<String, JobDefinition> index,
                Set<String> visited,
                Set<String> active) {
            if (active.contains(name)) {
                throw new AutomationException(
                        "Dependency cycle involving " + name);
            }
            if (!visited.add(name)) {
                return;
            }

            active.add(name);
            for (String dependency : index.get(name).needs()) {
                visit(dependency, index, visited, active);
            }
            active.remove(name);
        }

        WorkflowReport invoke(
                Map<String, String> suppliedInputs,
                Map<String, String> suppliedSecrets,
                Map<String, String> environment,
                CompositeAction action) {

            Map<String, String> inputs = contract.resolve(suppliedInputs);

            for (String secretName : requiredSecrets) {
                String value = suppliedSecrets.get(secretName);
                if (value == null || value.isBlank()) {
                    throw new AutomationException(
                            "Missing required secret: " + secretName);
                }
            }

            ExecutionContext context =
                    new ExecutionContext(inputs, suppliedSecrets, environment);

            Map<String, ExecutionState> states = new LinkedHashMap<>();
            Map<String, String> errors = new LinkedHashMap<>();
            Map<String, JobDefinition> index = new LinkedHashMap<>();

            for (JobDefinition job : jobs) {
                states.put(job.name(), ExecutionState.PENDING);
                index.put(job.name(), job);
            }

            Set<String> remaining = new HashSet<>(index.keySet());

            while (!remaining.isEmpty()) {
                boolean progressed = false;

                for (String jobName : List.copyOf(remaining)) {
                    JobDefinition job = index.get(jobName);

                    boolean dependencyFailed = job.needs().stream()
                            .map(states::get)
                            .anyMatch(state ->
                                    state == ExecutionState.FAILED ||
                                    state == ExecutionState.SKIPPED);

                    if (dependencyFailed) {
                        states.put(jobName, ExecutionState.SKIPPED);
                        remaining.remove(jobName);
                        context.log("Skipped job " + jobName);
                        progressed = true;
                        continue;
                    }

                    boolean ready = job.needs().stream()
                            .allMatch(dependency ->
                                    states.get(dependency) ==
                                            ExecutionState.SUCCEEDED);

                    if (!ready) {
                        continue;
                    }

                    states.put(jobName, ExecutionState.RUNNING);
                    context.log("Starting job " + jobName);

                    try {
                        if (jobName.equals("release")) {
                            action.execute(
                                    Map.of(
                                            "version", context.input("version"),
                                            "target", context.input("target")
                                    ),
                                    context);
                        } else {
                            job.operation().accept(context);
                        }

                        states.put(jobName, ExecutionState.SUCCEEDED);
                        context.log("Completed job " + jobName);
                    } catch (RuntimeException error) {
                        states.put(jobName, ExecutionState.FAILED);
                        errors.put(jobName, error.getMessage());
                        context.log("Job " + jobName + " failed: " +
                                error.getMessage());
                    }

                    remaining.remove(jobName);
                    progressed = true;
                }

                if (!progressed) {
                    throw new AutomationException(
                            "Scheduler stalled for " + remaining);
                }
            }

            context.log("Workflow " + name + " reached a terminal state.");

            return new WorkflowReport(
                    states, errors, context.outputs(), context.logs());
        }
    }

    static String sha256(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();

            for (byte item : bytes) {
                result.append(String.format("%02x", item));
            }

            return result.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new AutomationException("SHA-256 is unavailable.", error);
        }
    }

    static CompositeAction createDeploymentAction() {
        InputContract contract = new InputContract(List.of(
                new InputDefinition("version", true, "", Set.of()),
                new InputDefinition(
                        "target", true, "", Set.of("staging", "production"))
        ));

        return new CompositeAction(
                "deploy-service",
                contract,
                List.of(
                        new NamedStep("validate revision", context -> {
                            String sha = context.environment("GITHUB_SHA");
                            if (!sha.matches("[0-9a-fA-F]{7,64}")) {
                                throw new AutomationException(
                                        "Invalid commit revision.");
                            }
                            context.log("Commit revision validated.");
                        }),
                        new NamedStep("create artifact metadata", context -> {
                            String version = context.input("version");

                            if (!version.matches("\\d+\\.\\d+\\.\\d+")) {
                                throw new AutomationException(
                                        "Invalid semantic release version.");
                            }

                            String revision =
                                    context.environment("GITHUB_SHA").substring(0, 12);

                            context.output(
                                    "artifact",
                                    "service-" + version + "-" + revision + ".tar");
                        }),
                        new NamedStep("authorize destination", context -> {
                            String target = context.input("target");
                            String token = context.environment("DEPLOY_TOKEN");

                            if (token.length() < 16) {
                                throw new AutomationException(
                                        "Deployment credential is too short.");
                            }

                            if (target.equals("production") &&
                                    !context.environment("PRODUCTION_APPROVED")
                                            .equals("true")) {
                                throw new AutomationException(
                                        "Production approval is required.");
                            }

                            context.output("deployment-target", target);
                            context.log("Deployment destination authorized.");
                        }),
                        new NamedStep("record audit reference", context -> {
                            String artifact = context.output("artifact");
                            context.output("audit-reference", sha256(artifact));
                        })
                ),
                Set.of("artifact", "deployment-target", "audit-reference")
        );
    }

    static ReusableWorkflow createReleaseWorkflow() {
        InputContract contract = new InputContract(List.of(
                new InputDefinition("version", true, "", Set.of()),
                new InputDefinition(
                        "target", false, "staging",
                        Set.of("staging", "production"))
        ));

        return new ReusableWorkflow(
                "shared-release-workflow",
                contract,
                Set.of("DEPLOY_TOKEN"),
                List.of(
                        new JobDefinition(
                                "test",
                                List.of(),
                                context -> context.log(
                                        "Release validation checks passed.")),
                        new JobDefinition(
                                "release",
                                List.of("test"),
                                context -> context.log(
                                        "Release action was invoked.")),
                        new JobDefinition(
                                "audit",
                                List.of("release"),
                                context -> {
                                    if (context.output("artifact") == null) {
                                        throw new AutomationException(
                                                "No release artifact to audit.");
                                    }
                                    context.output("audit-state", "recorded");
                                })
                )
        );
    }

    static void printReport(WorkflowReport report) {
        System.out.println("Job states:");
        report.states().forEach((name, state) ->
                System.out.println("  " + name + ": " + state));

        if (!report.errors().isEmpty()) {
            System.out.println("Errors:");
            report.errors().forEach((name, error) ->
                    System.out.println("  " + name + ": " + error));
        }

        System.out.println("Outputs:");
        report.outputs().forEach((name, value) ->
                System.out.println("  " + name + ": " + value));

        System.out.println("Execution log:");
        report.logs().forEach(line -> System.out.println("  " + line));
    }

    public static void main(String[] args) {
        CompositeAction action = createDeploymentAction();
        ReusableWorkflow workflow = createReleaseWorkflow();

        Map<String, String> secrets =
                Map.of("DEPLOY_TOKEN", "local-demo-secret-12345");

        Map<String, String> environment = Map.of(
                "GITHUB_SHA",
                "b712af45cdef0123456789abcdef0123456789ab",
                "PRODUCTION_APPROVED",
                "false"
        );

        System.out.println("Successful staging release");
        WorkflowReport staging = workflow.invoke(
                Map.of("version", "3.2.0"),
                secrets,
                environment,
                action);
        printReport(staging);

        if (staging.states().get("release") != ExecutionState.SUCCEEDED) {
            throw new AssertionError("Expected staging release to succeed.");
        }

        System.out.println("\nProduction release without approval");
        WorkflowReport production = workflow.invoke(
                Map.of("version", "3.2.0", "target", "production"),
                secrets,
                environment,
                action);
        printReport(production);

        if (production.states().get("release") != ExecutionState.FAILED ||
                production.states().get("audit") != ExecutionState.SKIPPED) {
            throw new AssertionError("Production policy failure was not enforced.");
        }

        try {
            workflow.invoke(
                    Map.of("version", "3.2.0", "unexpected", "value"),
                    secrets,
                    environment,
                    action);
            throw new AssertionError("Unknown inputs should have been rejected.");
        } catch (AutomationException expected) {
            System.out.println("\nUnknown workflow input rejected correctly.");
        }

        try {
            workflow.invoke(
                    Map.of("version", "3.2.0"),
                    Map.of(),
                    environment,
                    action);
            throw new AssertionError("Missing secrets should have been rejected.");
        } catch (AutomationException expected) {
            System.out.println("Missing deployment secret rejected correctly.");
        }
    }
}

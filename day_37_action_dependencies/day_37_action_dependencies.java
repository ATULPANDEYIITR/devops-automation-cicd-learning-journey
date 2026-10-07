import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.BiPredicate;
import java.util.function.Function;

/**
 * Enterprise-oriented GitHub Actions dependency and conditional-execution
 * model.
 *
 * Java 17+.
 */
public class ActionsDependencyEngine {

    enum JobStatus {
        PENDING,
        RUNNING,
        SUCCESS,
        FAILURE,
        SKIPPED,
        CANCELLED
    }

    enum EventType {
        PUSH,
        PULL_REQUEST,
        WORKFLOW_DISPATCH
    }

    record WorkflowEvent(
        EventType type,
        String branch,
        boolean releaseEnabled
    ) {}

    record JobResult(
        String jobName,
        JobStatus status,
        String message,
        Map<String, String> outputs
    ) {
        JobResult {
            outputs = Collections.unmodifiableMap(
                new LinkedHashMap<>(outputs)
            );
        }

        boolean successful() {
            return status == JobStatus.SUCCESS;
        }

        boolean terminal() {
            return EnumSet.of(
                JobStatus.SUCCESS,
                JobStatus.FAILURE,
                JobStatus.SKIPPED,
                JobStatus.CANCELLED
            ).contains(status);
        }
    }

    @FunctionalInterface
    interface JobAction {
        JobResult execute(
            String jobName,
            Map<String, JobResult> dependencies
        ) throws Exception;
    }

    record JobDefinition(
        String name,
        List<String> needs,
        BiPredicate<Map<String, JobResult>, WorkflowEvent> condition,
        JobAction action,
        boolean allowFailure
    ) {
        JobDefinition {
            Objects.requireNonNull(name, "name");

            needs = List.copyOf(needs);

            if (needs.contains(name)) {
                throw new IllegalArgumentException(
                    "A job cannot depend on itself: " + name
                );
            }

            Objects.requireNonNull(action, "action");
        }
    }

    static final class WorkflowValidationException
        extends RuntimeException {

        WorkflowValidationException(String message) {
            super(message);
        }
    }

    static final class WorkflowExecutionException
        extends RuntimeException {

        WorkflowExecutionException(String message) {
            super(message);
        }
    }

    static final class Workflow {

        private final String name;

        private final Map<String, JobDefinition> jobs =
            new LinkedHashMap<>();

        Workflow(String name) {
            this.name = name;
        }

        void addJob(JobDefinition job) {
            if (jobs.containsKey(job.name())) {
                throw new WorkflowValidationException(
                    "Duplicate job: " + job.name()
                );
            }

            jobs.put(job.name(), job);
        }

        void validate() {
            for (JobDefinition job : jobs.values()) {
                for (String dependency : job.needs()) {
                    if (!jobs.containsKey(dependency)) {
                        throw new WorkflowValidationException(
                            "Job '" + job.name()
                            + "' references missing dependency '"
                            + dependency + "'"
                        );
                    }
                }
            }

            Map<String, Integer> states = new HashMap<>();

            for (String name : jobs.keySet()) {
                states.put(name, 0);
            }

            for (String name : jobs.keySet()) {
                visit(name, states);
            }
        }

        private void visit(
            String name,
            Map<String, Integer> states
        ) {
            int state = states.get(name);

            if (state == 1) {
                throw new WorkflowValidationException(
                    "Dependency cycle detected at " + name
                );
            }

            if (state == 2) {
                return;
            }

            states.put(name, 1);

            for (String dependency : jobs.get(name).needs()) {
                visit(dependency, states);
            }

            states.put(name, 2);
        }

        List<String> executionOrder() {
            Map<String, Integer> indegree =
                new LinkedHashMap<>();

            Map<String, List<String>> dependents =
                new LinkedHashMap<>();

            for (String name : jobs.keySet()) {
                indegree.put(name, 0);
                dependents.put(name, new ArrayList<>());
            }

            for (JobDefinition job : jobs.values()) {
                for (String dependency : job.needs()) {
                    indegree.put(
                        job.name(),
                        indegree.get(job.name()) + 1
                    );

                    dependents.get(dependency).add(job.name());
                }
            }

            Deque<String> ready = new ArrayDeque<>();

            for (Map.Entry<String, Integer> entry :
                indegree.entrySet()) {

                if (entry.getValue() == 0) {
                    ready.add(entry.getKey());
                }
            }

            List<String> order = new ArrayList<>();

            while (!ready.isEmpty()) {
                String current = ready.removeFirst();
                order.add(current);

                for (String dependent :
                    dependents.get(current)) {

                    int remaining =
                        indegree.get(dependent) - 1;

                    indegree.put(dependent, remaining);

                    if (remaining == 0) {
                        ready.addLast(dependent);
                    }
                }
            }

            if (order.size() != jobs.size()) {
                throw new WorkflowValidationException(
                    "Unable to construct an acyclic execution order."
                );
            }

            return order;
        }

        Map<String, JobResult> execute(
            WorkflowEvent event
        ) {
            validate();

            Map<String, JobResult> results =
                new LinkedHashMap<>();

            for (String name : executionOrder()) {
                JobDefinition job = jobs.get(name);

                Map<String, JobResult> dependencies =
                    dependencyResults(job, results);

                boolean defaultEligible =
                    job.needs().stream()
                        .allMatch(
                            dependency ->
                                dependencies.get(dependency)
                                    .successful()
                        );

                boolean eligible = defaultEligible;

                if (job.condition() != null) {
                    eligible =
                        job.condition().test(results, event);
                }

                if (!eligible) {
                    results.put(
                        name,
                        new JobResult(
                            name,
                            JobStatus.SKIPPED,
                            "Job condition was false.",
                            Map.of()
                        )
                    );
                    continue;
                }

                try {
                    JobResult result =
                        job.action().execute(
                            name,
                            dependencies
                        );

                    results.put(name, result);
                } catch (Exception error) {
                    JobStatus status =
                        JobStatus.FAILURE;

                    String message =
                        error.getMessage() == null
                            ? error.getClass().getSimpleName()
                            : error.getMessage();

                    results.put(
                        name,
                        new JobResult(
                            name,
                            status,
                            job.allowFailure()
                                ? "Failure allowed: " + message
                                : message,
                            Map.of()
                        )
                    );
                }
            }

            return results;
        }

        private Map<String, JobResult> dependencyResults(
            JobDefinition job,
            Map<String, JobResult> results
        ) {
            Map<String, JobResult> dependencies =
                new LinkedHashMap<>();

            for (String dependency : job.needs()) {
                dependencies.put(
                    dependency,
                    results.get(dependency)
                );
            }

            return dependencies;
        }
    }

    static JobAction successfulAction(String message) {
        return (jobName, dependencies) ->
            new JobResult(
                jobName,
                JobStatus.SUCCESS,
                message,
                Map.of()
            );
    }

    static JobAction buildAction() {
        return (jobName, dependencies) ->
            new JobResult(
                jobName,
                JobStatus.SUCCESS,
                "Build artifact generated.",
                Map.of(
                    "artifact",
                    "release/application.tar.gz",
                    "commit",
                    "a91b7f2"
                )
            );
    }

    static JobAction testAction() {
        return (jobName, dependencies) -> {
            JobResult build = dependencies.get("build");

            if (build == null || !build.successful()) {
                throw new IllegalStateException(
                    "Tests require a successful build."
                );
            }

            if (!build.outputs().containsKey("artifact")) {
                throw new IllegalStateException(
                    "Build did not publish an artifact."
                );
            }

            return new JobResult(
                jobName,
                JobStatus.SUCCESS,
                "Automated test suite passed.",
                Map.of("coverage", "93.8")
            );
        };
    }

    static JobAction securityAction() {
        return (jobName, dependencies) ->
            new JobResult(
                jobName,
                JobStatus.SUCCESS,
                "Security policy checks passed.",
                Map.of("critical", "0")
            );
    }

    static JobAction packageAction() {
        return (jobName, dependencies) -> {
            for (JobResult result : dependencies.values()) {
                if (!result.successful()) {
                    throw new IllegalStateException(
                        "Packaging received an unsuccessful dependency."
                    );
                }
            }

            return new JobResult(
                jobName,
                JobStatus.SUCCESS,
                "Release candidate assembled.",
                Map.of("candidate", "release-2026.10")
            );
        };
    }

    static JobAction deployAction() {
        return (jobName, dependencies) -> {
            JobResult candidate =
                dependencies.get("package");

            if (candidate == null ||
                !candidate.successful()) {

                throw new IllegalStateException(
                    "Deployment requires a successful package."
                );
            }

            return new JobResult(
                jobName,
                JobStatus.SUCCESS,
                "Production deployment completed.",
                Map.of("environment", "production")
            );
        };
    }

    static void printReport(
        Map<String, JobResult> results
    ) {
        System.out.println("\nJob execution report");
        System.out.println(
            String.format(
                "%-26s %-12s %s",
                "Job",
                "Status",
                "Message"
            )
        );

        System.out.println("-".repeat(75));

        for (JobResult result : results.values()) {
            System.out.println(
                String.format(
                    "%-26s %-12s %s",
                    result.jobName(),
                    result.status(),
                    result.message()
                )
            );
        }
    }

    static Workflow createEnterpriseWorkflow() {
        Workflow workflow =
            new Workflow("enterprise-release");

        workflow.addJob(
            new JobDefinition(
                "build",
                List.of(),
                null,
                buildAction(),
                false
            )
        );

        workflow.addJob(
            new JobDefinition(
                "unit-tests",
                List.of("build"),
                null,
                testAction(),
                false
            )
        );

        workflow.addJob(
            new JobDefinition(
                "security",
                List.of("build"),
                null,
                securityAction(),
                false
            )
        );

        workflow.addJob(
            new JobDefinition(
                "package",
                List.of(
                    "unit-tests",
                    "security"
                ),
                null,
                packageAction(),
                false
            )
        );

        /*
         * The production policy is modeled separately from dependency
         * ordering. The package must succeed, and the event must represent a
         * main-branch push with release capability enabled.
         */
        workflow.addJob(
            new JobDefinition(
                "deploy",
                List.of("package"),
                (results, event) ->
                    event.type() == EventType.PUSH
                    && event.branch().equals("main")
                    && event.releaseEnabled()
                    && results.get("package").successful(),
                deployAction(),
                false
            )
        );

        /*
         * Diagnostics deliberately use a condition that does not require
         * successful dependencies. This models cleanup or reporting work
         * that should remain useful after an upstream failure.
         */
        workflow.addJob(
            new JobDefinition(
                "diagnostics",
                List.of("deploy"),
                (results, event) -> true,
                successfulAction(
                    "Deployment state recorded for diagnostics."
                ),
                true
            )
        );

        return workflow;
    }

    static void demonstrateNormalRelease() {
        System.out.println(
            "\n=== Main branch release ==="
        );

        Workflow workflow =
            createEnterpriseWorkflow();

        WorkflowEvent event =
            new WorkflowEvent(
                EventType.PUSH,
                "main",
                true
            );

        printReport(workflow.execute(event));
    }

    static void demonstratePullRequestPath() {
        System.out.println(
            "\n=== Pull request validation ==="
        );

        Workflow workflow =
            createEnterpriseWorkflow();

        WorkflowEvent event =
            new WorkflowEvent(
                EventType.PULL_REQUEST,
                "feature/payment-validation",
                false
            );

        printReport(workflow.execute(event));
    }

    static void demonstrateInvalidGraph() {
        System.out.println(
            "\n=== Invalid dependency graph ==="
        );

        Workflow workflow =
            new Workflow("invalid");

        workflow.addJob(
            new JobDefinition(
                "build",
                List.of("tests"),
                null,
                successfulAction("Build."),
                false
            )
        );

        workflow.addJob(
            new JobDefinition(
                "tests",
                List.of("build"),
                null,
                successfulAction("Tests."),
                false
            )
        );

        try {
            workflow.validate();
        } catch (WorkflowValidationException error) {
            System.out.println(
                "Validation rejected workflow: "
                + error.getMessage()
            );
        }
    }

    static void demonstrateMatrixAggregation() {
        System.out.println(
            "\n=== Matrix-style validation policy ==="
        );

        record MatrixResult(
            String runner,
            boolean passed
        ) {}

        List<MatrixResult> matrix = List.of(
            new MatrixResult("ubuntu-java17", true),
            new MatrixResult("ubuntu-java21", true),
            new MatrixResult("windows-java21", true),
            new MatrixResult("macos-java21", false)
        );

        boolean allPassed =
            matrix.stream().allMatch(
                MatrixResult::passed
            );

        for (MatrixResult result : matrix) {
            System.out.println(
                String.format(
                    "%-24s %s",
                    result.runner(),
                    result.passed()
                        ? "PASS"
                        : "FAIL"
                )
            );
        }

        System.out.println(
            "Aggregate gate: "
            + (allPassed ? "OPEN" : "BLOCKED")
        );
    }

    public static void main(String[] args) {
        try {
            System.out.println(
                "GitHub Actions Job Dependencies and "
                + "Conditional Execution"
            );

            System.out.println(
                "=".repeat(58)
            );

            demonstrateNormalRelease();
            demonstratePullRequestPath();
            demonstrateInvalidGraph();
            demonstrateMatrixAggregation();

            System.out.println(
                "\nArchitectural rule: dependency edges determine "
                + "ordering; conditions determine eligibility."
            );
        } catch (RuntimeException error) {
            System.err.println(
                "Workflow execution failed: "
                + error.getMessage()
            );
            System.exit(1);
        }
    }
}

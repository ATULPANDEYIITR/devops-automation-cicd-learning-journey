import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Actions Matrix Builds
 *
 * Enterprise-oriented model of a multi-version CI matrix.
 *
 * The program demonstrates:
 * - explicit domain types for matrix dimensions
 * - matrix expansion
 * - compatibility policies
 * - job state transitions
 * - validation
 * - experimental/canary jobs
 * - merge-blocking failures
 * - immutable records
 * - service-oriented evaluation
 *
 * Compile:
 *   javac MatrixBuildGovernance.java
 *
 * Run:
 *   java MatrixBuildGovernance
 */
public class MatrixBuildGovernance {

    enum PythonVersion {
        V3_10("3.10"),
        V3_11("3.11"),
        V3_12("3.12"),
        V3_13("3.13");

        private final String value;

        PythonVersion(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    enum OperatingSystem {
        UBUNTU,
        WINDOWS,
        MACOS
    }

    enum DependencyMode {
        MINIMUM,
        LOCKED,
        LATEST
    }

    enum JobState {
        PENDING,
        RUNNING,
        PASSED,
        FAILED,
        CANCELLED
    }

    record MatrixJob(
            PythonVersion python,
            OperatingSystem operatingSystem,
            DependencyMode dependencyMode,
            boolean experimental
    ) {
        public MatrixJob {
            Objects.requireNonNull(python);
            Objects.requireNonNull(operatingSystem);
            Objects.requireNonNull(dependencyMode);
        }

        String key() {
            return python + "/" +
                   operatingSystem.name().toLowerCase() + "/" +
                   dependencyMode.name().toLowerCase();
        }

        String artifactName() {
            return "test-results-" +
                   python.value().replace(".", "") + "-" +
                   operatingSystem.name().toLowerCase() + "-" +
                   dependencyMode.name().toLowerCase();
        }
    }

    record CompatibilityFailure(
            String reason
    ) {
    }

    record JobResult(
            MatrixJob job,
            JobState state,
            int attempts,
            String message
    ) {
        boolean blockingFailure() {
            return state == JobState.FAILED && !job.experimental();
        }
    }

    static final class MatrixDefinition {
        private final Set<PythonVersion> pythonVersions;
        private final Set<OperatingSystem> operatingSystems;
        private final Set<DependencyMode> dependencyModes;
        private final Set<String> exclusions;

        MatrixDefinition(
                Set<PythonVersion> pythonVersions,
                Set<OperatingSystem> operatingSystems,
                Set<DependencyMode> dependencyModes,
                Set<String> exclusions) {

            if (pythonVersions.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one Python version is required.");
            }

            if (operatingSystems.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one operating system is required.");
            }

            if (dependencyModes.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one dependency mode is required.");
            }

            this.pythonVersions =
                    EnumSet.copyOf(pythonVersions);
            this.operatingSystems =
                    EnumSet.copyOf(operatingSystems);
            this.dependencyModes =
                    EnumSet.copyOf(dependencyModes);
            this.exclusions =
                    Set.copyOf(exclusions);
        }

        List<MatrixJob> expand() {
            List<MatrixJob> jobs = new ArrayList<>();

            for (PythonVersion python : pythonVersions) {
                for (OperatingSystem operatingSystem : operatingSystems) {
                    for (DependencyMode dependencyMode : dependencyModes) {
                        MatrixJob job = new MatrixJob(
                                python,
                                operatingSystem,
                                dependencyMode,
                                false
                        );

                        if (!exclusions.contains(job.key())) {
                            jobs.add(job);
                        }
                    }
                }
            }

            return jobs;
        }
    }

    static final class CompatibilityPolicy {
        CompatibilityFailure evaluate(MatrixJob job) {
            if (job.python() == PythonVersion.V3_10 &&
                job.dependencyMode() == DependencyMode.LATEST) {

                return new CompatibilityFailure(
                        "Latest dependencies do not support Python 3.10."
                );
            }

            if (job.operatingSystem() == OperatingSystem.WINDOWS &&
                job.python() == PythonVersion.V3_10) {

                return new CompatibilityFailure(
                        "Legacy Windows compatibility test failed."
                );
            }

            if (job.operatingSystem() == OperatingSystem.MACOS &&
                job.python() == PythonVersion.V3_13) {

                return new CompatibilityFailure(
                        "Native extension compatibility failed on macOS."
                );
            }

            if (job.python() == PythonVersion.V3_13 &&
                job.dependencyMode() == DependencyMode.MINIMUM) {

                return new CompatibilityFailure(
                        "Minimum dependency policy is incompatible with Python 3.13."
                );
            }

            return null;
        }
    }

    static final class MatrixEvaluationService {
        private final CompatibilityPolicy policy;
        private final boolean failFast;

        MatrixEvaluationService(
                CompatibilityPolicy policy,
                boolean failFast) {

            this.policy = policy;
            this.failFast = failFast;
        }

        List<JobResult> evaluate(List<MatrixJob> jobs) {
            List<JobResult> results = new ArrayList<>();
            boolean blockingFailure = false;

            for (MatrixJob job : jobs) {
                if (failFast &&
                    blockingFailure &&
                    !job.experimental()) {

                    results.add(new JobResult(
                            job,
                            JobState.CANCELLED,
                            0,
                            "Cancelled after a blocking matrix failure."
                    ));
                    continue;
                }

                results.add(evaluateJob(job));

                if (results.get(results.size() - 1).blockingFailure()) {
                    blockingFailure = true;
                }
            }

            return results;
        }

        private JobResult evaluateJob(MatrixJob job) {
            JobState state = JobState.PENDING;
            state = JobState.RUNNING;

            CompatibilityFailure failure = policy.evaluate(job);

            if (failure != null) {
                /*
                 * The state transition is explicit instead of encoding
                 * workflow policy through print statements.
                 */
                state = JobState.FAILED;

                return new JobResult(
                        job,
                        state,
                        1,
                        failure.reason()
                );
            }

            state = JobState.PASSED;

            return new JobResult(
                    job,
                    state,
                    1,
                    "All configured compatibility and test checks passed."
            );
        }
    }

    static final class ReportService {
        static void printMatrix(List<MatrixJob> jobs) {
            System.out.println("\nExpanded matrix");
            System.out.println("-".repeat(100));

            jobs.forEach(job ->
                    System.out.printf(
                            "%-34s %-14s %-14s%n",
                            job.key(),
                            job.experimental()
                                    ? "experimental"
                                    : "release-blocking",
                            job.artifactName()
                    )
            );
        }

        static void printResults(List<JobResult> results) {
            System.out.println("\nEvaluation results");
            System.out.println("-".repeat(110));

            results.forEach(result ->
                    System.out.printf(
                            "%-12s %-35s %-10d %s%n",
                            result.state(),
                            result.job().key(),
                            result.attempts(),
                            result.message()
                    )
            );
        }

        static void printStatistics(List<JobResult> results) {
            Map<JobState, Long> counts = results.stream()
                    .collect(Collectors.groupingBy(
                            JobResult::state,
                            Collectors.counting()
                    ));

            System.out.println("\nState statistics");
            System.out.println("-".repeat(60));

            for (JobState state : JobState.values()) {
                System.out.printf(
                        "%-12s %d%n",
                        state,
                        counts.getOrDefault(state, 0L)
                );
            }

            long blockingFailures = results.stream()
                    .filter(JobResult::blockingFailure)
                    .count();

            System.out.println(
                    "Release-blocking failures: " + blockingFailures
            );
        }
    }

    public static void main(String[] args) {
        Set<String> exclusions = new HashSet<>();
        exclusions.add(
                "3.10/macos/minimum"
        );
        exclusions.add(
                "3.13/windows/minimum"
        );

        MatrixDefinition definition = new MatrixDefinition(
                EnumSet.of(
                        PythonVersion.V3_10,
                        PythonVersion.V3_11,
                        PythonVersion.V3_12,
                        PythonVersion.V3_13
                ),
                EnumSet.of(
                        OperatingSystem.UBUNTU,
                        OperatingSystem.WINDOWS,
                        OperatingSystem.MACOS
                ),
                EnumSet.of(
                        DependencyMode.MINIMUM,
                        DependencyMode.LOCKED,
                        DependencyMode.LATEST
                ),
                exclusions
        );

        List<MatrixJob> jobs = definition.expand();

        /*
         * A canary is deliberately marked experimental. Its result remains
         * visible, but the governance layer does not treat its failure as a
         * release-blocking failure.
         */
        jobs = new ArrayList<>(jobs);

        int existingIndex = jobs.indexOf(
                new MatrixJob(
                        PythonVersion.V3_13,
                        OperatingSystem.UBUNTU,
                        DependencyMode.LATEST,
                        false
                )
        );

        if (existingIndex >= 0) {
            jobs.set(
                    existingIndex,
                    new MatrixJob(
                            PythonVersion.V3_13,
                            OperatingSystem.UBUNTU,
                            DependencyMode.LATEST,
                            true
                    )
            );
        }

        ReportService.printMatrix(jobs);

        CompatibilityPolicy compatibilityPolicy =
                new CompatibilityPolicy();

        MatrixEvaluationService service =
                new MatrixEvaluationService(
                        compatibilityPolicy,
                        false
                );

        List<JobResult> results = service.evaluate(jobs);

        ReportService.printResults(results);
        ReportService.printStatistics(results);

        long blockingFailures = results.stream()
                .filter(JobResult::blockingFailure)
                .count();

        System.out.println("\nWorkflow conclusion: " +
                (blockingFailures == 0 ? "SUCCESS" : "FAILURE"));

        System.out.println(
                "\nEnterprise design point: the matrix definition describes "
                + "coverage, the compatibility policy describes valid "
                + "combinations, and the evaluation service decides the "
                + "state of each concrete job."
        );
    }
}

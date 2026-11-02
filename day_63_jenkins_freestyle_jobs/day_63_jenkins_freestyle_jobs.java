import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class JenkinsFreestyleJobDemo {

    enum JobStatus {
        ENABLED,
        DISABLED
    }

    enum BuildStatus {
        SUCCESS,
        FAILURE,
        ABORTED
    }

    enum TriggerType {
        MANUAL,
        TIMER,
        SCM,
        UPSTREAM
    }

    static class JobException extends Exception {
        JobException(String message) {
            super(message);
        }
    }

    record ParameterDefinition(
        String name,
        String defaultValue,
        boolean required,
        Set<String> choices
    ) {
        ParameterDefinition {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Parameter name cannot be empty"
                );
            }

            choices = Set.copyOf(choices);
        }

        String validate(String value) throws JobException {
            String normalized =
                value == null ? "" : value.trim();

            if (required && normalized.isEmpty()) {
                throw new JobException(
                    "Parameter " + name +
                    " cannot be empty"
                );
            }

            if (!choices.isEmpty() &&
                !choices.contains(normalized)) {
                throw new JobException(
                    "Invalid value for " + name +
                    ": " + normalized
                );
            }

            return normalized;
        }
    }

    record Build(
        int number,
        Map<String, String> parameters,
        BuildStatus status,
        Path workspace,
        List<String> log
    ) {}

    interface BuildStep {
        void execute(
            Map<String, String> parameters,
            Path workspace,
            List<String> log
        ) throws Exception;
    }

    interface TriggerPolicy {
        boolean accepts(TriggerType trigger);
    }

    static final class FreestyleJob {
        private final String name;
        private final String description;
        private final Path workspaceRoot;

        private JobStatus status = JobStatus.ENABLED;

        private final Map<String, ParameterDefinition> parameters =
            new HashMap<>();

        private final EnumSet<TriggerType> triggers =
            EnumSet.noneOf(TriggerType.class);

        private final List<BuildStep> buildSteps =
            new ArrayList<>();

        private final List<Build> builds =
            new ArrayList<>();

        FreestyleJob(
            String name,
            String description,
            Path workspaceRoot
        ) {
            this.name = name;
            this.description = description;
            this.workspaceRoot = workspaceRoot;
        }

        void addParameter(ParameterDefinition parameter)
            throws JobException {
            if (parameters.containsKey(parameter.name())) {
                throw new JobException(
                    "Duplicate parameter: " +
                    parameter.name()
                );
            }

            parameters.put(parameter.name(), parameter);
        }

        void addTrigger(TriggerType trigger) {
            triggers.add(trigger);
        }

        void addBuildStep(BuildStep step) {
            buildSteps.add(step);
        }

        private Map<String, String> resolveParameters(
            Map<String, String> supplied
        ) throws JobException {
            for (String key : supplied.keySet()) {
                if (!parameters.containsKey(key)) {
                    throw new JobException(
                        "Unknown parameter: " + key
                    );
                }
            }

            Map<String, String> result = new HashMap<>();

            for (ParameterDefinition definition :
                parameters.values()) {

                String raw = supplied.containsKey(definition.name())
                    ? supplied.get(definition.name())
                    : definition.defaultValue();

                result.put(
                    definition.name(),
                    definition.validate(raw)
                );
            }

            return Map.copyOf(result);
        }

        Build run(
            Map<String, String> supplied,
            TriggerType trigger
        ) throws JobException {
            if (status != JobStatus.ENABLED) {
                throw new JobException("Job is disabled");
            }

            if (trigger != TriggerType.MANUAL &&
                !triggers.contains(trigger)) {
                throw new JobException(
                    "Trigger is not configured: " +
                    trigger
                );
            }

            Map<String, String> resolved =
                resolveParameters(supplied);

            int number = builds.size() + 1;

            Path workspace =
                workspaceRoot
                    .resolve(name)
                    .resolve("build-" + number);

            try {
                Files.createDirectories(workspace);
            } catch (IOException error) {
                throw new JobException(
                    "Cannot create workspace: " +
                    error.getMessage()
                );
            }

            List<String> log = new ArrayList<>();

            log.add(
                "BUILD #" + number +
                " started by " + trigger + " trigger"
            );

            log.add(
                "Workspace: " + workspace
            );

            BuildStatus buildStatus = BuildStatus.SUCCESS;

            try {
                for (BuildStep step : buildSteps) {
                    step.execute(
                        resolved,
                        workspace,
                        log
                    );
                }

                log.add("Build completed successfully");
            } catch (Exception error) {
                buildStatus = BuildStatus.FAILURE;
                log.add(
                    "Build failed: " +
                    error.getMessage()
                );
            }

            Build build = new Build(
                number,
                resolved,
                buildStatus,
                workspace,
                List.copyOf(log)
            );

            builds.add(build);
            return build;
        }

        List<Build> builds() {
            return List.copyOf(builds);
        }
    }

    static final class ManifestStep implements BuildStep {
        @Override
        public void execute(
            Map<String, String> parameters,
            Path workspace,
            List<String> log
        ) throws IOException {
            StringBuilder content =
                new StringBuilder("Freestyle build manifest\n");

            parameters.entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry ->
                    content
                        .append(entry.getKey())
                        .append("=")
                        .append(entry.getValue())
                        .append('\n')
                );

            Files.writeString(
                workspace.resolve("manifest.txt"),
                content
            );

            log.add("Created manifest.txt");
        }
    }

    static final class ReleasePolicyStep implements BuildStep {
        @Override
        public void execute(
            Map<String, String> parameters,
            Path workspace,
            List<String> log
        ) throws JobException {
            String environment =
                parameters.get("ENVIRONMENT");

            String version =
                parameters.get("VERSION");

            if (
                "production".equals(environment) &&
                version.startsWith("dev-")
            ) {
                throw new JobException(
                    "Production builds cannot use " +
                    "development versions"
                );
            }

            log.add(
                "Release policy passed for " +
                environment
            );
        }
    }

    static final class ArtifactStep implements BuildStep {
        @Override
        public void execute(
            Map<String, String> parameters,
            Path workspace,
            List<String> log
        ) throws IOException {
            String filename =
                "application-" +
                parameters.get("VERSION") +
                "-" +
                parameters.get("ENVIRONMENT") +
                ".txt";

            String content =
                "Freestyle build artifact\n" +
                "version=" +
                parameters.get("VERSION") +
                "\n" +
                "environment=" +
                parameters.get("ENVIRONMENT") +
                "\n";

            Files.writeString(
                workspace.resolve(filename),
                content
            );

            log.add("Created artifact: " + filename);
        }
    }

    static void printBuild(Build build) {
        System.out.println(
            "\nBuild #" + build.number() +
            ": " + build.status()
        );

        build.parameters().entrySet()
            .stream()
            .sorted(Map.Entry.comparingByKey())
            .forEach(entry ->
                System.out.println(
                    "  " +
                    entry.getKey() +
                    "=" +
                    entry.getValue()
                )
            );

        build.log().forEach(
            line -> System.out.println("  " + line)
        );
    }

    public static void main(String[] args) throws Exception {
        Path root =
            Files.createTempDirectory(
                "jenkins-freestyle-java-"
            );

        FreestyleJob job = new FreestyleJob(
            "release-application",
            "Parameterized enterprise Freestyle job",
            root
        );

        job.addParameter(
            new ParameterDefinition(
                "ENVIRONMENT",
                "staging",
                true,
                Set.of(
                    "development",
                    "staging",
                    "production"
                )
            )
        );

        job.addParameter(
            new ParameterDefinition(
                "VERSION",
                "1.0.0",
                true,
                Set.of()
            )
        );

        job.addTrigger(TriggerType.TIMER);
        job.addTrigger(TriggerType.SCM);
        job.addTrigger(TriggerType.UPSTREAM);

        job.addBuildStep(new ManifestStep());
        job.addBuildStep(new ReleasePolicyStep());
        job.addBuildStep(new ArtifactStep());

        Build first = job.run(
            Map.of(
                "ENVIRONMENT", "staging",
                "VERSION", "1.4.0"
            ),
            TriggerType.SCM
        );

        if (first.status() != BuildStatus.SUCCESS) {
            throw new IllegalStateException(
                "Expected first build to succeed"
            );
        }

        Build second = job.run(
            Map.of(
                "ENVIRONMENT", "production",
                "VERSION", "dev-2.0.0"
            ),
            TriggerType.UPSTREAM
        );

        if (second.status() != BuildStatus.FAILURE) {
            throw new IllegalStateException(
                "Expected invalid production build to fail"
            );
        }

        Build third = job.run(
            Map.of(
                "ENVIRONMENT", "production",
                "VERSION", "2.0.0"
            ),
            TriggerType.MANUAL
        );

        if (third.status() != BuildStatus.SUCCESS) {
            throw new IllegalStateException(
                "Expected valid production build to succeed"
            );
        }

        System.out.println(
            "Jenkins Freestyle Job Simulation"
        );
        System.out.println(
            "================================"
        );
        System.out.println("Job: " + job.name);
        System.out.println(
            "Build count: " + job.builds().size()
        );

        job.builds().forEach(
            JenkinsFreestyleJobDemo::printBuild
        );

        System.out.println(
            "\nWorkspace root: " + root
        );
    }
}

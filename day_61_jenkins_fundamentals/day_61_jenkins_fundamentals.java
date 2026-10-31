import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

public class JenkinsFundamentals {

    enum JobType {
        FREESTYLE,
        PIPELINE
    }

    enum BuildState {
        QUEUED,
        RUNNING,
        SUCCESS,
        FAILURE,
        ABORTED
    }

    enum AgentState {
        ONLINE,
        OFFLINE
    }

    enum ReviewLevel {
        STANDARD,
        PRODUCTION
    }

    record Commit(String sha, String message) {
        Commit {
            Objects.requireNonNull(sha, "sha");
            Objects.requireNonNull(message, "message");

            if (!sha.matches("[0-9a-fA-F]{7,40}")) {
                throw new IllegalArgumentException(
                    "Commit SHA must contain 7 to 40 hexadecimal characters."
                );
            }

            if (message.isBlank()) {
                throw new IllegalArgumentException(
                    "Commit message cannot be blank."
                );
            }
        }
    }

    record JobPolicy(
        Set<String> requiredLabels,
        ReviewLevel reviewLevel,
        int requiredStatusChecks
    ) {
        JobPolicy {
            requiredLabels = Set.copyOf(requiredLabels);

            if (requiredStatusChecks < 0) {
                throw new IllegalArgumentException(
                    "Required status checks cannot be negative."
                );
            }
        }
    }

    static final class Build {
        private final UUID id = UUID.randomUUID();
        private final int number;
        private final String jobName;
        private final Commit commit;
        private final List<String> logs = new ArrayList<>();

        private BuildState state = BuildState.QUEUED;
        private String agentName;
        private Path workspace;

        Build(int number, String jobName, Commit commit) {
            this.number = number;
            this.jobName = Objects.requireNonNull(jobName);
            this.commit = Objects.requireNonNull(commit);
        }

        UUID id() {
            return id;
        }

        int number() {
            return number;
        }

        String jobName() {
            return jobName;
        }

        Commit commit() {
            return commit;
        }

        BuildState state() {
            return state;
        }

        void transition(BuildState newState) {
            if (!isValidTransition(state, newState)) {
                throw new IllegalStateException(
                    "Invalid build transition: " + state + " -> " + newState
                );
            }
            state = newState;
        }

        void assignAgent(String name) {
            this.agentName = name;
        }

        String agentName() {
            return agentName;
        }

        void assignWorkspace(Path workspace) {
            this.workspace = workspace;
        }

        Path workspace() {
            return workspace;
        }

        void log(String message) {
            logs.add(message);
        }

        List<String> logs() {
            return List.copyOf(logs);
        }

        private static boolean isValidTransition(
            BuildState from,
            BuildState to
        ) {
            return switch (from) {
                case QUEUED ->
                    EnumSet.of(BuildState.RUNNING, BuildState.ABORTED)
                        .contains(to);
                case RUNNING ->
                    EnumSet.of(
                        BuildState.SUCCESS,
                        BuildState.FAILURE,
                        BuildState.ABORTED
                    ).contains(to);
                case SUCCESS, FAILURE, ABORTED -> false;
            };
        }
    }

    static final class Agent {
        private final String name;
        private final Set<String> labels;
        private final int executors;
        private AgentState state;
        private final Map<UUID, Build> activeBuilds = new HashMap<>();

        Agent(
            String name,
            Set<String> labels,
            int executors,
            AgentState state
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Agent name cannot be blank."
                );
            }
            if (executors < 1) {
                throw new IllegalArgumentException(
                    "Executors must be positive."
                );
            }

            this.name = name;
            this.labels = Set.copyOf(labels);
            this.executors = executors;
            this.state = state;
        }

        String name() {
            return name;
        }

        boolean compatible(Set<String> requiredLabels) {
            return state == AgentState.ONLINE
                && activeBuilds.size() < executors
                && labels.containsAll(requiredLabels);
        }

        void start(Build build) {
            if (!compatible(Set.of())) {
                throw new IllegalStateException(
                    "Agent cannot accept another build."
                );
            }
            activeBuilds.put(build.id(), build);
        }

        void finish(Build build) {
            activeBuilds.remove(build.id());
        }

        int activeCount() {
            return activeBuilds.size();
        }

        int executors() {
            return executors;
        }

        void setState(AgentState state) {
            this.state = state;
        }
    }

    static final class Job {
        private final String name;
        private final JobType type;
        private final JobPolicy policy;
        private final boolean enabled;
        private int nextBuildNumber = 1;
        private final List<Build> history = new ArrayList<>();

        Job(
            String name,
            JobType type,
            JobPolicy policy,
            boolean enabled
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Job name cannot be blank."
                );
            }

            this.name = name;
            this.type = type;
            this.policy = policy;
            this.enabled = enabled;
        }

        String name() {
            return name;
        }

        JobType type() {
            return type;
        }

        JobPolicy policy() {
            return policy;
        }

        boolean enabled() {
            return enabled;
        }

        Build createBuild(Commit commit) {
            return new Build(nextBuildNumber++, name, commit);
        }

        void record(Build build) {
            history.add(build);
        }

        List<Build> history() {
            return List.copyOf(history);
        }
    }

    interface BuildPolicy {
        void validate(Job job, Build build) throws BuildRejectedException;
    }

    static final class BuildRejectedException extends Exception {
        BuildRejectedException(String message) {
            super(message);
        }
    }

    static final class EnterprisePolicy implements BuildPolicy {
        @Override
        public void validate(Job job, Build build)
            throws BuildRejectedException {

            if (job.policy().reviewLevel() == ReviewLevel.PRODUCTION
                && build.commit().message().contains("[UNREVIEWED]")) {
                throw new BuildRejectedException(
                    "Production policy rejects an unreviewed change."
                );
            }

            if (job.policy().requiredStatusChecks() > 0
                && build.commit().message().contains("[CHECK-FAIL]")) {
                throw new BuildRejectedException(
                    "Required status checks failed."
                );
            }

            if (build.commit().message().contains("[FAIL]")) {
                throw new BuildRejectedException(
                    "Commit requested the failure test path."
                );
            }
        }
    }

    static final class JenkinsController {
        private final Map<String, Job> jobs = new HashMap<>();
        private final Map<String, Agent> agents = new HashMap<>();
        private final Deque<Build> queue = new ArrayDeque<>();
        private final BuildPolicy policy;
        private final Path workspaceRoot;

        JenkinsController(BuildPolicy policy, Path workspaceRoot) {
            this.policy = policy;
            this.workspaceRoot = workspaceRoot;
        }

        void registerJob(Job job) {
            if (jobs.putIfAbsent(job.name(), job) != null) {
                throw new IllegalArgumentException(
                    "Duplicate job: " + job.name()
                );
            }
        }

        void registerAgent(Agent agent) {
            if (agents.putIfAbsent(agent.name(), agent) != null) {
                throw new IllegalArgumentException(
                    "Duplicate agent: " + agent.name()
                );
            }
        }

        void schedule(String jobName, Commit commit) {
            Job job = requireJob(jobName);

            if (!job.enabled()) {
                throw new IllegalStateException(
                    "Job is disabled: " + jobName
                );
            }

            queue.addLast(job.createBuild(commit));
        }

        private Job requireJob(String name) {
            Job job = jobs.get(name);
            if (job == null) {
                throw new IllegalArgumentException(
                    "Unknown job: " + name
                );
            }
            return job;
        }

        private Optional<Agent> selectAgent(Job job) {
            return agents.values()
                .stream()
                .filter(agent -> agent.compatible(job.policy().requiredLabels()))
                .min(
                    Comparator.comparingInt(Agent::activeCount)
                );
        }

        private Path allocateWorkspace(
            Agent agent,
            Build build
        ) throws IOException {

            String safeJobName = build.jobName()
                .replaceAll("[^A-Za-z0-9._-]", "_");

            Path directory = workspaceRoot
                .resolve(agent.name())
                .resolve(safeJobName + "-" + build.number());

            Files.createDirectories(directory);
            return directory;
        }

        private void checkout(
            Build build
        ) throws IOException, BuildRejectedException {

            Path commitFile = build.workspace().resolve("commit.txt");

            Files.writeString(
                commitFile,
                build.commit().sha() + System.lineSeparator()
                    + build.commit().message(),
                StandardCharsets.UTF_8
            );

            String stored = Files.readString(
                commitFile,
                StandardCharsets.UTF_8
            );

            if (!stored.startsWith(build.commit().sha())) {
                throw new BuildRejectedException(
                    "Checkout integrity validation failed."
                );
            }

            build.log("Checkout and integrity validation passed.");
        }

        boolean runNext() {
            Build selected = null;
            Agent selectedAgent = null;

            for (Build candidate : queue) {
                Job job = requireJob(candidate.jobName());

                Optional<Agent> agent = selectAgent(job);

                if (agent.isPresent()) {
                    selected = candidate;
                    selectedAgent = agent.get();
                    break;
                }
            }

            if (selected == null || selectedAgent == null) {
                return false;
            }

            queue.remove(selected);

            Job job = requireJob(selected.jobName());

            try {
                selected.transition(BuildState.RUNNING);
                selected.assignAgent(selectedAgent.name());
                selectedAgent.start(selected);

                selected.assignWorkspace(
                    allocateWorkspace(selectedAgent, selected)
                );

                selected.log(
                    "Controller assigned the build to "
                        + selectedAgent.name() + "."
                );

                checkout(selected);
                policy.validate(job, selected);

                selected.log(
                    "Enterprise policy validation passed for "
                        + job.type() + " job."
                );

                selected.transition(BuildState.SUCCESS);
                selected.log("Build completed successfully.");
            } catch (BuildRejectedException | IOException ex) {
                if (selected.state() == BuildState.RUNNING) {
                    selected.transition(BuildState.FAILURE);
                }
                selected.log("Build failed: " + ex.getMessage());
            } finally {
                selectedAgent.finish(selected);
                job.record(selected);
            }

            return true;
        }

        void runAll() {
            while (!queue.isEmpty()) {
                if (!runNext()) {
                    throw new IllegalStateException(
                        "No compatible executor is available for queued work."
                    );
                }
            }
        }

        void printReport() {
            System.out.println("Jenkins Enterprise Governance Model");
            System.out.println("===================================");

            jobs.values().forEach(job -> {
                System.out.println(
                    "\nJob: " + job.name()
                        + " [" + job.type() + "]"
                );

                job.history().forEach(build -> {
                    System.out.println(
                        "  #" + build.number()
                            + " state=" + build.state()
                            + " agent=" + build.agentName()
                            + " workspace=" + build.workspace()
                    );

                    build.logs().forEach(
                        log -> System.out.println("    " + log)
                    );
                });
            });

            System.out.println("\nAgents");
            agents.values().forEach(agent ->
                System.out.println(
                    "  " + agent.name()
                        + ": " + agent.activeCount()
                        + "/" + agent.executors()
                        + " executors busy"
                )
            );

            System.out.println("\nQueued builds: " + queue.size());
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("jenkins-java17-");

        try {
            JenkinsController controller =
                new JenkinsController(
                    new EnterprisePolicy(),
                    root
                );

            controller.registerAgent(
                new Agent(
                    "linux-python",
                    Set.of("linux", "python", "container"),
                    2,
                    AgentState.ONLINE
                )
            );

            controller.registerAgent(
                new Agent(
                    "linux-java",
                    Set.of("linux", "java"),
                    1,
                    AgentState.ONLINE
                )
            );

            controller.registerAgent(
                new Agent(
                    "offline-python",
                    Set.of("linux", "python"),
                    1,
                    AgentState.OFFLINE
                )
            );

            controller.registerJob(
                new Job(
                    "python-service",
                    JobType.PIPELINE,
                    new JobPolicy(
                        Set.of("linux", "python"),
                        ReviewLevel.STANDARD,
                        1
                    ),
                    true
                )
            );

            controller.registerJob(
                new Job(
                    "java-production",
                    JobType.FREESTYLE,
                    new JobPolicy(
                        Set.of("linux", "java"),
                        ReviewLevel.PRODUCTION,
                        2
                    ),
                    true
                )
            );

            controller.schedule(
                "python-service",
                new Commit(
                    "a1b2c3d4",
                    "Validate configuration"
                )
            );

            controller.schedule(
                "python-service",
                new Commit(
                    "e5f6a7b8",
                    "[FAIL] exercise failure handling"
                )
            );

            controller.schedule(
                "java-production",
                new Commit(
                    "11223344",
                    "Release production validation"
                )
            );

            controller.runAll();
            controller.printReport();

            List<Build> allBuilds =
                controller.jobs.values()
                    .stream()
                    .flatMap(job -> job.history().stream())
                    .collect(Collectors.toList());

            if (allBuilds.size() != 3) {
                throw new IllegalStateException(
                    "Expected exactly three completed builds."
                );
            }

            long failures = allBuilds
                .stream()
                .filter(build -> build.state() == BuildState.FAILURE)
                .count();

            if (failures != 1) {
                throw new IllegalStateException(
                    "Expected exactly one failure."
                );
            }

            System.out.println("\nValidation checks passed.");
        } finally {
            try (var paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder())
                    .forEach(path -> {
                        try {
                            Files.deleteIfExists(path);
                        } catch (IOException ignored) {
                            // Temporary cleanup failure does not alter build results.
                        }
                    });
            }
        }
    }
}

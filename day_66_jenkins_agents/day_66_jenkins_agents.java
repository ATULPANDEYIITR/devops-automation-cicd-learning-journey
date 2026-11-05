import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Jenkins distributed build infrastructure.
 *
 * Enterprise-oriented model of:
 * - Controller and agent separation.
 * - Static and dynamic agent lifecycle.
 * - Label-based workload routing.
 * - Executor allocation.
 * - Provisioning policies.
 * - Build state transitions.
 * - Failure handling.
 * - Infrastructure reporting.
 *
 * Java 17, no third-party dependencies.
 */
public class JenkinsAgents {

    enum AgentType {
        STATIC,
        DYNAMIC
    }

    enum AgentStatus {
        ONLINE,
        BUSY,
        OFFLINE,
        TERMINATED
    }

    enum BuildStatus {
        QUEUED,
        RUNNING,
        SUCCESS,
        FAILED,
        CANCELLED
    }

    enum BuildPriority {
        LOW,
        NORMAL,
        HIGH,
        CRITICAL
    }

    static class JenkinsException extends RuntimeException {
        JenkinsException(String message) {
            super(message);
        }
    }

    record BuildRequest(
        String id,
        String jobName,
        Set<String> labels,
        int estimatedSeconds,
        BuildPriority priority,
        int maxRetries
    ) {
        BuildRequest {
            Objects.requireNonNull(id);
            Objects.requireNonNull(jobName);
            Objects.requireNonNull(labels);
            Objects.requireNonNull(priority);

            if (id.isBlank() || jobName.isBlank()) {
                throw new IllegalArgumentException(
                    "Build ID and job name are required."
                );
            }

            if (labels.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one label is required."
                );
            }

            if (estimatedSeconds <= 0 || maxRetries < 0) {
                throw new IllegalArgumentException(
                    "Invalid build execution parameters."
                );
            }

            labels = Set.copyOf(labels);

            for (String label : labels) {
                if (!label.matches("[a-zA-Z0-9_.-]+")) {
                    throw new IllegalArgumentException(
                        "Invalid label: " + label
                    );
                }
            }
        }

        static BuildRequest create(
            String jobName,
            Set<String> labels,
            int seconds,
            BuildPriority priority
        ) {
            return new BuildRequest(
                UUID.randomUUID().toString(),
                jobName,
                labels,
                seconds,
                priority,
                1
            );
        }
    }

    static final class BuildExecution {
        private final BuildRequest request;
        private BuildStatus status = BuildStatus.QUEUED;
        private String agentId;
        private int attempts;
        private String failureReason;
        private Instant startedAt;
        private Instant completedAt;

        BuildExecution(BuildRequest request) {
            this.request = Objects.requireNonNull(request);
        }

        BuildRequest request() {
            return request;
        }

        BuildStatus status() {
            return status;
        }

        String agentId() {
            return agentId;
        }

        int attempts() {
            return attempts;
        }

        String failureReason() {
            return failureReason;
        }

        void start(String agentId) {
            if (status != BuildStatus.QUEUED) {
                throw new JenkinsException(
                    "Only queued builds can start."
                );
            }

            this.agentId = agentId;
            this.attempts++;
            this.startedAt = Instant.now();
            this.status = BuildStatus.RUNNING;
        }

        void succeed() {
            requireRunning();
            status = BuildStatus.SUCCESS;
            completedAt = Instant.now();
            failureReason = null;
        }

        boolean fail(String reason) {
            requireRunning();

            failureReason = Objects.requireNonNull(reason);
            completedAt = Instant.now();

            if (attempts <= request.maxRetries()) {
                status = BuildStatus.QUEUED;
                agentId = null;
                return true;
            }

            status = BuildStatus.FAILED;
            return false;
        }

        void cancel() {
            if (
                status != BuildStatus.QUEUED &&
                status != BuildStatus.RUNNING
            ) {
                throw new JenkinsException(
                    "Build is already in a final state."
                );
            }

            status = BuildStatus.CANCELLED;
            completedAt = Instant.now();
        }

        private void requireRunning() {
            if (status != BuildStatus.RUNNING) {
                throw new JenkinsException(
                    "Build must be running for this transition."
                );
            }
        }
    }

    static final class Agent {
        private final String id;
        private final AgentType type;
        private final Set<String> labels;
        private final int executors;
        private final int maxBuilds;

        private int completedBuilds;
        private AgentStatus status = AgentStatus.ONLINE;

        private final Set<String> activeBuildIds = new HashSet<>();

        Agent(
            String id,
            AgentType type,
            Set<String> labels,
            int executors,
            int maxBuilds
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                    "Agent ID is required."
                );
            }

            if (
                executors <= 0 ||
                maxBuilds <= 0 ||
                labels == null ||
                labels.isEmpty()
            ) {
                throw new IllegalArgumentException(
                    "Invalid agent configuration."
                );
            }

            this.id = id;
            this.type = Objects.requireNonNull(type);
            this.labels = Set.copyOf(labels);
            this.executors = executors;
            this.maxBuilds = maxBuilds;
        }

        String id() {
            return id;
        }

        AgentType type() {
            return type;
        }

        AgentStatus status() {
            return status;
        }

        Set<String> activeBuildIds() {
            return Set.copyOf(activeBuildIds);
        }

        boolean supports(Set<String> required) {
            return labels.containsAll(required);
        }

        boolean available() {
            return status == AgentStatus.ONLINE
                && activeBuildIds.size() < executors
                && completedBuilds + activeBuildIds.size() < maxBuilds;
        }

        void assign(String buildId) {
            if (!available()) {
                throw new JenkinsException(
                    "Agent has no available executor."
                );
            }

            if (!activeBuildIds.add(buildId)) {
                throw new JenkinsException(
                    "Build is already assigned to this agent."
                );
            }

            status = AgentStatus.BUSY;
        }

        void release(String buildId) {
            if (!activeBuildIds.remove(buildId)) {
                throw new JenkinsException(
                    "Build assignment does not exist."
                );
            }

            completedBuilds++;

            if (activeBuildIds.isEmpty()) {
                status = AgentStatus.ONLINE;
            }
        }

        void offline() {
            if (!activeBuildIds.isEmpty()) {
                throw new JenkinsException(
                    "Cannot offline an agent with active builds."
                );
            }

            if (status == AgentStatus.TERMINATED) {
                throw new JenkinsException(
                    "Agent has been terminated."
                );
            }

            status = AgentStatus.OFFLINE;
        }

        void terminate() {
            if (type != AgentType.DYNAMIC) {
                throw new JenkinsException(
                    "Static agents cannot be dynamically terminated."
                );
            }

            if (!activeBuildIds.isEmpty()) {
                throw new JenkinsException(
                    "Cannot terminate an agent with active builds."
                );
            }

            status = AgentStatus.TERMINATED;
        }
    }

    interface AgentProvisioner {
        Agent provision(Set<String> requiredLabels);
        void terminate(Agent agent);
    }

    static final class CloudProvisioner implements AgentProvisioner {
        private final int maximumAgents;
        private final Map<String, Agent> provisioned =
            new LinkedHashMap<>();

        private int sequence = 1;

        CloudProvisioner(int maximumAgents) {
            if (maximumAgents < 0) {
                throw new IllegalArgumentException(
                    "Maximum agents cannot be negative."
                );
            }

            this.maximumAgents = maximumAgents;
        }

        @Override
        public Agent provision(Set<String> requiredLabels) {
            if (provisioned.size() >= maximumAgents) {
                throw new JenkinsException(
                    "Cloud provisioning capacity exhausted."
                );
            }

            String id = "cloud-agent-" + sequence++;

            Set<String> labels = new HashSet<>(requiredLabels);
            labels.add("ephemeral");

            Agent agent = new Agent(
                id,
                AgentType.DYNAMIC,
                labels,
                1,
                1
            );

            provisioned.put(id, agent);

            System.out.println("[PROVISIONED] " + id);
            return agent;
        }

        @Override
        public void terminate(Agent agent) {
            if (!provisioned.containsKey(agent.id())) {
                throw new JenkinsException(
                    "Agent is not managed by this provisioner."
                );
            }

            agent.terminate();
            provisioned.remove(agent.id());

            System.out.println("[TERMINATED] " + agent.id());
        }
    }

    static final class SchedulingPolicy {
        private final boolean preferStaticAgents;
        private final int maximumQueuedBuilds;

        SchedulingPolicy(
            boolean preferStaticAgents,
            int maximumQueuedBuilds
        ) {
            if (maximumQueuedBuilds <= 0) {
                throw new IllegalArgumentException(
                    "Queue capacity must be positive."
                );
            }

            this.preferStaticAgents = preferStaticAgents;
            this.maximumQueuedBuilds = maximumQueuedBuilds;
        }

        Comparator<Agent> comparator() {
            return Comparator
                .comparing(
                    (Agent agent) ->
                        preferStaticAgents &&
                        agent.type() == AgentType.DYNAMIC
                )
                .thenComparing(
                    agent -> -agent.activeBuildIds().size()
                );
        }
    }

    static final class JenkinsController {
        private final AgentProvisioner provisioner;
        private final SchedulingPolicy policy;

        private final Map<String, Agent> agents =
            new LinkedHashMap<>();

        private final Map<String, BuildExecution> builds =
            new LinkedHashMap<>();

        private final List<String> queue = new ArrayList<>();

        JenkinsController(
            AgentProvisioner provisioner,
            SchedulingPolicy policy
        ) {
            this.provisioner = Objects.requireNonNull(provisioner);
            this.policy = Objects.requireNonNull(policy);
        }

        void registerStaticAgent(Agent agent) {
            if (agent.type() != AgentType.STATIC) {
                throw new JenkinsException(
                    "Only static agents can be registered directly."
                );
            }

            if (agents.putIfAbsent(agent.id(), agent) != null) {
                throw new JenkinsException(
                    "Duplicate agent registration."
                );
            }
        }

        void submit(BuildRequest request) {
            if (builds.containsKey(request.id())) {
                throw new JenkinsException(
                    "Duplicate build request."
                );
            }

            if (queue.size() >= policy.maximumQueuedBuilds) {
                throw new JenkinsException(
                    "Build queue capacity exceeded."
                );
            }

            builds.put(
                request.id(),
                new BuildExecution(request)
            );

            queue.add(request.id());

            System.out.println(
                "[QUEUED] " + request.jobName()
            );
        }

        private Agent findCompatibleAgent(BuildRequest request) {
            return agents.values()
                .stream()
                .filter(Agent::available)
                .filter(agent -> agent.supports(request.labels()))
                .sorted(policy.comparator())
                .findFirst()
                .orElse(null);
        }

        private Agent acquireAgent(BuildRequest request) {
            Agent agent = findCompatibleAgent(request);

            if (agent != null) {
                return agent;
            }

            agent = provisioner.provision(request.labels());
            agents.put(agent.id(), agent);

            return agent;
        }

        int schedule() {
            int assigned = 0;

            List<String> pending = new ArrayList<>(queue);
            queue.clear();

            for (String buildId : pending) {
                BuildExecution execution = builds.get(buildId);

                if (execution.status() != BuildStatus.QUEUED) {
                    continue;
                }

                Agent agent;

                try {
                    agent = acquireAgent(execution.request());
                } catch (JenkinsException exception) {
                    queue.add(buildId);

                    System.out.println(
                        "[WAITING] " + execution.request().jobName()
                        + ": " + exception.getMessage()
                    );

                    continue;
                }

                if (!agent.available()) {
                    queue.add(buildId);
                    continue;
                }

                agent.assign(buildId);
                execution.start(agent.id());

                assigned++;

                System.out.println(
                    "[ASSIGNED] " +
                    execution.request().jobName() +
                    " -> " + agent.id()
                );
            }

            return assigned;
        }

        void complete(String buildId, boolean success) {
            BuildExecution execution = builds.get(buildId);

            if (execution == null) {
                throw new JenkinsException("Unknown build.");
            }

            if (execution.status() != BuildStatus.RUNNING) {
                throw new JenkinsException(
                    "Build is not running."
                );
            }

            Agent agent = agents.get(execution.agentId());

            agent.release(buildId);

            if (success) {
                execution.succeed();
            } else {
                boolean retry = execution.fail(
                    "Build execution returned a failure."
                );

                if (retry) {
                    queue.add(buildId);
                }
            }

            System.out.println(
                "[RESULT] " +
                execution.request().jobName() +
                " status=" + execution.status()
            );
        }

        void cancel(String buildId) {
            BuildExecution execution = builds.get(buildId);

            if (execution == null) {
                throw new JenkinsException("Unknown build.");
            }

            if (execution.status() == BuildStatus.RUNNING) {
                Agent agent = agents.get(execution.agentId());
                agent.release(buildId);
            } else if (execution.status() == BuildStatus.QUEUED) {
                queue.remove(buildId);
            }

            execution.cancel();
        }

        void cleanupDynamicAgents() {
            List<Agent> idleAgents = agents.values()
                .stream()
                .filter(agent -> agent.type() == AgentType.DYNAMIC)
                .filter(agent -> agent.status() == AgentStatus.ONLINE)
                .filter(agent -> agent.activeBuildIds().isEmpty())
                .toList();

            for (Agent agent : idleAgents) {
                provisioner.terminate(agent);
                agents.remove(agent.id());
            }
        }

        void validateAssignments() {
            for (Agent agent : agents.values()) {
                if (
                    agent.activeBuildIds().size() >
                    getExecutorCount(agent)
                ) {
                    throw new JenkinsException(
                        "Agent executor capacity exceeded."
                    );
                }

                for (String buildId : agent.activeBuildIds()) {
                    BuildExecution build = builds.get(buildId);

                    if (
                        build == null ||
                        build.status() != BuildStatus.RUNNING ||
                        !agent.id().equals(build.agentId())
                    ) {
                        throw new JenkinsException(
                            "Build-agent relationship is inconsistent."
                        );
                    }
                }
            }
        }

        private int getExecutorCount(Agent agent) {
            return agent.type() == AgentType.DYNAMIC ? 1 : 2;
        }

        void report() {
            System.out.println(
                "\n========== ENTERPRISE JENKINS REPORT =========="
            );

            for (Agent agent : agents.values()) {
                System.out.printf(
                    "%-20s type=%-7s status=%-10s active=%d labels=%s%n",
                    agent.id(),
                    agent.type(),
                    agent.status(),
                    agent.activeBuildIds().size(),
                    agent.labels
                );
            }

            Map<BuildStatus, Long> counts = builds.values()
                .stream()
                .collect(
                    Collectors.groupingBy(
                        BuildExecution::status,
                        Collectors.counting()
                    )
                );

            for (BuildStatus status : BuildStatus.values()) {
                System.out.println(
                    status + ": " + counts.getOrDefault(status, 0L)
                );
            }

            System.out.println("Queued builds: " + queue.size());
        }

        Map<String, BuildExecution> executions() {
            return Map.copyOf(builds);
        }
    }

    public static void main(String[] args) {
        try {
            CloudProvisioner provisioner =
                new CloudProvisioner(4);

            SchedulingPolicy policy =
                new SchedulingPolicy(true, 100);

            JenkinsController controller =
                new JenkinsController(provisioner, policy);

            controller.registerStaticAgent(
                new Agent(
                    "linux-static-01",
                    AgentType.STATIC,
                    Set.of("linux", "python", "docker"),
                    2,
                    1000
                )
            );

            controller.registerStaticAgent(
                new Agent(
                    "windows-static-01",
                    AgentType.STATIC,
                    Set.of("windows", "dotnet"),
                    2,
                    1000
                )
            );

            List<BuildRequest> requests = List.of(
                BuildRequest.create(
                    "Python Unit Tests",
                    Set.of("linux", "python"),
                    15,
                    BuildPriority.HIGH
                ),
                BuildRequest.create(
                    "Docker Image Build",
                    Set.of("linux", "docker"),
                    25,
                    BuildPriority.NORMAL
                ),
                BuildRequest.create(
                    "Windows Integration",
                    Set.of("windows", "dotnet"),
                    30,
                    BuildPriority.HIGH
                ),
                BuildRequest.create(
                    "Security Scan",
                    Set.of("linux", "security"),
                    20,
                    BuildPriority.CRITICAL
                ),
                BuildRequest.create(
                    "Cloud Deployment",
                    Set.of("linux", "deployment"),
                    35,
                    BuildPriority.NORMAL
                )
            );

            requests.forEach(controller::submit);

            System.out.println("\n--- First scheduling cycle ---");

            controller.schedule();
            controller.validateAssignments();

            System.out.println("\n--- Completing first cycle ---");

            controller.executions().values()
                .stream()
                .filter(
                    execution ->
                        execution.status() == BuildStatus.RUNNING
                )
                .toList()
                .forEach(execution ->
                    controller.complete(
                        execution.request().id(),
                        !execution.request().jobName()
                            .equals("Windows Integration")
                    )
                );

            System.out.println("\n--- Second scheduling cycle ---");

            controller.schedule();
            controller.validateAssignments();

            controller.executions().values()
                .stream()
                .filter(
                    execution ->
                        execution.status() == BuildStatus.RUNNING
                )
                .toList()
                .forEach(execution ->
                    controller.complete(
                        execution.request().id(),
                        true
                    )
                );

            controller.validateAssignments();
            controller.report();

            System.out.println("\n--- Dynamic agent cleanup ---");

            controller.cleanupDynamicAgents();
            controller.report();

        } catch (RuntimeException exception) {
            System.err.println(
                "Jenkins infrastructure error: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

public class JenkinsInstallationGovernance {

    enum ControllerState {
        NEW,
        VALIDATED,
        INSTALLED
    }

    enum PluginState {
        AVAILABLE,
        INSTALLED,
        REJECTED
    }

    enum ReviewState {
        APPROVED,
        CHANGES_REQUESTED,
        COMMENTED,
        PENDING
    }

    enum CheckState {
        PASSING,
        FAILING,
        PENDING
    }

    enum PullRequestState {
        DRAFT,
        OPEN,
        CLOSED,
        MERGED
    }

    static final class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static final class PluginException extends RuntimeException {
        PluginException(String message) {
            super(message);
        }
    }

    static final class MergeBlockedException extends RuntimeException {
        MergeBlockedException(String message) {
            super(message);
        }
    }

    record ControllerConfig(
        String name,
        String jenkinsVersion,
        int javaMajor,
        int httpPort,
        int executors,
        boolean csrfProtection,
        boolean anonymousRead,
        boolean allowSignup,
        String url
    ) {}

    record Plugin(
        String name,
        String version,
        int requiredJava,
        List<String> dependencies,
        boolean securityApproved
    ) {
        Plugin {
            Objects.requireNonNull(name);
            Objects.requireNonNull(version);
            dependencies = List.copyOf(dependencies);
        }
    }

    record CredentialRef(
        String id,
        String kind,
        String owner,
        String fingerprint
    ) {}

    record Review(
        String reviewer,
        ReviewState state,
        boolean eligible,
        boolean stale
    ) {}

    record StatusCheck(
        String name,
        CheckState state
    ) {}

    record BranchProtection(
        String branch,
        int requiredApprovals,
        Set<String> requiredChecks,
        boolean resolvedConversationsRequired,
        boolean directPushBlocked,
        boolean forcePushBlocked,
        boolean linearHistoryRequired
    ) {
        BranchProtection {
            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    record PullRequest(
        int number,
        String title,
        String sourceBranch,
        String targetBranch,
        String headCommit,
        List<Review> reviews,
        List<StatusCheck> checks,
        PullRequestState state,
        boolean conversationsResolved,
        boolean mergeConflict
    ) {
        PullRequest {
            reviews = List.copyOf(reviews);
            checks = List.copyOf(checks);
        }
    }

    record MergeDecision(
        boolean eligible,
        List<String> reasons
    ) {}

    interface PolicyRule {
        void evaluate(PullRequest pullRequest, BranchProtection policy);
    }

    static final class JenkinsController {
        private final ControllerConfig config;
        private ControllerState state = ControllerState.NEW;
        private final Map<String, Plugin> pluginCatalog = new HashMap<>();
        private final Set<String> installedPlugins = new HashSet<>();
        private final Map<String, CredentialRef> credentials = new HashMap<>();
        private final List<String> auditEvents = new ArrayList<>();

        JenkinsController(ControllerConfig config) {
            this.config = Objects.requireNonNull(config);
        }

        void validate() {
            if (config.javaMajor() < 17) {
                throw new ConfigurationException(
                    "Java 17 or later is required."
                );
            }

            if (config.httpPort() < 1024 ||
                config.httpPort() > 65535) {
                throw new ConfigurationException(
                    "HTTP port must be between 1024 and 65535."
                );
            }

            if (config.executors() < 1 ||
                config.executors() > 32) {
                throw new ConfigurationException(
                    "Executor count must be between 1 and 32."
                );
            }

            if (!config.csrfProtection()) {
                throw new ConfigurationException(
                    "CSRF protection cannot be disabled."
                );
            }

            if (config.anonymousRead() || config.allowSignup()) {
                throw new ConfigurationException(
                    "Anonymous access and public signup are disabled."
                );
            }

            if (!config.url().matches("^https?://.+/$")) {
                throw new ConfigurationException(
                    "Controller URL must end with '/'."
                );
            }

            state = ControllerState.VALIDATED;
            audit("controller.validated");
        }

        void install() {
            if (state != ControllerState.VALIDATED) {
                throw new ConfigurationException(
                    "Validation must occur before installation."
                );
            }

            state = ControllerState.INSTALLED;
            audit("controller.installed");
        }

        void registerPlugin(Plugin plugin) {
            if (pluginCatalog.containsKey(plugin.name())) {
                throw new PluginException(
                    "Duplicate plugin: " + plugin.name()
                );
            }

            pluginCatalog.put(plugin.name(), plugin);
        }

        void installPlugins(Set<String> requested) {
            if (state != ControllerState.INSTALLED) {
                throw new PluginException(
                    "Controller is not installed."
                );
            }

            ArrayDeque<String> visiting = new ArrayDeque<>();
            Set<String> visited = new HashSet<>();

            for (String name : requested) {
                resolvePlugin(
                    name,
                    visiting,
                    visited
                );
            }
        }

        private void resolvePlugin(
            String name,
            ArrayDeque<String> visiting,
            Set<String> visited
        ) {
            if (visited.contains(name)) {
                return;
            }

            if (visiting.contains(name)) {
                throw new PluginException(
                    "Circular dependency involving " + name
                );
            }

            Plugin plugin = pluginCatalog.get(name);

            if (plugin == null) {
                throw new PluginException(
                    "Unknown plugin: " + name
                );
            }

            if (plugin.requiredJava() > config.javaMajor()) {
                throw new PluginException(
                    "Plugin " + name +
                    " requires Java " +
                    plugin.requiredJava()
                );
            }

            if (!plugin.securityApproved()) {
                throw new PluginException(
                    "Plugin rejected by security policy: " + name
                );
            }

            visiting.push(name);

            for (String dependency : plugin.dependencies()) {
                resolvePlugin(
                    dependency,
                    visiting,
                    visited
                );
            }

            visiting.pop();
            visited.add(name);
            installedPlugins.add(name);

            audit(
                "plugin.installed:" +
                plugin.name() +
                ":" +
                plugin.version()
            );
        }

        void addCredential(
            String id,
            String kind,
            String owner,
            String fingerprint
        ) {
            if (!id.matches("[A-Za-z0-9._-]{3,64}")) {
                throw new ConfigurationException(
                    "Invalid credential identifier."
                );
            }

            if (fingerprint == null ||
                fingerprint.length() < 32) {
                throw new ConfigurationException(
                    "Credential fingerprint is invalid."
                );
            }

            if (credentials.containsKey(id)) {
                throw new ConfigurationException(
                    "Credential already exists."
                );
            }

            credentials.put(
                id,
                new CredentialRef(
                    id,
                    kind,
                    owner,
                    fingerprint
                )
            );

            audit("credential.registered:" + id);
        }

        boolean hasPlugin(String plugin) {
            return installedPlugins.contains(plugin);
        }

        private void audit(String event) {
            auditEvents.add(
                Instant.now() + " " + event
            );
        }

        List<String> auditEvents() {
            return Collections.unmodifiableList(auditEvents);
        }

        ControllerState state() {
            return state;
        }
    }

    static final class MergeEligibilityService {
        private final List<PolicyRule> rules;

        MergeEligibilityService() {
            rules = List.of(
                (pr, policy) -> {
                    if (pr.state() != PullRequestState.OPEN) {
                        throw new MergeBlockedException(
                            "Pull Request is not open."
                        );
                    }
                },
                (pr, policy) -> {
                    if (!pr.targetBranch().equals(policy.branch())) {
                        throw new MergeBlockedException(
                            "Pull Request targets a different branch."
                        );
                    }
                },
                (pr, policy) -> {
                    if (pr.mergeConflict()) {
                        throw new MergeBlockedException(
                            "Merge conflicts must be resolved."
                        );
                    }
                },
                (pr, policy) -> {
                    if (
                        policy.resolvedConversationsRequired() &&
                        !pr.conversationsResolved()
                    ) {
                        throw new MergeBlockedException(
                            "Review conversations remain unresolved."
                        );
                    }
                },
                (pr, policy) -> {
                    long approvals = pr.reviews()
                        .stream()
                        .filter(r ->
                            r.state() == ReviewState.APPROVED &&
                            r.eligible() &&
                            !r.stale()
                        )
                        .map(Review::reviewer)
                        .distinct()
                        .count();

                    if (approvals < policy.requiredApprovals()) {
                        throw new MergeBlockedException(
                            "Required approvals not satisfied: " +
                            approvals +
                            "/" +
                            policy.requiredApprovals()
                        );
                    }
                },
                (pr, policy) -> {
                    Map<String, CheckState> checks =
                        new HashMap<>();

                    pr.checks().forEach(
                        c -> checks.put(c.name(), c.state())
                    );

                    for (String required :
                        policy.requiredChecks()) {

                        if (
                            checks.get(required) !=
                            CheckState.PASSING
                        ) {
                            throw new MergeBlockedException(
                                "Required check is not passing: " +
                                required
                            );
                        }
                    }
                }
            );
        }

        MergeDecision evaluate(
            PullRequest pullRequest,
            BranchProtection policy
        ) {
            List<String> failures = new ArrayList<>();

            for (PolicyRule rule : rules) {
                try {
                    rule.evaluate(pullRequest, policy);
                } catch (MergeBlockedException error) {
                    failures.add(error.getMessage());
                }
            }

            return new MergeDecision(
                failures.isEmpty(),
                List.copyOf(failures)
            );
        }
    }

    static void require(
        boolean condition,
        String message
    ) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        ControllerConfig config = new ControllerConfig(
            "enterprise-controller",
            "2.5xx",
            21,
            8080,
            4,
            true,
            false,
            false,
            "http://localhost:8080/"
        );

        JenkinsController controller =
            new JenkinsController(config);

        controller.validate();
        controller.install();

        controller.registerPlugin(
            new Plugin(
                "git",
                "5.6.0",
                17,
                List.of(),
                true
            )
        );

        controller.registerPlugin(
            new Plugin(
                "credentials",
                "1400.1",
                17,
                List.of(),
                true
            )
        );

        controller.registerPlugin(
            new Plugin(
                "workflow-api",
                "1400.1",
                17,
                List.of(),
                true
            )
        );

        controller.registerPlugin(
            new Plugin(
                "workflow-job",
                "1500.1",
                17,
                List.of("workflow-api"),
                true
            )
        );

        controller.registerPlugin(
            new Plugin(
                "pipeline-model-definition",
                "2.22.0",
                17,
                List.of(
                    "workflow-job",
                    "credentials"
                ),
                true
            )
        );

        controller.installPlugins(
            Set.of(
                "git",
                "credentials",
                "pipeline-model-definition"
            )
        );

        controller.addCredential(
            "git-readonly",
            "username-password",
            "ci-service",
            "abcdef0123456789abcdef0123456789"
        );

        require(
            controller.state() == ControllerState.INSTALLED,
            "Controller was not installed."
        );

        require(
            controller.hasPlugin("pipeline-model-definition"),
            "Pipeline plugin was not installed."
        );

        BranchProtection policy =
            new BranchProtection(
                "main",
                2,
                Set.of(
                    "build",
                    "unit-tests",
                    "security-scan"
                ),
                true,
                true,
                true,
                true
            );

        PullRequest pullRequest =
            new PullRequest(
                1042,
                "Harden authentication pipeline",
                "feature/auth-hardening",
                "main",
                "a8e9d2",
                List.of(
                    new Review(
                        "alice",
                        ReviewState.APPROVED,
                        true,
                        false
                    ),
                    new Review(
                        "bob",
                        ReviewState.APPROVED,
                        true,
                        false
                    ),
                    new Review(
                        "automation-account",
                        ReviewState.APPROVED,
                        false,
                        false
                    )
                ),
                List.of(
                    new StatusCheck(
                        "build",
                        CheckState.PASSING
                    ),
                    new StatusCheck(
                        "unit-tests",
                        CheckState.PASSING
                    ),
                    new StatusCheck(
                        "security-scan",
                        CheckState.PASSING
                    )
                ),
                PullRequestState.OPEN,
                true,
                false
            );

        MergeEligibilityService service =
            new MergeEligibilityService();

        MergeDecision decision =
            service.evaluate(
                pullRequest,
                policy
            );

        System.out.println(
            "Initial merge eligibility: " +
            decision.eligible()
        );

        decision.reasons().forEach(
            reason -> System.out.println("- " + reason)
        );

        /*
         * A new commit can make an earlier approval stale.
         * The model explicitly evaluates current approval state rather
         * than assuming an approval remains valid indefinitely.
         */
        List<Review> staleReviews = new ArrayList<>(
            pullRequest.reviews()
        );

        staleReviews.set(
            1,
            new Review(
                "bob",
                ReviewState.APPROVED,
                true,
                true
            )
        );

        PullRequest afterNewCommit =
            new PullRequest(
                pullRequest.number(),
                pullRequest.title(),
                pullRequest.sourceBranch(),
                pullRequest.targetBranch(),
                "new-head-commit",
                staleReviews,
                pullRequest.checks(),
                PullRequestState.OPEN,
                pullRequest.conversationsResolved(),
                false
            );

        MergeDecision blockedDecision =
            service.evaluate(
                afterNewCommit,
                policy
            );

        System.out.println(
            "\nAfter approval becomes stale: " +
            blockedDecision.eligible()
        );

        blockedDecision.reasons().forEach(
            reason -> System.out.println("- " + reason)
        );

        System.out.println(
            "\nAudit events: " +
            controller.auditEvents().size()
        );
    }
}

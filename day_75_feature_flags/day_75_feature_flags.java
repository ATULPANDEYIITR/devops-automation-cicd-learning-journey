import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Feature Flag Enterprise Governance Platform.
 *
 * Java 17 implementation featuring:
 * - Immutable evaluation contexts
 * - Typed feature definitions
 * - Percentage rollout
 * - User and group targeting
 * - Environment isolation
 * - Version-based concurrency control
 * - Audit events
 * - Approval requirements
 * - Kill switches
 * - Expiration handling
 * - Service-oriented architecture
 */

public class Main {

    enum FlagType {
        BOOLEAN,
        PERCENTAGE,
        TARGETED
    }

    enum FlagStatus {
        ACTIVE,
        DISABLED,
        ARCHIVED
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum ChangeType {
        CREATE,
        ROLLOUT_CHANGE,
        ENABLE,
        DISABLE,
        ARCHIVE
    }

    record EvaluationContext(
        String userId,
        Environment environment,
        Set<String> groups,
        Map<String, String> attributes
    ) {
        public EvaluationContext {
            if (userId == null || userId.isBlank()) {
                throw new IllegalArgumentException(
                    "User ID is required"
                );
            }

            Objects.requireNonNull(environment);

            groups = Collections.unmodifiableSet(
                new HashSet<>(groups)
            );

            attributes = Collections.unmodifiableMap(
                new HashMap<>(attributes)
            );
        }
    }

    record AuditEvent(
        long id,
        String flagKey,
        String action,
        String actor,
        Instant timestamp,
        long version,
        String details
    ) {}

    record EvaluationResult(
        String flagKey,
        String userId,
        boolean enabled,
        String reason,
        long configurationVersion
    ) {}

    static final class FeatureFlagException
            extends RuntimeException {

        FeatureFlagException(String message) {
            super(message);
        }
    }

    static final class VersionConflictException
            extends FeatureFlagException {

        VersionConflictException(String message) {
            super(message);
        }
    }

    static final class FeatureFlag {

        private final String key;
        private final String description;
        private final FlagType type;
        private final FlagStatus status;

        private final Set<Environment> environments;
        private final Set<String> users;
        private final Set<String> groups;

        private final double percentage;
        private final boolean defaultValue;

        private final String owner;
        private final Instant expiresAt;
        private final long version;

        FeatureFlag(
            String key,
            String description,
            FlagType type,
            FlagStatus status,
            Set<Environment> environments,
            Set<String> users,
            Set<String> groups,
            double percentage,
            boolean defaultValue,
            String owner,
            Instant expiresAt,
            long version
        ) {
            this.key = key;
            this.description = description;
            this.type = type;
            this.status = status;

            this.environments = Set.copyOf(environments);
            this.users = Set.copyOf(users);
            this.groups = Set.copyOf(groups);

            this.percentage = percentage;
            this.defaultValue = defaultValue;

            this.owner = owner;
            this.expiresAt = expiresAt;
            this.version = version;

            validate();
        }

        private void validate() {
            if (key == null ||
                !key.matches("[a-zA-Z][a-zA-Z0-9_-]*")) {
                throw new FeatureFlagException(
                    "Invalid feature flag key"
                );
            }

            if (!Double.isFinite(percentage) ||
                percentage < 0 || percentage > 100) {
                throw new FeatureFlagException(
                    "Invalid rollout percentage"
                );
            }

            if (environments.isEmpty()) {
                throw new FeatureFlagException(
                    "At least one environment is required"
                );
            }

            if (owner == null || owner.isBlank()) {
                throw new FeatureFlagException(
                    "Flag owner is required"
                );
            }

            if (version < 1) {
                throw new FeatureFlagException(
                    "Invalid configuration version"
                );
            }
        }

        boolean isExpired() {
            return expiresAt != null &&
                !Instant.now().isBefore(expiresAt);
        }

        String getKey() {
            return key;
        }

        String getDescription() {
            return description;
        }

        FlagType getType() {
            return type;
        }

        FlagStatus getStatus() {
            return status;
        }

        Set<Environment> getEnvironments() {
            return environments;
        }

        Set<String> getUsers() {
            return users;
        }

        Set<String> getGroups() {
            return groups;
        }

        double getPercentage() {
            return percentage;
        }

        boolean getDefaultValue() {
            return defaultValue;
        }

        String getOwner() {
            return owner;
        }

        long getVersion() {
            return version;
        }

        Instant getExpiresAt() {
            return expiresAt;
        }

        FeatureFlag with(
            FlagType newType,
            FlagStatus newStatus,
            double newPercentage,
            long newVersion
        ) {
            return new FeatureFlag(
                key,
                description,
                newType,
                newStatus,
                environments,
                users,
                groups,
                newPercentage,
                defaultValue,
                owner,
                expiresAt,
                newVersion
            );
        }
    }

    interface FlagRepository {
        FeatureFlag findByKey(String key);

        void save(FeatureFlag flag);

        List<FeatureFlag> findAll();
    }

    static final class InMemoryFlagRepository
            implements FlagRepository {

        private final Map<String, FeatureFlag> storage =
            new HashMap<>();

        @Override
        public synchronized FeatureFlag findByKey(String key) {
            return storage.get(key);
        }

        @Override
        public synchronized void save(FeatureFlag flag) {
            storage.put(flag.getKey(), flag);
        }

        @Override
        public synchronized List<FeatureFlag> findAll() {
            return List.copyOf(storage.values());
        }
    }

    static final class AuditService {

        private final AtomicLong sequence = new AtomicLong();

        private final List<AuditEvent> events =
            new CopyOnWriteArrayList<>();

        private final List<Consumer<AuditEvent>> listeners =
            new CopyOnWriteArrayList<>();

        void subscribe(Consumer<AuditEvent> listener) {
            listeners.add(listener);
        }

        void record(
            String key,
            String action,
            String actor,
            long version,
            String details
        ) {
            AuditEvent event = new AuditEvent(
                sequence.incrementAndGet(),
                key,
                action,
                actor,
                Instant.now(),
                version,
                details
            );

            events.add(event);

            listeners.forEach(listener -> listener.accept(event));
        }

        List<AuditEvent> getEvents() {
            return List.copyOf(events);
        }
    }

    static final class RolloutPolicy {

        private static final long UINT32_RANGE =
            0x1_0000_0000L;

        double bucket(String key, String userId) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                byte[] hash = digest.digest(
                    (key + ":" + userId).getBytes(
                        StandardCharsets.UTF_8
                    )
                );

                long value =
                    ((long) (hash[0] & 0xff) << 24) |
                    ((long) (hash[1] & 0xff) << 16) |
                    ((long) (hash[2] & 0xff) << 8) |
                    (long) (hash[3] & 0xff);

                return (double) value /
                    UINT32_RANGE * 100.0;

            } catch (NoSuchAlgorithmException error) {
                throw new FeatureFlagException(
                    "Hashing algorithm unavailable"
                );
            }
        }

        boolean evaluate(
            FeatureFlag flag,
            EvaluationContext context
        ) {
            if (flag.getUsers().contains(context.userId())) {
                return true;
            }

            if (!Collections.disjoint(
                flag.getGroups(),
                context.groups()
            )) {
                return true;
            }

            return switch (flag.getType()) {
                case BOOLEAN -> flag.getDefaultValue();
                case TARGETED -> false;
                case PERCENTAGE ->
                    bucket(flag.getKey(), context.userId())
                        < flag.getPercentage();
            };
        }
    }

    static final class ApprovalPolicy {

        private final int requiredApprovals;
        private final Set<String> authorizedReleaseManagers;

        ApprovalPolicy(
            int requiredApprovals,
            Set<String> authorizedReleaseManagers
        ) {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Approval count cannot be negative"
                );
            }

            this.requiredApprovals = requiredApprovals;

            this.authorizedReleaseManagers =
                Set.copyOf(authorizedReleaseManagers);
        }

        boolean canModify(
            String actor,
            int receivedApprovals
        ) {
            return authorizedReleaseManagers.contains(actor)
                && receivedApprovals >= requiredApprovals;
        }
    }

    static final class FeatureFlagService {

        private final FlagRepository repository;
        private final RolloutPolicy rolloutPolicy;
        private final ApprovalPolicy approvalPolicy;
        private final AuditService auditService;

        FeatureFlagService(
            FlagRepository repository,
            RolloutPolicy rolloutPolicy,
            ApprovalPolicy approvalPolicy,
            AuditService auditService
        ) {
            this.repository = repository;
            this.rolloutPolicy = rolloutPolicy;
            this.approvalPolicy = approvalPolicy;
            this.auditService = auditService;
        }

        void register(FeatureFlag flag, String actor) {
            if (repository.findByKey(flag.getKey()) != null) {
                throw new FeatureFlagException(
                    "Feature flag already exists"
                );
            }

            repository.save(flag);

            auditService.record(
                flag.getKey(),
                "CREATED",
                actor,
                flag.getVersion(),
                "Initial configuration"
            );
        }

        EvaluationResult evaluate(
            String key,
            EvaluationContext context
        ) {
            FeatureFlag flag = repository.findByKey(key);

            if (flag == null) {
                return new EvaluationResult(
                    key,
                    context.userId(),
                    false,
                    "UNKNOWN_FLAG",
                    0
                );
            }

            if (flag.getStatus() != FlagStatus.ACTIVE) {
                return result(flag, context, false, "INACTIVE");
            }

            if (flag.isExpired()) {
                return result(flag, context, false, "EXPIRED");
            }

            if (!flag.getEnvironments().contains(
                context.environment()
            )) {
                return result(
                    flag,
                    context,
                    false,
                    "ENVIRONMENT_NOT_ALLOWED"
                );
            }

            boolean enabled = rolloutPolicy.evaluate(
                flag,
                context
            );

            return result(
                flag,
                context,
                enabled,
                enabled ? "MATCHED" : "NOT_TARGETED"
            );
        }

        private EvaluationResult result(
            FeatureFlag flag,
            EvaluationContext context,
            boolean enabled,
            String reason
        ) {
            return new EvaluationResult(
                flag.getKey(),
                context.userId(),
                enabled,
                reason,
                flag.getVersion()
            );
        }

        synchronized void updateRollout(
            String key,
            double percentage,
            long expectedVersion,
            String actor,
            int approvals
        ) {
            FeatureFlag current = requireFlag(key);

            if (current.getVersion() != expectedVersion) {
                throw new VersionConflictException(
                    "Configuration version conflict"
                );
            }

            if (!approvalPolicy.canModify(actor, approvals)) {
                throw new FeatureFlagException(
                    "Release policy approval denied"
                );
            }

            FeatureFlag updated = current.with(
                FlagType.PERCENTAGE,
                current.getStatus(),
                percentage,
                current.getVersion() + 1
            );

            repository.save(updated);

            auditService.record(
                key,
                "ROLLOUT_UPDATED",
                actor,
                updated.getVersion(),
                "Percentage=" + percentage
            );
        }

        synchronized void disable(String key, String actor) {
            FeatureFlag current = requireFlag(key);

            FeatureFlag updated = current.with(
                current.getType(),
                FlagStatus.DISABLED,
                current.getPercentage(),
                current.getVersion() + 1
            );

            repository.save(updated);

            auditService.record(
                key,
                "KILL_SWITCH_ACTIVATED",
                actor,
                updated.getVersion(),
                "Emergency disable"
            );
        }

        synchronized void enable(String key, String actor) {
            FeatureFlag current = requireFlag(key);

            if (current.isExpired()) {
                throw new FeatureFlagException(
                    "Expired flag cannot be enabled"
                );
            }

            FeatureFlag updated = current.with(
                current.getType(),
                FlagStatus.ACTIVE,
                current.getPercentage(),
                current.getVersion() + 1
            );

            repository.save(updated);

            auditService.record(
                key,
                "ENABLED",
                actor,
                updated.getVersion(),
                "Flag activated"
            );
        }

        synchronized void archive(String key, String actor) {
            FeatureFlag current = requireFlag(key);

            FeatureFlag updated = current.with(
                current.getType(),
                FlagStatus.ARCHIVED,
                current.getPercentage(),
                current.getVersion() + 1
            );

            repository.save(updated);

            auditService.record(
                key,
                "ARCHIVED",
                actor,
                updated.getVersion(),
                "Flag retired"
            );
        }

        private FeatureFlag requireFlag(String key) {
            FeatureFlag flag = repository.findByKey(key);

            if (flag == null) {
                throw new FeatureFlagException(
                    "Unknown feature flag: " + key
                );
            }

            return flag;
        }

        List<FeatureFlag> report() {
            return repository.findAll().stream()
                .sorted((a, b) ->
                    a.getKey().compareTo(b.getKey()))
                .collect(Collectors.toUnmodifiableList());
        }
    }

    public static void main(String[] args) {

        try {
            FlagRepository repository =
                new InMemoryFlagRepository();

            AuditService audit = new AuditService();

            audit.subscribe(event ->
                System.out.println(
                    "[AUDIT] " +
                    event.action() +
                    " | " +
                    event.flagKey() +
                    " | " +
                    event.actor()
                )
            );

            RolloutPolicy rollout = new RolloutPolicy();

            ApprovalPolicy approval = new ApprovalPolicy(
                2,
                Set.of("release-manager", "platform-admin")
            );

            FeatureFlagService service =
                new FeatureFlagService(
                    repository,
                    rollout,
                    approval,
                    audit
                );

            FeatureFlag checkout = new FeatureFlag(
                "new_checkout",
                "New checkout experience",
                FlagType.PERCENTAGE,
                FlagStatus.ACTIVE,
                EnumSet.of(
                    Environment.STAGING,
                    Environment.PRODUCTION
                ),
                Set.of("admin_001"),
                Set.of("beta_testers"),
                25.0,
                false,
                "payments-team",
                null,
                1
            );

            FeatureFlag search = new FeatureFlag(
                "new_search",
                "New search implementation",
                FlagType.BOOLEAN,
                FlagStatus.ACTIVE,
                EnumSet.of(Environment.STAGING),
                Set.of(),
                Set.of(),
                0.0,
                true,
                "search-team",
                null,
                1
            );

            service.register(checkout, "platform-admin");
            service.register(search, "platform-admin");

            List<EvaluationContext> users = List.of(
                new EvaluationContext(
                    "user_001",
                    Environment.PRODUCTION,
                    Set.of("standard"),
                    Map.of("region", "IN")
                ),
                new EvaluationContext(
                    "user_002",
                    Environment.PRODUCTION,
                    Set.of("beta_testers"),
                    Map.of("region", "IN")
                ),
                new EvaluationContext(
                    "admin_001",
                    Environment.PRODUCTION,
                    Set.of("standard"),
                    Map.of("region", "IN")
                ),
                new EvaluationContext(
                    "user_003",
                    Environment.STAGING,
                    Set.of("standard"),
                    Map.of("region", "EU")
                )
            );

            System.out.println("\nEVALUATION RESULTS");

            users.forEach(context -> {
                EvaluationResult result = service.evaluate(
                    "new_checkout",
                    context
                );

                System.out.println(result);
            });

            // Verify deterministic assignment.
            boolean first = service.evaluate(
                "new_checkout",
                users.get(0)
            ).enabled();

            boolean second = service.evaluate(
                "new_checkout",
                users.get(0)
            ).enabled();

            if (first != second) {
                throw new FeatureFlagException(
                    "Allocation is not deterministic"
                );
            }

            // Verify explicit group targeting.
            if (!service.evaluate(
                "new_checkout",
                users.get(1)
            ).enabled()) {
                throw new FeatureFlagException(
                    "Group targeting failed"
                );
            }

            // Increase rollout with the required approvals.
            service.updateRollout(
                "new_checkout",
                60.0,
                1,
                "release-manager",
                2
            );

            // Verify version conflict handling.
            try {
                service.updateRollout(
                    "new_checkout",
                    80.0,
                    1,
                    "release-manager",
                    2
                );

                throw new FeatureFlagException(
                    "Stale update was accepted"
                );

            } catch (VersionConflictException error) {
                System.out.println(
                    "\nStale configuration rejected."
                );
            }

            // Emergency kill switch.
            service.disable(
                "new_checkout",
                "incident-commander"
            );

            if (service.evaluate(
                "new_checkout",
                users.get(1)
            ).enabled()) {
                throw new FeatureFlagException(
                    "Kill switch failed"
                );
            }

            service.enable(
                "new_checkout",
                "release-manager"
            );

            System.out.println("\nCONFIGURATION REPORT");

            service.report().forEach(flag ->
                System.out.printf(
                    "%-20s %-12s %-10s version=%d%n",
                    flag.getKey(),
                    flag.getType(),
                    flag.getStatus(),
                    flag.getVersion()
                )
            );

            System.out.println(
                "\nAUDIT EVENTS: " + audit.getEvents().size()
            );

            System.out.println(
                "\nAll Java 17 checks passed."
            );

        } catch (RuntimeException error) {
            System.err.println(
                "APPLICATION ERROR: " + error.getMessage()
            );

            System.exit(1);
        }
    }
}

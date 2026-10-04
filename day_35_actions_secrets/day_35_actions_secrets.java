import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/*
 * Enterprise repository security model for Actions secrets.
 *
 * The program models secret ownership, scopes, environments, credential
 * rotation, access policies, lifecycle states, and deployment eligibility.
 * Java records are used for immutable policy/audit values while mutable
 * lifecycle state remains inside the domain service.
 */

public class ActionsSecretsEnterpriseDemo {

    enum SecretScope {
        ORGANIZATION,
        REPOSITORY,
        ENVIRONMENT
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum Role {
        DEVELOPER,
        MAINTAINER,
        SECURITY_ADMIN,
        CI_RUNNER
    }

    enum SecretState {
        ACTIVE,
        DISABLED
    }

    record Principal(
        String username,
        Role role,
        Set<String> repositories,
        Set<Environment> environments
    ) {
        Principal {
            repositories = Set.copyOf(repositories);
            environments = Set.copyOf(environments);
        }

        boolean administersSecrets() {
            return role == Role.SECURITY_ADMIN;
        }

        boolean belongsToRepository(String repository) {
            return repositories.contains(repository);
        }

        boolean canRunIn(Environment environment) {
            return environments.contains(environment);
        }
    }

    record SecretIdentity(
        String name,
        SecretScope scope,
        String repository,
        Environment environment
    ) {
    }

    record SecretMetadata(
        SecretIdentity identity,
        Instant createdAt,
        Instant rotatedAt,
        Instant expiresAt,
        SecretState state
    ) {
    }

    record AuditEvent(
        Instant timestamp,
        String actor,
        String action,
        SecretIdentity secret,
        String result
    ) {
    }

    record DeploymentPolicy(
        Set<String> requiredSecrets,
        boolean productionRequiresEnvironmentSecrets
    ) {
        DeploymentPolicy {
            requiredSecrets = Set.copyOf(requiredSecrets);
        }
    }

    static final class SecretRecord {
        private final SecretIdentity identity;
        private String value;
        private final Instant createdAt;
        private Instant rotatedAt;
        private Instant expiresAt;
        private SecretState state;

        SecretRecord(
            SecretIdentity identity,
            String value,
            Instant createdAt,
            Instant expiresAt
        ) {
            this.identity = identity;
            this.value = value;
            this.createdAt = createdAt;
            this.rotatedAt = null;
            this.expiresAt = expiresAt;
            this.state = SecretState.ACTIVE;
        }

        SecretIdentity identity() {
            return identity;
        }

        String value() {
            return value;
        }

        boolean usable() {
            return state == SecretState.ACTIVE
                && Instant.now().isBefore(expiresAt);
        }

        void rotate(String replacement, Instant newExpiry) {
            this.value = replacement;
            this.rotatedAt = Instant.now();
            this.expiresAt = newExpiry;
            this.state = SecretState.ACTIVE;
        }

        void disable() {
            this.state = SecretState.DISABLED;
        }

        SecretMetadata metadata() {
            return new SecretMetadata(
                identity,
                createdAt,
                rotatedAt,
                expiresAt,
                state
            );
        }
    }

    static final class SecretPolicyException extends RuntimeException {
        SecretPolicyException(String message) {
            super(message);
        }
    }

    static final class AuthorizationException extends RuntimeException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static final class SecretService {
        private static final Pattern SECRET_NAME =
            Pattern.compile("[A-Z][A-Z0-9_]{1,99}");

        private final Map<SecretIdentity, SecretRecord> records =
            new HashMap<>();

        private final List<AuditEvent> auditEvents =
            new ArrayList<>();

        private void audit(
            Principal actor,
            String action,
            SecretIdentity identity,
            String result
        ) {
            auditEvents.add(
                new AuditEvent(
                    Instant.now(),
                    actor.username(),
                    action,
                    identity,
                    result
                )
            );
        }

        private boolean canManage(
            Principal actor,
            String repository
        ) {
            if (actor.administersSecrets()) {
                return true;
            }

            return (
                actor.role() == Role.MAINTAINER &&
                actor.belongsToRepository(repository)
            );
        }

        private boolean canRead(
            Principal actor,
            String repository,
            Environment environment
        ) {
            if (actor.administersSecrets()) {
                return true;
            }

            if (!actor.belongsToRepository(repository)) {
                return false;
            }

            if (environment != null &&
                !actor.environments().isEmpty() &&
                !actor.canRunIn(environment)) {
                return false;
            }

            return actor.role() == Role.CI_RUNNER ||
                   actor.role() == Role.MAINTAINER;
        }

        private void validateName(String name) {
            if (!SECRET_NAME.matcher(name).matches()) {
                throw new SecretPolicyException(
                    "Secret names must use uppercase letters, digits, and underscores."
                );
            }

            if (Set.of("PASSWORD", "SECRET", "TOKEN", "KEY").contains(name)) {
                throw new SecretPolicyException(
                    "Generic secret names are rejected because they obscure purpose."
                );
            }
        }

        private void validateValue(String value) {
            if (value == null || value.length() < 16) {
                throw new SecretPolicyException(
                    "Credential does not meet the minimum length policy."
                );
            }

            if (value.contains("\n") || value.contains("\r")) {
                throw new SecretPolicyException(
                    "Unexpected newline in credential."
                );
            }
        }

        SecretMetadata put(
            Principal actor,
            SecretIdentity identity,
            String value,
            Duration lifetime
        ) {
            Objects.requireNonNull(identity);
            Objects.requireNonNull(value);

            validateName(identity.name());
            validateValue(value);

            if (identity.scope() == SecretScope.REPOSITORY &&
                identity.repository() == null) {
                throw new SecretPolicyException(
                    "Repository secrets require a repository."
                );
            }

            if (identity.scope() == SecretScope.ENVIRONMENT &&
                (identity.repository() == null ||
                 identity.environment() == null)) {
                throw new SecretPolicyException(
                    "Environment secrets require repository and environment."
                );
            }

            if (!canManage(actor, identity.repository())) {
                audit(actor, "write", identity, "denied");
                throw new AuthorizationException(
                    actor.username() + " cannot manage this secret."
                );
            }

            Instant expiry = Instant.now().plus(lifetime);

            SecretRecord existing = records.get(identity);

            if (existing == null) {
                SecretRecord created = new SecretRecord(
                    identity,
                    value,
                    Instant.now(),
                    expiry
                );

                records.put(identity, created);
                audit(actor, "create", identity, "allowed");

                return created.metadata();
            }

            existing.rotate(value, expiry);
            audit(actor, "rotate", identity, "allowed");

            return existing.metadata();
        }

        String resolve(
            Principal actor,
            String name,
            String repository,
            Environment environment
        ) {
            List<SecretIdentity> precedence = List.of(
                new SecretIdentity(
                    name,
                    SecretScope.ENVIRONMENT,
                    repository,
                    environment
                ),
                new SecretIdentity(
                    name,
                    SecretScope.REPOSITORY,
                    repository,
                    null
                ),
                new SecretIdentity(
                    name,
                    SecretScope.ORGANIZATION,
                    null,
                    null
                )
            );

            for (SecretIdentity identity : precedence) {
                SecretRecord record = records.get(identity);

                if (record == null || !record.usable()) {
                    continue;
                }

                if (!canRead(actor, repository, environment)) {
                    audit(actor, "read", identity, "denied");
                    throw new AuthorizationException(
                        actor.username() + " cannot read " + name
                    );
                }

                audit(actor, "read", identity, "allowed");
                return record.value();
            }

            throw new SecretPolicyException(
                "No active and non-expired credential is available."
            );
        }

        void disable(
            Principal actor,
            SecretIdentity identity
        ) {
            SecretRecord record = records.get(identity);

            if (record == null) {
                throw new SecretPolicyException(
                    "Secret does not exist."
                );
            }

            if (!canManage(actor, identity.repository())) {
                audit(actor, "disable", identity, "denied");
                throw new AuthorizationException(
                    "Actor cannot disable this secret."
                );
            }

            record.disable();
            audit(actor, "disable", identity, "allowed");
        }

        Optional<SecretMetadata> metadata(
            SecretIdentity identity
        ) {
            return Optional.ofNullable(records.get(identity))
                .map(SecretRecord::metadata);
        }

        List<AuditEvent> auditEvents() {
            return List.copyOf(auditEvents);
        }
    }

    static final class DeploymentEligibilityService {
        private final SecretService secretService;

        DeploymentEligibilityService(SecretService secretService) {
            this.secretService = secretService;
        }

        List<String> evaluate(
            Principal runner,
            String repository,
            Environment environment,
            DeploymentPolicy policy
        ) {
            List<String> findings = new ArrayList<>();

            for (String secretName : policy.requiredSecrets()) {
                try {
                    String value = secretService.resolve(
                        runner,
                        secretName,
                        repository,
                        environment
                    );

                    /*
                     * The policy records availability, not the credential.
                     * This avoids turning deployment diagnostics into a secret
                     * disclosure channel.
                     */
                    findings.add(
                        secretName +
                        " available; credential length=" +
                        value.length()
                    );
                } catch (RuntimeException error) {
                    findings.add(
                        secretName +
                        " unavailable; deployment requirement failed"
                    );
                }
            }

            if (environment == Environment.PRODUCTION &&
                policy.productionRequiresEnvironmentSecrets()) {
                findings.add(
                    "Production deployment requires environment-scoped credentials."
                );
            }

            return findings;
        }
    }

    private static String generateCredential(String prefix) {
        return prefix + "_" + UUID.randomUUID() +
               UUID.randomUUID().toString().replace("-", "");
    }

    private static String fingerprint(String value) {
        return Integer.toHexString(value.hashCode());
    }

    public static void main(String[] args) {
        System.out.println(
            "=== Enterprise Actions Secret Governance ==="
        );

        SecretService service = new SecretService();

        Principal securityAdmin = new Principal(
            "security-admin",
            Role.SECURITY_ADMIN,
            Set.of("acme/payments"),
            EnumSet.allOf(Environment.class)
        );

        Principal maintainer = new Principal(
            "payments-maintainer",
            Role.MAINTAINER,
            Set.of("acme/payments"),
            Set.of(Environment.DEVELOPMENT, Environment.STAGING)
        );

        Principal productionRunner = new Principal(
            "actions-production-runner",
            Role.CI_RUNNER,
            Set.of("acme/payments"),
            Set.of(Environment.PRODUCTION)
        );

        System.out.println("\n=== Secret provisioning ===");

        service.put(
            securityAdmin,
            new SecretIdentity(
                "PACKAGE_REGISTRY_TOKEN",
                SecretScope.ORGANIZATION,
                null,
                null
            ),
            generateCredential("package"),
            Duration.ofDays(90)
        );

        service.put(
            securityAdmin,
            new SecretIdentity(
                "DATABASE_PASSWORD",
                SecretScope.REPOSITORY,
                "acme/payments",
                null
            ),
            generateCredential("database"),
            Duration.ofDays(60)
        );

        service.put(
            securityAdmin,
            new SecretIdentity(
                "DATABASE_PASSWORD",
                SecretScope.ENVIRONMENT,
                "acme/payments",
                Environment.PRODUCTION
            ),
            generateCredential("production-db"),
            Duration.ofDays(30)
        );

        service.put(
            securityAdmin,
            new SecretIdentity(
                "DEPLOY_TOKEN",
                SecretScope.ENVIRONMENT,
                "acme/payments",
                Environment.PRODUCTION
            ),
            generateCredential("production-deploy"),
            Duration.ofDays(14)
        );

        System.out.println(
            service.metadata(
                new SecretIdentity(
                    "DEPLOY_TOKEN",
                    SecretScope.ENVIRONMENT,
                    "acme/payments",
                    Environment.PRODUCTION
                )
            )
        );

        System.out.println("\n=== Environment-aware resolution ===");

        String stagingPassword = service.resolve(
            maintainer,
            "DATABASE_PASSWORD",
            "acme/payments",
            Environment.STAGING
        );

        String productionPassword = service.resolve(
            productionRunner,
            "DATABASE_PASSWORD",
            "acme/payments",
            Environment.PRODUCTION
        );

        System.out.println(
            "Staging credential fingerprint: " +
            fingerprint(stagingPassword)
        );

        System.out.println(
            "Production credential fingerprint: " +
            fingerprint(productionPassword)
        );

        System.out.println(
            "Production uses a distinct environment value: " +
            !stagingPassword.equals(productionPassword)
        );

        System.out.println("\n=== Deployment policy ===");

        DeploymentPolicy policy = new DeploymentPolicy(
            Set.of(
                "DATABASE_PASSWORD",
                "DEPLOY_TOKEN",
                "PACKAGE_REGISTRY_TOKEN"
            ),
            true
        );

        DeploymentEligibilityService eligibility =
            new DeploymentEligibilityService(service);

        eligibility.evaluate(
            productionRunner,
            "acme/payments",
            Environment.PRODUCTION,
            policy
        ).forEach(System.out::println);

        System.out.println("\n=== Unauthorized environment access ===");

        try {
            service.resolve(
                maintainer,
                "DATABASE_PASSWORD",
                "acme/payments",
                Environment.PRODUCTION
            );

            System.out.println(
                "Unexpected production access."
            );
        } catch (AuthorizationException error) {
            System.out.println(
                "Access correctly rejected: " +
                error.getMessage()
            );
        }

        System.out.println("\n=== Credential rotation ===");

        SecretIdentity deploymentIdentity =
            new SecretIdentity(
                "DEPLOY_TOKEN",
                SecretScope.ENVIRONMENT,
                "acme/payments",
                Environment.PRODUCTION
            );

        service.put(
            securityAdmin,
            deploymentIdentity,
            generateCredential("rotated-production-deploy"),
            Duration.ofDays(14)
        );

        System.out.println(
            "Rotated metadata: " +
            service.metadata(deploymentIdentity).orElseThrow()
        );

        System.out.println("\n=== Emergency disable ===");

        service.disable(
            securityAdmin,
            deploymentIdentity
        );

        try {
            service.resolve(
                productionRunner,
                "DEPLOY_TOKEN",
                "acme/payments",
                Environment.PRODUCTION
            );

            System.out.println(
                "Unexpected credential resolution."
            );
        } catch (SecretPolicyException error) {
            System.out.println(
                "Disabled credential rejected: " +
                error.getMessage()
            );
        }

        System.out.println("\n=== Audit trail ===");

        service.auditEvents().forEach(event ->
            System.out.println(
                event.timestamp() +
                " actor=" + event.actor() +
                " action=" + event.action() +
                " secret=" + event.secret().name() +
                " scope=" + event.secret().scope() +
                " result=" + event.result()
            )
        );

        System.out.println(
            "\nThe model keeps secret values inside the secret service, " +
            "uses explicit scope precedence, restricts production access, " +
            "supports rotation and disabling, and keeps audit records free " +
            "of plaintext credentials."
        );
    }
}

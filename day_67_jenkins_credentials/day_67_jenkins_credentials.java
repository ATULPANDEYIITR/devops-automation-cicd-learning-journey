import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Jenkins Credentials Management
 *
 * Enterprise-oriented credential lifecycle and pipeline governance.
 * Compatible with Java 17.
 *
 * Secret values are simulated. This application does not replace
 * Jenkins encrypted credential storage or an external secret manager.
 */
public class JenkinsCredentialsManager {

    enum CredentialType {
        SECRET_TEXT,
        USERNAME_PASSWORD,
        SSH_PRIVATE_KEY,
        SECRET_FILE,
        CERTIFICATE
    }

    enum CredentialScope {
        GLOBAL,
        SYSTEM
    }

    enum CredentialStatus {
        ACTIVE,
        EXPIRED,
        REVOKED
    }

    enum AuditAction {
        CREATE,
        BIND,
        ROTATE,
        REVOKE,
        VALIDATION_FAILURE
    }

    static class CredentialException extends RuntimeException {
        CredentialException(String message) {
            super(message);
        }
    }

    static class PolicyViolationException extends CredentialException {
        PolicyViolationException(String message) {
            super(message);
        }
    }

    static class CredentialNotFoundException extends CredentialException {
        CredentialNotFoundException(String message) {
            super(message);
        }
    }

    record CredentialMetadata(
        String id,
        String description,
        CredentialType type,
        CredentialScope scope,
        String owner,
        Instant createdAt,
        Optional<Instant> expiresAt,
        CredentialStatus status,
        int version
    ) {}

    record AuditEvent(
        Instant timestamp,
        AuditAction action,
        String credentialId,
        String actor,
        String outcome,
        String details
    ) {}

    record PipelineDefinition(
        String name,
        String actor,
        List<String> credentialIds
    ) {
        PipelineDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(actor);
            credentialIds = List.copyOf(credentialIds);

            if (name.isBlank() || actor.isBlank()) {
                throw new IllegalArgumentException(
                    "Pipeline name and actor are required"
                );
            }
        }
    }

    record PolicyDecision(
        boolean allowed,
        List<String> violations
    ) {
        PolicyDecision {
            violations = List.copyOf(violations);
        }
    }

    record UsernamePassword(
        String username,
        String password
    ) {
        UsernamePassword {
            if (
                username == null || username.isBlank() ||
                password == null || password.isBlank()
            ) {
                throw new IllegalArgumentException(
                    "Username and password are required"
                );
            }
        }

        @Override
        public String toString() {
            return "UsernamePassword[username=" + username
                + ", password=REDACTED]";
        }
    }

    private static final Pattern ID_PATTERN =
        Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$");

    private static final class CredentialEntry {
        final String id;
        final String description;
        final CredentialType type;
        final CredentialScope scope;
        final String owner;
        final Instant createdAt;

        Instant expiresAt;
        CredentialStatus status;
        int version;
        Object secret;

        CredentialEntry(
            String id,
            String description,
            CredentialType type,
            CredentialScope scope,
            String owner,
            Object secret,
            Instant expiresAt
        ) {
            this.id = id;
            this.description = description;
            this.type = type;
            this.scope = scope;
            this.owner = owner;
            this.secret = secret;
            this.expiresAt = expiresAt;
            this.createdAt = Instant.now();
            this.status = CredentialStatus.ACTIVE;
            this.version = 1;
        }

        boolean isValid() {
            return status == CredentialStatus.ACTIVE
                && (
                    expiresAt == null ||
                    Instant.now().isBefore(expiresAt)
                );
        }

        CredentialMetadata metadata() {
            CredentialStatus displayedStatus =
                isValid() ? status :
                status == CredentialStatus.REVOKED
                    ? CredentialStatus.REVOKED
                    : CredentialStatus.EXPIRED;

            return new CredentialMetadata(
                id,
                description,
                type,
                scope,
                owner,
                createdAt,
                Optional.ofNullable(expiresAt),
                displayedStatus,
                version
            );
        }
    }

    interface SecretConsumer<T> {
        T execute(Object secret);
    }

    interface CredentialAccessPolicy {
        PolicyDecision evaluate(PipelineDefinition pipeline);
    }

    static final class CredentialStore {
        private final Map<String, CredentialEntry> entries =
            new HashMap<>();

        private final List<AuditEvent> audit =
            new ArrayList<>();

        private void record(
            AuditAction action,
            String id,
            String actor,
            String outcome,
            String details
        ) {
            audit.add(new AuditEvent(
                Instant.now(),
                action,
                id,
                actor,
                outcome,
                details
            ));
        }

        private void validateSecret(
            CredentialType type,
            Object secret
        ) {
            if (secret == null) {
                throw new IllegalArgumentException("Secret is required");
            }

            switch (type) {
                case USERNAME_PASSWORD -> {
                    if (!(secret instanceof UsernamePassword)) {
                        throw new IllegalArgumentException(
                            "UsernamePassword object required"
                        );
                    }
                }

                case SECRET_TEXT,
                     SSH_PRIVATE_KEY,
                     SECRET_FILE,
                     CERTIFICATE -> {
                    if (
                        !(secret instanceof String value) ||
                        value.isBlank()
                    ) {
                        throw new IllegalArgumentException(
                            "Non-empty string secret required"
                        );
                    }
                }
            }
        }

        public CredentialMetadata add(
            String id,
            String description,
            CredentialType type,
            CredentialScope scope,
            String owner,
            Object secret,
            Instant expiresAt
        ) {
            if (!ID_PATTERN.matcher(id).matches()) {
                throw new IllegalArgumentException(
                    "Invalid credential ID"
                );
            }

            if (entries.containsKey(id)) {
                throw new IllegalArgumentException(
                    "Duplicate credential ID"
                );
            }

            if (
                description == null || description.isBlank() ||
                owner == null || owner.isBlank()
            ) {
                throw new IllegalArgumentException(
                    "Description and owner are required"
                );
            }

            if (
                expiresAt != null &&
                !expiresAt.isAfter(Instant.now())
            ) {
                throw new IllegalArgumentException(
                    "Expiration must be in the future"
                );
            }

            validateSecret(type, secret);

            CredentialEntry entry = new CredentialEntry(
                id,
                description,
                type,
                scope,
                owner,
                secret,
                expiresAt
            );

            entries.put(id, entry);

            record(
                AuditAction.CREATE,
                id,
                owner,
                "SUCCESS",
                "Credential registered"
            );

            return entry.metadata();
        }

        public CredentialMetadata getMetadata(String id) {
            return find(id).metadata();
        }

        private CredentialEntry find(String id) {
            CredentialEntry entry = entries.get(id);

            if (entry == null) {
                throw new CredentialNotFoundException(
                    "Credential not found: " + id
                );
            }

            return entry;
        }

        public <T> T withCredential(
            String id,
            PipelineDefinition pipeline,
            CredentialType expectedType,
            boolean allowSystemScope,
            SecretConsumer<T> consumer
        ) {
            CredentialEntry entry = find(id);

            if (!entry.isValid()) {
                record(
                    AuditAction.BIND,
                    id,
                    pipeline.actor(),
                    "DENIED",
                    "Inactive or expired credential"
                );

                throw new PolicyViolationException(
                    "Credential is inactive"
                );
            }

            if (
                entry.scope == CredentialScope.SYSTEM &&
                !allowSystemScope
            ) {
                record(
                    AuditAction.BIND,
                    id,
                    pipeline.actor(),
                    "DENIED",
                    "System scope restriction"
                );

                throw new PolicyViolationException(
                    "System credential access denied"
                );
            }

            if (entry.type != expectedType) {
                throw new PolicyViolationException(
                    "Credential type mismatch"
                );
            }

            record(
                AuditAction.BIND,
                id,
                pipeline.actor(),
                "SUCCESS",
                "Pipeline: " + pipeline.name()
            );

            // The callback limits the intended secret-use boundary.
            // Java does not guarantee memory zeroization.
            return consumer.execute(entry.secret);
        }

        public CredentialMetadata rotate(
            String id,
            Object replacement,
            String actor
        ) {
            CredentialEntry entry = find(id);

            if (entry.status == CredentialStatus.REVOKED) {
                throw new PolicyViolationException(
                    "Revoked credentials cannot be rotated"
                );
            }

            validateSecret(entry.type, replacement);

            entry.secret = replacement;
            entry.version++;
            entry.status = CredentialStatus.ACTIVE;
            entry.expiresAt = null;

            record(
                AuditAction.ROTATE,
                id,
                actor,
                "SUCCESS",
                "Version " + entry.version
            );

            return entry.metadata();
        }

        public void revoke(String id, String actor) {
            CredentialEntry entry = find(id);

            entry.status = CredentialStatus.REVOKED;
            entry.secret = null;

            record(
                AuditAction.REVOKE,
                id,
                actor,
                "SUCCESS",
                "Credential revoked"
            );
        }

        public List<CredentialMetadata> list() {
            return entries.values()
                .stream()
                .map(CredentialEntry::metadata)
                .sorted((a, b) -> a.id().compareTo(b.id()))
                .toList();
        }

        public List<AuditEvent> getAudit() {
            return Collections.unmodifiableList(
                new ArrayList<>(audit)
            );
        }
    }

    static final class EnterprisePipelinePolicy
        implements CredentialAccessPolicy {

        private final CredentialStore store;

        EnterprisePipelinePolicy(CredentialStore store) {
            this.store = store;
        }

        @Override
        public PolicyDecision evaluate(
            PipelineDefinition pipeline
        ) {
            List<String> violations = new ArrayList<>();

            Set<String> uniqueIds = new HashSet<>(
                pipeline.credentialIds()
            );

            if (uniqueIds.size() != pipeline.credentialIds().size()) {
                violations.add("Duplicate credential references");
            }

            for (String id : uniqueIds) {
                try {
                    CredentialMetadata metadata =
                        store.getMetadata(id);

                    if (metadata.status() != CredentialStatus.ACTIVE) {
                        violations.add(id + ": credential inactive");
                    }

                    if (metadata.scope() == CredentialScope.SYSTEM) {
                        violations.add(id + ": system scope restricted");
                    }

                } catch (CredentialNotFoundException exception) {
                    violations.add(id + ": credential not found");
                }
            }

            return new PolicyDecision(
                violations.isEmpty(),
                violations
            );
        }
    }

    static final class JenkinsfileValidator {
        private static final List<Pattern> SECRET_PATTERNS = List.of(
            Pattern.compile(
                "(?i)(password|secret|token|api_key)\\s*=\\s*['\"][^'\"]+"
            ),
            Pattern.compile(
                "-----BEGIN [A-Z ]*PRIVATE KEY-----"
            ),
            Pattern.compile(
                "(?i)authorization\\s*:\\s*bearer\\s+\\S+"
            )
        );

        public List<String> scan(String jenkinsfile) {
            List<String> findings = new ArrayList<>();

            if (jenkinsfile == null) {
                throw new IllegalArgumentException(
                    "Jenkinsfile content is required"
                );
            }

            if (SECRET_PATTERNS.get(0).matcher(jenkinsfile).find()) {
                findings.add("Possible hardcoded password or token");
            }

            if (SECRET_PATTERNS.get(1).matcher(jenkinsfile).find()) {
                findings.add("Private key material detected");
            }

            if (SECRET_PATTERNS.get(2).matcher(jenkinsfile).find()) {
                findings.add("Possible hardcoded bearer token");
            }

            return findings;
        }
    }

    public static void main(String[] args) {
        System.out.println("JENKINS CREDENTIALS MANAGEMENT");
        System.out.println("=".repeat(55));

        CredentialStore store = new CredentialStore();

        store.add(
            "github-deploy-token",
            "GitHub deployment token",
            CredentialType.SECRET_TEXT,
            CredentialScope.GLOBAL,
            "devops-team",
            "SIMULATED_GITHUB_TOKEN",
            null
        );

        store.add(
            "docker-registry",
            "Docker registry credentials",
            CredentialType.USERNAME_PASSWORD,
            CredentialScope.GLOBAL,
            "platform-team",
            new UsernamePassword(
                "build-user",
                "SIMULATED_REGISTRY_PASSWORD"
            ),
            Instant.now().plus(30, ChronoUnit.DAYS)
        );

        store.add(
            "production-ssh",
            "Production SSH private key",
            CredentialType.SSH_PRIVATE_KEY,
            CredentialScope.SYSTEM,
            "infrastructure-team",
            "SIMULATED_PRIVATE_KEY",
            null
        );

        System.out.println("\n1. Credential inventory");

        store.list().forEach(metadata ->
            System.out.printf(
                "%s | %s | %s | %s | Version %d%n",
                metadata.id(),
                metadata.type(),
                metadata.scope(),
                metadata.status(),
                metadata.version()
            )
        );

        PipelineDefinition pipeline = new PipelineDefinition(
            "release-pipeline",
            "build-agent",
            List.of(
                "github-deploy-token",
                "docker-registry"
            )
        );

        EnterprisePipelinePolicy policy =
            new EnterprisePipelinePolicy(store);

        System.out.println("\n2. Pipeline policy evaluation");

        PolicyDecision decision = policy.evaluate(pipeline);

        System.out.println("Allowed: " + decision.allowed());
        System.out.println("Violations: " + decision.violations());

        System.out.println("\n3. Scoped credential binding");

        String result = store.withCredential(
            "docker-registry",
            pipeline,
            CredentialType.USERNAME_PASSWORD,
            false,
            secret -> {
                UsernamePassword credentials =
                    (UsernamePassword) secret;

                return "Authenticated as " + credentials.username();
            }
        );

        System.out.println(result);

        System.out.println("\n4. Jenkinsfile validation");

        JenkinsfileValidator validator = new JenkinsfileValidator();

        String jenkinsfile = """
            pipeline {
                agent any
                stages {
                    stage('Build') {
                        steps {
                            echo 'Building application'
                        }
                    }
                }
            }
            """;

        System.out.println(
            validator.scan(jenkinsfile)
        );

        System.out.println("\n5. Restricted system credential");

        try {
            store.withCredential(
                "production-ssh",
                pipeline,
                CredentialType.SSH_PRIVATE_KEY,
                false,
                secret -> "Connected"
            );
        } catch (PolicyViolationException exception) {
            System.out.println("Denied: " + exception.getMessage());
        }

        System.out.println("\n6. Credential rotation");

        CredentialMetadata rotated = store.rotate(
            "github-deploy-token",
            "SIMULATED_ROTATED_TOKEN",
            "security-admin"
        );

        System.out.println("New version: " + rotated.version());

        System.out.println("\n7. Credential revocation");

        store.revoke(
            "github-deploy-token",
            "security-admin"
        );

        PolicyDecision afterRevocation = policy.evaluate(
            new PipelineDefinition(
                "release-pipeline",
                "build-agent",
                List.of("github-deploy-token")
            )
        );

        System.out.println(afterRevocation);

        System.out.println("\n8. Audit records");

        store.getAudit().forEach(event ->
            System.out.printf(
                "%s | %s | %s | %s | %s%n",
                event.action(),
                event.credentialId(),
                event.actor(),
                event.outcome(),
                event.details()
            )
        );

        System.out.println("\n9. Validation tests");

        if (rotated.version() != 2) {
            throw new IllegalStateException("Rotation failed");
        }

        if (afterRevocation.allowed()) {
            throw new IllegalStateException(
                "Revoked credential incorrectly permitted"
            );
        }

        try {
            store.add(
                "invalid id",
                "Invalid credential",
                CredentialType.SECRET_TEXT,
                CredentialScope.GLOBAL,
                "admin",
                "secret",
                null
            );

            throw new IllegalStateException(
                "Invalid ID was accepted"
            );

        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid credential ID rejected");
        }

        System.out.println("All checks passed.");
    }
}

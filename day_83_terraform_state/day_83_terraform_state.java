import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/*
 * Terraform State Enterprise Governance
 *
 * Java 17 implementation.
 *
 * Features:
 * - Strongly typed state domain
 * - Resource and output records
 * - Local and remote backend models
 * - State version history
 * - Workspace management
 * - Lock acquisition and ownership validation
 * - State lineage and serial checks
 * - Approval-style operation policies
 * - Plan and apply services
 * - Optimistic concurrency
 * - Drift detection
 * - State migration
 * - Audit events
 *
 * Compile:
 * javac TerraformStateEnterprise.java
 *
 * Execute:
 * java TerraformStateEnterprise
 */

public class TerraformStateEnterprise {

    // ========================================================
    // ENUMERATIONS
    // ========================================================

    enum BackendType {
        LOCAL,
        REMOTE
    }

    enum OperationType {
        PLAN,
        APPLY,
        REFRESH,
        IMPORT,
        MIGRATION
    }

    enum ChangeAction {
        CREATE,
        UPDATE,
        DELETE
    }

    enum OperationStatus {
        PENDING,
        RUNNING,
        COMPLETED,
        FAILED
    }


    // ========================================================
    // CUSTOM EXCEPTIONS
    // ========================================================

    static class StateException extends RuntimeException {
        StateException(String message) {
            super(message);
        }
    }

    static class ValidationException extends StateException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class LockException extends StateException {
        LockException(String message) {
            super(message);
        }
    }

    static class ConcurrencyException extends StateException {
        ConcurrencyException(String message) {
            super(message);
        }
    }


    // ========================================================
    // DOMAIN RECORDS
    // ========================================================

    record Resource(
        String address,
        String type,
        String provider,
        String id,
        Map<String, String> attributes,
        Set<String> sensitiveAttributes
    ) {

        Resource {

            if (
                address == null ||
                !address.contains(".")
            ) {
                throw new ValidationException(
                    "Invalid resource address."
                );
            }

            Objects.requireNonNull(type);
            Objects.requireNonNull(provider);
            Objects.requireNonNull(id);

            if (
                type.isBlank() ||
                provider.isBlank() ||
                id.isBlank()
            ) {
                throw new ValidationException(
                    "Resource metadata cannot be blank."
                );
            }

            attributes = Map.copyOf(attributes);

            sensitiveAttributes = Set.copyOf(
                sensitiveAttributes
            );

            if (!attributes.keySet().containsAll(
                sensitiveAttributes
            )) {
                throw new ValidationException(
                    "Unknown sensitive resource attribute."
                );
            }
        }

        Map<String, String> displayAttributes() {

            Map<String, String> result =
                new TreeMap<>(attributes);

            sensitiveAttributes.forEach(
                key -> result.put(key, "[REDACTED]")
            );

            return Collections.unmodifiableMap(result);
        }

        boolean equivalent(Resource other) {

            return address.equals(other.address()) &&
                   type.equals(other.type()) &&
                   provider.equals(other.provider()) &&
                   id.equals(other.id()) &&
                   attributes.equals(other.attributes());
        }
    }


    record StateOutput(
        String name,
        String value,
        boolean sensitive
    ) {

        StateOutput {

            if (name == null || name.isBlank()) {
                throw new ValidationException(
                    "Output name is required."
                );
            }

            Objects.requireNonNull(value);
        }

        String displayValue() {
            return sensitive ? "[REDACTED]" : value;
        }
    }


    record StateLock(
        String id,
        String workspace,
        String owner,
        OperationType operation,
        Instant createdAt
    ) {}


    record AuditEvent(
        String eventId,
        String workspace,
        String action,
        String actor,
        String details,
        Instant timestamp
    ) {}


    // ========================================================
    // STATE DOMAIN
    // ========================================================

    static final class TerraformState {

        private final int version;

        private final String terraformVersion;

        private final String lineage;

        private final String workspace;

        private long serial;

        private Instant updatedAt;

        private final Map<String, Resource> resources;

        private final Map<String, StateOutput> outputs;

        TerraformState(String workspace) {

            this(
                4,
                "1.10.0",
                UUID.randomUUID().toString(),
                workspace,
                0,
                new LinkedHashMap<>(),
                new LinkedHashMap<>(),
                Instant.now()
            );
        }

        TerraformState(
            int version,
            String terraformVersion,
            String lineage,
            String workspace,
            long serial,
            Map<String, Resource> resources,
            Map<String, StateOutput> outputs,
            Instant updatedAt
        ) {

            if (version != 4) {
                throw new ValidationException(
                    "Unsupported state format."
                );
            }

            validateWorkspace(workspace);

            if (serial < 0) {
                throw new ValidationException(
                    "State serial cannot be negative."
                );
            }

            this.version = version;
            this.terraformVersion = terraformVersion;
            this.lineage = Objects.requireNonNull(lineage);
            this.workspace = workspace;
            this.serial = serial;
            this.resources = new LinkedHashMap<>(resources);
            this.outputs = new LinkedHashMap<>(outputs);
            this.updatedAt = updatedAt;

            validate();
        }

        private void validate() {

            for (var entry : resources.entrySet()) {

                if (!entry.getKey().equals(
                    entry.getValue().address()
                )) {
                    throw new ValidationException(
                        "Resource address mismatch."
                    );
                }
            }
        }

        synchronized TerraformState copy() {

            return new TerraformState(
                version,
                terraformVersion,
                lineage,
                workspace,
                serial,
                resources,
                outputs,
                updatedAt
            );
        }

        synchronized long serial() {
            return serial;
        }

        String lineage() {
            return lineage;
        }

        String workspace() {
            return workspace;
        }

        synchronized Map<String, Resource> resources() {
            return Map.copyOf(resources);
        }

        synchronized Map<String, StateOutput> outputs() {
            return Map.copyOf(outputs);
        }

        synchronized void addResource(Resource resource) {

            if (resources.containsKey(resource.address())) {
                throw new ValidationException(
                    "Resource already exists in state."
                );
            }

            resources.put(resource.address(), resource);
        }

        synchronized void replaceResource(Resource resource) {

            if (!resources.containsKey(resource.address())) {
                throw new ValidationException(
                    "Resource does not exist in state."
                );
            }

            resources.put(resource.address(), resource);
        }

        synchronized void removeResource(String address) {

            if (resources.remove(address) == null) {
                throw new ValidationException(
                    "Resource not found in state."
                );
            }
        }

        synchronized void setOutput(StateOutput output) {
            outputs.put(output.name(), output);
        }

        synchronized void advanceSerial() {
            serial++;
            updatedAt = Instant.now();
        }

        synchronized void display() {

            System.out.println("\nSTATE");
            System.out.println("Workspace: " + workspace);
            System.out.println("Lineage: " + lineage);
            System.out.println("Serial: " + serial);
            System.out.println("Resources: " + resources.size());

            resources.values().forEach(resource -> {

                System.out.println(
                    resource.address() +
                    " | " +
                    resource.id()
                );

                System.out.println(
                    resource.displayAttributes()
                );
            });
        }
    }


    // ========================================================
    // WORKSPACE VALIDATION
    // ========================================================

    static void validateWorkspace(String workspace) {

        if (
            workspace == null ||
            !workspace.matches("[a-zA-Z0-9_-]+")
        ) {
            throw new ValidationException(
                "Invalid workspace identifier."
            );
        }
    }


    // ========================================================
    // OPERATION POLICY
    // ========================================================

    interface OperationPolicy {

        boolean permits(
            OperationType operation,
            String actor,
            String workspace
        );
    }


    static final class EnvironmentPolicy
        implements OperationPolicy {

        private final Set<String> productionOperators;

        EnvironmentPolicy(Set<String> productionOperators) {
            this.productionOperators = Set.copyOf(
                productionOperators
            );
        }

        @Override
        public boolean permits(
            OperationType operation,
            String actor,
            String workspace
        ) {

            if (!workspace.equals("production")) {
                return true;
            }

            if (
                operation == OperationType.APPLY ||
                operation == OperationType.MIGRATION
            ) {
                return productionOperators.contains(actor);
            }

            return true;
        }
    }


    // ========================================================
    // STATE LOCK SERVICE
    // ========================================================

    static final class StateLockService {

        private final Map<String, StateLock> activeLocks =
            new ConcurrentHashMap<>();

        private final Map<String, ReentrantLock> mutexes =
            new ConcurrentHashMap<>();

        StateLock acquire(
            String workspace,
            OperationType operation,
            String owner
        ) {

            validateWorkspace(workspace);

            if (owner == null || owner.isBlank()) {
                throw new ValidationException(
                    "Lock owner is required."
                );
            }

            ReentrantLock mutex = mutexes.computeIfAbsent(
                workspace,
                key -> new ReentrantLock()
            );

            if (!mutex.tryLock()) {
                throw new LockException(
                    "Workspace already locked: " + workspace
                );
            }

            try {

                StateLock lock = new StateLock(
                    UUID.randomUUID().toString(),
                    workspace,
                    owner,
                    operation,
                    Instant.now()
                );

                StateLock previous = activeLocks.putIfAbsent(
                    workspace,
                    lock
                );

                if (previous != null) {
                    throw new LockException(
                        "Workspace lock conflict."
                    );
                }

                return lock;

            } catch (RuntimeException exception) {

                mutex.unlock();
                throw exception;
            }
        }

        void release(StateLock lock) {

            StateLock active = activeLocks.get(
                lock.workspace()
            );

            if (
                active == null ||
                !active.id().equals(lock.id())
            ) {
                throw new LockException(
                    "Lock ownership verification failed."
                );
            }

            activeLocks.remove(lock.workspace(), active);

            ReentrantLock mutex = mutexes.get(
                lock.workspace()
            );

            if (mutex == null || !mutex.isHeldByCurrentThread()) {
                throw new LockException(
                    "Lock must be released by its owning thread."
                );
            }

            mutex.unlock();
        }

        StateLock find(String workspace) {
            return activeLocks.get(workspace);
        }
    }


    // ========================================================
    // BACKEND INTERFACE
    // ========================================================

    interface StateBackend {

        TerraformState read(String workspace);

        void write(
            String workspace,
            TerraformState next,
            long expectedSerial
        );

        StateLockService locks();

        BackendType type();
    }


    // ========================================================
    // REMOTE BACKEND
    // ========================================================

    static final class RemoteStateBackend
        implements StateBackend {

        private final Map<String, TerraformState> states =
            new ConcurrentHashMap<>();

        private final Map<String, List<TerraformState>> history =
            new ConcurrentHashMap<>();

        private final StateLockService lockService =
            new StateLockService();

        @Override
        public TerraformState read(String workspace) {

            validateWorkspace(workspace);

            return states.computeIfAbsent(
                workspace,
                TerraformState::new
            ).copy();
        }

        @Override
        public void write(
            String workspace,
            TerraformState next,
            long expectedSerial
        ) {

            synchronized (this) {

                TerraformState current = read(workspace);

                if (current.serial() != expectedSerial) {
                    throw new ConcurrencyException(
                        "State serial conflict."
                    );
                }

                if (!current.lineage().equals(next.lineage())) {
                    throw new ConcurrencyException(
                        "State lineage conflict."
                    );
                }

                if (next.serial() != expectedSerial + 1) {
                    throw new ValidationException(
                        "Invalid serial transition."
                    );
                }

                if (!workspace.equals(next.workspace())) {
                    throw new ValidationException(
                        "Workspace mismatch."
                    );
                }

                TerraformState snapshot = next.copy();

                states.put(workspace, snapshot);

                history.computeIfAbsent(
                    workspace,
                    key -> Collections.synchronizedList(
                        new ArrayList<>()
                    )
                ).add(snapshot.copy());
            }
        }

        @Override
        public StateLockService locks() {
            return lockService;
        }

        @Override
        public BackendType type() {
            return BackendType.REMOTE;
        }

        List<TerraformState> history(String workspace) {

            return history.getOrDefault(
                workspace,
                List.of()
            ).stream()
             .map(TerraformState::copy)
             .collect(Collectors.toList());
        }
    }


    // ========================================================
    // LOCAL BACKEND
    // ========================================================

    static final class LocalStateBackend
        implements StateBackend {

        private final Map<String, TerraformState> files =
            new ConcurrentHashMap<>();

        private final StateLockService lockService =
            new StateLockService();

        @Override
        public TerraformState read(String workspace) {

            validateWorkspace(workspace);

            return files.computeIfAbsent(
                workspace,
                TerraformState::new
            ).copy();
        }

        @Override
        public synchronized void write(
            String workspace,
            TerraformState next,
            long expectedSerial
        ) {

            TerraformState current = read(workspace);

            if (current.serial() != expectedSerial) {
                throw new ConcurrencyException(
                    "Local state serial conflict."
                );
            }

            if (!current.lineage().equals(next.lineage())) {
                throw new ConcurrencyException(
                    "State lineage mismatch."
                );
            }

            if (next.serial() != expectedSerial + 1) {
                throw new ValidationException(
                    "Invalid serial transition."
                );
            }

            files.put(workspace, next.copy());
        }

        @Override
        public StateLockService locks() {
            return lockService;
        }

        @Override
        public BackendType type() {
            return BackendType.LOCAL;
        }
    }


    // ========================================================
    // INFRASTRUCTURE INVENTORY
    // ========================================================

    static final class InfrastructureInventory {

        private final Map<String, Resource> resources =
            new ConcurrentHashMap<>();

        synchronized void create(Resource resource) {

            if (resources.putIfAbsent(
                resource.address(),
                resource
            ) != null) {
                throw new StateException(
                    "Infrastructure resource already exists."
                );
            }
        }

        synchronized void update(
            String address,
            Resource updated
        ) {

            if (!resources.containsKey(address)) {
                throw new StateException(
                    "Infrastructure resource missing."
                );
            }

            resources.put(address, updated);
        }

        synchronized void delete(String address) {

            if (resources.remove(address) == null) {
                throw new StateException(
                    "Infrastructure resource missing."
                );
            }
        }

        Resource find(String address) {
            return resources.get(address);
        }

        Map<String, Resource> snapshot() {
            return Map.copyOf(resources);
        }
    }


    // ========================================================
    // PLAN MODEL
    // ========================================================

    record PlannedChange(
        String address,
        ChangeAction action,
        Resource before,
        Resource after
    ) {}


    record TerraformPlan(
        String workspace,
        String lineage,
        long baseSerial,
        List<PlannedChange> changes
    ) {

        TerraformPlan {
            changes = List.copyOf(changes);
        }
    }


    // ========================================================
    // PLAN SERVICE
    // ========================================================

    static final class PlanService {

        TerraformPlan generate(
            TerraformState state,
            Map<String, Resource> desired
        ) {

            List<PlannedChange> changes =
                new ArrayList<>();

            Map<String, Resource> current =
                state.resources();

            desired.forEach((address, target) -> {

                Resource existing = current.get(address);

                if (existing == null) {

                    changes.add(
                        new PlannedChange(
                            address,
                            ChangeAction.CREATE,
                            null,
                            target
                        )
                    );

                } else if (!existing.equivalent(target)) {

                    changes.add(
                        new PlannedChange(
                            address,
                            ChangeAction.UPDATE,
                            existing,
                            target
                        )
                    );
                }
            });

            current.forEach((address, resource) -> {

                if (!desired.containsKey(address)) {

                    changes.add(
                        new PlannedChange(
                            address,
                            ChangeAction.DELETE,
                            resource,
                            null
                        )
                    );
                }
            });

            return new TerraformPlan(
                state.workspace(),
                state.lineage(),
                state.serial(),
                changes
            );
        }
    }


    // ========================================================
    // AUDIT SERVICE
    // ========================================================

    static final class AuditService {

        private final List<AuditEvent> events =
            Collections.synchronizedList(
                new ArrayList<>()
            );

        void record(
            String workspace,
            String action,
            String actor,
            String details
        ) {

            events.add(
                new AuditEvent(
                    UUID.randomUUID().toString(),
                    workspace,
                    action,
                    actor,
                    details,
                    Instant.now()
                )
            );
        }

        List<AuditEvent> events() {
            synchronized (events) {
                return List.copyOf(events);
            }
        }
    }


    // ========================================================
    // MERGE-STYLE STATE OPERATION SERVICE
    // ========================================================

    static final class StateManagementService {

        private final StateBackend backend;

        private final InfrastructureInventory inventory;

        private final OperationPolicy policy;

        private final AuditService audit;

        StateManagementService(
            StateBackend backend,
            InfrastructureInventory inventory,
            OperationPolicy policy,
            AuditService audit
        ) {

            this.backend = backend;
            this.inventory = inventory;
            this.policy = policy;
            this.audit = audit;
        }

        TerraformState apply(
            TerraformPlan plan,
            String actor
        ) {

            if (!policy.permits(
                OperationType.APPLY,
                actor,
                plan.workspace()
            )) {
                throw new ValidationException(
                    "Actor is not authorized to apply production state."
                );
            }

            StateLock lock = backend.locks().acquire(
                plan.workspace(),
                OperationType.APPLY,
                actor
            );

            try {

                TerraformState current = backend.read(
                    plan.workspace()
                );

                if (
                    current.serial() != plan.baseSerial() ||
                    !current.lineage().equals(plan.lineage())
                ) {
                    throw new ConcurrencyException(
                        "Plan is stale."
                    );
                }

                TerraformState next = current.copy();

                for (PlannedChange change : plan.changes()) {

                    switch (change.action()) {

                        case CREATE -> {

                            inventory.create(change.after());

                            next.addResource(change.after());
                        }

                        case UPDATE -> {

                            inventory.update(
                                change.address(),
                                change.after()
                            );

                            next.replaceResource(change.after());
                        }

                        case DELETE -> {

                            inventory.delete(change.address());

                            next.removeResource(change.address());
                        }
                    }
                }

                if (!plan.changes().isEmpty()) {

                    next.advanceSerial();

                    backend.write(
                        plan.workspace(),
                        next,
                        current.serial()
                    );
                }

                audit.record(
                    plan.workspace(),
                    "APPLY",
                    actor,
                    "Changes: " + plan.changes().size()
                );

                return next;

            } finally {
                backend.locks().release(lock);
            }
        }

        TerraformState refresh(
            String workspace,
            String actor
        ) {

            StateLock lock = backend.locks().acquire(
                workspace,
                OperationType.REFRESH,
                actor
            );

            try {

                TerraformState current = backend.read(workspace);

                TerraformState next = current.copy();

                for (Resource resource :
                     current.resources().values()) {

                    Resource actual = inventory.find(
                        resource.address()
                    );

                    if (actual == null) {
                        throw new ConcurrencyException(
                            "Resource missing: " + resource.address()
                        );
                    }

                    next.replaceResource(actual);
                }

                next.advanceSerial();

                backend.write(
                    workspace,
                    next,
                    current.serial()
                );

                audit.record(
                    workspace,
                    "REFRESH",
                    actor,
                    "Infrastructure state refreshed."
                );

                return next;

            } finally {
                backend.locks().release(lock);
            }
        }

        Map<String, List<String>> detectDrift(
            String workspace
        ) {

            TerraformState state = backend.read(workspace);

            Map<String, Resource> actual =
                inventory.snapshot();

            List<String> missing = new ArrayList<>();
            List<String> modified = new ArrayList<>();
            List<String> untracked = new ArrayList<>();

            state.resources().forEach((address, resource) -> {

                Resource real = actual.get(address);

                if (real == null) {
                    missing.add(address);
                } else if (!resource.equivalent(real)) {
                    modified.add(address);
                }
            });

            actual.forEach((address, resource) -> {

                if (!state.resources().containsKey(address)) {
                    untracked.add(address);
                }
            });

            Map<String, List<String>> result =
                new LinkedHashMap<>();

            result.put("missing", List.copyOf(missing));
            result.put("modified", List.copyOf(modified));
            result.put("untracked", List.copyOf(untracked));

            return Collections.unmodifiableMap(result);
        }
    }


    // ========================================================
    // MIGRATION SERVICE
    // ========================================================

    static final class StateMigrationService {

        static void migrate(
            StateBackend source,
            StateBackend destination,
            String workspace
        ) {

            StateLock sourceLock = source.locks().acquire(
                workspace,
                OperationType.MIGRATION,
                "migration-service"
            );

            try {

                TerraformState sourceState = source.read(workspace);

                TerraformState targetState =
                    destination.read(workspace);

                if (
                    targetState.serial() != 0 ||
                    !targetState.resources().isEmpty()
                ) {
                    throw new ConcurrencyException(
                        "Destination state is not empty."
                    );
                }

                if (!sourceState.lineage().equals(
                    targetState.lineage()
                )) {
                    throw new ConcurrencyException(
                        "State lineage mismatch."
                    );
                }

                StateLock destinationLock =
                    destination.locks().acquire(
                        workspace,
                        OperationType.MIGRATION,
                        "migration-service"
                    );

                try {

                    TerraformState migrated =
                        sourceState.copy();

                    migrated.advanceSerial();

                    destination.write(
                        workspace,
                        migrated,
                        targetState.serial()
                    );

                } finally {

                    destination.locks().release(
                        destinationLock
                    );
                }

            } finally {

                source.locks().release(sourceLock);
            }
        }
    }


    // ========================================================
    // OUTPUT REPORTING
    // ========================================================

    static Map<String, String> reportOutputs(
        TerraformState state
    ) {

        return state.outputs()
            .entrySet()
            .stream()
            .collect(Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> entry.getValue().displayValue()
            ));
    }


    // ========================================================
    // DEMONSTRATION
    // ========================================================

    public static void main(String[] args) {

        RemoteStateBackend backend =
            new RemoteStateBackend();

        InfrastructureInventory inventory =
            new InfrastructureInventory();

        AuditService audit = new AuditService();

        OperationPolicy policy =
            new EnvironmentPolicy(
                Set.of("release-manager", "platform-admin")
            );

        StateManagementService service =
            new StateManagementService(
                backend,
                inventory,
                policy,
                audit
            );

        PlanService planService = new PlanService();

        String workspace = "production";

        TerraformState initial = backend.read(workspace);

        System.out.println("TERRAFORM STATE ENTERPRISE MODEL");

        System.out.println(
            "Initial lineage: " + initial.lineage()
        );

        // Define infrastructure resources.
        Map<String, Resource> desired = new LinkedHashMap<>();

        desired.put(
            "aws_instance.application",
            new Resource(
                "aws_instance.application",
                "aws_instance",
                "hashicorp/aws",
                "i-app-001",
                Map.of(
                    "instance_type", "t3.medium",
                    "region", "ap-south-1"
                ),
                Set.of()
            )
        );

        desired.put(
            "aws_s3_bucket.storage",
            new Resource(
                "aws_s3_bucket.storage",
                "aws_s3_bucket",
                "hashicorp/aws",
                "storage-001",
                Map.of(
                    "versioning", "enabled",
                    "encryption", "AES256"
                ),
                Set.of()
            )
        );

        // Generate a plan.
        TerraformPlan plan = planService.generate(
            initial,
            desired
        );

        System.out.println("\nPLAN");

        plan.changes().forEach(change ->
            System.out.println(
                change.action() + " " + change.address()
            )
        );

        // Test authorization.
        try {

            service.apply(
                plan,
                "unauthorized-user"
            );

        } catch (ValidationException exception) {

            System.out.println(
                "\nPOLICY REJECTION: " + exception.getMessage()
            );
        }

        // Authorized apply.
        TerraformState applied = service.apply(
            plan,
            "release-manager"
        );

        applied.display();

        // Demonstrate sensitive outputs.
        StateLock outputLock = backend.locks().acquire(
            workspace,
            OperationType.APPLY,
            "release-manager"
        );

        try {

            TerraformState updated = backend.read(workspace);

            updated.setOutput(
                new StateOutput(
                    "application_id",
                    "i-app-001",
                    false
                )
            );

            updated.setOutput(
                new StateOutput(
                    "database_password",
                    "example-secret",
                    true
                )
            );

            updated.advanceSerial();

            backend.write(
                workspace,
                updated,
                applied.serial()
            );

        } finally {

            backend.locks().release(outputLock);
        }

        System.out.println("\nOUTPUT REPORT");

        reportOutputs(
            backend.read(workspace)
        ).forEach((key, value) ->
            System.out.println(key + " = " + value)
        );

        // Simulate infrastructure drift.
        inventory.update(
            "aws_instance.application",
            new Resource(
                "aws_instance.application",
                "aws_instance",
                "hashicorp/aws",
                "i-app-001",
                Map.of(
                    "instance_type", "t3.large",
                    "region", "ap-south-1"
                ),
                Set.of()
            )
        );

        System.out.println("\nDRIFT REPORT");

        service.detectDrift(workspace)
            .forEach((type, addresses) ->
                System.out.println(type + ": " + addresses)
            );

        // Refresh state.
        TerraformState refreshed = service.refresh(
            workspace,
            "platform-admin"
        );

        System.out.println(
            "\nREFRESHED SERIAL: " + refreshed.serial()
        );

        // Reject stale plans.
        TerraformPlan stalePlan = planService.generate(
            backend.read(workspace),
            desired
        );

        service.refresh(
            workspace,
            "platform-admin"
        );

        try {

            service.apply(
                stalePlan,
                "release-manager"
            );

        } catch (ConcurrencyException exception) {

            System.out.println(
                "\nSTALE PLAN REJECTED: " +
                exception.getMessage()
            );
        }

        // Demonstrate migration.
        RemoteStateBackend destination =
            new RemoteStateBackend();

        StateMigrationService.migrate(
            backend,
            destination,
            workspace
        );

        System.out.println(
            "\nMIGRATED SERIAL: " +
            destination.read(workspace).serial()
        );

        // Audit reporting.
        System.out.println("\nAUDIT EVENTS");

        audit.events().forEach(event ->
            System.out.println(
                event.timestamp() +
                " | " +
                event.actor() +
                " | " +
                event.action() +
                " | " +
                event.details()
            )
        );

        System.out.println("\nEXECUTION COMPLETED");
    }
}

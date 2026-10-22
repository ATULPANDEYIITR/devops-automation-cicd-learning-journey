# Docker Volumes: Persistent Storage, Bind Mounts, and Named Volumes

## Scope

Docker containers have a lifecycle that is independent from the lifecycle of data that applications need to retain.

A container's writable layer is convenient for temporary state, but it is not an appropriate persistence boundary for databases, uploaded files, application-generated records, or other data that must survive container replacement.

Docker provides storage mechanisms that separate application data from container lifecycle:

| Mechanism | Data owner | Survives container removal | Typical use |
|---|---|---:|---|
| Container writable layer | Container | No | Temporary runtime state |
| Named volume | Docker volume | Yes | Databases and application data |
| Bind mount | Host filesystem | Yes | Host-managed configuration, source code, controlled host data |

The central distinction is ownership.

A **named volume** is managed as a Docker storage object. A **bind mount** exposes an existing host path to the container. A container's ordinary writable layer belongs to the container itself.

A useful lifecycle model is:

`Host data / Docker volume → mount → container process → application`

Removing the container does not necessarily remove the external storage.

---

## Named volumes

A named volume has an explicit Docker-managed identity such as `orders-db`.

The important lifecycle relationship is:

`named volume → container A → container removed → container B → same named volume`

Container A can write data to the volume, be removed, and then container B can mount the same volume and recover the data.

This makes named volumes suitable for:

- PostgreSQL data directories
- MySQL or MariaDB data
- application uploads
- persistent queues where the storage layer requires filesystem persistence
- service-managed application state

The source is not an arbitrary application-specific host path. Docker manages the volume as an independent storage object.

### Named-volume properties

A named volume has a lifecycle separate from the container.

It can be inspected, backed up, restored, attached to multiple containers where appropriate, and removed independently.

Removal should be treated as a destructive storage operation. A production workflow should verify consumers, backups, retention requirements, and recovery procedures before deleting it.

The Python implementation models this explicitly with a `NamedVolume` object and a set of attached containers. Removing a container removes its attachment but does not remove the volume.

The Java implementation places the same concept into a domain model with `NamedVolume`, `Container`, `Mount`, and `StorageRepository` types. This makes volume ownership explicit rather than treating a mounted directory as ordinary container state.

The SQL model separates `storage_volumes` from `containers`. The foreign key from `container_mounts` to `storage_volumes` uses `ON DELETE RESTRICT`, preventing accidental removal while a volume is still referenced.

---

## Bind mounts

A bind mount maps a host filesystem path into a container.

The relationship is:

`host path → bind mount → container destination`

For example, a host directory such as `/srv/orders/config` can appear inside a container as `/etc/orders`.

The host path remains the source of truth. Removing the container does not remove the host directory.

Bind mounts are useful when the host itself must control the data, such as:

- controlled configuration files
- development source trees
- host-generated input data
- specific operational directories

They also introduce a larger host-security boundary than a named volume.

A container with access to a writable bind mount can modify the corresponding host filesystem. The permissions available to the container process therefore matter.

For configuration data, a read-only bind mount is often safer:

`host configuration → read-only bind mount → application`

The examples explicitly reject writes through read-only bind mounts.

---

## Container writable storage

When a container writes to a path that is not covered by an external mount, the data belongs to the container's writable layer.

The lifecycle is:

`container created → file written → container removed → file unavailable`

This behavior is demonstrated by the temporary worker in the Python, JavaScript, C++, and Java implementations.

This storage is appropriate for disposable state such as:

- temporary processing files
- intermediate artifacts
- caches that can safely be rebuilt
- short-lived job output

It should not be used as the persistence boundary for important application state.

A database container that stores its database files only in the container writable layer can lose the database when the container is replaced.

---

## Mount resolution

A container can have multiple mounts at different destinations.

For example:

`/data`

and:

`/data/cache`

can represent different storage sources.

The most specific matching mount should control access to a path under its destination.

The implementations therefore resolve mounts by selecting the longest matching destination rather than simply selecting the first mount.

This matters when storage hierarchies overlap.

A duplicate destination is rejected because two storage sources cannot safely own the same container destination in the model.

---

## Python implementation

The Python script builds an in-memory storage engine that models Docker storage semantics without requiring a running Docker daemon.

The main domain objects are:

| Type | Responsibility |
|---|---|
| `NamedVolume` | Represents Docker-managed persistent storage |
| `BindMount` | Represents host-owned storage |
| `Mount` | Connects a storage source to a container destination |
| `Container` | Represents lifecycle and ephemeral writable state |
| `DockerStorageModel` | Coordinates storage operations |

The implementation validates volume and container names, rejects parent traversal in container paths, detects mount conflicts, and distinguishes read-only mounts from writable mounts.

The named-volume demonstration writes `orders.json`, removes the original container, creates another container, mounts the same volume, and verifies that the file remains.

The bind-mount demonstration exposes configuration data through a read-only mount and attempts a write. The operation is rejected.

The ephemeral-storage demonstration writes a temporary file and then removes the container. A replacement container cannot read the file.

The backup and restore functions copy named-volume state and restore it into the same volume.

The implementation intentionally uses standard-library data structures rather than a Docker SDK so that the storage semantics remain visible and executable without an external service.

---

## JavaScript implementation

The JavaScript implementation uses an event-driven model.

`StorageRegistry` extends Node.js `EventEmitter`, allowing storage operations to produce events such as:

`volume.created`

`storage.write`

`container.started`

`container.removed`

`volume.restored`

This represents an operational perspective in which storage changes can be observed by logging, auditing, metrics, or another event consumer.

The implementation uses JavaScript `Map` and `Set` structures for volume contents and attachment tracking.

Asynchronous method boundaries are used for storage operations so the model can be extended to real filesystem or Docker Engine I/O without changing the public workflow.

The volume snapshot includes a SHA-256 checksum. The checksum is useful for detecting whether the serialized snapshot representation has changed, although it is not a substitute for a complete backup-integrity system.

The JavaScript implementation also demonstrates that a read-only bind mount is a policy decision enforced before data mutation.

---

## C++ implementation

The C++ program treats storage as a resource-management engine.

Its core structures are:

- `StorageEngine`
- `Volume`
- `BindMount`
- `Container`
- `Mount`

The engine uses `std::map` for deterministic metadata lookup and `std::set` for tracking containers attached to named volumes.

The `resolveMount` operation searches all applicable mounts and selects the most specific destination. This prevents a broader mount from incorrectly shadowing a more specific mount.

Exceptions represent invalid storage operations, including:

- unknown containers
- unknown volumes
- invalid paths
- mount conflicts
- writes through read-only mounts
- deletion of volumes that still have consumers

The program also models backup and restoration as explicit storage operations.

The C++ implementation emphasizes ownership and lifecycle boundaries. A named volume remains after its container is removed, while the container's ordinary writable data is stored separately in `ephemeralFiles`.

The use of standard containers keeps the program portable under C++17 and avoids introducing dependencies unrelated to the storage model.

---

## Java implementation

The Java implementation introduces an enterprise-oriented storage governance layer.

The domain model uses:

- `StorageType` for storage classification
- `ContainerState` for lifecycle state
- `StoragePolicy` as an immutable policy record
- `Mount` as an immutable mount description
- `NamedVolume` as a persistent storage aggregate
- `Container` as a lifecycle-managed resource
- `StorageRepository` as the persistence abstraction
- `StorageGovernanceService` for policy evaluation

The `StoragePolicy` distinguishes whether named volumes and bind mounts are allowed and whether bind mounts must be read-only.

A production-oriented policy requires database workloads to use named volumes.

This separates two concerns that are often confused:

`storage mechanism` determines where data lives.

`governance policy` determines which mechanisms an organization permits for a workload.

The Java workflow therefore validates a database volume request before attaching the volume.

The example also attempts a read-only bind mount write and demonstrates failure handling through a domain-specific exception.

Java records provide compact immutable representations for policy and mount configuration, while collections model relationships between containers and persistent storage.

---

## PostgreSQL implementation

The SQL script represents Docker storage as a relational model.

The principal relationships are:

`repositories → containers → container_mounts → storage_volumes`

and:

`container_mounts → host_paths`

Persistent volume files are stored separately from ephemeral container files.

### Relational model

| Table | Purpose |
|---|---|
| `storage_volumes` | Docker-managed named volumes |
| `host_paths` | Host filesystem paths used by bind mounts |
| `repositories` | Workload ownership and environment |
| `containers` | Container lifecycle |
| `container_mounts` | Storage-to-container mappings |
| `container_files` | Container writable-layer data |
| `volume_files` | Persistent volume data |
| `storage_operations` | Storage audit events |
| `storage_policies` | Environment-specific storage rules |

The `container_mounts` table uses a check constraint to ensure that a mount references exactly one storage source.

A named-volume mount must reference `volume_id`.

A bind mount must reference `host_path_id`.

This prevents an invalid record from simultaneously representing two different storage mechanisms.

The unique constraint on `(container_id, container_destination)` prevents two mounts from occupying the same destination.

---

## Database-level policy enforcement

The `validate_mount_policy()` trigger examines the environment associated with the container and applies the corresponding storage policy.

Production and staging policies require bind mounts to be read-only.

The policy also requires database workloads to use named volumes.

This demonstrates an important distinction between application-level validation and database-level enforcement.

Application code can reject a dangerous mount request, but database constraints and triggers provide an additional integrity boundary for systems that store infrastructure metadata centrally.

The SQL script intentionally attempts a prohibited writable bind mount inside a transaction and savepoint. PostgreSQL reports the expected rejection while the savepoint is rolled back, leaving the valid storage configuration intact.

---

## Transactions and integrity

Storage metadata should not claim that an operation succeeded when the associated state change failed.

The SQL example therefore updates a persistent volume file and records the corresponding operation in one transaction.

The logical unit is:

`BEGIN → modify persistent state → audit operation → COMMIT`

If the write fails before commit, both the data change and audit record can be rolled back.

This is particularly important for infrastructure metadata because partial state can make an operational system report storage that does not actually exist or an operation that did not actually complete.

---

## Backup and restore

Persistent storage requires a lifecycle beyond mounting.

A useful operational sequence is:

`write data → verify persistence → backup → validate backup → restore when required`

A named volume can survive container replacement, but persistence alone is not backup.

If the underlying volume is corrupted, deleted, encrypted by an attacker, or otherwise unavailable, a second recovery mechanism is required.

The source implementations therefore expose backup or snapshot operations for named volumes.

A production backup strategy should also consider:

- application-consistent snapshots
- database-specific backup semantics
- encryption
- access control
- retention
- backup verification
- restore testing
- storage capacity
- recovery point objectives
- recovery time objectives

A simple copied dictionary or SQL row is a learning model, not a complete backup system for a production database.

---

## Security considerations

### Bind-mount exposure

A writable bind mount can expose host filesystem changes to a container.

The risk is substantially different from ordinary application data stored in a Docker-managed named volume.

Production policies should restrict host paths and prefer read-only access where mutation is unnecessary.

### Sensitive host paths

Paths containing operating-system credentials, Docker daemon control interfaces, SSH material, or other privileged host data should not be exposed casually to containers.

A storage policy should classify host paths rather than treating every bind mount as equivalent.

### Read-only mounts

Read-only mounts reduce the mutation surface.

They do not automatically make data safe from disclosure. A container can still read information made available through a read-only mount.

Therefore:

`read-only` controls modification.

It does not necessarily control confidentiality.

### Path traversal

The Python, JavaScript, C++, and Java models reject parent traversal such as `../`.

This prevents a container destination such as `/data/../etc` from bypassing the intended logical mount boundary in the simulation.

Real Docker storage security also depends on the Docker Engine, operating system permissions, namespaces, container privileges, SELinux or AppArmor configuration where applicable, and the underlying filesystem.

---

## Performance characteristics

Storage performance depends on the storage driver, filesystem, operating system, Docker configuration, workload, and access pattern.

Named volumes generally provide a cleaner persistence abstraction for container-managed application data.

Bind mounts can be useful when direct host access is required, but host filesystem behavior and synchronization characteristics can influence performance, particularly in environments where containers run through a virtualization layer.

The learning implementations use in-memory maps, so their performance does not represent actual Docker filesystem performance.

For the models:

- Python dictionaries provide average constant-time key lookup.
- JavaScript `Map` provides average constant-time key lookup.
- C++ `std::map` provides logarithmic lookup.
- Java `HashMap` provides average constant-time key lookup.
- PostgreSQL indexes accelerate volume and mount lookups where the indexed columns are used by queries.

These are metadata-model characteristics, not benchmarks of Docker storage.

---

## Failure modes represented by the implementations

| Failure | Expected behavior |
|---|---|
| Duplicate volume name | Reject creation |
| Invalid volume name | Reject creation |
| Unknown container | Reject operation |
| Unknown named volume | Reject operation |
| Unknown bind source | Reject mount |
| Duplicate mount destination | Reject mount |
| Relative container path | Reject operation |
| Parent traversal | Reject operation |
| Write to read-only mount | Reject write |
| Missing persistent file | Report storage error |
| Container removal | Delete ephemeral state |
| Named-volume consumer remains | Protect volume from deletion |
| Invalid production bind policy | Reject mount |
| Failed transactional operation | Roll back database state |

---

## Conceptual distinction

The three storage choices can be understood through ownership rather than through syntax.

| Question | Writable layer | Named volume | Bind mount |
|---|---|---|---|
| Who owns the data lifecycle? | Container | Docker volume | Host filesystem |
| Does data survive container removal? | No | Yes | Yes |
| Is a host path explicitly selected? | No | No | Yes |
| Good default for database data? | No | Yes | Sometimes, when deliberately managed |
| Good for host-controlled configuration? | No | Sometimes | Yes |
| Can it be read-only? | Not as a storage-source mount | Yes | Yes |
| Requires host path governance? | No | Less directly | Yes |
| Requires backup planning? | If data matters | Yes | Yes |

The mechanisms are related but are not interchangeable.

A container image defines application software.

A container writable layer provides disposable runtime changes.

A named volume provides Docker-managed persistent storage.

A bind mount exposes host-owned storage.

The correct choice depends on who should own the data lifecycle and what level of host access is required.

---

## Practical workflow represented by the five implementations

A persistent database workload can be modeled as:

`database container`
→ `named volume`
→ `/var/lib/postgresql/data`
→ `database files`

A host-controlled configuration workload can be modeled as:

`host configuration directory`
→ `read-only bind mount`
→ `/etc/application`
→ `application reads configuration`

A temporary processing workload can be modeled as:

`worker container`
→ `container writable layer`
→ `/tmp`
→ `container removed`
→ `temporary data discarded`

This separation keeps application lifecycle, storage lifecycle, and host ownership explicit rather than treating every filesystem path inside a container as persistent data.

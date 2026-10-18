# Docker CLI: Images, Containers, and Lifecycle Operations

## Purpose

The Docker command-line interface provides direct control over container images and containers managed by a Docker engine. Commands such as `pull`, `run`, `ps`, `exec`, `logs`, `stop`, and `start` support different stages of a container workflow.

These commands operate on different resources. An image is a reusable template, while a container is a specific instance created from an image. A container can exist without running, and stopping a container does not normally remove it.

The implementations use Alpine Linux for lightweight command-line demonstrations. The examples distinguish simulated lifecycle behavior from commands that interact with a real Docker installation.

## Images and containers

An image contains the filesystem layers and metadata required to create a container. An image reference commonly includes a repository and tag, such as `alpine:3.22`.

A container adds an isolated runtime environment and a writable layer to an image. Its lifecycle includes creation, execution, stopping, restarting, and eventual removal.

| Command | Purpose | Important behavior |
|---|---|---|
| `docker pull IMAGE` | Downloads an image | Retrieves image content without starting a container |
| `docker run IMAGE COMMAND` | Creates and starts a container | Combines container creation with process execution |
| `docker ps` | Lists running containers | Excludes stopped containers by default |
| `docker ps -a` | Lists all retained containers | Includes stopped and exited containers |
| `docker exec CONTAINER COMMAND` | Runs another process in a container | Normally requires the target container to be running |
| `docker logs CONTAINER` | Reads container output | Reads logs associated with the container's main process |
| `docker stop CONTAINER` | Stops a running container | Requests graceful termination before forced termination |
| `docker start CONTAINER` | Starts an existing stopped container | Reuses the existing container rather than creating a new one |

## The image workflow: `pull`

The Python implementation validates image references before calling the CLI and captures the exit status and error output. The JavaScript implementation uses asynchronous process execution, allowing a caller to wait for the download without blocking the Node.js event loop.

Image downloads can take substantially longer than ordinary inspection commands. Both implementations therefore allow a longer timeout for `pull`.

A successful pull confirms that the image was retrieved. It does not confirm that the image's application will start correctly or that the image is appropriate for production.

For reproducible deployments, teams should use controlled image versions, verify image provenance, and consider digest-based references when exact image identity matters.

## Creating workloads with `run`

The `run` command creates a container and starts its main process. It supports both temporary tasks and long-running services.

A one-shot operation can use:

`docker run --rm alpine:3.22 sh -c "echo task-completed"`

The `--rm` option removes the container after its main process exits. This is useful for short tasks that do not require retained container state.

A persistent service can use detached execution:

`docker run -d --name orders-api alpine:3.22 sh -c "while true; do echo ready; sleep 5; done"`

The `-d` option runs the container in the background. The explicit name makes subsequent inspection and lifecycle commands easier to target.

The command above is a training workload rather than a production API. A production service would generally need a real application process, resource limits, appropriate networking, health checks, and deliberate logging and restart policies.

## Inspecting containers with `ps`

The `ps` command reports the state of container instances. Running containers appear in the default output, while `ps -a` also displays retained containers that have stopped.

The Python implementation requests JSON-formatted records and parses each record into a dictionary. The JavaScript implementation handles Docker's newline-delimited JSON format by parsing each output line independently.

Machine-readable output is preferable to relying on fixed column positions in human-readable terminal output. It allows automation to identify names, IDs, images, and lifecycle states without assuming a particular display layout.

The database implementation provides a relational inventory view that joins container records to their image references. It is an audit model, not a live replacement for `docker ps`.

## Running commands with `exec`

`docker exec` starts a new process inside an existing running container.

For example:

`docker exec orders-api sh -c "echo readiness-check"`

The command does not replace the container's main process. It creates an additional process within the container's runtime environment.

This distinction matters when troubleshooting. If the main process has exited, `exec` generally cannot be used against that container. Inspect its state and logs first, then restart it if appropriate.

Automation should pass the container name and command as separate arguments. Building a shell command from untrusted strings introduces command-injection risks.

The Python and JavaScript implementations use argument arrays rather than concatenated shell command strings. The Java implementation uses `ProcessBuilder` for the same reason.

## Reading output with `logs`

`docker logs` retrieves output associated with the container's main process, usually its standard output and standard error streams when the logging configuration supports them.

A bounded query such as `docker logs --tail 20 orders-api` is useful when diagnosing a recent startup failure without printing an unlimited amount of output.

Logs can reveal application startup errors, configuration failures, unexpected termination, and repeated restart patterns. They do not replace application metrics or health checks.

Log availability and retention depend on the logging driver and its configuration. Applications that write only to files inside a container may require separate log collection.

The implementations validate log-tail limits and report command failures rather than interpreting empty output as proof of success.

## Stopping and starting containers

`docker stop orders-api` requests that the main process terminate gracefully. Docker waits for the configured grace period before forcibly terminating the container if necessary.

`docker start orders-api` starts an existing stopped container. It does not build a new image or create a new container identity.

This behavior differs from `docker run`, which creates a container instance. Repeatedly using `run` with an already-used container name can fail because container names must be unique among existing containers.

The Python implementation demonstrates stopping and restarting a service in a cleanup-controlled workflow. The JavaScript implementation uses asynchronous operations and a `finally` block to attempt cleanup even after a failure.

The Java implementation represents lifecycle states with an enum and validates transitions through a controller. The C++ program maintains an in-memory registry for lifecycle simulation before optionally executing real CLI commands.

## Python implementation

The Python file defines a `DockerCLI` wrapper around `subprocess.run`.

Its `run` method captures standard output and standard error, applies a timeout, and returns the exit code. The `require_success` method converts unsuccessful command execution into an exception containing the failure details.

The wrapper implements image retrieval, container creation, listing, execution, log retrieval, inspection, stopping, and starting. It parses JSON returned by Docker's formatting options instead of scraping the human-readable table.

The demonstration first executes a temporary task and then creates a detached service container. It inspects the container, runs an additional command, reads logs, stops and starts the service, and removes the named training container.

The cleanup operation is deliberately restricted to the explicitly named laboratory container. Automated cleanup should never target an unrestricted set of containers.

## JavaScript implementation

The JavaScript file provides an asynchronous `runDocker` function built on Node.js's `child_process.spawn`.

This approach allows Docker commands to run without blocking the event loop. The wrapper collects standard output and standard error, enforces a timeout, limits captured output, and rejects unsuccessful commands.

`DockerService` groups operations by their domain purpose. Its `listContainers` method parses newline-delimited JSON, while `inspectState` requests structured container-state output.

A generated container name reduces the chance of colliding with an existing training container. The main workflow uses `try` and `finally` to remove that specific container when possible.

The output limit and timeout help prevent an automation task from waiting indefinitely or accumulating unbounded captured output. They do not impose CPU, memory, or disk limits on the container itself.

## C++ case study

The C++ implementation models a small deployment containing an orders service and a report worker.

`DeploymentRegistry` stores container specifications in a `std::map`, indexed by container name. Each record tracks its image, command, lifecycle state, restart count, and event history.

The registry rejects duplicate names and invalid transitions. For example, starting an already-running container or restarting a container after registry removal produces an exception. These rules model application-level lifecycle expectations rather than attempting to duplicate every Docker Engine state.

The program runs in simulation mode by default. The `--execute` argument enables actual Docker commands. It pulls an image, starts a named detached workload, lists containers, executes a readiness check, reads logs, stops and restarts the workload, and then removes it.

The optional execution helper applies POSIX shell quoting to individual arguments. This makes its platform assumptions explicit: it is not a portable Windows command-line quoting implementation, and direct operating-system process APIs would be preferable for a cross-platform production utility.

The case study demonstrates why lifecycle state, command exit status, and cleanup policy should be handled explicitly. An application registry is useful for modeling intended behavior, but Docker's own state remains authoritative for real container operations.

## Java implementation

The Java program models operations with an `Operation` enum, container states with a `Lifecycle` enum, and workload configuration with a `ServiceDefinition` record.

The record validates required fields and defensively copies its command list. This prevents callers from mutating the command definition through the original list reference.

`DockerClient` encapsulates command execution through `ProcessBuilder`. It enforces timeouts, captures output, checks exit codes, and provides named methods for Docker operations.

`ServiceController` adds transition rules around start and stop actions. These rules are application-level constraints and must be reconciled with actual Docker state in a production implementation.

The program supports simulation without requiring Docker access. With `--execute`, it performs live operations against the local engine and attempts to remove the training container afterward.

A production-grade controller would also need robust concurrent output draining, bounded output capture, container inspection before transitions, structured logging, and explicit handling of cleanup failures. These concerns become important when many services are controlled concurrently.

## SQL data model

The PostgreSQL script defines the `docker_lab` schema to store a record of observed Docker CLI operations.

- `images` stores repository names, tags, optional digests, and pull timestamps. A unique constraint prevents duplicate repository-and-tag pairs.
- `containers` records container identity, image relationships, lifecycle state, timestamps, and exit codes. A foreign key ensures that every registered container references a known image.
- `cli_operations` records the command name, arguments, result, exit status, output excerpt, and execution time. JSONB stores argument arrays in a queryable format.
- `container_events` records lifecycle events and structured event details independently of command execution records.

Check constraints restrict recognized commands and lifecycle values. They also ensure that successful operations have a zero exit status and failed operations have a nonzero exit status.

Indexes support lifecycle filtering, recent-operation queries, failure analysis, and chronological event retrieval.

The `container_inventory` view joins containers to their image references and excludes records marked as removed. The reporting queries aggregate operation success rates, display inventory, retrieve recent events, and identify failed commands.

The SQL script intentionally models operational history rather than controlling Docker. A database transaction can make these records consistent within PostgreSQL, but it cannot make an external Docker operation atomic with a database write. Production automation should therefore record command attempts and outcomes carefully, including cases where a command succeeds but the subsequent database update fails.

## Failure handling and troubleshooting

| Symptom | Likely cause | Diagnostic action |
|---|---|---|
| Docker executable not found | CLI missing or PATH is incorrect | Check the installation and terminal PATH |
| Cannot connect to the Docker daemon | Engine stopped or access unavailable | Inspect Docker Desktop or Docker Engine status |
| Image pull fails | Registry, authentication, network, or image-reference problem | Read the complete pull error and verify the image reference |
| Container name conflict | An existing container already uses the name | Inspect with `docker ps -a` |
| `exec` fails | Container is stopped or command is unavailable | Inspect state and verify the command exists in the image |
| Container exits immediately | Main process completed or failed | Use `docker ps -a` and `docker logs` |
| Stop operation takes too long | Main process does not exit gracefully | Check the configured stop timeout and application shutdown behavior |
| Start fails | Container state, configuration, or daemon problem | Inspect the container and read the reported error |

Exit codes must be interpreted alongside command output and the container's actual state. A timeout does not necessarily prove that the Docker operation had no effect. After an interrupted or timed-out operation, inspect the named container before retrying a potentially destructive command.

## Operational and security considerations

- **Image trust:** Use approved images and controlled versions. A successful pull does not establish image integrity or safety.
- **Container permissions:** Avoid privileged mode and unnecessary capabilities. Mount only required host paths.
- **Resource limits:** Set suitable CPU and memory constraints for workloads that might consume excessive resources.
- **Secrets:** Avoid passing credentials through command-line arguments or storing them in logs. Use an appropriate secrets-management mechanism.
- **Cleanup:** Remove only containers created by the automation task. Forced removal can terminate a running workload and discard its writable container state.
- **Logging:** Limit captured output, protect sensitive log content, and configure retention for long-running systems.
- **Automation:** Use explicit timeouts, inspect state before retries, record exit codes, and make operations idempotent where practical.
- **Production deployment:** Use a deployment orchestrator when the workload requires scheduling, health-based recovery, multi-host coordination, or controlled rollouts.

## Implementation boundaries

The programs demonstrate local Docker CLI operations, not a complete production deployment platform. Their lifecycle models illustrate common state transitions, while the Docker Engine remains authoritative for real container status.

The SQL records are illustrative audit data and are not synchronized automatically with the Docker daemon. The C++ execution helper assumes a POSIX shell, while the Python, JavaScript, and Java implementations pass arguments through their respective process APIs.

All live demonstrations should be run only in an environment where the user has permission to access Docker and create or remove the explicitly named training containers.

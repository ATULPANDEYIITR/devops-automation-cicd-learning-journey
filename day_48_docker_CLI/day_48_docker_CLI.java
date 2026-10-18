import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/**
 * Enterprise-oriented Docker CLI operations model.
 *
 * Compile: javac DockerCliOperations.java
 * Simulate: java DockerCliOperations
 * Execute:  java DockerCliOperations --execute
 *
 * Requires Docker CLI and an accessible Docker engine for live operations.
 */
public class DockerCliOperations {

    enum Lifecycle {
        CREATED, RUNNING, STOPPED, REMOVED, FAILED
    }

    enum Operation {
        PULL, RUN, PS, EXEC, LOGS, STOP, START
    }

    record CommandResult(int exitCode, String stdout, String stderr) {
        boolean successful() {
            return exitCode == 0;
        }
    }

    record ServiceDefinition(
            String name,
            String image,
            List<String> command,
            boolean persistent
    ) {
        ServiceDefinition {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Service name is required");
            }
            if (image == null || image.isBlank()) {
                throw new IllegalArgumentException("Image is required");
            }
            command = List.copyOf(command);
        }
    }

    static final class DockerException extends RuntimeException {
        private final int exitCode;

        DockerException(String message, int exitCode) {
            super(message);
            this.exitCode = exitCode;
        }

        int exitCode() {
            return exitCode;
        }
    }

    static final class DockerClient {
        private final Duration timeout;

        DockerClient(Duration timeout) {
            this.timeout = Objects.requireNonNull(timeout);
            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalArgumentException("Timeout must be positive");
            }
        }

        CommandResult execute(List<String> arguments) {
            if (arguments.isEmpty()) {
                throw new IllegalArgumentException("Docker arguments are required");
            }

            List<String> command = new ArrayList<>();
            command.add("docker");
            command.addAll(arguments);

            Process process;
            try {
                // ProcessBuilder avoids shell interpolation and treats every
                // argument as an independent command-line token.
                process = new ProcessBuilder(command).start();

                boolean completed = process.waitFor(
                        timeout.toMillis(), TimeUnit.MILLISECONDS);

                if (!completed) {
                    process.destroyForcibly();
                    throw new DockerException("Docker command timed out", -1);
                }

                String stdout;
                String stderr;

                try (BufferedReader out = new BufferedReader(
                             new InputStreamReader(process.getInputStream()));
                     BufferedReader err = new BufferedReader(
                             new InputStreamReader(process.getErrorStream()))) {
                    stdout = out.lines().reduce("", (a, b) -> a + b + "\n");
                    stderr = err.lines().reduce("", (a, b) -> a + b + "\n");
                }

                int exitCode = process.exitValue();
                return new CommandResult(exitCode, stdout.strip(), stderr.strip());

            } catch (IOException e) {
                throw new IllegalStateException(
                        "Cannot launch Docker CLI. Verify installation and PATH.", e);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Docker operation interrupted", e);
            }
        }

        CommandResult requireSuccess(String... arguments) {
            CommandResult result = execute(List.of(arguments));
            if (!result.successful()) {
                throw new DockerException(
                        "docker " + arguments[0] + " failed: " + result.stderr(),
                        result.exitCode());
            }
            return result;
        }

        CommandResult pull(String image) {
            return requireSuccess("pull", image);
        }

        CommandResult ps(boolean includeStopped) {
            return includeStopped
                    ? requireSuccess("ps", "-a")
                    : requireSuccess("ps");
        }

        CommandResult run(ServiceDefinition service) {
            List<String> args = new ArrayList<>(
                    List.of("run", "--name", service.name()));

            if (service.persistent()) {
                args.add("-d");
            } else {
                args.add("--rm");
            }

            args.add(service.image());
            args.addAll(service.command());
            return requireSuccess(args.toArray(String[]::new));
        }

        CommandResult exec(String container, List<String> command) {
            if (command.isEmpty()) {
                throw new IllegalArgumentException("Exec command cannot be empty");
            }

            List<String> args = new ArrayList<>(List.of("exec", container));
            args.addAll(command);
            return requireSuccess(args.toArray(String[]::new));
        }

        CommandResult logs(String container, int tail) {
            if (tail < 1 || tail > 10000) {
                throw new IllegalArgumentException("Invalid log tail");
            }
            return requireSuccess("logs", "--tail", Integer.toString(tail), container);
        }

        CommandResult stop(String container) {
            return requireSuccess("stop", "--time", "10", container);
        }

        CommandResult start(String container) {
            return requireSuccess("start", container);
        }

        CommandResult remove(String container) {
            return requireSuccess("rm", "-f", container);
        }
    }

    static final class ServiceController {
        private final DockerClient client;
        private Lifecycle state = Lifecycle.CREATED;

        ServiceController(DockerClient client) {
            this.client = client;
        }

        void transition(Operation operation, String container) {
            switch (operation) {
                case STOP -> {
                    requireState(Lifecycle.RUNNING);
                    client.stop(container);
                    state = Lifecycle.STOPPED;
                }
                case START -> {
                    if (state != Lifecycle.STOPPED && state != Lifecycle.CREATED) {
                        throw new IllegalStateException(
                                "Start requires a stopped or created service");
                    }
                    client.start(container);
                    state = Lifecycle.RUNNING;
                }
                default -> throw new IllegalArgumentException(
                        "Operation does not represent a lifecycle transition");
            }
        }

        private void requireState(Lifecycle expected) {
            if (state != expected) {
                throw new IllegalStateException(
                        "Expected " + expected + " but found " + state);
            }
        }

        Lifecycle state() {
            return state;
        }
    }

    private static void printResult(String label, CommandResult result) {
        System.out.println("\n" + label);
        if (!result.stdout().isBlank()) {
            System.out.println(result.stdout());
        }
        if (!result.stderr().isBlank()) {
            System.err.println(result.stderr());
        }
    }

    public static void main(String[] args) {
        boolean execute = args.length == 1 && args[0].equals("--execute");

        if (args.length > 1 || (args.length == 1 && !execute)) {
            System.err.println("Usage: java DockerCliOperations [--execute]");
            System.exit(2);
        }

        ServiceDefinition service = new ServiceDefinition(
                "java-docker-cli-lab",
                "alpine:3.22",
                List.of("sh", "-c",
                        "while true; do echo enterprise-service-ready; sleep 5; done"),
                true
        );

        if (!execute) {
            System.out.println("Docker CLI operations model");
            for (Operation operation : Operation.values()) {
                System.out.println(operation + ": " + switch (operation) {
                    case PULL -> "Download image layers into the local image store";
                    case RUN -> "Create a container and optionally detach";
                    case PS -> "Inspect running or all container records";
                    case EXEC -> "Run a new process in a running container";
                    case LOGS -> "Read the container's main-process output";
                    case STOP -> "Request graceful shutdown before forced termination";
                    case START -> "Restart an existing stopped container";
                });
            }
            System.out.println("Run with --execute to use the local Docker engine.");
            return;
        }

        DockerClient client = new DockerClient(Duration.ofMinutes(10));
        boolean created = false;

        try {
            printResult("Pull image", client.pull(service.image()));

            // The unique, fixed training name makes cleanup explicit.
            printResult("Run detached service", client.run(service));
            created = true;

            printResult("Running containers", client.ps(false));
            printResult("All containers", client.ps(true));

            printResult("Execute readiness check",
                    client.exec(service.name(),
                            List.of("sh", "-c", "echo readiness-check")));

            printResult("Read recent logs", client.logs(service.name(), 10));

            ServiceController controller = new ServiceController(client);
            controller.transition(Operation.START, service.name());
            controller.transition(Operation.STOP, service.name());
            System.out.println("Lifecycle state: " + controller.state());

            controller.transition(Operation.START, service.name());
            System.out.println("Lifecycle state: " + controller.state());

        } catch (RuntimeException e) {
            System.err.println("Docker workflow failed: " + e.getMessage());
            System.exitCode = 1;
        } finally {
            if (created) {
                try {
                    printResult("Remove training container",
                            client.remove(service.name()));
                } catch (RuntimeException cleanupError) {
                    System.err.println(
                            "Cleanup failed: " + cleanupError.getMessage());
                    System.exitCode = 1;
                }
            }
        }
    }
}

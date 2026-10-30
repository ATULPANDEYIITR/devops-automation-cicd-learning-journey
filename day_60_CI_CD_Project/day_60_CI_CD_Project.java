import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import java.util.jar.Manifest;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class CiCdPipelineDemo {

    private static final Path DEFAULT_WORKSPACE =
        Path.of("ci_cd_java_workspace");

    private static final String MARKER = ".ci_cd_java_workspace";

    private static final String IMAGE_TAG = "inventory-health-service:1.0.0";

    private static final String SERVICE_SOURCE = """
        package com.acme;

        import com.sun.net.httpserver.HttpExchange;
        import com.sun.net.httpserver.HttpServer;
        import java.io.IOException;
        import java.net.InetSocketAddress;
        import java.nio.charset.StandardCharsets;
        import java.util.Map;
        import java.util.TreeMap;
        import java.util.concurrent.Executors;

        public final class HealthService {

            private static final class Inventory {
                private final Map<String, Integer> items = new TreeMap<>();

                synchronized void add(String sku, int quantity) {
                    if (sku == null || !sku.matches("[A-Z0-9][A-Z0-9-]{0,31}")) {
                        throw new IllegalArgumentException("Invalid SKU");
                    }
                    if (quantity <= 0) {
                        throw new IllegalArgumentException("Quantity must be positive");
                    }
                    if (items.putIfAbsent(sku, quantity) != null) {
                        throw new IllegalArgumentException("Duplicate SKU");
                    }
                }

                synchronized int size() {
                    return items.size();
                }

                synchronized String toJson() {
                    StringBuilder result = new StringBuilder("[");
                    boolean first = true;

                    for (Map.Entry<String, Integer> entry : items.entrySet()) {
                        if (!first) {
                            result.append(",");
                        }
                        first = false;
                        result.append("{\\"sku\\":\\"")
                            .append(entry.getKey())
                            .append("\\",\\"quantity\\":")
                            .append(entry.getValue())
                            .append("}");
                    }

                    return result.append("]").toString();
                }
            }

            private static void send(
                HttpExchange exchange,
                int status,
                String response
            ) throws IOException {
                byte[] body = response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                    "Content-Type",
                    "application/json; charset=utf-8"
                );
                exchange.getResponseHeaders().set(
                    "X-Content-Type-Options",
                    "nosniff"
                );
                exchange.sendResponseHeaders(status, body.length);

                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            }

            private static void startServer() throws IOException {
                String portValue = System.getenv().getOrDefault("PORT", "8080");
                int port;

                try {
                    port = Integer.parseInt(portValue);
                } catch (NumberFormatException exception) {
                    throw new IllegalArgumentException("PORT must be an integer");
                }

                if (port < 1 || port > 65535) {
                    throw new IllegalArgumentException("PORT is outside the valid range");
                }

                Inventory inventory = new Inventory();
                inventory.add("SKU-100", 25);
                inventory.add("SKU-200", 12);

                HttpServer server = HttpServer.create(
                    new InetSocketAddress("0.0.0.0", port),
                    0
                );

                server.createContext("/health", exchange ->
                    send(exchange, 200, "{\\"status\\":\\"ok\\"}")
                );

                server.createContext("/inventory", exchange ->
                    send(exchange, 200, "{\\"items\\":" + inventory.toJson() + "}")
                );

                server.setExecutor(Executors.newFixedThreadPool(4));
                server.start();

                System.out.println("Inventory health service listening on " + port);
            }

            private static void runSelfTests() {
                Inventory inventory = new Inventory();
                inventory.add("SKU-100", 5);
                inventory.add("SKU-200", 8);

                if (inventory.size() != 2) {
                    throw new AssertionError("Inventory size mismatch");
                }

                boolean duplicateRejected = false;
                try {
                    inventory.add("SKU-100", 9);
                } catch (IllegalArgumentException expected) {
                    duplicateRejected = true;
                }

                if (!duplicateRejected) {
                    throw new AssertionError("Duplicate SKU was accepted");
                }

                boolean invalidQuantityRejected = false;
                try {
                    inventory.add("SKU-300", 0);
                } catch (IllegalArgumentException expected) {
                    invalidQuantityRejected = true;
                }

                if (!invalidQuantityRejected) {
                    throw new AssertionError("Invalid quantity was accepted");
                }

                System.out.println("SELF_TESTS_PASSED");
            }

            public static void main(String[] args) throws Exception {
                if (args.length == 1 && args[0].equals("--self-test")) {
                    runSelfTests();
                    return;
                }

                startServer();
            }
        }
        """;

    private enum Stage {
        BUILD,
        TEST,
        SCAN,
        PACKAGE,
        DOCKERIZE
    }

    private enum StageStatus {
        PENDING,
        RUNNING,
        SUCCEEDED,
        FAILED,
        SKIPPED
    }

    private record StageResult(
        Stage stage,
        StageStatus status,
        Instant startedAt,
        Instant finishedAt,
        long durationMillis,
        String detail
    ) {}

    @FunctionalInterface
    private interface StageAction {
        String execute() throws Exception;
    }

    private static final class PipelineException extends Exception {
        PipelineException(String message) {
            super(message);
        }

        PipelineException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final Path workspace;
    private final boolean dockerEnabled;
    private final EnumMap<Stage, StageStatus> states =
        new EnumMap<>(Stage.class);
    private final List<StageResult> results = new ArrayList<>();

    private Path classesDirectory;
    private Path packageDirectory;

    private CiCdPipelineDemo(Path workspace, boolean dockerEnabled) {
        this.workspace = workspace;
        this.dockerEnabled = dockerEnabled;

        for (Stage stage : Stage.values()) {
            states.put(stage, StageStatus.PENDING);
        }
    }

    private static String javaExecutable() {
        String executable = System.getProperty("os.name")
            .toLowerCase()
            .contains("win") ? "java.exe" : "java";

        return Path.of(
            System.getProperty("java.home"),
            "bin",
            executable
        ).toString();
    }

    private static void ensureWorkspace(Path root) throws IOException, PipelineException {
        if (Files.isSymbolicLink(root)) {
            throw new PipelineException("Workspace must not be a symbolic link.");
        }

        Files.createDirectories(root);
        Path marker = root.resolve(MARKER);

        if (Files.exists(marker)) {
            if (!Files.isRegularFile(marker)) {
                throw new PipelineException("Workspace marker must be a regular file.");
            }
            return;
        }

        try (Stream<Path> entries = Files.list(root)) {
            if (entries.findAny().isPresent()) {
                throw new PipelineException(
                    "Refusing to use a non-empty directory without a workspace marker."
                );
            }
        }

        Files.writeString(
            marker,
            "Managed by the Java 17 CI/CD demonstration pipeline.\n",
            StandardCharsets.UTF_8
        );
    }

    private static void deleteManagedDirectory(Path path) throws IOException, PipelineException {
        if (Files.isSymbolicLink(path)) {
            throw new PipelineException("Refusing to remove symbolic link: " + path);
        }

        if (!Files.exists(path)) {
            return;
        }

        Files.walkFileTree(path, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult visitFile(
                Path file,
                BasicFileAttributes attributes
            ) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                Path directory,
                IOException error
            ) throws IOException {
                if (error != null) throw error;
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private void prepareProject() throws Exception {
        for (String directory : List.of("build", "dist")) {
            deleteManagedDirectory(workspace.resolve(directory));
        }

        Path sourceFile = workspace.resolve("src/com/acme/HealthService.java");
        Files.createDirectories(sourceFile.getParent());

        Files.writeString(
            sourceFile,
            SERVICE_SOURCE,
            StandardCharsets.UTF_8
        );

        classesDirectory = workspace.resolve("build/classes");
        packageDirectory = workspace.resolve("dist/package");
        Files.createDirectories(classesDirectory);
    }

    private static String runProcess(
        List<String> command,
        Path workingDirectory,
        Duration timeout
    ) throws PipelineException {
        Process process;

        try {
            process = new ProcessBuilder(command)
                .directory(workingDirectory.toFile())
                .redirectErrorStream(true)
                .start();
        } catch (IOException exception) {
            throw new PipelineException(
                "Unable to start process: " + command.get(0),
                exception
            );
        }

        try {
            boolean completed = process.waitFor(
                timeout.toMillis(),
                java.util.concurrent.TimeUnit.MILLISECONDS
            );

            if (!completed) {
                process.destroyForcibly();
                throw new PipelineException(
                    "Process timed out: " + command.get(0)
                );
            }

            String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
            );

            if (process.exitValue() != 0) {
                throw new PipelineException(
                    "Process failed with exit code " + process.exitValue()
                    + ": " + command.get(0) + "\n" + output
                );
            }

            return output.strip();

        } catch (InterruptedException exception) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw new PipelineException("Process execution was interrupted.", exception);
        } catch (IOException exception) {
            throw new PipelineException("Unable to read process output.", exception);
        }
    }

    private String build() throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new PipelineException(
                "A JDK is required. The current Java runtime has no system compiler."
            );
        }

        Path source = workspace.resolve("src/com/acme/HealthService.java");

        int exitCode = compiler.run(
            null,
            null,
            null,
            "--release",
            "17",
            "-Xlint:all",
            "-d",
            classesDirectory.toString(),
            source.toString()
        );

        if (exitCode != 0) {
            throw new PipelineException("Java compiler returned exit code " + exitCode);
        }

        return "Compiled the enterprise inventory service with Java 17.";
    }

    private String test() throws Exception {
        String output = runProcess(
            List.of(
                javaExecutable(),
                "-cp",
                classesDirectory.toString(),
                "com.acme.HealthService",
                "--self-test"
            ),
            workspace,
            Duration.ofSeconds(30)
        );

        if (!output.contains("SELF_TESTS_PASSED")) {
            throw new PipelineException("Expected self-test completion marker was missing.");
        }

        return output;
    }

    private String scan() throws Exception {
        Path source = workspace.resolve("src/com/acme/HealthService.java");
        String contents = Files.readString(source, StandardCharsets.UTF_8);

        List<String> findings = new ArrayList<>();

        Pattern credentialPattern = Pattern.compile(
            "(?i)(api[_-]?key|password|secret|access[_-]?token)"
            + "\\s*[:=]\\s*[\"] [^\"]{8,}[\"]".replace(" ", "")
        );

        if (credentialPattern.matcher(contents).find()) {
            findings.add("Possible hard-coded credential");
        }

        for (String prohibited : List.of(
            "Runtime.getRuntime().exec",
            "ProcessBuilder("
        )) {
            if (contents.contains(prohibited)) {
                findings.add("Prohibited process execution pattern: " + prohibited);
            }
        }

        if (!findings.isEmpty()) {
            throw new PipelineException(
                "Static security policy failed: " + String.join("; ", findings)
            );
        }

        return "Java source passed configured static security rules.";
    }

    private static String sha256(Path file) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (var input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }

    private String packageApplication() throws Exception {
        Files.createDirectories(packageDirectory);

        Manifest manifest = new Manifest();
        Attributes attributes = manifest.getMainAttributes();
        attributes.put(Attributes.Name.MANIFEST_VERSION, "1.0");
        attributes.put(Attributes.Name.MAIN_CLASS, "com.acme.HealthService");

        Path jarFile = packageDirectory.resolve("health-service.jar");

        try (JarOutputStream jar = new JarOutputStream(
            Files.newOutputStream(jarFile),
            manifest
        )) {
            List<Path> classFiles;

            try (Stream<Path> paths = Files.walk(classesDirectory)) {
                classFiles = paths
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.naturalOrder())
                    .toList();
            }

            for (Path file : classFiles) {
                String entryName = classesDirectory
                    .relativize(file)
                    .toString()
                    .replace('\\', '/');

                jar.putNextEntry(new JarEntry(entryName));
                Files.copy(file, jar);
                jar.closeEntry();
            }
        }

        String manifestJson = """
            {
              "application": "inventory-health-service",
              "version": "1.0.0",
              "artifact": "health-service.jar",
              "sha256": "%s"
            }
            """.formatted(sha256(jarFile));

        Files.writeString(
            packageDirectory.resolve("release-manifest.json"),
            manifestJson,
            StandardCharsets.UTF_8
        );

        return "Created executable JAR and SHA-256 release manifest.";
    }

    private String dockerize() throws Exception {
        String dockerfile = """
            FROM eclipse-temurin:17-jre-jammy

            ENV PORT=8080
            WORKDIR /app

            COPY --chown=10001:10001 health-service.jar /app/health-service.jar

            USER 10001:10001

            EXPOSE 8080

            ENTRYPOINT ["java", "-jar", "/app/health-service.jar"]
            """;

        Files.writeString(
            packageDirectory.resolve("Dockerfile"),
            dockerfile,
            StandardCharsets.UTF_8
        );

        if (!dockerEnabled) {
            return "Dockerfile and image context created; image build not requested.";
        }

        runProcess(
            List.of(
                "docker",
                "build",
                "--tag",
                IMAGE_TAG,
                packageDirectory.toString()
            ),
            workspace,
            Duration.ofMinutes(10)
        );

        return "Built Docker image " + IMAGE_TAG;
    }

    private StageResult executeStage(Stage stage, StageAction action) {
        Instant started = Instant.now();
        states.put(stage, StageStatus.RUNNING);

        try {
            String detail = action.execute();
            Instant finished = Instant.now();

            states.put(stage, StageStatus.SUCCEEDED);

            StageResult result = new StageResult(
                stage,
                StageStatus.SUCCEEDED,
                started,
                finished,
                Duration.between(started, finished).toMillis(),
                detail
            );

            results.add(result);
            printResult(result);
            return result;

        } catch (Exception exception) {
            Instant finished = Instant.now();
            states.put(stage, StageStatus.FAILED);

            StageResult result = new StageResult(
                stage,
                StageStatus.FAILED,
                started,
                finished,
                Duration.between(started, finished).toMillis(),
                exception.getClass().getSimpleName() + ": " + exception.getMessage()
            );

            results.add(result);
            printResult(result);
            return result;
        }
    }

    private void markSkipped(Stage stage) {
        states.put(stage, StageStatus.SKIPPED);

        StageResult result = new StageResult(
            stage,
            StageStatus.SKIPPED,
            null,
            null,
            0,
            "A preceding required stage failed."
        );

        results.add(result);
        printResult(result);
    }

    private static void printResult(StageResult result) {
        System.out.printf(
            "[%s] %s: %s (%d ms)%n",
            result.status(),
            result.stage(),
            result.detail(),
            result.durationMillis()
        );
    }

    private void writeReport(boolean success) throws IOException {
        StringBuilder report = new StringBuilder();

        report.append("{\n")
            .append("  \"pipeline\": \"Build -> Test -> Scan -> Package -> Dockerize\",\n")
            .append("  \"status\": \"")
            .append(success ? "succeeded" : "failed")
            .append("\",\n")
            .append("  \"stages\": [\n");

        for (int index = 0; index < results.size(); index++) {
            StageResult result = results.get(index);

            report.append("    {\"name\":\"")
                .append(result.stage())
                .append("\",\"status\":\"")
                .append(result.status())
                .append("\",\"durationMillis\":")
                .append(result.durationMillis())
                .append(",\"detail\":\"")
                .append(result.detail().replace("\\", "\\\\").replace("\"", "\\\""))
                .append("\"}");

            if (index + 1 < results.size()) {
                report.append(",");
            }
            report.append("\n");
        }

        report.append("  ]\n}\n");

        Files.writeString(
            workspace.resolve("pipeline-report.json"),
            report.toString(),
            StandardCharsets.UTF_8
        );
    }

    private boolean run() throws IOException {
        List<StageAction> actions = List.of(
            this::build,
            this::test,
            this::scan,
            this::packageApplication,
            this::dockerize
        );

        Stage[] stages = Stage.values();

        for (int index = 0; index < stages.length; index++) {
            StageResult result = executeStage(stages[index], actions.get(index));

            if (result.status() == StageStatus.FAILED) {
                for (int remaining = index + 1; remaining < stages.length; remaining++) {
                    markSkipped(stages[remaining]);
                }

                writeReport(false);
                return false;
            }
        }

        writeReport(true);
        return true;
    }

    public static void main(String[] args) {
        boolean dockerEnabled = false;
        Path workspace = DEFAULT_WORKSPACE;

        try {
            for (int index = 0; index < args.length; index++) {
                switch (args[index]) {
                    case "--docker" -> dockerEnabled = true;
                    case "--workspace" -> {
                        if (index + 1 >= args.length) {
                            throw new PipelineException("--workspace requires a directory.");
                        }
                        workspace = Path.of(args[++index]);
                    }
                    default -> throw new PipelineException(
                        "Unknown command-line argument: " + args[index]
                    );
                }
            }

            ensureWorkspace(workspace);
            CiCdPipelineDemo pipeline = new CiCdPipelineDemo(
                workspace.toAbsolutePath().normalize(),
                dockerEnabled
            );

            pipeline.prepareProject();
            boolean success = pipeline.run();

            System.out.println(
                "Pipeline report: "
                + pipeline.workspace.resolve("pipeline-report.json")
            );

            if (!success) {
                System.exit(1);
            }

        } catch (Exception exception) {
            System.err.println(
                "CI/CD pipeline failed: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}

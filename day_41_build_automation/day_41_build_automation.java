import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.Callable;

/**
 * Enterprise-oriented build automation for a document-conversion service.
 *
 * Compile and run:
 *   javac BuildAutomation.java
 *   java BuildAutomation
 *   java BuildAutomation --workspace enterprise-build
 *
 * The pipeline models compilation, dependency resolution, verification,
 * artifact staging, checksums, and immutable stage outcomes.
 */
public class BuildAutomation {
    enum StageStatus {
        PENDING,
        RUNNING,
        PASSED,
        FAILED,
        SKIPPED
    }

    enum ArtifactType {
        EXECUTABLE,
        SOURCE_ARCHIVE,
        MANIFEST,
        TEST_REPORT
    }

    record BuildArtifact(
        String name,
        ArtifactType type,
        long sizeBytes,
        String sha256,
        Path location
    ) {
        BuildArtifact {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
            Objects.requireNonNull(sha256);
            Objects.requireNonNull(location);
            if (sizeBytes < 0) {
                throw new IllegalArgumentException("Artifact size cannot be negative");
            }
        }
    }

    record StageResult(
        String stage,
        StageStatus status,
        Duration duration,
        String details
    ) {
        StageResult {
            Objects.requireNonNull(stage);
            Objects.requireNonNull(status);
            Objects.requireNonNull(duration);
            Objects.requireNonNull(details);
            if (duration.isNegative()) {
                throw new IllegalArgumentException("Duration cannot be negative");
            }
        }
    }

    record ProjectDefinition(
        String name,
        String version,
        int minimumJavaFeature,
        List<String> dependencies
    ) {
        ProjectDefinition {
            if (name == null || !name.matches("[a-z][a-z0-9-]*")) {
                throw new IllegalArgumentException("Invalid project name");
            }
            if (version == null || !version.matches("\\d+\\.\\d+\\.\\d+")) {
                throw new IllegalArgumentException("Version must use MAJOR.MINOR.PATCH");
            }
            if (minimumJavaFeature < 17) {
                throw new IllegalArgumentException("This pipeline requires Java 17 or later");
            }
            dependencies = List.copyOf(dependencies);
            if (dependencies.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Dependency coordinates cannot be blank");
            }
        }
    }

    static final class PipelineException extends Exception {
        private final String stage;

        PipelineException(String stage, String message) {
            super(message);
            this.stage = stage;
        }

        PipelineException(String stage, String message, Throwable cause) {
            super(message, cause);
            this.stage = stage;
        }

        String stage() {
            return stage;
        }
    }

    static final class BuildContext {
        private final ProjectDefinition project;
        private final Path workspace;
        private final Path source;
        private final Path build;
        private final Path distribution;
        private final List<StageResult> results = new ArrayList<>();
        private final List<BuildArtifact> artifacts = new ArrayList<>();

        BuildContext(ProjectDefinition project, Path workspace) {
            this.project = project;
            this.workspace = workspace.toAbsolutePath().normalize();
            this.source = this.workspace.resolve("src");
            this.build = this.workspace.resolve("build");
            this.distribution = this.workspace.resolve("dist");
        }

        ProjectDefinition project() {
            return project;
        }

        Path workspace() {
            return workspace;
        }

        Path source() {
            return source;
        }

        Path build() {
            return build;
        }

        Path distribution() {
            return distribution;
        }

        List<StageResult> results() {
            return List.copyOf(results);
        }

        List<BuildArtifact> artifacts() {
            return List.copyOf(artifacts);
        }

        void record(StageResult result) {
            results.add(result);
        }

        void recordArtifact(BuildArtifact artifact) {
            artifacts.add(artifact);
        }
    }

    @FunctionalInterface
    interface BuildOperation {
        String execute(BuildContext context) throws Exception;
    }

    static final class BuildEngine {
        private final BuildContext context;
        private final Map<StageStatus, Integer> statusCounts =
            new EnumMap<>(StageStatus.class);

        BuildEngine(BuildContext context) {
            this.context = context;
            for (StageStatus status : StageStatus.values()) {
                statusCounts.put(status, 0);
            }
        }

        private void runStage(String name, BuildOperation operation)
                throws PipelineException {
            Instant started = Instant.now();
            try {
                String details = operation.execute(context);
                StageResult result = new StageResult(
                    name,
                    StageStatus.PASSED,
                    Duration.between(started, Instant.now()),
                    details
                );
                context.record(result);
                statusCounts.merge(StageStatus.PASSED, 1, Integer::sum);
                System.out.printf("[PASS] %s: %s%n", name, details);
            } catch (Exception error) {
                StageResult result = new StageResult(
                    name,
                    StageStatus.FAILED,
                    Duration.between(started, Instant.now()),
                    error.getMessage() == null ? error.getClass().getSimpleName()
                        : error.getMessage()
                );
                context.record(result);
                statusCounts.merge(StageStatus.FAILED, 1, Integer::sum);
                throw new PipelineException(name, result.details(), error);
            }
        }

        int execute() {
            try {
                runStage("workspace initialization", BuildEngine::initialize);
                runStage("dependency verification", BuildEngine::verifyDependencies);
                runStage("source compilation", BuildEngine::compileSources);
                runStage("quality verification", BuildEngine::verifyBuild);
                runStage("release packaging", BuildEngine::packageRelease);
                runStage("artifact integrity", BuildEngine::writeManifest);
                runStage("build reporting", BuildEngine::writeReport);
                System.out.println("Build completed successfully.");
                return 0;
            } catch (PipelineException error) {
                System.err.printf(
                    "Build stopped at '%s': %s%n",
                    error.stage(),
                    error.getMessage()
                );
                try {
                    writeFailureReport(context);
                } catch (IOException reportError) {
                    System.err.println("Unable to write failure report: "
                        + reportError.getMessage());
                }
                return 1;
            }
        }

        private static String initialize(BuildContext context) throws IOException {
            Path marker = context.workspace().resolve(".java-build-demo");
            if (Files.exists(context.workspace())) {
                if (!Files.exists(marker)) {
                    try (var entries = Files.list(context.workspace())) {
                        if (entries.findAny().isPresent()) {
                            throw new IOException(
                                "Refusing to overwrite a non-demo workspace"
                            );
                        }
                    }
                } else {
                    deleteTree(context.workspace());
                }
            }

            Files.createDirectories(context.source());
            Files.createDirectories(context.build());
            Files.createDirectories(context.distribution());
            Files.writeString(marker, "Managed by BuildAutomation.java\n");

            Path javaSource = context.source().resolve("DocumentJob.java");
            String code = """
                public class DocumentJob {
                    public static String convert(String documentId, String format) {
                        if (documentId == null || documentId.isBlank()) {
                            throw new IllegalArgumentException("Document ID is required");
                        }
                        if (format == null ||
                            !java.util.Set.of("pdf", "txt", "html").contains(format)) {
                            throw new IllegalArgumentException("Unsupported output format");
                        }
                        return documentId + "." + format;
                    }

                    public static void main(String[] args) {
                        if (args.length != 2) {
                            System.err.println("Usage: DocumentJob DOCUMENT_ID FORMAT");
                            System.exit(2);
                        }
                        try {
                            System.out.println(convert(args[0], args[1]));
                        } catch (IllegalArgumentException error) {
                            System.err.println(error.getMessage());
                            System.exit(2);
                        }
                    }
                }
                """;
            Files.writeString(javaSource, code, StandardCharsets.UTF_8);

            Files.writeString(
                context.workspace().resolve("dependencies.txt"),
                "# JDK standard library only; no external runtime dependencies\n"
            );
            Files.writeString(
                context.workspace().resolve("build.properties"),
                "project=" + context.project().name() + "\n"
                    + "version=" + context.project().version() + "\n"
                    + "minimumJava=" + context.project().minimumJavaFeature() + "\n"
            );
            return "Prepared document conversion source and build metadata";
        }

        private static String verifyDependencies(BuildContext context)
                throws IOException {
            Path dependencies = context.workspace().resolve("dependencies.txt");
            if (!Files.isRegularFile(dependencies)) {
                throw new IOException("Dependency manifest is missing");
            }
            if (!context.project().dependencies().isEmpty()) {
                throw new IOException(
                    "External dependencies require an explicitly configured resolver"
                );
            }
            if (Runtime.version().feature() < context.project().minimumJavaFeature()) {
                throw new IOException("The running JDK does not meet the project requirement");
            }
            return "Verified Java runtime and dependency manifest";
        }

        private static String compileSources(BuildContext context)
                throws IOException, InterruptedException {
            Path output = context.build().resolve("classes");
            Files.createDirectories(output);

            List<String> command = List.of(
                Path.of(System.getProperty("java.home"), "bin",
                    isWindows() ? "javac.exe" : "javac").toString(),
                "--release",
                Integer.toString(context.project().minimumJavaFeature()),
                "-Xlint:all",
                "-Werror",
                "-d",
                output.toString(),
                context.source().resolve("DocumentJob.java").toString()
            );

            Process process = new ProcessBuilder(command)
                .directory(context.workspace().toFile())
                .redirectErrorStream(true)
                .start();

            String compilerOutput = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
            );
            int exitCode = process.waitFor();

            if (!compilerOutput.isBlank()) {
                System.out.print(compilerOutput);
            }
            if (exitCode != 0) {
                throw new IOException("javac returned exit code " + exitCode);
            }

            context.recordArtifact(createArtifact(
                output.resolve("DocumentJob.class"),
                ArtifactType.EXECUTABLE
            ));
            return "Compiled DocumentJob.java using javac --release 17";
        }

        private static String verifyBuild(BuildContext context)
                throws IOException, InterruptedException {
            Path classes = context.build().resolve("classes");
            String javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin",
                isWindows() ? "java.exe" : "java"
            ).toString();

            Process valid = new ProcessBuilder(
                javaExecutable, "-cp", classes.toString(),
                "DocumentJob", "invoice-482", "pdf"
            ).redirectErrorStream(true).start();

            String output = new String(
                valid.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
            ).trim();
            if (valid.waitFor() != 0 || !output.equals("invoice-482.pdf")) {
                throw new IOException("Valid document conversion test failed: " + output);
            }

            Process invalid = new ProcessBuilder(
                javaExecutable, "-cp", classes.toString(),
                "DocumentJob", "invoice-482", "exe"
            ).redirectErrorStream(true).start();

            String errorOutput = new String(
                invalid.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
            );
            int invalidExit = invalid.waitFor();
            if (invalidExit != 2 || !errorOutput.contains("Unsupported output format")) {
                throw new IOException("Unsupported format was not rejected correctly");
            }

            Files.writeString(
                context.build().resolve("test-report.txt"),
                "PASS valid conversion: invoice-482.pdf\n"
                    + "PASS invalid format rejected with exit code 2\n"
            );
            context.recordArtifact(createArtifact(
                context.build().resolve("test-report.txt"),
                ArtifactType.TEST_REPORT
            ));
            return "Validated successful conversion and rejected executable format";
        }

        private static String packageRelease(BuildContext context) throws IOException {
            Path release = context.distribution().resolve(
                context.project().name() + "-" + context.project().version()
            );
            Files.createDirectories(release);

            copyTree(context.build().resolve("classes"), release.resolve("classes"));
            Files.copy(
                context.workspace().resolve("build.properties"),
                release.resolve("build.properties")
            );
            Files.copy(
                context.build().resolve("test-report.txt"),
                release.resolve("test-report.txt")
            );

            Path archive = context.distribution().resolve(
                context.project().name() + "-" + context.project().version() + ".zip"
            );

            try (var output = new java.util.zip.ZipOutputStream(
                    Files.newOutputStream(archive))) {
                try (var paths = Files.walk(release)) {
                    for (Path file : paths.filter(Files::isRegularFile).sorted().toList()) {
                        String entryName = release.getFileName() + "/"
                            + release.relativize(file).toString().replace('\\', '/');
                        output.putNextEntry(new java.util.zip.ZipEntry(entryName));
                        Files.copy(file, output);
                        output.closeEntry();
                    }
                }
            }

            context.recordArtifact(createArtifact(archive, ArtifactType.SOURCE_ARCHIVE));
            return "Created ZIP release containing compiled classes and test evidence";
        }

        private static String writeManifest(BuildContext context)
                throws IOException {
            Path manifest = context.distribution().resolve("SHA256SUMS.txt");
            List<String> lines = new ArrayList<>();

            try (var paths = Files.list(context.distribution())) {
                for (Path file : paths.filter(Files::isRegularFile)
                        .filter(path -> !path.equals(manifest))
                        .sorted().toList()) {
                    lines.add(sha256(file) + "  " + file.getFileName());
                }
            }

            Files.write(manifest, lines, StandardCharsets.UTF_8);
            context.recordArtifact(createArtifact(manifest, ArtifactType.MANIFEST));
            return "Generated SHA-256 hashes for distributable files";
        }

        private static String writeReport(BuildContext context) throws IOException {
            Path report = context.distribution().resolve("build-report.txt");
            List<String> lines = new ArrayList<>();
            lines.add("Project: " + context.project().name());
            lines.add("Version: " + context.project().version());
            for (StageResult result : context.results()) {
                lines.add(
                    result.stage() + " | " + result.status()
                        + " | " + result.duration().toMillis() + " ms"
                        + " | " + result.details()
                );
            }
            Files.write(report, lines, StandardCharsets.UTF_8);
            return "Recorded stage results and execution durations";
        }

        private static void writeFailureReport(BuildContext context) throws IOException {
            Files.createDirectories(context.distribution());
            List<String> lines = context.results().stream()
                .map(result -> result.stage() + " | " + result.status()
                    + " | " + result.details())
                .toList();
            Files.write(
                context.distribution().resolve("build-failure-report.txt"),
                lines,
                StandardCharsets.UTF_8
            );
        }
    }

    static BuildArtifact createArtifact(Path path, ArtifactType type)
            throws IOException {
        return new BuildArtifact(
            path.getFileName().toString(),
            type,
            Files.size(path),
            sha256(path),
            path.toAbsolutePath().normalize()
        );
    }

    static String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[8192];
                int length;
                while ((length = input.read(buffer)) != -1) {
                    digest.update(buffer, 0, length);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    static boolean isWindows() {
        return System.getProperty("os.name").toLowerCase().contains("win");
    }

    static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
                Files.delete(path);
            }
        }
    }

    static void copyTree(Path source, Path destination) throws IOException {
        try (var paths = Files.walk(source)) {
            for (Path item : paths.toList()) {
                Path target = destination.resolve(source.relativize(item));
                if (Files.isDirectory(item)) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(item, target);
                }
            }
        }
    }

    public static void main(String[] args) {
        Path workspace = Path.of("enterprise-build");
        for (int index = 0; index < args.length; index++) {
            if ("--workspace".equals(args[index]) && index + 1 < args.length) {
                workspace = Path.of(args[++index]);
            } else {
                System.err.println("Usage: java BuildAutomation [--workspace PATH]");
                System.exit(2);
            }
        }

        ProjectDefinition project = new ProjectDefinition(
            "document-converter",
            "1.0.0",
            17,
            List.of()
        );
        BuildContext context = new BuildContext(project, workspace);
        System.exit(new BuildEngine(context).execute());
    }
}

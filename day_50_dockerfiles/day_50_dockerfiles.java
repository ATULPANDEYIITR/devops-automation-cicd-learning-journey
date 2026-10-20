import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

public class DockerfileGovernance {

    enum InstructionType {
        FROM,
        RUN,
        COPY,
        CMD,
        ENTRYPOINT,
        ENV,
        WORKDIR,
        EXPOSE,
        USER
    }

    record Instruction(
            InstructionType type,
            String arguments,
            int lineNumber
    ) {
        Instruction {
            Objects.requireNonNull(type);
            Objects.requireNonNull(arguments);

            if (arguments.isBlank()) {
                throw new IllegalArgumentException(
                        "Instruction arguments cannot be empty"
                );
            }
        }
    }

    record PolicyResult(
            String policy,
            boolean passed,
            String reason
    ) {}

    static final class DockerfileParser {

        List<Instruction> parse(String source) {
            Objects.requireNonNull(source);

            List<Instruction> result = new ArrayList<>();

            StringBuilder logical = new StringBuilder();
            int startLine = 0;
            String[] lines = source.split("\\R", -1);

            for (int index = 0; index < lines.length; index++) {
                int lineNumber = index + 1;
                String line = lines[index].trim();

                if (line.isEmpty()) {
                    continue;
                }

                if (line.startsWith("#") && logical.isEmpty()) {
                    continue;
                }

                if (logical.isEmpty()) {
                    startLine = lineNumber;
                }

                if (line.endsWith("\\")) {
                    logical
                            .append(line, 0, line.length() - 1)
                            .append(' ');
                    continue;
                }

                logical.append(line);

                String[] parts = logical.toString().trim().split(
                        "\\s+",
                        2
                );

                InstructionType type;

                try {
                    type = InstructionType.valueOf(
                            parts[0].toUpperCase()
                    );
                } catch (IllegalArgumentException exception) {
                    throw new IllegalArgumentException(
                            "Unsupported instruction at line " +
                            startLine + ": " + parts[0]
                    );
                }

                if (parts.length < 2 || parts[1].isBlank()) {
                    throw new IllegalArgumentException(
                            type + " requires arguments at line " +
                            startLine
                    );
                }

                result.add(
                        new Instruction(
                                type,
                                parts[1].trim(),
                                startLine
                        )
                );

                logical.setLength(0);
                startLine = 0;
            }

            if (!logical.isEmpty()) {
                throw new IllegalArgumentException(
                        "Incomplete line continuation at line " +
                        startLine
                );
            }

            validateStructure(result);
            return List.copyOf(result);
        }

        private void validateStructure(List<Instruction> instructions) {
            if (instructions.isEmpty()) {
                throw new IllegalArgumentException(
                        "Dockerfile contains no instructions"
                );
            }

            if (instructions.get(0).type() != InstructionType.FROM) {
                throw new IllegalArgumentException(
                        "FROM must be the first effective instruction"
                );
            }

            long fromCount = instructions.stream()
                    .filter(item -> item.type() == InstructionType.FROM)
                    .count();

            if (fromCount != 1) {
                throw new IllegalArgumentException(
                        "This enterprise model requires one FROM instruction"
                );
            }
        }
    }

    static final class SecurityPolicy {

        private static final Set<String> SECRET_WORDS = Set.of(
                "password",
                "secret",
                "token",
                "private_key"
        );

        List<PolicyResult> evaluate(List<Instruction> instructions) {
            List<PolicyResult> results = new ArrayList<>();

            boolean startupDefined = instructions.stream().anyMatch(
                    item -> item.type() == InstructionType.CMD ||
                            item.type() == InstructionType.ENTRYPOINT
            );

            results.add(new PolicyResult(
                    "startup-definition",
                    startupDefined,
                    startupDefined
                            ? "Container startup behavior is defined."
                            : "CMD or ENTRYPOINT is missing."
            ));

            boolean credentialsSafe = instructions.stream()
                    .filter(item -> item.type() == InstructionType.ENV ||
                            item.type() == InstructionType.RUN)
                    .noneMatch(this::containsCredential);

            results.add(new PolicyResult(
                    "credential-storage",
                    credentialsSafe,
                    credentialsSafe
                            ? "No obvious credentials were embedded."
                            : "Credential-like data appears in ENV or RUN."
            ));

            boolean copySafe = instructions.stream()
                    .filter(item -> item.type() == InstructionType.COPY)
                    .noneMatch(
                            item -> item.arguments().contains("../")
                    );

            results.add(new PolicyResult(
                    "build-context-boundary",
                    copySafe,
                    copySafe
                            ? "COPY paths remain within the intended context."
                            : "COPY attempts to escape the build context."
            ));

            return List.copyOf(results);
        }

        private boolean containsCredential(Instruction instruction) {
            String lower = instruction.arguments().toLowerCase();

            return SECRET_WORDS.stream().anyMatch(lower::contains);
        }
    }

    static final class MergeLikePolicyEngine {

        private final SecurityPolicy securityPolicy;

        MergeLikePolicyEngine(SecurityPolicy securityPolicy) {
            this.securityPolicy = securityPolicy;
        }

        boolean approve(List<Instruction> instructions) {
            List<PolicyResult> results =
                    securityPolicy.evaluate(instructions);

            System.out.println("Governance policy results");
            System.out.println("------------------------");

            for (PolicyResult result : results) {
                System.out.printf(
                        "[%s] %s: %s%n",
                        result.passed() ? "PASS" : "FAIL",
                        result.policy(),
                        result.reason()
                );
            }

            return results.stream().allMatch(PolicyResult::passed);
        }
    }

    static final class ImagePlan {

        record Layer(
                int sequence,
                InstructionType source,
                String cacheIdentity
        ) {}

        List<Layer> create(List<Instruction> instructions) {
            List<Layer> layers = new ArrayList<>();
            int sequence = 0;

            for (Instruction instruction : instructions) {
                if (EnumSet.of(
                        InstructionType.FROM,
                        InstructionType.RUN,
                        InstructionType.COPY
                ).contains(instruction.type())) {
                    sequence++;

                    layers.add(new Layer(
                            sequence,
                            instruction.type(),
                            sequence + "|" +
                            instruction.type() + "|" +
                            instruction.arguments()
                    ));
                }
            }

            return List.copyOf(layers);
        }
    }

    public static void main(String[] args) {
        String dockerfile = """
                FROM eclipse-temurin:17-jre-alpine

                ENV APP_ENV=production APP_PORT=8080

                WORKDIR /opt/order-service

                COPY order-service.jar .

                RUN chmod 0555 order-service.jar

                ENTRYPOINT ["java", "-jar", "order-service.jar"]
                CMD ["--server.port=8080"]
                """;

        try {
            DockerfileParser parser = new DockerfileParser();
            List<Instruction> instructions = parser.parse(dockerfile);

            System.out.println("Enterprise Dockerfile model");
            System.out.println("===========================");

            instructions.forEach(instruction ->
                    System.out.printf(
                            "Line %d: %-11s %s%n",
                            instruction.lineNumber(),
                            instruction.type(),
                            instruction.arguments()
                    )
            );

            SecurityPolicy securityPolicy = new SecurityPolicy();
            MergeLikePolicyEngine governance =
                    new MergeLikePolicyEngine(securityPolicy);

            if (!governance.approve(instructions)) {
                throw new IllegalStateException(
                        "Dockerfile failed governance policy"
                );
            }

            ImagePlan plan = new ImagePlan();
            List<ImagePlan.Layer> layers = plan.create(instructions);

            System.out.println("\nImage construction plan");
            System.out.println("-----------------------");

            for (ImagePlan.Layer layer : layers) {
                System.out.printf(
                        "Layer %d: %-4s cache-identity=%s%n",
                        layer.sequence(),
                        layer.source(),
                        layer.cacheIdentity()
                );
            }

            System.out.println("\nDomain decisions");
            System.out.println("----------------");
            System.out.println(
                    "FROM defines the image construction baseline."
            );
            System.out.println(
                    "RUN represents build-time state changes."
            );
            System.out.println(
                    "COPY transfers files from the build context."
            );
            System.out.println(
                    "ENV establishes configuration visible to later stages and containers."
            );
            System.out.println(
                    "ENTRYPOINT defines the primary executable."
            );
            System.out.println(
                    "CMD supplies default startup behavior or arguments."
            );

            System.out.println("\nProduction constraints");
            System.out.println("----------------------");
            System.out.println(
                    "Credentials must not be persisted in Dockerfile instructions."
            );
            System.out.println(
                    "COPY must not expose files outside the intended build context."
            );
            System.out.println(
                    "Layer ordering affects cache reuse and rebuild cost."
            );
            System.out.println(
                    "A minimal runtime image can reduce attack surface."
            );
            System.out.println(
                    "Running as a non-root USER should be considered for production workloads."
            );

        } catch (RuntimeException exception) {
            System.err.println(
                    "Dockerfile processing failed: " +
                    exception.getMessage()
            );
            System.exit(1);
        }
    }
}

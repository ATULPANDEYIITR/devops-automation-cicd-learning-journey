#include <algorithm>
#include <cctype>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct Instruction {
    std::string keyword;
    std::string arguments;
    std::size_t line;
};

class DockerfileError : public std::runtime_error {
public:
    explicit DockerfileError(const std::string& message)
        : std::runtime_error(message) {}
};

class Dockerfile {
private:
    std::vector<Instruction> instructions_;

    static std::string trim(const std::string& value) {
        const auto first = value.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) {
            return {};
        }

        const auto last = value.find_last_not_of(" \t\r\n");
        return value.substr(first, last - first + 1);
    }

    static std::string upper(std::string value) {
        std::transform(
            value.begin(),
            value.end(),
            value.begin(),
            [](unsigned char c) {
                return static_cast<char>(std::toupper(c));
            }
        );
        return value;
    }

    static bool supported(const std::string& keyword) {
        static const std::set<std::string> allowed{
            "FROM", "RUN", "COPY", "CMD", "ENTRYPOINT",
            "ENV", "WORKDIR", "EXPOSE", "USER"
        };

        return allowed.contains(keyword);
    }

public:
    void parse(const std::string& source) {
        instructions_.clear();

        std::istringstream input(source);
        std::string physical;
        std::string logical;
        std::size_t startLine = 0;
        std::size_t lineNumber = 0;

        while (std::getline(input, physical)) {
            ++lineNumber;

            std::string line = trim(physical);

            if (line.empty()) {
                continue;
            }

            if (line[0] == '#' && logical.empty()) {
                continue;
            }

            if (logical.empty()) {
                startLine = lineNumber;
            }

            if (!line.empty() && line.back() == '\\') {
                line.pop_back();
                logical += trim(line) + " ";
                continue;
            }

            logical += line;

            std::istringstream parser(logical);
            std::string keyword;

            if (!(parser >> keyword)) {
                logical.clear();
                continue;
            }

            keyword = upper(keyword);

            std::string arguments;
            std::getline(parser, arguments);
            arguments = trim(arguments);

            if (!supported(keyword)) {
                throw DockerfileError(
                    "Line " + std::to_string(startLine) +
                    ": unsupported instruction " + keyword
                );
            }

            if (arguments.empty()) {
                throw DockerfileError(
                    "Line " + std::to_string(startLine) +
                    ": " + keyword + " requires arguments"
                );
            }

            instructions_.push_back(
                {keyword, arguments, startLine}
            );

            logical.clear();
            startLine = 0;
        }

        if (!logical.empty()) {
            throw DockerfileError(
                "Line " + std::to_string(startLine) +
                ": incomplete continuation"
            );
        }

        validate();
    }

    void validate() const {
        if (instructions_.empty()) {
            throw DockerfileError("Dockerfile is empty");
        }

        if (instructions_.front().keyword != "FROM") {
            throw DockerfileError("FROM must be the first effective instruction");
        }

        const auto fromCount = std::count_if(
            instructions_.begin(),
            instructions_.end(),
            [](const Instruction& item) {
                return item.keyword == "FROM";
            }
        );

        if (fromCount != 1) {
            throw DockerfileError(
                "This engine expects exactly one FROM instruction"
            );
        }

        for (const auto& item : instructions_) {
            if (item.keyword == "ENV") {
                const std::string lower = [&item] {
                    std::string result = item.arguments;
                    std::transform(
                        result.begin(),
                        result.end(),
                        result.begin(),
                        [](unsigned char c) {
                            return static_cast<char>(std::tolower(c));
                        }
                    );
                    return result;
                }();

                if (lower.find("password") != std::string::npos ||
                    lower.find("secret") != std::string::npos ||
                    lower.find("token") != std::string::npos) {
                    throw DockerfileError(
                        "Line " + std::to_string(item.line) +
                        ": credentials must not be stored in ENV"
                    );
                }
            }

            if (item.keyword == "COPY" &&
                item.arguments.find("../") != std::string::npos) {
                throw DockerfileError(
                    "Line " + std::to_string(item.line) +
                    ": COPY cannot escape the build context"
                );
            }
        }
    }

    const std::vector<Instruction>& instructions() const {
        return instructions_;
    }
};

struct BuildLayer {
    std::size_t number;
    std::string operation;
    std::string cacheKey;
};

class BuildPlanner {
private:
    std::vector<BuildLayer> layers_;

    static std::string makeKey(
        const Instruction& instruction,
        std::size_t previousLayer
    ) {
        return std::to_string(previousLayer) + "|" +
               instruction.keyword + "|" +
               instruction.arguments;
    }

public:
    void createPlan(const Dockerfile& dockerfile) {
        layers_.clear();

        std::size_t layerNumber = 0;
        for (const auto& instruction : dockerfile.instructions()) {
            const bool createsLayer =
                instruction.keyword == "FROM" ||
                instruction.keyword == "RUN" ||
                instruction.keyword == "COPY";

            if (!createsLayer) {
                continue;
            }

            ++layerNumber;

            layers_.push_back({
                layerNumber,
                instruction.keyword,
                makeKey(instruction, layerNumber - 1)
            });
        }
    }

    void print() const {
        std::cout << "\nBuild layer plan\n";
        std::cout << "----------------\n";

        for (const auto& layer : layers_) {
            std::cout
                << "Layer " << layer.number
                << ": " << layer.operation
                << " | cache-key=" << layer.cacheKey
                << '\n';
        }

        std::cout << "\nThe cache key depends on the previous layer and "
                     "the instruction text in this simplified model.\n";
    }
};

class StartupPolicy {
public:
    static void evaluate(const Dockerfile& dockerfile) {
        bool hasCmd = false;
        bool hasEntrypoint = false;

        for (const auto& instruction : dockerfile.instructions()) {
            hasCmd |= instruction.keyword == "CMD";
            hasEntrypoint |= instruction.keyword == "ENTRYPOINT";
        }

        if (!hasCmd && !hasEntrypoint) {
            throw DockerfileError(
                "Image has no CMD or ENTRYPOINT startup configuration"
            );
        }

        std::cout << "\nStartup policy\n";
        std::cout << "--------------\n";

        if (hasEntrypoint && hasCmd) {
            std::cout
                << "ENTRYPOINT supplies the executable and CMD supplies "
                   "default arguments.\n";
        } else if (hasEntrypoint) {
            std::cout
                << "ENTRYPOINT supplies the primary executable without "
                   "a default CMD argument list.\n";
        } else {
            std::cout
                << "CMD supplies the default startup command.\n";
        }
    }
};

int main() {
    const std::string source = R"(# Production-oriented example
FROM nginx:stable-alpine

ENV NGINX_PORT=8080

WORKDIR /usr/share/nginx/html

COPY index.html .

RUN chmod 0644 index.html

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
)";

    try {
        Dockerfile dockerfile;
        dockerfile.parse(source);

        std::cout << "Dockerfile instruction model\n";
        std::cout << "============================\n";

        for (const auto& instruction : dockerfile.instructions()) {
            std::cout
                << "Line " << instruction.line
                << ": " << instruction.keyword
                << " " << instruction.arguments
                << '\n';
        }

        StartupPolicy::evaluate(dockerfile);

        BuildPlanner planner;
        planner.createPlan(dockerfile);
        planner.print();

        std::cout << "\nInstruction semantics\n";
        std::cout << "---------------------\n";
        std::cout << "FROM: selects the image used as the build starting point.\n";
        std::cout << "RUN: executes build-time commands and can create filesystem layers.\n";
        std::cout << "COPY: copies build-context content into the image.\n";
        std::cout << "ENV: records environment configuration for later build/runtime use.\n";
        std::cout << "ENTRYPOINT: establishes the primary container executable.\n";
        std::cout << "CMD: supplies default command or default arguments.\n";

        std::cout << "\nEngineering constraints\n";
        std::cout << "-----------------------\n";
        std::cout << "Build context must not expose files outside its intended boundary.\n";
        std::cout << "Credentials should not be persisted through ENV or RUN commands.\n";
        std::cout << "COPY and RUN ordering affects cache reuse and rebuild cost.\n";
        std::cout << "Smaller base images reduce attack surface and transfer size.\n";
        std::cout << "A non-root USER is preferable when the application permits it.\n";

        return 0;
    } catch (const DockerfileError& error) {
        std::cerr << "Dockerfile validation failed: "
                  << error.what() << '\n';
        return 1;
    } catch (const std::exception& error) {
        std::cerr << "Unexpected failure: "
                  << error.what() << '\n';
        return 2;
    }
}

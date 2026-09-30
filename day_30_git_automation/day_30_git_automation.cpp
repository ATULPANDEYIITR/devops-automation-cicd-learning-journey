#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

/*
 * Case study:
 *
 * A financial-services engineering repository receives changes from several
 * developers. Before a commit can become part of the shared branch, local
 * automation checks staged content, validates the commit subject, scans for
 * accidental credentials, runs deterministic tests, and records an audit.
 *
 * The program models a governance engine rather than merely showing C++ syntax.
 * It deliberately separates:
 *
 *   Git hook trigger
 *       -> validation pipeline
 *       -> individual checks
 *       -> pass/fail decision
 *       -> audit record
 *
 * The same checks can be invoked by a local hook or a CI job. This separation
 * is important because a local hook is controlled by the developer, whereas a
 * CI system can enforce the policy on the shared repository.
 */

struct CheckResult {
    std::string name;
    bool passed;
    std::string message;
    std::vector<std::string> details;
};

struct RepositoryPolicy {
    std::string protectedBranch = "main";
    std::size_t maxTextFileBytes = 512 * 1024;
    bool requireTests = true;
    bool requireSecretScan = true;
    bool requireWhitespaceCheck = true;
    bool requireCommitMessage = true;
};

struct CommitContext {
    std::string branch;
    std::string message;
    std::vector<fs::path> stagedFiles;
};

struct AuditEntry {
    std::string event;
    std::string check;
    bool passed;
    std::string message;
};

class RepositoryGovernanceEngine {
public:
    explicit RepositoryGovernanceEngine(fs::path repository)
        : repository_(std::move(repository)) {}

    CheckResult validateCommitMessage(const std::string& message) const {
        const std::string subject = firstLine(message);

        if (subject.empty()) {
            return fail(
                "commit-message",
                "Commit subject is empty."
            );
        }

        if (subject.size() > 100) {
            return fail(
                "commit-message",
                "Commit subject exceeds 100 characters."
            );
        }

        /*
         * A regex makes the repository's message grammar explicit. The policy
         * allows a conventional type, an optional scope, an optional breaking
         * marker, and a descriptive subject.
         */
        static const std::regex pattern(
            R"(^(feat|fix|docs|refactor|test|build|ci|chore|perf|style|revert)(\([a-z0-9._/-]+\))?!?: .{1,100}$)"
        );

        if (!std::regex_match(subject, pattern)) {
            return CheckResult{
                "commit-message",
                false,
                "Commit subject does not match repository policy.",
                {"Expected form: fix(api): reject malformed requests"}
            };
        }

        return CheckResult{
            "commit-message",
            true,
            "Commit subject matches repository policy.",
            {}
        };
    }

    CheckResult validatePaths(
        const std::vector<fs::path>& stagedFiles
    ) const {
        std::vector<std::string> violations;

        for (const auto& file : stagedFiles) {
            const std::string value = file.generic_string();

            if (file.is_absolute()) {
                violations.push_back(value + ": absolute path");
            }

            for (const auto& part : file) {
                const std::string component = part.string();

                if (
                    component == ".git" ||
                    component == "node_modules" ||
                    component == "__pycache__"
                ) {
                    violations.push_back(
                        value + ": generated/dependency path"
                    );
                }
            }
        }

        if (!violations.empty()) {
            return CheckResult{
                "staged-path-policy",
                false,
                "Staged paths violate repository policy.",
                violations
            };
        }

        return CheckResult{
            "staged-path-policy",
            true,
            "Staged paths satisfy repository policy.",
            {}
        };
    }

    CheckResult validateFileSizes(
        const std::vector<fs::path>& stagedFiles
    ) const {
        std::vector<std::string> violations;

        for (const auto& relative : stagedFiles) {
            const fs::path absolute = repository_ / relative;

            std::error_code error;
            if (!fs::exists(absolute, error) || error) {
                continue;
            }

            if (!fs::is_regular_file(absolute, error) || error) {
                continue;
            }

            const auto size = fs::file_size(absolute, error);
            if (!error && size > policy_.maxTextFileBytes) {
                violations.push_back(
                    relative.generic_string() +
                    ": file exceeds configured size limit"
                );
            }
        }

        if (!violations.empty()) {
            return CheckResult{
                "file-size-policy",
                false,
                "At least one staged file is too large.",
                violations
            };
        }

        return CheckResult{
            "file-size-policy",
            true,
            "Staged files satisfy the size policy.",
            {}
        };
    }

    CheckResult scanSecrets(
        const std::vector<fs::path>& stagedFiles
    ) const {
        /*
         * This is intentionally a small demonstration scanner. Regex-based
         * detection reduces accidental credential commits but cannot prove
         * that a repository contains no secrets. Production scanning normally
         * combines entropy analysis, provider-specific patterns, allowlists,
         * and server-side controls.
         */
        static const std::vector<std::regex> secretPatterns = {
            std::regex(R"(\bghp_[A-Za-z0-9]{20,})"),
            std::regex(R"(\bgithub_pat_[A-Za-z0-9_]{20,})"),
            std::regex(
                R"((?i)(api[_-]?key|secret[_-]?key)\s*[:=]\s*["'][^"']{8,})"
            ),
            std::regex(
                R"((?i)aws(.{0,20})(access[_-]?key|secret)[^\n]{0,80})"
            )
        };

        std::vector<std::string> findings;

        for (const auto& relative : stagedFiles) {
            if (!isTextExtension(relative.extension().string())) {
                continue;
            }

            const fs::path absolute = repository_ / relative;
            std::ifstream input(absolute);

            if (!input) {
                continue;
            }

            std::stringstream buffer;
            buffer << input.rdbuf();
            const std::string content = buffer.str();

            for (const auto& pattern : secretPatterns) {
                if (std::regex_search(content, pattern)) {
                    findings.push_back(
                        "Potential credential detected in " +
                        relative.generic_string()
                    );
                    break;
                }
            }
        }

        if (!findings.empty()) {
            return CheckResult{
                "secret-scan",
                false,
                "Potential secret material was detected.",
                findings
            };
        }

        return CheckResult{
            "secret-scan",
            true,
            "Configured secret patterns were not detected.",
            {}
        };
    }

    CheckResult checkWhitespace(
        const std::vector<fs::path>& stagedFiles
    ) const {
        std::vector<std::string> findings;

        for (const auto& relative : stagedFiles) {
            if (!isTextExtension(relative.extension().string())) {
                continue;
            }

            std::ifstream input(repository_ / relative);
            if (!input) {
                continue;
            }

            std::string line;
            std::size_t lineNumber = 0;

            while (std::getline(input, line)) {
                ++lineNumber;

                if (!line.empty() &&
                    (line.back() == ' ' || line.back() == '\t')) {
                    findings.push_back(
                        relative.generic_string() +
                        ":" +
                        std::to_string(lineNumber)
                    );
                }
            }
        }

        if (!findings.empty()) {
            return CheckResult{
                "whitespace",
                false,
                "Trailing whitespace was detected.",
                findings
            };
        }

        return CheckResult{
            "whitespace",
            true,
            "No trailing whitespace was detected.",
            {}
        };
    }

    CheckResult runDomainTests() const {
        /*
         * The domain under test is a repository automation policy itself.
         * These tests exercise boundary behavior rather than testing generic
         * C++ syntax.
         */
        const auto valid =
            validateCommitMessage("fix(api): reject invalid request");
        const auto invalid =
            validateCommitMessage("changed stuff");
        const auto empty =
            validateCommitMessage("");

        if (!valid.passed || invalid.passed || empty.passed) {
            return CheckResult{
                "domain-tests",
                false,
                "Commit-policy boundary tests failed.",
                {}
            };
        }

        return CheckResult{
            "domain-tests",
            true,
            "Commit-policy boundary tests passed.",
            {
                "valid conventional subject accepted",
                "unstructured subject rejected",
                "empty subject rejected"
            }
        };
    }

    std::vector<CheckResult> runPreCommit(
        const CommitContext& context
    ) const {
        std::vector<CheckResult> results;

        if (policy_.requireCommitMessage) {
            results.push_back(
                validateCommitMessage(context.message)
            );
        }

        results.push_back(
            validatePaths(context.stagedFiles)
        );

        results.push_back(
            validateFileSizes(context.stagedFiles)
        );

        if (policy_.requireSecretScan) {
            results.push_back(
                scanSecrets(context.stagedFiles)
            );
        }

        if (policy_.requireWhitespaceCheck) {
            results.push_back(
                checkWhitespace(context.stagedFiles)
            );
        }

        if (policy_.requireTests) {
            results.push_back(runDomainTests());
        }

        return results;
    }

    std::vector<AuditEntry> convertToAudit(
        const std::string& event,
        const std::vector<CheckResult>& results
    ) const {
        std::vector<AuditEntry> entries;

        for (const auto& result : results) {
            entries.push_back({
                event,
                result.name,
                result.passed,
                result.message
            });
        }

        return entries;
    }

    const RepositoryPolicy& policy() const {
        return policy_;
    }

private:
    fs::path repository_;
    RepositoryPolicy policy_;

    static std::string firstLine(const std::string& message) {
        const auto position = message.find_first_of("\r\n");
        return message.substr(
            0,
            position == std::string::npos
                ? message.size()
                : position
        );
    }

    static CheckResult fail(
        const std::string& name,
        const std::string& message
    ) {
        return CheckResult{name, false, message, {}};
    }

    static bool isTextExtension(const std::string& extension) {
        static const std::vector<std::string> extensions = {
            ".py", ".js", ".ts", ".cpp", ".h", ".hpp",
            ".md", ".txt", ".json", ".yaml", ".yml",
            ".toml", ".ini"
        };

        return std::find(
            extensions.begin(),
            extensions.end(),
            extension
        ) != extensions.end();
    }
};

class HookSimulator {
public:
    using HookHandler =
        std::function<std::vector<CheckResult>(const CommitContext&)>;

    void registerHook(
        const std::string& hookName,
        HookHandler handler
    ) {
        hooks_[hookName] = std::move(handler);
    }

    std::vector<CheckResult> trigger(
        const std::string& hookName,
        const CommitContext& context
    ) const {
        const auto found = hooks_.find(hookName);

        if (found == hooks_.end()) {
            throw std::runtime_error(
                "No handler registered for hook: " + hookName
            );
        }

        return found->second(context);
    }

private:
    std::map<std::string, HookHandler> hooks_;
};

void printResults(
    const std::string& title,
    const std::vector<CheckResult>& results
) {
    std::cout << "\n=== " << title << " ===\n";

    bool passed = true;

    for (const auto& result : results) {
        std::cout
            << "[" << (result.passed ? "PASS" : "FAIL") << "] "
            << result.name
            << ": "
            << result.message
            << "\n";

        for (const auto& detail : result.details) {
            std::cout << "    " << detail << "\n";
        }

        passed = passed && result.passed;
    }

    std::cout
        << "Pipeline result: "
        << (passed ? "PASS" : "FAIL")
        << "\n";
}

void printAudit(
    const std::vector<AuditEntry>& entries
) {
    std::cout << "\n=== Automation Audit ===\n";

    for (const auto& entry : entries) {
        std::cout
            << entry.event
            << " | "
            << entry.check
            << " | "
            << (entry.passed ? "PASS" : "FAIL")
            << " | "
            << entry.message
            << "\n";
    }
}

fs::path createRepositoryFixture() {
    const auto timestamp =
        std::chrono::steady_clock::now().time_since_epoch().count();

    const fs::path repository =
        fs::temp_directory_path() /
        ("cpp-git-automation-" + std::to_string(timestamp));

    fs::create_directories(repository / "src");
    fs::create_directories(repository / "tests");

    std::ofstream calculator(repository / "src" / "risk_engine.cpp");
    calculator
        << "#include <stdexcept>\n"
        << "\n"
        << "double validateRiskLimit(double limit) {\n"
        << "    if (limit < 0.0 || limit > 1.0) {\n"
        << "        throw std::invalid_argument(\"risk limit out of range\");\n"
        << "    }\n"
        << "    return limit;\n"
        << "}\n";

    std::ofstream readme(repository / "README.md");
    readme
        << "# Repository Automation Fixture\n"
        << "\n"
        << "Fixture for staged-content validation.\n";

    return repository;
}

void demonstrateCommitMessageGate(
    RepositoryGovernanceEngine& engine
) {
    const CommitContext invalid{
        "feature/risk-validation",
        "updated some files",
        {"src/risk_engine.cpp"}
    };

    const auto rejected =
        engine.validateCommitMessage(invalid.message);

    printResults(
        "Commit Message Rejection",
        {rejected}
    );

    const CommitContext valid{
        "feature/risk-validation",
        "fix(risk): reject invalid exposure limits",
        {"src/risk_engine.cpp"}
    };

    const auto accepted =
        engine.validateCommitMessage(valid.message);

    printResults(
        "Commit Message Acceptance",
        {accepted}
    );
}

void demonstratePreCommitFailure(
    RepositoryGovernanceEngine& engine,
    const fs::path& repository
) {
    /*
     * The failure is introduced into a staged-file fixture. The check is
     * intentionally focused on the index contents that would enter the
     * commit, rather than scanning arbitrary files elsewhere on disk.
     */
    const fs::path readme = repository / "README.md";

    std::ofstream broken(readme, std::ios::app);
    broken << "Policy text with trailing whitespace   \n";
    broken.close();

    const CommitContext context{
        "feature/risk-validation",
        "fix(risk): reject invalid exposure limits",
        {"README.md", "src/risk_engine.cpp"}
    };

    auto results = engine.runPreCommit(context);
    printResults(
        "Pre-Commit Failure Scenario",
        results
    );
}

void demonstrateSuccessfulPipeline(
    RepositoryGovernanceEngine& engine
) {
    const CommitContext context{
        "feature/risk-validation",
        "fix(risk): reject invalid exposure limits",
        {"src/risk_engine.cpp"}
    };

    const auto results = engine.runPreCommit(context);
    printResults(
        "Successful Pre-Commit Pipeline",
        results
    );
}

void demonstrateHookArchitecture(
    RepositoryGovernanceEngine& engine
) {
    HookSimulator hooks;

    /*
     * pre-commit handles staged content and tests.
     * commit-msg handles the message itself.
     *
     * Keeping these responsibilities distinct means a message-format failure
     * does not need to know anything about source-file scanning.
     */
    hooks.registerHook(
        "pre-commit",
        [&engine](const CommitContext& context) {
            return engine.runPreCommit(context);
        }
    );

    hooks.registerHook(
        "commit-msg",
        [&engine](const CommitContext& context) {
            return {
                engine.validateCommitMessage(context.message)
            };
        }
    );

    const CommitContext context{
        "feature/risk-validation",
        "fix(risk): reject invalid exposure limits",
        {"src/risk_engine.cpp"}
    };

    const auto messageResults =
        hooks.trigger("commit-msg", context);

    printResults(
        "commit-msg Hook",
        messageResults
    );

    const auto preCommitResults =
        hooks.trigger("pre-commit", context);

    printResults(
        "pre-commit Hook",
        preCommitResults
    );
}

void explainProductionBoundary(
    const RepositoryGovernanceEngine& engine
) {
    std::cout
        << "\n=== Production Boundary ===\n"
        << "Protected branch: "
        << engine.policy().protectedBranch
        << "\n"
        << "Local hooks provide immediate feedback but are not an enforcement "
           "boundary.\n"
        << "CI should repeat required checks after a push.\n"
        << "Server-side repository rules should enforce checks that must apply "
           "to every contributor.\n"
        << "Secret detection should not be treated as proof that credentials "
           "are absent.\n";
}

int main() {
    fs::path repository;

    try {
        repository = createRepositoryFixture();

        RepositoryGovernanceEngine engine(repository);

        std::cout
            << "Git Automation Governance Engine\n"
            << "Repository fixture: "
            << repository
            << "\n";

        demonstrateCommitMessageGate(engine);
        demonstratePreCommitFailure(engine);
        demonstrateSuccessfulPipeline(engine);
        demonstrateHookArchitecture(engine);
        explainProductionBoundary(engine);

        const CommitContext ciContext{
            "main",
            "fix(risk): reject invalid exposure limits",
            {"src/risk_engine.cpp"}
        };

        const auto ciResults =
            engine.runPreCommit(ciContext);

        std::vector<AuditEntry> audit =
            engine.convertToAudit("ci", ciResults);

        printAudit(audit);

        const bool ciPassed =
            std::all_of(
                ciResults.begin(),
                ciResults.end(),
                [](const CheckResult& result) {
                    return result.passed;
                }
            );

        std::cout
            << "\nIndependent CI policy decision: "
            << (ciPassed ? "PASS" : "FAIL")
            << "\n";

        fs::remove_all(repository);
        std::cout << "Temporary fixture removed.\n";
        return ciPassed ? 0 : 1;
    } catch (const std::exception& error) {
        if (!repository.empty()) {
            std::error_code cleanupError;
            fs::remove_all(repository, cleanupError);
        }

        std::cerr
            << "Automation engine error: "
            << error.what()
            << "\n";

        return 1;
    }
}

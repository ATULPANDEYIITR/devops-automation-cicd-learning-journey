#include <algorithm>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Actions Variables Governance Engine
 *
 * Technical case study:
 * A platform engineering team needs a deterministic local policy engine for
 * CI/CD configuration. Before a deployment job is allowed to execute, the
 * engine evaluates:
 *
 *   - workflow/job/step environment scopes,
 *   - configuration variables,
 *   - GitHub metadata,
 *   - matrix dimensions,
 *   - step outputs,
 *   - job outputs consumed through needs,
 *   - boolean expressions,
 *   - deployment environment policy,
 *   - security constraints around sensitive values.
 *
 * This is not a complete GitHub Actions runner. It is a C++17 model that
 * focuses on the data relationships and decision logic behind Actions
 * variables, contexts, and expressions.
 */

namespace actions {

using StringMap = std::map<std::string, std::string>;

struct GithubContext {
    std::string repository;
    std::string ref;
    std::string refName;
    std::string eventName;
    std::string sha;
    std::string actor;
};

struct RunnerContext {
    std::string operatingSystem;
    std::string architecture;
};

struct MatrixContext {
    StringMap values;
};

struct StepOutput {
    StringMap values;
};

struct StepState {
    std::string id;
    std::string name;
    std::string outcome;
    std::string conclusion;
    StepOutput outputs;
};

struct JobState {
    std::string result;
    StringMap outputs;
};

struct NeedsContext {
    std::map<std::string, JobState> jobs;
};

struct VariableScopes {
    StringMap workflowEnvironment;
    StringMap jobEnvironment;
    StringMap stepEnvironment;
    StringMap configurationVariables;
    StringMap runnerEnvironment;

    /*
     * Environment precedence is intentionally explicit.
     *
     * A more specific scope overwrites a less specific scope:
     * runner < workflow < job < step.
     *
     * Configuration variables are not merged here because vars.NAME is an
     * Actions context lookup rather than an ordinary process environment
     * lookup.
     */
    StringMap effectiveEnvironment() const {
        StringMap result = runnerEnvironment;

        for (const auto& [key, value] : workflowEnvironment) {
            result[key] = value;
        }

        for (const auto& [key, value] : jobEnvironment) {
            result[key] = value;
        }

        for (const auto& [key, value] : stepEnvironment) {
            result[key] = value;
        }

        return result;
    }
};

class ExpressionError : public std::runtime_error {
public:
    explicit ExpressionError(const std::string& message)
        : std::runtime_error(message) {}
};


static std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");

    if (first == std::string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}


static std::vector<std::string> splitArguments(const std::string& text) {
    std::vector<std::string> result;
    std::size_t start = 0;
    int depth = 0;
    char quote = '\0';

    for (std::size_t i = 0; i < text.size(); ++i) {
        const char c = text[i];

        if (quote != '\0') {
            if (c == quote && (i == 0 || text[i - 1] != '\\')) {
                quote = '\0';
            }

            continue;
        }

        if (c == '\'' || c == '"') {
            quote = c;
        } else if (c == '(') {
            ++depth;
        } else if (c == ')') {
            --depth;
        } else if (c == ',' && depth == 0) {
            result.push_back(trim(text.substr(start, i - start)));
            start = i + 1;
        }
    }

    const std::string finalArgument = trim(text.substr(start));

    if (!finalArgument.empty()) {
        result.push_back(finalArgument);
    }

    return result;
}


static std::optional<std::size_t> findTopLevelOperator(
    const std::string& expression,
    const std::string& operatorText
) {
    int depth = 0;
    char quote = '\0';

    for (std::size_t i = 0;
         i + operatorText.size() <= expression.size();
         ++i) {

        const char c = expression[i];

        if (quote != '\0') {
            if (c == quote && (i == 0 || expression[i - 1] != '\\')) {
                quote = '\0';
            }

            continue;
        }

        if (c == '\'' || c == '"') {
            quote = c;
        } else if (c == '(') {
            ++depth;
        } else if (c == ')') {
            --depth;
        } else if (
            depth == 0 &&
            expression.compare(i, operatorText.size(), operatorText) == 0
        ) {
            return i;
        }
    }

    return std::nullopt;
}


class ContextStore {
private:
    GithubContext github_;
    RunnerContext runner_;
    MatrixContext matrix_;
    NeedsContext needs_;
    StringMap vars_;
    StringMap env_;
    std::map<std::string, StepState> steps_;

public:
    ContextStore(
        GithubContext github,
        RunnerContext runner,
        StringMap vars,
        StringMap env
    )
        : github_(std::move(github)),
          runner_(std::move(runner)),
          vars_(std::move(vars)),
          env_(std::move(env)) {}

    void setMatrix(MatrixContext matrix) {
        matrix_ = std::move(matrix);
    }

    void setNeeds(NeedsContext needs) {
        needs_ = std::move(needs);
    }

    void setStep(StepState state) {
        steps_[state.id] = std::move(state);
    }

    const StringMap& vars() const {
        return vars_;
    }

    const StringMap& env() const {
        return env_;
    }

    const GithubContext& github() const {
        return github_;
    }

    const RunnerContext& runner() const {
        return runner_;
    }

    const MatrixContext& matrix() const {
        return matrix_;
    }

    const NeedsContext& needs() const {
        return needs_;
    }

    const std::map<std::string, StepState>& steps() const {
        return steps_;
    }
};


static std::string lookupMapValue(
    const StringMap& values,
    const std::string& key,
    const std::string& contextName
) {
    const auto iterator = values.find(key);

    if (iterator == values.end()) {
        throw ExpressionError(
            "Missing value '" + contextName + "." + key + "'."
        );
    }

    return iterator->second;
}


static std::string lookupContextValue(
    const ContextStore& contexts,
    const std::string& reference
) {
    const auto dot = reference.find('.');

    if (dot == std::string::npos) {
        throw ExpressionError(
            "A context object cannot be converted to a scalar: " + reference
        );
    }

    const std::string context = reference.substr(0, dot);
    const std::string path = reference.substr(dot + 1);

    if (context == "vars") {
        return lookupMapValue(contexts.vars(), path, "vars");
    }

    if (context == "env") {
        return lookupMapValue(contexts.env(), path, "env");
    }

    if (context == "github") {
        if (path == "repository") return contexts.github().repository;
        if (path == "ref") return contexts.github().ref;
        if (path == "ref_name") return contexts.github().refName;
        if (path == "event_name") return contexts.github().eventName;
        if (path == "sha") return contexts.github().sha;
        if (path == "actor") return contexts.github().actor;

        throw ExpressionError(
            "Unknown github context property: " + path
        );
    }

    if (context == "runner") {
        if (path == "os") return contexts.runner().operatingSystem;
        if (path == "arch") return contexts.runner().architecture;

        throw ExpressionError(
            "Unknown runner context property: " + path
        );
    }

    if (context == "matrix") {
        return lookupMapValue(contexts.matrix().values, path, "matrix");
    }

    if (context == "needs") {
        const auto separator = path.find('.');

        if (separator == std::string::npos) {
            throw ExpressionError("Invalid needs reference: " + path);
        }

        const std::string jobId = path.substr(0, separator);
        const std::string property = path.substr(separator + 1);

        const auto jobIterator = contexts.needs().jobs.find(jobId);

        if (jobIterator == contexts.needs().jobs.end()) {
            throw ExpressionError("Unknown needs job: " + jobId);
        }

        if (property == "result") {
            return jobIterator->second.result;
        }

        if (property.rfind("outputs.", 0) == 0) {
            const std::string outputName = property.substr(8);

            return lookupMapValue(
                jobIterator->second.outputs,
                outputName,
                "needs." + jobId + ".outputs"
            );
        }

        throw ExpressionError(
            "Unknown needs property: " + property
        );
    }

    if (context == "steps") {
        const auto firstDot = path.find('.');

        if (firstDot == std::string::npos) {
            throw ExpressionError("Invalid steps reference: " + path);
        }

        const std::string stepId = path.substr(0, firstDot);
        const std::string remainder = path.substr(firstDot + 1);

        const auto iterator = contexts.steps().find(stepId);

        if (iterator == contexts.steps().end()) {
            throw ExpressionError("Unknown step: " + stepId);
        }

        if (remainder == "outcome") {
            return iterator->second.outcome;
        }

        if (remainder == "conclusion") {
            return iterator->second.conclusion;
        }

        if (remainder.rfind("outputs.", 0) == 0) {
            const std::string outputName = remainder.substr(8);

            return lookupMapValue(
                iterator->second.outputs.values,
                outputName,
                "steps." + stepId + ".outputs"
            );
        }

        throw ExpressionError(
            "Unknown steps property: " + remainder
        );
    }

    throw ExpressionError("Unknown context: " + context);
}


static std::string evaluateExpression(
    const std::string& expression,
    const ContextStore& contexts
) {
    const std::string source = trim(expression);

    if (source.empty()) {
        return "";
    }

    /*
     * Logical operators are evaluated outside quoted strings and nested
     * function calls. This avoids accidentally splitting a format string.
     */
    for (const std::string& logical : {"||", "&&"}) {
        if (const auto position =
                findTopLevelOperator(source, logical)) {

            const std::string left = evaluateExpression(
                source.substr(0, *position),
                contexts
            );

            const bool leftTruthy =
                !left.empty() &&
                left != "false" &&
                left != "0";

            if (logical == "&&") {
                return leftTruthy
                    ? evaluateExpression(
                        source.substr(*position + logical.size()),
                        contexts
                    )
                    : left;
            }

            return leftTruthy
                ? left
                : evaluateExpression(
                    source.substr(*position + logical.size()),
                    contexts
                );
        }
    }

    for (const std::string comparison : {"==", "!="}) {
        if (const auto position =
                findTopLevelOperator(source, comparison)) {

            const std::string left = trim(
                source.substr(0, *position)
            );

            const std::string right = trim(
                source.substr(
                    *position + comparison.size()
                )
            );

            const std::string leftValue =
                evaluateExpression(left, contexts);

            const std::string rightValue =
                evaluateExpression(right, contexts);

            const bool equal = leftValue == rightValue;

            return comparison == "==" 
                ? (equal ? "true" : "false")
                : (equal ? "false" : "true");
        }
    }

    if (source.front() == '!' && source.size() > 1) {
        const std::string value =
            evaluateExpression(source.substr(1), contexts);

        const bool truthy =
            !value.empty() &&
            value != "false" &&
            value != "0";

        return truthy ? "false" : "true";
    }

    if (
        (source.front() == '\'' && source.back() == '\'') ||
        (source.front() == '"' && source.back() == '"')
    ) {
        return source.substr(1, source.size() - 2);
    }

    if (source == "true" || source == "false") {
        return source;
    }

    /*
     * Function parsing is deliberately explicit instead of using eval-like
     * behavior. Arbitrary code cannot be executed through an expression.
     */
    const std::regex functionPattern(
        R"(^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$)"
    );

    std::smatch functionMatch;

    if (std::regex_match(source, functionMatch, functionPattern)) {
        const std::string functionName = functionMatch[1].str();
        const auto arguments =
            splitArguments(functionMatch[2].str());

        std::vector<std::string> evaluatedArguments;

        for (const auto& argument : arguments) {
            evaluatedArguments.push_back(
                evaluateExpression(argument, contexts)
            );
        }

        if (
            functionName == "startsWith" ||
            functionName == "endsWith" ||
            functionName == "contains"
        ) {
            if (evaluatedArguments.size() != 2) {
                throw ExpressionError(
                    functionName + " requires two arguments."
                );
            }

            const std::string& sourceValue =
                evaluatedArguments[0];

            const std::string& searchValue =
                evaluatedArguments[1];

            if (functionName == "startsWith") {
                return sourceValue.rfind(searchValue, 0) == 0
                    ? "true"
                    : "false";
            }

            if (functionName == "endsWith") {
                if (searchValue.size() > sourceValue.size()) {
                    return "false";
                }

                return sourceValue.compare(
                    sourceValue.size() - searchValue.size(),
                    searchValue.size(),
                    searchValue
                ) == 0
                    ? "true"
                    : "false";
            }

            return sourceValue.find(searchValue) != std::string::npos
                ? "true"
                : "false";
        }

        if (functionName == "format") {
            if (evaluatedArguments.empty()) {
                throw ExpressionError(
                    "format requires a template."
                );
            }

            std::string result = evaluatedArguments[0];

            for (std::size_t i = 1;
                 i < evaluatedArguments.size();
                 ++i) {

                const std::string token =
                    "{" + std::to_string(i - 1) + "}";

                std::size_t position = 0;

                while (
                    (position = result.find(token, position))
                    != std::string::npos
                ) {
                    result.replace(
                        position,
                        token.size(),
                        evaluatedArguments[i]
                    );

                    position += evaluatedArguments[i].size();
                }
            }

            return result;
        }

        throw ExpressionError(
            "Unsupported expression function: " + functionName
        );
    }

    /*
     * Plain numeric strings are treated as scalar values so that comparisons
     * such as vars.RETRY_LIMIT == '3' remain deterministic.
     */
    if (
        std::regex_match(
            source,
            std::regex(R"(^-?[0-9]+(\.[0-9]+)?$)")
        )
    ) {
        return source;
    }

    return lookupContextValue(contexts, source);
}


static std::string interpolate(
    const std::string& input,
    const ContextStore& contexts
) {
    std::string result;
    std::size_t position = 0;

    while (position < input.size()) {
        const auto start = input.find("${{", position);

        if (start == std::string::npos) {
            result += input.substr(position);
            break;
        }

        result += input.substr(position, start - position);

        const auto end = input.find("}}", start + 3);

        if (end == std::string::npos) {
            throw ExpressionError(
                "Unclosed Actions expression."
            );
        }

        const std::string expression =
            trim(input.substr(start + 3, end - start - 3));

        result += evaluateExpression(
            expression,
            contexts
        );

        position = end + 2;
    }

    return result;
}


class GovernanceEngine {
private:
    VariableScopes scopes_;
    ContextStore contexts_;

public:
    GovernanceEngine(
        VariableScopes scopes,
        GithubContext github,
        RunnerContext runner
    )
        : scopes_(std::move(scopes)),
          contexts_(
              github,
              runner,
              scopes_.configurationVariables,
              scopes_.effectiveEnvironment()
          ) {}

    ContextStore& contexts() {
        return contexts_;
    }

    const StringMap& effectiveEnvironment() const {
        return scopes_.effectiveEnvironment();
    }

    bool evaluateCondition(
        const std::string& expression
    ) const {
        const std::string value =
            evaluateExpression(expression, contexts_);

        return value == "true" ||
               (!value.empty() && value != "false" && value != "0");
    }

    std::string resolve(
        const std::string& value
    ) const {
        return interpolate(value, contexts_);
    }

    void recordStep(
        StepState step
    ) {
        contexts_.setStep(std::move(step));
    }

    void printEnvironment() const {
        std::cout << "Effective process environment\n";

        for (const auto& [key, value] :
             effectiveEnvironment()) {
            std::cout
                << "  "
                << key
                << "="
                << value
                << '\n';
        }
    }
};


static void printHeader(const std::string& title) {
    std::cout << "\n=== " << title << " ===\n";
}


static void runEnvironmentCaseStudy() {
    printHeader("Environment scope resolution");

    VariableScopes scopes;

    scopes.workflowEnvironment = {
        {"DEPLOY_REGION", "global"},
        {"LOG_LEVEL", "info"},
        {"SERVICE_NAME", "payments-api"}
    };

    scopes.jobEnvironment = {
        {"LOG_LEVEL", "debug"},
        {"DEPLOY_REGION", "ap-south-1"}
    };

    scopes.stepEnvironment = {
        {"LOG_LEVEL", "trace"}
    };

    scopes.configurationVariables = {
        {"DEPLOYMENT_TIER", "production"},
        {"ARTIFACT_PREFIX", "payments"}
    };

    scopes.runnerEnvironment = {
        {"RUNNER_OS", "Linux"},
        {"CI", "true"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "f019ac8e",
            "release-bot"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    engine.printEnvironment();

    std::cout
        << "vars.DEPLOYMENT_TIER = "
        << engine.resolve("${{ vars.DEPLOYMENT_TIER }}")
        << '\n';

    std::cout
        << "env.LOG_LEVEL = "
        << engine.resolve("${{ env.LOG_LEVEL }}")
        << '\n';
}


static void runMatrixCaseStudy() {
    printHeader("Matrix test planning");

    VariableScopes scopes;

    scopes.workflowEnvironment = {
        {"CI", "true"}
    };

    scopes.configurationVariables = {
        {"SERVICE", "payments-api"}
    };

    scopes.runnerEnvironment = {
        {"RUNNER_OS", "Linux"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "5a8e21",
            "developer"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    const std::vector<MatrixContext> matrixValues = {
        {{{"compiler", "gcc"}, {"database", "postgres"}}},
        {{{"compiler", "clang"}, {"database", "postgres"}}},
        {{{"compiler", "gcc"}, {"database", "sqlite"}}}
    };

    for (const auto& matrix : matrixValues) {
        engine.contexts().setMatrix(matrix);

        const std::string label = engine.resolve(
            "test-${{ matrix.compiler }}-${{ matrix.database }}"
        );

        std::cout << label << '\n';
    }
}


static void runStepOutputCaseStudy() {
    printHeader("Step output propagation");

    VariableScopes scopes;

    scopes.configurationVariables = {
        {"SERVICE", "payments-api"}
    };

    scopes.runnerEnvironment = {
        {"RUNNER_OS", "Linux"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "a8f3d7",
            "developer"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    StepState build{
        "build",
        "Build release artifact",
        "success",
        "success",
        StepOutput{
            {
                {"version", "2026.10.04"},
                {"artifact", "payments-api-2026.10.04.tar.gz"}
            }
        }
    };

    engine.recordStep(build);

    std::cout
        << "Artifact produced by build step: "
        << engine.resolve(
            "${{ steps.build.outputs.artifact }}"
        )
        << '\n';

    std::cout
        << "Version produced by build step: "
        << engine.resolve(
            "${{ steps.build.outputs.version }}"
        )
        << '\n';
}


static void runNeedsCaseStudy() {
    printHeader("Job-to-job data flow through needs");

    VariableScopes scopes;

    scopes.configurationVariables = {
        {"DEPLOY_ENVIRONMENT", "production"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "9a12ef",
            "release-bot"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    NeedsContext needs;

    needs.jobs["build"] = JobState{
        "success",
        {
            {"image", "registry.example.com/payments-api:2026.10.04"},
            {"version", "2026.10.04"}
        }
    };

    engine.contexts().setNeeds(needs);

    std::cout
        << "Required build result: "
        << engine.resolve(
            "${{ needs.build.result }}"
        )
        << '\n';

    std::cout
        << "Deployment image: "
        << engine.resolve(
            "${{ needs.build.outputs.image }}"
        )
        << '\n';
}


static void runDeploymentPolicyCaseStudy() {
    printHeader("Deployment expression policy");

    VariableScopes scopes;

    scopes.workflowEnvironment = {
        {"CI", "true"}
    };

    scopes.configurationVariables = {
        {"DEPLOY_ENVIRONMENT", "production"},
        {"SERVICE", "payments-api"}
    };

    scopes.runnerEnvironment = {
        {"RUNNER_OS", "Linux"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "3be91f",
            "release-bot"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    const std::string policy =
        "github.ref_name == 'main' && "
        "vars.DEPLOY_ENVIRONMENT == 'production'";

    std::cout
        << "Policy expression: "
        << policy
        << '\n';

    std::cout
        << "Deployment permitted: "
        << std::boolalpha
        << engine.evaluateCondition(policy)
        << '\n';

    /*
     * This models an important distinction: configuration data is consumed
     * through vars, while process-specific settings can be placed in env.
     * The expression decides whether a deployment is allowed; it does not
     * itself execute the deployment command.
     */
}


static std::vector<std::string> validateEnvironment(
    const StringMap& values
) {
    std::vector<std::string> errors;

    const std::regex validName(
        R"(^[A-Z][A-Z0-9_]*$)"
    );

    for (const auto& [name, value] : values) {
        if (!std::regex_match(name, validName)) {
            errors.push_back(
                "Invalid environment variable name: " + name
            );
        }

        if (value.find('\0') != std::string::npos) {
            errors.push_back(
                "NUL byte detected in variable: " + name
            );
        }

        if (
            value.find('\n') != std::string::npos ||
            value.find('\r') != std::string::npos
        ) {
            errors.push_back(
                "Line break detected in variable: " + name
            );
        }
    }

    return errors;
}


static void runValidationCaseStudy() {
    printHeader("Environment validation");

    const StringMap values = {
        {"API_BASE_URL", "https://api.example.com"},
        {"RETRY_LIMIT", "3"},
        {"bad-name", "invalid"}
    };

    const auto errors = validateEnvironment(values);

    if (errors.empty()) {
        std::cout << "Environment configuration is valid.\n";
        return;
    }

    for (const auto& error : errors) {
        std::cout << "Validation error: " << error << '\n';
    }
}


static std::string maskSecrets(
    std::string value,
    const StringMap& secrets
) {
    for (const auto& [name, secret] : secrets) {
        (void)name;

        if (secret.empty()) {
            continue;
        }

        std::size_t position = 0;

        while (
            (position = value.find(secret, position))
            != std::string::npos
        ) {
            value.replace(
                position,
                secret.size(),
                "***"
            );

            position += 3;
        }
    }

    return value;
}


static void runSecurityCaseStudy() {
    printHeader("Sensitive value handling");

    const StringMap secrets = {
        {"DEPLOY_TOKEN", "ghs_example_token_123"},
        {"DATABASE_PASSWORD", "correct-example-password"}
    };

    const std::string logLine =
        "deploy token=ghs_example_token_123 "
        "target=production";

    std::cout
        << maskSecrets(logLine, secrets)
        << '\n';

    /*
     * Masking is a defensive logging measure, not a replacement for correct
     * secret handling. Sensitive values should not be exposed through command
     * arguments, generated artifacts, cache keys, or diagnostic output.
     */
}


static void runFailureCaseStudy() {
    printHeader("Failure conditions");

    VariableScopes scopes;

    scopes.configurationVariables = {
        {"KNOWN", "value"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "example/repository",
            "refs/heads/main",
            "main",
            "push",
            "abc",
            "developer"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    try {
        std::cout
            << engine.resolve(
                "${{ vars.MISSING }}"
            )
            << '\n';
    } catch (const ExpressionError& error) {
        std::cout
            << "Expected expression failure: "
            << error.what()
            << '\n';
    }

    try {
        std::cout
            << engine.resolve(
                "${{ github.unknown }}"
            )
            << '\n';
    } catch (const ExpressionError& error) {
        std::cout
            << "Expected context failure: "
            << error.what()
            << '\n';
    }
}


static void runCompleteReleaseScenario() {
    printHeader("Complete release governance scenario");

    VariableScopes scopes;

    scopes.workflowEnvironment = {
        {"CI", "true"},
        {"LOG_LEVEL", "info"}
    };

    scopes.jobEnvironment = {
        {"DEPLOY_REGION", "ap-south-1"},
        {"SERVICE_MODE", "release"}
    };

    scopes.configurationVariables = {
        {"SERVICE", "payments-api"},
        {"DEPLOY_ENVIRONMENT", "production"},
        {"REGISTRY", "registry.example.com"}
    };

    scopes.runnerEnvironment = {
        {"RUNNER_OS", "Linux"},
        {"RUNNER_ARCH", "x64"}
    };

    GovernanceEngine engine(
        scopes,
        GithubContext{
            "ATULPANDEYIITR/payments-api",
            "refs/heads/main",
            "main",
            "push",
            "f9a81d23",
            "release-bot"
        },
        RunnerContext{
            "Linux",
            "x64"
        }
    );

    StepState build{
        "build",
        "Compile and package",
        "success",
        "success",
        StepOutput{
            {
                {"version", "2026.10.04"},
                {"artifact", "payments-api-2026.10.04.tar.gz"}
            }
        }
    };

    engine.recordStep(build);

    const std::string policy =
        "github.ref_name == 'main' && "
        "vars.DEPLOY_ENVIRONMENT == 'production'";

    const bool permitted =
        engine.evaluateCondition(policy);

    std::cout
        << "Release artifact: "
        << engine.resolve(
            "${{ steps.build.outputs.artifact }}"
        )
        << '\n';

    std::cout
        << "Target environment: "
        << engine.resolve(
            "${{ vars.DEPLOY_ENVIRONMENT }}"
        )
        << '\n';

    std::cout
        << "Target region: "
        << engine.resolve(
            "${{ env.DEPLOY_REGION }}"
        )
        << '\n';

    std::cout
        << "Deployment policy result: "
        << std::boolalpha
        << permitted
        << '\n';

    if (permitted) {
        std::cout
            << "Decision: deployment command may proceed.\n";
    } else {
        std::cout
            << "Decision: deployment command must be blocked.\n";
    }
}

} // namespace actions


int main() {
    try {
        std::cout
            << "Actions Variables Governance Engine\n"
            << "Environment variables | Contexts | Expressions\n";

        actions::runEnvironmentCaseStudy();
        actions::runMatrixCaseStudy();
        actions::runStepOutputCaseStudy();
        actions::runNeedsCaseStudy();
        actions::runDeploymentPolicyCaseStudy();
        actions::runValidationCaseStudy();
        actions::runSecurityCaseStudy();
        actions::runFailureCaseStudy();
        actions::runCompleteReleaseScenario();

        std::cout
            << "\n=== Case study completed ===\n";
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}

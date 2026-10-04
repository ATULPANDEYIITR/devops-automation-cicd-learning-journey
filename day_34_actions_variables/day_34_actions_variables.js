"use strict";

/*
 * Actions Variables Laboratory
 *
 * Topic:
 * Environment variables, contexts, and expressions in GitHub Actions.
 *
 * This Node.js program deliberately models the boundaries between:
 * - process environment variables,
 * - workflow/job/step environment scopes,
 * - configuration variables accessed through the vars context,
 * - GitHub metadata accessed through github,
 * - matrix values,
 * - step outputs,
 * - needs/job outputs,
 * - expression evaluation before a command starts.
 *
 * It is a local model rather than a complete GitHub Actions runner.
 */

const { execFileSync } = require("node:child_process");
const process = require("node:process");


class ExpressionError extends Error {}


function getNested(object, path) {
    let current = object;

    for (const part of path.split(".")) {
        if (
            current === null ||
            current === undefined ||
            typeof current !== "object" ||
            !Object.prototype.hasOwnProperty.call(current, part)
        ) {
            throw new ExpressionError(`Context value '${path}' is unavailable.`);
        }

        current = current[part];
    }

    return current;
}


function splitArguments(text) {
    const argumentsList = [];
    let start = 0;
    let depth = 0;
    let quote = null;

    for (let i = 0; i < text.length; i += 1) {
        const character = text[i];

        if (quote !== null) {
            if (character === quote && text[i - 1] !== "\\") {
                quote = null;
            }
            continue;
        }

        if (character === "'" || character === '"') {
            quote = character;
        } else if (character === "(") {
            depth += 1;
        } else if (character === ")") {
            depth -= 1;
        } else if (character === "," && depth === 0) {
            argumentsList.push(text.slice(start, i).trim());
            start = i + 1;
        }
    }

    argumentsList.push(text.slice(start).trim());
    return argumentsList.filter(Boolean);
}


function evaluateExpression(expression, contexts) {
    const source = expression.trim();

    if (source === "") {
        return "";
    }

    if (
        source.startsWith("(") &&
        source.endsWith(")") &&
        isBalancedOuterParentheses(source)
    ) {
        return evaluateExpression(source.slice(1, -1), contexts);
    }

    const logicalOperator = findTopLevelLogicalOperator(source);

    if (logicalOperator) {
        const left = evaluateExpression(
            source.slice(0, logicalOperator.index),
            contexts,
        );

        if (logicalOperator.operator === "&&") {
            return left
                ? evaluateExpression(
                    source.slice(logicalOperator.index + 2),
                    contexts,
                )
                : left;
        }

        return left
            ? left
            : evaluateExpression(
                source.slice(logicalOperator.index + 2),
                contexts,
            );
    }

    for (const operator of ["==", "!="]) {
        const index = findTopLevelOperator(source, operator);

        if (index !== -1) {
            const left = evaluateExpression(source.slice(0, index), contexts);
            const right = evaluateExpression(
                source.slice(index + operator.length),
                contexts,
            );

            return operator === "==" ? left === right : left !== right;
        }
    }

    if (source.startsWith("!")) {
        return !Boolean(evaluateExpression(source.slice(1), contexts));
    }

    const functionMatch = source.match(
        /^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$/s,
    );

    if (functionMatch) {
        const functionName = functionMatch[1];
        const argumentsList = splitArguments(functionMatch[2]).map(
            (argument) => evaluateExpression(argument, contexts),
        );

        switch (functionName) {
            case "startsWith":
                requireArgumentCount(functionName, argumentsList, 2);
                return String(argumentsList[0]).startsWith(
                    String(argumentsList[1]),
                );

            case "endsWith":
                requireArgumentCount(functionName, argumentsList, 2);
                return String(argumentsList[0]).endsWith(
                    String(argumentsList[1]),
                );

            case "contains":
                requireArgumentCount(functionName, argumentsList, 2);
                return String(argumentsList[0]).includes(
                    String(argumentsList[1]),
                );

            case "format": {
                if (argumentsList.length === 0) {
                    throw new ExpressionError(
                        "format requires a template argument.",
                    );
                }

                let result = String(argumentsList[0]);

                argumentsList.slice(1).forEach((value, index) => {
                    result = result.replaceAll(
                        `{${index}}`,
                        String(value),
                    );
                });

                return result;
            }

            case "success":
            case "failure":
            case "cancelled":
            case "always":
                requireArgumentCount(functionName, argumentsList, 0);
                return Boolean(
                    contexts._status?.[functionName] ?? false,
                );

            default:
                throw new ExpressionError(
                    `Unsupported expression function '${functionName}'.`,
                );
        }
    }

    if (
        (source.startsWith("'") && source.endsWith("'")) ||
        (source.startsWith('"') && source.endsWith('"'))
    ) {
        return source.slice(1, -1);
    }

    if (source === "true") {
        return true;
    }

    if (source === "false") {
        return false;
    }

    if (source === "null") {
        return null;
    }

    if (/^-?\d+$/.test(source)) {
        return Number.parseInt(source, 10);
    }

    if (/^-?\d+\.\d+$/.test(source)) {
        return Number.parseFloat(source);
    }

    const contextMatch = source.match(
        /^(github|env|vars|matrix|needs|steps|runner|job|secrets)(?:\.([A-Za-z_][A-Za-z0-9_.-]*))?$/,
    );

    if (!contextMatch) {
        throw new ExpressionError(`Cannot evaluate expression '${source}'.`);
    }

    const contextName = contextMatch[1];
    const path = contextMatch[2];

    if (!Object.prototype.hasOwnProperty.call(contexts, contextName)) {
        throw new ExpressionError(
            `Context '${contextName}' is unavailable.`,
        );
    }

    return path
        ? getNested(contexts[contextName], path)
        : contexts[contextName];
}


function isBalancedOuterParentheses(source) {
    let depth = 0;
    let quote = null;

    for (let i = 0; i < source.length; i += 1) {
        const character = source[i];

        if (quote !== null) {
            if (character === quote && source[i - 1] !== "\\") {
                quote = null;
            }
            continue;
        }

        if (character === "'" || character === '"') {
            quote = character;
        } else if (character === "(") {
            depth += 1;
        } else if (character === ")") {
            depth -= 1;

            if (depth === 0 && i !== source.length - 1) {
                return false;
            }
        }
    }

    return depth === 0 && quote === null;
}


function findTopLevelLogicalOperator(source) {
    let depth = 0;
    let quote = null;

    for (let i = source.length - 1; i >= 0; i -= 1) {
        const character = source[i];

        if (quote !== null) {
            if (character === quote && source[i - 1] !== "\\") {
                quote = null;
            }
            continue;
        }

        if (character === "'" || character === '"') {
            quote = character;
        } else if (character === ")") {
            depth += 1;
        } else if (character === "(") {
            depth -= 1;
        } else if (depth === 0) {
            const pair = source.slice(i, i + 2);

            if (pair === "&&" || pair === "||") {
                return { index: i, operator: pair };
            }
        }
    }

    return null;
}


function findTopLevelOperator(source, operator) {
    let depth = 0;
    let quote = null;

    for (let i = 0; i <= source.length - operator.length; i += 1) {
        const character = source[i];

        if (quote !== null) {
            if (character === quote && source[i - 1] !== "\\") {
                quote = null;
            }
            continue;
        }

        if (character === "'" || character === '"') {
            quote = character;
        } else if (character === "(") {
            depth += 1;
        } else if (character === ")") {
            depth -= 1;
        } else if (
            depth === 0 &&
            source.slice(i, i + operator.length) === operator
        ) {
            return i;
        }
    }

    return -1;
}


function requireArgumentCount(name, argumentsList, expected) {
    if (argumentsList.length !== expected) {
        throw new ExpressionError(
            `${name} requires ${expected} argument(s).`,
        );
    }
}


function interpolate(value, contexts) {
    if (typeof value !== "string") {
        return value;
    }

    const complete = value.match(/^\$\{\{\s*(.*?)\s*\}\}$/s);

    if (complete) {
        return evaluateExpression(complete[1], contexts);
    }

    return value.replace(
        /\$\{\{\s*(.*?)\s*\}\}/gs,
        (_, expression) => {
            const result = evaluateExpression(expression, contexts);
            return result === null || result === undefined
                ? ""
                : String(result);
        },
    );
}


// ---------------------------------------------------------------------------
// Variable scope model
// ---------------------------------------------------------------------------

class EnvironmentScopes {
    constructor({
        workflow = {},
        job = {},
        step = {},
        vars = {},
        runner = {},
    } = {}) {
        this.workflow = { ...workflow };
        this.job = { ...job };
        this.step = { ...step };
        this.vars = { ...vars };
        this.runner = { ...runner };
    }

    effectiveEnvironment() {
        return {
            ...this.runner,
            ...this.workflow,
            ...this.job,
            ...this.step,
        };
    }
}


// ---------------------------------------------------------------------------
// Event-driven workflow model
// ---------------------------------------------------------------------------

class ActionsWorkflow {
    constructor(configuration) {
        this.scopes = new EnvironmentScopes({
            workflow: configuration.workflowEnv,
            vars: configuration.vars,
            runner: {
                CI: "true",
                RUNNER_OS: configuration.runnerOS,
            },
        });

        this.github = configuration.github;
        this.steps = new Map();
        this.jobs = new Map();

        this.events = new Map();
    }

    on(eventName, listener) {
        if (!this.events.has(eventName)) {
            this.events.set(eventName, []);
        }

        this.events.get(eventName).push(listener);
    }

    emit(eventName, payload) {
        for (const listener of this.events.get(eventName) ?? []) {
            listener(payload);
        }
    }

    createContexts({
        jobEnv = {},
        stepEnv = {},
        matrix = {},
        needs = {},
        jobStatus = "success",
    } = {}) {
        const scopes = new EnvironmentScopes({
            workflow: this.scopes.workflow,
            job: jobEnv,
            step: stepEnv,
            vars: this.scopes.vars,
            runner: this.scopes.runner,
        });

        return {
            github: this.github,
            vars: this.scopes.vars,
            env: scopes.effectiveEnvironment(),
            matrix,
            needs,
            steps: Object.fromEntries(
                [...this.steps.entries()].map(([id, step]) => [
                    id,
                    {
                        outcome: step.outcome,
                        conclusion: step.conclusion,
                        outputs: step.outputs,
                    },
                ]),
            ),
            runner: this.scopes.runner,
            job: {
                status: jobStatus,
            },
            secrets: {},
            _status: {
                success: jobStatus === "success",
                failure: jobStatus === "failure",
                cancelled: jobStatus === "cancelled",
                always: true,
            },
        };
    }

    runStep({
        id,
        name,
        run,
        jobEnv = {},
        stepEnv = {},
        ifExpression = null,
        matrix = {},
    }) {
        let contexts = this.createContexts({
            jobEnv,
            stepEnv,
            matrix,
        });

        if (ifExpression !== null) {
            const condition = evaluateExpression(
                ifExpression,
                contexts,
            );

            if (!condition) {
                const skipped = {
                    id,
                    name,
                    outcome: "skipped",
                    conclusion: "skipped",
                    outputs: {},
                };

                this.steps.set(id, skipped);
                this.emit("step.skipped", skipped);
                return skipped;
            }
        }

        const resolvedStepEnvironment = Object.fromEntries(
            Object.entries(stepEnv).map(([key, value]) => [
                key,
                String(interpolate(value, contexts)),
            ]),
        );

        contexts = this.createContexts({
            jobEnv,
            stepEnv: resolvedStepEnvironment,
            matrix,
        });

        const resolvedCommand = interpolate(run, contexts);

        const processEnvironment = {
            ...process.env,
            ...contexts.env,
            ...resolvedStepEnvironment,
        };

        /*
         * The shell receives the effective environment only when the process
         * starts. Expressions are resolved first; shell variables such as
         * $DEPLOY_ENVIRONMENT are then interpreted by the child shell.
         */
        let stdout = "";
        let stderr = "";
        let outcome = "success";

        try {
            stdout = execFileSync(
                process.platform === "win32" ? "cmd.exe" : "sh",
                process.platform === "win32"
                    ? ["/d", "/s", "/c", resolvedCommand]
                    : ["-c", resolvedCommand],
                {
                    env: processEnvironment,
                    encoding: "utf8",
                    stdio: ["ignore", "pipe", "pipe"],
                },
            );
        } catch (error) {
            outcome = "failure";
            stdout = error.stdout?.toString() ?? "";
            stderr = error.stderr?.toString() ?? error.message;
        }

        const result = {
            id,
            name,
            outcome,
            conclusion: outcome,
            outputs: {},
            command: resolvedCommand,
            stdout,
            stderr,
        };

        this.steps.set(id, result);

        this.emit("step.completed", result);

        return result;
    }

    setStepOutput(stepId, name, value) {
        const step = this.steps.get(stepId);

        if (!step) {
            throw new ExpressionError(
                `Cannot write output for unknown step '${stepId}'.`,
            );
        }

        step.outputs[name] = String(value);
    }

    registerJobResult(jobId, result, outputs = {}) {
        this.jobs.set(jobId, {
            result,
            outputs,
        });

        this.emit("job.completed", {
            jobId,
            result,
            outputs,
        });
    }

    getNeedsContext() {
        return Object.fromEntries(
            [...this.jobs.entries()].map(([jobId, job]) => [
                jobId,
                {
                    result: job.result,
                    outputs: job.outputs,
                },
            ]),
        );
    }
}


// ---------------------------------------------------------------------------
// Practical demonstrations
// ---------------------------------------------------------------------------

function demonstrateEnvironmentPrecedence() {
    console.log("\n=== Environment precedence ===");

    const scopes = new EnvironmentScopes({
        workflow: {
            DEPLOY_REGION: "global",
            LOG_LEVEL: "info",
        },
        job: {
            LOG_LEVEL: "debug",
            JOB_NAME: "release",
        },
        step: {
            LOG_LEVEL: "trace",
        },
    });

    console.log(
        "Effective environment:",
        scopes.effectiveEnvironment(),
    );
}


function demonstrateContexts() {
    console.log("\n=== Contexts and expressions ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {
            CI: "true",
        },
        vars: {
            SERVICE_NAME: "orders-api",
            DEPLOY_ENVIRONMENT: "production",
        },
        runnerOS: "Linux",
        github: {
            repository: "example/orders-api",
            ref: "refs/heads/main",
            ref_name: "main",
            event_name: "push",
            sha: "a84f19e7",
        },
    });

    const contexts = workflow.createContexts({
        jobEnv: {
            REGION: "ap-south-1",
        },
    });

    const values = [
        "${{ vars.SERVICE_NAME }}",
        "${{ github.ref_name }}",
        "${{ env.REGION }}",
        "${{ github.ref_name == 'main' }}",
        "${{ startsWith(github.ref, 'refs/heads/') }}",
        "${{ format('{0}-{1}', vars.SERVICE_NAME, github.ref_name) }}",
    ];

    for (const value of values) {
        console.log(value, "=>", interpolate(value, contexts));
    }
}


function demonstrateMatrixExecution() {
    console.log("\n=== Matrix-specific context ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {
            CI: "true",
        },
        vars: {
            TEST_COMMAND: "npm test",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "main",
            event_name: "push",
        },
    });

    const matrix = [
        { node: "20", database: "postgres" },
        { node: "22", database: "postgres" },
        { node: "22", database: "sqlite" },
    ];

    for (const combination of matrix) {
        const contexts = workflow.createContexts({
            matrix: combination,
        });

        const label = interpolate(
            "node-${{ matrix.node }}-${{ matrix.database }}",
            contexts,
        );

        console.log(label);
    }
}


function demonstrateStepOutputs() {
    console.log("\n=== Step outputs ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {},
        vars: {
            ARTIFACT_PREFIX: "orders-api",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "main",
        },
    });

    const build = workflow.runStep({
        id: "build",
        name: "Build artifact",
        run: "printf 'build-started\\n'",
    });

    workflow.setStepOutput(
        build.id,
        "artifact",
        "orders-api-2026.10.04.tar.gz",
    );

    const contexts = workflow.createContexts();

    console.log(
        "Artifact output:",
        interpolate(
            "${{ steps.build.outputs.artifact }}",
            contexts,
        ),
    );
}


function demonstrateNeedsContext() {
    console.log("\n=== needs context ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {},
        vars: {
            DEPLOY_ENVIRONMENT: "production",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "main",
        },
    });

    workflow.registerJobResult(
        "build",
        "success",
        {
            image: "registry.example.com/orders-api:2026.10.04",
            version: "2026.10.04",
        },
    );

    const contexts = workflow.createContexts({
        needs: workflow.getNeedsContext(),
    });

    console.log(
        "Build result:",
        interpolate("${{ needs.build.result }}", contexts),
    );

    console.log(
        "Image:",
        interpolate("${{ needs.build.outputs.image }}", contexts),
    );
}


function demonstrateConditionalWorkflow() {
    console.log("\n=== Conditional workflow execution ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {
            CI: "true",
        },
        vars: {
            DEPLOY_ENVIRONMENT: "production",
        },
        runnerOS: "Linux",
        github: {
            ref: "refs/heads/main",
            ref_name: "main",
            event_name: "push",
        },
    });

    const result = workflow.runStep({
        id: "deploy",
        name: "Deploy production",
        ifExpression:
            "github.ref_name == 'main' && vars.DEPLOY_ENVIRONMENT == 'production'",
        run: "printf 'production deployment permitted\\n'",
    });

    console.log("Deployment outcome:", result.outcome);
}


function demonstrateEventDrivenBehavior() {
    console.log("\n=== Event-driven step processing ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {
            CI: "true",
        },
        vars: {
            SERVICE: "billing-api",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "feature/observability",
            event_name: "pull_request",
        },
    });

    workflow.on("step.completed", (result) => {
        console.log(
            `Event received: step '${result.id}' completed with ${result.outcome}.`,
        );
    });

    workflow.on("step.skipped", (result) => {
        console.log(
            `Event received: step '${result.id}' was skipped.`,
        );
    });

    workflow.runStep({
        id: "inspect",
        name: "Inspect pull request",
        ifExpression: "github.event_name == 'pull_request'",
        run: "printf 'review environment active\\n'",
    });
}


function demonstrateSecurityBoundary() {
    console.log("\n=== Security boundary ===");

    const secrets = {
        DEPLOY_TOKEN: "ghs_example_token_12345",
        DATABASE_PASSWORD: "strong-example-password",
    };

    const unsafeLog =
        `deploy token=${secrets.DEPLOY_TOKEN} environment=production`;

    let safeLog = unsafeLog;

    for (const value of Object.values(secrets)) {
        if (value.length > 0) {
            safeLog = safeLog.split(value).join("***");
        }
    }

    console.log(safeLog);
    console.log(
        "Secrets should not be placed in command-line arguments, generated artifacts,",
        "or diagnostic output when an environment-based mechanism is sufficient.",
    );
}


function demonstrateValidation() {
    console.log("\n=== Environment validation ===");

    const values = {
        API_BASE_URL: "https://api.example.com",
        RETRY_LIMIT: "3",
        "bad-name": "invalid",
        SAFE_VALUE: "normal",
    };

    const namePattern = /^[A-Z][A-Z0-9_]*$/;

    for (const [name, value] of Object.entries(values)) {
        if (!namePattern.test(name)) {
            console.log(
                `Invalid environment variable name: ${name}`,
            );
        }

        if (value.includes("\0")) {
            console.log(
                `NUL byte detected in variable: ${name}`,
            );
        }

        if (value.includes("\n") || value.includes("\r")) {
            console.log(
                `Line break detected in variable: ${name}`,
            );
        }
    }
}


function demonstrateFailureModes() {
    console.log("\n=== Expression failure modes ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {},
        vars: {
            KNOWN: "value",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "main",
        },
    });

    const contexts = workflow.createContexts();

    const expressions = [
        "${{ vars.MISSING }}",
        "${{ github.unknown }}",
        "${{ unsupported(value) }}",
        "${{ startsWith(github.ref_name) }}",
    ];

    for (const expression of expressions) {
        try {
            console.log(
                expression,
                "=>",
                interpolate(expression, contexts),
            );
        } catch (error) {
            console.log(
                expression,
                "=> ERROR:",
                error.message,
            );
        }
    }
}


function demonstrateExpressionAndShellBoundary() {
    console.log("\n=== Expression stage versus shell stage ===");

    const workflow = new ActionsWorkflow({
        workflowEnv: {
            REGION: "ap-south-1",
        },
        vars: {
            SERVICE: "orders-api",
        },
        runnerOS: "Linux",
        github: {
            ref_name: "main",
        },
    });

    const result = workflow.runStep({
        id: "boundary",
        name: "Show evaluation boundary",
        jobEnv: {
            DEPLOY_ENVIRONMENT: "staging",
        },
        run:
            "printf 'service=${{ vars.SERVICE }} branch=${{ github.ref_name }} env=%s\\n' \"$DEPLOY_ENVIRONMENT\"",
    });

    console.log("Command:", result.command);
    console.log("Output:", result.stdout.trim());
}


function main() {
    console.log(
        "Actions Variables Laboratory: Environment variables, contexts, expressions",
    );

    demonstrateEnvironmentPrecedence();
    demonstrateContexts();
    demonstrateMatrixExecution();
    demonstrateStepOutputs();
    demonstrateNeedsContext();
    demonstrateConditionalWorkflow();
    demonstrateEventDrivenBehavior();
    demonstrateSecurityBoundary();
    demonstrateValidation();
    demonstrateFailureModes();
    demonstrateExpressionAndShellBoundary();

    console.log("\n=== Completed ===");
}


main();

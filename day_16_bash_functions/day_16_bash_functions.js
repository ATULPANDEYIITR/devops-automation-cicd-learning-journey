#!/usr/bin/env node
"use strict";

/*
 * Bash Functions: JavaScript companion
 *
 * This file complements a Bash study by demonstrating the same engineering
 * concepts in JavaScript:
 *
 * - functions and parameters
 * - rest parameters
 * - return values versus process exit codes
 * - validation
 * - command dispatch
 * - asynchronous operations
 * - error handling
 * - reusable modules
 * - subprocess execution
 * - argument parsing
 * - retries
 * - cleanup
 * - security-aware process execution
 * - testing
 *
 * Run with:
 *   node bash-functions-companion.js
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFile, spawn } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);


// ---------------------------------------------------------------------------
// 1. Basic functions
// ---------------------------------------------------------------------------

function greet(name) {
    return `Hello, ${name}`;
}

function demonstrateBasicFunction() {
    console.log("\n=== 1. Basic function ===");
    console.log(greet("Atul"));
    console.log(greet("Developer"));
}


// ---------------------------------------------------------------------------
// 2. Function arguments
// ---------------------------------------------------------------------------
//
// Bash uses $1, $2, $# and "$@".
// JavaScript can use named parameters and ...rest.
//
// Rest parameters preserve argument boundaries as individual array elements.

function inspectArguments(...argumentsList) {
    return {
        count: argumentsList.length,
        first: argumentsList[0] ?? null,
        second: argumentsList[1] ?? null,
        all: argumentsList
    };
}

function demonstrateArguments() {
    console.log("\n=== 2. Function arguments ===");

    console.log(
        inspectArguments(
            "alpha",
            "two words",
            "gamma"
        )
    );

    console.log(
        "Bash analogy: $# = count, $1 = first argument, \"$@\" = all arguments"
    );
}


// ---------------------------------------------------------------------------
// 3. Return values versus process exit codes
// ---------------------------------------------------------------------------
//
// A JavaScript return value is not the same thing as a Unix process exit code.
//
// Bash:
//   return 0
//
// JavaScript:
//   return value;
//
// Node.js process:
//   process.exitCode = 0;
//
// This distinction matters when JavaScript is used as an executable CLI.

function validateUsername(username) {
    if (typeof username !== "string" || username.length === 0) {
        return {
            value: null,
            status: 2,
            message: "username is required"
        };
    }

    if (!/^[A-Za-z0-9_]+$/.test(username)) {
        return {
            value: null,
            status: 3,
            message: "username contains invalid characters"
        };
    }

    return {
        value: username.toLowerCase(),
        status: 0,
        message: "valid"
    };
}

function demonstrateReturnCodes() {
    console.log("\n=== 3. Return values and status codes ===");

    for (const value of ["Atul", "user_01", "", "bad-name"]) {
        console.log(value, "=>", validateUsername(value));
    }

    console.log(
        "A CLI can translate an internal result into process.exitCode."
    );
}


// ---------------------------------------------------------------------------
// 4. Default parameters
// ---------------------------------------------------------------------------

function greetWithDefault(name = "Guest") {
    return `Hello, ${name}`;
}

function demonstrateDefaults() {
    console.log("\n=== 4. Default parameters ===");
    console.log(greetWithDefault());
    console.log(greetWithDefault("Atul"));
}


// ---------------------------------------------------------------------------
// 5. Validation and errors
// ---------------------------------------------------------------------------

function parsePositiveInteger(value) {
    if (typeof value !== "string" || value.trim() === "") {
        return {
            value: null,
            status: 2,
            error: "integer value is required"
        };
    }

    if (!/^-?\d+$/.test(value.trim())) {
        return {
            value: null,
            status: 2,
            error: "invalid integer"
        };
    }

    const number = Number(value);

    if (number <= 0) {
        return {
            value: null,
            status: 3,
            error: "value must be positive"
        };
    }

    return {
        value: number,
        status: 0,
        error: null
    };
}

function demonstrateValidation() {
    console.log("\n=== 5. Validation ===");

    for (const value of ["42", "0", "-4", "abc", ""]) {
        console.log(value, "=>", parsePositiveInteger(value));
    }
}


// ---------------------------------------------------------------------------
// 6. Argument parsing
// ---------------------------------------------------------------------------
//
// This models the sort of positional processing commonly performed with
// Bash's shift and case constructs.

function parseArguments(argumentsList) {
    const options = {
        verbose: false,
        name: "Guest",
        files: []
    };

    let index = 0;

    while (index < argumentsList.length) {
        const current = argumentsList[index];

        if (current === "--verbose") {
            options.verbose = true;
            index += 1;
        } else if (current === "--name") {
            if (index + 1 >= argumentsList.length) {
                return {
                    options: null,
                    status: 2,
                    error: "--name requires a value"
                };
            }

            options.name = argumentsList[index + 1];
            index += 2;
        } else if (current === "--") {
            options.files.push(...argumentsList.slice(index + 1));
            break;
        } else if (current.startsWith("-")) {
            return {
                options: null,
                status: 2,
                error: `unknown option: ${current}`
            };
        } else {
            options.files.push(current);
            index += 1;
        }
    }

    return {
        options,
        status: 0,
        error: null
    };
}

function demonstrateArgumentParser() {
    console.log("\n=== 6. Argument parser ===");

    const samples = [
        ["--verbose", "--name", "Atul", "report.txt"],
        ["--name", "Research", "--", "--literal"],
        ["--unknown"]
    ];

    for (const sample of samples) {
        console.log("Input:", sample);
        console.log("Result:", parseArguments(sample));
    }
}


// ---------------------------------------------------------------------------
// 7. Function composition
// ---------------------------------------------------------------------------

function normalizeEmail(email) {
    return email.trim().toLowerCase();
}

function validateEmail(email) {
    const normalized = normalizeEmail(email);
    const atIndex = normalized.indexOf("@");

    return (
        atIndex > 0 &&
        atIndex < normalized.length - 1 &&
        normalized.slice(atIndex + 1).includes(".")
    );
}

function prepareEmail(email) {
    const normalized = normalizeEmail(email);

    if (!validateEmail(normalized)) {
        return {
            value: null,
            status: 2,
            error: "invalid email address"
        };
    }

    return {
        value: normalized,
        status: 0,
        error: null
    };
}

function demonstrateComposition() {
    console.log("\n=== 7. Function composition ===");

    for (const email of [
        " ATUL@example.com ",
        "invalid",
        "person@example.org"
    ]) {
        console.log(email, "=>", prepareEmail(email));
    }
}


// ---------------------------------------------------------------------------
// 8. Environment variables
// ---------------------------------------------------------------------------
//
// Bash:
//   APP_ENV="${APP_ENV:-development}"
//
// Node:
//   process.env.APP_ENV
//
// Environment variables are strings. Conversion and validation should be
// explicit.

function getConfiguration(environment = process.env) {
    return {
        environment: environment.APP_ENV || "development",
        logLevel: environment.LOG_LEVEL || "INFO",
        timeout: environment.TIMEOUT || "30"
    };
}

function demonstrateEnvironment() {
    console.log("\n=== 8. Environment configuration ===");

    console.log(
        getConfiguration({
            APP_ENV: "production",
            LOG_LEVEL: "WARNING"
        })
    );
}


// ---------------------------------------------------------------------------
// 9. Logging
// ---------------------------------------------------------------------------
//
// In a CLI, stdout can carry data while stderr carries diagnostics.
// console.error writes to stderr.

function logInfo(message) {
    console.error(`[INFO] ${message}`);
}

function logWarning(message) {
    console.error(`[WARN] ${message}`);
}

function logError(message) {
    console.error(`[ERROR] ${message}`);
}

function demonstrateLogging() {
    console.log("\n=== 9. Logging ===");
    logInfo("operation started");
    logWarning("configuration uses a default");
    logError("example diagnostic");
}


// ---------------------------------------------------------------------------
// 10. Secure subprocess execution
// ---------------------------------------------------------------------------
//
// Avoid building shell command strings from untrusted input.
//
// Less safe:
//   exec(`grep ${userInput} file.txt`)
//
// Safer:
//   execFile("grep", [userInput, "file.txt"])
//
// execFile passes arguments separately and does not require a shell.

async function runExternalCommand(command, argumentsList) {
    try {
        const result = await execFileAsync(command, argumentsList, {
            shell: false,
            windowsHide: true
        });

        return {
            stdout: result.stdout.trim(),
            stderr: result.stderr.trim(),
            status: 0
        };
    } catch (error) {
        return {
            stdout: String(error.stdout || "").trim(),
            stderr: String(error.stderr || error.message).trim(),
            status: typeof error.code === "number" ? error.code : 1
        };
    }
}

async function demonstrateSubprocessExecution() {
    console.log("\n=== 10. External commands ===");

    const nodeExecutable = process.execPath;

    const successful = await runExternalCommand(
        nodeExecutable,
        ["-e", "console.log('child process ran')"]
    );

    console.log(successful);

    const failed = await runExternalCommand(
        nodeExecutable,
        ["-e", "process.exit(7)"]
    );

    console.log("Failed command status:", failed.status);
}


// ---------------------------------------------------------------------------
// 11. Security-aware input handling
// ---------------------------------------------------------------------------

async function safeEcho(userInput) {
    return runExternalCommand(
        process.execPath,
        [
            "-e",
            "console.log(process.argv[1])",
            userInput
        ]
    );
}

async function demonstrateCommandInjectionDefense() {
    console.log("\n=== 11. Command injection defense ===");

    const maliciousText = "hello; pretend-this-is-a-command";

    const result = await safeEcho(maliciousText);

    console.log("Input :", maliciousText);
    console.log("Output:", result.stdout);
    console.log("Status:", result.status);

    console.log(
        "The input is supplied as data, not inserted into shell syntax."
    );
}


// ---------------------------------------------------------------------------
// 12. Asynchronous functions and retries
// ---------------------------------------------------------------------------
//
// Bash scripts frequently retry network or infrastructure commands.
// JavaScript naturally models such operations with async/await.

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function retry(operation, attempts, delayMilliseconds = 0) {
    if (!Number.isInteger(attempts) || attempts <= 0) {
        return {
            value: null,
            status: 2,
            error: "attempt count must be positive"
        };
    }

    let lastResult = {
        value: null,
        status: 1,
        error: "operation did not execute"
    };

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
        lastResult = await operation();

        if (lastResult.status === 0) {
            return lastResult;
        }

        if (attempt < attempts && delayMilliseconds > 0) {
            await sleep(delayMilliseconds);
        }
    }

    return lastResult;
}

async function demonstrateRetry() {
    console.log("\n=== 12. Retry logic ===");

    let attempts = 0;

    const operation = async () => {
        attempts += 1;

        if (attempts < 3) {
            return {
                value: null,
                status: 1,
                error: "temporary failure"
            };
        }

        return {
            value: "success",
            status: 0,
            error: null
        };
    };

    const result = await retry(operation, 4);

    console.log("Attempts:", attempts);
    console.log("Result:", result);
}


// ---------------------------------------------------------------------------
// 13. Idempotent filesystem operation
// ---------------------------------------------------------------------------

function ensureDirectory(directoryPath) {
    try {
        fs.mkdirSync(directoryPath, {
            recursive: true
        });

        return {
            value: directoryPath,
            status: 0,
            error: null
        };
    } catch (error) {
        return {
            value: null,
            status: 1,
            error: error.message
        };
    }
}

function demonstrateIdempotency() {
    console.log("\n=== 13. Idempotency ===");

    const temporaryDirectory = fs.mkdtempSync(
        path.join(os.tmpdir(), "bash-functions-")
    );

    const target = path.join(
        temporaryDirectory,
        "nested",
        "output"
    );

    console.log("First :", ensureDirectory(target));
    console.log("Second:", ensureDirectory(target));

    fs.rmSync(temporaryDirectory, {
        recursive: true,
        force: true
    });
}


// ---------------------------------------------------------------------------
// 14. Controlled command dispatch
// ---------------------------------------------------------------------------
//
// A Bash script can dispatch functions through case statements:
//
// case "$command" in
//     status) status ;;
//     version) version ;;
//     *) return 127 ;;
// esac
//
// JavaScript can use an explicit object of allowed handlers.
// This avoids arbitrary evaluation of user-provided function names.

function commandStatus() {
    console.log("status: system is operational");
    return 0;
}

function commandVersion() {
    console.log("version: 1.0.0");
    return 0;
}

function commandEcho(argumentsList) {
    console.log(argumentsList.join(" "));
    return 0;
}

const commandHandlers = Object.freeze({
    status: commandStatus,
    version: commandVersion,
    echo: commandEcho
});

function dispatchCommand(command, argumentsList) {
    const handler = commandHandlers[command];

    if (typeof handler !== "function") {
        console.error(`Unknown command: ${command}`);
        return 127;
    }

    return handler(argumentsList);
}

function demonstrateDispatch() {
    console.log("\n=== 14. Command dispatch ===");

    const commands = [
        ["status", []],
        ["version", []],
        ["echo", ["hello", "shell", "functions"]],
        ["missing", []]
    ];

    for (const [command, argumentsList] of commands) {
        const status = dispatchCommand(command, argumentsList);
        console.log("Exit-style status:", status);
    }
}


// ---------------------------------------------------------------------------
// 15. Cleanup and temporary resources
// ---------------------------------------------------------------------------
//
// Bash commonly uses:
//   trap cleanup EXIT
//
// Node provides process events, but synchronous or structured cleanup is
// often easier to reason about. The example explicitly removes its temporary
// resource.

function demonstrateCleanup() {
    console.log("\n=== 15. Cleanup ===");

    const temporaryDirectory = fs.mkdtempSync(
        path.join(os.tmpdir(), "bash-cleanup-")
    );

    const temporaryFile = path.join(
        temporaryDirectory,
        "data.txt"
    );

    fs.writeFileSync(temporaryFile, "temporary data\n");

    console.log("Created:", temporaryFile);
    console.log("Exists:", fs.existsSync(temporaryFile));

    fs.rmSync(temporaryDirectory, {
        recursive: true,
        force: true
    });

    console.log("After cleanup:", fs.existsSync(temporaryFile));
}


// ---------------------------------------------------------------------------
// 16. Realistic task runner
// ---------------------------------------------------------------------------

class TaskRunner {
    constructor(tasks) {
        this.tasks = new Map(tasks.map(task => [task.name, task]));
    }

    listTasks() {
        return [...this.tasks.values()]
            .sort((a, b) => a.name.localeCompare(b.name))
            .map(task => ({
                name: task.name,
                description: task.description
            }));
    }

    async run(name, argumentsList) {
        const task = this.tasks.get(name);

        if (!task) {
            logError(`unknown task: ${name}`);

            return {
                status: 127,
                value: null
            };
        }

        logInfo(`starting task: ${name}`);

        try {
            const status = await task.handler(argumentsList);

            if (status === 0) {
                logInfo(`task completed: ${name}`);
            } else {
                logError(`task failed: ${name}, status=${status}`);
            }

            return {
                status,
                value: null
            };
        } catch (error) {
            logError(`task threw an exception: ${error.message}`);

            return {
                status: 1,
                value: null
            };
        }
    }
}

function buildTaskRunner() {
    return new TaskRunner([
        {
            name: "status",
            description: "display service status",
            handler: async () => commandStatus()
        },
        {
            name: "version",
            description: "display application version",
            handler: async () => commandVersion()
        },
        {
            name: "echo",
            description: "print supplied arguments",
            handler: async argumentsList => commandEcho(argumentsList)
        }
    ]);
}

async function demonstrateTaskRunner() {
    console.log("\n=== 16. Realistic task runner ===");

    const runner = buildTaskRunner();

    console.log("Tasks:", runner.listTasks());

    console.log("\nRun status:");
    console.log(await runner.run("status", []));

    console.log("\nRun echo:");
    console.log(
        await runner.run(
            "echo",
            ["reusable", "shell", "functions"]
        )
    );

    console.log("\nRun invalid task:");
    console.log(await runner.run("missing", []));
}


// ---------------------------------------------------------------------------
// 17. Child-process streaming
// ---------------------------------------------------------------------------
//
// execFile is useful when the output is collected.
// spawn is useful when output should be processed as it arrives.
//
// This is analogous to the shell's stream-oriented model.

function runStreamingCommand(command, argumentsList) {
    return new Promise(resolve => {
        const child = spawn(command, argumentsList, {
            shell: false,
            stdio: ["ignore", "pipe", "pipe"],
            windowsHide: true
        });

        let stdout = "";
        let stderr = "";

        child.stdout.on("data", chunk => {
            stdout += chunk.toString();
        });

        child.stderr.on("data", chunk => {
            stderr += chunk.toString();
        });

        child.on("error", error => {
            resolve({
                stdout,
                stderr: error.message,
                status: 1
            });
        });

        child.on("close", status => {
            resolve({
                stdout: stdout.trim(),
                stderr: stderr.trim(),
                status: typeof status === "number" ? status : 1
            });
        });
    });
}

async function demonstrateStreaming() {
    console.log("\n=== 17. Streaming child process ===");

    const result = await runStreamingCommand(
        process.execPath,
        [
            "-e",
            "console.log('line one'); console.log('line two');"
        ]
    );

    console.log(result);
}


// ---------------------------------------------------------------------------
// 18. Testing
// ---------------------------------------------------------------------------

async function runSelfTests() {
    console.log("\n=== 18. Self-tests ===");

    console.assert(
        greet("Atul") === "Hello, Atul",
        "greet failed"
    );

    const valid = validateUsername("Atul_123");
    console.assert(
        valid.status === 0 && valid.value === "atul_123",
        "username validation failed"
    );

    const invalid = validateUsername("bad-name");
    console.assert(
        invalid.status !== 0,
        "invalid username should fail"
    );

    const parsed = parseArguments([
        "--verbose",
        "--name",
        "Atul",
        "report.txt"
    ]);

    console.assert(
        parsed.status === 0,
        "argument parsing failed"
    );

    console.assert(
        parsed.options.verbose === true,
        "verbose parsing failed"
    );

    console.assert(
        parsed.options.name === "Atul",
        "name parsing failed"
    );

    console.assert(
        parsed.options.files.length === 1,
        "file parsing failed"
    );

    console.assert(
        dispatchCommand("status", []) === 0,
        "status command failed"
    );

    console.assert(
        dispatchCommand("missing", []) === 127,
        "unknown command status failed"
    );

    console.log("All self-tests passed.");
}


// ---------------------------------------------------------------------------
// 19. CLI entry point
// ---------------------------------------------------------------------------
//
// process.argv corresponds conceptually to Bash's positional parameters.
//
// process.argv[0] = Node executable
// process.argv[1] = script path
// process.argv.slice(2) = user arguments

async function main(argumentsList) {
    console.log("BASH FUNCTIONS: JAVASCRIPT COMPANION");

    if (argumentsList.length > 0) {
        const parsed = parseArguments(argumentsList);

        if (parsed.status !== 0) {
            console.error(parsed.error);
            return parsed.status;
        }

        console.log(`Hello, ${parsed.options.name}`);

        if (parsed.options.verbose) {
            console.log(
                `Files received: ${parsed.options.files.length}`
            );
        }

        for (const file of parsed.options.files) {
            console.log(`Processing: ${file}`);
        }
    }

    demonstrateBasicFunction();
    demonstrateArguments();
    demonstrateReturnCodes();
    demonstrateDefaults();
    demonstrateValidation();
    demonstrateArgumentParser();
    demonstrateComposition();
    demonstrateEnvironment();
    demonstrateLogging();

    await demonstrateSubprocessExecution();
    await demonstrateCommandInjectionDefense();
    await demonstrateRetry();

    demonstrateIdempotency();
    demonstrateDispatch();
    demonstrateCleanup();

    await demonstrateTaskRunner();
    await demonstrateStreaming();

    await runSelfTests();

    console.log("\nImportant Bash design rules:");
    console.log('1. Quote variable expansions: "$value".');
    console.log('2. Forward arguments with "$@".');
    console.log("3. Keep data separate from shell syntax.");
    console.log("4. Use explicit non-zero statuses for failures.");
    console.log("5. Keep reusable functions separate from the main entry point.");
    console.log("6. Send diagnostics to stderr.");
    console.log("7. Avoid eval for untrusted data.");
    console.log("8. Prefer idempotent operations for automation.");

    return 0;
}


if (require.main === module) {
    main(process.argv.slice(2))
        .then(status => {
            process.exitCode = status;
        })
        .catch(error => {
            console.error(error);
            process.exitCode = 1;
        });
}

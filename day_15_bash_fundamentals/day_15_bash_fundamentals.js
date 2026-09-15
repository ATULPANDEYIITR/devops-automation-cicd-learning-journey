#!/usr/bin/env node

/*
 * Bash Fundamentals Companion
 * Topic: Shell syntax, variables, conditions, loops
 *
 * This JavaScript file complements the Python study implementation by
 * demonstrating Bash concepts through JavaScript's process, filesystem,
 * validation, iteration, asynchronous execution, and application-level APIs.
 *
 * Run with:
 *     node bash_fundamentals.js
 *
 * No external npm packages are required.
 */

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync, spawn, spawnSync } = require("child_process");
const readline = require("readline");

// ============================================================================
// 1. OUTPUT HELPERS
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subsection(title) {
    console.log(`\n--- ${title} ---`);
}

function safeRun(title, callback) {
    subsection(title);

    try {
        callback();
    } catch (error) {
        console.error(`${error.name}: ${error.message}`);
    }
}

// ============================================================================
// 2. INTRODUCTION
// ============================================================================

section("BASH FUNDAMENTALS THROUGH JAVASCRIPT");

console.log(`
JavaScript and Bash solve different problems, but JavaScript can demonstrate
many shell-related concepts at the application level.

This implementation focuses on:

  * executing programs
  * arguments and argument boundaries
  * environment variables
  * exit statuses
  * synchronous and asynchronous processes
  * pipelines
  * filesystem operations
  * validation
  * conditions
  * loops
  * functions and classes
  * command-injection risks
  * production-oriented process execution
`);

// ============================================================================
// 3. VARIABLES
// ============================================================================

section("1. VARIABLES AND BASH'S STRING-CENTRIC MODEL");

const applicationName = "Market Audit";
let attemptCount = 3;
const productionMode = true;

console.log("Application:", applicationName);
console.log("Attempts:", attemptCount);
console.log("Production mode:", productionMode);

console.log(`
Bash variables are commonly string-oriented:

    name="Atul"
    count=10

JavaScript variables have explicit runtime value types, so arithmetic and
string operations have different language semantics.

Bash:
    count=$((count + 1))

JavaScript:
    count += 1
`);

attemptCount += 1;
console.log("Incremented attempts:", attemptCount);

// ============================================================================
// 4. ENVIRONMENT VARIABLES
// ============================================================================

section("2. ENVIRONMENT VARIABLES");

console.log("HOME:", process.env.HOME || process.env.USERPROFILE || "<unknown>");
console.log("PATH:", process.env.PATH ? "available" : "missing");

process.env.DEMO_MODE = "development";
console.log("DEMO_MODE:", process.env.DEMO_MODE);

console.log(`
Bash:
    export DEMO_MODE="development"

JavaScript:
    process.env.DEMO_MODE = "development"

Child processes inherit environment variables unless a replacement environment
is explicitly supplied.
`);

// ============================================================================
// 5. EXIT STATUS
// ============================================================================

section("3. EXIT STATUS");

safeRun("Successful child process", () => {
    const result = spawnSync(
        process.execPath,
        ["-e", "process.exit(0)"],
        { encoding: "utf8" }
    );

    console.log("Exit status:", result.status);
});

safeRun("Failed child process", () => {
    const result = spawnSync(
        process.execPath,
        ["-e", "process.exit(5)"],
        { encoding: "utf8" }
    );

    console.log("Exit status:", result.status);
    console.log("Nonzero means failure in the conventional Unix model.");
});

console.log(`
Bash exposes the previous command's status through $?.

Node.js process APIs expose a child's status through result.status for
synchronous execution and through the close/exit events for asynchronous
execution.
`);

// ============================================================================
// 6. COMMAND EXECUTION
// ============================================================================

section("4. COMMAND EXECUTION");

safeRun("execFileSync with separate arguments", () => {
    const output = execFileSync(
        process.execPath,
        ["-e", "console.log(process.argv[1])", "hello world"],
        {
            encoding: "utf8",
            stdio: ["ignore", "pipe", "pipe"]
        }
    );

    console.log("Received:", output.trim());
});

console.log(`
A major security distinction is:

    execFile(command, arguments)

versus constructing a command string for a shell.

When shell interpretation is unnecessary, structured argument APIs preserve
argument boundaries and reduce command-injection risk.
`);

// ============================================================================
// 7. ARGUMENT BOUNDARIES
// ============================================================================

section("5. ARGUMENT BOUNDARIES");

const testArguments = [
    "normal",
    "hello world",
    "semi;colon",
    "$(echo unexpected)",
    "--dangerous-looking-option"
];

for (const argument of testArguments) {
    const output = execFileSync(
        process.execPath,
        [
            "-e",
            "console.log(JSON.stringify(process.argv[1]))",
            argument
        ],
        { encoding: "utf8" }
    );

    console.log(output.trim());
}

console.log(`
The important property is that each value remains one argument.

This is conceptually similar to Bash:

    command -- "$value"

rather than inserting "$value" into shell source.
`);

// ============================================================================
// 8. CONDITIONS
// ============================================================================

section("6. CONDITIONS");

function classifyScore(score) {
    if (score >= 90) {
        return "excellent";
    } else if (score >= 60) {
        return "passing";
    }

    return "needs improvement";
}

for (const score of [95, 72, 40]) {
    console.log(`${score}: ${classifyScore(score)}`);
}

console.log(`
Bash conditions commonly use:

    if (( score >= 90 )); then
        ...
    elif (( score >= 60 )); then
        ...
    else
        ...
    fi

JavaScript uses ordinary boolean expressions inside if/else statements.
`);

// ============================================================================
// 9. STRING VALIDATION
// ============================================================================

section("7. STRING CONDITIONS AND REGULAR EXPRESSIONS");

function isValidIdentifier(value) {
    return /^[A-Za-z_][A-Za-z0-9_]*$/.test(value);
}

const identifiers = [
    "server_1",
    "123server",
    "valid_name",
    "bad-name",
    ""
];

for (const identifier of identifiers) {
    console.log(
        `${JSON.stringify(identifier)} -> ${isValidIdentifier(identifier)}`
    );
}

console.log(`
Bash [[ ... ]] can perform regular-expression matching:

    [[ "$value" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]

The =~ operator uses regular-expression semantics, not ordinary shell glob
semantics.
`);

// ============================================================================
// 10. SWITCH / CASE
// ============================================================================

section("8. BASH CASE AND JAVASCRIPT SWITCH");

function interpretAction(action) {
    switch (action) {
        case "start":
            return "starting service";
        case "stop":
            return "stopping service";
        case "status":
            return "checking service";
        default:
            return "unknown command";
    }
}

for (const action of ["start", "status", "restart"]) {
    console.log(action, "->", interpretAction(action));
}

console.log(`
Bash equivalent:

    case "$action" in
        start)  ... ;;
        stop)   ... ;;
        status) ... ;;
        *)      ... ;;
    esac
`);

// ============================================================================
// 11. FOR LOOPS
// ============================================================================

section("9. FOR LOOPS");

const languages = ["Bash", "Python", "JavaScript", "C++"];

for (const language of languages) {
    console.log("Language:", language);
}

console.log("\nNumeric loop:");

for (let index = 0; index < 5; index++) {
    console.log("index =", index);
}

console.log(`
Bash forms include:

    for language in Bash Python JavaScript C++; do
        echo "$language"
    done

and:

    for ((i=0; i<5; i++)); do
        ...
    done
`);

// ============================================================================
// 12. WHILE LOOPS
// ============================================================================

section("10. WHILE LOOPS");

let counter = 0;

while (counter < 5) {
    console.log("counter =", counter);
    counter += 1;
}

// ============================================================================
// 13. UNTIL LOOP CONCEPT
// ============================================================================

section("11. UNTIL LOOP CONCEPT");

let ready = false;
let checks = 0;

while (!ready) {
    checks += 1;
    console.log("check:", checks);

    if (checks >= 3) {
        ready = true;
    }
}

console.log("Condition became true.");

console.log(`
Bash:

    until ready_command; do
        ...
    done

JavaScript has no direct until keyword, so:

    while (!condition) {
        ...
    }

expresses the same basic control-flow concept.
`);

// ============================================================================
// 14. BREAK AND CONTINUE
// ============================================================================

section("12. BREAK AND CONTINUE");

for (let number = 1; number <= 10; number++) {
    if (number === 5) {
        continue;
    }

    if (number === 8) {
        break;
    }

    console.log(number);
}

// ============================================================================
// 15. FUNCTIONS
// ============================================================================

section("13. FUNCTIONS");

function calculateTotal(prices) {
    let total = 0;

    for (const price of prices) {
        if (!Number.isFinite(price) || price < 0) {
            throw new Error(`Invalid price: ${price}`);
        }

        total += price;
    }

    return total;
}

safeRun("Function validation", () => {
    console.log(calculateTotal([100, 200, 50]));
    console.log(calculateTotal([10, 20, 30]));
});

console.log(`
Bash functions return an integer status using return.

If a function needs to return data, it often writes data to stdout and the
caller captures it using command substitution:

    result=$(calculate_something)

JavaScript functions can directly return arbitrary values.
`);

// ============================================================================
// 16. ARRAYS
// ============================================================================

section("14. ARRAYS");

const ports = [80, 443, 22, 5432];

console.log("Number of ports:", ports.length);
console.log("First port:", ports[0]);

for (const port of ports) {
    console.log("port:", port);
}

const servicePorts = {
    http: 80,
    https: 443,
    ssh: 22,
    postgres: 5432
};

console.log("HTTPS:", servicePorts.https);

console.log(`
Bash indexed array:

    ports=(80 443 22 5432)

Bash associative array:

    declare -A ports
    ports[https]=443

JavaScript arrays and objects provide analogous data-structure concepts.
`);

// ============================================================================
// 17. PARAMETER EXPANSION ANALOGUES
// ============================================================================

section("15. BASH PARAMETER EXPANSION AND JAVASCRIPT");

const configuredName = "";
const fallbackName = configuredName || "Guest";

console.log("Fallback name:", fallbackName);

const filePath = "/var/log/application.log";
const fileName = path.basename(filePath);
const extension = path.extname(fileName);
const stem = path.basename(fileName, extension);

console.log("Path:", filePath);
console.log("Filename:", fileName);
console.log("Extension:", extension);
console.log("Stem:", stem);

console.log(`
Bash provides compact string operations such as:

    ${name:-default}
    ${name:0:5}
    ${file%.log}

JavaScript uses string methods and path utilities for similar tasks.
`);

// ============================================================================
// 18. GLOBBING
// ============================================================================

section("16. GLOBBING");

const directoryEntries = [
    "application.log",
    "database.log",
    "readme.md",
    "metrics.csv"
];

const logFiles = directoryEntries.filter(
    (entry) => entry.endsWith(".log")
);

console.log("Conceptual *.log matches:", logFiles);

console.log(`
Bash pathname expansion:

    *.log

is performed by the shell before the target command executes.

It is different from a regular expression.

Glob:
    *.log

Regex:
    .*\\.log$
`);

// ============================================================================
// 19. FILESYSTEM
// ============================================================================

section("17. FILESYSTEM OPERATIONS");

const temporaryDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "bash-study-")
);

const temporaryFile = path.join(temporaryDirectory, "example.txt");

try {
    fs.writeFileSync(
        temporaryFile,
        "first line\nline with spaces\nthird line\n",
        "utf8"
    );

    console.log("Directory exists:", fs.existsSync(temporaryDirectory));
    console.log("File exists:", fs.existsSync(temporaryFile));

    const content = fs.readFileSync(temporaryFile, "utf8");
    console.log("File contents:");
    console.log(content);
} finally {
    fs.rmSync(temporaryDirectory, {
        recursive: true,
        force: true
    });
}

console.log(`
Bash examples:

    printf '%s\\n' "data" > file.txt
    cat file.txt
    rm -- file.txt

JavaScript provides explicit filesystem APIs rather than shell redirection
syntax.
`);

// ============================================================================
// 20. SAFE LINE PROCESSING
// ============================================================================

section("18. LINE-ORIENTED FILE PROCESSING");

const sampleLines = [
    "first line",
    "line with spaces",
    "backslash: \\",
    "empty follows",
    ""
];

for (const line of sampleLines) {
    console.log(JSON.stringify(line));
}

console.log(`
Classic safe Bash pattern:

    while IFS= read -r line; do
        printf '%s\\n' "$line"
    done < file

The purpose is to preserve line boundaries, whitespace, and backslashes.
`);

// ============================================================================
// 21. ENVIRONMENT OVERRIDES
// ============================================================================

section("19. CHILD-PROCESS ENVIRONMENT");

safeRun("Child environment override", () => {
    const environment = {
        ...process.env,
        DEMO_CHILD_MODE: "test"
    };

    const output = execFileSync(
        process.execPath,
        [
            "-e",
            "console.log(process.env.DEMO_CHILD_MODE)"
        ],
        {
            encoding: "utf8",
            env: environment
        }
    );

    console.log("Child received:", output.trim());
});

// ============================================================================
// 22. SYNCHRONOUS VS ASYNCHRONOUS PROCESS EXECUTION
// ============================================================================

section("20. SYNCHRONOUS AND ASYNCHRONOUS PROCESS EXECUTION");

console.log(`
Synchronous execution blocks the JavaScript event loop until the child
finishes.

Asynchronous execution lets JavaScript continue while the child runs.

Bash also supports background processes:

    command &

followed by:

    wait "$pid"
`);

function runChildAsynchronously() {
    return new Promise((resolve, reject) => {
        const child = spawn(
            process.execPath,
            ["-e", "setTimeout(() => console.log('child finished'), 100)"],
            {
                stdio: ["ignore", "pipe", "pipe"]
            }
        );

        let stdout = "";
        let stderr = "";

        child.stdout.on("data", (chunk) => {
            stdout += chunk.toString();
        });

        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString();
        });

        child.on("error", reject);

        child.on("close", (code, signal) => {
            if (code !== 0) {
                reject(
                    new Error(
                        `Child failed with code=${code}, signal=${signal}, stderr=${stderr}`
                    )
                );
                return;
            }

            resolve(stdout.trim());
        });
    });
}

// ============================================================================
// 23. PIPELINE CONCEPT
// ============================================================================

section("21. PIPELINES");

console.log(`
Bash:

    producer | consumer

The producer's stdout becomes the consumer's stdin.

Node.js can build the same structure with child-process streams.
`);

function demonstratePipeline() {
    return new Promise((resolve, reject) => {
        const producer = spawn(
            process.execPath,
            [
                "-e",
                "console.log('alpha'); console.log('beta'); console.log('gamma');"
            ],
            { stdio: ["ignore", "pipe", "inherit"] }
        );

        const consumer = spawn(
            process.execPath,
            [
                "-e",
                `
let data = "";
process.stdin.on("data", chunk => data += chunk);
process.stdin.on("end", () => {
    console.log("received lines:", data.trim().split(/\\r?\\n/).length);
});
`
            ],
            { stdio: ["pipe", "pipe", "pipe"] }
        );

        let consumerOutput = "";
        let producerError = "";
        let consumerError = "";

        producer.stderr.on("data", (chunk) => {
            producerError += chunk.toString();
        });

        consumer.stdout.on("data", (chunk) => {
            consumerOutput += chunk.toString();
        });

        consumer.stderr.on("data", (chunk) => {
            consumerError += chunk.toString();
        });

        producer.stdout.pipe(consumer.stdin);

        let producerCode = null;
        let consumerCode = null;

        producer.on("close", (code) => {
            producerCode = code;
            if (consumerCode !== null) {
                finish();
            }
        });

        consumer.on("close", (code) => {
            consumerCode = code;
            if (producerCode !== null) {
                finish();
            }
        });

        function finish() {
            if (producerCode !== 0 || consumerCode !== 0) {
                reject(
                    new Error(
                        `Pipeline failure: producer=${producerCode}, consumer=${consumerCode}, ` +
                        `producerError=${producerError}, consumerError=${consumerError}`
                    )
                );
                return;
            }

            resolve(consumerOutput.trim());
        }
    });
}

// ============================================================================
// 24. COMMAND INJECTION
// ============================================================================

section("22. SECURITY: COMMAND INJECTION");

console.log(`
Consider an application that receives:

    userInput

Dangerous design:

    exec("grep " + userInput + " file.txt")

If exec invokes a shell, shell metacharacters can change the command.

Safer design:

    execFile("grep", [userInput, "file.txt"])

when the application genuinely wants grep and userInput should be one
argument.

This is the same core security principle as Bash quoting:

    grep -- "$userInput" file.txt

But argument arrays are generally easier to reason about than manually
constructing shell source.
`);

safeRun("Demonstrating safe argument handling", () => {
    const maliciousLookingInput = "$(echo SHOULD_NOT_EXECUTE)";

    const output = execFileSync(
        process.execPath,
        [
            "-e",
            "console.log(process.argv[1])",
            maliciousLookingInput
        ],
        {
            encoding: "utf8"
        }
    );

    console.log("Input received literally:", output.trim());
});

// ============================================================================
// 25. SHELL OPTION
// ============================================================================

section("23. WHEN A SHELL IS ACTUALLY REQUIRED");

console.log(`
Some tasks genuinely require shell features such as:

    pipelines
    redirection
    shell expansion
    command grouping
    shell builtins
    shell syntax

If shell interpretation is required, the command should be constructed
carefully and untrusted input should never be inserted directly into shell
source.

Prefer direct executable invocation whenever shell syntax is unnecessary.
`);

// ============================================================================
// 26. SHELL DETECTION
// ============================================================================

section("24. DETECTING BASH");

safeRun("Bash availability", () => {
    const result = spawnSync("bash", ["--version"], {
        encoding: "utf8"
    });

    if (result.error) {
        console.log("Bash was not found:", result.error.message);
        return;
    }

    console.log(result.stdout.split("\n")[0]);
});

// ============================================================================
// 27. RUNNING A SAFE BASH SCRIPT
// ============================================================================

section("25. EXECUTING A REAL BASH SCRIPT");

safeRun("Small Bash script", () => {
    const bashScript = `
name="JavaScript caller"
count=3

if (( count > 0 )); then
    printf 'name=%s\\n' "$name"
fi

for ((i=1; i<=count; i++)); do
    printf 'iteration=%d\\n' "$i"
done
`;

    const result = spawnSync(
        "bash",
        ["-c", bashScript],
        {
            encoding: "utf8"
        }
    );

    if (result.error) {
        console.log("Could not execute Bash:", result.error.message);
        return;
    }

    console.log("Exit status:", result.status);
    console.log(result.stdout.trim());

    if (result.stderr) {
        console.error(result.stderr.trim());
    }
});

// ============================================================================
// 28. ARGUMENT PASSING TO BASH
// ============================================================================

section("26. BASH POSitional ARGUMENTS");

safeRun("Bash positional arguments", () => {
    const result = spawnSync(
        "bash",
        [
            "-c",
            'printf "script=%s\\nfirst=%s\\nsecond=%s\\ncount=%s\\n" "$0" "$1" "$2" "$#"',
            "demo.sh",
            "hello world",
            "2026"
        ],
        {
            encoding: "utf8"
        }
    );

    console.log(result.stdout.trim());
});

console.log(`
Notice that the values "hello world" and "2026" are supplied as separate
arguments to Bash.

In Bash:

    $0 = demo.sh
    $1 = hello world
    $2 = 2026
    $# = 2
`);

// ============================================================================
// 29. FUNCTIONS AS OBJECTS
// ============================================================================

section("27. FUNCTIONAL COMPOSITION");

const records = [
    { status: "success", duration: 120 },
    { status: "failure", duration: 300 },
    { status: "success", duration: 80 },
    { status: "warning", duration: 200 }
];

const successfulRecords = records.filter(
    (record) => record.status === "success"
);

const totalSuccessfulDuration = successfulRecords.reduce(
    (total, record) => total + record.duration,
    0
);

console.log("Successful records:", successfulRecords.length);
console.log("Successful duration:", totalSuccessfulDuration);

console.log(`
Bash can compose commands through pipelines:

    producer | filter | transform

JavaScript can compose arrays through filter(), map(), and reduce().
The mechanisms differ, but both encourage decomposition into focused stages.
`);

// ============================================================================
// 30. CLASS-BASED CASE STUDY
// ============================================================================

section("28. DEPLOYMENT VALIDATOR");

class DeploymentValidator {
    constructor(configuration) {
        this.configuration = configuration;
        this.errors = [];
    }

    validateRequiredFields() {
        const requiredFields = [
            "application",
            "version",
            "environment"
        ];

        for (const field of requiredFields) {
            if (!this.configuration[field]) {
                this.errors.push(`Missing required field: ${field}`);
            }
        }
    }

    validateEnvironment() {
        const allowed = new Set([
            "development",
            "staging",
            "production"
        ]);

        if (!allowed.has(this.configuration.environment)) {
            this.errors.push(
                `Invalid environment: ${this.configuration.environment}`
            );
        }
    }

    validateVersion() {
        const version = this.configuration.version || "";

        if (!/^\d+\.\d+\.\d+$/.test(version)) {
            this.errors.push(
                `Invalid version: ${version}`
            );
        }
    }

    validate() {
        this.errors = [];

        this.validateRequiredFields();
        this.validateEnvironment();
        this.validateVersion();

        return this.errors.length === 0;
    }

    report() {
        if (this.validate()) {
            return {
                valid: true,
                errors: []
            };
        }

        return {
            valid: false,
            errors: [...this.errors]
        };
    }
}

const validDeployment = new DeploymentValidator({
    application: "market-api",
    version: "2.4.1",
    environment: "production"
});

const invalidDeployment = new DeploymentValidator({
    application: "",
    version: "2",
    environment: "unknown"
});

console.log("Valid deployment:", validDeployment.report());
console.log("Invalid deployment:", invalidDeployment.report());

// ============================================================================
// 31. RETRY LOGIC
// ============================================================================

section("29. RETRY LOGIC");

function simulatedOperation(attempt) {
    if (attempt < 3) {
        throw new Error("Temporary failure");
    }

    return "success";
}

function retry(maxAttempts) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            console.log(`Attempt ${attempt}`);
            return simulatedOperation(attempt);
        } catch (error) {
            console.log("Failure:", error.message);

            if (attempt === maxAttempts) {
                throw new Error("Maximum retry count exceeded");
            }
        }
    }

    throw new Error("Unreachable state");
}

safeRun("Retry", () => {
    console.log("Final result:", retry(5));
});

console.log(`
Production retry design should consider:

    * retryable versus permanent errors
    * maximum attempts
    * total timeout
    * exponential backoff
    * jitter
    * idempotency
`);

// ============================================================================
// 32. ASYNCHRONOUS RETRY
// ============================================================================

section("30. ASYNCHRONOUS RETRY");

function delay(milliseconds) {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}

async function retryAsync(maxAttempts) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            console.log(`Async attempt ${attempt}`);

            if (attempt < 3) {
                throw new Error("temporary async failure");
            }

            return "async success";
        } catch (error) {
            if (attempt === maxAttempts) {
                throw error;
            }

            const backoff = Math.min(100 * 2 ** (attempt - 1), 1000);
            await delay(backoff);
        }
    }

    throw new Error("Retry failed");
}

// ============================================================================
// 33. FILE VALIDATION
// ============================================================================

section("31. FILE VALIDATION");

function requireRegularFile(filePath) {
    const statistics = fs.statSync(filePath);

    if (!statistics.isFile()) {
        throw new Error(`Not a regular file: ${filePath}`);
    }
}

safeRun("File validation", () => {
    const temporaryDirectory = fs.mkdtempSync(
        path.join(os.tmpdir(), "bash-study-file-")
    );

    const file = path.join(temporaryDirectory, "config.txt");

    try {
        fs.writeFileSync(file, "enabled=true\n", "utf8");

        requireRegularFile(file);
        console.log("File is valid.");
    } finally {
        fs.rmSync(temporaryDirectory, {
            recursive: true,
            force: true
        });
    }
});

// ============================================================================
// 34. SIGNALS
// ============================================================================

section("32. SIGNALS AND CLEANUP");

console.log(`
Bash:

    trap cleanup EXIT
    trap cleanup INT TERM

Node.js:

    process.on("SIGINT", cleanup);
    process.on("SIGTERM", cleanup);

A production process should clean up resources carefully and avoid leaving
partial state behind.
`);

function cleanupExample() {
    console.log("Cleanup handler concept executed.");
}

process.once("SIGINT", cleanupExample);

// ============================================================================
// 35. TEMPORARY RESOURCES
// ============================================================================

section("33. TEMPORARY RESOURCE SAFETY");

console.log(`
Predictable temporary filenames can create race conditions and symlink attacks.

Prefer operating-system-supported temporary-directory mechanisms.

Node.js provides fs.mkdtempSync() and related APIs.
Bash commonly uses mktemp.

Temporary resources should be cleaned up with finally/traps where appropriate.
`);

// ============================================================================
// 36. PATH AND EXECUTABLE SEARCH
// ============================================================================

section("34. PATH AND EXECUTABLE SEARCH");

console.log("PATH entries:");

const pathEntries = (process.env.PATH || "").split(path.delimiter);

for (const entry of pathEntries.slice(0, 5)) {
    console.log(" ", entry);
}

console.log(`
Bash:

    command -v python

Node.js applications should similarly avoid trusting an unexpected executable
search path when operating in security-sensitive environments.

Explicit executable paths can reduce ambiguity when operational requirements
justify them.
`);

// ============================================================================
// 37. STANDARD OUTPUT AND ERROR
// ============================================================================

section("35. STANDARD OUTPUT AND STANDARD ERROR");

safeRun("Separate stdout and stderr", () => {
    const result = spawnSync(
        process.execPath,
        [
            "-e",
            `
console.log("normal output");
console.error("diagnostic output");
`
        ],
        {
            encoding: "utf8"
        }
    );

    console.log("Captured stdout:", JSON.stringify(result.stdout.trim()));
    console.log("Captured stderr:", JSON.stringify(result.stderr.trim()));
});

console.log(`
Unix conventions:

    fd 0 = stdin
    fd 1 = stdout
    fd 2 = stderr

Bash redirection manipulates these streams.

Applications should keep machine-readable output and diagnostics separated
when scripts are consumed by other programs.
`);

// ============================================================================
// 38. PERFORMANCE
// ============================================================================

section("36. PROCESS CREATION PERFORMANCE");

console.log(`
Launching external processes has overhead.

A shell loop that invokes an external program thousands of times can be much
slower than one process that handles all records internally.

Node.js demonstrates the same cost through spawn()/execFile().

Use process composition when it improves clarity and is operationally useful,
but avoid excessive process creation in hot loops.
`);

safeRun("Small process benchmark", () => {
    const iterations = 30;

    const start = process.hrtime.bigint();

    for (let index = 0; index < iterations; index++) {
        spawnSync(
            process.execPath,
            ["-e", "process.exit(0)"],
            { stdio: "ignore" }
        );
    }

    const elapsedNanoseconds =
        process.hrtime.bigint() - start;

    console.log(
        `Started ${iterations} child processes in approximately ` +
        `${Number(elapsedNanoseconds) / 1e6} ms`
    );
});

// ============================================================================
// 39. PARALLEL TASKS
// ============================================================================

section("37. PARALLEL TASKS");

function runParallelCommands() {
    const commands = [
        ["first", 100],
        ["second", 150],
        ["third", 50]
    ];

    return Promise.all(
        commands.map(([name, milliseconds]) => {
            return new Promise((resolve) => {
                setTimeout(() => {
                    resolve(`${name} completed`);
                }, milliseconds);
            });
        })
    );
}

// ============================================================================
// 40. INPUT VALIDATION
// ============================================================================

section("38. INPUT VALIDATION");

function validateEnvironment(environment) {
    const allowed = new Set([
        "development",
        "staging",
        "production"
    ]);

    if (!allowed.has(environment)) {
        throw new Error(`Unsupported environment: ${environment}`);
    }

    return true;
}

for (const environment of [
    "development",
    "production",
    "unknown"
]) {
    try {
        validateEnvironment(environment);
        console.log(environment, "accepted");
    } catch (error) {
        console.log(environment, "rejected:", error.message);
    }
}

// ============================================================================
// 41. BASH SPECIAL PARAMETERS
// ============================================================================

section("39. BASH SPECIAL PARAMETERS");

console.log(`
Important Bash parameters:

    $0     script name
    $1     first argument
    $2     second argument
    $#     number of arguments
    $@     positional arguments
    $?     previous exit status
    $$     current shell PID
    $!     most recent background PID

JavaScript analogues are not exact because the process models differ.

For example:

    process.argv
    process.pid

represent related concepts at the Node.js level.
`);

console.log("Node process PID:", process.pid);
console.log("Node arguments:", process.argv.slice(2));

// ============================================================================
// 42. QUOTING CONCEPT
// ============================================================================

section("40. QUOTING AND ARGUMENT PRESERVATION");

console.log(`
Bash:

    value="hello world"
    printf '%s\\n' "$value"

The quotes preserve the value as one argument.

Without quotes:

    printf '%s\\n' $value

the shell may split the value into multiple words.

JavaScript's argument arrays naturally preserve boundaries:

    execFile(command, ["hello world"])

This is one reason structured process APIs are valuable.
`);

// ============================================================================
// 43. SHELL EXPANSION ORDER
// ============================================================================

section("41. SHELL EXPANSION MENTAL MODEL");

console.log(`
A useful simplified model is:

    1. parse shell syntax
    2. perform expansions
    3. perform pathname expansion where applicable
    4. construct command arguments
    5. perform redirections
    6. execute the command
    7. obtain exit status

Important expansions include:

    parameter expansion      $name
    command substitution     $(command)
    arithmetic expansion      $((expression))
    pathname expansion        *.log
    brace expansion           {1..5}

The exact Bash parsing and expansion rules contain important details and
exceptions, so the simplified model should be treated as a learning aid.
`);

// ============================================================================
// 44. MINI LOG AUDIT
// ============================================================================

section("42. INDUSTRY-STYLE CASE STUDY: LOG AUDIT");

class LogAuditor {
    constructor(logFiles) {
        this.logFiles = logFiles;
    }

    analyze() {
        const report = {
            files: 0,
            lines: 0,
            errors: 0,
            warnings: 0
        };

        for (const [filename, content] of Object.entries(this.logFiles)) {
            if (typeof content !== "string") {
                throw new TypeError(`Invalid content for ${filename}`);
            }

            report.files += 1;

            const lines = content.split(/\r?\n/);

            for (const line of lines) {
                if (line === "") {
                    continue;
                }

                report.lines += 1;

                if (line.includes("ERROR")) {
                    report.errors += 1;
                }

                if (line.includes("WARNING")) {
                    report.warnings += 1;
                }
            }
        }

        return report;
    }
}

const logs = {
    "application.log":
        "INFO startup\nWARNING slow request\nERROR database failure\n",
    "worker.log":
        "INFO worker started\nERROR timeout\nINFO retry succeeded\n"
};

const auditor = new LogAuditor(logs);

console.log(auditor.analyze());

console.log(`
A Bash implementation could compose:

    find
    grep
    awk
    sort
    uniq
    printf

into a pipeline.

The JavaScript implementation instead keeps records in memory and processes
them with explicit program logic. This becomes preferable when parsing rules,
state, validation, or business logic become complex.
`);

// ============================================================================
// 45. COMMAND RESULT ABSTRACTION
// ============================================================================

section("43. COMMAND RESULT ABSTRACTION");

function runExecutable(executable, argumentsList, options = {}) {
    const result = spawnSync(
        executable,
        argumentsList,
        {
            encoding: "utf8",
            ...options
        }
    );

    if (result.error) {
        throw result.error;
    }

    return {
        status: result.status,
        signal: result.signal,
        stdout: result.stdout || "",
        stderr: result.stderr || ""
    };
}

safeRun("Command abstraction", () => {
    const result = runExecutable(
        process.execPath,
        ["-e", "console.log('structured command result')"]
    );

    console.log("Status:", result.status);
    console.log("Output:", result.stdout.trim());
});

// ============================================================================
// 46. ERROR CATEGORIES
// ============================================================================

section("44. FAILURE CATEGORIES");

const failures = [
    "Executable not found",
    "Permission denied",
    "Invalid argument",
    "Missing input file",
    "Invalid configuration",
    "Nonzero child-process exit status",
    "Timeout",
    "Signal termination",
    "Partial output",
    "Network or external-service failure"
];

for (const failure of failures) {
    console.log("*", failure);
}

console.log(`
A production automation system should distinguish failures where practical.

For example:

    command not found
    invalid user input
    temporary network failure
    permanent configuration failure

should not necessarily receive identical retry or alert behavior.
`);

// ============================================================================
// 47. SECURITY CHECKLIST
// ============================================================================

section("45. SECURITY CHECKLIST");

const securityChecklist = [
    "Do not concatenate untrusted input into shell commands.",
    "Prefer direct executable APIs when shell features are unnecessary.",
    "Quote Bash expansions.",
    "Validate paths and identifiers.",
    "Use option terminators such as -- where supported.",
    "Do not log passwords or access tokens.",
    "Protect temporary resources.",
    "Avoid trusting untrusted PATH entries.",
    "Use least-privilege execution.",
    "Treat environment variables as configuration, not automatic secret storage.",
    "Handle signals and cleanup.",
    "Test unusual filenames and input values."
];

for (const item of securityChecklist) {
    console.log("[ ]", item);
}

// ============================================================================
// 48. COMMON MISTAKES
// ============================================================================

section("46. COMMON MISTAKES");

const mistakes = {
    "Unquoted Bash expansion":
        'rm $file',
    "Unsafe shell construction":
        'exec("tool " + userInput)',
    "Parsing human output unnecessarily":
        "regular expression over unstable CLI output",
    "Ignoring exit status":
        "assuming command success",
    "Unlimited retry":
        "retry forever without timeout",
    "Excessive process creation":
        "spawn one process per small record"
};

for (const [mistake, example] of Object.entries(mistakes)) {
    console.log(`${mistake}: ${example}`);
}

// ============================================================================
// 49. ASYNCHRONOUS EXECUTION DEMONSTRATION
// ============================================================================

section("47. ASYNCHRONOUS EXECUTION");

async function demonstrateAsyncExecution() {
    const childOutput = await runChildAsynchronously();
    console.log("Asynchronous child output:", childOutput);

    const pipelineOutput = await demonstratePipeline();
    console.log("Pipeline output:", pipelineOutput);

    const retryOutput = await retryAsync(5);
    console.log("Retry result:", retryOutput);

    const parallelResults = await runParallelCommands();
    console.log("Parallel results:", parallelResults);
}

// ============================================================================
// 50. PRODUCTION SCRIPT ARCHITECTURE
// ============================================================================

section("48. PRODUCTION SCRIPT ARCHITECTURE");

console.log(`
A maintainable Bash automation script often follows this structure:

    #!/usr/bin/env bash
    set -euo pipefail

    usage() {
        ...
    }

    validate_arguments() {
        ...
    }

    prepare() {
        ...
    }

    run() {
        ...
    }

    cleanup() {
        ...
    }

    trap cleanup EXIT

    main "$@"

The JavaScript equivalent may separate:

    configuration
    validation
    process execution
    business logic
    cleanup
    error handling

The architectural principle is to keep operational concerns explicit.
`);

// ============================================================================
// 51. PORTABILITY
// ============================================================================

section("49. BASH PORTABILITY");

console.log(`
Bash-specific syntax should not be assumed to work in every shell.

Examples of Bash-specific or Bash-oriented features include:

    [[ ... ]]
    arrays
    associative arrays
    Bash-specific parameter expansion
    process substitution
    brace expansion

A script that starts with:

    #!/usr/bin/env bash

declares that Bash is required.

A POSIX sh script should follow POSIX shell syntax instead.
`);

// ============================================================================
// 52. PERFORMANCE MODEL
// ============================================================================

section("50. PERFORMANCE MODEL");

console.log(`
Shell is strongest as an orchestration language.

Use Bash when the main task is:

    * starting programs
    * connecting programs
    * moving files
    * configuring environments
    * simple conditions
    * straightforward loops
    * deployment automation

Consider Python, JavaScript, C++, or another language when the task requires:

    * complex algorithms
    * large in-memory data structures
    * sophisticated error models
    * extensive testing
    * high-throughput computation
    * complicated application state

A useful production boundary is:

    Bash = orchestration
    Specialized language = substantial application logic
`);

// ============================================================================
// 53. KNOWLEDGE TEST
// ============================================================================

section("51. KNOWLEDGE TEST");

const knowledgeTest = [
    ["Bash variable expansion", "$variable"],
    ["Command substitution", "$(command)"],
    ["Arithmetic expansion", "$((expression))"],
    ["Previous exit status", "$?"],
    ["First positional argument", "$1"],
    ["Argument count", "$#"],
    ["All positional arguments", "$@"],
    ["Conditional construct", "[[ ... ]]"],
    ["Multi-branch selection", "case ... esac"],
    ["Loop over values", "for"],
    ["Condition-controlled loop", "while"],
    ["Inverse-condition loop", "until"],
    ["Break current loop", "break"],
    ["Skip current iteration", "continue"],
    ["Standard input", "file descriptor 0"],
    ["Standard output", "file descriptor 1"],
    ["Standard error", "file descriptor 2"]
];

for (const [concept, answer] of knowledgeTest) {
    console.log(`${concept}: ${answer}`);
}

// ============================================================================
// 54. RUN ASYNC DEMONSTRATIONS
// ============================================================================

(async () => {
    try {
        await demonstrateAsyncExecution();

        section("52. COMPLETION");

        console.log(`
The JavaScript implementation demonstrated Bash concepts through process
execution, structured arguments, environment variables, exit statuses,
pipelines, filesystem operations, conditions, loops, validation, concurrency,
security boundaries, and production-oriented architecture.

The key distinction is that Bash interprets shell syntax, while JavaScript
normally operates through explicit language constructs and process APIs.
`);
    } catch (error) {
        console.error("Asynchronous demonstration failed:", error.message);
        process.exitCode = 1;
    }
})();

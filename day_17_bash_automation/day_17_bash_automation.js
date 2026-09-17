#!/usr/bin/env node

/**
 * Bash Automation Companion in JavaScript
 *
 * This program demonstrates automation concepts from an application/process
 * perspective. Node.js is useful here because it exposes filesystem,
 * process, asynchronous execution, streams, timers, and operating-system
 * interfaces directly.
 *
 * The program creates a disposable temporary workspace and never performs
 * destructive operations against an arbitrary user-selected directory.
 */

"use strict";

const fs = require("node:fs");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFile, spawn } = require("node:child_process");
const { promisify } = require("node:util");

const execFileAsync = promisify(execFile);

function heading(title) {
    console.log(`\n${"=".repeat(72)}\n${title}\n${"=".repeat(72)}`);
}

async function createDemoTree(root) {
    const directories = [
        "documents",
        "documents/reports",
        "logs",
        "cache",
        "backup"
    ];

    for (const directory of directories) {
        await fsp.mkdir(path.join(root, directory), { recursive: true });
    }

    const files = new Map([
        ["documents/notes.txt", "Important notes\n"],
        ["documents/reports/annual.txt", "Annual report\n"],
        ["logs/application.log", "INFO application started\n"],
        ["logs/old.log", "INFO old event\n"],
        ["cache/temporary.tmp", "temporary data\n"]
    ]);

    for (const [relativePath, content] of files) {
        await fsp.writeFile(path.join(root, relativePath), content, "utf8");
    }
}

async function listFiles(directory) {
    const results = [];

    async function walk(current) {
        const entries = await fsp.readdir(current, { withFileTypes: true });

        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);

            if (entry.isDirectory()) {
                await walk(fullPath);
            } else if (entry.isFile()) {
                results.push(fullPath);
            }
        }
    }

    await walk(directory);
    return results;
}

function sha256(filePath) {
    return new Promise((resolve, reject) => {
        const hash = crypto.createHash("sha256");
        const stream = fs.createReadStream(filePath);

        stream.on("data", chunk => hash.update(chunk));
        stream.on("error", reject);
        stream.on("end", () => resolve(hash.digest("hex")));
    });
}

async function executeProgram(program, argumentsList) {
    // execFile passes arguments separately rather than building a shell string.
    // This avoids unnecessary shell interpretation and reduces injection risk.
    return execFileAsync(program, argumentsList, {
        windowsHide: true
    });
}

async function demonstrateProcessExecution() {
    heading("1. Process execution");

    const command = process.platform === "win32"
        ? ["cmd.exe", ["/c", "echo Bash automation concept"]]
        : ["/bin/echo", ["Bash automation concept"]];

    const result = await executeProgram(command[0], command[1]);

    console.log("Output:", result.stdout.trim());

    /*
     * Bash equivalent concept:
     *
     *     command
     *     status=$?
     *
     * Exit code 0 normally means success.
     * A non-zero exit code indicates failure.
     */
}

async function demonstrateFileAutomation(root) {
    heading("2. File discovery and filtering");

    const files = await listFiles(root);

    for (const file of files.sort()) {
        const relative = path.relative(root, file);
        const stat = await fsp.stat(file);
        console.log(`${relative} | ${stat.size} bytes`);
    }

    const logs = files.filter(file => path.extname(file) === ".log");

    console.log("\nLog files:");
    for (const log of logs) {
        console.log(" ", path.relative(root, log));
    }

    /*
     * Bash commonly uses:
     *
     *     find "$ROOT" -type f -name "*.log"
     *
     * Quoting "$ROOT" matters when paths contain spaces.
     */
}

async function backupDirectory(source, destination) {
    await fsp.mkdir(destination, { recursive: true });

    const sourceFiles = await listFiles(source);
    const manifest = [];

    for (const sourceFile of sourceFiles) {
        const relative = path.relative(source, sourceFile);
        const destinationFile = path.join(destination, relative);

        await fsp.mkdir(path.dirname(destinationFile), { recursive: true });
        await fsp.copyFile(sourceFile, destinationFile);

        const sourceHash = await sha256(sourceFile);
        const destinationHash = await sha256(destinationFile);

        if (sourceHash !== destinationHash) {
            throw new Error(`Integrity check failed: ${relative}`);
        }

        const stat = await fsp.stat(sourceFile);

        manifest.push({
            file: relative,
            size: stat.size,
            sha256: sourceHash
        });
    }

    return manifest;
}

async function demonstrateBackup(root) {
    heading("3. Backup with verification");

    const source = path.join(root, "documents");
    const destination = path.join(root, "backup", "documents");

    const manifest = await backupDirectory(source, destination);

    console.log(JSON.stringify(manifest, null, 2));

    /*
     * A Bash implementation might use:
     *
     *     rsync -a -- "$SOURCE/" "$DESTINATION/"
     *
     * rsync is often more efficient than copying every file on every run
     * because it can identify data that has already been synchronized.
     */
}

async function demonstrateCleanup(root) {
    heading("4. Safe cleanup");

    const logsDirectory = path.join(root, "logs");
    const files = await listFiles(logsDirectory);

    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    const deleted = [];

    for (const file of files) {
        if (path.extname(file) !== ".log") {
            continue;
        }

        const stat = await fsp.stat(file);

        if (stat.mtimeMs < cutoff) {
            // The target was constrained to the known temporary logs directory.
            await fsp.unlink(file);
            deleted.push(file);
        }
    }

    console.log("Deleted:");
    for (const file of deleted) {
        console.log(" ", path.relative(root, file));
    }

    /*
     * Bash equivalent:
     *
     *     find "$LOG_DIR" -type f -name "*.log" -mtime +7 -print
     *
     * Review the output before changing -print to -delete in a new cleanup
     * script.
     */
}

async function demonstrateArchiveConcept() {
    heading("5. Archive and compression concepts");

    console.log(`
Bash archive commands:

    tar -czf backup.tar.gz directory/
    tar -tzf backup.tar.gz
    tar -xzf backup.tar.gz

Compression trades CPU time for reduced storage and transfer size.

A production backup process should also consider:
    - retention
    - integrity
    - encryption
    - restoration testing
    - off-site storage
    - partial failures
`);
}

async function demonstrateStreaming() {
    heading("6. Streams and pipelines");

    const child = spawn(
        process.platform === "win32" ? "cmd.exe" : "printf",
        process.platform === "win32"
            ? ["/c", "echo first line & echo second line"]
            : ["%s\\n%s\\n", "first line", "second line"],
        { stdio: ["ignore", "pipe", "pipe"] }
    );

    let output = "";
    let errors = "";

    child.stdout.on("data", chunk => {
        output += chunk.toString();
    });

    child.stderr.on("data", chunk => {
        errors += chunk.toString();
    });

    await new Promise((resolve, reject) => {
        child.on("error", reject);
        child.on("close", code => {
            if (code === 0) {
                resolve();
            } else {
                reject(new Error(`Process exited with ${code}: ${errors}`));
            }
        });
    });

    console.log(output.trim());

    /*
     * Bash pipelines connect stdout of one command to stdin of another:
     *
     *     command1 | command2 | command3
     *
     * Pipelines are powerful but require careful failure handling.
     */
}

class Logger {
    constructor(filePath) {
        this.filePath = filePath;
    }

    async log(level, message) {
        const timestamp = new Date().toISOString();
        const line = `${timestamp} [${level.toUpperCase()}] ${message}\n`;

        await fsp.appendFile(this.filePath, line, "utf8");
        process.stdout.write(line);
    }
}

async function demonstrateLogging(root) {
    heading("7. Logging");

    const logger = new Logger(path.join(root, "automation.log"));

    await logger.log("info", "Automation started");
    await logger.log("info", "Backup verification completed");
    await logger.log("warning", "Example warning");
    await logger.log("info", "Automation finished");

    /*
     * Bash normally separates:
     *
     *     stdout
     *     stderr
     *
     * Examples:
     *
     *     command > output.log
     *     command 2> error.log
     *     command >> output.log 2>&1
     */
}

async function demonstrateDryRun(root) {
    heading("8. Dry-run design");

    const candidates = (await listFiles(path.join(root, "cache")))
        .filter(file => path.extname(file) === ".tmp");

    console.log("The following files would be removed:");

    for (const file of candidates) {
        console.log(" WOULD DELETE:", path.relative(root, file));
    }

    /*
     * A dry run should calculate the exact intended actions without performing
     * them. This is especially important for cleanup and migration scripts.
     */
}

async function demonstrateRetry() {
    heading("9. Retry with bounded attempts");

    let attempts = 0;

    async function unstableOperation() {
        attempts++;

        if (attempts < 3) {
            throw new Error("Temporary failure");
        }

        return "Success";
    }

    async function retry(operation, maximumAttempts = 3) {
        let lastError;

        for (let attempt = 1; attempt <= maximumAttempts; attempt++) {
            try {
                return await operation();
            } catch (error) {
                lastError = error;

                if (attempt < maximumAttempts) {
                    // Exponential delay: 100ms, 200ms, 400ms...
                    await new Promise(resolve =>
                        setTimeout(resolve, 100 * 2 ** (attempt - 1))
                    );
                }
            }
        }

        throw new Error(
            `Operation failed after ${maximumAttempts} attempts`,
            { cause: lastError }
        );
    }

    console.log(await retry(unstableOperation));
    console.log("Attempts:", attempts);
}

function demonstrateScheduling() {
    heading("10. Scheduling");

    console.log(`
Cron example:

    0 2 * * * /opt/scripts/backup.sh

Common fields:

    minute hour day-of-month month day-of-week

Examples:

    */5 * * * *     every five minutes
    0 * * * *       every hour
    0 2 * * *       every day at 02:00
    0 2 * * 0       every Sunday at 02:00

A scheduled process may have a different environment from an interactive
terminal, so scripts should define important PATH, working-directory, and
configuration assumptions explicitly.
`);
}

function demonstrateSecurity() {
    heading("11. Shell security");

    console.log(`
Important shell-security rules:

    Quote variables:
        "$FILE"

    Do not execute untrusted input as code:
        eval "$INPUT"

    Prefer separate argument arrays in application code.

    Validate destructive targets.

    Use least privilege.

    Never expose credentials in logs.

    Restrict secret-file permissions.

    Treat filenames as data rather than shell syntax.

    Be careful with PATH, temporary files, symbolic links, and permissions.

Command injection happens when untrusted data becomes executable shell syntax.
Using execFile with explicit arguments avoids unnecessary shell parsing.
`);
}

function demonstrateIdempotency() {
    heading("12. Idempotency");

    console.log(`
Idempotent Bash operation:

    mkdir -p "$TARGET"

Repeated execution converges on the same desired state.

Automation should be designed so a retry does not accidentally:
    - duplicate records
    - overwrite unrelated data
    - send duplicate notifications
    - create conflicting resources
    - delete newly created data
`);
}

function demonstratePerformance() {
    heading("13. Performance");

    console.log(`
Potential performance bottlenecks:

    - millions of filesystem entries
    - excessive process creation
    - repeated hashing
    - unnecessary compression
    - network transfers
    - serial operations that could safely run concurrently

Useful Unix tools include:

    find
    rsync
    tar
    xargs
    awk
    sed

Measure before optimizing. Parallelism can improve throughput but may increase
disk contention, memory use, network load, and operational complexity.
`);
}

async function demonstrateTests(root) {
    heading("14. Automated verification");

    const source = path.join(root, "documents");
    const destination = path.join(root, "backup", "test");

    const manifest = await backupDirectory(source, destination);

    if (manifest.length === 0) {
        throw new Error("Expected backup manifest to contain files");
    }

    for (const item of manifest) {
        const backupFile = path.join(destination, item.file);
        const actualHash = await sha256(backupFile);

        if (actualHash !== item.sha256) {
            throw new Error(`Test failed for ${item.file}`);
        }
    }

    console.log("All backup integrity tests passed.");
}

async function main() {
    heading("BASH AUTOMATION STUDY COMPANION");

    const root = await fsp.mkdtemp(
        path.join(os.tmpdir(), "bash-automation-study-")
    );

    try {
        await createDemoTree(root);

        await demonstrateProcessExecution();
        await demonstrateFileAutomation(root);
        await demonstrateBackup(root);
        await demonstrateCleanup(root);
        await demonstrateArchiveConcept();
        await demonstrateStreaming();
        await demonstrateLogging(root);
        await demonstrateDryRun(root);
        await demonstrateRetry();
        demonstrateScheduling();
        demonstrateSecurity();
        demonstrateIdempotency();
        demonstratePerformance();
        await demonstrateTests(root);

        heading("Production design");

        console.log(`
A reliable automation lifecycle is:

    configuration
        -> validation
        -> locking
        -> pre-flight checks
        -> execution
        -> verification
        -> logging
        -> cleanup
        -> exit status

Important Bash features to understand:

    variables
    quoting
    command substitution
    pipelines
    redirection
    exit codes
    functions
    arrays
    conditions
    loops
    traps
    cron
    find
    tar
    rsync
    permissions
    signals
    environment variables
    strict mode

The disposable workspace will now be removed.
`);
    } finally {
        await fsp.rm(root, { recursive: true, force: true });
    }
}

main().catch(error => {
    console.error(`Automation failed: ${error.message}`);
    process.exitCode = 1;
});

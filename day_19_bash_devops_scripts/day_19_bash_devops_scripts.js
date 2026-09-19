#!/usr/bin/env node
"use strict";

/*
 * Bash DevOps Scripts: Deployment, Health Checks, and Log Processing
 *
 * This JavaScript program complements the Bash-oriented study material by
 * demonstrating the same operational concepts using Node.js APIs.
 *
 * Topics demonstrated:
 * - exit codes
 * - environment configuration
 * - command execution
 * - child processes
 * - pipelines
 * - streaming logs
 * - structured log parsing
 * - health checks
 * - retries and timeouts
 * - deployment staging
 * - atomic activation
 * - rollback
 * - idempotency
 * - cleanup
 * - validation
 * - security-aware command execution
 * - performance-conscious streaming
 */

const fs = require("node:fs");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const http = require("node:http");
const net = require("node:net");
const crypto = require("node:crypto");


// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

function loadConfig() {
    const retries = Number.parseInt(
        process.env.HEALTH_RETRIES || "3",
        10
    );

    const timeout = Number.parseInt(
        process.env.HEALTH_TIMEOUT || "3000",
        10
    );

    return {
        application: process.env.APP_NAME || "example-app",
        environment: process.env.DEPLOY_ENV || "development",
        version: process.env.APP_VERSION || "1.0.0",
        retries: Number.isFinite(retries) && retries > 0 ? retries : 3,
        healthTimeoutMs:
            Number.isFinite(timeout) && timeout > 0 ? timeout : 3000
    };
}


function validateConfig(config) {
    const errors = [];

    if (!/^[A-Za-z0-9._-]+$/.test(config.application)) {
        errors.push("Application name contains unsafe characters.");
    }

    if (!/^[A-Za-z0-9._-]+$/.test(config.environment)) {
        errors.push("Environment contains unsafe characters.");
    }

    if (!/^[A-Za-z0-9._+-]+$/.test(config.version)) {
        errors.push("Version contains unsafe characters.");
    }

    return errors;
}


// ---------------------------------------------------------------------------
// Exit codes
// ---------------------------------------------------------------------------

function demonstrateExitCodes() {
    console.log("\n=== Exit Codes ===");

    const success = 0;
    const failure = 1;

    console.log(`Success status: ${success}`);
    console.log(`Failure status: ${failure}`);

    if (success === 0) {
        console.log("Zero represents successful completion.");
    }

    if (failure !== 0) {
        console.log("Non-zero represents failure.");
    }
}


// ---------------------------------------------------------------------------
// Safe command execution
// ---------------------------------------------------------------------------

function runCommand(command, args = [], options = {}) {
    /*
     * spawn() receives executable and arguments separately.
     *
     * This is preferable to building a shell command string from untrusted
     * input. shell: false is the default and is intentionally explicit here.
     */
    return new Promise((resolve) => {
        const child = spawn(command, args, {
            cwd: options.cwd,
            env: options.env || process.env,
            shell: false
        });

        let stdout = "";
        let stderr = "";
        let timedOut = false;

        const start = process.hrtime.bigint();

        const timer = setTimeout(() => {
            timedOut = true;
            child.kill("SIGTERM");

            setTimeout(() => {
                if (!child.killed) {
                    child.kill("SIGKILL");
                }
            }, 250);
        }, options.timeoutMs || 5000);

        child.stdout.on("data", (chunk) => {
            stdout += chunk.toString();
        });

        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString();
        });

        child.on("error", (error) => {
            clearTimeout(timer);

            resolve({
                command: [command, ...args],
                exitCode: 127,
                stdout,
                stderr: `${stderr}${error.message}`,
                durationMs: Number(process.hrtime.bigint() - start) / 1e6
            });
        });

        child.on("close", (code) => {
            clearTimeout(timer);

            resolve({
                command: [command, ...args],
                exitCode: timedOut ? 124 : (code ?? 1),
                stdout,
                stderr,
                durationMs: Number(process.hrtime.bigint() - start) / 1e6
            });
        });
    });
}


async function demonstrateCommandExecution() {
    console.log("\n=== Safe Command Execution ===");

    const result = await runCommand(
        process.platform === "win32" ? "cmd.exe" : "printf",
        process.platform === "win32"
            ? ["/c", "echo", "Hello from Node.js"]
            : ["%s\\n", "Hello from Node.js"]
    );

    console.log("Command:", result.command.join(" "));
    console.log("Exit code:", result.exitCode);
    console.log("STDOUT:", result.stdout.trim());
    console.log("Duration:", result.durationMs.toFixed(2), "ms");
}


// ---------------------------------------------------------------------------
// Log pipeline
// ---------------------------------------------------------------------------

const sampleLogs = [
    "2026-09-19T10:00:01Z INFO api status=200 latency_ms=31",
    "2026-09-19T10:00:02Z INFO api status=200 latency_ms=22",
    "2026-09-19T10:00:03Z WARN api status=200 latency_ms=820",
    "2026-09-19T10:00:04Z ERROR db status=503 latency_ms=0",
    "2026-09-19T10:00:05Z INFO api status=201 latency_ms=45",
    "2026-09-19T10:00:06Z ERROR db status=503 latency_ms=0",
    "2026-09-19T10:00:07Z INFO api status=200 latency_ms=27",
    "2026-09-19T10:00:08Z WARN api status=200 latency_ms=700",
    "2026-09-19T10:00:09Z INFO api status=200 latency_ms=19"
];


function filterLogs(logs, level) {
    const expected = level.toUpperCase();

    return logs.filter((line) => {
        const fields = line.split(/\s+/);
        return fields[1]?.toUpperCase() === expected;
    });
}


function extractStatusCodes(logs) {
    const pattern = /\bstatus=(\d{3})\b/g;
    const statuses = [];

    for (const line of logs) {
        for (const match of line.matchAll(pattern)) {
            statuses.push(Number(match[1]));
        }
    }

    return statuses;
}


function processLogs(logs) {
    const result = {
        total: logs.length,
        levels: {
            INFO: 0,
            WARN: 0,
            ERROR: 0
        },
        statusCodes: {},
        latencies: []
    };

    const latencyPattern = /\blatency_ms=(\d+(?:\.\d+)?)\b/;

    for (const line of logs) {
        const fields = line.split(/\s+/);
        const level = fields[1];

        if (Object.hasOwn(result.levels, level)) {
            result.levels[level] += 1;
        }

        for (const status of extractStatusCodes([line])) {
            result.statusCodes[status] =
                (result.statusCodes[status] || 0) + 1;
        }

        const latency = line.match(latencyPattern);

        if (latency) {
            result.latencies.push(Number(latency[1]));
        }
    }

    result.averageLatency =
        result.latencies.length === 0
            ? 0
            : result.latencies.reduce((a, b) => a + b, 0) /
              result.latencies.length;

    result.errorRate =
        result.total === 0
            ? 0
            : result.levels.ERROR / result.total;

    return result;
}


function demonstrateLogProcessing() {
    console.log("\n=== Log Processing ===");

    const errors = filterLogs(sampleLogs, "ERROR");
    const statusCodes = extractStatusCodes(errors);
    const report = processLogs(sampleLogs);

    console.log("Error lines:", errors);
    console.log("Error status codes:", statusCodes);
    console.log(
        "Report:",
        JSON.stringify(report, null, 2)
    );
}


// ---------------------------------------------------------------------------
// Streaming file processing
// ---------------------------------------------------------------------------

async function createLargeLog(filePath, count = 10000) {
    const stream = fs.createWriteStream(filePath, {
        encoding: "utf8"
    });

    for (let index = 0; index < count; index += 1) {
        if (!stream.write(
            `2026-09-19T10:00:00Z INFO record=${index}\n`
        )) {
            await new Promise((resolve) =>
                stream.once("drain", resolve)
            );
        }
    }

    await new Promise((resolve, reject) => {
        stream.end(resolve);
        stream.on("error", reject);
    });
}


async function countFileLines(filePath) {
    /*
     * The stream-based implementation avoids loading the entire log into
     * memory. This matters when processing multi-gigabyte production logs.
     */
    const stream = fs.createReadStream(filePath, {
        encoding: "utf8"
    });

    let lineCount = 0;
    let remainder = "";

    for await (const chunk of stream) {
        const text = remainder + chunk;
        const lines = text.split("\n");

        remainder = lines.pop() || "";
        lineCount += lines.length;
    }

    if (remainder.length > 0) {
        lineCount += 1;
    }

    return lineCount;
}


async function demonstrateStreaming() {
    console.log("\n=== Streaming Log Processing ===");

    const temporaryDirectory = await fsp.mkdtemp(
        path.join(os.tmpdir(), "devops-stream-")
    );

    try {
        const filePath = path.join(
            temporaryDirectory,
            "application.log"
        );

        await createLargeLog(filePath, 10000);

        const count = await countFileLines(filePath);
        console.log("Lines:", count);
    } finally {
        await fsp.rm(temporaryDirectory, {
            recursive: true,
            force: true
        });
    }
}


// ---------------------------------------------------------------------------
// Health checks
// ---------------------------------------------------------------------------

function tcpHealthCheck(host, port, timeoutMs = 1000) {
    return new Promise((resolve) => {
        const socket = new net.Socket();

        let settled = false;

        const finish = (healthy) => {
            if (settled) {
                return;
            }

            settled = true;
            socket.destroy();
            resolve(healthy);
        };

        socket.setTimeout(timeoutMs);

        socket.once("connect", () => finish(true));
        socket.once("timeout", () => finish(false));
        socket.once("error", () => finish(false));
        socket.once("close", () => finish(false));

        socket.connect(port, host);
    });
}


function httpHealthCheck(url, timeoutMs = 3000) {
    return new Promise((resolve) => {
        const request = http.get(url, (response) => {
            const healthy =
                response.statusCode >= 200 &&
                response.statusCode < 400;

            response.resume();
            response.once("end", () => resolve(healthy));
        });

        request.setTimeout(timeoutMs, () => {
            request.destroy();
            resolve(false);
        });

        request.once("error", () => resolve(false));
    });
}


async function retry(operation, attempts, delayMs) {
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
        try {
            if (await operation()) {
                return true;
            }
        } catch {
            // A failed attempt is retried only when attempts remain.
        }

        if (attempt < attempts) {
            await new Promise((resolve) =>
                setTimeout(resolve, delayMs)
            );
        }
    }

    return false;
}


async function demonstrateHealthChecks() {
    console.log("\n=== Health Checks ===");

    const healthyCommand = await runCommand(
        process.platform === "win32" ? "cmd.exe" : "true",
        process.platform === "win32" ? ["/c", "exit", "0"] : []
    );

    const commandHealthy = healthyCommand.exitCode === 0;

    console.log(
        "Command check:",
        commandHealthy ? "healthy" : "unhealthy"
    );

    const tcpHealthy = await tcpHealthCheck(
        "127.0.0.1",
        65534,
        100
    );

    console.log(
        "TCP check:",
        tcpHealthy ? "healthy" : "unhealthy"
    );
}


// ---------------------------------------------------------------------------
// Deployment model
// ---------------------------------------------------------------------------

class DeploymentManager {
    constructor(rootDirectory) {
        this.rootDirectory = rootDirectory;
        this.currentPath = path.join(
            rootDirectory,
            "current"
        );
    }

    async initialize() {
        await fsp.mkdir(this.rootDirectory, {
            recursive: true
        });
    }

    releasePath(version) {
        return path.join(
            this.rootDirectory,
            version
        );
    }

    validateVersion(version) {
        return /^[A-Za-z0-9._+-]+$/.test(version);
    }

    async createRelease(version, files) {
        if (!this.validateVersion(version)) {
            throw new Error("Unsafe release version.");
        }

        const releasePath = this.releasePath(version);

        try {
            await fsp.mkdir(releasePath);
        } catch (error) {
            if (error.code === "EEXIST") {
                throw new Error(
                    `Release ${version} already exists.`
                );
            }
            throw error;
        }

        for (const [relativeName, content] of Object.entries(files)) {
            if (
                path.isAbsolute(relativeName) ||
                relativeName
                    .split(/[\\/]+/)
                    .includes("..")
            ) {
                throw new Error(
                    `Unsafe release path: ${relativeName}`
                );
            }

            const destination = path.join(
                releasePath,
                relativeName
            );

            await fsp.mkdir(
                path.dirname(destination),
                { recursive: true }
            );

            await fsp.writeFile(
                destination,
                content,
                "utf8"
            );
        }

        return releasePath;
    }

    async getCurrentVersion() {
        try {
            const target = await fsp.readlink(
                this.currentPath
            );

            return path.basename(target);
        } catch (error) {
            if (error.code === "ENOENT") {
                return null;
            }

            throw error;
        }
    }

    async activate(version) {
        const target = this.releasePath(version);

        await fsp.access(target);

        const temporaryLink = path.join(
            this.rootDirectory,
            `.current-${crypto.randomUUID()}`
        );

        await fsp.symlink(
            target,
            temporaryLink,
            "junction"
        );

        /*
         * The conceptual goal is an atomic active-version switch.
         * The exact atomic replacement semantics vary between filesystems
         * and operating systems, so production deployment code should account
         * for the target platform explicitly.
         */
        try {
            await fsp.rm(this.currentPath, {
                recursive: true,
                force: true
            });

            await fsp.rename(
                temporaryLink,
                this.currentPath
            );
        } catch (error) {
            await fsp.rm(temporaryLink, {
                recursive: true,
                force: true
            });

            throw error;
        }
    }
}


async function demonstrateDeployment() {
    console.log("\n=== Deployment and Rollback ===");

    const root = await fsp.mkdtemp(
        path.join(os.tmpdir(), "devops-release-")
    );

    try {
        const manager = new DeploymentManager(
            path.join(root, "releases")
        );

        await manager.initialize();

        await manager.createRelease(
            "1.0.0",
            {
                "VERSION": "1.0.0\n"
            }
        );

        await manager.activate("1.0.0");

        const previous = await manager.getCurrentVersion();

        console.log("Initial active version:", previous);

        await manager.createRelease(
            "1.1.0",
            {
                "VERSION": "1.1.0\n"
            }
        );

        const healthCheck = async () => true;

        await manager.activate("1.1.0");

        if (await healthCheck()) {
            console.log(
                "Deployment 1.1.0 passed health validation."
            );
        } else {
            await manager.activate(previous);
            console.log("Rollback completed.");
        }

        console.log(
            "Current version:",
            await manager.getCurrentVersion()
        );

        await manager.createRelease(
            "1.2.0",
            {
                "VERSION": "1.2.0\n"
            }
        );

        await manager.activate("1.2.0");

        const failedHealthCheck = async () => false;

        if (!(await failedHealthCheck())) {
            await manager.activate(previous === "1.0.0"
                ? "1.0.0"
                : "1.1.0");

            console.log(
                "Failed deployment rolled back."
            );
        }

        console.log(
            "Version after rollback:",
            await manager.getCurrentVersion()
        );
    } finally {
        await fsp.rm(root, {
            recursive: true,
            force: true
        });
    }
}


// ---------------------------------------------------------------------------
// Structured JSON logs
// ---------------------------------------------------------------------------

function parseJsonLogs(lines) {
    const records = [];

    lines.forEach((line, index) => {
        try {
            const record = JSON.parse(line);

            if (
                record &&
                typeof record === "object" &&
                !Array.isArray(record)
            ) {
                records.push({
                    ...record,
                    lineNumber: index + 1
                });
            }
        } catch {
            // Invalid JSON is skipped rather than crashing the entire report.
        }
    });

    return records;
}


function demonstrateJsonLogs() {
    console.log("\n=== Structured Logs ===");

    const lines = [
        '{"level":"INFO","service":"api","status":200}',
        '{"level":"ERROR","service":"db","status":503}',
        "not-json",
        '{"level":"ERROR","service":"api","status":500}'
    ];

    const records = parseJsonLogs(lines);
    const errors = records.filter(
        (record) => record.level === "ERROR"
    );

    console.log(
        JSON.stringify(
            {
                validRecords: records.length,
                errors
            },
            null,
            2
        )
    );
}


// ---------------------------------------------------------------------------
// Validation and security
// ---------------------------------------------------------------------------

function safeFilename(filename) {
    if (!filename || path.isAbsolute(filename)) {
        return false;
    }

    if (
        filename.split(/[\\/]+/).includes("..")
    ) {
        return false;
    }

    return /^[A-Za-z0-9._-]+$/.test(filename);
}


function demonstrateSecurity() {
    console.log("\n=== Security Validation ===");

    const filenames = [
        "application.log",
        "release-1.0.0.tar.gz",
        "../secret",
        "/etc/passwd",
        "file;rm -rf /"
    ];

    for (const filename of filenames) {
        console.log(
            `${filename.padEnd(24)} -> ${
                safeFilename(filename)
                    ? "accepted"
                    : "rejected"
            }`
        );
    }
}


// ---------------------------------------------------------------------------
// Local health server for a deterministic HTTP demonstration
// ---------------------------------------------------------------------------

function startHealthServer() {
    const server = http.createServer((request, response) => {
        if (request.url === "/health") {
            response.writeHead(200, {
                "Content-Type": "application/json"
            });

            response.end(
                JSON.stringify({
                    status: "healthy",
                    service: "devops-demo"
                })
            );

            return;
        }

        response.writeHead(404);
        response.end();
    });

    return new Promise((resolve) => {
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();

            resolve({
                server,
                url: `http://127.0.0.1:${address.port}/health`
            });
        });
    });
}


async function demonstrateHttpHealthCheck() {
    console.log("\n=== HTTP Health Check ===");

    const { server, url } = await startHealthServer();

    try {
        const healthy = await retry(
            () => httpHealthCheck(url, 1000),
            3,
            100
        );

        console.log(
            "HTTP health:",
            healthy ? "healthy" : "unhealthy"
        );
    } finally {
        await new Promise((resolve) =>
            server.close(resolve)
        );
    }
}


// ---------------------------------------------------------------------------
// Main program
// ---------------------------------------------------------------------------

async function runAll() {
    const config = loadConfig();

    console.log("=== Bash DevOps Concepts in Node.js ===");
    console.log(
        JSON.stringify(config, null, 2)
    );

    const configErrors = validateConfig(config);

    if (configErrors.length > 0) {
        console.error(
            "Configuration errors:",
            configErrors
        );
        process.exitCode = 1;
        return;
    }

    demonstrateExitCodes();
    await demonstrateCommandExecution();
    demonstrateLogProcessing();
    await demonstrateStreaming();
    await demonstrateHealthChecks();
    await demonstrateDeployment();
    demonstrateJsonLogs();
    demonstrateSecurity();
    await demonstrateHttpHealthCheck();

    console.log("\nAll demonstrations completed.");
}


runAll().catch((error) => {
    console.error("Fatal error:", error.message);
    process.exitCode = 1;
});

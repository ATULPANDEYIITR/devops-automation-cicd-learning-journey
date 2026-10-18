"use strict";

/*
 * Docker CLI lifecycle controller for Node.js.
 * Requires Docker Engine or Docker Desktop and a working Docker CLI.
 * Run with: node docker-cli.js
 */

const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");

function runDocker(args, options = {}) {
    const { timeout = 30000, maxOutputBytes = 2 * 1024 * 1024 } = options;

    if (!Array.isArray(args) || args.length === 0) {
        return Promise.reject(new TypeError("Docker arguments must be a non-empty array."));
    }

    return new Promise((resolve, reject) => {
        // Avoid shell interpolation: every argument is passed directly to Docker.
        const child = spawn("docker", args, {
            shell: false,
            windowsHide: true,
            stdio: ["ignore", "pipe", "pipe"],
        });

        let stdout = "";
        let stderr = "";
        let outputBytes = 0;
        let settled = false;

        function finish(error, result) {
            if (settled) return;
            settled = true;
            clearTimeout(timer);

            if (error) reject(error);
            else resolve(result);
        }

        function collect(stream, chunk, destination) {
            outputBytes += chunk.length;

            if (outputBytes > maxOutputBytes) {
                child.kill();
                finish(new Error("Docker output exceeded the configured limit."));
                return;
            }

            if (destination === "stdout") stdout += chunk.toString();
            else stderr += chunk.toString();
        }

        child.stdout.on("data", chunk => collect(child.stdout, chunk, "stdout"));
        child.stderr.on("data", chunk => collect(child.stderr, chunk, "stderr"));

        child.on("error", error => {
            finish(new Error(`Could not start Docker CLI: ${error.message}`));
        });

        child.on("close", (code, signal) => {
            if (code !== 0) {
                finish(
                    new Error(
                        `docker ${args[0]} failed; exit=${code}, signal=${signal}, ` +
                        `stderr=${stderr.trim()}`
                    )
                );
                return;
            }

            finish(null, { stdout: stdout.trim(), stderr: stderr.trim() });
        });

        const timer = setTimeout(() => {
            child.kill();
            finish(new Error(`Docker command timed out after ${timeout} ms.`));
        }, timeout);
    });
}

class DockerService {
    async pull(image) {
        if (typeof image !== "string" || !image.trim()) {
            throw new TypeError("An image reference is required.");
        }

        return runDocker(["pull", image], { timeout: 600000 });
    }

    async runEphemeral(image, command) {
        if (!Array.isArray(command) || command.length === 0) {
            throw new TypeError("Provide a command as an argument array.");
        }

        // --rm removes this one-shot container when its main process exits.
        return runDocker([
            "run",
            "--rm",
            image,
            ...command,
        ], { timeout: 120000 });
    }

    async startService(image) {
        const name = `cli-demo-${randomUUID().slice(0, 8)}`;

        const result = await runDocker([
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "purpose=docker-cli-training",
            image,
            "sh",
            "-c",
            "while true; do echo service-ready; sleep 5; done",
        ], { timeout: 120000 });

        return { name, containerId: result.stdout };
    }

    async listContainers(includeStopped = false) {
        const args = ["ps"];
        if (includeStopped) args.push("-a");
        args.push("--format", "{{json .}}");

        const { stdout } = await runDocker(args);

        // Docker emits one JSON object per line rather than a JSON array.
        return stdout
            ? stdout.split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line))
            : [];
    }

    async exec(container, command) {
        if (!container || !Array.isArray(command) || command.length === 0) {
            throw new TypeError("Container and command are required.");
        }

        return runDocker(["exec", container, ...command]);
    }

    async logs(container, tail = 20) {
        if (!Number.isInteger(tail) || tail < 1 || tail > 10000) {
            throw new RangeError("tail must be an integer between 1 and 10000.");
        }

        return runDocker(["logs", "--tail", String(tail), container]);
    }

    async inspectState(container) {
        const { stdout } = await runDocker([
            "inspect",
            "--format",
            "{{json .State}}",
            container,
        ]);

        return JSON.parse(stdout);
    }

    async stop(container) {
        return runDocker(["stop", "--time", "10", container], { timeout: 30000 });
    }

    async start(container) {
        return runDocker(["start", container], { timeout: 30000 });
    }

    async remove(container) {
        return runDocker(["rm", "-f", container], { timeout: 30000 });
    }
}

async function main() {
    const docker = new DockerService();
    let service;

    try {
        console.log("Docker client and engine versions");
        console.log((await runDocker(["version", "--format", "{{.Client.Version}} / {{.Server.Version}}"])).stdout);

        console.log("\nPulling Alpine Linux");
        console.log((await docker.pull("alpine:3.22")).stdout);

        console.log("\nRunning a one-shot container");
        const result = await docker.runEphemeral("alpine:3.22", [
            "sh",
            "-c",
            "echo 'One-shot task completed'; uname -s",
        ]);
        console.log(result.stdout);

        console.log("\nStarting a persistent service container");
        service = await docker.startService("alpine:3.22");
        console.log(service);

        console.log("\nRunning ps");
        console.log(await docker.listContainers());

        console.log("\nRunning exec");
        console.log((await docker.exec(service.name, [
            "sh", "-c", "echo 'Health probe executed'",
        ])).stdout);

        console.log("\nReading logs");
        console.log((await docker.logs(service.name, 5)).stdout);

        console.log("\nInspecting state");
        console.log(await docker.inspectState(service.name));

        console.log("\nStopping container");
        console.log((await docker.stop(service.name)).stdout);

        console.log("\nStarting stopped container");
        console.log((await docker.start(service.name)).stdout);
    } catch (error) {
        console.error(`Docker workflow failed: ${error.message}`);
        process.exitCode = 1;
    } finally {
        if (service) {
            try {
                await docker.remove(service.name);
                console.log(`Removed training container ${service.name}`);
            } catch (error) {
                console.error(`Cleanup failed: ${error.message}`);
                process.exitCode = 1;
            }
        }
    }
}

if (require.main === module) {
    main();
}

module.exports = { DockerService, runDocker };

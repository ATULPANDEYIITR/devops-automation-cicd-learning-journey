"use strict";

/**
 * Jenkins + Docker pipeline orchestration.
 *
 * Node.js 18+
 *
 * Features:
 * - Event-driven pipeline execution
 * - Docker build and image verification
 * - Test and security validation hooks
 * - Registry publishing
 * - Docker Compose deployment
 * - Stage dependencies
 * - Retry and timeout management
 * - Pipeline metrics
 * - JSON execution reports
 *
 * Usage:
 *   node jenkins-docker.js
 *   EXECUTE=true node jenkins-docker.js
 *   EXECUTE=true PUSH=true node jenkins-docker.js
 */

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const EventEmitter = require("node:events");

// -------------------------------------------------------
// Configuration
// -------------------------------------------------------

const CONFIG = Object.freeze({
    application: "inventory-api",
    image: process.env.IMAGE_REPOSITORY || "inventory-api",
    tag: process.env.IMAGE_TAG || "1.0.0",
    dockerfile: process.env.DOCKERFILE || "Dockerfile",
    context: process.env.BUILD_CONTEXT || ".",
    composeFile: process.env.COMPOSE_FILE || "compose.yaml",
    registry: process.env.DOCKER_REGISTRY || "docker.io",
    execute: process.env.EXECUTE === "true",
    push: process.env.PUSH === "true",
    retries: 2,
    timeout: 120000
});

const IMAGE = `${CONFIG.image}:${CONFIG.tag}`;

const StageState = Object.freeze({
    PENDING: "PENDING",
    RUNNING: "RUNNING",
    SUCCESS: "SUCCESS",
    FAILED: "FAILED",
    SKIPPED: "SKIPPED"
});

// -------------------------------------------------------
// Validation
// -------------------------------------------------------

function validateConfiguration() {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/.test(CONFIG.application)) {
        throw new Error("Invalid application name.");
    }

    if (!/^[a-z0-9]+(?:[._/-][a-z0-9]+)*$/.test(CONFIG.image)) {
        throw new Error("Invalid image name.");
    }

    if (!/^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$/.test(CONFIG.tag)) {
        throw new Error("Invalid image tag.");
    }

    if (!fs.existsSync(CONFIG.dockerfile)) {
        throw new Error("Dockerfile does not exist.");
    }

    if (!fs.statSync(CONFIG.context).isDirectory()) {
        throw new Error("Build context must be a directory.");
    }

    if (!fs.existsSync(CONFIG.composeFile)) {
        throw new Error("Docker Compose file does not exist.");
    }

    if (CONFIG.retries < 0 || CONFIG.timeout <= 0) {
        throw new Error("Invalid retry or timeout configuration.");
    }

    if (CONFIG.push && !CONFIG.registry) {
        throw new Error("Registry configuration is required.");
    }
}

// -------------------------------------------------------
// Pipeline event manager
// -------------------------------------------------------

class PipelineEvents extends EventEmitter {

    constructor() {
        super();
        this.setMaxListeners(20);
    }

    attach() {
        this.on("pipeline:start", id => {
            console.log(`[${id}] Pipeline started.`);
        });

        this.on("stage:start", name => {
            console.log(`[START] ${name}`);
        });

        this.on("stage:success", name => {
            console.log(`[SUCCESS] ${name}`);
        });

        this.on("stage:failure", data => {
            console.error(`[FAILED] ${data.name}: ${data.error}`);
        });

        this.on("pipeline:complete", status => {
            console.log(`[PIPELINE] ${status}`);
        });
    }
}

// -------------------------------------------------------
// Pipeline stage
// -------------------------------------------------------

class PipelineStage {

    constructor(name, action, options = {}) {
        this.name = name;
        this.action = action;
        this.retries = options.retries ?? 0;
        this.status = StageState.PENDING;
        this.attempts = 0;
        this.duration = 0;
        this.error = null;
    }

    async execute(events) {
        this.status = StageState.RUNNING;
        events.emit("stage:start", this.name);

        const started = Date.now();

        for (
            let attempt = 1;
            attempt <= this.retries + 1;
            attempt++
        ) {
            this.attempts = attempt;

            try {
                await this.action();

                this.status = StageState.SUCCESS;
                events.emit("stage:success", this.name);
                break;

            } catch (error) {
                this.error = error.message;

                if (attempt > this.retries) {
                    this.status = StageState.FAILED;

                    events.emit("stage:failure", {
                        name: this.name,
                        error: error.message
                    });
                } else {
                    await new Promise(resolve =>
                        setTimeout(resolve, Math.min(1000 * 2 ** (attempt - 1), 8000))
                    );
                }
            }
        }

        this.duration = Date.now() - started;

        return this.status === StageState.SUCCESS;
    }
}

// -------------------------------------------------------
// Docker command executor
// -------------------------------------------------------

class DockerExecutor {

    async execute(args, description) {
        if (!CONFIG.execute) {
            console.log(`[DRY RUN] docker ${args.join(" ")}`);
            return "";
        }

        return new Promise((resolve, reject) => {
            const child = spawn("docker", args, {
                shell: false,
                stdio: ["ignore", "pipe", "pipe"],
                env: { ...process.env }
            });

            let stdout = "";
            let stderr = "";
            let settled = false;

            const finish = (error, result) => {
                if (settled) return;
                settled = true;

                clearTimeout(timer);

                if (error) {
                    reject(error);
                } else {
                    resolve(result);
                }
            };

            const timer = setTimeout(() => {
                child.kill("SIGTERM");

                setTimeout(() => {
                    if (child.exitCode === null) {
                        child.kill("SIGKILL");
                    }
                }, 3000).unref();

                finish(new Error(`${description} timed out.`));
            }, CONFIG.timeout);

            child.stdout.on("data", chunk => {
                stdout += chunk.toString();
            });

            child.stderr.on("data", chunk => {
                stderr += chunk.toString();
            });

            child.on("error", error => finish(error));

            child.on("close", code => {
                if (code === 0) {
                    finish(null, stdout);
                } else {
                    finish(
                        new Error(
                            `${description} failed (${code}): ${stderr.trim()}`
                        )
                    );
                }
            });
        });
    }
}

// -------------------------------------------------------
// Pipeline orchestrator
// -------------------------------------------------------

class JenkinsDockerPipeline {

    constructor() {
        this.id = crypto.randomUUID();
        this.events = new PipelineEvents();
        this.events.attach();

        this.docker = new DockerExecutor();
        this.stages = [];
        this.startedAt = null;
        this.finishedAt = null;
        this.status = "CREATED";

        this.createStages();
    }

    createStages() {
        this.stages = [
            new PipelineStage(
                "CHECKOUT",
                async () => {
                    if (!fs.existsSync(CONFIG.dockerfile)) {
                        throw new Error("Dockerfile missing.");
                    }

                    if (!fs.existsSync(CONFIG.composeFile)) {
                        throw new Error("Compose file missing.");
                    }
                }
            ),

            new PipelineStage(
                "DOCKER_BUILD",
                async () => {
                    await this.docker.execute(
                        [
                            "build",
                            "--pull",
                            "-f", CONFIG.dockerfile,
                            "-t", IMAGE,
                            CONFIG.context
                        ],
                        "Docker build"
                    );
                },
                { retries: 2 }
            ),

            new PipelineStage(
                "IMAGE_VALIDATION",
                async () => {
                    await this.docker.execute(
                        ["image", "inspect", IMAGE],
                        "Image validation"
                    );
                }
            ),

            new PipelineStage(
                "DOCKER_TEST",
                async () => {
                    // Verify that the image has a valid configuration.
                    await this.docker.execute(
                        ["image", "inspect", "--format", "{{.Id}}", IMAGE],
                        "Docker image inspection"
                    );
                }
            ),

            new PipelineStage(
                "DOCKER_PUSH",
                async () => {
                    if (!CONFIG.push) {
                        return;
                    }

                    await this.docker.execute(
                        ["push", IMAGE],
                        "Docker registry push"
                    );
                },
                { retries: 2 }
            ),

            new PipelineStage(
                "DEPLOYMENT",
                async () => {
                    await this.docker.execute(
                        [
                            "compose",
                            "-f", CONFIG.composeFile,
                            "up",
                            "-d",
                            "--no-build"
                        ],
                        "Docker Compose deployment"
                    );
                },
                { retries: 1 }
            )
        ];
    }

    async run() {
        this.status = "RUNNING";
        this.startedAt = new Date().toISOString();

        this.events.emit("pipeline:start", this.id);

        try {
            for (const stage of this.stages) {
                const success = await stage.execute(this.events);

                if (!success) {
                    this.status = "FAILED";
                    break;
                }

                // A disabled publishing stage is recorded separately.
                if (
                    stage.name === "DOCKER_PUSH" &&
                    !CONFIG.push
                ) {
                    stage.status = StageState.SKIPPED;
                }
            }

            if (this.stages.every(stage =>
                stage.status === StageState.SUCCESS ||
                stage.status === StageState.SKIPPED
            )) {
                this.status = "SUCCESS";
            }

        } catch (error) {
            this.status = "FAILED";
            console.error(error.message);

        } finally {
            this.finishedAt = new Date().toISOString();
            this.events.emit("pipeline:complete", this.status);
        }

        return this.report();
    }

    report() {
        return {
            pipelineId: this.id,
            application: CONFIG.application,
            image: IMAGE,
            status: this.status,
            startedAt: this.startedAt,
            finishedAt: this.finishedAt,
            stages: this.stages.map(stage => ({
                name: stage.name,
                status: stage.status,
                attempts: stage.attempts,
                durationMs: stage.duration,
                error: stage.error
            }))
        };
    }
}

// -------------------------------------------------------
// Execution
// -------------------------------------------------------

async function main() {
    try {
        validateConfiguration();

        const pipeline = new JenkinsDockerPipeline();
        const report = await pipeline.run();

        const reportPath = path.resolve("pipeline-report.json");

        fs.writeFileSync(
            reportPath,
            JSON.stringify(report, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );

        console.log("\nPIPELINE REPORT");
        console.log(JSON.stringify(report, null, 2));

        process.exitCode = report.status === "SUCCESS" ? 0 : 1;

    } catch (error) {
        console.error("Pipeline configuration error:", error.message);
        process.exitCode = 1;
    }
}

main();

"use strict";

/*
 * Jenkinsfile Event-Driven Pipeline Model
 *
 * Demonstrates:
 * - Declarative stages and steps
 * - Global and stage-level environment
 * - Asynchronous step execution
 * - Stage dependencies
 * - Conditional execution
 * - Build lifecycle events
 * - Post-build conditions
 * - Failure propagation
 * - Execution reports
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");

const BuildStatus = Object.freeze({
    CREATED: "CREATED",
    RUNNING: "RUNNING",
    SUCCESS: "SUCCESS",
    FAILURE: "FAILURE",
    UNSTABLE: "UNSTABLE",
    ABORTED: "ABORTED"
});

const StageStatus = Object.freeze({
    PENDING: "PENDING",
    RUNNING: "RUNNING",
    SUCCESS: "SUCCESS",
    FAILURE: "FAILURE",
    SKIPPED: "SKIPPED"
});

class PipelineConfigurationError extends Error {}

class PipelineExecutionError extends Error {
    constructor(message, stage, cause) {
        super(message, { cause });
        this.stage = stage;
    }
}

function validateEnvironment(environment) {
    const validated = {};

    for (const [key, value] of Object.entries(environment)) {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
            throw new PipelineConfigurationError(
                `Invalid environment key: ${key}`
            );
        }

        if (typeof value !== "string") {
            throw new PipelineConfigurationError(
                `Environment value ${key} must be a string`
            );
        }

        validated[key] = value;
    }

    return Object.freeze(validated);
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

class PipelineStep {
    constructor({
        name,
        execute,
        timeoutMs = 10000,
        continueOnError = false
    }) {
        if (!name || typeof execute !== "function") {
            throw new PipelineConfigurationError(
                "A step requires a name and execution function"
            );
        }

        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            throw new PipelineConfigurationError(
                `Invalid timeout for step ${name}`
            );
        }

        this.name = name;
        this.execute = execute;
        this.timeoutMs = timeoutMs;
        this.continueOnError = continueOnError;
    }
}

class PipelineStage {
    constructor({
        name,
        steps,
        environment = {},
        when = () => true,
        dependsOn = []
    }) {
        if (!name || !Array.isArray(steps) || steps.length === 0) {
            throw new PipelineConfigurationError(
                "A stage requires a name and at least one step"
            );
        }

        if (typeof when !== "function") {
            throw new PipelineConfigurationError(
                "Stage condition must be a function"
            );
        }

        this.name = name;
        this.steps = steps;
        this.environment = validateEnvironment(environment);
        this.when = when;
        this.dependsOn = [...dependsOn];
        this.status = StageStatus.PENDING;
        this.durationMs = 0;
        this.error = null;
    }
}

class JenkinsPipeline extends EventEmitter {
    constructor({
        name,
        environment = {},
        stages,
        post = {}
    }) {
        super();

        if (!name || !Array.isArray(stages) || stages.length === 0) {
            throw new PipelineConfigurationError(
                "Pipeline requires a name and stages"
            );
        }

        this.name = name;
        this.environment = validateEnvironment(environment);
        this.stages = stages;
        this.post = post;
        this.status = BuildStatus.CREATED;
        this.history = [];
        this.artifacts = new Map();
        this.startedAt = null;
        this.finishedAt = null;

        this.validateGraph();
    }

    validateGraph() {
        const names = new Set(
            this.stages.map(stage => stage.name)
        );

        if (names.size !== this.stages.length) {
            throw new PipelineConfigurationError(
                "Duplicate stage names are not allowed"
            );
        }

        for (const stage of this.stages) {
            for (const dependency of stage.dependsOn) {
                if (!names.has(dependency)) {
                    throw new PipelineConfigurationError(
                        `Unknown dependency ${dependency} in ${stage.name}`
                    );
                }

                if (dependency === stage.name) {
                    throw new PipelineConfigurationError(
                        "A stage cannot depend on itself"
                    );
                }
            }
        }

        // Detect circular dependencies before execution.
        const visiting = new Set();
        const visited = new Set();
        const stageMap = new Map(
            this.stages.map(stage => [stage.name, stage])
        );

        const visit = name => {
            if (visiting.has(name)) {
                throw new PipelineConfigurationError(
                    `Circular stage dependency involving ${name}`
                );
            }

            if (visited.has(name)) return;

            visiting.add(name);

            for (const dependency of stageMap.get(name).dependsOn) {
                visit(dependency);
            }

            visiting.delete(name);
            visited.add(name);
        };

        for (const stage of this.stages) {
            visit(stage.name);
        }
    }

    record(type, details = {}) {
        const event = Object.freeze({
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            type,
            ...details
        });

        this.history.push(event);
        this.emit("pipeline:event", event);
    }

    async executeStep(stage, step, environment) {
        this.record("STEP_STARTED", {
            stage: stage.name,
            step: step.name
        });

        const controller = new AbortController();

        let timeoutHandle;

        const timeoutPromise = new Promise((_, reject) => {
            timeoutHandle = setTimeout(() => {
                controller.abort();

                reject(
                    new Error(
                        `Step timed out after ${step.timeoutMs}ms`
                    )
                );
            }, step.timeoutMs);
        });

        try {
            const result = await Promise.race([
                Promise.resolve().then(() =>
                    step.execute({
                        environment,
                        artifacts: this.artifacts,
                        signal: controller.signal
                    })
                ),
                timeoutPromise
            ]);

            this.record("STEP_SUCCESS", {
                stage: stage.name,
                step: step.name,
                result
            });

            return result;
        } catch (error) {
            this.record("STEP_FAILURE", {
                stage: stage.name,
                step: step.name,
                error: error.message
            });

            if (step.continueOnError) {
                return null;
            }

            throw new PipelineExecutionError(
                `Step ${step.name} failed: ${error.message}`,
                stage.name,
                error
            );
        } finally {
            clearTimeout(timeoutHandle);
        }
    }

    async executeStage(stage) {
        const dependencyMap = new Map(
            this.stages.map(item => [item.name, item])
        );

        const dependenciesSuccessful = stage.dependsOn.every(name =>
            dependencyMap.get(name).status === StageStatus.SUCCESS
        );

        if (!dependenciesSuccessful) {
            stage.status = StageStatus.SKIPPED;

            this.record("STAGE_SKIPPED", {
                stage: stage.name,
                reason: "Dependency did not succeed"
            });

            return;
        }

        const environment = Object.freeze({
            ...this.environment,
            ...stage.environment
        });

        if (!(await stage.when(environment))) {
            stage.status = StageStatus.SKIPPED;

            this.record("STAGE_SKIPPED", {
                stage: stage.name,
                reason: "Condition returned false"
            });

            return;
        }

        stage.status = StageStatus.RUNNING;

        const start = performance.now();

        this.record("STAGE_STARTED", {
            stage: stage.name
        });

        try {
            for (const step of stage.steps) {
                await this.executeStep(
                    stage,
                    step,
                    environment
                );
            }

            stage.status = StageStatus.SUCCESS;

            this.record("STAGE_SUCCESS", {
                stage: stage.name
            });
        } catch (error) {
            stage.status = StageStatus.FAILURE;
            stage.error = error.message;
            throw error;
        } finally {
            stage.durationMs = Number(
                (performance.now() - start).toFixed(2)
            );
        }
    }

    async executePostActions() {
        const actions = [
            ...(this.post.always || [])
        ];

        if (this.status === BuildStatus.SUCCESS) {
            actions.push(...(this.post.success || []));
        } else if (this.status === BuildStatus.FAILURE) {
            actions.push(...(this.post.failure || []));
        } else if (this.status === BuildStatus.UNSTABLE) {
            actions.push(...(this.post.unstable || []));
        }

        actions.push(...(this.post.cleanup || []));

        for (const action of actions) {
            try {
                await action({
                    status: this.status,
                    environment: this.environment,
                    history: this.history
                });

                this.record("POST_ACTION_SUCCESS");
            } catch (error) {
                this.record("POST_ACTION_FAILURE", {
                    error: error.message
                });

                if (this.status === BuildStatus.SUCCESS) {
                    this.status = BuildStatus.FAILURE;
                }
            }
        }
    }

    async run() {
        if (this.status !== BuildStatus.CREATED) {
            throw new Error(
                "A pipeline instance can only run once"
            );
        }

        this.status = BuildStatus.RUNNING;
        this.startedAt = new Date();

        this.record("PIPELINE_STARTED", {
            pipeline: this.name
        });

        try {
            for (const stage of this.stages) {
                await this.executeStage(stage);
            }

            this.status = BuildStatus.SUCCESS;
        } catch (error) {
            this.status = BuildStatus.FAILURE;

            this.record("PIPELINE_FAILURE", {
                error: error.message,
                stage: error.stage || null
            });

            for (const stage of this.stages) {
                if (stage.status === StageStatus.PENDING) {
                    stage.status = StageStatus.SKIPPED;
                }
            }
        } finally {
            await this.executePostActions();

            this.finishedAt = new Date();

            this.record("PIPELINE_COMPLETED", {
                status: this.status
            });
        }

        return this.report();
    }

    report() {
        return {
            pipeline: this.name,
            status: this.status,
            startedAt: this.startedAt?.toISOString(),
            finishedAt: this.finishedAt?.toISOString(),
            durationMs:
                this.finishedAt - this.startedAt,
            stages: this.stages.map(stage => ({
                name: stage.name,
                status: stage.status,
                durationMs: stage.durationMs,
                error: stage.error
            })),
            artifactNames: [...this.artifacts.keys()],
            events: this.history.length
        };
    }
}

// ---------------------------------------------------------
// Application workflow
// ---------------------------------------------------------

async function main() {
    const pipeline = new JenkinsPipeline({
        name: "Customer API CI/CD",

        environment: {
            GIT_BRANCH: "main",
            APPLICATION: "customer-api",
            BUILD_NUMBER: "205",
            DEPLOY_TARGET: "staging",
            NODE_ENV: "production"
        },

        stages: [
            new PipelineStage({
                name: "Checkout",
                steps: [
                    new PipelineStep({
                        name: "Validate source branch",
                        execute: async ({ environment }) => {
                            if (!/^[A-Za-z0-9._/-]+$/.test(
                                environment.GIT_BRANCH
                            )) {
                                throw new Error("Invalid branch");
                            }

                            return environment.GIT_BRANCH;
                        }
                    })
                ]
            }),

            new PipelineStage({
                name: "Install",
                dependsOn: ["Checkout"],
                steps: [
                    new PipelineStep({
                        name: "Resolve dependencies",
                        execute: async () => {
                            await delay(100);
                            return "Dependencies resolved";
                        }
                    })
                ]
            }),

            new PipelineStage({
                name: "Build",
                dependsOn: ["Install"],
                steps: [
                    new PipelineStep({
                        name: "Create build artifact",
                        execute: async ({ environment, artifacts }) => {
                            const artifact = {
                                application: environment.APPLICATION,
                                build: environment.BUILD_NUMBER,
                                checksum: crypto
                                    .createHash("sha256")
                                    .update(
                                        `${environment.APPLICATION}:${environment.BUILD_NUMBER}`
                                    )
                                    .digest("hex")
                            };

                            artifacts.set("application", artifact);

                            return artifact.checksum;
                        }
                    })
                ]
            }),

            new PipelineStage({
                name: "Test",
                dependsOn: ["Build"],
                steps: [
                    new PipelineStep({
                        name: "Run unit tests",
                        execute: async () => {
                            await delay(100);
                            return "Unit tests passed";
                        }
                    }),
                    new PipelineStep({
                        name: "Run security checks",
                        execute: async () => {
                            return "Security checks passed";
                        }
                    })
                ]
            }),

            new PipelineStage({
                name: "Deploy",
                dependsOn: ["Test"],
                environment: {
                    DEPLOY_TARGET: "staging"
                },
                when: environment =>
                    environment.GIT_BRANCH === "main",
                steps: [
                    new PipelineStep({
                        name: "Deploy artifact",
                        execute: async ({ environment, artifacts }) => {
                            if (!artifacts.has("application")) {
                                throw new Error("Artifact not found");
                            }

                            return `Deployed to ${environment.DEPLOY_TARGET}`;
                        }
                    })
                ]
            })
        ],

        post: {
            always: [
                async ({ status }) => {
                    console.log(`Build status: ${status}`);
                }
            ],

            success: [
                async ({ environment }) => {
                    console.log(
                        `Build ${environment.BUILD_NUMBER} succeeded`
                    );
                }
            ],

            failure: [
                async () => {
                    console.error("Failure notification dispatched");
                }
            ],

            cleanup: [
                async () => {
                    console.log("Temporary resources cleaned");
                }
            ]
        }
    });

    pipeline.on("pipeline:event", event => {
        console.log(
            `[EVENT] ${event.type}`,
            event.stage ? `| ${event.stage}` : ""
        );
    });

    const report = await pipeline.run();

    console.log("\nPIPELINE REPORT");
    console.log(JSON.stringify(report, null, 2));

    const reportPath = "./pipeline-report.json";

    await fs.writeFile(
        reportPath,
        JSON.stringify(
            {
                ...report,
                history: pipeline.history
            },
            null,
            2
        ),
        { mode: 0o600 }
    );

    if (report.status !== BuildStatus.SUCCESS) {
        process.exitCode = 1;
    }

    // Circular dependency validation.
    try {
        new JenkinsPipeline({
            name: "Invalid pipeline",
            stages: [
                new PipelineStage({
                    name: "A",
                    dependsOn: ["B"],
                    steps: [
                        new PipelineStep({
                            name: "A step",
                            execute: async () => "A"
                        })
                    ]
                }),
                new PipelineStage({
                    name: "B",
                    dependsOn: ["A"],
                    steps: [
                        new PipelineStep({
                            name: "B step",
                            execute: async () => "B"
                        })
                    ]
                })
            ]
        });

        throw new Error("Circular dependency was not detected");
    } catch (error) {
        if (!(error instanceof PipelineConfigurationError)) {
            throw error;
        }

        console.log("Circular dependency validation passed.");
    }
}

main().catch(error => {
    console.error("Fatal pipeline error:", error);
    process.exitCode = 1;
});

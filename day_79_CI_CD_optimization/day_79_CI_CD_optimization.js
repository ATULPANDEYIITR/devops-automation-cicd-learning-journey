"use strict";

/**
 * Event-driven CI/CD optimization engine.
 * Node.js 18+
 *
 * Features:
 * - Dependency-aware parallel scheduling
 * - Bounded concurrency
 * - Content-addressed caching
 * - Immutable artifact reuse
 * - Execution events
 * - Retry policies
 * - Failure propagation
 * - Pipeline metrics
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

const State = Object.freeze({
    PENDING: "PENDING",
    RUNNING: "RUNNING",
    SUCCESS: "SUCCESS",
    CACHED: "CACHED",
    FAILED: "FAILED",
    BLOCKED: "BLOCKED"
});

class PipelineError extends Error {
    constructor(message) {
        super(message);
        this.name = "PipelineError";
    }
}

function stableStringify(value) {
    if (Array.isArray(value)) {
        return `[${value.map(stableStringify).join(",")}]`;
    }

    if (value && typeof value === "object") {
        return `{${Object.keys(value)
            .sort()
            .map(key =>
                `${JSON.stringify(key)}:${stableStringify(value[key])}`
            )
            .join(",")}}`;
    }

    return JSON.stringify(value);
}

function digest(value) {
    return crypto
        .createHash("sha256")
        .update(value)
        .digest("hex");
}

class ArtifactStore {
    constructor() {
        this.artifacts = new Map();
        this.hits = 0;
        this.misses = 0;
    }

    get(key) {
        const artifact = this.artifacts.get(key);

        if (artifact) {
            this.hits++;
            return artifact;
        }

        this.misses++;
        return null;
    }

    put(key, artifact) {
        if (!Object.isFrozen(artifact)) {
            throw new PipelineError("Artifacts must be immutable");
        }

        this.artifacts.set(key, artifact);
    }

    statistics() {
        return {
            entries: this.artifacts.size,
            hits: this.hits,
            misses: this.misses
        };
    }
}

class Semaphore {
    constructor(limit) {
        if (!Number.isInteger(limit) || limit < 1) {
            throw new RangeError("Concurrency must be positive");
        }

        this.limit = limit;
        this.active = 0;
        this.queue = [];
    }

    async acquire() {
        if (this.active < this.limit) {
            this.active++;
            return;
        }

        await new Promise(resolve => this.queue.push(resolve));
        this.active++;
    }

    release() {
        if (this.active <= 0) {
            throw new PipelineError("Invalid semaphore release");
        }

        this.active--;

        const next = this.queue.shift();

        if (next) {
            next();
        }
    }
}

class Pipeline {
    constructor(stages, options = {}) {
        this.stages = new Map();
        this.store = options.store || new ArtifactStore();
        this.events = new EventEmitter();

        this.semaphore = new Semaphore(options.concurrency || 4);
        this.maxRetries = options.maxRetries ?? 1;

        if (!Number.isInteger(this.maxRetries) || this.maxRetries < 0) {
            throw new RangeError("Invalid retry count");
        }

        this.results = new Map();
        this._validate(stages);
    }

    _validate(stages) {
        for (const stage of stages) {
            if (
                !stage.id ||
                typeof stage.id !== "string" ||
                typeof stage.run !== "function"
            ) {
                throw new PipelineError("Invalid stage definition");
            }

            if (this.stages.has(stage.id)) {
                throw new PipelineError(
                    `Duplicate stage: ${stage.id}`
                );
            }

            this.stages.set(stage.id, {
                ...stage,
                dependencies: [...(stage.dependencies || [])],
                inputs: { ...(stage.inputs || {}) }
            });
        }

        for (const stage of this.stages.values()) {
            for (const dependency of stage.dependencies) {
                if (!this.stages.has(dependency)) {
                    throw new PipelineError(
                        `Unknown dependency: ${dependency}`
                    );
                }

                if (dependency === stage.id) {
                    throw new PipelineError("Self-dependency detected");
                }
            }
        }

        const visiting = new Set();
        const visited = new Set();

        const visit = id => {
            if (visiting.has(id)) {
                throw new PipelineError("Dependency cycle detected");
            }

            if (visited.has(id)) return;

            visiting.add(id);

            for (const dependency of this.stages.get(id).dependencies) {
                visit(dependency);
            }

            visiting.delete(id);
            visited.add(id);
        };

        for (const id of this.stages.keys()) {
            visit(id);
        }
    }

    _cacheKey(stage) {
        const dependencies = {};

        for (const id of [...stage.dependencies].sort()) {
            const result = this.results.get(id);

            if (!result?.artifact) {
                throw new PipelineError(
                    `Dependency artifact unavailable: ${id}`
                );
            }

            dependencies[id] = result.artifact.digest;
        }

        return digest(stableStringify({
            schema: 1,
            id: stage.id,
            command: stage.command || "",
            inputs: stage.inputs,
            dependencies
        }));
    }

    async _execute(stage) {
        const start = performance.now();
        const key = this._cacheKey(stage);

        const cached = this.store.get(key);

        if (cached) {
            const result = {
                state: State.CACHED,
                artifact: cached,
                duration: performance.now() - start
            };

            this.events.emit("cache-hit", {
                stage: stage.id,
                digest: cached.digest
            });

            return result;
        }

        await this.semaphore.acquire();

        try {
            let output;
            let attempt = 0;

            while (true) {
                try {
                    this.events.emit("stage-started", {
                        stage: stage.id,
                        attempt: attempt + 1
                    });

                    output = await stage.run({
                        dependencies: stage.dependencies.map(
                            id => this.results.get(id).artifact
                        ),
                        inputs: Object.freeze({ ...stage.inputs }),
                        attempt: attempt + 1
                    });

                    break;
                } catch (error) {
                    if (attempt >= this.maxRetries) {
                        throw error;
                    }

                    attempt++;

                    this.events.emit("retry", {
                        stage: stage.id,
                        attempt,
                        error: error.message
                    });
                }
            }

            if (
                typeof output !== "string" &&
                !Buffer.isBuffer(output)
            ) {
                throw new PipelineError(
                    `Invalid output from stage ${stage.id}`
                );
            }

            const content = Buffer.isBuffer(output)
                ? output.toString("base64")
                : output;

            const artifact = Object.freeze({
                name: stage.id,
                content,
                digest: digest(content)
            });

            this.store.put(key, artifact);

            return {
                state: State.SUCCESS,
                artifact,
                duration: performance.now() - start
            };

        } catch (error) {
            this.events.emit("stage-failed", {
                stage: stage.id,
                error: error.message
            });

            return {
                state: State.FAILED,
                artifact: null,
                duration: performance.now() - start,
                error: error.message
            };
        } finally {
            this.semaphore.release();
        }
    }

    async run() {
        this.results.clear();

        for (const id of this.stages.keys()) {
            this.results.set(id, {
                state: State.PENDING,
                artifact: null
            });
        }

        const pending = new Set(this.stages.keys());
        const running = new Map();

        while (pending.size || running.size) {
            let scheduled = false;

            for (const id of [...pending]) {
                const stage = this.stages.get(id);

                const dependencies = stage.dependencies.map(
                    dependency => this.results.get(dependency)
                );

                if (dependencies.some(result =>
                    result.state === State.FAILED ||
                    result.state === State.BLOCKED
                )) {
                    this.results.set(id, {
                        state: State.BLOCKED,
                        error: "Dependency failure"
                    });

                    pending.delete(id);
                    scheduled = true;

                    this.events.emit("stage-blocked", { stage: id });
                    continue;
                }

                if (!dependencies.every(result =>
                    result.state === State.SUCCESS ||
                    result.state === State.CACHED
                )) {
                    continue;
                }

                pending.delete(id);

                this.results.set(id, { state: State.RUNNING });

                const promise = this._execute(stage).then(result => {
                    this.results.set(id, result);

                    this.events.emit("stage-completed", {
                        stage: id,
                        state: result.state,
                        duration: result.duration
                    });
                });

                running.set(id, promise);
                scheduled = true;

                if (running.size >= this.semaphore.limit) {
                    break;
                }
            }

            if (running.size) {
                const completed = await Promise.race(
                    [...running.entries()].map(
                        async ([id, promise]) => {
                            await promise;
                            return id;
                        }
                    )
                );

                running.delete(completed);
                scheduled = true;
            }

            if (!scheduled && pending.size) {
                throw new PipelineError(
                    "Scheduler deadlock or invalid dependency state"
                );
            }
        }

        const report = [...this.results.entries()].map(
            ([stage, result]) => ({
                stage,
                state: result.state,
                digest: result.artifact?.digest || null,
                error: result.error || null,
                duration: result.duration || 0
            })
        );

        return {
            success: report.every(item =>
                item.state === State.SUCCESS ||
                item.state === State.CACHED
            ),
            stages: report,
            cache: this.store.statistics()
        };
    }
}

function createStages(version) {
    const task = (name, output) => async () => {
        await new Promise(resolve => setTimeout(resolve, 100));
        console.log(`Executing ${name}`);
        return output;
    };

    return [
        {
            id: "checkout",
            command: "git checkout",
            inputs: { version },
            run: task("checkout", `source-${version}`)
        },
        {
            id: "compile",
            dependencies: ["checkout"],
            command: "compile release binary",
            inputs: { compiler: "clang-19" },
            run: task("compile", "binary-v1")
        },
        {
            id: "lint",
            dependencies: ["checkout"],
            command: "static analysis",
            inputs: { rules: "strict" },
            run: task("lint", "lint-passed")
        },
        {
            id: "unit-tests",
            dependencies: ["compile"],
            command: "run unit tests",
            inputs: { suite: "unit-v1" },
            run: task("unit tests", "unit-passed")
        },
        {
            id: "integration-tests",
            dependencies: ["compile"],
            command: "run integration tests",
            inputs: { suite: "integration-v1" },
            run: task("integration tests", "integration-passed")
        },
        {
            id: "security",
            dependencies: ["checkout"],
            command: "security scan",
            inputs: { scanner: "v1" },
            run: task("security scan", "security-passed")
        },
        {
            id: "package",
            dependencies: [
                "unit-tests",
                "integration-tests",
                "lint",
                "security"
            ],
            command: "package application",
            inputs: { format: "tar" },
            run: task("package", "release-package-v1")
        },
        {
            id: "deploy",
            dependencies: ["package"],
            command: "deploy staging",
            inputs: { environment: "staging" },
            run: task("deployment", "deployment-success")
        }
    ];
}

async function main() {
    const store = new ArtifactStore();

    const pipeline = new Pipeline(
        createStages("commit-100"),
        {
            concurrency: 4,
            maxRetries: 1,
            store
        }
    );

    pipeline.events.on("stage-failed", event => {
        console.error("FAILED:", event);
    });

    pipeline.events.on("stage-blocked", event => {
        console.warn("BLOCKED:", event.stage);
    });

    pipeline.events.on("cache-hit", event => {
        console.log("CACHE HIT:", event.stage);
    });

    console.log("\nFIRST EXECUTION");
    const first = await pipeline.run();
    console.table(first.stages);

    if (!first.success) {
        throw new PipelineError("Initial pipeline failed");
    }

    console.log("\nSECOND EXECUTION");
    const second = await pipeline.run();
    console.table(second.stages);

    if (!second.success) {
        throw new PipelineError("Cached pipeline failed");
    }

    if (!second.stages.every(
        stage => stage.state === State.CACHED
    )) {
        throw new PipelineError("Expected complete cache reuse");
    }

    console.log("\nCACHE STATISTICS");
    console.log(second.cache);

    console.log("\nCI/CD optimization validation passed.");
}

main().catch(error => {
    console.error("Pipeline error:", error);
    process.exitCode = 1;
});

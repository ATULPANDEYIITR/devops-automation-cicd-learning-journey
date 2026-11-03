'use strict';

/*
 * Jenkins Pipeline execution model for Node.js.
 *
 * Declarative mode:
 *   Executes a validated stage dependency graph.
 *
 * Scripted mode:
 *   Executes stages through imperative asynchronous control flow.
 *
 * This program is a local model. It does not connect to Jenkins or run
 * operating-system commands on Jenkins agents.
 */

const { EventEmitter } = require('node:events');

class PipelineError extends Error {
    constructor(message, cause) {
        super(message, { cause });
        this.name = 'PipelineError';
    }
}

const StageState = Object.freeze({
    PENDING: 'PENDING',
    RUNNING: 'RUNNING',
    SUCCESS: 'SUCCESS',
    FAILED: 'FAILED',
    SKIPPED: 'SKIPPED',
    UNSTABLE: 'UNSTABLE'
});

const BuildState = Object.freeze({
    SUCCESS: 'SUCCESS',
    FAILURE: 'FAILURE',
    UNSTABLE: 'UNSTABLE'
});

class CredentialStore {
    constructor(entries = {}) {
        this.entries = new Map(Object.entries(entries));
    }

    get(id) {
        if (!this.entries.has(id)) {
            throw new PipelineError(`Credential '${id}' is unavailable`);
        }
        return this.entries.get(id);
    }

    mask(message) {
        let safe = String(message);
        const secrets = [...this.entries.values()]
            .filter(value => typeof value === 'string' && value.length > 0)
            .sort((a, b) => b.length - a.length);

        for (const secret of secrets) {
            safe = safe.split(secret).join('****');
        }
        return safe;
    }
}

class PipelineEngine extends EventEmitter {
    constructor(options = {}) {
        super();

        this.maxConcurrency = options.maxConcurrency ?? 3;
        if (!Number.isInteger(this.maxConcurrency) || this.maxConcurrency < 1) {
            throw new TypeError('maxConcurrency must be a positive integer');
        }

        this.credentials = new CredentialStore(options.credentials ?? {});
    }

    createContext(parameters = {}) {
        const artifacts = new Map();

        return {
            parameters: Object.freeze({ ...parameters }),
            artifacts,
            credential: id => this.credentials.get(id),
            publishArtifact: (name, metadata = {}) => {
                if (typeof name !== 'string' || name.trim() === '') {
                    throw new TypeError('Artifact name cannot be empty');
                }
                if (artifacts.has(name)) {
                    throw new PipelineError(`Artifact '${name}' already exists`);
                }
                artifacts.set(name, Object.freeze({ ...metadata }));
            },
            log: message => {
                const safe = this.credentials.mask(message);
                this.emit('log', safe);
                process.stdout.write(`${safe}\n`);
            }
        };
    }

    validateStage(stage) {
        if (!stage || typeof stage !== 'object') {
            throw new TypeError('Each stage must be an object');
        }
        if (typeof stage.name !== 'string' || stage.name.trim() === '') {
            throw new TypeError('Stage name is required');
        }
        if (typeof stage.run !== 'function') {
            throw new TypeError(`Stage '${stage.name}' must define run()`);
        }

        const retries = stage.retries ?? 0;
        if (!Number.isInteger(retries) || retries < 0) {
            throw new TypeError(
                `Stage '${stage.name}' has an invalid retry count`
            );
        }

        const dependencies = stage.needs ?? [];
        if (!Array.isArray(dependencies) ||
            dependencies.some(name => typeof name !== 'string')) {
            throw new TypeError(
                `Stage '${stage.name}' has invalid dependencies`
            );
        }

        return {
            ...stage,
            needs: [...dependencies],
            retries,
            agent: stage.agent ?? 'any',
            continueOnFailure: stage.continueOnFailure ?? false
        };
    }

    validateGraph(stages) {
        if (!Array.isArray(stages) || stages.length === 0) {
            throw new PipelineError('A pipeline must contain stages');
        }

        const normalized = stages.map(stage => this.validateStage(stage));
        const byName = new Map();

        for (const stage of normalized) {
            if (byName.has(stage.name)) {
                throw new PipelineError(
                    `Duplicate stage name '${stage.name}'`
                );
            }
            byName.set(stage.name, stage);
        }

        for (const stage of normalized) {
            for (const dependency of stage.needs) {
                if (!byName.has(dependency)) {
                    throw new PipelineError(
                        `Stage '${stage.name}' depends on unknown stage '${dependency}'`
                    );
                }
                if (dependency === stage.name) {
                    throw new PipelineError(
                        `Stage '${stage.name}' cannot depend on itself`
                    );
                }
            }
        }

        // Kahn's algorithm detects dependency cycles before execution.
        const indegree = new Map(
            normalized.map(stage => [stage.name, stage.needs.length])
        );
        const dependents = new Map(
            normalized.map(stage => [stage.name, []])
        );

        for (const stage of normalized) {
            for (const dependency of stage.needs) {
                dependents.get(dependency).push(stage.name);
            }
        }

        const queue = normalized
            .filter(stage => indegree.get(stage.name) === 0)
            .map(stage => stage.name);

        let visited = 0;

        while (queue.length > 0) {
            const name = queue.shift();
            visited += 1;

            for (const dependent of dependents.get(name)) {
                const remaining = indegree.get(dependent) - 1;
                indegree.set(dependent, remaining);
                if (remaining === 0) {
                    queue.push(dependent);
                }
            }
        }

        if (visited !== normalized.length) {
            throw new PipelineError('Pipeline contains a dependency cycle');
        }

        return normalized;
    }

    async mapLimit(items, limit, callback) {
        const output = new Array(items.length);
        let nextIndex = 0;

        const workers = Array.from(
            { length: Math.min(limit, items.length) },
            async () => {
                while (true) {
                    const index = nextIndex++;
                    if (index >= items.length) {
                        return;
                    }
                    output[index] = await callback(items[index], index);
                }
            }
        );

        await Promise.all(workers);
        return output;
    }

    async executeStage(stage, context, records) {
        const startedAt = Date.now();

        if (stage.when !== undefined) {
            if (typeof stage.when !== 'function') {
                throw new TypeError(
                    `Stage '${stage.name}' has a non-function condition`
                );
            }

            let condition;
            try {
                condition = Boolean(stage.when(context));
            } catch (error) {
                const record = {
                    name: stage.name,
                    state: StageState.FAILED,
                    attempts: 0,
                    error: String(error),
                    durationMs: Date.now() - startedAt
                };
                records.set(stage.name, record);
                this.emit('stage:failed', record);
                return record;
            }

            if (!condition) {
                const record = {
                    name: stage.name,
                    state: StageState.SKIPPED,
                    attempts: 0,
                    error: null,
                    durationMs: Date.now() - startedAt
                };
                records.set(stage.name, record);
                this.emit('stage:skipped', record);
                return record;
            }
        }

        this.emit('stage:started', {
            name: stage.name,
            agent: stage.agent
        });
        context.log(`[${stage.name}] started on agent '${stage.agent}'`);

        let lastError = null;

        for (let attempt = 1; attempt <= stage.retries + 1; attempt++) {
            try {
                await stage.run(context);
                const record = {
                    name: stage.name,
                    state: StageState.SUCCESS,
                    attempts: attempt,
                    error: null,
                    durationMs: Date.now() - startedAt
                };
                records.set(stage.name, record);
                this.emit('stage:completed', record);
                return record;
            } catch (error) {
                lastError = error;
                this.emit('stage:retry', {
                    name: stage.name,
                    attempt,
                    error: String(error)
                });

                if (attempt <= stage.retries) {
                    context.log(
                        `[${stage.name}] retrying after attempt ${attempt}`
                    );
                }
            }
        }

        const state = stage.continueOnFailure
            ? StageState.UNSTABLE
            : StageState.FAILED;

        const record = {
            name: stage.name,
            state,
            attempts: stage.retries + 1,
            error: String(lastError),
            durationMs: Date.now() - startedAt
        };

        records.set(stage.name, record);
        this.emit(
            state === StageState.FAILED ? 'stage:failed' : 'stage:unstable',
            record
        );
        return record;
    }

    async runDeclarative(definition) {
        if (!definition || typeof definition.name !== 'string') {
            throw new TypeError('Pipeline definition requires a name');
        }

        const stages = this.validateGraph(definition.stages);
        const context = this.createContext(definition.parameters ?? {});
        const records = new Map();
        const pending = new Set(stages.map(stage => stage.name));
        const byName = new Map(stages.map(stage => [stage.name, stage]));

        context.log(`Starting declarative pipeline '${definition.name}'`);

        while (pending.size > 0) {
            const ready = stages.filter(stage => {
                if (!pending.has(stage.name)) {
                    return false;
                }
                return stage.needs.every(name => records.has(name));
            });

            if (ready.length === 0) {
                throw new PipelineError(
                    'No executable stage remains; dependency state is inconsistent'
                );
            }

            const runnable = [];

            for (const stage of ready) {
                const blocked = stage.needs.some(dependency => {
                    const state = records.get(dependency).state;
                    return state !== StageState.SUCCESS;
                });

                if (blocked) {
                    const record = {
                        name: stage.name,
                        state: StageState.SKIPPED,
                        attempts: 0,
                        error: 'A dependency did not succeed',
                        durationMs: 0
                    };
                    records.set(stage.name, record);
                    this.emit('stage:skipped', record);
                } else {
                    runnable.push(stage);
                }
                pending.delete(stage.name);
            }

            await this.mapLimit(
                runnable,
                this.maxConcurrency,
                stage => this.executeStage(stage, context, records)
            );
        }

        const result = this.makeBuildResult(
            definition.name,
            records,
            context
        );

        await this.runPostActions(definition.post ?? {}, result, context);
        this.emit('build:completed', result);
        return result;
    }

    async runScripted(name, script, parameters = {}, post = {}) {
        if (typeof script !== 'function') {
            throw new TypeError('Scripted pipeline requires a function');
        }

        const context = this.createContext(parameters);
        const records = new Map();
        let scriptError = null;

        const api = {
            stage: async stageDefinition => {
                const stage = this.validateStage({
                    ...stageDefinition,
                    needs: []
                });

                if (records.has(stage.name)) {
                    throw new PipelineError(
                        `Scripted stage '${stage.name}' was already executed`
                    );
                }

                const record = await this.executeStage(
                    stage,
                    context,
                    records
                );

                if (record.state === StageState.FAILED) {
                    throw new PipelineError(
                        `Scripted stage '${stage.name}' failed`,
                        new Error(record.error)
                    );
                }
                return record;
            },

            parallel: async branches => {
                if (!branches || typeof branches !== 'object') {
                    throw new TypeError('Parallel branches must be an object');
                }

                const entries = Object.entries(branches);
                if (entries.length === 0) {
                    throw new PipelineError(
                        'Parallel block must contain a branch'
                    );
                }

                await Promise.all(
                    entries.map(async ([branchName, branch]) => {
                        if (typeof branch !== 'function') {
                            throw new TypeError(
                                `Parallel branch '${branchName}' must be a function`
                            );
                        }
                        await branch();
                    })
                );
            },

            node: async (agent, callback) => {
                if (typeof agent !== 'string' || agent.trim() === '') {
                    throw new TypeError('Agent label is required');
                }
                if (typeof callback !== 'function') {
                    throw new TypeError('Node block requires a function');
                }

                context.log(`[node] allocated '${agent}'`);
                try {
                    return await callback();
                } finally {
                    context.log(`[node] released '${agent}'`);
                }
            },

            context
        };

        context.log(`Starting scripted pipeline '${name}'`);

        try {
            await script(api);
        } catch (error) {
            scriptError = error;
            context.log(`[script] failed: ${error}`);
        }

        const result = this.makeBuildResult(
            name,
            records,
            context,
            scriptError
        );

        await this.runPostActions(post, result, context);
        this.emit('build:completed', result);
        return result;
    }

    makeBuildResult(name, records, context, scriptError = null) {
        const stages = [...records.values()];
        let state = BuildState.SUCCESS;

        if (scriptError ||
            stages.some(stage => stage.state === StageState.FAILED)) {
            state = BuildState.FAILURE;
        } else if (
            stages.some(stage => stage.state === StageState.UNSTABLE)
        ) {
            state = BuildState.UNSTABLE;
        }

        return {
            name,
            state,
            stages,
            artifacts: [...context.artifacts.keys()].sort(),
            scriptError: scriptError ? String(scriptError) : null
        };
    }

    async runPostActions(post, result, context) {
        const allowed = new Set([
            'always',
            'success',
            'failure',
            'unstable'
        ]);

        for (const condition of Object.keys(post)) {
            if (!allowed.has(condition)) {
                throw new PipelineError(
                    `Unsupported post condition '${condition}'`
                );
            }
            if (typeof post[condition] !== 'function') {
                throw new TypeError(
                    `Post action '${condition}' must be a function`
                );
            }
        }

        const selected = ['always', result.state.toLowerCase()];

        for (const condition of selected) {
            if (typeof post[condition] !== 'function') {
                continue;
            }
            try {
                await post[condition](context, result);
            } catch (error) {
                context.log(
                    `[post:${condition}] failed: ${String(error)}`
                );
            }
        }
    }
}

function createBuildStages() {
    return [
        {
            name: 'Checkout',
            agent: 'linux',
            needs: [],
            run: async context => {
                context.log('Checking out payments-service');
            }
        },
        {
            name: 'Compile',
            agent: 'linux-docker',
            needs: ['Checkout'],
            run: async context => {
                context.publishArtifact('application.jar', {
                    format: 'jar',
                    version: '2.4.0'
                });
                context.log('Application compiled');
            }
        },
        {
            name: 'Unit Tests',
            agent: 'linux',
            needs: ['Compile'],
            retries: 1,
            run: async context => {
                context.log('Unit tests passed');
            }
        },
        {
            name: 'Integration Tests',
            agent: 'linux-docker',
            needs: ['Compile'],
            run: async context => {
                context.log('Integration tests passed');
            }
        },
        {
            name: 'Package',
            agent: 'linux-docker',
            needs: ['Unit Tests', 'Integration Tests'],
            run: async context => {
                if (!context.artifacts.has('application.jar')) {
                    throw new PipelineError('Compiled artifact is missing');
                }
                context.publishArtifact('payments-release.tar.gz', {
                    format: 'tar.gz',
                    version: '2.4.0'
                });
                context.log('Release package created');
            }
        },
        {
            name: 'Production Deployment',
            agent: 'linux-deploy',
            needs: ['Package'],
            when: context =>
                context.parameters.branch === 'main' &&
                context.parameters.deploymentApproved === true,
            run: async context => {
                const token = context.credential('production-deploy');
                context.log(`Deployment credential length: ${token.length}`);
                context.log('Production deployment completed');
            }
        }
    ];
}

async function main() {
    const engine = new PipelineEngine({
        maxConcurrency: 2,
        credentials: {
            'production-deploy': 'deployment-secret-42'
        }
    });

    engine.on('stage:retry', event => {
        process.stdout.write(
            `[event] retry ${event.name}, attempt ${event.attempt}\n`
        );
    });

    engine.on('build:completed', result => {
        process.stdout.write(
            `[event] build ${result.name}: ${result.state}\n`
        );
    });

    const declarativeResult = await engine.runDeclarative({
        name: 'payments-declarative',
        parameters: {
            branch: 'main',
            deploymentApproved: true
        },
        stages: createBuildStages(),
        post: {
            always: async context => {
                context.log('Declarative cleanup completed');
            },
            success: async context => {
                context.log('Declarative build is successful');
            }
        }
    });

    process.stdout.write(
        `Declarative result: ${JSON.stringify(declarativeResult, null, 2)}\n`
    );

    const scriptedResult = await engine.runScripted(
        'payments-scripted',
        async pipeline => {
            await pipeline.node('linux-docker', async () => {
                await pipeline.stage({
                    name: 'Checkout',
                    run: async context => {
                        context.log('Scripted checkout completed');
                    }
                });

                await pipeline.stage({
                    name: 'Build',
                    run: async context => {
                        context.publishArtifact('scripted-app.jar', {
                            version: '2.4.0'
                        });
                    }
                });

                await pipeline.parallel({
                    unit: async () => {
                        await pipeline.stage({
                            name: 'Unit Tests',
                            run: async context => {
                                context.log('Scripted unit tests passed');
                            }
                        });
                    },
                    integration: async () => {
                        await pipeline.stage({
                            name: 'Integration Tests',
                            run: async context => {
                                context.log('Scripted integration tests passed');
                            }
                        });
                    }
                });

                await pipeline.stage({
                    name: 'Package',
                    run: async context => {
                        context.publishArtifact('scripted-release.tar.gz');
                    }
                });
            });
        },
        { branch: 'feature/metrics' },
        {
            always: async context => {
                context.log('Scripted cleanup completed');
            }
        }
    );

    process.stdout.write(
        `Scripted result: ${JSON.stringify(scriptedResult, null, 2)}\n`
    );
}

if (require.main === module) {
    main().catch(error => {
        process.stderr.write(`${error.stack ?? error}\n`);
        process.exitCode = 1;
    });
}

module.exports = {
    PipelineEngine,
    PipelineError,
    StageState,
    BuildState
};

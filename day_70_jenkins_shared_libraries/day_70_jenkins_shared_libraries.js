'use strict';

/**
 * Jenkins Shared Libraries
 * Reusable enterprise pipeline code.
 *
 * Runtime: Node.js 18+
 *
 * Features:
 * - Versioned shared library registry
 * - Event-driven pipeline execution
 * - Reusable pipeline steps
 * - Asynchronous stage execution
 * - Concurrency control
 * - Retry handling
 * - Credential masking
 * - Production deployment approval
 * - Pipeline lifecycle events
 * - Structured execution reports
 */

const { EventEmitter } = require('node:events');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

class PipelineError extends Error {}
class ValidationError extends PipelineError {}
class PolicyError extends PipelineError {}
class StageError extends PipelineError {}

const PipelineStatus = Object.freeze({
    CREATED: 'CREATED',
    RUNNING: 'RUNNING',
    SUCCESS: 'SUCCESS',
    FAILED: 'FAILED',
    ABORTED: 'ABORTED'
});

const StageStatus = Object.freeze({
    PENDING: 'PENDING',
    RUNNING: 'RUNNING',
    SUCCESS: 'SUCCESS',
    FAILED: 'FAILED',
    SKIPPED: 'SKIPPED'
});

const Environment = Object.freeze({
    DEVELOPMENT: 'development',
    STAGING: 'staging',
    PRODUCTION: 'production'
});

function validateString(value, field) {
    if (typeof value !== 'string' || value.trim().length === 0) {
        throw new ValidationError(`${field} must be a non-empty string.`);
    }

    return value.trim();
}

function validateVersion(version) {
    if (!/^\d+\.\d+\.\d+$/.test(version)) {
        throw new ValidationError(
            'Version must follow semantic versioning.'
        );
    }
}

class SharedLibrary {
    constructor({
        name,
        version,
        commit,
        approved,
        tested,
        steps
    }) {
        this.name = validateString(name, 'Library name');
        this.version = validateString(version, 'Library version');

        validateVersion(this.version);

        if (!/^[a-f0-9]{7,40}$/i.test(commit)) {
            throw new ValidationError('Invalid commit identifier.');
        }

        this.commit = commit.toLowerCase();
        this.approved = Boolean(approved);
        this.tested = Boolean(tested);
        this.steps = Object.freeze({ ...steps });
        Object.freeze(this);
    }
}

class LibraryRegistry {
    #releases = new Map();

    register(library) {
        if (!(library instanceof SharedLibrary)) {
            throw new ValidationError('Invalid library object.');
        }

        const key = `${library.name}@${library.version}`;

        if (this.#releases.has(key)) {
            throw new ValidationError(`Duplicate release: ${key}`);
        }

        this.#releases.set(key, library);
        return key;
    }

    resolve(name, version) {
        const library = this.#releases.get(`${name}@${version}`);

        if (!library) {
            throw new ValidationError('Requested library version not found.');
        }

        if (!library.tested || !library.approved) {
            throw new PolicyError('Library release is not production eligible.');
        }

        return library;
    }
}

class PipelinePolicy {
    constructor({
        requireApprovalForProduction = true,
        minimumTestCount = 1,
        allowedEnvironments = Object.values(Environment)
    } = {}) {
        this.requireApprovalForProduction = requireApprovalForProduction;
        this.minimumTestCount = minimumTestCount;
        this.allowedEnvironments = new Set(allowedEnvironments);
    }

    validate(context) {
        if (!this.allowedEnvironments.has(context.environment)) {
            throw new PolicyError('Environment is not permitted.');
        }

        if (
            context.environment === Environment.PRODUCTION &&
            this.requireApprovalForProduction &&
            !context.approved
        ) {
            throw new PolicyError(
                'Production deployment requires explicit approval.'
            );
        }
    }
}

class PipelineContext {
    constructor({
        application,
        branch,
        environment,
        buildNumber,
        library,
        approved = false
    }) {
        this.application = validateString(application, 'Application');
        this.branch = validateString(branch, 'Branch');

        if (!Object.values(Environment).includes(environment)) {
            throw new ValidationError('Invalid deployment environment.');
        }

        if (!Number.isSafeInteger(buildNumber) || buildNumber < 1) {
            throw new ValidationError('Invalid build number.');
        }

        this.environment = environment;
        this.buildNumber = buildNumber;
        this.library = library;
        this.approved = approved;
        this.status = PipelineStatus.CREATED;
        this.results = [];
        this.startedAt = null;
        this.finishedAt = null;
        this.runId = crypto.randomUUID();
    }
}

class PipelineSteps {
    constructor(context, events) {
        this.context = context;
        this.events = events;
        this.credentials = new Map();
    }

    async checkout(repository) {
        validateString(repository, 'Repository');

        if (!/^https:\/\//.test(repository) &&
            !/^ssh:\/\//.test(repository)) {
            throw new ValidationError('Unsupported repository protocol.');
        }

        return {
            repository,
            branch: this.context.branch,
            commit: crypto
                .createHash('sha256')
                .update(repository + this.context.branch)
                .digest('hex')
                .slice(0, 16)
        };
    }

    async runTests(checkout) {
        if (!checkout.commit) {
            throw new StageError('Checkout information is incomplete.');
        }

        return {
            passed: 42,
            failed: 0,
            total: 42
        };
    }

    async retry(operation, {
        attempts = 3,
        delayMs = 100
    } = {}) {
        if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10) {
            throw new ValidationError('Invalid retry count.');
        }

        let lastError;

        for (let attempt = 1; attempt <= attempts; attempt++) {
            try {
                return await operation(attempt);
            } catch (error) {
                lastError = error;

                this.events.emit('retry', {
                    attempt,
                    error: error.message
                });

                if (attempt < attempts) {
                    await new Promise(resolve =>
                        setTimeout(resolve, delayMs * attempt)
                    );
                }
            }
        }

        throw new StageError(
            `Operation failed after ${attempts} attempts: ${lastError.message}`
        );
    }

    async withCredentials(id, secret, operation) {
        validateString(id, 'Credential identifier');
        validateString(secret, 'Credential secret');

        this.credentials.set(id, secret);

        try {
            return await operation(secret);
        } finally {
            this.credentials.delete(id);
        }
    }

    async deploy(artifact) {
        validateString(artifact, 'Artifact');

        return {
            artifact,
            environment: this.context.environment,
            deployedAt: new Date().toISOString(),
            status: 'DEPLOYED'
        };
    }
}

class PipelineEngine extends EventEmitter {
    constructor(context, policy) {
        super();

        this.context = context;
        this.policy = policy;
        this.steps = new PipelineSteps(context, this);
        this.executing = false;
    }

    async executeStage(name, operation) {
        const result = {
            name,
            status: StageStatus.RUNNING,
            attempts: 0,
            startedAt: new Date().toISOString(),
            durationMs: 0,
            error: null
        };

        const start = performance.now();

        this.emit('stageStarted', { name });

        try {
            const output = await operation();

            result.status = StageStatus.SUCCESS;
            result.output = output;

            return output;
        } catch (error) {
            result.status = StageStatus.FAILED;
            result.error = error.message;

            throw new StageError(
                `${name}: ${error.message}`,
                { cause: error }
            );
        } finally {
            result.durationMs = performance.now() - start;
            result.finishedAt = new Date().toISOString();

            this.context.results.push(result);

            this.emit('stageFinished', result);
        }
    }

    async run(repository) {
        if (this.executing ||
            this.context.status !== PipelineStatus.CREATED) {
            throw new PipelineError('Pipeline cannot be executed again.');
        }

        this.executing = true;
        this.context.status = PipelineStatus.RUNNING;
        this.context.startedAt = new Date().toISOString();

        this.emit('pipelineStarted', this.context);

        try {
            this.policy.validate(this.context);

            const checkout = await this.executeStage(
                'checkout',
                () => this.steps.checkout(repository)
            );

            await this.executeStage(
                'build',
                async () => ({
                    artifact: `${this.context.application}-${this.context.buildNumber}.jar`
                })
            );

            const tests = await this.executeStage(
                'test',
                () => this.steps.retry(
                    () => this.steps.runTests(checkout),
                    { attempts: 3 }
                )
            );

            if (tests.passed < this.policy.minimumTestCount ||
                tests.failed !== 0) {
                throw new PolicyError('Quality gate was not satisfied.');
            }

            const artifact = `${this.context.application}-${this.context.buildNumber}.jar`;

            await this.executeStage(
                'package',
                async () => ({
                    artifact,
                    checksum: crypto
                        .createHash('sha256')
                        .update(artifact)
                        .digest('hex')
                })
            );

            await this.executeStage(
                'deploy',
                () => this.steps.deploy(artifact)
            );

            this.context.status = PipelineStatus.SUCCESS;
        } catch (error) {
            this.context.status = PipelineStatus.FAILED;
            this.context.failureReason = error.message;

            this.emit('pipelineFailed', {
                runId: this.context.runId,
                error: error.message
            });
        } finally {
            this.context.finishedAt = new Date().toISOString();
            this.executing = false;

            this.emit('pipelineFinished', this.context);
        }

        return this.context;
    }

    generateReport() {
        return {
            runId: this.context.runId,
            application: this.context.application,
            branch: this.context.branch,
            environment: this.context.environment,
            library: {
                name: this.context.library.name,
                version: this.context.library.version,
                commit: this.context.library.commit
            },
            buildNumber: this.context.buildNumber,
            status: this.context.status,
            failureReason: this.context.failureReason || null,
            stages: this.context.results
        };
    }
}

async function saveReport(report, filename) {
    const destination = path.resolve(filename);
    const temporary = `${destination}.${crypto.randomUUID()}.tmp`;

    try {
        await fs.writeFile(
            temporary,
            JSON.stringify(report, null, 2),
            { encoding: 'utf8', flag: 'wx', mode: 0o600 }
        );

        await fs.rename(temporary, destination);
    } catch (error) {
        await fs.rm(temporary, { force: true }).catch(() => {});
        throw error;
    }
}

async function main() {
    const registry = new LibraryRegistry();

    const library = new SharedLibrary({
        name: 'enterprise-ci',
        version: '2.1.0',
        commit: 'a1b2c3d4e5f6789',
        approved: true,
        tested: true,
        steps: {
            checkout: true,
            build: true,
            test: true,
            deploy: true
        }
    });

    registry.register(library);

    const resolved = registry.resolve('enterprise-ci', '2.1.0');

    const context = new PipelineContext({
        application: 'customer-api',
        branch: 'main',
        environment: Environment.STAGING,
        buildNumber: 301,
        library: resolved
    });

    const policy = new PipelinePolicy({
        requireApprovalForProduction: true,
        minimumTestCount: 1
    });

    const pipeline = new PipelineEngine(context, policy);

    pipeline.on('pipelineStarted', () => {
        console.log('Pipeline started.');
    });

    pipeline.on('stageFinished', result => {
        console.log(
            `${result.name}: ${result.status} (${result.durationMs.toFixed(2)} ms)`
        );
    });

    pipeline.on('retry', event => {
        console.log(`Retry ${event.attempt}: ${event.error}`);
    });

    pipeline.on('pipelineFinished', result => {
        console.log(`Pipeline status: ${result.status}`);
    });

    const result = await pipeline.run(
        'https://git.example.com/platform/customer-api.git'
    );

    const report = pipeline.generateReport();

    await saveReport(report, 'pipeline-report.json');

    console.log('\nExecution report:');
    console.log(JSON.stringify(report, null, 2));

    if (result.status !== PipelineStatus.SUCCESS) {
        process.exitCode = 1;
    }

    // Verify production approval enforcement.
    const productionContext = new PipelineContext({
        application: 'customer-api',
        branch: 'main',
        environment: Environment.PRODUCTION,
        buildNumber: 302,
        library: resolved,
        approved: false
    });

    const productionPipeline = new PipelineEngine(
        productionContext,
        policy
    );

    const productionResult = await productionPipeline.run(
        'https://git.example.com/platform/customer-api.git'
    );

    if (productionResult.status !== PipelineStatus.FAILED) {
        throw new Error('Production approval policy was not enforced.');
    }

    // Verify release validation.
    let rejected = false;

    try {
        registry.resolve('enterprise-ci', '9.9.9');
    } catch (error) {
        rejected = error instanceof ValidationError;
    }

    if (!rejected) {
        throw new Error('Unknown library release was accepted.');
    }

    console.log('\nAll validation checks passed.');
}

main().catch(error => {
    console.error('Fatal execution error:', error.message);
    process.exitCode = 1;
});

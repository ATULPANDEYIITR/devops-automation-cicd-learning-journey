'use strict';

/*
 * Actions Matrix Builds
 *
 * This Node.js program models a multi-version CI matrix as an event-driven
 * workflow. It focuses on JavaScript-specific concerns:
 * - matrix expansion
 * - asynchronous job execution
 * - event emission
 * - status aggregation
 * - fail-fast cancellation
 * - experimental jobs
 * - retry handling
 * - artifact naming
 *
 * Run with:
 *   node matrix-builds.js
 */

const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');

const VALID_PYTHON = new Set(['3.10', '3.11', '3.12', '3.13']);
const VALID_OS = new Set(['ubuntu', 'windows', 'macos']);
const VALID_DEPS = new Set(['minimum', 'locked', 'latest']);

function validateMatrixDefinition(definition) {
    if (!Array.isArray(definition.python) || definition.python.length === 0) {
        throw new Error('The Python matrix dimension cannot be empty.');
    }

    if (!Array.isArray(definition.os) || definition.os.length === 0) {
        throw new Error('The operating-system matrix dimension cannot be empty.');
    }

    if (!Array.isArray(definition.dependencies) || definition.dependencies.length === 0) {
        throw new Error('The dependency matrix dimension cannot be empty.');
    }

    for (const version of definition.python) {
        if (!VALID_PYTHON.has(version)) {
            throw new Error(`Unsupported Python version: ${version}`);
        }
    }

    for (const operatingSystem of definition.os) {
        if (!VALID_OS.has(operatingSystem)) {
            throw new Error(`Unsupported operating system: ${operatingSystem}`);
        }
    }

    for (const dependencyMode of definition.dependencies) {
        if (!VALID_DEPS.has(dependencyMode)) {
            throw new Error(`Unsupported dependency mode: ${dependencyMode}`);
        }
    }
}

function matchesRule(job, rule) {
    return Object.entries(rule).every(([key, value]) => job[key] === value);
}

function stableJobId(job) {
    return crypto
        .createHash('sha256')
        .update(`${job.python}|${job.os}|${job.dependencies}`)
        .digest('hex')
        .slice(0, 10);
}

function expandMatrix(definition) {
    validateMatrixDefinition(definition);

    const jobs = [];

    for (const python of definition.python) {
        for (const os of definition.os) {
            for (const dependencies of definition.dependencies) {
                const job = {
                    python,
                    os,
                    dependencies,
                    experimental: false,
                };

                if (
                    definition.exclude?.some((rule) =>
                        matchesRule(job, rule)
                    )
                ) {
                    continue;
                }

                jobs.push(job);
            }
        }
    }

    for (const include of definition.include ?? []) {
        const existing = jobs.findIndex((job) =>
            ['python', 'os', 'dependencies'].every(
                (key) => include[key] === job[key]
            )
        );

        if (existing >= 0) {
            jobs[existing] = {
                ...jobs[existing],
                ...include,
            };
            continue;
        }

        for (const key of ['python', 'os', 'dependencies']) {
            if (!(key in include)) {
                throw new Error(
                    `An include rule adding a new job must define ${key}.`
                );
            }
        }

        jobs.push({
            python: include.python,
            os: include.os,
            dependencies: include.dependencies,
            experimental: Boolean(include.experimental),
        });
    }

    return jobs.map((job) => ({
        ...job,
        id: stableJobId(job),
    }));
}

function evaluateTests(job) {
    if (job.python === '3.10' && job.dependencies === 'latest') {
        return {
            passed: false,
            message: 'Latest dependencies no longer support Python 3.10.',
        };
    }

    if (job.os === 'windows' && job.python === '3.10') {
        return {
            passed: false,
            message: 'Legacy Windows compatibility test failed.',
        };
    }

    if (job.os === 'macos' && job.python === '3.13') {
        return {
            passed: false,
            message: 'Native extension compatibility test failed.',
        };
    }

    if (job.python === '3.13' && job.dependencies === 'minimum') {
        return {
            passed: false,
            message: 'Minimum dependency set is incompatible with Python 3.13.',
        };
    }

    return {
        passed: true,
        message: 'All selected test suites passed.',
    };
}

class MatrixWorkflow extends EventEmitter {
    constructor({
        failFast = true,
        maxRetries = 1,
        continueOnError = (job) => job.experimental,
    } = {}) {
        super();
        this.failFast = failFast;
        this.maxRetries = maxRetries;
        this.continueOnError = continueOnError;
        this.workflowFailed = false;
    }

    async executeJob(job) {
        this.emit('jobStarted', job);

        let attempt = 0;
        let result;

        while (attempt <= this.maxRetries) {
            attempt += 1;

            // Promise-based delay models an asynchronous CI runner without
            // requiring a third-party package or real external service.
            await new Promise((resolve) => setTimeout(resolve, 10));

            result = evaluateTests(job);

            if (result.passed) {
                break;
            }
        }

        const completed = {
            ...job,
            status: result.passed ? 'passed' : 'failed',
            attempts: attempt,
            message: result.message,
            artifact: `results-${job.id}-${job.os}-py${job.python.replace('.', '')}`,
        };

        this.emit('jobCompleted', completed);

        if (
            completed.status === 'failed' &&
            !this.continueOnError(job)
        ) {
            this.workflowFailed = true;
        }

        return completed;
    }

    async run(jobs) {
        const results = [];

        for (const job of jobs) {
            if (
                this.failFast &&
                this.workflowFailed &&
                !this.continueOnError(job)
            ) {
                const cancelled = {
                    ...job,
                    status: 'cancelled',
                    attempts: 0,
                    message: 'Cancelled after a blocking matrix failure.',
                    artifact: null,
                };

                this.emit('jobCancelled', cancelled);
                results.push(cancelled);
                continue;
            }

            results.push(await this.executeJob(job));
        }

        return results;
    }
}

function printMatrix(jobs) {
    console.log('\nExpanded matrix');
    console.log('-'.repeat(95));

    for (const job of jobs) {
        console.log(
            `${job.id.padEnd(14)} ` +
            `Python ${job.python.padEnd(4)} ` +
            `${job.os.padEnd(8)} ` +
            `${job.dependencies.padEnd(8)} ` +
            `${job.experimental ? 'experimental' : 'release-blocking'}`
        );
    }
}

function summarize(results) {
    const summary = {
        total: results.length,
        passed: results.filter((r) => r.status === 'passed').length,
        failed: results.filter((r) => r.status === 'failed').length,
        cancelled: results.filter((r) => r.status === 'cancelled').length,
    };

    const blockingFailures = results.filter(
        (r) => r.status === 'failed' && !r.experimental
    );

    summary.workflow = blockingFailures.length === 0 ? 'success' : 'failure';
    return summary;
}

function printResults(results) {
    console.log('\nMatrix results');
    console.log('-'.repeat(120));

    for (const result of results) {
        console.log(
            `${result.status.padEnd(10)} ` +
            `${result.id.padEnd(14)} ` +
            `py=${result.python} ` +
            `os=${result.os.padEnd(8)} ` +
            `deps=${result.dependencies.padEnd(8)} ` +
            `attempts=${String(result.attempts).padEnd(2)} ` +
            result.message
        );
    }
}

async function main() {
    const matrix = {
        python: ['3.10', '3.11', '3.12', '3.13'],
        os: ['ubuntu', 'windows', 'macos'],
        dependencies: ['minimum', 'locked', 'latest'],
        exclude: [
            {
                python: '3.10',
                os: 'macos',
                dependencies: 'minimum',
            },
            {
                python: '3.13',
                os: 'windows',
                dependencies: 'minimum',
            },
        ],
        include: [
            {
                python: '3.13',
                os: 'ubuntu',
                dependencies: 'latest',
                experimental: true,
            },
        ],
    };

    const jobs = expandMatrix(matrix);
    printMatrix(jobs);

    const workflow = new MatrixWorkflow({
        failFast: false,
        maxRetries: 1,
    });

    workflow.on('jobStarted', (job) => {
        console.log(`Starting ${job.id} (${job.python}/${job.os})`);
    });

    workflow.on('jobCompleted', (job) => {
        console.log(`Completed ${job.id}: ${job.status}`);
    });

    workflow.on('jobCancelled', (job) => {
        console.log(`Cancelled ${job.id}: ${job.message}`);
    });

    const results = await workflow.run(jobs);

    printResults(results);

    console.log('\nWorkflow summary');
    console.log('-'.repeat(50));
    console.log(JSON.stringify(summarize(results), null, 2));

    console.log('\nArtifact isolation example');
    console.log('-'.repeat(70));

    for (const result of results.filter((r) => r.status === 'passed').slice(0, 4)) {
        console.log(`${result.id}: ${result.artifact}`);
    }
}

main().catch((error) => {
    console.error(`Matrix workflow failed to initialize: ${error.message}`);
    process.exitCode = 1;
});

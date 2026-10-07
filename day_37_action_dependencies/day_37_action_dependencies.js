'use strict';

/**
 * GitHub Actions dependency and conditional-execution model.
 *
 * This file focuses on JavaScript's event-driven strengths. Jobs are modeled
 * as asynchronous tasks, dependencies are resolved before execution, and
 * conditions inspect completed dependency results.
 *
 * Runtime: Node.js 18+
 */

const JobStatus = Object.freeze({
    PENDING: 'pending',
    RUNNING: 'running',
    SUCCESS: 'success',
    FAILURE: 'failure',
    SKIPPED: 'skipped',
    CANCELLED: 'cancelled'
});

class WorkflowError extends Error {
    constructor(message) {
        super(message);
        this.name = 'WorkflowError';
    }
}

class JobResult {
    constructor(name, status, message = '', outputs = {}) {
        this.name = name;
        this.status = status;
        this.message = message;
        this.outputs = Object.freeze({ ...outputs });
    }

    get successful() {
        return this.status === JobStatus.SUCCESS;
    }

    get failed() {
        return this.status === JobStatus.FAILURE;
    }

    get terminal() {
        return [
            JobStatus.SUCCESS,
            JobStatus.FAILURE,
            JobStatus.SKIPPED,
            JobStatus.CANCELLED
        ].includes(this.status);
    }
}

class Job {
    constructor({
        name,
        needs = [],
        condition = null,
        run,
        allowFailure = false
    }) {
        this.name = name;
        this.needs = [...needs];
        this.condition = condition;
        this.run = run || (async () => new JobResult(
            name,
            JobStatus.SUCCESS,
            'No operation was supplied.'
        ));
        this.allowFailure = allowFailure;
    }
}

class ActionsWorkflow {
    constructor(name, context = {}) {
        this.name = name;
        this.context = Object.freeze({ ...context });
        this.jobs = new Map();
        this.results = new Map();
    }

    addJob(job) {
        if (this.jobs.has(job.name)) {
            throw new WorkflowError(`Duplicate job '${job.name}'.`);
        }

        if (job.needs.includes(job.name)) {
            throw new WorkflowError(
                `Job '${job.name}' cannot depend on itself.`
            );
        }

        this.jobs.set(job.name, job);
    }

    validate() {
        for (const job of this.jobs.values()) {
            for (const dependency of job.needs) {
                if (!this.jobs.has(dependency)) {
                    throw new WorkflowError(
                        `Job '${job.name}' references unknown dependency '${dependency}'.`
                    );
                }
            }
        }

        const visiting = new Set();
        const visited = new Set();

        const visit = (name) => {
            if (visiting.has(name)) {
                throw new WorkflowError(
                    `Dependency cycle detected at '${name}'.`
                );
            }

            if (visited.has(name)) {
                return;
            }

            visiting.add(name);

            for (const dependency of this.jobs.get(name).needs) {
                visit(dependency);
            }

            visiting.delete(name);
            visited.add(name);
        };

        for (const name of this.jobs.keys()) {
            visit(name);
        }
    }

    dependencyResults(job) {
        return Object.fromEntries(
            job.needs.map(name => [name, this.results.get(name)])
        );
    }

    defaultCondition(job) {
        if (job.needs.length === 0) {
            return true;
        }

        return job.needs.every(
            dependency => this.results.get(dependency)?.successful
        );
    }

    async executeJob(job) {
        const dependencyResults = this.dependencyResults(job);

        const eligible = job.condition
            ? await job.condition({
                results: this.results,
                dependencies: dependencyResults,
                context: this.context,
                job
            })
            : this.defaultCondition(job);

        if (!eligible) {
            return new JobResult(
                job.name,
                JobStatus.SKIPPED,
                'Condition evaluated to false.'
            );
        }

        try {
            const result = await job.run({
                job,
                context: this.context,
                dependencies: dependencyResults
            });

            if (!(result instanceof JobResult)) {
                throw new WorkflowError(
                    `Job '${job.name}' did not return a JobResult.`
                );
            }

            return result;
        } catch (error) {
            if (job.allowFailure) {
                return new JobResult(
                    job.name,
                    JobStatus.FAILURE,
                    `Failure allowed: ${error.message}`
                );
            }

            return new JobResult(
                job.name,
                JobStatus.FAILURE,
                error.message
            );
        }
    }

    async run() {
        this.validate();

        while (this.results.size < this.jobs.size) {
            const ready = [...this.jobs.values()].filter(job => {
                if (this.results.has(job.name)) {
                    return false;
                }

                return job.needs.every(
                    dependency => this.results.has(dependency)
                );
            });

            if (ready.length === 0) {
                throw new WorkflowError(
                    'No executable job remains. The graph is unresolved.'
                );
            }

            /*
             * Independent jobs can execute concurrently. This is where the
             * asynchronous JavaScript model gives a useful representation of
             * CI fan-out: jobs sharing the same prerequisites need not wait
             * for one another.
             */
            const executions = ready.map(async job => {
                const result = await this.executeJob(job);
                this.results.set(job.name, result);
                return result;
            });

            await Promise.all(executions);
        }

        return this.results;
    }

    report() {
        console.log(`\n=== ${this.name} ===`);

        for (const [name, result] of this.results) {
            console.log(
                `${name.padEnd(24)} ` +
                `${result.status.padEnd(10)} ` +
                `${result.message}`
            );
        }
    }
}

function success(name, message) {
    return async () => {
        await delay(25);
        return new JobResult(name, JobStatus.SUCCESS, message);
    };
}

function failure(name, message) {
    return async () => {
        await delay(25);
        return new JobResult(name, JobStatus.FAILURE, message);
    };
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function buildJob({ job }) {
    await delay(30);

    return new JobResult(
        job.name,
        JobStatus.SUCCESS,
        'Build completed.',
        {
            artifact: 'dist/application.tar.gz',
            sha: 'build-7f4c2a'
        }
    );
}

async function unitTests({ dependencies, job }) {
    await delay(40);

    const build = dependencies.build;

    if (!build?.outputs.artifact) {
        throw new WorkflowError(
            'Unit tests require the build artifact.'
        );
    }

    return new JobResult(
        job.name,
        JobStatus.SUCCESS,
        'Unit tests passed.',
        {
            coverage: '94.2'
        }
    );
}

async function integrationTests({ dependencies, job }) {
    await delay(60);

    if (!dependencies['unit-tests']?.successful) {
        throw new WorkflowError(
            'Integration tests cannot start without successful unit tests.'
        );
    }

    return new JobResult(
        job.name,
        JobStatus.SUCCESS,
        'Integration tests passed.'
    );
}

async function deploy({ dependencies, job }) {
    await delay(35);

    const candidate = dependencies['release-candidate'];

    if (!candidate?.successful) {
        throw new WorkflowError(
            'Deployment requires an eligible release candidate.'
        );
    }

    return new JobResult(
        job.name,
        JobStatus.SUCCESS,
        'Deployment completed.'
    );
}

async function runBasicPipeline() {
    const workflow = new ActionsWorkflow('node-ci-pipeline');

    workflow.addJob(new Job({
        name: 'build',
        run: buildJob
    }));

    workflow.addJob(new Job({
        name: 'unit-tests',
        needs: ['build'],
        run: unitTests
    }));

    workflow.addJob(new Job({
        name: 'integration-tests',
        needs: ['unit-tests'],
        run: integrationTests
    }));

    workflow.addJob(new Job({
        name: 'release-candidate',
        needs: ['integration-tests'],
        run: success(
            'release-candidate',
            'Release candidate created.'
        )
    }));

    workflow.addJob(new Job({
        name: 'deploy',
        needs: ['release-candidate'],
        run: deploy
    }));

    await workflow.run();
    workflow.report();
}

async function runFanOutPipeline() {
    const workflow = new ActionsWorkflow('parallel-validation');

    workflow.addJob(new Job({
        name: 'build',
        run: buildJob
    }));

    workflow.addJob(new Job({
        name: 'lint',
        needs: ['build'],
        run: success('lint', 'Lint completed.')
    }));

    workflow.addJob(new Job({
        name: 'unit-tests',
        needs: ['build'],
        run: unitTests
    }));

    workflow.addJob(new Job({
        name: 'security',
        needs: ['build'],
        run: success('security', 'Security scan passed.')
    }));

    workflow.addJob(new Job({
        name: 'package',
        needs: ['lint', 'unit-tests', 'security'],
        run: success(
            'package',
            'Packaging started only after all validation branches passed.'
        )
    }));

    await workflow.run();
    workflow.report();
}

async function runConditionalPipeline() {
    const workflow = new ActionsWorkflow(
        'conditional-release',
        {
            branch: 'main',
            releaseEnabled: true,
            event: 'push'
        }
    );

    workflow.addJob(new Job({
        name: 'build',
        run: buildJob
    }));

    workflow.addJob(new Job({
        name: 'quality',
        needs: ['build'],
        run: success('quality', 'Quality checks passed.')
    }));

    workflow.addJob(new Job({
        name: 'production-deploy',
        needs: ['quality'],
        condition: ({ context, dependencies }) => (
            context.branch === 'main' &&
            context.releaseEnabled === true &&
            dependencies.quality?.successful
        ),
        run: async ({ job }) => new JobResult(
            job.name,
            JobStatus.SUCCESS,
            'Production deployment approved by workflow conditions.'
        )
    }));

    workflow.addJob(new Job({
        name: 'post-failure-diagnostics',
        needs: ['production-deploy'],
        condition: ({ dependencies }) => (
            dependencies['production-deploy']?.status !== JobStatus.SUCCESS
        ),
        run: success(
            'post-failure-diagnostics',
            'Failure diagnostics collected.'
        )
    }));

    await workflow.run();
    workflow.report();
}

async function runFailurePropagation() {
    const workflow = new ActionsWorkflow('failure-propagation');

    workflow.addJob(new Job({
        name: 'build',
        run: failure(
            'build',
            'Compiler error: release build failed.'
        )
    }));

    workflow.addJob(new Job({
        name: 'deploy',
        needs: ['build'],
        run: success('deploy', 'This should not execute.')
    }));

    /*
     * This job deliberately ignores the normal success-only dependency rule.
     * The equivalent idea is useful for cleanup, artifact collection, and
     * diagnostics, but should not be used casually for release jobs.
     */
    workflow.addJob(new Job({
        name: 'diagnostics',
        needs: ['build'],
        condition: async () => true,
        run: success(
            'diagnostics',
            'Diagnostics collected after build failure.'
        )
    }));

    await workflow.run();
    workflow.report();
}

function createMatrixJobs(versions) {
    return versions.map(version => ({
        name: `test-node-${version}`,
        version,
        passed: version !== '16'
    }));
}

async function runMatrixAggregation() {
    const matrix = createMatrixJobs(['18', '20', '22', '16']);

    console.log('\n=== Matrix-like dependency aggregation ===');

    for (const entry of matrix) {
        console.log(
            `${entry.name.padEnd(20)} ` +
            `${entry.passed ? 'PASS' : 'FAIL'}`
        );
    }

    const allPassed = matrix.every(entry => entry.passed);

    console.log(
        `Release gate: ${allPassed ? 'OPEN' : 'BLOCKED'}`
    );
}

function demonstrateDependencyGraph() {
    const graph = {
        checkout: [],
        build: ['checkout'],
        lint: ['build'],
        tests: ['build'],
        package: ['lint', 'tests'],
        deploy: ['package']
    };

    const indegree = Object.fromEntries(
        Object.keys(graph).map(node => [node, 0])
    );

    const dependents = Object.fromEntries(
        Object.keys(graph).map(node => [node, []])
    );

    for (const [node, dependencies] of Object.entries(graph)) {
        for (const dependency of dependencies) {
            if (!(dependency in graph)) {
                throw new WorkflowError(
                    `Unknown dependency '${dependency}'.`
                );
            }

            indegree[node] += 1;
            dependents[dependency].push(node);
        }
    }

    const queue = Object.keys(indegree)
        .filter(node => indegree[node] === 0);

    const order = [];

    while (queue.length > 0) {
        const current = queue.shift();
        order.push(current);

        for (const dependent of dependents[current]) {
            indegree[dependent] -= 1;

            if (indegree[dependent] === 0) {
                queue.push(dependent);
            }
        }
    }

    if (order.length !== Object.keys(graph).length) {
        throw new WorkflowError('Dependency cycle detected.');
    }

    console.log('\n=== Topological execution order ===');
    console.log(order.join(' -> '));
}

function demonstrateInvalidCondition() {
    const workflow = new ActionsWorkflow('invalid-graph');

    workflow.addJob(new Job({
        name: 'a',
        needs: ['b'],
        run: success('a', 'A completed.')
    }));

    workflow.addJob(new Job({
        name: 'b',
        needs: ['a'],
        run: success('b', 'B completed.')
    }));

    try {
        workflow.validate();
    } catch (error) {
        console.log('\n=== Invalid dependency graph ===');
        console.log(error.message);
    }
}

async function main() {
    console.log('GitHub Actions Dependencies and Conditional Execution');
    console.log('='.repeat(58));

    await runBasicPipeline();
    await runFanOutPipeline();
    await runConditionalPipeline();
    await runFailurePropagation();
    await runMatrixAggregation();

    demonstrateDependencyGraph();
    demonstrateInvalidCondition();
}

main().catch(error => {
    console.error('Workflow execution failed:', error);
    process.exitCode = 1;
});

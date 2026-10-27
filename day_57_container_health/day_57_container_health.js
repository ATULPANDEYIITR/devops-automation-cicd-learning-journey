'use strict';

/*
 * Container health automation model.
 *
 * Distinguishes:
 *   1. process state
 *   2. application health
 *   3. restart policy
 *   4. resource limits
 *
 * Uses event-driven JavaScript to represent health events and automated
 * recovery decisions without requiring external npm packages.
 */

const { EventEmitter } = require('node:events');

const HealthStatus = Object.freeze({
    STARTING: 'starting',
    HEALTHY: 'healthy',
    UNHEALTHY: 'unhealthy'
});

const ContainerState = Object.freeze({
    CREATED: 'created',
    RUNNING: 'running',
    STOPPED: 'stopped',
    RESTARTING: 'restarting'
});

const RestartPolicy = Object.freeze({
    NO: 'no',
    ON_FAILURE: 'on-failure',
    ALWAYS: 'always',
    UNLESS_STOPPED: 'unless-stopped'
});

class ValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = 'ValidationError';
    }
}

class HealthCheckError extends Error {
    constructor(message) {
        super(message);
        this.name = 'HealthCheckError';
    }
}

class ResourceLimits {
    constructor({ cpuMillicores, memoryMb }) {
        if (!Number.isInteger(cpuMillicores) || cpuMillicores <= 0) {
            throw new ValidationError('CPU limit must be a positive integer');
        }

        if (!Number.isInteger(memoryMb) || memoryMb <= 0) {
            throw new ValidationError('Memory limit must be a positive integer');
        }

        this.cpuMillicores = cpuMillicores;
        this.memoryMb = memoryMb;
        Object.freeze(this);
    }
}

class HealthCheck {
    constructor({
        intervalMs = 5000,
        timeoutMs = 2000,
        retries = 3,
        startPeriodMs = 0
    } = {}) {
        if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
            throw new HealthCheckError('Invalid health-check interval');
        }

        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            throw new HealthCheckError('Invalid health-check timeout');
        }

        if (timeoutMs > intervalMs) {
            throw new HealthCheckError(
                'Health-check timeout cannot exceed its interval'
            );
        }

        if (!Number.isInteger(retries) || retries < 1) {
            throw new HealthCheckError('Retries must be at least one');
        }

        if (!Number.isFinite(startPeriodMs) || startPeriodMs < 0) {
            throw new HealthCheckError('Invalid start period');
        }

        this.intervalMs = intervalMs;
        this.timeoutMs = timeoutMs;
        this.retries = retries;
        this.startPeriodMs = startPeriodMs;
        Object.freeze(this);
    }
}

class Container extends EventEmitter {
    constructor({
        name,
        image,
        resources,
        healthCheck,
        restartPolicy = RestartPolicy.NO,
        maxRestarts = 5
    }) {
        super();

        if (typeof name !== 'string' || name.trim() === '') {
            throw new ValidationError('Container name is required');
        }

        if (typeof image !== 'string' || image.trim() === '') {
            throw new ValidationError('Container image is required');
        }

        if (!Object.values(RestartPolicy).includes(restartPolicy)) {
            throw new ValidationError('Unknown restart policy');
        }

        if (!Number.isInteger(maxRestarts) || maxRestarts < 0) {
            throw new ValidationError('Invalid restart limit');
        }

        this.name = name;
        this.image = image;
        this.resources = resources;
        this.healthCheck = healthCheck;
        this.restartPolicy = restartPolicy;
        this.maxRestarts = maxRestarts;

        this.state = ContainerState.CREATED;
        this.health = HealthStatus.STARTING;
        this.restartCount = 0;
        this.failureCount = 0;
        this.manuallyStopped = false;
        this.startedAt = null;
        this.healthHistory = [];
    }

    start() {
        if (this.state === ContainerState.RUNNING) {
            return;
        }

        this.manuallyStopped = false;
        this.state = ContainerState.RUNNING;
        this.health = HealthStatus.STARTING;
        this.failureCount = 0;
        this.startedAt = Date.now();

        this.emit('started', {
            name: this.name,
            timestamp: this.startedAt
        });
    }

    stop(manual = true) {
        this.state = ContainerState.STOPPED;
        this.manuallyStopped = manual;

        this.emit('stopped', {
            name: this.name,
            manual
        });
    }

    async executeHealthCheck(probe) {
        if (this.state !== ContainerState.RUNNING) {
            throw new Error(`Container ${this.name} is not running`);
        }

        const elapsed = Date.now() - this.startedAt;

        const result = await Promise.race([
            Promise.resolve().then(() => probe(this)),
            new Promise((resolve) => {
                setTimeout(() => {
                    resolve({
                        success: false,
                        latencyMs: this.healthCheck.timeoutMs,
                        message: 'health check timeout'
                    });
                }, this.healthCheck.timeoutMs);
            })
        ]);

        this.healthHistory.push({
            timestamp: Date.now(),
            ...result
        });

        if (elapsed < this.healthCheck.startPeriodMs) {
            this.health = HealthStatus.STARTING;
            this.failureCount = 0;
            return this.health;
        }

        const valid =
            result.success === true &&
            Number.isFinite(result.latencyMs) &&
            result.latencyMs <= this.healthCheck.timeoutMs;

        if (valid) {
            this.failureCount = 0;
            this.health = HealthStatus.HEALTHY;

            this.emit('healthy', {
                name: this.name,
                result
            });

            return this.health;
        }

        this.failureCount += 1;

        if (this.failureCount >= this.healthCheck.retries) {
            this.health = HealthStatus.UNHEALTHY;

            this.emit('unhealthy', {
                name: this.name,
                result,
                failures: this.failureCount
            });
        }

        return this.health;
    }

    shouldRestart(exitCode) {
        if (this.manuallyStopped || this.restartCount >= this.maxRestarts) {
            return false;
        }

        switch (this.restartPolicy) {
            case RestartPolicy.ALWAYS:
            case RestartPolicy.UNLESS_STOPPED:
                return true;

            case RestartPolicy.ON_FAILURE:
                return exitCode !== 0;

            default:
                return false;
        }
    }

    restart(exitCode = 1) {
        if (!this.shouldRestart(exitCode)) {
            return false;
        }

        this.state = ContainerState.RESTARTING;
        this.restartCount += 1;

        // Deterministic bounded backoff for this executable model.
        const delayMs = Math.min(1000 * (2 ** (this.restartCount - 1)), 8000);

        this.emit('restarting', {
            name: this.name,
            restartCount: this.restartCount,
            delayMs
        });

        this.start();
        return true;
    }
}

class ContainerOrchestrator extends EventEmitter {
    constructor() {
        super();
        this.containers = new Map();
    }

    register(container) {
        if (this.containers.has(container.name)) {
            throw new ValidationError(
                `Duplicate container: ${container.name}`
            );
        }

        this.containers.set(container.name, container);

        container.on('unhealthy', (event) => {
            this.emit('health-failure', event);

            if (container.restart(1)) {
                this.emit('recovery-started', {
                    name: container.name,
                    restartCount: container.restartCount
                });
            }
        });
    }

    startAll() {
        for (const container of this.containers.values()) {
            container.start();
        }
    }

    getStatus() {
        return [...this.containers.values()].map((container) => ({
            name: container.name,
            state: container.state,
            health: container.health,
            restarts: container.restartCount,
            cpuMillicores: container.resources.cpuMillicores,
            memoryMb: container.resources.memoryMb
        }));
    }
}

function healthyApiProbe() {
    return {
        success: true,
        latencyMs: 45,
        message: 'HTTP 200 /health'
    };
}

function failingWorkerProbe() {
    return {
        success: false,
        latencyMs: 3000,
        message: 'dependency unavailable'
    };
}

async function main() {
    const orchestrator = new ContainerOrchestrator();

    const api = new Container({
        name: 'api',
        image: 'example/api:2.4',
        resources: new ResourceLimits({
            cpuMillicores: 500,
            memoryMb: 512
        }),
        healthCheck: new HealthCheck({
            intervalMs: 5000,
            timeoutMs: 2000,
            retries: 3,
            startPeriodMs: 100
        }),
        restartPolicy: RestartPolicy.UNLESS_STOPPED
    });

    const worker = new Container({
        name: 'worker',
        image: 'example/worker:4.1',
        resources: new ResourceLimits({
            cpuMillicores: 750,
            memoryMb: 1024
        }),
        healthCheck: new HealthCheck({
            intervalMs: 5000,
            timeoutMs: 100,
            retries: 2
        }),
        restartPolicy: RestartPolicy.ON_FAILURE,
        maxRestarts: 2
    });

    orchestrator.on('health-failure', (event) => {
        console.log(
            `[health] ${event.name}: ${event.result.message}; ` +
            `failures=${event.failures}`
        );
    });

    orchestrator.on('recovery-started', (event) => {
        console.log(
            `[recovery] ${event.name} restart #${event.restartCount}`
        );
    });

    orchestrator.register(api);
    orchestrator.register(worker);
    orchestrator.startAll();

    await new Promise((resolve) => setTimeout(resolve, 120));

    await api.executeHealthCheck(healthyApiProbe);

    for (let i = 0; i < 4; i += 1) {
        await worker.executeHealthCheck(failingWorkerProbe);
    }

    console.table(orchestrator.getStatus());

    api.stop(true);

    if (!api.shouldRestart(1)) {
        console.log('[policy] manual stop correctly suppresses restart');
    }

    try {
        new HealthCheck({
            intervalMs: 1000,
            timeoutMs: 2000
        });
    } catch (error) {
        if (error instanceof HealthCheckError) {
            console.log(`[validation] ${error.message}`);
        } else {
            throw error;
        }
    }

    if (api.health !== HealthStatus.HEALTHY) {
        throw new Error('API should be healthy after a successful probe');
    }

    console.log(
        '\nResource limits constrain runtime consumption; ' +
        'health checks evaluate application behavior.'
    );
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});

'use strict';

/**
 * Ansible Fundamentals
 *
 * Inventory, modules, playbooks, asynchronous execution,
 * idempotency, handlers, variable precedence, check mode,
 * and execution reporting.
 *
 * Runtime: Node.js 18+
 * External dependencies: None
 */

const { EventEmitter } = require('node:events');
const fs = require('node:fs/promises');

class ConfigurationError extends Error {}
class TaskExecutionError extends Error {}

const TaskStatus = Object.freeze({
    OK: 'ok',
    CHANGED: 'changed',
    FAILED: 'failed',
    SKIPPED: 'skipped'
});

function validateName(value, label) {
    if (
        typeof value !== 'string' ||
        !/^[A-Za-z0-9_.-]+$/.test(value)
    ) {
        throw new ConfigurationError(`Invalid ${label}: ${value}`);
    }
}

class Inventory {
    constructor() {
        this.hosts = new Map();
        this.groups = new Map();
        this.groupVariables = new Map();
    }

    addHost(host, groups = ['ungrouped']) {
        validateName(host.name, 'hostname');

        if (this.hosts.has(host.name)) {
            throw new ConfigurationError(
                `Duplicate host: ${host.name}`
            );
        }

        if (!host.address || !Number.isInteger(host.port)) {
            throw new ConfigurationError(
                'Host address and valid port are required.'
            );
        }

        if (host.port < 1 || host.port > 65535) {
            throw new ConfigurationError('Invalid port.');
        }

        this.hosts.set(host.name, {
            ...host,
            state: {
                packages: new Set(),
                services: new Map(),
                files: new Map()
            }
        });

        for (const group of groups) {
            validateName(group, 'group');

            if (!this.groups.has(group)) {
                this.groups.set(group, new Set());
            }

            this.groups.get(group).add(host.name);
        }
    }

    setGroupVariables(group, variables) {
        if (!this.groups.has(group)) {
            throw new ConfigurationError(
                `Unknown group: ${group}`
            );
        }

        this.groupVariables.set(group, { ...variables });
    }

    select(pattern) {
        let names;

        if (pattern === 'all') {
            names = [...this.hosts.keys()];
        } else if (this.groups.has(pattern)) {
            names = [...this.groups.get(pattern)];
        } else if (this.hosts.has(pattern)) {
            names = [pattern];
        } else {
            throw new ConfigurationError(
                `Inventory pattern not found: ${pattern}`
            );
        }

        return names
            .sort()
            .map(name => this.hosts.get(name));
    }

    variablesFor(host) {
        const result = {};

        for (const [group, members] of this.groups) {
            if (members.has(host.name)) {
                Object.assign(
                    result,
                    this.groupVariables.get(group) || {}
                );
            }
        }

        return {
            ...result,
            ...host.variables
        };
    }

    static fromJSON(data) {
        const inventory = new Inventory();

        if (!Array.isArray(data.hosts)) {
            throw new ConfigurationError(
                'Inventory requires a hosts array.'
            );
        }

        for (const host of data.hosts) {
            inventory.addHost(
                {
                    name: host.name,
                    address: host.address,
                    port: host.port || 22,
                    username: host.username || 'ansible',
                    variables: host.variables || {},
                    reachable: host.reachable !== false
                },
                host.groups || ['ungrouped']
            );
        }

        for (const [group, variables] of Object.entries(
            data.groupVariables || {}
        )) {
            inventory.setGroupVariables(group, variables);
        }

        return inventory;
    }
}

class ModuleRegistry {
    constructor() {
        this.modules = new Map();

        this.register('package', async (host, args, check) => {
            const { name, state = 'present' } = args;

            validateName(name, 'package');

            if (!['present', 'absent'].includes(state)) {
                throw new TaskExecutionError(
                    'Invalid package state.'
                );
            }

            const exists = host.state.packages.has(name);

            if (
                (state === 'present' && exists) ||
                (state === 'absent' && !exists)
            ) {
                return {
                    status: TaskStatus.OK,
                    message: `${name} already compliant`
                };
            }

            if (!check) {
                if (state === 'present') {
                    host.state.packages.add(name);
                } else {
                    host.state.packages.delete(name);
                }
            }

            return {
                status: TaskStatus.CHANGED,
                message: `Package ${name}: ${state}`
            };
        });

        this.register('service', async (host, args, check) => {
            const {
                name,
                state = 'started',
                enabled = true
            } = args;

            validateName(name, 'service');

            if (!['started', 'stopped'].includes(state)) {
                throw new TaskExecutionError(
                    'Invalid service state.'
                );
            }

            if (typeof enabled !== 'boolean') {
                throw new TaskExecutionError(
                    'enabled must be boolean.'
                );
            }

            const desired = { state, enabled };
            const current = host.state.services.get(name);

            if (
                current &&
                current.state === state &&
                current.enabled === enabled
            ) {
                return {
                    status: TaskStatus.OK,
                    message: `Service ${name} already compliant`
                };
            }

            if (!check) {
                host.state.services.set(name, desired);
            }

            return {
                status: TaskStatus.CHANGED,
                message: `Service ${name}: ${state}`
            };
        });

        this.register('file', async (host, args, check) => {
            const {
                path,
                state = 'file',
                mode = '0644'
            } = args;

            if (
                typeof path !== 'string' ||
                !path.startsWith('/') ||
                path.split('/').includes('..')
            ) {
                throw new TaskExecutionError(
                    'An absolute safe path is required.'
                );
            }

            if (
                !['file', 'directory', 'absent'].includes(state)
            ) {
                throw new TaskExecutionError(
                    'Invalid file state.'
                );
            }

            if (!/^[0-7]{3,4}$/.test(String(mode))) {
                throw new TaskExecutionError(
                    'Invalid file permissions.'
                );
            }

            const desired = state === 'absent'
                ? null
                : { state, mode: String(mode) };

            const current = host.state.files.get(path);

            if (
                JSON.stringify(current ?? null) ===
                JSON.stringify(desired)
            ) {
                return {
                    status: TaskStatus.OK,
                    message: `${path} already compliant`
                };
            }

            if (!check) {
                if (desired === null) {
                    host.state.files.delete(path);
                } else {
                    host.state.files.set(path, desired);
                }
            }

            return {
                status: TaskStatus.CHANGED,
                message: `File evaluated: ${path}`
            };
        });

        this.register('command', async (host, args) => {
            const allowed = new Map([
                ['check_http', 'HTTP configuration verified'],
                ['check_disk', 'Disk capacity verified'],
                ['check_service', 'Service availability verified']
            ]);

            if (!allowed.has(args.command)) {
                throw new TaskExecutionError(
                    'Command is not permitted.'
                );
            }

            return {
                status: TaskStatus.OK,
                message: allowed.get(args.command)
            };
        });
    }

    register(name, handler) {
        if (this.modules.has(name)) {
            throw new ConfigurationError(
                `Module already registered: ${name}`
            );
        }

        this.modules.set(name, handler);
    }

    async execute(name, host, args, checkMode) {
        const module = this.modules.get(name);

        if (!module) {
            throw new TaskExecutionError(
                `Unknown module: ${name}`
            );
        }

        return module(host, args, checkMode);
    }
}

class PlaybookEngine extends EventEmitter {
    constructor(inventory) {
        super();

        this.inventory = inventory;
        this.registry = new ModuleRegistry();
        this.results = [];
        this.maxConcurrency = 3;
    }

    resolveArguments(args, variables) {
        const resolve = value => {
            if (typeof value === 'string') {
                const match = value.match(
                    /^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$/
                );

                if (match) {
                    if (!(match[1] in variables)) {
                        throw new TaskExecutionError(
                            `Undefined variable: ${match[1]}`
                        );
                    }

                    return variables[match[1]];
                }

                return value;
            }

            if (Array.isArray(value)) {
                return value.map(resolve);
            }

            if (
                value !== null &&
                typeof value === 'object'
            ) {
                return Object.fromEntries(
                    Object.entries(value).map(
                        ([key, item]) => [key, resolve(item)]
                    )
                );
            }

            return value;
        };

        return resolve(args);
    }

    record(host, task, status, message) {
        const result = {
            host: host.name,
            task,
            status,
            message,
            timestamp: new Date().toISOString()
        };

        this.results.push(result);
        this.emit('taskComplete', result);

        return result;
    }

    async executeTask(host, task, variables, checkMode) {
        if (task.when === false) {
            return this.record(
                host,
                task.name,
                TaskStatus.SKIPPED,
                'Condition evaluated to false'
            );
        }

        try {
            const args = this.resolveArguments(
                task.args || {},
                variables
            );

            const result = await this.registry.execute(
                task.module,
                host,
                args,
                checkMode
            );

            return this.record(
                host,
                task.name,
                result.status,
                result.message
            );
        } catch (error) {
            const result = this.record(
                host,
                task.name,
                TaskStatus.FAILED,
                error.message
            );

            if (!task.ignoreErrors) {
                throw new TaskExecutionError(
                    `${host.name}: ${task.name}: ${error.message}`
                );
            }

            return result;
        }
    }

    async executeHost(host, play, checkMode) {
        if (host.reachable === false) {
            return [
                this.record(
                    host,
                    'connection',
                    TaskStatus.FAILED,
                    'Host unreachable'
                )
            ];
        }

        const variables = {
            ...this.inventory.variablesFor(host),
            ...(play.vars || {})
        };

        const notifications = new Set();
        const hostResults = [];

        for (const task of play.tasks) {
            try {
                const result = await this.executeTask(
                    host,
                    task,
                    variables,
                    checkMode
                );

                hostResults.push(result);

                if (result.status === TaskStatus.CHANGED) {
                    for (const handler of task.notify || []) {
                        notifications.add(handler);
                    }
                }
            } catch (error) {
                hostResults.push({
                    host: host.name,
                    task: 'execution',
                    status: TaskStatus.FAILED,
                    message: error.message
                });

                return hostResults;
            }
        }

        for (const handlerName of notifications) {
            const handler = (play.handlers || {})[handlerName];

            if (!handler) {
                hostResults.push(
                    this.record(
                        host,
                        `handler:${handlerName}`,
                        TaskStatus.FAILED,
                        'Handler not defined'
                    )
                );

                continue;
            }

            try {
                hostResults.push(
                    await this.executeTask(
                        host,
                        {
                            ...handler,
                            name: `handler:${handlerName}`
                        },
                        variables,
                        checkMode
                    )
                );
            } catch (error) {
                hostResults.push({
                    host: host.name,
                    task: `handler:${handlerName}`,
                    status: TaskStatus.FAILED,
                    message: error.message
                });
            }
        }

        return hostResults;
    }

    async executePlay(play, checkMode = false) {
        if (
            !play.name ||
            !Array.isArray(play.tasks) ||
            play.tasks.length === 0
        ) {
            throw new ConfigurationError(
                'Play requires a name and tasks.'
            );
        }

        const hosts = this.inventory.select(play.hosts);
        const output = [];

        // Bounded concurrency prevents uncontrolled host fan-out.
        for (
            let index = 0;
            index < hosts.length;
            index += this.maxConcurrency
        ) {
            const batch = hosts.slice(
                index,
                index + this.maxConcurrency
            );

            const results = await Promise.all(
                batch.map(host =>
                    this.executeHost(host, play, checkMode)
                )
            );

            output.push(...results.flat());
        }

        return output;
    }

    report() {
        const report = {};

        for (const result of this.results) {
            const host = report[result.host] ||= {
                ok: 0,
                changed: 0,
                failed: 0,
                skipped: 0
            };

            host[result.status]++;
        }

        return report;
    }
}

function createExample() {
    const inventory = new Inventory();

    inventory.addHost({
        name: 'web01',
        address: '192.168.10.11',
        port: 22,
        username: 'ansible',
        variables: { environment: 'production' }
    }, ['web']);

    inventory.addHost({
        name: 'web02',
        address: '192.168.10.12',
        port: 22,
        username: 'ansible',
        variables: { environment: 'production' }
    }, ['web']);

    inventory.addHost({
        name: 'db01',
        address: '192.168.10.21',
        port: 22,
        username: 'ansible',
        variables: {}
    }, ['database']);

    inventory.setGroupVariables('web', {
        package_name: 'nginx'
    });

    inventory.setGroupVariables('database', {
        package_name: 'postgresql'
    });

    const webPlay = {
        name: 'Configure web servers',
        hosts: 'web',
        vars: {
            service_enabled: true
        },
        tasks: [
            {
                name: 'Install nginx',
                module: 'package',
                args: {
                    name: '{{ package_name }}',
                    state: 'present'
                }
            },
            {
                name: 'Create application directory',
                module: 'file',
                args: {
                    path: '/srv/application',
                    state: 'directory',
                    mode: '0755'
                }
            },
            {
                name: 'Start nginx',
                module: 'service',
                args: {
                    name: 'nginx',
                    state: 'started',
                    enabled: '{{ service_enabled }}'
                },
                notify: ['reload_nginx']
            },
            {
                name: 'Validate HTTP configuration',
                module: 'command',
                args: { command: 'check_http' }
            }
        ],
        handlers: {
            reload_nginx: {
                module: 'service',
                args: {
                    name: 'nginx',
                    state: 'started',
                    enabled: true
                }
            }
        }
    };

    const databasePlay = {
        name: 'Configure database servers',
        hosts: 'database',
        tasks: [
            {
                name: 'Install PostgreSQL',
                module: 'package',
                args: {
                    name: '{{ package_name }}',
                    state: 'present'
                }
            },
            {
                name: 'Start PostgreSQL',
                module: 'service',
                args: {
                    name: 'postgresql',
                    state: 'started',
                    enabled: true
                }
            }
        ]
    };

    return {
        inventory,
        plays: [webPlay, databasePlay]
    };
}

async function main() {
    const checkMode = process.argv.includes('--check');
    const inventoryFile = process.argv.find(
        arg => arg.startsWith('--inventory=')
    );

    const { inventory: defaultInventory, plays } =
        createExample();

    let inventory = defaultInventory;

    if (inventoryFile) {
        const filename = inventoryFile.split('=').slice(1).join('=');

        try {
            const content = await fs.readFile(filename, 'utf8');
            inventory = Inventory.fromJSON(
                JSON.parse(content)
            );
        } catch (error) {
            throw new ConfigurationError(
                `Inventory loading failed: ${error.message}`
            );
        }
    }

    const engine = new PlaybookEngine(inventory);

    engine.on('taskComplete', result => {
        console.log(
            `[${result.status.toUpperCase()}]`,
            result.host,
            result.task,
            result.message
        );
    });

    for (const play of plays) {
        await engine.executePlay(play, checkMode);
    }

    console.log('\nExecution report:');
    console.log(JSON.stringify(engine.report(), null, 2));
}

main().catch(error => {
    console.error('Execution failed:', error.message);
    process.exitCode = 1;
});

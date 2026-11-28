"use strict";

/*
 * Ansible Roles: Event-Driven Configuration Management
 *
 * Features:
 * - Role definitions and dependency resolution
 * - Asynchronous task execution
 * - Inventory and host-specific configuration
 * - Variable resolution
 * - Event-driven handlers
 * - Idempotent resource management
 * - Tags and conditional execution
 * - Check mode
 * - Execution failures and reporting
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");

class ConfigurationError extends Error {}
class DependencyError extends ConfigurationError {}
class TaskError extends Error {}

const TaskStatus = Object.freeze({
    OK: "ok",
    CHANGED: "changed",
    FAILED: "failed",
    SKIPPED: "skipped"
});

function deepClone(value) {
    return structuredClone(value);
}

function validateName(name, type = "name") {
    if (
        typeof name !== "string" ||
        !/^[a-zA-Z0-9_-]+$/.test(name)
    ) {
        throw new ConfigurationError(
            `Invalid ${type}: ${String(name)}`
        );
    }
}

class Host {
    constructor(name, variables = {}) {
        validateName(name, "host name");

        this.name = name;
        this.variables = deepClone(variables);
        this.state = {
            packages: new Set(),
            services: new Map(),
            files: new Map(),
            restartCount: new Map()
        };

        this.failed = false;
    }

    snapshot() {
        return {
            name: this.name,
            packages: [...this.state.packages].sort(),
            services: Object.fromEntries(this.state.services),
            files: Object.fromEntries(this.state.files),
            restartCount: Object.fromEntries(
                this.state.restartCount
            ),
            failed: this.failed
        };
    }
}

class Task {
    constructor({
        name,
        action,
        tags = [],
        notify = [],
        condition = () => true,
        become = false
    }) {
        if (!name || typeof action !== "function") {
            throw new ConfigurationError(
                "A task requires a name and action."
            );
        }

        this.name = name;
        this.action = action;
        this.tags = new Set(tags);
        this.notify = [...notify];
        this.condition = condition;
        this.become = become;
    }
}

class Role {
    constructor({
        name,
        defaults = {},
        variables = {},
        dependencies = [],
        tasks = [],
        handlers = {},
        metadata = {}
    }) {
        validateName(name, "role name");

        this.name = name;
        this.defaults = deepClone(defaults);
        this.variables = deepClone(variables);
        this.dependencies = [...dependencies];
        this.tasks = [...tasks];
        this.handlers = new Map(Object.entries(handlers));
        this.metadata = deepClone(metadata);

        this.validate();
    }

    validate() {
        for (const dependency of this.dependencies) {
            validateName(dependency, "dependency");

            if (dependency === this.name) {
                throw new DependencyError(
                    `Role ${this.name} cannot depend on itself.`
                );
            }
        }

        for (const task of this.tasks) {
            for (const handler of task.notify) {
                if (!this.handlers.has(handler)) {
                    throw new ConfigurationError(
                        `Unknown handler ${handler} in ${this.name}.`
                    );
                }
            }
        }
    }
}

class RoleRegistry {
    constructor() {
        this.roles = new Map();
    }

    register(role) {
        if (!(role instanceof Role)) {
            throw new ConfigurationError(
                "Only Role instances can be registered."
            );
        }

        if (this.roles.has(role.name)) {
            throw new ConfigurationError(
                `Duplicate role: ${role.name}`
            );
        }

        this.roles.set(role.name, role);
    }

    resolve(requested) {
        const visited = new Set();
        const active = new Set();
        const result = [];

        const visit = (name) => {
            if (!this.roles.has(name)) {
                throw new DependencyError(
                    `Missing dependency: ${name}`
                );
            }

            if (active.has(name)) {
                throw new DependencyError(
                    `Circular dependency at ${name}`
                );
            }

            if (visited.has(name)) return;

            active.add(name);

            const role = this.roles.get(name);

            for (const dependency of role.dependencies) {
                visit(dependency);
            }

            active.delete(name);
            visited.add(name);
            result.push(role);
        };

        for (const name of requested) {
            visit(name);
        }

        return result;
    }
}

class VariableResolver {
    static resolve(role, host, playVariables, extraVariables) {
        return Object.assign(
            {},
            deepClone(role.defaults),
            deepClone(host.variables),
            deepClone(role.variables),
            deepClone(playVariables),
            deepClone(extraVariables)
        );
    }
}

class RoleExecutor extends EventEmitter {
    constructor({
        registry,
        checkMode = false,
        tags = [],
        playVariables = {},
        extraVariables = {},
        concurrency = 4
    }) {
        super();

        if (!Number.isInteger(concurrency) || concurrency < 1) {
            throw new ConfigurationError(
                "Concurrency must be a positive integer."
            );
        }

        this.registry = registry;
        this.checkMode = checkMode;
        this.tags = new Set(tags);
        this.playVariables = deepClone(playVariables);
        this.extraVariables = deepClone(extraVariables);
        this.concurrency = concurrency;

        this.results = [];
        this.pendingHandlers = new Map();
    }

    record(host, role, task, status, message) {
        const result = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            host: host.name,
            role: role.name,
            task,
            status,
            message
        };

        this.results.push(result);
        this.emit("task", result);

        return result;
    }

    async executeTask(host, role, task, variables) {
        if (host.failed) {
            return;
        }

        if (
            this.tags.size > 0 &&
            ![...task.tags].some(tag => this.tags.has(tag)) &&
            !task.tags.has("always")
        ) {
            this.record(
                host,
                role,
                task.name,
                TaskStatus.SKIPPED,
                "No matching execution tag."
            );
            return;
        }

        try {
            if (!(await task.condition(host, variables))) {
                this.record(
                    host,
                    role,
                    task.name,
                    TaskStatus.SKIPPED,
                    "Condition evaluated to false."
                );
                return;
            }

            if (this.checkMode) {
                this.record(
                    host,
                    role,
                    task.name,
                    TaskStatus.OK,
                    "Check mode: no state modification."
                );
                return;
            }

            const outcome = await task.action(host, variables);

            if (
                !outcome ||
                typeof outcome.changed !== "boolean"
            ) {
                throw new TaskError(
                    "Task action must return a changed boolean."
                );
            }

            this.record(
                host,
                role,
                task.name,
                outcome.changed
                    ? TaskStatus.CHANGED
                    : TaskStatus.OK,
                outcome.message || "Task completed."
            );

            if (outcome.changed) {
                for (const handler of task.notify) {
                    const key = `${role.name}:${handler}`;

                    if (!this.pendingHandlers.has(key)) {
                        this.pendingHandlers.set(key, {
                            role,
                            handler,
                            hosts: new Set()
                        });
                    }

                    this.pendingHandlers.get(key).hosts.add(host);
                }
            }
        } catch (error) {
            host.failed = true;

            this.record(
                host,
                role,
                task.name,
                TaskStatus.FAILED,
                error.message
            );
        }
    }

    async runLimited(hosts, role, task) {
        let index = 0;

        const workers = Array.from(
            { length: Math.min(this.concurrency, hosts.length) },
            async () => {
                while (index < hosts.length) {
                    const host = hosts[index++];

                    if (host.failed) continue;

                    const variables = VariableResolver.resolve(
                        role,
                        host,
                        this.playVariables,
                        this.extraVariables
                    );

                    await this.executeTask(
                        host,
                        role,
                        task,
                        variables
                    );
                }
            }
        );

        await Promise.all(workers);
    }

    async flushHandlers() {
        const notifications = [...this.pendingHandlers.values()];

        this.pendingHandlers.clear();

        for (const notification of notifications) {
            const { role, handler, hosts } = notification;
            const action = role.handlers.get(handler);

            for (const host of hosts) {
                if (host.failed) continue;

                try {
                    const variables = VariableResolver.resolve(
                        role,
                        host,
                        this.playVariables,
                        this.extraVariables
                    );

                    const result = await action(host, variables);

                    this.record(
                        host,
                        role,
                        `handler:${handler}`,
                        result.changed
                            ? TaskStatus.CHANGED
                            : TaskStatus.OK,
                        result.message
                    );
                } catch (error) {
                    host.failed = true;

                    this.record(
                        host,
                        role,
                        `handler:${handler}`,
                        TaskStatus.FAILED,
                        error.message
                    );
                }
            }
        }
    }

    async run(hosts, requestedRoles) {
        if (!Array.isArray(hosts) || hosts.length === 0) {
            throw new ConfigurationError(
                "Inventory cannot be empty."
            );
        }

        const roles = this.registry.resolve(requestedRoles);

        for (const role of roles) {
            // Tasks execute in declared order. Hosts execute concurrently.
            for (const task of role.tasks) {
                await this.runLimited(hosts, role, task);
            }

            // Handlers execute after the role's task sequence.
            await this.flushHandlers();
        }

        this.emit("complete", this.report());

        return this.results;
    }

    report() {
        const report = Object.fromEntries(
            Object.values(TaskStatus).map(
                status => [status, 0]
            )
        );

        for (const result of this.results) {
            report[result.status]++;
        }

        return report;
    }
}

// Resource actions.

function installPackage(packageName) {
    return async host => {
        if (!/^[a-zA-Z0-9.+_-]+$/.test(packageName)) {
            throw new TaskError("Invalid package name.");
        }

        if (host.state.packages.has(packageName)) {
            return {
                changed: false,
                message: `${packageName} already installed.`
            };
        }

        host.state.packages.add(packageName);

        return {
            changed: true,
            message: `Installed ${packageName}.`
        };
    };
}

function manageService(serviceName, desiredState = "running") {
    return async host => {
        if (!["running", "stopped"].includes(desiredState)) {
            throw new TaskError("Invalid service state.");
        }

        if (host.state.services.get(serviceName) === desiredState) {
            return {
                changed: false,
                message: `${serviceName} already ${desiredState}.`
            };
        }

        host.state.services.set(serviceName, desiredState);

        return {
            changed: true,
            message: `Service ${serviceName} is ${desiredState}.`
        };
    };
}

function deployFile(path, contentVariable) {
    return async (host, variables) => {
        if (!path.startsWith("/etc/")) {
            throw new TaskError(
                "Configuration path must be under /etc/."
            );
        }

        const content = variables[contentVariable];

        if (typeof content !== "string") {
            throw new TaskError(
                `Invalid configuration variable: ${contentVariable}`
            );
        }

        if (host.state.files.get(path) === content) {
            return {
                changed: false,
                message: "Configuration already current."
            };
        }

        host.state.files.set(path, content);

        return {
            changed: true,
            message: `Updated ${path}.`
        };
    };
}

function restartService(serviceName) {
    return async host => {
        if (host.state.services.get(serviceName) !== "running") {
            throw new TaskError(
                `Cannot restart stopped service ${serviceName}.`
            );
        }

        const count = host.state.restartCount.get(serviceName) || 0;

        host.state.restartCount.set(serviceName, count + 1);

        return {
            changed: true,
            message: `Restarted ${serviceName}.`
        };
    };
}

// A basic atomic JSON inventory export.
// Production deployments should use access controls and restrictive
// filesystem permissions for inventory and configuration files.
async function exportReport(filePath, hosts, report) {
    const payload = {
        generatedAt: new Date().toISOString(),
        report,
        hosts: hosts.map(host => host.snapshot())
    };

    const temporaryPath = `${filePath}.tmp`;

    try {
        await fs.writeFile(
            temporaryPath,
            JSON.stringify(payload, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );

        await fs.rename(temporaryPath, filePath);
    } catch (error) {
        await fs.rm(temporaryPath, { force: true }).catch(() => {});
        throw error;
    }
}

function buildRegistry() {
    const registry = new RoleRegistry();

    registry.register(new Role({
        name: "base",
        defaults: {
            timezone: "UTC"
        },
        tasks: [
            new Task({
                name: "Install curl",
                tags: ["packages", "base"],
                action: installPackage("curl")
            })
        ]
    }));

    registry.register(new Role({
        name: "webserver",
        defaults: {
            nginx_config:
                "server { listen 8080; server_name app.internal; }"
        },
        dependencies: ["base"],
        handlers: {
            "reload nginx": restartService("nginx")
        },
        tasks: [
            new Task({
                name: "Install nginx",
                tags: ["packages", "web"],
                action: installPackage("nginx")
            }),
            new Task({
                name: "Deploy nginx configuration",
                tags: ["configuration", "web"],
                notify: ["reload nginx"],
                action: deployFile(
                    "/etc/nginx/nginx.conf",
                    "nginx_config"
                )
            }),
            new Task({
                name: "Start nginx",
                tags: ["services", "web"],
                action: manageService("nginx")
            })
        ],
        metadata: {
            version: "1.0.0",
            description: "Reusable web server configuration"
        }
    }));

    registry.register(new Role({
        name: "monitoring",
        defaults: {
            monitoring_enabled: true
        },
        tasks: [
            new Task({
                name: "Install node exporter",
                tags: ["monitoring"],
                condition: (_, variables) =>
                    variables.monitoring_enabled === true,
                action: installPackage("node-exporter")
            })
        ]
    }));

    return registry;
}

async function main() {
    const registry = buildRegistry();

    const hosts = [
        new Host("web-01", {
            environment: "production"
        }),
        new Host("web-02", {
            environment: "staging",
            monitoring_enabled: false
        })
    ];

    const executor = new RoleExecutor({
        registry,
        concurrency: 2,
        playVariables: {
            nginx_config:
                "server { listen 8080; server_name production.internal; }"
        }
    });

    executor.on("task", result => {
        console.log(
            `[${result.status.toUpperCase()}]`,
            result.host,
            result.role,
            result.task
        );
    });

    executor.on("complete", report => {
        console.log("\nExecution report:", report);
    });

    await executor.run(
        hosts,
        ["webserver", "monitoring"]
    );

    console.log("\nHost states:");

    console.log(
        JSON.stringify(
            hosts.map(host => host.snapshot()),
            null,
            2
        )
    );

    // A second execution verifies idempotence.
    const secondRun = new RoleExecutor({ registry });

    await secondRun.run(
        hosts,
        ["webserver", "monitoring"]
    );

    if (
        secondRun.results.some(
            result => result.status === TaskStatus.CHANGED
        )
    ) {
        throw new Error("Idempotence verification failed.");
    }

    console.log("\nIdempotence verification passed.");

    // Check mode does not mutate host state.
    const before = JSON.stringify(
        hosts.map(host => host.snapshot())
    );

    const checkExecutor = new RoleExecutor({
        registry,
        checkMode: true
    });

    await checkExecutor.run(hosts, ["webserver"]);

    const after = JSON.stringify(
        hosts.map(host => host.snapshot())
    );

    if (before !== after) {
        throw new Error("Check mode modified host state.");
    }

    console.log("Check mode verification passed.");

    // Dependency cycle detection.
    const cyclic = new RoleRegistry();

    cyclic.register(new Role({
        name: "alpha",
        dependencies: ["beta"]
    }));

    cyclic.register(new Role({
        name: "beta",
        dependencies: ["alpha"]
    }));

    try {
        cyclic.resolve(["alpha"]);
    } catch (error) {
        if (!(error instanceof DependencyError)) throw error;
        console.log("Cycle validation passed:", error.message);
    }

    // Export the final execution report.
    await exportReport(
        "ansible-roles-report.json",
        hosts,
        executor.report()
    );

    console.log("Execution report exported.");
}

main().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});

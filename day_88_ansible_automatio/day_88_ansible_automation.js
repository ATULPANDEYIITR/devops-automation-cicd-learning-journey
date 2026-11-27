"use strict";

/*
 * Ansible Automation: Variables, Handlers, Templates, and Conditionals.
 *
 * Event-driven configuration management simulation.
 *
 * Features:
 * - Layered variable resolution.
 * - Immutable execution context snapshots.
 * - Conditional task evaluation.
 * - Template rendering.
 * - Idempotent configuration changes.
 * - Event-driven handler notifications.
 * - Handler deduplication and execution ordering.
 * - Asynchronous task execution.
 * - Host failure isolation.
 * - Structured execution reports.
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");

class AutomationError extends Error {
    constructor(message, code = "AUTOMATION_ERROR") {
        super(message);
        this.name = "AutomationError";
        this.code = code;
    }
}

class VariableError extends AutomationError {
    constructor(message) {
        super(message, "VARIABLE_ERROR");
    }
}

class TemplateError extends AutomationError {
    constructor(message) {
        super(message, "TEMPLATE_ERROR");
    }
}

const PRECEDENCE = [
    "defaults",
    "inventory",
    "groupVars",
    "hostVars",
    "playVars",
    "taskVars",
    "extraVars"
];

function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
        Object.freeze(value);

        for (const child of Object.values(value)) {
            deepFreeze(child);
        }
    }

    return value;
}

class VariableStore {
    constructor(sources = {}) {
        this.sources = sources;
    }

    resolve() {
        const resolved = Object.create(null);

        for (const source of PRECEDENCE) {
            const values = this.sources[source] ?? {};

            if (
                typeof values !== "object" ||
                values === null ||
                Array.isArray(values)
            ) {
                throw new VariableError(
                    `Invalid variable source: ${source}`
                );
            }

            Object.assign(resolved, values);
        }

        return deepFreeze({ ...resolved });
    }

    static validate(variables) {
        const required = [
            "applicationName",
            "applicationPort",
            "applicationDirectory",
            "serviceName",
            "applicationVersion"
        ];

        for (const key of required) {
            if (
                variables[key] === undefined ||
                variables[key] === null ||
                variables[key] === ""
            ) {
                throw new VariableError(
                    `Required variable is missing: ${key}`
                );
            }
        }

        if (
            !Number.isInteger(variables.applicationPort) ||
            variables.applicationPort < 1 ||
            variables.applicationPort > 65535
        ) {
            throw new VariableError("Invalid application port");
        }

        if (!path.posix.isAbsolute(variables.applicationDirectory)) {
            throw new VariableError(
                "Application directory must be absolute"
            );
        }
    }
}

class TemplateRenderer {
    static render(template, variables) {
        if (typeof template !== "string") {
            throw new TemplateError("Template must be a string");
        }

        return template.replace(
            /{{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*}}/g,
            (_, expression) => {
                const value = expression
                    .split(".")
                    .reduce((current, key) => {
                        if (
                            current === null ||
                            typeof current !== "object" ||
                            !(key in current)
                        ) {
                            throw new TemplateError(
                                `Undefined variable: ${expression}`
                            );
                        }

                        return current[key];
                    }, variables);

                if (
                    value === null ||
                    typeof value === "object" ||
                    typeof value === "undefined"
                ) {
                    throw new TemplateError(
                        `Unsupported template value: ${expression}`
                    );
                }

                return String(value);
            }
        );
    }
}

class Host {
    constructor(name, groups = []) {
        if (!name || typeof name !== "string") {
            throw new AutomationError("Host name is required");
        }

        this.name = name;
        this.groups = new Set(groups);
        this.state = {
            directories: new Set(),
            files: new Map(),
            services: new Map(),
            facts: new Map()
        };
        this.failed = false;
    }
}

class Task {
    constructor({
        name,
        action,
        when = async () => true,
        notify = [],
        tags = []
    }) {
        if (!name || typeof action !== "function") {
            throw new AutomationError(
                "A task requires a name and an action"
            );
        }

        this.name = name;
        this.action = action;
        this.when = when;
        this.notify = notify;
        this.tags = new Set(tags);
    }
}

class Handler {
    constructor({ name, action, listen = [] }) {
        this.name = name;
        this.action = action;
        this.listen = new Set(listen);
    }
}

class AutomationEngine extends EventEmitter {
    constructor() {
        super();

        this.hosts = new Map();
        this.tasks = [];
        this.handlers = new Map();
        this.handlerEvents = new Map();
        this.results = [];
        this.pending = new Map();
        this.variables = new Map();

        this.on("handler-notification", event => {
            this.queueHandler(event.host, event.notification);
        });
    }

    addHost(host, variables) {
        if (this.hosts.has(host.name)) {
            throw new AutomationError(
                `Duplicate host: ${host.name}`
            );
        }

        VariableStore.validate(variables);

        this.hosts.set(host.name, host);
        this.variables.set(host.name, variables);
    }

    addTask(task) {
        this.tasks.push(task);
    }

    addHandler(handler) {
        if (this.handlers.has(handler.name)) {
            throw new AutomationError(
                `Duplicate handler: ${handler.name}`
            );
        }

        this.handlers.set(handler.name, handler);

        for (const event of handler.listen) {
            if (!this.handlerEvents.has(event)) {
                this.handlerEvents.set(event, new Set());
            }

            this.handlerEvents.get(event).add(handler.name);
        }
    }

    queueHandler(host, notification) {
        const matched = new Set();

        if (this.handlers.has(notification)) {
            matched.add(notification);
        }

        for (
            const handlerName of
            this.handlerEvents.get(notification) ?? []
        ) {
            matched.add(handlerName);
        }

        if (matched.size === 0) {
            throw new AutomationError(
                `Unknown handler: ${notification}`
            );
        }

        if (!this.pending.has(host.name)) {
            this.pending.set(host.name, new Set());
        }

        const queue = this.pending.get(host.name);

        for (const handlerName of matched) {
            queue.add(handlerName);
        }
    }

    record(host, task, status, message) {
        this.results.push({
            host: host.name,
            task,
            status,
            message,
            timestamp: new Date().toISOString()
        });
    }

    async executeTask(task, host) {
        if (host.failed) return;

        const variables = this.variables.get(host.name);

        try {
            const eligible = await task.when(host, variables);

            if (!eligible) {
                this.record(
                    host,
                    task.name,
                    "skipped",
                    "Conditional expression evaluated to false"
                );
                return;
            }

            const changed = Boolean(
                await task.action(host, variables)
            );

            this.record(
                host,
                task.name,
                changed ? "changed" : "ok",
                "Task completed"
            );

            if (changed) {
                for (const notification of task.notify) {
                    this.emit("handler-notification", {
                        host,
                        notification
                    });
                }
            }
        } catch (error) {
            host.failed = true;

            this.record(
                host,
                task.name,
                "failed",
                error.message
            );
        }
    }

    async flushHandlers(host) {
        const queue = this.pending.get(host.name);

        if (!queue || host.failed) return;

        this.pending.delete(host.name);

        // Registration order is preserved independently of
        // notification order.
        for (const [handlerName, handler] of this.handlers) {
            if (!queue.has(handlerName)) continue;

            try {
                const changed = Boolean(
                    await handler.action(
                        host,
                        this.variables.get(host.name)
                    )
                );

                this.record(
                    host,
                    `Handler: ${handlerName}`,
                    changed ? "changed" : "ok",
                    "Handler executed"
                );
            } catch (error) {
                host.failed = true;

                this.record(
                    host,
                    `Handler: ${handlerName}`,
                    "failed",
                    error.message
                );

                break;
            }
        }
    }

    async run() {
        for (const task of this.tasks) {
            // Hosts run concurrently for each task, while task
            // ordering remains consistent across the play.
            await Promise.all(
                [...this.hosts.values()].map(
                    host => this.executeTask(task, host)
                )
            );

            await Promise.all(
                [...this.hosts.values()].map(
                    host => this.flushHandlers(host)
                )
            );
        }

        return this.report();
    }

    report() {
        const report = {};

        for (const [hostName, host] of this.hosts) {
            const entries = this.results.filter(
                result => result.host === hostName
            );

            report[hostName] = {
                failed: host.failed,
                counts: {
                    changed: entries.filter(
                        item => item.status === "changed"
                    ).length,
                    ok: entries.filter(
                        item => item.status === "ok"
                    ).length,
                    skipped: entries.filter(
                        item => item.status === "skipped"
                    ).length,
                    failed: entries.filter(
                        item => item.status === "failed"
                    ).length
                },
                results: entries
            };
        }

        return report;
    }
}

async function createApplicationDirectory(host, variables) {
    const directory = variables.applicationDirectory;

    if (host.state.directories.has(directory)) {
        return false;
    }

    host.state.directories.add(directory);
    return true;
}

async function deployApplication(host, variables) {
    const previous = host.state.facts.get("applicationVersion");

    if (previous === variables.applicationVersion) {
        return false;
    }

    host.state.facts.set(
        "applicationVersion",
        variables.applicationVersion
    );

    return true;
}

async function renderConfiguration(host, variables) {
    const template = [
        "server {",
        "    listen {{ applicationPort }};",
        "    server_name {{ applicationName }};",
        "    environment {{ environment }};",
        "}"
    ].join("\n");

    const content = TemplateRenderer.render(
        template,
        variables
    );

    const destination = path.posix.join(
        variables.applicationDirectory,
        "application.conf"
    );

    if (host.state.files.get(destination) === content) {
        return false;
    }

    host.state.files.set(destination, content);
    return true;
}

async function restartService(host, variables) {
    host.state.services.set(
        variables.serviceName,
        "running"
    );

    host.state.facts.set("lastRestart", Date.now());

    return true;
}

async function verifyService(host, variables) {
    if (
        host.state.facts.get("applicationVersion") === undefined
    ) {
        throw new AutomationError(
            "Application version has not been deployed"
        );
    }

    if (
        host.state.services.get(variables.serviceName) !== "running"
    ) {
        throw new AutomationError(
            "Application service is not running"
        );
    }

    return false;
}

async function main() {
    const engine = new AutomationEngine();

    const commonVariables = new VariableStore({
        defaults: {
            applicationName: "inventory-api",
            applicationPort: 8080,
            applicationDirectory: "/opt/inventory",
            serviceName: "inventory-api",
            applicationVersion: "1.0.0",
            environment: "development"
        },
        groupVars: {
            environment: "production"
        },
        hostVars: {}
    }).resolve();

    const hosts = [
        new Host("web01.example.internal", ["web"]),
        new Host("web02.example.internal", ["web", "canary"])
    ];

    engine.addHost(hosts[0], commonVariables);

    engine.addHost(
        hosts[1],
        new VariableStore({
            defaults: commonVariables,
            hostVars: {
                applicationPort: 8081
            }
        }).resolve()
    );

    engine.addHandler(
        new Handler({
            name: "restart application",
            action: restartService,
            listen: ["application configuration changed"]
        })
    );

    engine.addTask(
        new Task({
            name: "Create application directory",
            action: createApplicationDirectory
        })
    );

    engine.addTask(
        new Task({
            name: "Deploy application",
            action: deployApplication,
            notify: ["application configuration changed"]
        })
    );

    engine.addTask(
        new Task({
            name: "Render configuration",
            action: renderConfiguration,
            notify: ["restart application"],
            when: async (_, variables) =>
                variables.environment === "production"
        })
    );

    engine.addTask(
        new Task({
            name: "Verify service",
            action: verifyService,
            when: async host => host.groups.has("web")
        })
    );

    const report = await engine.run();

    console.log(JSON.stringify(report, null, 2));

    if (
        [...engine.hosts.values()].some(host => host.failed)
    ) {
        process.exitCode = 1;
    }
}

if (require.main === module) {
    main().catch(error => {
        console.error("Automation failed:", error.message);
        process.exitCode = 1;
    });
}

module.exports = {
    AutomationEngine,
    VariableStore,
    TemplateRenderer,
    Host,
    Task,
    Handler
};

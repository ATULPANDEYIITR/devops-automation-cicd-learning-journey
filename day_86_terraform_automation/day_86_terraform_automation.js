"use strict";

/*
 * Terraform Automation Integrated with CI/CD
 *
 * Event-driven infrastructure pipeline model.
 *
 * Features:
 * - EventEmitter-based pipeline monitoring
 * - Asynchronous stage execution
 * - Configuration policy evaluation
 * - Plan artifact verification
 * - Approval quorum
 * - Deployment concurrency control
 * - Environment-specific policies
 * - Drift evaluation
 * - Audit events
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const { spawn } = require("node:child_process");


class PipelineError extends Error {
    constructor(message, code = "PIPELINE_ERROR") {
        super(message);
        this.name = "PipelineError";
        this.code = code;
    }
}


const Stage = Object.freeze({
    CREATED: "CREATED",
    VALIDATING: "VALIDATING",
    INITIALIZING: "INITIALIZING",
    PLANNING: "PLANNING",
    SCANNING: "SCANNING",
    REVIEW: "REVIEW",
    APPLYING: "APPLYING",
    SUCCEEDED: "SUCCEEDED",
    FAILED: "FAILED",
    CANCELLED: "CANCELLED"
});


const Environment = Object.freeze({
    DEVELOPMENT: "development",
    STAGING: "staging",
    PRODUCTION: "production"
});


const AllowedTransitions = Object.freeze({
    CREATED: ["VALIDATING", "CANCELLED"],
    VALIDATING: ["INITIALIZING", "FAILED", "CANCELLED"],
    INITIALIZING: ["PLANNING", "FAILED", "CANCELLED"],
    PLANNING: ["SCANNING", "REVIEW", "FAILED", "CANCELLED"],
    SCANNING: ["REVIEW", "FAILED", "CANCELLED"],
    REVIEW: ["APPLYING", "FAILED", "CANCELLED"],
    APPLYING: ["SUCCEEDED", "FAILED", "CANCELLED"],
    SUCCEEDED: [],
    FAILED: [],
    CANCELLED: []
});


class AuditLogger extends EventEmitter {
    constructor() {
        super();
        this.events = [];
    }

    record(type, details = {}) {
        const event = Object.freeze({
            eventId: crypto.randomUUID(),
            type,
            timestamp: new Date().toISOString(),
            details: structuredClone(details)
        });

        this.events.push(event);
        this.emit(type, event);
        this.emit("audit", event);

        return event;
    }

    export() {
        return structuredClone(this.events);
    }
}


class ConfigurationPolicy {
    constructor(options = {}) {
        this.maxResourceCount = options.maxResourceCount ?? 100;
        this.requireEncryption = options.requireEncryption ?? true;
        this.blockPublicIngress = options.blockPublicIngress ?? true;
        this.allowDestroy = options.allowDestroy ?? false;
        this.allowedProviders = new Set(
            options.allowedProviders ?? ["aws", "azurerm", "google"]
        );
    }

    evaluate(configuration) {
        const violations = [];

        if (!Array.isArray(configuration.resources)) {
            throw new PipelineError(
                "Configuration resources must be an array",
                "INVALID_CONFIGURATION"
            );
        }

        if (configuration.resources.length > this.maxResourceCount) {
            violations.push("Resource count exceeds policy limit");
        }

        for (const resource of configuration.resources) {
            if (!resource.type || !resource.name) {
                violations.push("Resource type and name are required");
                continue;
            }

            const provider = resource.type.split("_")[0];

            if (!this.allowedProviders.has(provider)) {
                violations.push(
                    `Provider not permitted: ${provider}`
                );
            }

            if (
                this.requireEncryption &&
                resource.encrypted === false
            ) {
                violations.push(
                    `Encryption disabled: ${resource.name}`
                );
            }

            if (
                this.blockPublicIngress &&
                resource.publicIngress === true
            ) {
                violations.push(
                    `Public ingress prohibited: ${resource.name}`
                );
            }

            if (
                !this.allowDestroy &&
                resource.action === "delete"
            ) {
                violations.push(
                    `Resource destruction prohibited: ${resource.name}`
                );
            }
        }

        return Object.freeze({
            passed: violations.length === 0,
            violations: Object.freeze(violations)
        });
    }
}


class ApprovalManager {
    constructor(requiredApprovals = 1) {
        if (
            !Number.isInteger(requiredApprovals) ||
            requiredApprovals < 0
        ) {
            throw new PipelineError("Invalid approval requirement");
        }

        this.requiredApprovals = requiredApprovals;
        this.decisions = new Map();
    }

    decide(reviewer, decision, comment = "") {
        if (!reviewer || !reviewer.trim()) {
            throw new PipelineError("Reviewer identity is required");
        }

        if (!["approved", "rejected"].includes(decision)) {
            throw new PipelineError("Invalid approval decision");
        }

        if (this.decisions.has(reviewer)) {
            throw new PipelineError(
                "Reviewer already submitted a decision"
            );
        }

        this.decisions.set(reviewer, Object.freeze({
            reviewer,
            decision,
            comment,
            timestamp: new Date().toISOString()
        }));
    }

    evaluate() {
        const decisions = [...this.decisions.values()];

        const rejected = decisions.some(
            item => item.decision === "rejected"
        );

        const approved = decisions.filter(
            item => item.decision === "approved"
        ).length;

        return Object.freeze({
            eligible: !rejected &&
                approved >= this.requiredApprovals,
            approved,
            required: this.requiredApprovals,
            rejected
        });
    }
}


class DeploymentLock {
    constructor() {
        this.owners = new Map();
    }

    acquire(environment, runId) {
        if (this.owners.has(environment)) {
            throw new PipelineError(
                `Environment ${environment} is locked`,
                "LOCK_CONFLICT"
            );
        }

        this.owners.set(environment, runId);
    }

    release(environment, runId) {
        if (this.owners.get(environment) !== runId) {
            throw new PipelineError(
                "Deployment lock ownership mismatch"
            );
        }

        this.owners.delete(environment);
    }
}


class TerraformCommandRunner {
    constructor(directory, enabled = false, timeout = 300000) {
        this.directory = path.resolve(directory);
        this.enabled = enabled;
        this.timeout = timeout;
    }

    async run(args) {
        if (!this.enabled) {
            return {
                simulated: true,
                command: `terraform ${args.join(" ")}`
            };
        }

        return new Promise((resolve, reject) => {
            const child = spawn("terraform", args, {
                cwd: this.directory,
                shell: false,
                windowsHide: true,
                stdio: ["ignore", "pipe", "pipe"]
            });

            let stdout = "";
            let stderr = "";
            let finished = false;

            const timer = setTimeout(() => {
                if (!finished) {
                    child.kill("SIGTERM");
                    reject(new PipelineError("Terraform timed out"));
                }
            }, this.timeout);

            child.stdout.setEncoding("utf8");
            child.stderr.setEncoding("utf8");

            child.stdout.on("data", chunk => {
                stdout += chunk;
            });

            child.stderr.on("data", chunk => {
                stderr += chunk;
            });

            child.on("error", error => {
                finished = true;
                clearTimeout(timer);
                reject(error);
            });

            child.on("close", code => {
                finished = true;
                clearTimeout(timer);

                if (code !== 0) {
                    reject(new PipelineError(
                        `Terraform failed (${code}): ${stderr.slice(-2000)}`
                    ));
                    return;
                }

                resolve({ stdout, stderr, code });
            });
        });
    }
}


class PlanArtifact {
    constructor({
        runId,
        environment,
        configurationHash,
        additions,
        changes,
        destructions
    }) {
        this.id = crypto.randomUUID();
        this.runId = runId;
        this.environment = environment;
        this.configurationHash = configurationHash;
        this.additions = additions;
        this.changes = changes;
        this.destructions = destructions;
        this.createdAt = new Date().toISOString();
        this.applied = false;

        Object.seal(this);
    }

    validate(policy) {
        if (
            !policy.allowDestroy &&
            this.destructions > 0
        ) {
            throw new PipelineError(
                "Plan contains prohibited destruction"
            );
        }

        if (
            !Number.isInteger(this.additions) ||
            !Number.isInteger(this.changes) ||
            !Number.isInteger(this.destructions) ||
            this.additions < 0 ||
            this.changes < 0 ||
            this.destructions < 0
        ) {
            throw new PipelineError("Invalid plan metrics");
        }
    }
}


class TerraformPipeline extends EventEmitter {
    constructor(options) {
        super();

        this.id = crypto.randomUUID();
        this.environment = options.environment;
        this.directory = path.resolve(options.directory);
        this.policy = options.policy;
        this.approvals = options.approvals;
        this.runner = options.runner;
        this.audit = options.audit;
        this.lock = options.lock;

        this.stage = Stage.CREATED;
        this.plan = null;
        this.cancelled = false;
        this.startedAt = new Date().toISOString();
    }

    transition(next) {
        const allowed = AllowedTransitions[this.stage];

        if (!allowed.includes(next)) {
            throw new PipelineError(
                `Invalid transition: ${this.stage} -> ${next}`
            );
        }

        const previous = this.stage;
        this.stage = next;

        this.audit.record("stage_changed", {
            runId: this.id,
            previous,
            next
        });

        this.emit("stage", { previous, next });
    }

    checkCancellation() {
        if (this.cancelled) {
            throw new PipelineError(
                "Pipeline cancellation requested",
                "CANCELLED"
            );
        }
    }

    cancel() {
        if (
            [Stage.SUCCEEDED, Stage.FAILED, Stage.CANCELLED]
                .includes(this.stage)
        ) {
            throw new PipelineError(
                "Terminal pipeline cannot be cancelled"
            );
        }

        this.cancelled = true;
        this.audit.record("cancellation_requested", {
            runId: this.id
        });
    }

    async inspectConfiguration() {
        const files = (await fs.readdir(this.directory))
            .filter(file => file.endsWith(".tf"))
            .sort();

        if (files.length === 0) {
            throw new PipelineError(
                "No Terraform configuration files found"
            );
        }

        const resources = [];
        const hash = crypto.createHash("sha256");

        for (const file of files) {
            const fullPath = path.join(this.directory, file);
            const content = await fs.readFile(fullPath, "utf8");

            hash.update(file);
            hash.update(content);

            const expression =
                /^\s*resource\s+"([^"]+)"\s+"([^"]+)"/gm;

            for (
                let match;
                (match = expression.exec(content)) !== null;
            ) {
                resources.push({
                    type: match[1],
                    name: match[2]
                });
            }
        }

        return {
            resources,
            configurationHash: hash.digest("hex"),
            fileCount: files.length
        };
    }

    async validate() {
        this.transition(Stage.VALIDATING);
        this.checkCancellation();

        const configuration = await this.inspectConfiguration();

        const result = this.policy.evaluate(configuration);

        if (!result.passed) {
            throw new PipelineError(
                result.violations.join("; "),
                "POLICY_REJECTED"
            );
        }

        await this.runner.run(["fmt", "-check", "-recursive"]);
        await this.runner.run(["validate", "-no-color"]);

        this.audit.record("configuration_validated", {
            runId: this.id,
            resources: configuration.resources.length
        });

        return configuration;
    }

    async initialize() {
        this.transition(Stage.INITIALIZING);
        this.checkCancellation();

        await this.runner.run([
            "init",
            "-input=false",
            "-lockfile=readonly"
        ]);
    }

    async generatePlan(configuration) {
        this.transition(Stage.PLANNING);
        this.checkCancellation();

        await this.runner.run([
            "plan",
            "-input=false",
            "-lock-timeout=60s",
            "-out",
            "pipeline.tfplan"
        ]);

        // These metrics represent a controlled demonstration.
        // Real metrics must come from the saved Terraform plan.
        this.plan = new PlanArtifact({
            runId: this.id,
            environment: this.environment,
            configurationHash: configuration.configurationHash,
            additions: 2,
            changes: 1,
            destructions: 0
        });

        this.plan.validate(this.policy);

        this.audit.record("plan_created", {
            runId: this.id,
            planId: this.plan.id,
            additions: this.plan.additions,
            changes: this.plan.changes,
            destructions: this.plan.destructions
        });
    }

    async securityScan() {
        this.transition(Stage.SCANNING);
        this.checkCancellation();

        const files = (await fs.readdir(this.directory))
            .filter(file => file.endsWith(".tf"));

        const findings = [];

        for (const file of files) {
            const content = await fs.readFile(
                path.join(this.directory, file),
                "utf8"
            );

            if (/secret_key\s*=\s*"[^"]+"/i.test(content)) {
                findings.push(`${file}: hardcoded secret`);
            }

            if (/encrypted\s*=\s*false/i.test(content)) {
                findings.push(`${file}: encryption disabled`);
            }

            if (/0\.0\.0\.0\/0/.test(content)) {
                findings.push(`${file}: public ingress`);
            }
        }

        if (findings.length > 0) {
            throw new PipelineError(
                findings.join("; "),
                "SECURITY_FAILURE"
            );
        }
    }

    async review() {
        this.transition(Stage.REVIEW);
        this.checkCancellation();

        const decision = this.approvals.evaluate();

        if (!decision.eligible) {
            throw new PipelineError(
                `Approval requirement not met: ${decision.approved}/${decision.required}`,
                "APPROVAL_REQUIRED"
            );
        }

        this.plan.approved = true;
    }

    async apply() {
        this.checkCancellation();

        if (!this.plan || !this.plan.approved) {
            throw new PipelineError(
                "An approved plan is required"
            );
        }

        this.transition(Stage.APPLYING);

        this.lock.acquire(this.environment, this.id);

        try {
            this.checkCancellation();

            // Applying the saved plan prevents an implicit
            // recalculation between review and deployment.
            await this.runner.run([
                "apply",
                "-input=false",
                "-lock-timeout=60s",
                "pipeline.tfplan"
            ]);

            this.plan.applied = true;
        } finally {
            this.lock.release(this.environment, this.id);
        }
    }

    async execute() {
        try {
            const configuration = await this.validate();

            await this.initialize();
            await this.generatePlan(configuration);
            await this.securityScan();
            await this.review();
            await this.apply();

            this.transition(Stage.SUCCEEDED);
        } catch (error) {
            const target = this.cancelled
                ? Stage.CANCELLED
                : Stage.FAILED;

            if (AllowedTransitions[this.stage].includes(target)) {
                this.transition(target);
            }

            this.audit.record("pipeline_failure", {
                runId: this.id,
                message: error.message,
                code: error.code || "UNEXPECTED_ERROR"
            });

            throw error;
        }

        return {
            runId: this.id,
            stage: this.stage,
            planId: this.plan.id,
            auditEvents: this.audit.export()
        };
    }
}


function detectDrift(expected, actual) {
    const missing = [];
    const unexpected = [];
    const changed = [];

    for (const [key, value] of Object.entries(expected)) {
        if (!(key in actual)) {
            missing.push(key);
        } else if (actual[key] !== value) {
            changed.push({
                resource: key,
                expected: value,
                actual: actual[key]
            });
        }
    }

    for (const key of Object.keys(actual)) {
        if (!(key in expected)) {
            unexpected.push(key);
        }
    }

    return {
        driftDetected:
            missing.length > 0 ||
            unexpected.length > 0 ||
            changed.length > 0,
        missing,
        unexpected,
        changed
    };
}


async function main() {
    const directory = path.resolve("terraform-demo");

    await fs.mkdir(directory, { recursive: true });

    const mainFile = path.join(directory, "main.tf");

    try {
        await fs.access(mainFile);
    } catch {
        await fs.writeFile(
            mainFile,
            [
                'terraform {',
                '  required_version = ">= 1.5.0"',
                '}',
                '',
                'resource "aws_s3_bucket" "application_data" {',
                '  bucket = "example-application-data-2026"',
                '}',
                ''
            ].join("\n"),
            "utf8"
        );
    }

    const audit = new AuditLogger();

    audit.on("stage_changed", event => {
        console.log(
            `[PIPELINE] ${event.details.previous} -> ${event.details.next}`
        );
    });

    const approvals = new ApprovalManager(2);

    approvals.decide(
        "platform-lead",
        "approved",
        "Infrastructure reviewed"
    );

    approvals.decide(
        "security-lead",
        "approved",
        "Security controls verified"
    );

    const policy = new ConfigurationPolicy({
        maxResourceCount: 100,
        requireEncryption: true,
        blockPublicIngress: true,
        allowDestroy: false
    });

    const pipeline = new TerraformPipeline({
        environment: Environment.PRODUCTION,
        directory,
        policy,
        approvals,
        runner: new TerraformCommandRunner(directory, false),
        audit,
        lock: new DeploymentLock()
    });

    try {
        const result = await pipeline.execute();

        console.log("\nPIPELINE RESULT");
        console.log(JSON.stringify(result, null, 2));
    } catch (error) {
        console.error("PIPELINE FAILED:", error.message);
        process.exitCode = 1;
    }

    console.log("\nDRIFT REPORT");

    console.log(JSON.stringify(
        detectDrift(
            {
                database: "encrypted",
                network: "private"
            },
            {
                database: "encrypted",
                network: "public"
            }
        ),
        null,
        2
    ));

    await fs.mkdir("reports", { recursive: true });

    await fs.writeFile(
        path.join("reports", "pipeline-audit.json"),
        JSON.stringify(audit.export(), null, 2),
        { encoding: "utf8", mode: 0o600 }
    );
}


if (require.main === module) {
    main().catch(error => {
        console.error(error);
        process.exitCode = 1;
    });
}

module.exports = {
    TerraformPipeline,
    ConfigurationPolicy,
    ApprovalManager,
    DeploymentLock,
    TerraformCommandRunner,
    PlanArtifact,
    AuditLogger,
    detectDrift,
    Stage,
    Environment
};

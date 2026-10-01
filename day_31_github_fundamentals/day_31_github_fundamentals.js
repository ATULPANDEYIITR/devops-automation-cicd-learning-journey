/**
 * GitHub Fundamentals
 *
 * Complementary Node.js implementation covering:
 * repositories, issues, projects, Actions-style event processing,
 * workflow runs, environments, deployments, and operational policy.
 *
 * Run with:
 *     node github-fundamentals.js
 */

"use strict";

const crypto = require("node:crypto");

class Repository {
    constructor(owner, name, visibility = "private") {
        if (!owner || !name) {
            throw new Error("Repository owner and name are required.");
        }

        this.owner = owner;
        this.name = name;
        this.visibility = visibility;
        this.defaultBranch = "main";
        this.branches = new Set(["main"]);
        this.files = new Map();
    }

    get fullName() {
        return `${this.owner}/${this.name}`;
    }

    createBranch(name) {
        if (!/^[A-Za-z0-9._/-]+$/.test(name)) {
            throw new Error(`Invalid branch name: ${name}`);
        }
        if (this.branches.has(name)) {
            throw new Error(`Branch already exists: ${name}`);
        }

        this.branches.add(name);
        return name;
    }

    writeFile(path, content) {
        if (!path || path.includes("..")) {
            throw new Error("Repository paths must not escape the repository root.");
        }

        this.files.set(path, content);
    }
}

class Issue {
    constructor(number, title, body, author) {
        if (!title.trim()) {
            throw new Error("Issue title cannot be empty.");
        }

        this.number = number;
        this.title = title;
        this.body = body;
        this.author = author;
        this.state = "open";
        this.labels = new Set();
        this.assignees = new Set();
        this.comments = [];
    }

    addLabel(label) {
        if (!label.trim()) {
            throw new Error("Labels cannot be empty.");
        }
        this.labels.add(label);
    }

    assign(user) {
        this.assignees.add(user);
    }

    comment(author, body) {
        if (!body.trim()) {
            throw new Error("Comment cannot be empty.");
        }

        this.comments.push({
            author,
            body,
            createdAt: new Date().toISOString()
        });
    }

    close() {
        this.state = "closed";
    }
}

class IssueTracker {
    constructor() {
        this.issues = new Map();
        this.nextNumber = 1;
    }

    create(title, body, author) {
        const issue = new Issue(this.nextNumber++, title, body, author);
        this.issues.set(issue.number, issue);
        return issue;
    }

    get(number) {
        const issue = this.issues.get(number);
        if (!issue) {
            throw new Error(`Issue #${number} was not found.`);
        }
        return issue;
    }
}

class ProjectBoard {
    constructor(name) {
        this.name = name;
        this.items = new Map();
        this.validStatuses = new Set([
            "Todo",
            "In Progress",
            "Blocked",
            "Done"
        ]);
    }

    add(contentType, contentId, status = "Todo") {
        if (!this.validStatuses.has(status)) {
            throw new Error(`Invalid project status: ${status}`);
        }

        const key = `${contentType}:${contentId}`;
        this.items.set(key, {
            contentType,
            contentId,
            status,
            updatedAt: new Date().toISOString()
        });
    }

    transition(contentType, contentId, status) {
        if (!this.validStatuses.has(status)) {
            throw new Error(`Invalid project status: ${status}`);
        }

        const key = `${contentType}:${contentId}`;
        const item = this.items.get(key);

        if (!item) {
            throw new Error(`Project item does not exist: ${key}`);
        }

        item.status = status;
        item.updatedAt = new Date().toISOString();
    }

    counts() {
        const counts = Object.fromEntries(
            [...this.validStatuses].map(status => [status, 0])
        );

        for (const item of this.items.values()) {
            counts[item.status]++;
        }

        return counts;
    }
}

class PullRequest {
    constructor(number, source, target, title, author, draft = true) {
        if (source === target) {
            throw new Error("Source and target branches must differ.");
        }

        this.number = number;
        this.source = source;
        this.target = target;
        this.title = title;
        this.author = author;
        this.draft = draft;
        this.state = "open";
        this.commits = [];
        this.changedFiles = new Map();
        this.issueLinks = [];
        this.updatedAt = new Date().toISOString();
    }

    addCommit(message, changes) {
        if (this.state !== "open") {
            throw new Error("Cannot add commits to a closed pull request.");
        }

        const sha = crypto
            .createHash("sha1")
            .update(`${message}:${JSON.stringify(changes)}:${Date.now()}`)
            .digest("hex")
            .slice(0, 12);

        this.commits.push({
            sha,
            message,
            createdAt: new Date().toISOString()
        });

        for (const [file, content] of Object.entries(changes)) {
            this.changedFiles.set(file, content);
        }

        this.updatedAt = new Date().toISOString();
        return sha;
    }

    markReadyForReview() {
        this.draft = false;
    }

    close() {
        this.state = "closed";
    }

    reopen() {
        if (this.state !== "closed") {
            throw new Error("Only closed pull requests can be reopened.");
        }

        this.state = "open";
    }

    synchronize(baseChanged) {
        if (this.state !== "open") {
            throw new Error("Closed pull requests cannot be synchronized.");
        }

        return {
            required: Boolean(baseChanged),
            reason: baseChanged
                ? "The target branch changed."
                : "The source branch is already synchronized."
        };
    }
}

class ActionsEngine {
    constructor() {
        this.runs = [];
        this.listeners = new Map();
    }

    on(event, listener) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(listener);
    }

    emit(event, payload) {
        const listeners = this.listeners.get(event) || [];
        for (const listener of listeners) {
            listener(payload);
        }
    }

    async runWorkflow(repository, workflowName, eventName, branch) {
        const run = {
            id: crypto.randomUUID(),
            workflow: workflowName,
            event: eventName,
            branch,
            status: "queued",
            logs: [],
            startedAt: new Date().toISOString()
        };

        this.runs.push(run);
        this.emit("workflow.queued", run);

        run.status = "running";
        run.logs.push(`Starting ${workflowName} for ${repository.fullName}.`);
        this.emit("workflow.started", run);

        await new Promise(resolve => setTimeout(resolve, 10));

        if (!repository.branches.has(branch)) {
            run.status = "failure";
            run.logs.push(`Branch '${branch}' does not exist.`);
            this.emit("workflow.completed", run);
            return run;
        }

        if (!repository.files.has("README.md")) {
            run.status = "failure";
            run.logs.push("Required README.md is missing.");
        } else {
            run.status = "success";
            run.logs.push("Repository validation passed.");
        }

        run.completedAt = new Date().toISOString();
        this.emit("workflow.completed", run);
        return run;
    }
}

class Environment {
    constructor(name, options = {}) {
        this.name = name;
        this.variables = new Map(Object.entries(options.variables || {}));

        // Secrets are represented by their names, not their values. This
        // prevents accidental secret disclosure through application output.
        this.secretNames = new Set(options.secretNames || []);

        this.requiredApprovals = options.requiredApprovals || 0;
        this.approvals = new Set();
        this.deploymentHistory = [];
    }

    approve(user) {
        if (!user || !user.trim()) {
            throw new Error("An approval requires a reviewer identity.");
        }

        this.approvals.add(user);
    }

    canDeploy() {
        return this.approvals.size >= this.requiredApprovals;
    }

    deploy(actor, branch, commit) {
        if (!this.canDeploy()) {
            return {
                environment: this.name,
                status: "waiting",
                actor,
                branch,
                commit
            };
        }

        const record = {
            environment: this.name,
            status: "deployed",
            actor,
            branch,
            commit,
            timestamp: new Date().toISOString()
        };

        this.deploymentHistory.push(record);
        return record;
    }
}

function displayIssue(issue) {
    console.log(`Issue #${issue.number}: ${issue.title}`);
    console.log(`State: ${issue.state}`);
    console.log(`Labels: ${[...issue.labels].join(", ")}`);
    console.log(`Assignees: ${[...issue.assignees].join(", ")}`);
}

async function main() {
    console.log("=== GitHub Fundamentals: Node.js Model ===");

    const repository = new Repository(
        "example-org",
        "release-platform",
        "private"
    );

    repository.writeFile(
        "README.md",
        "# Release Platform\nRepository documentation."
    );

    repository.writeFile(
        ".github/workflows/ci.yml",
        "name: CI"
    );

    repository.createBranch("feature/audit-deployments");

    console.log(`Repository: ${repository.fullName}`);
    console.log(`Branches: ${[...repository.branches].join(", ")}`);

    console.log("\n=== Issues ===");

    const issueTracker = new IssueTracker();
    const issue = issueTracker.create(
        "Add deployment audit trail",
        "Record deployment actor, branch, and commit.",
        "maya"
    );

    issue.addLabel("enhancement");
    issue.addLabel("deployment");
    issue.assign("maya");
    issue.comment(
        "maya",
        "The audit record must not contain deployment secrets."
    );

    displayIssue(issue);

    console.log("\n=== Projects ===");

    const project = new ProjectBoard("Release Platform Roadmap");

    project.add("issue", issue.number, "In Progress");
    project.add("repository", repository.fullName, "Todo");

    project.transition("issue", issue.number, "Done");

    console.log("Project counts:", project.counts());

    console.log("\n=== Pull Request Lifecycle ===");

    const pullRequest = new PullRequest(
        1,
        "feature/audit-deployments",
        "main",
        "Add deployment audit trail",
        "maya",
        true
    );

    const firstCommit = pullRequest.addCommit(
        "Record deployment actor",
        {
            "audit.js":
                "function recordDeployment(actor, commit) { return { actor, commit }; }"
        }
    );

    pullRequest.addCommit(
        "Add audit validation",
        {
            "audit.test.js":
                "assert(typeof recordDeployment === 'function');"
        }
    );

    pullRequest.issueLinks.push(issue.number);

    console.log(
        `Draft PR #${pullRequest.number}: ` +
        `${pullRequest.source} -> ${pullRequest.target}`
    );
    console.log(`First commit: ${firstCommit}`);
    console.log(`Changed files: ${pullRequest.changedFiles.size}`);

    pullRequest.markReadyForReview();
    console.log(`Ready for review: ${!pullRequest.draft}`);

    const syncResult = pullRequest.synchronize(true);
    console.log("Synchronization result:", syncResult);

    console.log("\n=== GitHub Actions-Style Event Processing ===");

    const actions = new ActionsEngine();

    actions.on("workflow.queued", run => {
        console.log(`Queued workflow ${run.workflow}: ${run.id}`);
    });

    actions.on("workflow.completed", run => {
        console.log(`Workflow completed with status: ${run.status}`);
    });

    const ciRun = await actions.runWorkflow(
        repository,
        "CI",
        "pull_request",
        pullRequest.source
    );

    console.log("Workflow logs:");
    for (const log of ciRun.logs) {
        console.log(`  ${log}`);
    }

    console.log("\n=== Environment-Gated Deployment ===");

    const staging = new Environment("staging", {
        variables: {
            APP_MODE: "staging"
        },
        secretNames: ["DEPLOY_TOKEN"],
        requiredApprovals: 0
    });

    const production = new Environment("production", {
        variables: {
            APP_MODE: "production"
        },
        secretNames: ["DEPLOY_TOKEN", "DATABASE_URL"],
        requiredApprovals: 2
    });

    const stagingDeployment = staging.deploy(
        "maya",
        "main",
        firstCommit
    );
    console.log("Staging:", stagingDeployment);

    const productionBeforeApproval = production.deploy(
        "maya",
        "main",
        firstCommit
    );
    console.log("Production before approvals:", productionBeforeApproval);

    production.approve("release-manager");
    production.approve("security-reviewer");

    const productionDeployment = production.deploy(
        "maya",
        "main",
        firstCommit
    );

    console.log("Production after approvals:", productionDeployment);

    console.log("\n=== Failure Cases ===");

    try {
        repository.createBranch("invalid branch");
    } catch (error) {
        console.log(`Branch validation: ${error.message}`);
    }

    try {
        project.transition("issue", 999, "Done");
    } catch (error) {
        console.log(`Project validation: ${error.message}`);
    }

    try {
        const invalidEnvironment = new Environment("protected-production", {
            requiredApprovals: 1
        });

        const blocked = invalidEnvironment.deploy(
            "maya",
            "main",
            "abc1234"
        );

        console.log("Protected environment without approval:", blocked);
    } catch (error) {
        console.log(`Environment error: ${error.message}`);
    }

    console.log("\n=== Operational Model ===");
    console.log(
        JSON.stringify(
            {
                repository: repository.fullName,
                issue: issue.number,
                projectItems: project.items.size,
                pullRequest: pullRequest.number,
                workflowStatus: ciRun.status,
                deployments: staging.deploymentHistory.length +
                    production.deploymentHistory.length
            },
            null,
            2
        )
    );
}

main().catch(error => {
    console.error("Fatal error:", error.message);
    process.exitCode = 1;
});

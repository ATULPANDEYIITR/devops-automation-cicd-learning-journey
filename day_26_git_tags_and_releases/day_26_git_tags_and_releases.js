/**
 * Git Tags & Releases: Semantic Versioning and Release Concepts
 * ==============================================================
 *
 * This self-contained JavaScript file demonstrates:
 *   - Git tag concepts
 *   - lightweight vs annotated tags
 *   - Semantic Versioning
 *   - SemVer precedence
 *   - prerelease identifiers
 *   - build metadata
 *   - version bumping
 *   - simple version constraints
 *   - release planning
 *   - changelog generation
 *   - validation
 *   - Git command execution with Node.js
 *   - asynchronous release inspection
 *   - safe command argument handling
 *
 * Runtime:
 *   Node.js 18+ recommended.
 *
 * Examples:
 *   node git-tags-releases.js
 *   node git-tags-releases.js --repo .
 *   node git-tags-releases.js --version 2.4.0
 */

"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

const execFileAsync = promisify(execFile);


// ---------------------------------------------------------------------------
// 1. Semantic Versioning
// ---------------------------------------------------------------------------

class SemVer {
    constructor(major, minor, patch, prerelease = [], build = []) {
        this.major = major;
        this.minor = minor;
        this.patch = patch;
        this.prerelease = [...prerelease];
        this.build = [...build];
    }

    static parse(input) {
        if (typeof input !== "string") {
            throw new TypeError("A semantic version must be a string.");
        }

        const value = input.trim();

        /*
         * JavaScript's regular expression is used only for structural
         * validation. Numeric conversion happens afterward.
         *
         * This implements the important SemVer 2.0.0 grammar:
         * MAJOR.MINOR.PATCH
         * optional -prerelease
         * optional +build
         */
        const pattern =
            /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)` +
            `(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)` +
            `(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?` +
            `(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/`;

        /*
         * The expression above is easier to audit when constructed from
         * smaller pieces. The literal string is therefore normalized here.
         */
        const semverPattern = new RegExp(
            "^(0|[1-9]\\d*)\\." +
            "(0|[1-9]\\d*)\\." +
            "(0|[1-9]\\d*)" +
            "(?:-(" +
            "(?:0|[1-9]\\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)" +
            "(?:\\.(?:0|[1-9]\\d*|[0-9A-Za-z-]*[A-Za-z-]" +
            "[0-9A-Za-z-]*))*" +
            "))?" +
            "(?:\\+([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?$"
        );

        const match = semverPattern.exec(value);

        if (!match) {
            throw new Error(`Invalid Semantic Version: ${input}`);
        }

        const prerelease = match[4]
            ? match[4].split(".")
            : [];

        const build = match[5]
            ? match[5].split(".")
            : [];

        return new SemVer(
            Number(match[1]),
            Number(match[2]),
            Number(match[3]),
            prerelease,
            build
        );
    }

    toString() {
        let value = `${this.major}.${this.minor}.${this.patch}`;

        if (this.prerelease.length > 0) {
            value += `-${this.prerelease.join(".")}`;
        }

        if (this.build.length > 0) {
            value += `+${this.build.join(".")}`;
        }

        return value;
    }

    isPrerelease() {
        return this.prerelease.length > 0;
    }

    compare(other) {
        if (!(other instanceof SemVer)) {
            throw new TypeError("Can only compare SemVer instances.");
        }

        if (this.major !== other.major) {
            return Math.sign(this.major - other.major);
        }

        if (this.minor !== other.minor) {
            return Math.sign(this.minor - other.minor);
        }

        if (this.patch !== other.patch) {
            return Math.sign(this.patch - other.patch);
        }

        // Build metadata does not participate in SemVer precedence.
        return comparePrereleaseIdentifiers(
            this.prerelease,
            other.prerelease
        );
    }

    equals(other) {
        return this.compare(other) === 0;
    }

    lessThan(other) {
        return this.compare(other) < 0;
    }

    greaterThan(other) {
        return this.compare(other) > 0;
    }

    bumpMajor() {
        return new SemVer(this.major + 1, 0, 0);
    }

    bumpMinor() {
        return new SemVer(this.major, this.minor + 1, 0);
    }

    bumpPatch() {
        return new SemVer(this.major, this.minor, this.patch + 1);
    }

    toJSON() {
        return {
            major: this.major,
            minor: this.minor,
            patch: this.patch,
            prerelease: this.prerelease,
            build: this.build,
            isPrerelease: this.isPrerelease(),
            string: this.toString()
        };
    }
}


function comparePrereleaseIdentifiers(left, right) {
    if (left.length === 0 && right.length === 0) {
        return 0;
    }

    // A normal version has higher precedence than a prerelease.
    if (left.length === 0) {
        return 1;
    }

    if (right.length === 0) {
        return -1;
    }

    const length = Math.min(left.length, right.length);

    for (let index = 0; index < length; index += 1) {
        const leftIdentifier = left[index];
        const rightIdentifier = right[index];

        if (leftIdentifier === rightIdentifier) {
            continue;
        }

        const leftNumeric = /^\d+$/.test(leftIdentifier);
        const rightNumeric = /^\d+$/.test(rightIdentifier);

        if (leftNumeric && rightNumeric) {
            return Number(leftIdentifier) < Number(rightIdentifier)
                ? -1
                : 1;
        }

        if (leftNumeric !== rightNumeric) {
            return leftNumeric ? -1 : 1;
        }

        return leftIdentifier < rightIdentifier ? -1 : 1;
    }

    if (left.length === right.length) {
        return 0;
    }

    return left.length < right.length ? -1 : 1;
}


// ---------------------------------------------------------------------------
// 2. Tag naming and release policy
// ---------------------------------------------------------------------------

class ReleasePolicy {
    constructor({
        prefix = "v",
        requireSemVer = true,
        requireAnnotated = true,
        requireCleanWorktree = true,
        immutableTags = true
    } = {}) {
        this.prefix = prefix;
        this.requireSemVer = requireSemVer;
        this.requireAnnotated = requireAnnotated;
        this.requireCleanWorktree = requireCleanWorktree;
        this.immutableTags = immutableTags;
    }

    parseTag(tagName) {
        if (typeof tagName !== "string" || tagName.length === 0) {
            throw new Error("Tag name must be a non-empty string.");
        }

        if (this.prefix && !tagName.startsWith(this.prefix)) {
            throw new Error(
                `Release tag must start with "${this.prefix}".`
            );
        }

        const versionText = this.prefix
            ? tagName.slice(this.prefix.length)
            : tagName;

        return SemVer.parse(versionText);
    }

    validateTag(tagName) {
        const version = this.parseTag(tagName);

        return {
            valid: true,
            tagName,
            version
        };
    }
}


// ---------------------------------------------------------------------------
// 3. Simple version constraints
// ---------------------------------------------------------------------------

class VersionConstraint {
    constructor(operator, version) {
        this.operator = operator;
        this.version = version;
    }

    matches(candidate) {
        const comparison = candidate.compare(this.version);

        switch (this.operator) {
            case "=":
            case "==":
                return comparison === 0;
            case "!=":
                return comparison !== 0;
            case ">":
                return comparison > 0;
            case ">=":
                return comparison >= 0;
            case "<":
                return comparison < 0;
            case "<=":
                return comparison <= 0;
            default:
                throw new Error(
                    `Unsupported constraint operator: ${this.operator}`
                );
        }
    }
}


function parseConstraint(expression) {
    const match = /^\s*(==|!=|>=|<=|>|<|=)\s*(.+)\s*$/.exec(
        expression
    );

    if (!match) {
        throw new Error(
            `Invalid simple constraint: ${expression}`
        );
    }

    return new VersionConstraint(
        match[1],
        SemVer.parse(match[2])
    );
}


// ---------------------------------------------------------------------------
// 4. Release object
// ---------------------------------------------------------------------------

class Release {
    constructor({
        version,
        title = null,
        notes = [],
        prerelease = version.isPrerelease()
    }) {
        if (!(version instanceof SemVer)) {
            throw new TypeError("Release version must be a SemVer.");
        }

        this.version = version;
        this.tagName = `v${version}`;
        this.title = title || `Release ${this.tagName}`;
        this.notes = [...notes];
        this.prerelease = prerelease;
        this.createdAt = new Date().toISOString();
    }

    toJSON() {
        return {
            version: this.version.toJSON(),
            tagName: this.tagName,
            title: this.title,
            notes: this.notes,
            prerelease: this.prerelease,
            createdAt: this.createdAt
        };
    }
}


// ---------------------------------------------------------------------------
// 5. Changelog generation
// ---------------------------------------------------------------------------

function classifyCommit(subject) {
    const value = subject.toLowerCase();

    if (value.startsWith("feat")) return "Features";
    if (value.startsWith("fix")) return "Bug Fixes";
    if (value.startsWith("docs")) return "Documentation";
    if (value.startsWith("perf")) return "Performance";
    if (value.startsWith("refactor")) return "Refactoring";
    if (value.startsWith("test")) return "Tests";
    if (value.startsWith("build") || value.startsWith("ci")) {
        return "Build and CI";
    }

    return "Other Changes";
}


function generateChangelog(commits, version) {
    const groups = new Map();

    for (const commit of commits) {
        const category = classifyCommit(commit.subject);

        if (!groups.has(category)) {
            groups.set(category, []);
        }

        groups.get(category).push(commit);
    }

    const order = [
        "Breaking Changes",
        "Features",
        "Bug Fixes",
        "Performance",
        "Refactoring",
        "Documentation",
        "Tests",
        "Build and CI",
        "Other Changes"
    ];

    const lines = [
        `## ${version}`,
        "",
        `Released: ${new Date().toISOString().slice(0, 10)}`,
        ""
    ];

    for (const category of order) {
        const entries = groups.get(category);

        if (!entries || entries.length === 0) {
            continue;
        }

        lines.push(`### ${category}`, "");

        for (const commit of entries) {
            lines.push(
                `- ${commit.subject} (${commit.hash.slice(0, 8)})`
            );
        }

        lines.push("");
    }

    if (lines.length === 4) {
        lines.push("- No categorized commits were found.");
    }

    return lines.join("\n").trim();
}


// ---------------------------------------------------------------------------
// 6. Git integration
// ---------------------------------------------------------------------------

async function runGit(repository, argumentsList, { allowFailure = false } = {}) {
    /*
     * execFile is used instead of a shell command string.
     * This avoids shell parsing and makes arguments less vulnerable to shell
     * injection when values originate from user input.
     */
    try {
        const result = await execFileAsync(
            "git",
            ["-C", repository, ...argumentsList],
            {
                encoding: "utf8",
                maxBuffer: 1024 * 1024 * 10
            }
        );

        return result.stdout.trim();
    } catch (error) {
        if (allowFailure) {
            return "";
        }

        const message =
            error.stderr?.trim() ||
            error.stdout?.trim() ||
            error.message;

        throw new Error(
            `Git command failed: git -C ${repository} ` +
            `${argumentsList.join(" ")}\n${message}`
        );
    }
}


async function isGitRepository(repository) {
    try {
        const result = await runGit(
            repository,
            ["rev-parse", "--is-inside-work-tree"]
        );

        return result === "true";
    } catch {
        return false;
    }
}


async function getRepositoryState(repository) {
    if (!(await isGitRepository(repository))) {
        throw new Error(
            `${repository} is not a Git working tree.`
        );
    }

    const [
        branchOutput,
        head,
        status,
        remotes
    ] = await Promise.all([
        runGit(repository, ["branch", "--show-current"]),
        runGit(repository, ["rev-parse", "HEAD"]),
        runGit(repository, ["status", "--porcelain"]),
        runGit(repository, ["remote"])
    ]);

    return {
        branch: branchOutput || "(detached HEAD)",
        head,
        dirty: status.length > 0,
        remotes: remotes
            ? remotes.split(/\r?\n/).filter(Boolean)
            : []
    };
}


async function listTags(repository) {
    const format =
        "%(refname:short)%09" +
        "%(objecttype)%09" +
        "%(objectname)%09" +
        "%(creatordate:iso-strict)";

    const output = await runGit(
        repository,
        ["for-each-ref", `--format=${format}`, "refs/tags"]
    );

    if (!output) {
        return [];
    }

    return output.split(/\r?\n/).map(line => {
        const [
            name,
            objectType,
            objectId,
            createdAt
        ] = line.split("\t");

        return {
            name,
            objectType,
            objectId,
            createdAt,
            annotated: objectType === "tag"
        };
    });
}


async function tagExists(repository, tagName) {
    const output = await runGit(
        repository,
        [
            "show-ref",
            "--tags",
            "--verify",
            `refs/tags/${tagName}`
        ],
        { allowFailure: true }
    );

    return output.length > 0;
}


async function validateRelease(repository, tagName, policy) {
    const errors = [];

    try {
        policy.parseTag(tagName);
    } catch (error) {
        errors.push(error.message);
    }

    if (policy.requireCleanWorktree) {
        const status = await runGit(
            repository,
            ["status", "--porcelain"]
        );

        if (status) {
            errors.push("Working tree is not clean.");
        }
    }

    if (policy.immutableTags && await tagExists(repository, tagName)) {
        errors.push(
            `Tag ${tagName} already exists. ` +
            "Immutable release policy refuses to move it."
        );
    }

    return errors;
}


async function createAnnotatedTag(
    repository,
    tagName,
    message,
    { force = false, dryRun = false } = {}
) {
    const argumentsList = [
        "tag",
        "-a",
        tagName,
        "-m",
        message
    ];

    if (force) {
        argumentsList.splice(1, 0, "--force");
    }

    if (dryRun) {
        console.log(
            "DRY RUN:",
            ["git", "-C", repository, ...argumentsList].join(" ")
        );
        return;
    }

    await runGit(repository, argumentsList);
}


async function pushTag(
    repository,
    tagName,
    {
        remote = "origin",
        dryRun = false
    } = {}
) {
    const argumentsList = ["push", remote, tagName];

    if (dryRun) {
        console.log(
            "DRY RUN:",
            ["git", "-C", repository, ...argumentsList].join(" ")
        );
        return;
    }

    await runGit(repository, argumentsList);
}


// ---------------------------------------------------------------------------
// 7. Async demonstration
// ---------------------------------------------------------------------------

async function demonstrateConcurrentGitQueries(repository) {
    console.log("\n=== Asynchronous Repository Inspection ===");

    /*
     * These independent queries can execute concurrently.
     * Promise.all waits until every query succeeds.
     */
    const [state, tags] = await Promise.all([
        getRepositoryState(repository),
        listTags(repository)
    ]);

    console.log("Branch:", state.branch);
    console.log("HEAD:", state.head);
    console.log("Working tree:", state.dirty ? "DIRTY" : "CLEAN");
    console.log("Remotes:", state.remotes.join(", ") || "(none)");
    console.log("Tag count:", tags.length);

    if (tags.length > 0) {
        for (const tag of tags) {
            console.log(
                `  ${tag.name} | ` +
                `${tag.annotated ? "annotated" : "lightweight"} | ` +
                `${tag.objectId.slice(0, 12)}`
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 8. File-based release metadata
// ---------------------------------------------------------------------------

async function writeReleaseMetadata(outputPath, release) {
    const absolutePath = path.resolve(outputPath);

    const content = JSON.stringify(
        release,
        null,
        2
    );

    /*
     * Writing metadata is useful for CI systems and deployment pipelines.
     * The directory is created explicitly so a missing directory does not
     * become an unexplained runtime failure.
     */
    await fs.mkdir(path.dirname(absolutePath), {
        recursive: true
    });

    await fs.writeFile(
        absolutePath,
        content + "\n",
        "utf8"
    );

    return absolutePath;
}


// ---------------------------------------------------------------------------
// 9. Educational examples
// ---------------------------------------------------------------------------

function printSection(title) {
    console.log(`\n${"=".repeat(78)}`);
    console.log(title);
    console.log("=".repeat(78));
}


function demonstrateSemVer() {
    printSection("1. Semantic Versioning");

    const values = [
        "0.1.0",
        "1.0.0",
        "1.2.3",
        "2.0.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-rc.1",
        "1.0.0+build.42"
    ];

    for (const value of values) {
        const version = SemVer.parse(value);

        console.log(
            `${value.padEnd(24)} ` +
            `major=${version.major}, ` +
            `minor=${version.minor}, ` +
            `patch=${version.patch}, ` +
            `prerelease=${version.prerelease.join(".") || "-"}, ` +
            `build=${version.build.join(".") || "-"}`
        );
    }
}


function demonstratePrecedence() {
    printSection("2. SemVer Precedence");

    const values = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0"
    ];

    const versions = values.map(SemVer.parse);

    for (let index = 0; index < versions.length - 1; index += 1) {
        console.log(
            `${versions[index]} < ${versions[index + 1]}`
        );
    }

    /*
     * Build metadata is ignored when determining precedence.
     */
    const first = SemVer.parse("1.0.0+linux");
    const second = SemVer.parse("1.0.0+windows");

    console.log(
        `${first} equals ${second}:`,
        first.equals(second)
    );
}


function demonstrateBumps() {
    printSection("3. Version Bumping");

    const current = SemVer.parse("3.8.4");

    console.log("Current:", current.toString());
    console.log("Patch:", current.bumpPatch().toString());
    console.log("Minor:", current.bumpMinor().toString());
    console.log("Major:", current.bumpMajor().toString());
}


function demonstrateConstraints() {
    printSection("4. Version Constraints");

    const constraints = [
        parseConstraint(">=1.5.0"),
        parseConstraint("<2.0.0")
    ];

    const candidates = [
        "1.4.9",
        "1.5.0",
        "1.9.9",
        "2.0.0"
    ];

    for (const value of candidates) {
        const candidate = SemVer.parse(value);

        console.log(
            value,
            constraints.map(
                constraint => constraint.matches(candidate)
            )
        );
    }
}


function demonstrateRelease() {
    printSection("5. Release Object");

    const release = new Release({
        version: SemVer.parse("2.5.0-rc.1"),
        notes: [
            "Added release validation.",
            "Improved tag inspection.",
            "Updated release documentation."
        ]
    });

    console.log(
        JSON.stringify(release, null, 2)
    );
}


function demonstrateChangelog() {
    printSection("6. Changelog");

    const commits = [
        {
            hash: "a1b2c3d4e5f6",
            subject: "feat: add release dashboard"
        },
        {
            hash: "b2c3d4e5f6a7",
            subject: "fix: reject invalid tags"
        },
        {
            hash: "c3d4e5f6a7b8",
            subject: "docs: explain immutable releases"
        },
        {
            hash: "d4e5f6a7b8c9",
            subject: "perf: optimize version parsing"
        },
        {
            hash: "e5f6a7b8c9d0",
            subject: "refactor: separate Git commands"
        }
    ];

    console.log(
        generateChangelog(
            commits,
            SemVer.parse("1.4.0")
        )
    );
}


// ---------------------------------------------------------------------------
// 10. Self-tests
// ---------------------------------------------------------------------------

function runTests() {
    printSection("7. Automated Self-Tests");

    const valid = [
        "1.0.0",
        "1.2.3-alpha",
        "1.2.3-alpha.1",
        "1.2.3+build.7",
        "1.2.3-rc.1+linux.x64"
    ];

    for (const value of valid) {
        const parsed = SemVer.parse(value);
        if (parsed.toString() !== value) {
            throw new Error(
                `Round-trip failed for ${value}`
            );
        }
    }

    const invalid = [
        "1",
        "1.2",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-",
        "1.2.3+"
    ];

    for (const value of invalid) {
        let rejected = false;

        try {
            SemVer.parse(value);
        } catch {
            rejected = true;
        }

        if (!rejected) {
            throw new Error(
                `Invalid version was accepted: ${value}`
            );
        }
    }

    const precedence = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0"
    ].map(SemVer.parse);

    for (let index = 0; index < precedence.length - 1; index += 1) {
        if (!precedence[index].lessThan(precedence[index + 1])) {
            throw new Error(
                "SemVer precedence test failed."
            );
        }
    }

    const policy = new ReleasePolicy();
    policy.validateTag("v1.2.3");

    if (!parseConstraint(">=1.0.0")
        .matches(SemVer.parse("1.2.0"))) {
        throw new Error("Constraint test failed.");
    }

    if (classifyCommit("feat: add API") !== "Features") {
        throw new Error("Commit classifier test failed.");
    }

    console.log("All tests passed.");
}


// ---------------------------------------------------------------------------
// 11. CLI
// ---------------------------------------------------------------------------

function parseArguments(argumentsList) {
    const options = {
        repository: ".",
        inspect: false,
        version: null,
        runTests: false,
        metadataPath: null
    };

    for (let index = 0; index < argumentsList.length; index += 1) {
        const argument = argumentsList[index];

        if (argument === "--repo") {
            options.repository = argumentsList[++index];
        } else if (argument === "--inspect") {
            options.inspect = true;
        } else if (argument === "--version") {
            options.version = argumentsList[++index];
        } else if (argument === "--run-tests") {
            options.runTests = true;
        } else if (argument === "--metadata") {
            options.metadataPath = argumentsList[++index];
        } else if (argument === "--help") {
            printHelp();
            process.exit(0);
        } else {
            throw new Error(`Unknown argument: ${argument}`);
        }
    }

    return options;
}


function printHelp() {
    console.log(`
Usage:
  node git-tags-releases.js
  node git-tags-releases.js --repo .
  node git-tags-releases.js --repo . --inspect
  node git-tags-releases.js --version 2.4.0
  node git-tags-releases.js --version 2.4.0 --metadata release.json
  node git-tags-releases.js --run-tests

Options:
  --repo PATH        Git repository to inspect.
  --inspect          Inspect repository state and tags.
  --version VERSION  Parse and display a semantic version.
  --metadata FILE    Write release metadata to JSON.
  --run-tests        Execute self-tests.
  --help             Display this help.
`);
}


async function main() {
    const options = parseArguments(process.argv.slice(2));

    demonstrateSemVer();
    demonstratePrecedence();
    demonstrateBumps();
    demonstrateConstraints();
    demonstrateRelease();
    demonstrateChangelog();

    if (options.runTests) {
        runTests();
    }

    if (options.version) {
        printSection("Requested Version");

        const version = SemVer.parse(options.version);

        console.log(
            JSON.stringify(
                version,
                null,
                2
            )
        );

        if (options.metadataPath) {
            const release = new Release({
                version,
                notes: [
                    "Metadata generated from the requested version."
                ]
            });

            const writtenPath = await writeReleaseMetadata(
                options.metadataPath,
                release
            );

            console.log(
                `Release metadata written to: ${writtenPath}`
            );
        }
    }

    if (options.inspect) {
        printSection("Git Repository");

        const repository = path.resolve(options.repository);

        if (!(await isGitRepository(repository))) {
            throw new Error(
                `${repository} is not a Git repository.`
            );
        }

        await demonstrateConcurrentGitQueries(repository);

        /*
         * The following validation demonstrates how a release pipeline can
         * check a proposed tag before mutation.
         */
        const policy = new ReleasePolicy();

        const proposedTag = "v1.0.0";
        const errors = await validateRelease(
            repository,
            proposedTag,
            policy
        );

        console.log("\nProposed tag:", proposedTag);

        if (errors.length > 0) {
            console.log("Release validation errors:");

            for (const error of errors) {
                console.log(`  - ${error}`);
            }
        } else {
            console.log(
                "Release validation passed. " +
                "No Git mutation was performed by this example."
            );
        }
    }
}


main().catch(error => {
    console.error(`Error: ${error.message}`);
    process.exitCode = 1;
});

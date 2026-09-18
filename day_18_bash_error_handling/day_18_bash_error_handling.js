"use strict";

/*
 * Bash Error Handling companion study program.
 *
 * This JavaScript file demonstrates Bash error-handling concepts by executing
 * isolated Bash programs through Node.js child_process.spawnSync().
 *
 * Requirements:
 *   - Node.js 18+
 *   - Bash available as "bash"
 *
 * The examples are intentionally independent. A failing Bash example does not
 * terminate this JavaScript program, allowing the complete study sequence to
 * run.
 */

const {
    spawnSync,
    mkdtempSync,
    writeFileSync,
    rmSync,
} = require("node:child_process") ? {
    spawnSync: require("node:child_process").spawnSync,
    mkdtempSync: require("node:fs").mkdtempSync,
    writeFileSync: require("node:fs").writeFileSync,
    rmSync: require("node:fs").rmSync,
} : {};

/*
 * The destructuring above keeps the required Node.js modules explicit.
 * The actual imports below are used for filesystem and path operations.
 */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");


function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}


function concept(title, text) {
    console.log(`\n${title}`);
    console.log("-".repeat(title.length));
    console.log(text.trim());
}


function runBash(name, script, options = {}) {
    /*
     * spawnSync receives Bash and the script as separate arguments.
     * No shell is created by Node.js for this invocation, reducing unnecessary
     * command-string interpretation.
     */
    const result = spawnSync(
        "bash",
        ["--noprofile", "--norc"],
        {
            input: script,
            encoding: "utf8",
            timeout: options.timeout ?? 5000,
            env: options.env ?? process.env,
        }
    );

    if (result.error) {
        console.log(`\n--- ${name} ---`);
        console.log(`execution error: ${result.error.message}`);
        return {
            name,
            status: null,
            stdout: "",
            stderr: result.error.message,
        };
    }

    const outcome = {
        name,
        status: result.status,
        stdout: result.stdout ?? "",
        stderr: result.stderr ?? "",
    };

    console.log(`\n--- ${name} ---`);
    console.log(`exit code: ${outcome.status}`);

    if (outcome.stdout) {
        console.log("stdout:");
        console.log(outcome.stdout.trimEnd());
    }

    if (outcome.stderr) {
        console.log("stderr:");
        console.log(outcome.stderr.trimEnd());
    }

    return outcome;
}


function showResult(result) {
    if (result.status === 0) {
        console.log("Interpretation: Bash reported success.");
    } else {
        console.log(
            "Interpretation: Bash reported a nonzero status. " +
            "The exact meaning depends on the command."
        );
    }
}


function demonstrateExitCodes() {
    section("1. Exit codes and process status");

    concept(
        "Exit status",
        `
Every Bash command returns a numeric exit status.

By convention:
  0       means success.
  nonzero means failure or another condition defined by the command.

Bash exposes the previous command's status through $?.

The status can be used by if statements, &&, ||, functions, and callers.
`
    );

    showResult(runBash(
        "success status",
        `
true
printf 'status=%s\\n' "$?"
`
    ));

    showResult(runBash(
        "failure status",
        `
false
printf 'status=%s\\n' "$?"
`
    ));

    concept(
        "Capture immediately",
        `
$? changes after another command runs. Capture it before executing another
command whose status would replace it.
`
    );

    showResult(runBash(
        "capturing $? immediately",
        `
false
status=$?
printf 'captured=%s\\n' "$status"
`
    ));
}


function demonstrateConditionals() {
    section("2. Explicit error handling");

    concept(
        "if statements",
        `
Bash treats a command's exit status as a condition. An if statement is often
the clearest way to distinguish expected failure from unexpected failure.
`
    );

    showResult(runBash(
        "explicit condition handling",
        `
if test -f /path/that/does/not/exist; then
    printf 'file exists\\n'
else
    printf 'file does not exist; expected condition\\n'
fi
`
    ));

    concept(
        "&& and ||",
        `
&& executes the right-hand side when the left-hand command succeeds.
|| executes the right-hand side when the left-hand command fails.

They are concise, but complicated chains can become difficult to reason about.
`
    );

    showResult(runBash(
        "short-circuit operators",
        `
true && printf 'success branch\\n'
false || printf 'failure branch\\n'
`
    ));

    concept(
        "A subtle chain",
        `
command && success_action || failure_action

is not always equivalent to an if statement. If success_action itself fails,
failure_action can execute. Explicit if/else logic is safer for complicated
control flow.
`
    );

    showResult(runBash(
        "&& and || subtle behavior",
        `
true && {
    printf 'original command succeeded\\n'
    false
} || {
    printf 'fallback also executed\\n'
}
`
    ));
}


function demonstrateSetE() {
    section("3. set -e and errexit");

    concept(
        "Purpose",
        `
set -e, or set -o errexit, requests that Bash exit when an unhandled simple
command fails in contexts where errexit applies.

It prevents many scripts from silently continuing after serious failures.
It is not equivalent to an unconditional exception mechanism because Bash has
specific syntactic contexts where errexit is suppressed.
`
    );

    showResult(runBash(
        "set -e stops a simple failure",
        `
set -e
printf 'before failure\\n'
false
printf 'not reached\\n'
`
    ));

    showResult(runBash(
        "set -e inside an if condition",
        `
set -e

if false; then
    printf 'success\\n'
else
    printf 'condition returned false and was handled\\n'
fi

printf 'script continued\\n'
`
    ));

    concept(
        "pipefail",
        `
Without pipefail, the status of a pipeline is normally the status of its last
command. Therefore an earlier failure can be hidden.

set -o pipefail changes this behavior so a pipeline can expose failures in
earlier stages.
`
    );

    showResult(runBash(
        "pipeline without pipefail",
        `
set -e
false | true
printf 'pipeline appeared successful\\n'
`
    ));

    showResult(runBash(
        "pipeline with pipefail",
        `
set -e
set -o pipefail
false | true
printf 'not reached\\n'
`
    ));
}


function demonstrateSetU() {
    section("4. set -u and nounset");

    concept(
        "Purpose",
        `
set -u treats unintended expansion of unset variables as an error.

This catches spelling mistakes and missing configuration that could otherwise
silently become empty strings.
`
    );

    showResult(runBash(
        "unset variable without nounset",
        `
unset MISSING_SETTING
printf 'value=[%s]\\n' "$MISSING_SETTING"
printf 'continued\\n'
`
    ));

    showResult(runBash(
        "unset variable with nounset",
        `
set -u
unset MISSING_SETTING
printf 'value=[%s]\\n' "$MISSING_SETTING"
`
    ));

    concept(
        "Safe parameter expansion",
        `
Use forms such as:

  \${name:-default}
  \${name-default}
  \${name:?message}
  \${name?message}

They allow scripts to distinguish optional and required configuration.
`
    );

    showResult(runBash(
        "default value with nounset",
        `
set -u
unset OPTIONAL_PORT
port="\${OPTIONAL_PORT:-8080}"
printf 'port=%s\\n' "$port"
`
    ));

    showResult(runBash(
        "required configuration",
        `
set -u
unset DATABASE_URL
: "\${DATABASE_URL:?DATABASE_URL must be configured}"
`
    ));
}


function demonstrateTraps() {
    section("5. trap and shell events");

    concept(
        "EXIT trap",
        `
trap can register code for shell events. EXIT is particularly useful for
cleanup because it runs when the shell is about to exit.
`
    );

    showResult(runBash(
        "EXIT cleanup",
        `
cleanup() {
    printf 'cleanup executed\\n'
}

trap cleanup EXIT
printf 'main work\\n'
`
    ));

    concept(
        "ERR trap",
        `
ERR can be used for diagnostics after many command failures. Its behavior
follows rules related to errexit and conditional contexts.

set -E, also called errtrace, allows ERR traps to propagate into relevant
function, command-substitution, and subshell contexts.
`
    );

    showResult(runBash(
        "ERR diagnostic trap",
        `
set -E

trap '
    status=$?
    printf "ERR status=%s command=%s function=%s\\n" \
        "$status" "$BASH_COMMAND" "${FUNCNAME[1]:-main}" >&2
' ERR

perform_task() {
    false
}

perform_task
`
    ));

    concept(
        "Signal handling",
        `
INT and TERM traps allow scripts to react to interrupts and termination
requests. Cleanup should be safe if it is executed after partial setup.
`
    );

    showResult(runBash(
        "cleanup after partial setup",
        `
set -u

temporary_file=""

cleanup() {
    if [[ -n "$temporary_file" && -e "$temporary_file" ]]; then
        rm -f -- "$temporary_file"
        printf 'temporary resource removed\\n'
    fi
}

trap cleanup EXIT

temporary_file="$(mktemp)"
printf 'temporary data\\n' > "$temporary_file"
printf 'resource=%s\\n' "$temporary_file"
`
    ));
}


function demonstrateQuotingAndArrays() {
    section("6. Quoting, arrays, and command safety");

    concept(
        "Quoting",
        `
Double quotes preserve a variable expansion as one argument in most ordinary
command contexts.

"$file"

is generally safer than:

$file

because the unquoted form can undergo word splitting and pathname expansion.
`
    );

    showResult(runBash(
        "quoted argument",
        `
filename="annual report.txt"

show_argument() {
    printf 'argument=[%s]\\n' "$1"
}

show_argument "$filename"
`
    ));

    concept(
        "Arrays",
        `
Bash arrays are useful for constructing argument lists. Each array element is
an individual argument.

"${args[@]}"

preserves those boundaries when expanded correctly.
`
    );

    showResult(runBash(
        "safe argument array",
        `
set -u

filename="report final.txt"
args=("alpha value" "--mode" "safe")

printf 'arg1=[%s]\\n' "\${args[0]}"
printf 'arg2=[%s]\\n' "\${args[1]}"
printf 'arg3=[%s]\\n' "\${args[2]}"

printf 'filename=[%s]\\n' "$filename"
`
    ));

    concept(
        "Avoid eval with untrusted input",
        `
eval asks Bash to parse generated text as shell code. If that text contains
untrusted input, command injection can result.

Prefer direct arguments and arrays rather than building shell source code.
`
    );
}


function demonstrateFunctions() {
    section("7. Functions and error propagation");

    concept(
        "return",
        `
Bash functions communicate status with return. The caller can inspect that
status with if, !, &&, ||, or explicit capture.
`
    );

    showResult(runBash(
        "function validation",
        `
validate_port() {
    local port=$1

    if [[ ! "$port" =~ ^[0-9]+$ ]]; then
        printf 'port is not numeric\\n' >&2
        return 2
    fi

    if (( port < 1 || port > 65535 )); then
        printf 'port outside range\\n' >&2
        return 2
    fi

    printf 'valid port=%s\\n' "$port"
}

validate_port 443

if ! validate_port 70000; then
    printf 'caller handled invalid port\\n'
fi
`
    ));

    concept(
        "set -e and functions",
        `
When set -e is enabled, deliberate failure handling should be expressed in
contexts where Bash knows the failure is expected.

Using:

if ! function_call; then
    ...
fi

is clearer than allowing an unexpected function failure to terminate execution
before custom recovery can run.
`
    );

    showResult(runBash(
        "function with deliberate recovery",
        `
set -e

perform_task() {
    printf 'task started\\n'

    if ! false; then
        printf 'task failure handled inside function\\n' >&2
        return 42
    fi
}

if ! perform_task; then
    printf 'caller received the failure\\n'
fi

printf 'execution continues\\n'
`
    ));
}


function demonstratePipelines() {
    section("8. Pipelines and PIPESTATUS");

    concept(
        "PIPESTATUS",
        `
Bash exposes PIPESTATUS as an array containing the individual exit statuses of
the most recent foreground pipeline.
`
    );

    showResult(runBash(
        "individual pipeline statuses",
        `
set +e
false | true | false

printf 'statuses=%s,%s,%s\\n' \
    "\${PIPESTATUS[0]}" \
    "\${PIPESTATUS[1]}" \
    "\${PIPESTATUS[2]}"
`
    ));

    concept(
        "Command substitution",
        `
$(...) captures standard output.

When the command inside the substitution is important, explicitly handle its
failure rather than assuming that captured output proves successful execution.
`
    );

    showResult(runBash(
        "safe command substitution",
        `
set -e

if output="$(printf 'generated output\\n')"; then
    printf 'captured=[%s]\\n' "$output"
else
    printf 'generation failed\\n' >&2
    exit 1
fi
`
    ));
}


function demonstrateExpectedFailures() {
    section("9. Expected nonzero statuses");

    concept(
        "Nonzero does not always mean disaster",
        `
Some commands intentionally return nonzero for normal conditions.

grep can return:
  0 = match
  1 = no match
  2 = error

test can return nonzero when a condition is false.

Therefore an explicit conditional can be more appropriate than treating every
nonzero status as fatal.
`
    );

    showResult(runBash(
        "grep condition",
        `
set -e

if grep -q "pattern-that-is-not-present" /dev/null; then
    printf 'match\\n'
else
    printf 'no match was an expected condition\\n'
fi

printf 'continued\\n'
`
    ));

    showResult(runBash(
        "temporary errexit suppression",
        `
set -e

set +e
false
status=$?
set -e

printf 'captured expected status=%s\\n' "$status"
`
    ));
}


function demonstrateSubshells() {
    section("10. Subshells and execution boundaries");

    concept(
        "Parentheses",
        `
( commands ) runs commands in a subshell. Variable modifications made inside
the subshell normally do not modify the parent shell.
`
    );

    showResult(runBash(
        "subshell scope",
        `
value="parent"

(
    value="child"
    printf 'inside=%s\\n' "$value"
)

printf 'outside=%s\\n' "$value"
`
    ));

    concept(
        "Brace grouping",
        `
{ commands; } groups commands in the current shell. It therefore differs from
parentheses with respect to variable scope and process creation.
`
    );

    showResult(runBash(
        "current-shell grouping",
        `
value="parent"

{
    value="changed"
    printf 'inside=%s\\n' "$value"
}

printf 'outside=%s\\n' "$value"
`
    ));
}


function demonstrateSecurity() {
    section("11. Security-oriented defensive scripting");

    concept(
        "Command injection",
        `
Shell syntax has operators such as ;, &, |, redirects, command substitution,
and variable expansion.

Do not concatenate untrusted input into a shell program. Pass values as
arguments instead.
`
    );

    showResult(runBash(
        "argument boundary protection",
        `
set -euo pipefail

user_input="report; printf 'this is data, not shell code\\n'"

printf 'received=[%s]\\n' "$user_input"
`
    ));

    concept(
        "Temporary files",
        `
Predictable temporary filenames can introduce collisions and security issues.
Use mktemp and register cleanup with an EXIT trap.
`
    );

    showResult(runBash(
        "secure temporary resource pattern",
        `
set -Eeuo pipefail

work_dir=""

cleanup() {
    if [[ -n "$work_dir" && -d "$work_dir" ]]; then
        rm -rf -- "$work_dir"
    fi
}

trap cleanup EXIT

work_dir="$(mktemp -d)"
printf 'temporary data\\n' > "$work_dir/data.txt"
cat -- "$work_dir/data.txt"
`
    ));

    concept(
        "Debugging secrets",
        `
set -x is useful because Bash prints commands as they execute. It can also
leak passwords, API tokens, credentials, and other sensitive values.

Disable tracing around secret handling and avoid putting secrets in logs.
`
    );
}


function demonstrateRetries() {
    section("12. Retry and recovery policies");

    concept(
        "Bounded retries",
        `
Retries should have explicit limits. A useful policy defines:
  - which failures are retryable
  - maximum attempts
  - delay
  - backoff
  - final failure status

Retrying every error forever can turn a failure into an indefinite process.
`
    );

    showResult(runBash(
        "bounded retry",
        `
set -u

attempt=1
max_attempts=3

while (( attempt <= max_attempts )); do
    printf 'attempt %d/%d\\n' "$attempt" "$max_attempts"

    if (( attempt == max_attempts )); then
        printf 'simulated recovery on final attempt\\n'
        break
    fi

    printf 'simulated transient failure\\n' >&2
    ((attempt++))
done
`
    ));

    showResult(runBash(
        "exponential backoff calculation",
        `
set -u

base=1
maximum=8

for attempt in 1 2 3 4 5; do
    delay=$(( base * 2 ** (attempt - 1) ))

    if (( delay > maximum )); then
        delay=$maximum
    fi

    printf 'attempt=%d delay=%ds\\n' "$attempt" "$delay"
done
`
    ));
}


function demonstrateIntegratedCaseStudy() {
    section("13. Integrated deployment-style Bash case study");

    concept(
        "Scenario",
        `
The following Bash program simulates a deployment pipeline entirely inside
temporary directories.

It validates configuration, stages metadata, validates the staged artifact,
promotes it, and cleans resources through an EXIT trap.

No real deployment target or network service is modified.
`
    );

    const result = runBash(
        "deployment simulation",
        `
set -Eeuo pipefail

readonly APP_NAME="example-service"
readonly VERSION="1.0.0"

staging_dir=""
target_dir=""

log() {
    printf '[INFO] %s\\n' "$*"
}

cleanup() {
    local status=$?

    if [[ -n "$staging_dir" && -d "$staging_dir" ]]; then
        rm -rf -- "$staging_dir"
    fi

    if [[ -n "$target_dir" && -d "$target_dir" ]]; then
        rm -rf -- "$target_dir"
    fi

    printf '[INFO] cleanup status=%s\\n' "$status" >&2
}

on_error() {
    local status=$?

    printf '[ERROR] status=%s command=%s line=%s\\n' \
        "$status" "$BASH_COMMAND" "${BASH_LINENO[0]}" >&2
}

trap on_error ERR
trap cleanup EXIT

: "\${APP_NAME:?application name is required}"
: "\${VERSION:?version is required}"

staging_dir="$(mktemp -d)"
target_dir="$(mktemp -d)"

log "created isolated staging resources"

printf 'name=%s\\nversion=%s\\n' \
    "$APP_NAME" "$VERSION" > "$staging_dir/metadata.txt"

grep -q "^version=$VERSION$" "$staging_dir/metadata.txt"

cp -- "$staging_dir/metadata.txt" "$target_dir/application.txt"

if [[ ! -s "$target_dir/application.txt" ]]; then
    printf 'promotion created an empty file\\n' >&2
    exit 1
fi

log "deployment simulation succeeded"
`
    );

    showResult(result);
}


function demonstrateTemporaryDirectoryFromNode() {
    section("14. Node.js filesystem integration");

    concept(
        "Why JavaScript is useful here",
        `
Node.js can manage files and processes around Bash automation. This makes it
possible to build an application-level orchestration layer while retaining Bash
for shell-native tasks.

The following example creates a temporary directory in Node.js, writes a shell
script into it, executes the script, and then removes the directory.
`
    );

    const prefix = path.join(os.tmpdir(), "bash-error-study-");
    const directory = fs.mkdtempSync(prefix);

    try {
        const scriptPath = path.join(directory, "check.sh");

        const script = `#!/usr/bin/env bash
set -Eeuo pipefail

trap 'status=$?; printf "cleanup status=%s\\n" "$status" >&2' EXIT

printf 'Node.js created this Bash workload\\n'
printf 'working directory=%s\\n' "$PWD"
`;

        fs.writeFileSync(scriptPath, script, { mode: 0o700 });

        const result = spawnSync(
            "bash",
            [scriptPath],
            {
                cwd: directory,
                encoding: "utf8",
            }
        );

        console.log(`exit code: ${result.status}`);
        console.log(result.stdout.trimEnd());

        if (result.stderr) {
            console.log("stderr:");
            console.log(result.stderr.trimEnd());
        }
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
        console.log("Node.js cleanup: temporary directory removed.");
    }
}


function printComparison() {
    section("15. Error-handling mechanism comparison");

    const mechanisms = [
        ["$?", "Inspect previous command status"],
        ["if", "Handle expected success/failure explicitly"],
        ["&& / ||", "Short-circuit command execution"],
        ["set -e", "Stop on many unhandled failures"],
        ["set -u", "Reject unintended unset variables"],
        ["pipefail", "Expose failures inside pipelines"],
        ["trap EXIT", "Centralize cleanup"],
        ["trap ERR", "Generate failure diagnostics"],
        ["trap INT/TERM", "React to process signals"],
        ["return", "Propagate function status"],
        ["exit", "Define process termination status"],
    ];

    console.log(`${"Mechanism".padEnd(18)}Purpose`);
    console.log("-".repeat(70));

    for (const [mechanism, purpose] of mechanisms) {
        console.log(`${mechanism.padEnd(18)}${purpose}`);
    }
}


function main() {
    console.log("Bash Error Handling Companion Study Program");
    console.log("Topic: exit codes, set -e, set -u, traps, defensive scripting");

    demonstrateExitCodes();
    demonstrateConditionals();
    demonstrateSetE();
    demonstrateSetU();
    demonstrateTraps();
    demonstrateQuotingAndArrays();
    demonstrateFunctions();
    demonstratePipelines();
    demonstrateExpectedFailures();
    demonstrateSubshells();
    demonstrateSecurity();
    demonstrateRetries();
    demonstrateIntegratedCaseStudy();
    demonstrateTemporaryDirectoryFromNode();
    printComparison();

    section("16. Completion");
    console.log(
        "All JavaScript and Bash demonstrations completed. " +
        "Nonzero Bash statuses were inspected without terminating the study."
    );
}


main();

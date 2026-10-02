#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

/*
 * GitHub Actions Basics
 *
 * Technical case study:
 *   A C++ repository has a CI workflow that validates changes, builds an
 *   application, and prepares a release. The program models the workflow as a
 *   directed dependency graph and evaluates whether each job can execute after
 *   a repository event occurs.
 *
 * The implementation concentrates on:
 *   - workflow triggers
 *   - events
 *   - jobs
 *   - ordered steps
 *   - job dependencies
 *   - conditional execution
 *   - matrix expansion
 *   - job outputs
 *   - failure propagation
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic github_actions_basics.cpp -o actions_demo
 */

namespace actions {

// -----------------------------------------------------------------------------
// Basic domain types
// -----------------------------------------------------------------------------

enum class JobStatus {
    Queued,
    Running,
    Success,
    Failure,
    Skipped
};

std::string to_string(JobStatus status) {
    switch (status) {
        case JobStatus::Queued:
            return "queued";
        case JobStatus::Running:
            return "running";
        case JobStatus::Success:
            return "success";
        case JobStatus::Failure:
            return "failure";
        case JobStatus::Skipped:
            return "skipped";
    }

    return "unknown";
}

struct RepositoryEvent {
    std::string name;
    std::string branch;
    std::string actor;
    std::string action;
    std::string commit;
};

struct StepResult {
    std::string name;
    JobStatus status;
    std::string message;
};

struct JobContext {
    RepositoryEvent event;
    std::string runner;
    std::map<std::string, std::string> environment;
    std::map<std::string, std::string> matrixValues;
    std::map<std::string, std::string> outputs;
};

using StepFunction = std::function<StepResult(JobContext&)>;

struct Step {
    std::string name;
    StepFunction execute;
    bool continueOnError{false};
};

struct Job {
    std::string id;
    std::string displayName;
    std::string runsOn;
    std::vector<std::string> needs;
    std::vector<Step> steps;
    std::function<bool(const RepositoryEvent&)> condition;
    std::map<std::string, std::vector<std::string>> matrix;
    std::map<std::string, std::string> environment;
    std::map<std::string, std::string> outputs;
    JobStatus status{JobStatus::Queued};
};

struct Workflow {
    std::string name;
    std::set<std::string> events;
    std::set<std::string> branches;
    std::map<std::string, Job> jobs;
};

// -----------------------------------------------------------------------------
// Output formatting
// -----------------------------------------------------------------------------

void heading(const std::string& title) {
    std::cout << "\n" << std::string(76, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(76, '=') << "\n";
}

void print_map(
    const std::map<std::string, std::string>& values,
    const std::string& prefix
) {
    for (const auto& [key, value] : values) {
        std::cout << prefix << key << "=" << value << "\n";
    }
}

// -----------------------------------------------------------------------------
// Trigger evaluation
// -----------------------------------------------------------------------------

bool event_matches(const Workflow& workflow, const RepositoryEvent& event) {
    /*
     * The trigger layer answers only one question: should this workflow start
     * for the supplied event? It does not evaluate individual jobs.
     */
    if (!workflow.events.contains(event.name)) {
        return false;
    }

    if (!workflow.branches.empty() &&
        !workflow.branches.contains(event.branch)) {
        return false;
    }

    return true;
}

// -----------------------------------------------------------------------------
// Matrix expansion
// -----------------------------------------------------------------------------

using MatrixCombination = std::map<std::string, std::string>;

std::vector<MatrixCombination> expand_matrix(
    const std::map<std::string, std::vector<std::string>>& matrix
) {
    /*
     * Matrix execution is a Cartesian product. Each generated combination is
     * treated as an independent concrete job instance.
     */
    std::vector<MatrixCombination> combinations{{}};

    for (const auto& [dimension, values] : matrix) {
        if (values.empty()) {
            throw std::invalid_argument(
                "Matrix dimension '" + dimension + "' has no values"
            );
        }

        std::vector<MatrixCombination> expanded;

        for (const auto& existing : combinations) {
            for (const auto& value : values) {
                auto combination = existing;
                combination[dimension] = value;
                expanded.push_back(std::move(combination));
            }
        }

        combinations = std::move(expanded);
    }

    return combinations;
}

// -----------------------------------------------------------------------------
// Dependency graph
// -----------------------------------------------------------------------------

class DependencyGraph {
public:
    explicit DependencyGraph(const std::map<std::string, Job>& jobs)
        : jobs_(jobs) {}

    std::vector<std::string> topological_order() const {
        /*
         * Kahn's algorithm is useful here because workflow jobs form a directed
         * acyclic graph. The indegree of a job represents the number of jobs
         * that must finish before it becomes eligible.
         */
        std::unordered_map<std::string, int> indegree;
        std::unordered_map<std::string, std::vector<std::string>> dependents;

        for (const auto& [jobId, job] : jobs_) {
            indegree[jobId] = static_cast<int>(job.needs.size());

            for (const auto& dependency : job.needs) {
                if (!jobs_.contains(dependency)) {
                    throw std::invalid_argument(
                        "Job '" + jobId +
                        "' references unknown dependency '" +
                        dependency + "'"
                    );
                }

                dependents[dependency].push_back(jobId);
            }
        }

        std::queue<std::string> ready;

        for (const auto& [jobId, degree] : indegree) {
            if (degree == 0) {
                ready.push(jobId);
            }
        }

        std::vector<std::string> order;

        while (!ready.empty()) {
            const auto current = ready.front();
            ready.pop();

            order.push_back(current);

            for (const auto& dependent : dependents[current]) {
                --indegree[dependent];

                if (indegree[dependent] == 0) {
                    ready.push(dependent);
                }
            }
        }

        if (order.size() != jobs_.size()) {
            throw std::invalid_argument(
                "Workflow contains a cyclic job dependency"
            );
        }

        return order;
    }

private:
    const std::map<std::string, Job>& jobs_;
};

// -----------------------------------------------------------------------------
// Workflow engine
// -----------------------------------------------------------------------------

class WorkflowEngine {
public:
    explicit WorkflowEngine(Workflow workflow)
        : workflow_(std::move(workflow)) {}

    void validate() const {
        if (workflow_.name.empty()) {
            throw std::invalid_argument("Workflow name cannot be empty");
        }

        if (workflow_.events.empty()) {
            throw std::invalid_argument(
                "Workflow must declare at least one trigger event"
            );
        }

        if (workflow_.jobs.empty()) {
            throw std::invalid_argument(
                "Workflow must contain at least one job"
            );
        }

        for (const auto& [jobId, job] : workflow_.jobs) {
            if (job.id.empty()) {
                throw std::invalid_argument(
                    "Job identifiers cannot be empty"
                );
            }

            if (job.runsOn.empty()) {
                throw std::invalid_argument(
                    "Job '" + jobId + "' is missing a runner"
                );
            }

            if (job.steps.empty()) {
                throw std::invalid_argument(
                    "Job '" + jobId + "' has no steps"
                );
            }

            for (const auto& dependency : job.needs) {
                if (!workflow_.jobs.contains(dependency)) {
                    throw std::invalid_argument(
                        "Job '" + jobId +
                        "' references unknown job '" +
                        dependency + "'"
                    );
                }
            }
        }

        DependencyGraph graph(workflow_.jobs);
        static_cast<void>(graph.topological_order());
    }

    void execute(const RepositoryEvent& event) {
        validate();

        heading("WORKFLOW EXECUTION: " + workflow_.name);

        if (!event_matches(workflow_, event)) {
            std::cout
                << "Workflow ignored event '" << event.name
                << "' on branch '" << event.branch << "'.\n";
            return;
        }

        std::cout
            << "Trigger matched: " << event.name
            << " / branch=" << event.branch
            << " / action=" << event.action << "\n";

        DependencyGraph graph(workflow_.jobs);
        const auto order = graph.topological_order();

        for (const auto& jobId : order) {
            Job& job = workflow_.jobs.at(jobId);

            if (dependency_failed(job)) {
                job.status = JobStatus::Skipped;
                std::cout
                    << "Job '" << job.displayName
                    << "' -> skipped because a dependency failed\n";
                continue;
            }

            if (job.condition && !job.condition(event)) {
                job.status = JobStatus::Skipped;
                std::cout
                    << "Job '" << job.displayName
                    << "' -> skipped by condition\n";
                continue;
            }

            const auto variants = expand_matrix(job.matrix);
            std::vector<JobStatus> variantStatuses;

            for (const auto& matrixValues : variants) {
                variantStatuses.push_back(
                    execute_job(job, event, matrixValues)
                );
            }

            if (std::any_of(
                    variantStatuses.begin(),
                    variantStatuses.end(),
                    [](JobStatus status) {
                        return status == JobStatus::Failure;
                    })) {
                job.status = JobStatus::Failure;
            } else if (
                std::all_of(
                    variantStatuses.begin(),
                    variantStatuses.end(),
                    [](JobStatus status) {
                        return status == JobStatus::Skipped;
                    })
            ) {
                job.status = JobStatus::Skipped;
            } else {
                job.status = JobStatus::Success;
            }
        }

        print_workflow_result();
    }

private:
    bool dependency_failed(const Job& job) const {
        for (const auto& dependency : job.needs) {
            const auto status = workflow_.jobs.at(dependency).status;

            if (
                status == JobStatus::Failure ||
                status == JobStatus::Skipped
            ) {
                return true;
            }
        }

        return false;
    }

    JobStatus execute_job(
        Job& job,
        const RepositoryEvent& event,
        const MatrixCombination& matrixValues
    ) {
        job.status = JobStatus::Running;

        std::ostringstream label;
        label << job.displayName;

        if (!matrixValues.empty()) {
            label << " [";

            bool first = true;
            for (const auto& [key, value] : matrixValues) {
                if (!first) {
                    label << ", ";
                }

                label << key << "=" << value;
                first = false;
            }

            label << "]";
        }

        std::cout
            << "\nJob '" << label.str()
            << "' on " << job.runsOn
            << " -> running\n";

        JobContext context{
            event,
            job.runsOn,
            {
                {"CI", "true"},
                {"GITHUB_EVENT_NAME", event.name},
                {"GITHUB_REF_NAME", event.branch},
                {"GITHUB_ACTOR", event.actor},
                {"RUNNER_OS", job.runsOn},
            },
            matrixValues,
            {}
        };

        for (const auto& [key, value] : job.environment) {
            context.environment[key] = value;
        }

        for (const auto& [key, value] : matrixValues) {
            context.environment[key] = value;
        }

        for (const auto& step : job.steps) {
            std::cout
                << "  Step '" << step.name
                << "' -> running\n";

            StepResult result;

            try {
                result = step.execute(context);
            } catch (const std::exception& error) {
                result = {
                    step.name,
                    JobStatus::Failure,
                    error.what()
                };
            }

            std::cout
                << "  Step '" << step.name
                << "' -> " << to_string(result.status);

            if (!result.message.empty()) {
                std::cout << ": " << result.message;
            }

            std::cout << "\n";

            if (result.status == JobStatus::Failure) {
                if (step.continueOnError) {
                    std::cout
                        << "  Failure is non-blocking because "
                        << "continue-on-error is enabled.\n";
                    continue;
                }

                job.status = JobStatus::Failure;
                std::cout
                    << "Job '" << label.str()
                    << "' -> failure\n";
                return JobStatus::Failure;
            }
        }

        job.outputs = context.outputs;
        job.status = JobStatus::Success;

        std::cout
            << "Job '" << label.str()
            << "' -> success\n";

        return JobStatus::Success;
    }

    void print_workflow_result() const {
        heading("WORKFLOW RESULT");

        for (const auto& [jobId, job] : workflow_.jobs) {
            std::cout
                << std::left
                << std::setw(18)
                << jobId
                << to_string(job.status)
                << "\n";

            if (!job.outputs.empty()) {
                print_map(job.outputs, "  output: ");
            }
        }
    }

    Workflow workflow_;
};

// -----------------------------------------------------------------------------
// Case-study step implementations
// -----------------------------------------------------------------------------

Step checkout_step() {
    return Step{
        "Checkout repository",
        [](JobContext& context) -> StepResult {
            /*
             * In a real workflow, actions/checkout retrieves repository content
             * into the runner workspace. The case study records that state so
             * later steps can depend on the checkout phase.
             */
            return {
                "Checkout repository",
                JobStatus::Success,
                "Repository revision " + context.event.commit +
                " is available in the workspace"
            };
        }
    };
}

Step lint_step() {
    return Step{
        "Lint source",
        [](JobContext& context) -> StepResult {
            /*
             * Linting is modeled as a quality gate. It is a separate job from
             * tests because the workflow can report style and test failures
             * independently.
             */
            return {
                "Lint source",
                JobStatus::Success,
                "C++ and JavaScript source passed configured style checks"
            };
        }
    };
}

Step test_step() {
    return Step{
        "Run tests",
        [](JobContext& context) -> StepResult {
            const auto iterator =
                context.matrixValues.find("compiler");

            const std::string compiler =
                iterator == context.matrixValues.end()
                    ? "default"
                    : iterator->second;

            /*
             * A matrix value changes the execution environment while preserving
             * one logical job definition.
             */
            if (compiler == "gcc-13") {
                return {
                    "Run tests",
                    JobStatus::Success,
                    "Tests passed with GCC 13 compatibility profile"
                };
            }

            if (compiler == "clang-18") {
                return {
                    "Run tests",
                    JobStatus::Success,
                    "Tests passed with Clang 18 compatibility profile"
                };
            }

            return {
                "Run tests",
                JobStatus::Success,
                "Tests passed"
            };
        }
    };
}

Step build_step() {
    return Step{
        "Build release",
        [](JobContext& context) -> StepResult {
            /*
             * Build runs only after its declared dependencies have succeeded.
             * This creates an explicit quality gate rather than relying on
             * execution order that happens to work today.
             */
            const auto testCompiler =
                context.environment.find("BUILD_MODE");

            const std::string mode =
                testCompiler == context.environment.end()
                    ? "release"
                    : testCompiler->second;

            return {
                "Build release",
                JobStatus::Success,
                "Produced application artifact in " + mode + " mode"
            };
        }
    };
}

Step publish_metadata_step() {
    return Step{
        "Publish build metadata",
        [](JobContext& context) -> StepResult {
            context.outputs["artifact"] =
                "application-" + context.event.commit + ".tar";

            context.outputs["source_branch"] = context.event.branch;

            return {
                "Publish build metadata",
                JobStatus::Success,
                "Job outputs recorded"
            };
        }
    };
}

Step deployment_step() {
    return Step{
        "Prepare deployment",
        [](JobContext& context) -> StepResult {
            if (context.event.branch != "main") {
                return {
                    "Prepare deployment",
                    JobStatus::Failure,
                    "Production deployment requires the main branch"
                };
            }

            return {
                "Prepare deployment",
                JobStatus::Success,
                "Release is eligible for production deployment"
            };
        }
    };
}

// -----------------------------------------------------------------------------
// Complete workflow
// -----------------------------------------------------------------------------

Workflow build_repository_workflow() {
    Workflow workflow;

    workflow.name = "C++ Repository CI";
    workflow.events = {"push", "pull_request"};
    workflow.branches = {"main", "develop"};

    Job lint;
    lint.id = "lint";
    lint.displayName = "Lint";
    lint.runsOn = "ubuntu-latest";
    lint.steps = {
        checkout_step(),
        lint_step()
    };

    Job tests;
    tests.id = "test";
    tests.displayName = "Test";
    tests.runsOn = "ubuntu-latest";
    tests.matrix = {
        {"compiler", {"gcc-13", "clang-18"}}
    };
    tests.steps = {
        checkout_step(),
        test_step()
    };

    Job build;
    build.id = "build";
    build.displayName = "Build";
    build.runsOn = "ubuntu-latest";
    build.needs = {"lint", "test"};
    build.environment = {
        {"BUILD_MODE", "release"}
    };
    build.steps = {
        checkout_step(),
        build_step(),
        publish_metadata_step()
    };

    Job deploy;
    deploy.id = "deploy";
    deploy.displayName = "Deploy";
    deploy.runsOn = "ubuntu-latest";
    deploy.needs = {"build"};
    deploy.condition = [](const RepositoryEvent& event) {
        /*
         * A pull request can validate the build but must not automatically
         * become a production deployment. The event type and branch are both
         * part of the condition.
         */
        return event.name == "push" && event.branch == "main";
    };
    deploy.steps = {
        deployment_step()
    };

    workflow.jobs = {
        {"lint", std::move(lint)},
        {"test", std::move(tests)},
        {"build", std::move(build)},
        {"deploy", std::move(deploy)}
    };

    return workflow;
}

// -----------------------------------------------------------------------------
// Failure propagation case study
// -----------------------------------------------------------------------------

Workflow build_failure_workflow() {
    Workflow workflow;

    workflow.name = "Failure Propagation";
    workflow.events = {"push"};
    workflow.branches = {"main"};

    Job test;
    test.id = "test";
    test.displayName = "Test";
    test.runsOn = "ubuntu-latest";

    test.steps = {
        Step{
            "Failing regression test",
            [](JobContext&) -> StepResult {
                return {
                    "Failing regression test",
                    JobStatus::Failure,
                    "Regression detected in payment calculation"
                };
            }
        }
    };

    Job build;
    build.id = "build";
    build.displayName = "Build";
    build.runsOn = "ubuntu-latest";
    build.needs = {"test"};
    build.steps = {
        build_step()
    };

    workflow.jobs = {
        {"test", std::move(test)},
        {"build", std::move(build)}
    };

    return workflow;
}

// -----------------------------------------------------------------------------
// Validation case study
// -----------------------------------------------------------------------------

void demonstrate_invalid_workflow() {
    heading("INVALID WORKFLOW DETECTION");

    Workflow invalid;
    invalid.name = "Broken Workflow";
    invalid.events = {"push"};

    Job first;
    first.id = "first";
    first.displayName = "First";
    first.runsOn = "ubuntu-latest";
    first.needs = {"second"};
    first.steps = {checkout_step()};

    Job second;
    second.id = "second";
    second.displayName = "Second";
    second.runsOn = "ubuntu-latest";
    second.needs = {"first"};
    second.steps = {checkout_step()};

    invalid.jobs = {
        {"first", std::move(first)},
        {"second", std::move(second)}
    };

    try {
        WorkflowEngine engine(std::move(invalid));
        engine.validate();
        std::cout << "Unexpected result: invalid workflow accepted\n";
    } catch (const std::exception& error) {
        std::cout
            << "Validation correctly rejected workflow: "
            << error.what()
            << "\n";
    }
}

// -----------------------------------------------------------------------------
// Main case-study execution
// -----------------------------------------------------------------------------

} // namespace actions

int main() {
    using namespace actions;

    try {
        heading("GITHUB ACTIONS BASICS: C++ CASE STUDY");

        Workflow workflow = build_repository_workflow();
        WorkflowEngine engine(std::move(workflow));

        heading("PULL REQUEST VALIDATION");

        RepositoryEvent pullRequest{
            "pull_request",
            "main",
            "contributor",
            "opened",
            "abc1234"
        };

        engine.execute(pullRequest);

        heading("PUSH TO MAIN");

        Workflow productionWorkflow = build_repository_workflow();
        WorkflowEngine productionEngine(std::move(productionWorkflow));

        RepositoryEvent push{
            "push",
            "main",
            "release-bot",
            "updated",
            "def5678"
        };

        productionEngine.execute(push);

        heading("FAILURE PROPAGATION");

        Workflow failureWorkflow = build_failure_workflow();
        WorkflowEngine failureEngine(std::move(failureWorkflow));

        RepositoryEvent failingPush{
            "push",
            "main",
            "developer",
            "updated",
            "bad9999"
        };

        failureEngine.execute(failingPush);

        demonstrate_invalid_workflow();

        heading("ARCHITECTURAL RELATIONSHIP");

        std::cout
            << "Workflow file  -> declares triggers and jobs\n"
            << "Event          -> starts a matching workflow\n"
            << "Job            -> isolated execution unit on a runner\n"
            << "Step           -> ordered operation inside a job\n"
            << "needs          -> directed dependency between jobs\n"
            << "matrix         -> expands one job into multiple variants\n"
            << "condition      -> decides whether eligible work executes\n"
            << "outputs        -> carry selected results from a completed job\n";

        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal workflow error: "
            << error.what()
            << "\n";

        return EXIT_FAILURE;
    }
}

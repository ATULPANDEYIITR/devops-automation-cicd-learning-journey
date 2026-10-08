#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

enum class JobStatus {
    Pending,
    Passed,
    Failed,
    Cancelled
};

enum class DependencyMode {
    Minimum,
    Locked,
    Latest
};

std::string to_string(DependencyMode mode) {
    switch (mode) {
        case DependencyMode::Minimum:
            return "minimum";
        case DependencyMode::Locked:
            return "locked";
        case DependencyMode::Latest:
            return "latest";
    }
    return "unknown";
}

std::string to_string(JobStatus status) {
    switch (status) {
        case JobStatus::Pending:
            return "pending";
        case JobStatus::Passed:
            return "passed";
        case JobStatus::Failed:
            return "failed";
        case JobStatus::Cancelled:
            return "cancelled";
    }
    return "unknown";
}

struct MatrixJob {
    std::string python;
    std::string operating_system;
    DependencyMode dependency_mode;
    bool experimental = false;

    std::string key() const {
        return python + "/" + operating_system + "/" +
               to_string(dependency_mode);
    }
};

struct JobResult {
    MatrixJob job;
    JobStatus status = JobStatus::Pending;
    int attempts = 0;
    std::string message;
};

struct MatrixPolicy {
    std::vector<std::string> supported_python;
    std::vector<std::string> supported_os;
    std::vector<DependencyMode> dependency_modes;
    bool fail_fast = true;
};

class RepositoryGovernanceEngine {
public:
    explicit RepositoryGovernanceEngine(MatrixPolicy policy)
        : policy_(std::move(policy)) {}

    std::vector<MatrixJob> expand(
        const std::vector<std::tuple<std::string, std::string, DependencyMode>>&
            exclusions,
        const std::vector<MatrixJob>& additions) const {

        std::vector<MatrixJob> jobs;

        for (const auto& python : policy_.supported_python) {
            for (const auto& operating_system : policy_.supported_os) {
                for (const auto& dependency_mode : policy_.dependency_modes) {
                    MatrixJob candidate{
                        python,
                        operating_system,
                        dependency_mode,
                        false
                    };

                    if (isExcluded(candidate, exclusions)) {
                        continue;
                    }

                    jobs.push_back(candidate);
                }
            }
        }

        // Explicit additions represent matrix combinations that are not
        // naturally produced by the Cartesian product, such as a canary job.
        for (const auto& addition : additions) {
            auto existing = std::find_if(
                jobs.begin(),
                jobs.end(),
                [&](const MatrixJob& job) {
                    return job.python == addition.python &&
                           job.operating_system == addition.operating_system &&
                           job.dependency_mode == addition.dependency_mode;
                });

            if (existing != jobs.end()) {
                existing->experimental = addition.experimental;
            } else {
                jobs.push_back(addition);
            }
        }

        return jobs;
    }

    std::vector<JobResult> evaluate(const std::vector<MatrixJob>& jobs) const {
        std::vector<JobResult> results;
        bool blocking_failure = false;

        for (const auto& job : jobs) {
            if (policy_.fail_fast &&
                blocking_failure &&
                !job.experimental) {

                results.push_back({
                    job,
                    JobStatus::Cancelled,
                    0,
                    "Cancelled by fail-fast after a blocking failure."
                });
                continue;
            }

            JobResult result = runTests(job);

            if (result.status == JobStatus::Failed && !job.experimental) {
                blocking_failure = true;
            }

            results.push_back(std::move(result));
        }

        return results;
    }

private:
    MatrixPolicy policy_;

    static bool isExcluded(
        const MatrixJob& job,
        const std::vector<
            std::tuple<std::string, std::string, DependencyMode>>& exclusions) {

        return std::any_of(
            exclusions.begin(),
            exclusions.end(),
            [&](const auto& exclusion) {
                const auto& [python, operating_system, dependency_mode] =
                    exclusion;

                return job.python == python &&
                       job.operating_system == operating_system &&
                       job.dependency_mode == dependency_mode;
            });
    }

    static JobResult runTests(const MatrixJob& job) {
        JobResult result;
        result.job = job;

        // The case study models compatibility failures that are tied to
        // concrete matrix dimensions rather than arbitrary random failures.
        if (job.python == "3.10" &&
            job.dependency_mode == DependencyMode::Latest) {

            result.status = JobStatus::Failed;
            result.message =
                "Latest dependencies have removed Python 3.10 support.";
            result.attempts = 1;
            return result;
        }

        if (job.operating_system == "windows" &&
            job.python == "3.10") {

            result.status = JobStatus::Failed;
            result.message =
                "Legacy Windows integration test failed.";
            result.attempts = 1;
            return result;
        }

        if (job.operating_system == "macos" &&
            job.python == "3.13") {

            result.status = JobStatus::Failed;
            result.message =
                "Native extension test is incompatible with Python 3.13.";
            result.attempts = 1;
            return result;
        }

        if (job.python == "3.13" &&
            job.dependency_mode == DependencyMode::Minimum) {

            result.status = JobStatus::Failed;
            result.message =
                "Minimum dependency policy has no compatible release.";
            result.attempts = 1;
            return result;
        }

        result.status = JobStatus::Passed;
        result.message =
            "Unit, integration, packaging, and compatibility checks passed.";
        result.attempts = 1;
        return result;
    }
};

class MatrixReporter {
public:
    static void printExpandedMatrix(const std::vector<MatrixJob>& jobs) {
        std::cout << "\nExpanded matrix\n"
                  << std::string(100, '-') << '\n';

        for (const auto& job : jobs) {
            std::cout
                << std::left
                << std::setw(6) << job.python
                << std::setw(12) << job.operating_system
                << std::setw(12) << to_string(job.dependency_mode)
                << (job.experimental ? "experimental" : "release-blocking")
                << '\n';
        }
    }

    static void printResults(const std::vector<JobResult>& results) {
        std::cout << "\nExecution results\n"
                  << std::string(120, '-') << '\n';

        for (const auto& result : results) {
            std::cout
                << std::left
                << std::setw(10) << to_string(result.status)
                << std::setw(32) << result.job.key()
                << std::setw(10) << result.attempts
                << result.message
                << '\n';
        }
    }

    static std::map<std::string, int>
    countByPython(const std::vector<JobResult>& results) {
        std::map<std::string, int> counts;

        for (const auto& result : results) {
            if (result.status == JobStatus::Passed) {
                ++counts[result.job.python];
            }
        }

        return counts;
    }
};

int main() {
    try {
        /*
         * The repository supports several Python versions, three execution
         * environments, and three dependency strategies. The engine evaluates
         * every meaningful combination as an independent build/test job.
         */
        MatrixPolicy policy{
            {"3.10", "3.11", "3.12", "3.13"},
            {"ubuntu", "windows", "macos"},
            {
                DependencyMode::Minimum,
                DependencyMode::Locked,
                DependencyMode::Latest
            },
            false
        };

        RepositoryGovernanceEngine engine(policy);

        std::vector<
            std::tuple<std::string, std::string, DependencyMode>>
            exclusions{
                {"3.10", "macos", DependencyMode::Minimum},
                {"3.13", "windows", DependencyMode::Minimum}
            };

        std::vector<MatrixJob> additions{
            {"3.13", "ubuntu", DependencyMode::Latest, true}
        };

        const auto jobs = engine.expand(exclusions, additions);

        MatrixReporter::printExpandedMatrix(jobs);

        const auto results = engine.evaluate(jobs);

        MatrixReporter::printResults(results);

        int passed = 0;
        int failed = 0;
        int cancelled = 0;

        for (const auto& result : results) {
            switch (result.status) {
                case JobStatus::Passed:
                    ++passed;
                    break;
                case JobStatus::Failed:
                    ++failed;
                    break;
                case JobStatus::Cancelled:
                    ++cancelled;
                    break;
                case JobStatus::Pending:
                    break;
            }
        }

        std::cout << "\nCoverage statistics\n"
                  << std::string(60, '-') << '\n'
                  << "Concrete matrix jobs: " << results.size() << '\n'
                  << "Passed:               " << passed << '\n'
                  << "Failed:               " << failed << '\n'
                  << "Cancelled:            " << cancelled << '\n';

        const auto successful_by_python =
            MatrixReporter::countByPython(results);

        std::cout << "\nSuccessful jobs by Python version\n"
                  << std::string(60, '-') << '\n';

        for (const auto& [version, count] : successful_by_python) {
            std::cout << "Python " << version << ": " << count << '\n';
        }

        std::cout << "\nCase-study interpretation\n"
                  << std::string(60, '-') << '\n'
                  << "The matrix separates compatibility dimensions from "
                     "individual test results.\n"
                  << "A failure can identify a specific runtime, operating "
                     "system, or dependency policy.\n"
                  << "An experimental combination does not automatically "
                     "block the release workflow.\n";

        return failed > 0 ? 1 : 0;
    } catch (const std::exception& error) {
        std::cerr << "Matrix evaluation error: "
                  << error.what() << '\n';
        return 2;
    }
}

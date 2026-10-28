#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

enum class PipelineState {
    Created,
    Built,
    Tested,
    Scanned,
    Published,
    Failed
};

std::string toString(PipelineState state) {
    switch (state) {
        case PipelineState::Created: return "created";
        case PipelineState::Built: return "built";
        case PipelineState::Tested: return "tested";
        case PipelineState::Scanned: return "scanned";
        case PipelineState::Published: return "published";
        case PipelineState::Failed: return "failed";
    }
    return "unknown";
}

enum class ReviewStatus {
    NotRun,
    Passed,
    Failed
};

struct StatusCheck {
    std::string name;
    ReviewStatus status{ReviewStatus::NotRun};
    std::string details;
};

struct Image {
    std::string repository;
    std::string tag;
    std::string digest;

    std::string reference() const {
        return repository + ":" + tag;
    }
};

struct PipelineContext {
    std::string project;
    std::string sourceBranch;
    std::string commit;
    Image image;
    std::vector<StatusCheck> checks;
    bool credentialsAvailable{false};
    bool registryReachable{false};
    bool publishRequested{false};
};

class GovernanceError : public std::runtime_error {
public:
    explicit GovernanceError(const std::string& message)
        : std::runtime_error(message) {}
};

class MergeEligibilityEngine {
public:
    struct Policy {
        bool requireTests{true};
        bool requireSecurityScan{true};
        bool requireImmutableDigest{true};
        bool requireRegistry{true};
        std::set<std::string> blockedTags{"latest", "prod", "production"};
    };

    explicit MergeEligibilityEngine(Policy policy = {})
        : policy_(std::move(policy)) {}

    bool eligible(const PipelineContext& context,
                  std::vector<std::string>& failures) const {
        failures.clear();

        if (context.project.empty()) {
            failures.push_back("project is required");
        }

        if (context.sourceBranch.empty()) {
            failures.push_back("source branch is required");
        }

        if (context.commit.empty()) {
            failures.push_back("source commit is required");
        }

        if (context.image.repository.empty() || context.image.tag.empty()) {
            failures.push_back("image repository and tag are required");
        }

        if (policy_.blockedTags.contains(context.image.tag)) {
            failures.push_back("mutable production-style tag is blocked");
        }

        auto passed = [&context](const std::string& name) {
            return std::any_of(
                context.checks.begin(),
                context.checks.end(),
                [&name](const StatusCheck& check) {
                    return check.name == name &&
                           check.status == ReviewStatus::Passed;
                });
        };

        if (policy_.requireTests && !passed("unit-tests")) {
            failures.push_back("unit-tests did not pass");
        }

        if (policy_.requireSecurityScan && !passed("security-scan")) {
            failures.push_back("security-scan did not pass");
        }

        if (policy_.requireImmutableDigest &&
            context.image.digest.empty()) {
            failures.push_back("image digest is missing");
        }

        if (context.publishRequested) {
            if (policy_.requireRegistry && !context.registryReachable) {
                failures.push_back("registry is unavailable");
            }

            if (!context.credentialsAvailable) {
                failures.push_back("registry credentials are unavailable");
            }
        }

        return failures.empty();
    }

private:
    Policy policy_;
};

class ContainerPipeline {
public:
    explicit ContainerPipeline(PipelineContext context)
        : context_(std::move(context)) {}

    void build() {
        require(PipelineState::Created);

        validateImage();

        // A real CI runner would execute docker build here. This executable
        // models the governance decision while keeping the case study
        // portable and independent of a local Docker daemon.
        context_.image.digest = calculateDigest(
            context_.project + ":" +
            context_.sourceBranch + ":" +
            context_.commit
        );

        transition(PipelineState::Built);
    }

    void test() {
        require(PipelineState::Built);

        addCheck("unit-tests", ReviewStatus::Passed,
                 "application test suite completed");

        transition(PipelineState::Tested);
    }

    void scan() {
        require(PipelineState::Tested);

        // Security policy rejects obvious unsafe image tags before publication.
        if (context_.image.tag == "latest") {
            addCheck("security-scan", ReviewStatus::Failed,
                     "mutable latest tag is prohibited");
            fail("security policy rejected image");
        }

        addCheck("security-scan", ReviewStatus::Passed,
                 "no high or critical findings");

        transition(PipelineState::Scanned);
    }

    bool publish() {
        require(PipelineState::Scanned);

        if (!context_.credentialsAvailable) {
            fail("registry credentials are unavailable");
        }

        if (!context_.registryReachable) {
            fail("registry is unreachable");
        }

        // Publication is modeled as successful only after all prerequisites
        // have already passed.
        transition(PipelineState::Published);
        return true;
    }

    const PipelineContext& context() const {
        return context_;
    }

    PipelineState state() const {
        return state_;
    }

private:
    PipelineContext context_;
    PipelineState state_{PipelineState::Created};

    void require(PipelineState expected) const {
        if (state_ != expected) {
            throw GovernanceError(
                "invalid state transition: expected " +
                toString(expected) +
                ", actual " +
                toString(state_)
            );
        }
    }

    void transition(PipelineState next) {
        state_ = next;
    }

    void validateImage() const {
        static const std::regex repositoryPattern(
            R"(^[a-z0-9][a-z0-9._/-]*$)"
        );
        static const std::regex tagPattern(
            R"(^[A-Za-z0-9_.-]+$)"
        );

        if (!std::regex_match(context_.image.repository,
                              repositoryPattern)) {
            throw GovernanceError("invalid image repository");
        }

        if (!std::regex_match(context_.image.tag, tagPattern)) {
            throw GovernanceError("invalid image tag");
        }
    }

    static std::string calculateDigest(const std::string& input) {
        // std::hash is used only as a portable deterministic fingerprint for
        // this case study. A production registry should expose a SHA-256
        // content digest and that digest should be persisted unchanged.
        const std::size_t value = std::hash<std::string>{}(input);
        std::ostringstream stream;
        stream << "sha256:" << std::hex << std::setw(16)
               << std::setfill('0') << value;
        return stream.str();
    }

    void addCheck(const std::string& name,
                  ReviewStatus status,
                  const std::string& details) {
        context_.checks.push_back({name, status, details});
    }

    [[noreturn]] void fail(const std::string& message) {
        state_ = PipelineState::Failed;
        throw GovernanceError(message);
    }
};

void printChecks(const PipelineContext& context) {
    std::cout << "Checks:\n";
    for (const auto& check : context.checks) {
        std::cout << "  - " << check.name << ": "
                  << (check.status == ReviewStatus::Passed
                          ? "passed"
                          : check.status == ReviewStatus::Failed
                                ? "failed"
                                : "not-run")
                  << " (" << check.details << ")\n";
    }
}

int main() {
    try {
        PipelineContext context{
            .project = "payments-api",
            .sourceBranch = "feature/container-pipeline",
            .commit = "9c1e7f2",
            .image = {
                "registry.example.com/platform/payments-api",
                "2026.10.28-9c1e7f2",
                ""
            },
            .checks = {},
            .credentialsAvailable = true,
            .registryReachable = true,
            .publishRequested = true
        };

        ContainerPipeline pipeline(context);

        pipeline.build();
        pipeline.test();
        pipeline.scan();

        MergeEligibilityEngine::Policy policy;
        MergeEligibilityEngine governance(policy);

        std::vector<std::string> failures;
        if (!governance.eligible(
                pipeline.context(),
                failures)) {
            std::cerr << "Pipeline is not eligible:\n";
            for (const auto& failure : failures) {
                std::cerr << "  - " << failure << '\n';
            }
            return EXIT_FAILURE;
        }

        pipeline.publish();

        const auto& finalContext = pipeline.context();

        std::cout << "Container CI/CD governance result\n";
        std::cout << "Project: " << finalContext.project << '\n';
        std::cout << "Commit: " << finalContext.commit << '\n';
        std::cout << "Image: " << finalContext.image.reference() << '\n';
        std::cout << "Digest: " << finalContext.image.digest << '\n';
        std::cout << "State: " << toString(pipeline.state()) << '\n';
        printChecks(finalContext);

        // Demonstrate an edge case without affecting the successful pipeline.
        PipelineContext unsafe = finalContext;
        unsafe.image.tag = "latest";

        std::vector<std::string> rejected;
        if (!governance.eligible(unsafe, rejected)) {
            std::cout << "\nRejected policy scenario:\n";
            for (const auto& reason : rejected) {
                std::cout << "  - " << reason << '\n';
            }
        }

        return EXIT_SUCCESS;
    } catch (const GovernanceError& error) {
        std::cerr << "Governance failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    } catch (const std::exception& error) {
        std::cerr << "Unexpected failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}

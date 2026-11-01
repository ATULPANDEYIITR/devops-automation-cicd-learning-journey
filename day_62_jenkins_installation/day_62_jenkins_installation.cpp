#include <algorithm>
#include <exception>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class ControllerState {
    New,
    Validated,
    Installed
};

enum class ReviewResult {
    Approved,
    ChangesRequested,
    Commented,
    Pending
};

enum class CheckState {
    Passing,
    Failing,
    Pending
};

enum class MergeState {
    Eligible,
    Blocked
};

struct Plugin {
    std::string name;
    std::string version;
    int requiredJava;
    std::vector<std::string> dependencies;
    bool securityApproved;
};

struct StatusCheck {
    std::string name;
    CheckState state;
};

struct Review {
    std::string reviewer;
    ReviewResult result;
    bool eligible;
    bool stale;
};

struct PullRequest {
    int id;
    std::string title;
    std::string sourceBranch;
    std::string targetBranch;
    std::string headCommit;
    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;
    bool draft;
    bool conversationsResolved;
    bool mergeConflict;
};

struct BranchPolicy {
    std::string branch;
    int requiredApprovals;
    std::set<std::string> requiredChecks;
    bool requireResolvedConversations;
    bool prohibitForcePush;
    bool prohibitDirectPush;
    bool requireLinearHistory;
};

class GovernanceError : public std::runtime_error {
public:
    explicit GovernanceError(const std::string& message)
        : std::runtime_error(message) {}
};

class PluginManager {
private:
    std::map<std::string, Plugin> catalog;
    std::set<std::string> installed;

    void resolve(
        const std::string& name,
        int javaMajor,
        std::set<std::string>& visiting,
        std::set<std::string>& visited,
        std::vector<std::string>& order
    ) {
        if (visited.count(name)) {
            return;
        }

        if (visiting.count(name)) {
            throw GovernanceError(
                "Circular plugin dependency: " + name
            );
        }

        auto it = catalog.find(name);
        if (it == catalog.end()) {
            throw GovernanceError("Unknown plugin: " + name);
        }

        const Plugin& plugin = it->second;

        if (plugin.requiredJava > javaMajor) {
            throw GovernanceError(
                "Plugin " + name + " requires Java " +
                std::to_string(plugin.requiredJava)
            );
        }

        if (!plugin.securityApproved) {
            throw GovernanceError(
                "Plugin rejected by security policy: " + name
            );
        }

        visiting.insert(name);

        for (const auto& dependency : plugin.dependencies) {
            resolve(
                dependency,
                javaMajor,
                visiting,
                visited,
                order
            );
        }

        visiting.erase(name);
        visited.insert(name);
        order.push_back(name);
    }

public:
    void registerPlugin(const Plugin& plugin) {
        if (plugin.name.empty()) {
            throw GovernanceError("Plugin name cannot be empty.");
        }

        if (catalog.count(plugin.name)) {
            throw GovernanceError(
                "Duplicate plugin: " + plugin.name
            );
        }

        catalog.emplace(plugin.name, plugin);
    }

    void install(
        const std::vector<std::string>& requested,
        int javaMajor
    ) {
        std::set<std::string> visiting;
        std::set<std::string> visited;
        std::vector<std::string> order;

        for (const auto& plugin : requested) {
            resolve(
                plugin,
                javaMajor,
                visiting,
                visited,
                order
            );
        }

        for (const auto& plugin : order) {
            installed.insert(plugin);
        }
    }

    bool isInstalled(const std::string& plugin) const {
        return installed.count(plugin) > 0;
    }

    std::vector<std::string> installedPlugins() const {
        return {
            installed.begin(),
            installed.end()
        };
    }
};

class MergeEligibilityEngine {
private:
    static int countValidApprovals(
        const PullRequest& pr
    ) {
        std::set<std::string> reviewers;

        for (const auto& review : pr.reviews) {
            if (
                review.result == ReviewResult::Approved &&
                review.eligible &&
                !review.stale
            ) {
                reviewers.insert(review.reviewer);
            }
        }

        return static_cast<int>(reviewers.size());
    }

    static bool checksPass(
        const PullRequest& pr,
        const BranchPolicy& policy
    ) {
        std::map<std::string, CheckState> states;

        for (const auto& check : pr.checks) {
            states[check.name] = check.state;
        }

        for (const auto& required : policy.requiredChecks) {
            auto it = states.find(required);

            if (
                it == states.end() ||
                it->second != CheckState::Passing
            ) {
                return false;
            }
        }

        return true;
    }

public:
    static MergeState evaluate(
        const PullRequest& pr,
        const BranchPolicy& policy,
        std::vector<std::string>& reasons
    ) {
        reasons.clear();

        if (pr.targetBranch != policy.branch) {
            reasons.push_back("Pull Request targets a different branch.");
        }

        if (pr.draft) {
            reasons.push_back("Draft Pull Requests cannot be merged.");
        }

        if (pr.mergeConflict) {
            reasons.push_back("Merge conflict must be resolved.");
        }

        if (
            policy.requireResolvedConversations &&
            !pr.conversationsResolved
        ) {
            reasons.push_back("Open review conversations remain.");
        }

        const int approvals = countValidApprovals(pr);

        if (approvals < policy.requiredApprovals) {
            reasons.push_back(
                "Required approvals not satisfied: " +
                std::to_string(approvals) + "/" +
                std::to_string(policy.requiredApprovals)
            );
        }

        if (!checksPass(pr, policy)) {
            reasons.push_back("Required status checks are not passing.");
        }

        if (reasons.empty()) {
            return MergeState::Eligible;
        }

        return MergeState::Blocked;
    }
};

class JenkinsInstallation {
private:
    ControllerState state = ControllerState::New;
    int javaMajor = 0;
    int httpPort = 0;
    int executors = 0;
    PluginManager plugins;

public:
    void validate(
        int java,
        int port,
        int executorCount
    ) {
        if (java < 17) {
            throw GovernanceError("Java 17+ is required.");
        }

        if (port < 1024 || port > 65535) {
            throw GovernanceError("Invalid HTTP port.");
        }

        if (executorCount < 1 || executorCount > 32) {
            throw GovernanceError("Invalid executor count.");
        }

        javaMajor = java;
        httpPort = port;
        executors = executorCount;
        state = ControllerState::Validated;
    }

    void install() {
        if (state != ControllerState::Validated) {
            throw GovernanceError(
                "Prerequisite validation must occur first."
            );
        }

        state = ControllerState::Installed;
    }

    PluginManager& pluginManager() {
        if (state != ControllerState::Installed) {
            throw GovernanceError(
                "Controller is not installed."
            );
        }

        return plugins;
    }

    void printConfiguration() const {
        std::cout
            << "Controller state: installed\n"
            << "Java major: " << javaMajor << "\n"
            << "HTTP port: " << httpPort << "\n"
            << "Executors: " << executors << "\n";
    }
};

static std::string reviewResultToString(ReviewResult result) {
    switch (result) {
        case ReviewResult::Approved:
            return "approved";
        case ReviewResult::ChangesRequested:
            return "changes_requested";
        case ReviewResult::Commented:
            return "commented";
        case ReviewResult::Pending:
            return "pending";
    }

    return "unknown";
}

int main() {
    try {
        JenkinsInstallation jenkins;

        jenkins.validate(
            21,
            8080,
            4
        );

        jenkins.install();

        jenkins.pluginManager().registerPlugin({
            "git",
            "5.6.0",
            17,
            {},
            true
        });

        jenkins.pluginManager().registerPlugin({
            "credentials",
            "1400.1",
            17,
            {},
            true
        });

        jenkins.pluginManager().registerPlugin({
            "workflow-api",
            "1400.1",
            17,
            {},
            true
        });

        jenkins.pluginManager().registerPlugin({
            "workflow-job",
            "1500.1",
            17,
            {"workflow-api"},
            true
        });

        jenkins.pluginManager().registerPlugin({
            "pipeline-model-definition",
            "2.22.0",
            17,
            {"workflow-job", "credentials"},
            true
        });

        jenkins.pluginManager().install(
            {
                "git",
                "credentials",
                "pipeline-model-definition"
            },
            21
        );

        jenkins.printConfiguration();

        std::cout << "\nInstalled plugins:\n";
        for (
            const auto& plugin :
            jenkins.pluginManager().installedPlugins()
        ) {
            std::cout << "- " << plugin << "\n";
        }

        BranchPolicy policy{
            "main",
            2,
            {"build", "unit-tests", "security-scan"},
            true,
            true,
            true,
            true
        };

        PullRequest pullRequest{
            1042,
            "Harden authentication pipeline",
            "feature/auth-hardening",
            "main",
            "a8e9d2",
            {
                {
                    "reviewer-alice",
                    ReviewResult::Approved,
                    true,
                    false
                },
                {
                    "reviewer-bob",
                    ReviewResult::Approved,
                    true,
                    false
                },
                {
                    "reviewer-service",
                    ReviewResult::Approved,
                    false,
                    false
                }
            },
            {
                {"build", CheckState::Passing},
                {"unit-tests", CheckState::Passing},
                {"security-scan", CheckState::Passing}
            },
            false,
            true,
            false
        };

        std::vector<std::string> reasons;

        MergeState result =
            MergeEligibilityEngine::evaluate(
                pullRequest,
                policy,
                reasons
            );

        std::cout << "\nPull Request #" << pullRequest.id << "\n";
        std::cout << "Title: " << pullRequest.title << "\n";
        std::cout << "Review state:\n";

        for (const auto& review : pullRequest.reviews) {
            std::cout
                << "  "
                << review.reviewer
                << ": "
                << reviewResultToString(review.result)
                << ", eligible="
                << (review.eligible ? "yes" : "no")
                << ", stale="
                << (review.stale ? "yes" : "no")
                << "\n";
        }

        if (result == MergeState::Eligible) {
            std::cout << "Merge eligibility: ELIGIBLE\n";
        } else {
            std::cout << "Merge eligibility: BLOCKED\n";

            for (const auto& reason : reasons) {
                std::cout << "- " << reason << "\n";
            }
        }

        // Demonstrate a stale approval blocking a later revision.
        pullRequest.reviews[1].stale = true;

        result = MergeEligibilityEngine::evaluate(
            pullRequest,
            policy,
            reasons
        );

        std::cout << "\nAfter new commit invalidates one approval:\n";

        if (result == MergeState::Eligible) {
            std::cout << "Merge eligibility: ELIGIBLE\n";
        } else {
            std::cout << "Merge eligibility: BLOCKED\n";

            for (const auto& reason : reasons) {
                std::cout << "- " << reason << "\n";
            }
        }

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Configuration or governance failure: "
            << error.what()
            << "\n";
        return 1;
    }
}

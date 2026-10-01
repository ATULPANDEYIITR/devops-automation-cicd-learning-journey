/*
    GitHub Fundamentals: Repository Governance and Delivery Case Study

    C++17 case study:
      - Repository and branch representation
      - Issue tracking
      - Project planning
      - Pull Request state
      - Actions-style status checks
      - Environment protection
      - Merge eligibility
      - Deployment audit records

    Compile:
      g++ -std=c++17 -Wall -Wextra -pedantic github_fundamentals.cpp -o github_fundamentals

    The program intentionally models GitHub behavior instead of calling the
    GitHub API. This keeps the case study self-contained and deterministic.
*/

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace std;

static string nowUtcLike() {
    auto current = chrono::system_clock::now();
    auto time = chrono::system_clock::to_time_t(current);

    tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif

    ostringstream output;
    output << put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return output.str();
}

enum class IssueState {
    Open,
    Closed
};

enum class CheckStatus {
    Pending,
    Success,
    Failure
};

enum class EnvironmentState {
    Ready,
    WaitingForApproval,
    Deployed,
    Failed
};

enum class PullRequestState {
    Open,
    Closed,
    Merged
};

struct Issue {
    int number;
    string title;
    string body;
    string author;
    IssueState state = IssueState::Open;
    set<string> labels;
    vector<string> comments;
};

struct ProjectItem {
    string type;
    string identifier;
    string status = "Todo";
    string priority = "Medium";
};

struct StatusCheck {
    string name;
    CheckStatus status = CheckStatus::Pending;
};

struct PullRequest {
    int number;
    string sourceBranch;
    string targetBranch;
    string title;
    string author;
    PullRequestState state = PullRequestState::Open;
    bool draft = true;
    vector<string> commits;
    set<string> changedFiles;
    vector<int> linkedIssues;
    vector<StatusCheck> checks;
};

struct Environment {
    string name;
    EnvironmentState state = EnvironmentState::Ready;
    int requiredApprovals = 0;
    set<string> approvers;
    set<string> deploymentSecrets;
};

struct DeploymentRecord {
    string environment;
    string branch;
    string commit;
    string actor;
    EnvironmentState state;
    string timestamp;
};

class Repository {
private:
    string owner;
    string name;
    string visibility;
    set<string> branches;
    set<string> files;

public:
    Repository(string repositoryOwner,
               string repositoryName,
               string repositoryVisibility)
        : owner(move(repositoryOwner)),
          name(move(repositoryName)),
          visibility(move(repositoryVisibility)) {
        branches.insert("main");
    }

    const string& defaultBranch() const {
        static const string mainBranch = "main";
        return mainBranch;
    }

    string fullName() const {
        return owner + "/" + name;
    }

    void createBranch(const string& branch) {
        if (branch.empty() || branch.find(' ') != string::npos) {
            throw invalid_argument("Invalid branch name.");
        }

        if (!branches.insert(branch).second) {
            throw invalid_argument("Branch already exists: " + branch);
        }
    }

    bool hasBranch(const string& branch) const {
        return branches.count(branch) > 0;
    }

    void addFile(const string& path) {
        if (path.empty() || path.rfind("../", 0) == 0) {
            throw invalid_argument("Invalid repository-relative path.");
        }

        files.insert(path);
    }

    bool hasFile(const string& path) const {
        return files.count(path) > 0;
    }

    void printState() const {
        cout << "Repository: " << fullName() << '\n';
        cout << "Visibility: " << visibility << '\n';

        cout << "Branches: ";
        for (const auto& branch : branches) {
            cout << branch << ' ';
        }
        cout << '\n';

        cout << "Files: ";
        for (const auto& file : files) {
            cout << file << ' ';
        }
        cout << "\n";
    }
};

class IssueManager {
private:
    int nextNumber = 1;
    map<int, Issue> issues;

public:
    Issue& create(const string& title,
                  const string& body,
                  const string& author) {
        if (title.empty()) {
            throw invalid_argument("Issue title cannot be empty.");
        }

        Issue issue{
            nextNumber,
            title,
            body,
            author
        };

        auto [iterator, inserted] =
            issues.emplace(nextNumber, move(issue));

        if (!inserted) {
            throw runtime_error("Unable to allocate issue number.");
        }

        ++nextNumber;
        return iterator->second;
    }

    Issue& get(int number) {
        auto iterator = issues.find(number);
        if (iterator == issues.end()) {
            throw out_of_range("Issue does not exist.");
        }

        return iterator->second;
    }

    size_t openCount() const {
        size_t count = 0;

        for (const auto& [number, issue] : issues) {
            (void)number;

            if (issue.state == IssueState::Open) {
                ++count;
            }
        }

        return count;
    }
};

class Project {
private:
    string name;
    map<string, ProjectItem> items;

    bool validStatus(const string& status) const {
        static const set<string> statuses{
            "Todo",
            "In Progress",
            "Blocked",
            "Done"
        };

        return statuses.count(status) > 0;
    }

public:
    explicit Project(string projectName)
        : name(move(projectName)) {}

    void addItem(const string& type,
                 const string& identifier,
                 const string& status,
                 const string& priority) {
        if (!validStatus(status)) {
            throw invalid_argument("Invalid project status.");
        }

        string key = type + ":" + identifier;
        items[key] = ProjectItem{
            type,
            identifier,
            status,
            priority
        };
    }

    void moveItem(const string& type,
                  const string& identifier,
                  const string& status) {
        if (!validStatus(status)) {
            throw invalid_argument("Invalid project status.");
        }

        string key = type + ":" + identifier;
        auto iterator = items.find(key);

        if (iterator == items.end()) {
            throw out_of_range("Project item does not exist: " + key);
        }

        iterator->second.status = status;
    }

    map<string, int> statusCounts() const {
        map<string, int> counts{
            {"Todo", 0},
            {"In Progress", 0},
            {"Blocked", 0},
            {"Done", 0}
        };

        for (const auto& [key, item] : items) {
            (void)key;
            ++counts[item.status];
        }

        return counts;
    }
};

class ActionsEngine {
private:
    map<string, StatusCheck> checks;

public:
    void startCheck(const string& name) {
        checks[name] = StatusCheck{name, CheckStatus::Pending};
    }

    void completeCheck(const string& name,
                       bool successful) {
        auto iterator = checks.find(name);

        if (iterator == checks.end()) {
            throw out_of_range("Unknown status check: " + name);
        }

        iterator->second.status =
            successful ? CheckStatus::Success
                       : CheckStatus::Failure;
    }

    bool allRequiredChecksSuccessful(
        const vector<string>& requiredChecks) const {
        for (const auto& required : requiredChecks) {
            auto iterator = checks.find(required);

            if (iterator == checks.end() ||
                iterator->second.status != CheckStatus::Success) {
                return false;
            }
        }

        return true;
    }
};

class PullRequestEngine {
private:
    int nextNumber = 1;
    map<int, PullRequest> pullRequests;

public:
    PullRequest& create(const string& source,
                        const string& target,
                        const string& title,
                        const string& author) {
        if (source.empty() || target.empty()) {
            throw invalid_argument(
                "Pull Request requires source and target branches."
            );
        }

        if (source == target) {
            throw invalid_argument(
                "Source and target branches must differ."
            );
        }

        PullRequest pullRequest{
            nextNumber,
            source,
            target,
            title,
            author
        };

        auto [iterator, inserted] =
            pullRequests.emplace(nextNumber, move(pullRequest));

        if (!inserted) {
            throw runtime_error(
                "Unable to allocate Pull Request number."
            );
        }

        ++nextNumber;
        return iterator->second;
    }

    void addCommit(PullRequest& pullRequest,
                   const string& commit,
                   const set<string>& files) {
        if (pullRequest.state != PullRequestState::Open) {
            throw logic_error(
                "Only open Pull Requests can receive commits."
            );
        }

        if (commit.size() < 7) {
            throw invalid_argument(
                "Commit identifier is too short."
            );
        }

        pullRequest.commits.push_back(commit);
        pullRequest.changedFiles.insert(files.begin(), files.end());
    }

    void markReady(PullRequest& pullRequest) {
        if (pullRequest.state != PullRequestState::Open) {
            throw logic_error(
                "Closed Pull Requests cannot become ready."
            );
        }

        pullRequest.draft = false;
    }
};

class GovernanceEngine {
private:
    Environment production;
    int requiredApprovals;
    set<string> approvedReviewers;
    bool conversationsResolved = false;
    bool branchUpToDate = true;

public:
    GovernanceEngine(
        Environment protectedEnvironment,
        int approvalsRequired
    )
        : production(move(protectedEnvironment)),
          requiredApprovals(approvalsRequired) {}

    void approve(const string& reviewer) {
        if (reviewer.empty()) {
            throw invalid_argument(
                "Reviewer identity cannot be empty."
            );
        }

        approvedReviewers.insert(reviewer);
    }

    void setConversationsResolved(bool resolved) {
        conversationsResolved = resolved;
    }

    void setBranchUpToDate(bool current) {
        branchUpToDate = current;
    }

    bool mergeEligible(
        const PullRequest& pullRequest,
        const ActionsEngine& actions,
        const vector<string>& requiredChecks
    ) const {
        if (pullRequest.state != PullRequestState::Open) {
            return false;
        }

        if (pullRequest.draft) {
            return false;
        }

        if (!branchUpToDate) {
            return false;
        }

        if (!conversationsResolved) {
            return false;
        }

        if (static_cast<int>(approvedReviewers.size()) <
            requiredApprovals) {
            return false;
        }

        if (!actions.allRequiredChecksSuccessful(requiredChecks)) {
            return false;
        }

        return true;
    }

    bool deployEligible() const {
        return static_cast<int>(approvedReviewers.size()) >=
               production.requiredApprovals;
    }
};

static string checkStatusName(CheckStatus status) {
    switch (status) {
        case CheckStatus::Pending:
            return "pending";
        case CheckStatus::Success:
            return "success";
        case CheckStatus::Failure:
            return "failure";
    }

    return "unknown";
}

static void printEnvironmentState(EnvironmentState state) {
    switch (state) {
        case EnvironmentState::Ready:
            cout << "ready";
            break;
        case EnvironmentState::WaitingForApproval:
            cout << "waiting_for_approval";
            break;
        case EnvironmentState::Deployed:
            cout << "deployed";
            break;
        case EnvironmentState::Failed:
            cout << "failed";
            break;
    }
}

int main() {
    try {
        cout << "=== Repository Governance Case Study ===\n\n";

        Repository repository(
            "example-org",
            "release-platform",
            "private"
        );

        repository.addFile("README.md");
        repository.addFile(".github/workflows/ci.yml");
        repository.createBranch("feature/deployment-audit");

        repository.printState();

        cout << "\n=== Issue and Project Planning ===\n";

        IssueManager issueManager;

        Issue& issue = issueManager.create(
            "Add deployment audit trail",
            "Record actor, commit, branch, and deployment environment.",
            "maya"
        );

        issue.labels.insert("enhancement");
        issue.labels.insert("deployment");
        issue.comments.push_back(
            "maya: Deployment credentials must never be stored in issues."
        );

        cout << "Created Issue #" << issue.number << '\n';
        cout << "Issue title: " << issue.title << '\n';
        cout << "Open issues: " << issueManager.openCount() << '\n';

        Project project("Release Platform Roadmap");

        project.addItem(
            "issue",
            to_string(issue.number),
            "In Progress",
            "High"
        );

        project.addItem(
            "repository",
            repository.fullName(),
            "Todo",
            "Medium"
        );

        project.moveItem(
            "issue",
            to_string(issue.number),
            "Done"
        );

        cout << "Project status counts:\n";
        for (const auto& [status, count] : project.statusCounts()) {
            cout << "  " << status << ": " << count << '\n';
        }

        cout << "\n=== Pull Request ===\n";

        PullRequestEngine pullRequestEngine;

        PullRequest& pullRequest = pullRequestEngine.create(
            "feature/deployment-audit",
            "main",
            "Add deployment audit trail",
            "maya"
        );

        pullRequestEngine.addCommit(
            pullRequest,
            "a81c93d4",
            {"audit.cpp", "audit_tests.cpp"}
        );

        pullRequestEngine.addCommit(
            pullRequest,
            "b42e7610",
            {"deployment_log.cpp"}
        );

        pullRequest.linkedIssues.push_back(issue.number);

        cout << "PR #" << pullRequest.number << '\n';
        cout << "Source: " << pullRequest.sourceBranch << '\n';
        cout << "Target: " << pullRequest.targetBranch << '\n';
        cout << "Draft: " << boolalpha << pullRequest.draft << '\n';
        cout << "Commits: " << pullRequest.commits.size() << '\n';
        cout << "Changed files: "
             << pullRequest.changedFiles.size() << '\n';

        pullRequestEngine.markReady(pullRequest);

        cout << "Ready for review: "
             << boolalpha << !pullRequest.draft << '\n';

        cout << "\n=== Actions Status Checks ===\n";

        ActionsEngine actions;

        actions.startCheck("build");
        actions.startCheck("unit-tests");
        actions.startCheck("security-scan");

        actions.completeCheck("build", true);
        actions.completeCheck("unit-tests", true);
        actions.completeCheck("security-scan", true);

        pullRequest.checks = {
            {"build", CheckStatus::Success},
            {"unit-tests", CheckStatus::Success},
            {"security-scan", CheckStatus::Success}
        };

        for (const auto& check : pullRequest.checks) {
            cout << check.name << ": "
                 << checkStatusName(check.status) << '\n';
        }

        cout << "\n=== Protected Production Environment ===\n";

        Environment production{
            "production",
            EnvironmentState::Ready,
            2,
            {},
            {"DEPLOY_TOKEN", "DATABASE_URL"}
        };

        /*
            The actual secret values are intentionally absent. A governance
            system needs to know that protected credentials exist without
            exposing those values to project output or source control.
        */

        GovernanceEngine governance(
            production,
            2
        );

        vector<string> requiredChecks{
            "build",
            "unit-tests",
            "security-scan"
        };

        cout << "Merge eligibility before approvals: "
             << boolalpha
             << governance.mergeEligible(
                    pullRequest,
                    actions,
                    requiredChecks
                )
             << '\n';

        governance.approve("release-manager");

        cout << "Merge eligibility after one approval: "
             << governance.mergeEligible(
                    pullRequest,
                    actions,
                    requiredChecks
                )
             << '\n';

        governance.approve("security-reviewer");
        governance.setConversationsResolved(true);

        cout << "Merge eligibility after required approvals: "
             << governance.mergeEligible(
                    pullRequest,
                    actions,
                    requiredChecks
                )
             << '\n';

        cout << "\n=== Governance Failure Simulation ===\n";

        governance.setBranchUpToDate(false);

        cout << "Eligibility with stale target-branch state: "
             << governance.mergeEligible(
                    pullRequest,
                    actions,
                    requiredChecks
                )
             << '\n';

        governance.setBranchUpToDate(true);

        actions.completeCheck("security-scan", false);

        cout << "Eligibility after failed security check: "
             << governance.mergeEligible(
                    pullRequest,
                    actions,
                    requiredChecks
                )
             << '\n';

        cout << "\n=== Deployment Audit Record ===\n";

        DeploymentRecord deployment{
            "production",
            "main",
            pullRequest.commits.back(),
            "maya",
            EnvironmentState::Deployed,
            nowUtcLike()
        };

        cout << "Environment: " << deployment.environment << '\n';
        cout << "Branch: " << deployment.branch << '\n';
        cout << "Commit: " << deployment.commit << '\n';
        cout << "Actor: " << deployment.actor << '\n';
        cout << "State: ";
        printEnvironmentState(deployment.state);
        cout << '\n';
        cout << "Timestamp: " << deployment.timestamp << '\n';

        cout << "\n=== Case Study Design ===\n";
        cout << "Repositories provide the durable source structure.\n";
        cout << "Issues capture work and discussion.\n";
        cout << "Projects organize work across tracked items.\n";
        cout << "Actions execute automated checks and delivery workflows.\n";
        cout << "Environments apply deployment-specific controls.\n";
        cout << "Governance evaluates whether those systems collectively permit delivery.\n";

        cout << "\n=== Edge-Case Validation ===\n";

        try {
            repository.createBranch("main");
        } catch (const exception& error) {
            cout << "Duplicate branch rejected: "
                 << error.what() << '\n';
        }

        try {
            pullRequestEngine.create(
                "main",
                "main",
                "Invalid PR",
                "maya"
            );
        } catch (const exception& error) {
            cout << "Invalid PR rejected: "
                 << error.what() << '\n';
        }

        return 0;
    }
    catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}

/*
 * Git Workflows Case Study
 *
 * Topic:
 *   Feature Branches, GitHub Flow, and Trunk-Based Development
 *
 * Scenario:
 *   A software organization operates an e-commerce platform containing
 *   authentication, catalog, payments, and deployment automation. The program
 *   models a workflow engine used to validate proposed changes before they are
 *   integrated into a protected production branch.
 *
 * Standard:
 *   C++17 or later
 *
 * Build example:
 *   g++ -std=c++17 -Wall -Wextra -pedantic git_workflows_case_study.cpp -o git_workflows
 *
 * The implementation intentionally uses only the C++ standard library.
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
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

// =============================================================================
// 1. GENERAL HELPERS
// =============================================================================

void section(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

void printList(const vector<string>& values) {
    for (const auto& value : values) {
        cout << "  - " << value << "\n";
    }
}

// =============================================================================
// 2. DOMAIN ENUMERATIONS
// =============================================================================

enum class WorkflowType {
    FeatureBranch,
    GitHubFlow,
    TrunkBased
};

enum class IntegrationStrategy {
    Merge,
    Rebase,
    Squash
};

enum class CheckStatus {
    Pending,
    Passed,
    Failed
};

string toString(WorkflowType workflow) {
    switch (workflow) {
        case WorkflowType::FeatureBranch:
            return "Feature Branch Workflow";
        case WorkflowType::GitHubFlow:
            return "GitHub Flow";
        case WorkflowType::TrunkBased:
            return "Trunk-Based Development";
    }

    return "Unknown";
}

string toString(IntegrationStrategy strategy) {
    switch (strategy) {
        case IntegrationStrategy::Merge:
            return "Merge";
        case IntegrationStrategy::Rebase:
            return "Rebase";
        case IntegrationStrategy::Squash:
            return "Squash";
    }

    return "Unknown";
}

string toString(CheckStatus status) {
    switch (status) {
        case CheckStatus::Pending:
            return "Pending";
        case CheckStatus::Passed:
            return "Passed";
        case CheckStatus::Failed:
            return "Failed";
    }

    return "Unknown";
}

// =============================================================================
// 3. COMMIT MODEL
// =============================================================================

class Commit {
private:
    string id_;
    string message_;
    string author_;
    vector<string> parents_;
    vector<string> changedFiles_;

public:
    Commit(
        string id,
        string message,
        string author,
        vector<string> parents,
        vector<string> changedFiles
    )
        : id_(move(id)),
          message_(move(message)),
          author_(move(author)),
          parents_(move(parents)),
          changedFiles_(move(changedFiles)) {}

    const string& id() const {
        return id_;
    }

    const string& message() const {
        return message_;
    }

    const string& author() const {
        return author_;
    }

    const vector<string>& parents() const {
        return parents_;
    }

    const vector<string>& changedFiles() const {
        return changedFiles_;
    }

    string shortId() const {
        return id_.substr(0, min<size_t>(10, id_.size()));
    }
};

// =============================================================================
// 4. BRANCH MODEL
// =============================================================================

class Branch {
private:
    string name_;
    string head_;
    bool protected_;

public:
    Branch(
        string name,
        string head,
        bool protectedBranch
    )
        : name_(move(name)),
          head_(move(head)),
          protected_(protectedBranch) {}

    const string& name() const {
        return name_;
    }

    const string& head() const {
        return head_;
    }

    void setHead(string newHead) {
        head_ = move(newHead);
    }

    bool isProtected() const {
        return protected_;
    }

    string describe() const {
        return name_ + " -> " +
               head_.substr(0, min<size_t>(10, head_.size())) +
               (protected_ ? " [protected]" : " [unprotected]");
    }
};

// =============================================================================
// 5. REPOSITORY GRAPH
// =============================================================================

class RepositoryGraph {
private:
    map<string, Commit> commits_;
    map<string, Branch> branches_;
    int sequence_ = 0;

    string generateCommitId() {
        ++sequence_;

        ostringstream stream;
        stream << "commit-"
               << setw(4)
               << setfill('0')
               << sequence_
               << "-abcdef";

        return stream.str();
    }

public:
    RepositoryGraph() = default;

    void initialize() {
        if (!branches_.empty()) {
            return;
        }

        branches_.emplace(
            "main",
            Branch("main", "", true)
        );

        commit(
            "main",
            "Initial repository structure",
            "System",
            {"README.md"}
        );
    }

    Commit& commit(
        const string& branchName,
        const string& message,
        const string& author,
        const vector<string>& changedFiles
    ) {
        auto branchIterator = branches_.find(branchName);

        if (branchIterator == branches_.end()) {
            throw runtime_error(
                "Cannot create commit: branch does not exist: " + branchName
            );
        }

        if (message.empty()) {
            throw invalid_argument("Commit message cannot be empty.");
        }

        string id = generateCommitId();

        vector<string> parents;

        if (!branchIterator->second.head().empty()) {
            parents.push_back(branchIterator->second.head());
        }

        auto [iterator, inserted] = commits_.emplace(
            id,
            Commit(
                id,
                message,
                author,
                parents,
                changedFiles
            )
        );

        if (!inserted) {
            throw runtime_error("Generated duplicate commit ID.");
        }

        branchIterator->second.setHead(id);

        return iterator->second;
    }

    void createBranch(
        const string& branchName,
        const string& fromBranch
    ) {
        if (branchName.empty()) {
            throw invalid_argument("Branch name cannot be empty.");
        }

        if (branches_.contains(branchName)) {
            throw invalid_argument(
                "Branch already exists: " + branchName
            );
        }

        auto source = branches_.find(fromBranch);

        if (source == branches_.end()) {
            throw invalid_argument(
                "Source branch does not exist: " + fromBranch
            );
        }

        branches_.emplace(
            branchName,
            Branch(
                branchName,
                source->second.head(),
                false
            )
        );
    }

    const Branch& branch(const string& name) const {
        auto iterator = branches_.find(name);

        if (iterator == branches_.end()) {
            throw out_of_range("Unknown branch: " + name);
        }

        return iterator->second;
    }

    Branch& mutableBranch(const string& name) {
        auto iterator = branches_.find(name);

        if (iterator == branches_.end()) {
            throw out_of_range("Unknown branch: " + name);
        }

        return iterator->second;
    }

    const Commit& getCommit(const string& id) const {
        auto iterator = commits_.find(id);

        if (iterator == commits_.end()) {
            throw out_of_range("Unknown commit: " + id);
        }

        return iterator->second;
    }

    unordered_set<string> ancestors(const string& commitId) const {
        getCommit(commitId);

        unordered_set<string> result;
        vector<string> stack{commitId};

        while (!stack.empty()) {
            string current = stack.back();
            stack.pop_back();

            if (!result.insert(current).second) {
                continue;
            }

            const Commit& currentCommit = getCommit(current);

            for (const auto& parent : currentCommit.parents()) {
                stack.push_back(parent);
            }
        }

        return result;
    }

    optional<string> commonAncestor(
        const string& first,
        const string& second
    ) const {
        const auto firstAncestors = ancestors(first);
        const auto secondAncestors = ancestors(second);

        for (const auto& candidate : firstAncestors) {
            if (secondAncestors.contains(candidate)) {
                return candidate;
            }
        }

        return nullopt;
    }

    void printGraph() const {
        cout << "\nCommits:\n";

        for (const auto& [id, commitObject] : commits_) {
            cout << "  "
                 << commitObject.shortId()
                 << " | "
                 << commitObject.message()
                 << " | author="
                 << commitObject.author()
                 << " | parents=";

            if (commitObject.parents().empty()) {
                cout << "none";
            } else {
                for (size_t index = 0;
                     index < commitObject.parents().size();
                     ++index) {
                    if (index > 0) {
                        cout << ",";
                    }

                    cout << commitObject.parents()[index].substr(
                        0,
                        min<size_t>(10, commitObject.parents()[index].size())
                    );
                }
            }

            cout << "\n";
        }

        cout << "\nBranches:\n";

        for (const auto& [name, branchObject] : branches_) {
            cout << "  " << branchObject.describe() << "\n";
        }
    }
};

// =============================================================================
// 6. BRANCH VALIDATION
// =============================================================================

class BranchNameValidator {
private:
    static bool validPrefix(const string& prefix) {
        static const set<string> prefixes{
            "feature",
            "bugfix",
            "hotfix",
            "chore",
            "docs",
            "refactor",
            "test"
        };

        return prefixes.contains(prefix);
    }

public:
    static pair<bool, string> validate(const string& branchName) {
        if (branchName.empty()) {
            return {false, "Branch name cannot be empty."};
        }

        if (
            branchName == "main" ||
            branchName == "master" ||
            branchName == "develop"
        ) {
            return {true, "Shared branch."};
        }

        const auto slash = branchName.find('/');

        if (slash == string::npos) {
            return {
                false,
                "Use a category prefix such as feature/login."
            };
        }

        const string prefix = branchName.substr(0, slash);
        const string name = branchName.substr(slash + 1);

        if (!validPrefix(prefix)) {
            return {
                false,
                "Unknown branch prefix: " + prefix
            };
        }

        if (name.empty()) {
            return {
                false,
                "Branch description cannot be empty."
            };
        }

        if (name.front() == '-' || name.back() == '-') {
            return {
                false,
                "Avoid leading or trailing hyphens."
            };
        }

        for (const char character : name) {
            if (isspace(static_cast<unsigned char>(character))) {
                return {
                    false,
                    "Spaces are discouraged in branch names."
                };
            }
        }

        return {true, "Valid workflow branch name."};
    }
};

// =============================================================================
// 7. PULL REQUEST MODEL
// =============================================================================

class PullRequest {
private:
    int number_;
    string sourceBranch_;
    string targetBranch_;
    string title_;
    int approvals_ = 0;
    CheckStatus checks_ = CheckStatus::Pending;
    bool merged_ = false;
    vector<string> comments_;

public:
    PullRequest(
        int number,
        string sourceBranch,
        string targetBranch,
        string title
    )
        : number_(number),
          sourceBranch_(move(sourceBranch)),
          targetBranch_(move(targetBranch)),
          title_(move(title)) {}

    void approve() {
        ++approvals_;
    }

    void setChecks(CheckStatus status) {
        checks_ = status;
    }

    void addComment(string comment) {
        if (!comment.empty()) {
            comments_.push_back(move(comment));
        }
    }

    bool mergeable(int requiredApprovals) const {
        return (
            !merged_ &&
            checks_ == CheckStatus::Passed &&
            approvals_ >= requiredApprovals
        );
    }

    void merge(int requiredApprovals) {
        if (!mergeable(requiredApprovals)) {
            throw runtime_error(
                "Pull request does not satisfy merge requirements."
            );
        }

        merged_ = true;
    }

    string describe() const {
        ostringstream stream;

        stream << "PR #"
               << number_
               << ": "
               << title_
               << " ["
               << sourceBranch_
               << " -> "
               << targetBranch_
               << "]";

        return stream.str();
    }

    int approvals() const {
        return approvals_;
    }

    CheckStatus checks() const {
        return checks_;
    }

    bool merged() const {
        return merged_;
    }
};

// =============================================================================
// 8. QUALITY GATES
// =============================================================================

class QualityGate {
private:
    bool testsPassed_;
    bool lintPassed_;
    bool securityPassed_;
    int requiredApprovals_;
    int actualApprovals_;

public:
    QualityGate(
        bool testsPassed,
        bool lintPassed,
        bool securityPassed,
        int requiredApprovals,
        int actualApprovals
    )
        : testsPassed_(testsPassed),
          lintPassed_(lintPassed),
          securityPassed_(securityPassed),
          requiredApprovals_(requiredApprovals),
          actualApprovals_(actualApprovals) {
        if (requiredApprovals_ < 0 || actualApprovals_ < 0) {
            throw invalid_argument(
                "Approval counts cannot be negative."
            );
        }
    }

    bool passes() const {
        return (
            testsPassed_ &&
            lintPassed_ &&
            securityPassed_ &&
            actualApprovals_ >= requiredApprovals_
        );
    }

    void setTestsPassed(bool value) {
        testsPassed_ = value;
    }

    void setLintPassed(bool value) {
        lintPassed_ = value;
    }

    void setSecurityPassed(bool value) {
        securityPassed_ = value;
    }

    void setActualApprovals(int value) {
        if (value < 0) {
            throw invalid_argument(
                "Approval count cannot be negative."
            );
        }

        actualApprovals_ = value;
    }
};

// =============================================================================
// 9. FEATURE FLAGS
// =============================================================================

class FeatureFlagService {
private:
    unordered_map<string, bool> flags_;

public:
    bool enabled(
        const string& flagName,
        bool defaultValue = false
    ) const {
        const auto iterator = flags_.find(flagName);

        if (iterator == flags_.end()) {
            return defaultValue;
        }

        return iterator->second;
    }

    void set(
        const string& flagName,
        bool enabledValue
    ) {
        if (flagName.empty()) {
            throw invalid_argument(
                "Feature flag name cannot be empty."
            );
        }

        flags_[flagName] = enabledValue;
    }
};

// =============================================================================
// 10. WORKFLOW ENGINE
// =============================================================================

class WorkflowEngine {
private:
    RepositoryGraph repository_;
    vector<PullRequest> pullRequests_;
    int requiredApprovals_ = 1;

public:
    WorkflowEngine() {
        repository_.initialize();
    }

    RepositoryGraph& repository() {
        return repository_;
    }

    const RepositoryGraph& repository() const {
        return repository_;
    }

    PullRequest& createPullRequest(
        const string& source,
        const string& target,
        const string& title
    ) {
        if (source == target) {
            throw invalid_argument(
                "Source and target branches must differ."
            );
        }

        // Accessing the branches validates their existence.
        repository_.branch(source);
        repository_.branch(target);

        const int number =
            static_cast<int>(pullRequests_.size()) + 1;

        pullRequests_.emplace_back(
            number,
            source,
            target,
            title
        );

        return pullRequests_.back();
    }

    void setRequiredApprovals(int required) {
        if (required < 0) {
            throw invalid_argument(
                "Required approvals cannot be negative."
            );
        }

        requiredApprovals_ = required;
    }

    bool canMerge(const PullRequest& pullRequest) const {
        return pullRequest.mergeable(requiredApprovals_);
    }

    void merge(PullRequest& pullRequest) {
        if (!canMerge(pullRequest)) {
            throw runtime_error(
                "Quality gates have not been satisfied."
            );
        }

        pullRequest.merge(requiredApprovals_);
    }
};

// =============================================================================
// 11. CHANGE-IMPACT ANALYSIS
// =============================================================================

set<string> affectedServices(
    const vector<string>& changedFiles
) {
    set<string> services;

    for (const auto& path : changedFiles) {
        const string prefix = "services/";

        if (path.rfind(prefix, 0) != 0) {
            continue;
        }

        const size_t start = prefix.size();
        const size_t separator = path.find('/', start);

        if (separator == string::npos) {
            continue;
        }

        services.insert(
            path.substr(start, separator - start)
        );
    }

    return services;
}

// =============================================================================
// 12. RELEASE MODEL
// =============================================================================

class Release {
private:
    string version_;
    string commitId_;

public:
    Release(string version, string commitId)
        : version_(move(version)),
          commitId_(move(commitId)) {
        if (version_.empty()) {
            throw invalid_argument(
                "Release version cannot be empty."
            );
        }

        if (commitId_.empty()) {
            throw invalid_argument(
                "Release commit cannot be empty."
            );
        }
    }

    string tag() const {
        return "v" + version_;
    }

    const string& commitId() const {
        return commitId_;
    }
};

class Hotfix {
private:
    string issue_;
    string sourceCommit_;
    bool closed_ = false;

public:
    Hotfix(string issue, string sourceCommit)
        : issue_(move(issue)),
          sourceCommit_(move(sourceCommit)) {}

    void close() {
        closed_ = true;
    }

    bool closed() const {
        return closed_;
    }

    const string& issue() const {
        return issue_;
    }
};

// =============================================================================
// 13. DATABASE MIGRATION MODEL
// =============================================================================

enum class MigrationStage {
    Expand,
    CompatibleApplication,
    DataMigration,
    SwitchBehavior,
    Contract
};

string toString(MigrationStage stage) {
    switch (stage) {
        case MigrationStage::Expand:
            return "Expand schema";
        case MigrationStage::CompatibleApplication:
            return "Deploy backward-compatible application";
        case MigrationStage::DataMigration:
            return "Migrate data";
        case MigrationStage::SwitchBehavior:
            return "Switch application behavior";
        case MigrationStage::Contract:
            return "Remove obsolete schema";
    }

    return "Unknown";
}

// =============================================================================
// 14. DELIVERY METRICS
// =============================================================================

class DeliveryMetrics {
private:
    double deploymentFrequency_;
    double leadTimeHours_;
    double changeFailureRate_;
    double recoveryTimeHours_;

public:
    DeliveryMetrics(
        double deploymentFrequency,
        double leadTimeHours,
        double changeFailureRate,
        double recoveryTimeHours
    )
        : deploymentFrequency_(deploymentFrequency),
          leadTimeHours_(leadTimeHours),
          changeFailureRate_(changeFailureRate),
          recoveryTimeHours_(recoveryTimeHours) {
        validate();
    }

    void validate() const {
        if (deploymentFrequency_ < 0) {
            throw invalid_argument(
                "Deployment frequency cannot be negative."
            );
        }

        if (leadTimeHours_ < 0) {
            throw invalid_argument(
                "Lead time cannot be negative."
            );
        }

        if (
            changeFailureRate_ < 0 ||
            changeFailureRate_ > 1
        ) {
            throw invalid_argument(
                "Change failure rate must be between 0 and 1."
            );
        }

        if (recoveryTimeHours_ < 0) {
            throw invalid_argument(
                "Recovery time cannot be negative."
            );
        }
    }

    void print() const {
        cout << "Deployment frequency: "
             << deploymentFrequency_
             << "\n";

        cout << "Lead time (hours): "
             << leadTimeHours_
             << "\n";

        cout << "Change failure rate: "
             << changeFailureRate_
             << "\n";

        cout << "Recovery time (hours): "
             << recoveryTimeHours_
             << "\n";
    }
};

// =============================================================================
// 15. TEST UTILITIES
// =============================================================================

void expect(
    bool condition,
    const string& testName
) {
    if (!condition) {
        throw runtime_error(
            "Test failed: " + testName
        );
    }

    cout << "PASS: " << testName << "\n";
}

// =============================================================================
// 16. CASE STUDY
// =============================================================================

void runCaseStudy() {
    section("1. Industry-Style Git Workflow Case Study");

    cout
        << "Scenario: e-commerce platform\n"
        << "Primary branch: main\n"
        << "Integration policy: pull request + automated validation\n"
        << "Deployment model: automated after approved integration\n";

    WorkflowEngine engine;

    auto& repository = engine.repository();

    repository.commit(
        "main",
        "Create commerce application skeleton",
        "Platform Team",
        {
            "services/catalog/catalog.cpp",
            "services/payments/payment.cpp"
        }
    );

    // -------------------------------------------------------------------------
    // Feature branch creation
    // -------------------------------------------------------------------------

    section("2. Feature Branch Development");

    const auto validation =
        BranchNameValidator::validate(
            "feature/payment-validation"
        );

    cout << "Branch validation: "
         << validation.second
         << "\n";

    if (!validation.first) {
        throw runtime_error(
            "Cannot continue with invalid feature branch."
        );
    }

    repository.createBranch(
        "feature/payment-validation",
        "main"
    );

    repository.commit(
        "feature/payment-validation",
        "Add payment input validation",
        "Payments Team",
        {
            "services/payments/payment.cpp",
            "services/payments/payment_test.cpp"
        }
    );

    repository.commit(
        "feature/payment-validation",
        "Add payment validation tests",
        "Payments Team",
        {
            "services/payments/payment_test.cpp"
        }
    );

    cout << "\nFeature branch head:\n"
         << repository.branch(
                "feature/payment-validation"
            ).describe()
         << "\n";

    // -------------------------------------------------------------------------
    // Pull request
    // -------------------------------------------------------------------------

    section("3. Pull Request");

    auto& pullRequest = engine.createPullRequest(
        "feature/payment-validation",
        "main",
        "Validate payment requests"
    );

    cout << pullRequest.describe() << "\n";

    QualityGate gate(
        true,   // tests
        true,   // lint
        true,   // security
        2,      // required approvals
        1       // current approvals
    );

    cout << "Quality gate before second approval: "
         << (gate.passes() ? "PASS" : "BLOCK")
         << "\n";

    gate.setActualApprovals(2);

    cout << "Quality gate after second approval: "
         << (gate.passes() ? "PASS" : "BLOCK")
         << "\n";

    pullRequest.setChecks(CheckStatus::Passed);
    pullRequest.approve();
    pullRequest.approve();

    engine.setRequiredApprovals(2);

    cout << "Pull request mergeable: "
         << (engine.canMerge(pullRequest) ? "YES" : "NO")
         << "\n";

    engine.merge(pullRequest);

    cout << "Pull request merged: "
         << (pullRequest.merged() ? "YES" : "NO")
         << "\n";

    // -------------------------------------------------------------------------
    // Feature flags
    // -------------------------------------------------------------------------

    section("4. Feature Flag");

    FeatureFlagService flags;

    flags.set("enhanced-payment-validation", false);

    cout << "Enhanced validation exposed: "
         << (flags.enabled("enhanced-payment-validation")
                 ? "YES"
                 : "NO")
         << "\n";

    flags.set("enhanced-payment-validation", true);

    cout << "Enhanced validation exposed after activation: "
         << (flags.enabled("enhanced-payment-validation")
                 ? "YES"
                 : "NO")
         << "\n";

    // -------------------------------------------------------------------------
    // Main branch development
    // -------------------------------------------------------------------------

    section("5. Trunk-Oriented Small Change");

    repository.commit(
        "main",
        "Improve catalog response validation",
        "Catalog Team",
        {
            "services/catalog/catalog.cpp",
            "services/catalog/catalog_test.cpp"
        }
    );

    cout << repository.branch("main").describe() << "\n";

    // -------------------------------------------------------------------------
    // Graph inspection
    // -------------------------------------------------------------------------

    section("6. Repository Graph");

    repository.printGraph();

    const string mainHead =
        repository.branch("main").head();

    const string featureHead =
        repository.branch(
            "feature/payment-validation"
        ).head();

    const auto ancestor =
        repository.commonAncestor(
            mainHead,
            featureHead
        );

    cout << "\nCommon ancestor of main and feature: ";

    if (ancestor.has_value()) {
        cout << ancestor->substr(
            0,
            min<size_t>(10, ancestor->size())
        );
    } else {
        cout << "none";
    }

    cout << "\n";

    // -------------------------------------------------------------------------
    // Monorepo impact analysis
    // -------------------------------------------------------------------------

    section("7. Monorepo Change Impact");

    const vector<string> changedFiles{
        "services/payments/payment.cpp",
        "services/payments/payment_test.cpp",
        "services/catalog/catalog.cpp",
        "docs/payment-api.md"
    };

    const auto services =
        affectedServices(changedFiles);

    cout << "Affected services:\n";

    for (const auto& service : services) {
        cout << "  " << service << "\n";
    }

    // -------------------------------------------------------------------------
    // Release
    // -------------------------------------------------------------------------

    section("8. Release");

    Release release(
        "2.4.0",
        mainHead
    );

    cout << "Release tag: "
         << release.tag()
         << "\n";

    cout << "Release commit: "
         << release.commitId()
         << "\n";

    // -------------------------------------------------------------------------
    // Hotfix
    // -------------------------------------------------------------------------

    section("9. Production Hotfix");

    Hotfix hotfix(
        "Payment timeout in production",
        release.commitId()
    );

    cout << "Hotfix issue: "
         << hotfix.issue()
         << "\n";

    cout << "Hotfix status: "
         << (hotfix.closed() ? "closed" : "open")
         << "\n";

    hotfix.close();

    cout << "Hotfix status after validation: "
         << (hotfix.closed() ? "closed" : "open")
         << "\n";

    // -------------------------------------------------------------------------
    // Database migration
    // -------------------------------------------------------------------------

    section("10. Database Migration Sequence");

    const vector<MigrationStage> migration{
        MigrationStage::Expand,
        MigrationStage::CompatibleApplication,
        MigrationStage::DataMigration,
        MigrationStage::SwitchBehavior,
        MigrationStage::Contract
    };

    for (size_t index = 0; index < migration.size(); ++index) {
        cout << index + 1
             << ". "
             << toString(migration[index])
             << "\n";
    }

    // -------------------------------------------------------------------------
    // Operational metrics
    // -------------------------------------------------------------------------

    section("11. Delivery Metrics");

    DeliveryMetrics metrics(
        12.0,
        8.0,
        0.05,
        2.0
    );

    metrics.print();
}

// =============================================================================
// 17. EDUCATIONAL DEMONSTRATIONS
// =============================================================================

void explainWorkflowConcepts() {
    section("12. Workflow Concepts");

    cout
        << "Feature branches:\n"
        << "  Isolate logical changes and commonly provide a review boundary.\n\n"

        << "GitHub Flow:\n"
        << "  Uses a main-centered model with short-lived branches and pull\n"
        << "  requests as the central collaboration mechanism.\n\n"

        << "Trunk-based development:\n"
        << "  Emphasizes frequent integration into the shared trunk.\n\n"

        << "Merge:\n"
        << "  Combines histories without requiring existing commits to be\n"
        << "  rewritten.\n\n"

        << "Rebase:\n"
        << "  Replays commits onto another base and creates new commit identities.\n\n"

        << "Squash:\n"
        << "  Combines multiple logical commits into a smaller integration history.\n\n"

        << "Feature flags:\n"
        << "  Separate deployment of code from activation of behavior.\n";
}

void explainSecurity() {
    section("13. Security Considerations");

    printList({
        "Do not commit passwords, API keys, private keys, or access tokens.",
        "Protect the primary branch from unauthorized direct pushes.",
        "Review CI workflow changes because they can control privileged actions.",
        "Avoid exposing secrets to untrusted pull-request execution.",
        "Rotate exposed credentials rather than relying only on history cleanup.",
        "Restrict repository administration and bypass permissions.",
        "Validate dependencies and generated artifacts.",
        "Audit production deployment permissions."
    });

    cout
        << "\nA secret committed to Git may remain in historical objects even after\n"
        << "the latest file version is changed. Credential rotation is therefore\n"
        << "an important part of incident response.\n";
}

void explainPerformance() {
    section("14. Performance Considerations");

    cout
        << "Workflow performance is not only Git command speed.\n\n"
        << "Useful measurements include:\n"
        << "  - CI feedback time\n"
        << "  - Pull-request review time\n"
        << "  - Branch lifetime\n"
        << "  - Build duration\n"
        << "  - Test duration\n"
        << "  - Deployment duration\n"
        << "  - Recovery time\n\n"
        << "Large repositories can also be affected by binary assets, generated\n"
        << "files, long histories, and inefficient CI pipelines.\n";
}

void explainRebaseSafety() {
    section("15. Rebase Safety");

    cout
        << "Before rebase:\n"
        << "    A -- B -- C       main\n"
        << "          \\\n"
        << "           D -- E     feature\n\n"

        << "After rebasing feature onto C:\n"
        << "    A -- B -- C -- D' -- E'\n\n"

        << "D' and E' are new commits. They are not the original D and E.\n\n"

        << "When a deliberate rebase requires updating a remote branch, a safer\n"
        << "force-update form is often:\n\n"
        << "    git push --force-with-lease\n\n"

        << "History rewriting should be coordinated when other developers depend\n"
        << "on the affected branch.\n";
}

// =============================================================================
// 18. TESTS
// =============================================================================

void runTests() {
    section("16. Automated Tests");

    {
        const auto [valid, message] =
            BranchNameValidator::validate(
                "feature/login"
            );

        (void)message;

        expect(
            valid,
            "valid feature branch name"
        );
    }

    {
        const auto [valid, message] =
            BranchNameValidator::validate(
                "feature/"
            );

        (void)message;

        expect(
            !valid,
            "invalid empty feature name"
        );
    }

    {
        PullRequest pullRequest(
            1,
            "feature/a",
            "main",
            "Test PR"
        );

        pullRequest.setChecks(CheckStatus::Passed);

        expect(
            !pullRequest.mergeable(1),
            "approval is required"
        );

        pullRequest.approve();

        expect(
            pullRequest.mergeable(1),
            "PR becomes mergeable after approval"
        );
    }

    {
        FeatureFlagService flags;

        expect(
            !flags.enabled("missing"),
            "missing feature flag defaults to false"
        );

        flags.set("search", true);

        expect(
            flags.enabled("search"),
            "enabled feature flag returns true"
        );
    }

    {
        QualityGate gate(
            true,
            true,
            true,
            2,
            1
        );

        expect(
            !gate.passes(),
            "quality gate blocks with insufficient approvals"
        );

        gate.setActualApprovals(2);

        expect(
            gate.passes(),
            "quality gate passes after required approvals"
        );
    }

    {
        const auto services = affectedServices({
            "services/payments/payment.cpp",
            "services/catalog/catalog.cpp",
            "README.md"
        });

        expect(
            services.contains("payments"),
            "payments service detected"
        );

        expect(
            services.contains("catalog"),
            "catalog service detected"
        );

        expect(
            !services.contains("README.md"),
            "documentation is not treated as a service"
        );
    }
}

// =============================================================================
// 19. MAIN
// =============================================================================

int main() {
    try {
        cout
            << "Git Workflows Case Study\n"
            << "Feature Branches | GitHub Flow | Trunk-Based Development\n";

        explainWorkflowConcepts();
        runCaseStudy();
        explainSecurity();
        explainPerformance();
        explainRebaseSafety();
        runTests();

        section("17. Command Reference");

        printList({
            "git status",
            "git switch main",
            "git pull --ff-only origin main",
            "git switch -c feature/my-change",
            "git add <files>",
            "git commit -m \"Describe the change\"",
            "git fetch origin",
            "git rebase origin/main",
            "git push -u origin feature/my-change",
            "git log --oneline --decorate --graph --all",
            "git reflog",
            "git merge <branch>",
            "git branch --delete feature/my-change"
        });

        section("18. Architectural Observations");

        cout
            << "1. Branch strategy controls how code diverges.\n"
            << "2. CI controls automated validation.\n"
            << "3. Review controls collaborative inspection.\n"
            << "4. Branch protection controls integration permissions.\n"
            << "5. Feature flags control runtime exposure.\n"
            << "6. Deployment automation controls delivery speed.\n"
            << "7. Monitoring controls operational feedback.\n"
            << "8. Rollback or roll-forward controls recovery.\n"
            << "9. Security controls protect credentials and privileged actions.\n"
            << "10. Database migration strategy must account for persistent state.\n";

        section("19. Case Study Complete");

        cout
            << "The simulated repository demonstrates feature-branch isolation,\n"
            << "pull-request quality gates, trunk-oriented integration, feature\n"
            << "flags, monorepo impact analysis, releases, hotfixes, database\n"
            << "migration sequencing, security controls, and delivery metrics.\n";

        return 0;
    }
    catch (const exception& error) {
        cerr
            << "\nFatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}

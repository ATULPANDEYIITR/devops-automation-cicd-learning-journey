#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace std;

enum class TestKind { Unit, Integration, Smoke, Regression };
enum class CheckState { Pending, Passed, Failed, Skipped };
enum class ReviewGate { NotRequired, Required, Satisfied, Rejected };
enum class PullRequestState { Draft, Open, Merged, Closed };

string to_string(TestKind kind) {
    switch (kind) {
        case TestKind::Unit: return "unit";
        case TestKind::Integration: return "integration";
        case TestKind::Smoke: return "smoke";
        case TestKind::Regression: return "regression";
    }
    return "unknown";
}

string to_string(CheckState state) {
    switch (state) {
        case CheckState::Pending: return "pending";
        case CheckState::Passed: return "passed";
        case CheckState::Failed: return "failed";
        case CheckState::Skipped: return "skipped";
    }
    return "unknown";
}

struct StatusCheck {
    string name;
    CheckState state{CheckState::Pending};
    bool required{true};
};

struct TestEvidence {
    TestKind kind;
    string suite;
    CheckState state;
    size_t executed;
    size_t failed;
};

struct BranchProtection {
    string branch;
    int requiredApprovals{2};
    bool requireUnitTests{true};
    bool requireIntegrationTests{true};
    bool requireSmokeTests{true};
    bool requireRegressionTests{true};
    bool requireResolvedConversations{true};
    bool requireLinearHistory{true};
    bool allowForcePush{false};
    bool allowDeletion{false};
    bool allowDirectPush{false};
    bool allowAdministratorBypass{false};
};

struct PullRequest {
    int number{};
    string title;
    string sourceBranch;
    string targetBranch;
    PullRequestState state{PullRequestState::Open};
    bool draft{false};
    bool sourceSynchronized{true};
    bool hasMergeConflicts{false};
    bool conversationsResolved{true};
    bool linearHistory{true};
    int commits{1};
    int approvals{0};
    int changesRequested{0};
    vector<StatusCheck> checks;
    vector<TestEvidence> evidence;
};

struct GateResult {
    bool eligible{true};
    vector<string> blockers;

    void reject(const string& reason) {
        eligible = false;
        blockers.push_back(reason);
    }
};

class GovernanceEngine {
public:
    explicit GovernanceEngine(BranchProtection policy) : policy_(move(policy)) {
        if (policy_.branch.empty()) {
            throw invalid_argument("Protected branch name cannot be empty.");
        }
        if (policy_.requiredApprovals < 0) {
            throw invalid_argument("Approval requirement cannot be negative.");
        }
    }

    GateResult evaluate(const PullRequest& pr) const {
        GateResult result;

        if (pr.number <= 0) result.reject("Pull request number is invalid.");
        if (pr.title.empty()) result.reject("Pull request title is empty.");
        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            result.reject("Source and target branches are required.");
        }
        if (pr.sourceBranch == pr.targetBranch) {
            result.reject("Source and target branches must differ.");
        }
        if (pr.targetBranch != policy_.branch) {
            result.reject("This policy applies to a different target branch.");
        }
        if (pr.state != PullRequestState::Open) {
            result.reject("Pull request is not open.");
        }
        if (pr.draft) result.reject("Draft pull requests cannot be merged.");
        if (!pr.sourceSynchronized) {
            result.reject("Source branch must be synchronized with the base branch.");
        }
        if (pr.hasMergeConflicts) {
            result.reject("Merge conflicts must be resolved.");
        }
        if (pr.commits <= 0) result.reject("At least one commit is required.");
        if (pr.changesRequested > 0) {
            result.reject("Outstanding change requests block merging.");
        }
        if (pr.approvals < policy_.requiredApprovals) {
            result.reject("Required approval count has not been reached.");
        }
        if (policy_.requireResolvedConversations && !pr.conversationsResolved) {
            result.reject("Review conversations remain unresolved.");
        }
        if (policy_.requireLinearHistory && !pr.linearHistory) {
            result.reject("The resulting history must be linear.");
        }

        const map<TestKind, bool> requiredEvidence{
            {TestKind::Unit, policy_.requireUnitTests},
            {TestKind::Integration, policy_.requireIntegrationTests},
            {TestKind::Smoke, policy_.requireSmokeTests},
            {TestKind::Regression, policy_.requireRegressionTests},
        };

        for (const auto& [kind, required] : requiredEvidence) {
            if (!required) continue;

            const auto evidence = find_if(
                pr.evidence.begin(), pr.evidence.end(),
                [kind](const TestEvidence& item) {
                    return item.kind == kind;
                }
            );

            if (evidence == pr.evidence.end()) {
                result.reject("Missing " + to_string(kind) + " test evidence.");
            } else if (evidence->state != CheckState::Passed ||
                       evidence->failed != 0) {
                result.reject(to_string(kind) + " test evidence is not successful.");
            }
        }

        for (const auto& check : pr.checks) {
            if (check.required && check.state != CheckState::Passed) {
                result.reject(
                    "Required status check '" + check.name + "' is " +
                    to_string(check.state) + "."
                );
            }
        }

        return result;
    }

    const BranchProtection& policy() const { return policy_; }

private:
    BranchProtection policy_;
};

TestEvidence makeEvidence(TestKind kind, const string& suite, size_t executed,
                          size_t failed = 0) {
    return {
        kind,
        suite,
        failed == 0 ? CheckState::Passed : CheckState::Failed,
        executed,
        failed
    };
}

PullRequest healthyPullRequest() {
    PullRequest pr;
    pr.number = 482;
    pr.title = "Prevent duplicate order submission";
    pr.sourceBranch = "fix/idempotent-order-submit";
    pr.targetBranch = "main";
    pr.state = PullRequestState::Open;
    pr.draft = false;
    pr.sourceSynchronized = true;
    pr.hasMergeConflicts = false;
    pr.conversationsResolved = true;
    pr.linearHistory = true;
    pr.commits = 3;
    pr.approvals = 2;
    pr.changesRequested = 0;
    pr.checks = {
        {"build-linux", CheckState::Passed, true},
        {"static-analysis", CheckState::Passed, true},
        {"dependency-audit", CheckState::Passed, true},
        {"preview-environment", CheckState::Skipped, false}
    };
    pr.evidence = {
        makeEvidence(TestKind::Unit, "order-domain", 84),
        makeEvidence(TestKind::Integration, "postgres-order-api", 21),
        makeEvidence(TestKind::Smoke, "staging-health", 4),
        makeEvidence(TestKind::Regression, "order-regression", 37)
    };
    return pr;
}

void printEvaluation(const PullRequest& pr, const GateResult& result) {
    cout << "\nPull Request #" << pr.number << ": " << pr.title << '\n';
    cout << "Source: " << pr.sourceBranch
         << " -> Target: " << pr.targetBranch << '\n';
    cout << "Merge eligibility: " << (result.eligible ? "ELIGIBLE" : "BLOCKED")
         << '\n';

    for (const auto& blocker : result.blockers) {
        cout << "  Blocker: " << blocker << '\n';
    }
}

int main() {
    try {
        BranchProtection mainPolicy;
        mainPolicy.branch = "main";
        mainPolicy.requiredApprovals = 2;
        mainPolicy.requireUnitTests = true;
        mainPolicy.requireIntegrationTests = true;
        mainPolicy.requireSmokeTests = true;
        mainPolicy.requireRegressionTests = true;
        mainPolicy.requireResolvedConversations = true;
        mainPolicy.requireLinearHistory = true;
        mainPolicy.allowForcePush = false;
        mainPolicy.allowDeletion = false;
        mainPolicy.allowDirectPush = false;
        mainPolicy.allowAdministratorBypass = false;

        GovernanceEngine engine(mainPolicy);

        cout << "Repository Governance and Testing Gate\n";
        cout << "Protected branch: " << engine.policy().branch << '\n';
        cout << "Required independent approvals: "
             << engine.policy().requiredApprovals << '\n';

        PullRequest accepted = healthyPullRequest();
        GateResult acceptedResult = engine.evaluate(accepted);
        printEvaluation(accepted, acceptedResult);

        // A failed integration suite blocks merging even when all reviewers
        // have approved. Approval and test evidence are separate gate inputs.
        PullRequest failedIntegration = healthyPullRequest();
        failedIntegration.number = 483;
        failedIntegration.evidence[1] =
            makeEvidence(TestKind::Integration, "postgres-order-api", 21, 2);
        printEvaluation(failedIntegration, engine.evaluate(failedIntegration));

        // A successful build does not compensate for unresolved review concerns.
        PullRequest unresolvedReview = healthyPullRequest();
        unresolvedReview.number = 484;
        unresolvedReview.conversationsResolved = false;
        unresolvedReview.changesRequested = 1;
        printEvaluation(unresolvedReview, engine.evaluate(unresolvedReview));

        // A draft is intentionally excluded from merge eligibility even if
        // its tests pass, because the author has not declared it ready.
        PullRequest draft = healthyPullRequest();
        draft.number = 485;
        draft.draft = true;
        printEvaluation(draft, engine.evaluate(draft));

        // Required checks must pass. Optional checks may be skipped without
        // blocking the merge.
        PullRequest pendingCheck = healthyPullRequest();
        pendingCheck.number = 486;
        pendingCheck.checks[0].state = CheckState::Pending;
        printEvaluation(pendingCheck, engine.evaluate(pendingCheck));

        // Validate a policy conflict before evaluating repository changes.
        try {
            BranchProtection invalidPolicy;
            invalidPolicy.branch = "main";
            invalidPolicy.requiredApprovals = -1;
            GovernanceEngine invalidEngine(invalidPolicy);
        } catch (const invalid_argument& error) {
            cout << "\nPASS: invalid protection policy rejected: "
                 << error.what() << '\n';
        }

        cout << "\nDesign notes\n";
        cout << "- Unit tests isolate business rules and execute quickly.\n";
        cout << "- Integration tests verify interactions across components.\n";
        cout << "- Smoke tests check essential deployed-service behavior.\n";
        cout << "- Regression tests protect previously corrected behavior.\n";
        cout << "- Merge eligibility combines test evidence with repository policy.\n";
        cout << "- Production systems should obtain evidence from trusted CI records,\n"
             << "  not accept caller-supplied pass states without authentication.\n";

        return acceptedResult.eligible ? 0 : 1;
    } catch (const exception& error) {
        cerr << "Governance engine failure: " << error.what() << '\n';
        return 2;
    }
}

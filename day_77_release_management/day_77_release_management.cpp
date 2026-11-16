#include <algorithm>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Release Governance and Deployment Eligibility Engine
 *
 * C++17 implementation emphasizing:
 * - Semantic version validation and ordering
 * - Immutable release identity
 * - Approval authorization
 * - Automated quality gates
 * - Protected production environments
 * - Release eligibility
 * - Deployment and rollback
 * - Audit events
 *
 * Standard library only.
 */

enum class ReleaseState {
    Draft,
    Candidate,
    Approved,
    Released,
    Rejected,
    RolledBack
};

enum class Decision {
    Approved,
    Rejected
};

enum class CheckStatus {
    Passed,
    Failed,
    Pending
};

enum class Environment {
    Staging,
    Production
};

std::string toString(ReleaseState state) {
    switch (state) {
        case ReleaseState::Draft: return "DRAFT";
        case ReleaseState::Candidate: return "CANDIDATE";
        case ReleaseState::Approved: return "APPROVED";
        case ReleaseState::Released: return "RELEASED";
        case ReleaseState::Rejected: return "REJECTED";
        case ReleaseState::RolledBack: return "ROLLED_BACK";
    }
    throw std::logic_error("Unknown release state");
}

std::string toString(CheckStatus status) {
    switch (status) {
        case CheckStatus::Passed: return "PASSED";
        case CheckStatus::Failed: return "FAILED";
        case CheckStatus::Pending: return "PENDING";
    }
    throw std::logic_error("Unknown check status");
}

class GovernanceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Version {
private:
    int major_;
    int minor_;
    int patch_;
    std::string prerelease_;

public:
    Version(int major, int minor, int patch,
            std::string prerelease = "")
        : major_(major),
          minor_(minor),
          patch_(patch),
          prerelease_(std::move(prerelease)) {

        if (major < 0 || minor < 0 || patch < 0) {
            throw GovernanceError("Version components cannot be negative.");
        }
    }

    static Version parse(const std::string& text) {
        static const std::regex* unused = nullptr;
        (void)unused;

        std::istringstream input(text);
        int major, minor, patch;
        char first, second;

        if (!(input >> major >> first >> minor >> second >> patch) ||
            first != '.' || second != '.') {
            throw GovernanceError("Invalid semantic version: " + text);
        }

        if (major < 0 || minor < 0 || patch < 0) {
            throw GovernanceError("Negative version component.");
        }

        std::string suffix;

        if (input.peek() == '-') {
            input.get();
            std::getline(input, suffix);

            if (suffix.empty()) {
                throw GovernanceError("Empty prerelease identifier.");
            }

            for (unsigned char c : suffix) {
                if (!std::isalnum(c) && c != '.' && c != '-') {
                    throw GovernanceError("Invalid prerelease identifier.");
                }
            }
        }

        if (input.peek() != EOF) {
            throw GovernanceError("Unexpected version characters.");
        }

        std::string canonical =
            std::to_string(major) + "." +
            std::to_string(minor) + "." +
            std::to_string(patch);

        if (canonical != text.substr(0, canonical.size())) {
            throw GovernanceError("Leading zeros are not permitted.");
        }

        return Version(major, minor, patch, suffix);
    }

    std::string str() const {
        std::string result =
            std::to_string(major_) + "." +
            std::to_string(minor_) + "." +
            std::to_string(patch_);

        if (!prerelease_.empty()) {
            result += "-" + prerelease_;
        }

        return result;
    }

    bool isPrerelease() const {
        return !prerelease_.empty();
    }

    friend bool operator<(const Version& a, const Version& b) {
        if (a.major_ != b.major_) return a.major_ < b.major_;
        if (a.minor_ != b.minor_) return a.minor_ < b.minor_;
        if (a.patch_ != b.patch_) return a.patch_ < b.patch_;

        if (a.prerelease_.empty() != b.prerelease_.empty()) {
            return !a.prerelease_.empty();
        }

        return a.prerelease_ < b.prerelease_;
    }

    friend bool operator==(const Version& a, const Version& b) {
        return a.major_ == b.major_ &&
               a.minor_ == b.minor_ &&
               a.patch_ == b.patch_ &&
               a.prerelease_ == b.prerelease_;
    }

    friend bool operator<=(const Version& a, const Version& b) {
        return !(b < a);
    }
};

struct Approval {
    std::string reviewer;
    std::string role;
    Decision decision;
    std::string comment;
};

struct QualityCheck {
    std::string name;
    CheckStatus status;
    std::string details;
};

struct AuditEvent {
    std::size_t sequence;
    std::string actor;
    std::string action;
    std::string details;
};

struct ReleasePolicy {
    std::size_t requiredApprovals = 2;

    std::set<std::string> eligibleRoles = {
        "security_lead",
        "engineering_lead",
        "qa_lead",
        "product_owner"
    };

    std::set<std::string> requiredChecks = {
        "unit_tests",
        "integration_tests",
        "security_scan",
        "dependency_audit"
    };

    bool allowPrereleaseProduction = false;
    bool requireReleaseNotes = true;
    bool requireDigest = true;
};

struct Release {
    std::string id;
    std::string product;
    Version version;
    std::string sourceCommit;
    std::string artifactDigest;
    std::string releaseNotes;
    Environment environment;

    ReleaseState state = ReleaseState::Draft;

    std::map<std::string, Approval> approvals;
    std::map<std::string, QualityCheck> checks;
    std::vector<AuditEvent> audit;

    std::string rollbackVersion;

    Release(
        std::string releaseId,
        std::string productName,
        Version releaseVersion,
        std::string commit,
        std::string digest,
        std::string notes,
        Environment target
    )
        : id(std::move(releaseId)),
          product(std::move(productName)),
          version(std::move(releaseVersion)),
          sourceCommit(std::move(commit)),
          artifactDigest(std::move(digest)),
          releaseNotes(std::move(notes)),
          environment(target) {}
};

struct Evaluation {
    bool eligible = false;
    std::vector<std::string> blockers;
    std::size_t approvals = 0;
};

class ReleaseGovernanceEngine {
private:
    ReleasePolicy policy_;

    std::map<std::string, Release> releases_;

    std::map<std::string, std::set<Version>> published_;
    std::map<std::string, Version> production_;

    static bool validCommit(const std::string& value) {
        if (value.size() < 7 || value.size() > 64) return false;

        return std::all_of(
            value.begin(), value.end(),
            [](unsigned char c) { return std::isxdigit(c); }
        );
    }

    static bool validDigest(const std::string& value) {
        return value.size() == 64 &&
            std::all_of(
                value.begin(), value.end(),
                [](unsigned char c) { return std::isxdigit(c); }
            );
    }

    void log(
        Release& release,
        const std::string& actor,
        const std::string& action,
        const std::string& details = ""
    ) {
        release.audit.push_back({
            release.audit.size() + 1,
            actor,
            action,
            details
        });
    }

    Release& get(const std::string& id) {
        auto it = releases_.find(id);

        if (it == releases_.end()) {
            throw GovernanceError("Unknown release: " + id);
        }

        return it->second;
    }

public:
    explicit ReleaseGovernanceEngine(ReleasePolicy policy)
        : policy_(std::move(policy)) {

        if (policy_.requiredApprovals == 0) {
            throw GovernanceError("Approval threshold must be positive.");
        }

        if (policy_.requiredChecks.empty()) {
            throw GovernanceError("At least one quality check is required.");
        }
    }

    void createRelease(
        const std::string& id,
        const std::string& product,
        const std::string& versionText,
        const std::string& commit,
        const std::string& digest,
        const std::string& notes,
        Environment environment
    ) {
        if (id.empty() || product.empty()) {
            throw GovernanceError("Release ID and product are required.");
        }

        if (releases_.count(id)) {
            throw GovernanceError("Duplicate release ID.");
        }

        if (!validCommit(commit)) {
            throw GovernanceError("Invalid source commit.");
        }

        if (policy_.requireDigest && !validDigest(digest)) {
            throw GovernanceError("Artifact digest must be SHA-256.");
        }

        if (policy_.requireReleaseNotes && notes.empty()) {
            throw GovernanceError("Release notes are required.");
        }

        Release release(
            id,
            product,
            Version::parse(versionText),
            commit,
            digest,
            notes,
            environment
        );

        log(release, "release_service", "CREATED", versionText);

        releases_.emplace(id, std::move(release));
    }

    void submitCandidate(const std::string& id) {
        Release& release = get(id);

        if (release.state != ReleaseState::Draft) {
            throw GovernanceError("Release is not a draft.");
        }

        const auto& versions = published_[release.product];

        if (versions.count(release.version)) {
            throw GovernanceError("Version already published.");
        }

        if (release.environment == Environment::Production) {
            auto it = production_.find(release.product);

            if (it != production_.end() &&
                release.version <= it->second) {
                throw GovernanceError(
                    "Production version must be newer."
                );
            }
        }

        release.state = ReleaseState::Candidate;
        log(release, "release_manager", "CANDIDATE_SUBMITTED");
    }

    void recordCheck(
        const std::string& id,
        const std::string& name,
        CheckStatus status,
        const std::string& details
    ) {
        Release& release = get(id);

        if (release.state != ReleaseState::Candidate) {
            throw GovernanceError("Checks require candidate state.");
        }

        if (!policy_.requiredChecks.count(name)) {
            throw GovernanceError("Unknown quality check.");
        }

        release.checks[name] = {name, status, details};

        log(
            release,
            "ci_pipeline",
            "CHECK_RECORDED",
            name + "=" + toString(status)
        );
    }

    void recordApproval(
        const std::string& id,
        const std::string& reviewer,
        const std::string& role,
        Decision decision,
        const std::string& comment
    ) {
        Release& release = get(id);

        if (release.state != ReleaseState::Candidate) {
            throw GovernanceError("Approval requires candidate state.");
        }

        if (reviewer.empty()) {
            throw GovernanceError("Reviewer identity is required.");
        }

        if (!policy_.eligibleRoles.count(role)) {
            throw GovernanceError("Reviewer role is not eligible.");
        }

        if (release.approvals.count(reviewer)) {
            throw GovernanceError("Duplicate reviewer decision.");
        }

        release.approvals.emplace(
            reviewer,
            Approval{reviewer, role, decision, comment}
        );

        log(
            release,
            reviewer,
            "APPROVAL_RECORDED",
            decision == Decision::Approved ? "APPROVED" : "REJECTED"
        );
    }

    Evaluation evaluate(const std::string& id) {
        Release& release = get(id);
        Evaluation result;

        if (release.state != ReleaseState::Candidate) {
            result.blockers.push_back("Release is not a candidate.");
        }

        if (policy_.requireReleaseNotes && release.releaseNotes.empty()) {
            result.blockers.push_back("Release notes missing.");
        }

        if (policy_.requireDigest && !validDigest(release.artifactDigest)) {
            result.blockers.push_back("Artifact digest invalid.");
        }

        for (const auto& [name, approval] : release.approvals) {
            if (approval.decision == Decision::Rejected) {
                result.blockers.push_back(
                    "Release rejected by " + name
                );
            }

            if (approval.decision == Decision::Approved) {
                ++result.approvals;
            }
        }

        if (result.approvals < policy_.requiredApprovals) {
            result.blockers.push_back("Insufficient approvals.");
        }

        for (const auto& name : policy_.requiredChecks) {
            auto it = release.checks.find(name);

            if (it == release.checks.end()) {
                result.blockers.push_back("Missing check: " + name);
            } else if (it->second.status != CheckStatus::Passed) {
                result.blockers.push_back("Check not passed: " + name);
            }
        }

        if (
            release.environment == Environment::Production &&
            release.version.isPrerelease() &&
            !policy_.allowPrereleaseProduction
        ) {
            result.blockers.push_back(
                "Prerelease production deployment is prohibited."
            );
        }

        result.eligible = result.blockers.empty();
        return result;
    }

    void approveForDeployment(const std::string& id) {
        Release& release = get(id);
        Evaluation evaluation = evaluate(id);

        if (!evaluation.eligible) {
            std::ostringstream message;
            message << "Release blocked:";

            for (const auto& blocker : evaluation.blockers) {
                message << "\n - " << blocker;
            }

            throw GovernanceError(message.str());
        }

        release.state = ReleaseState::Approved;
        log(release, "governance_engine", "GOVERNANCE_APPROVED");
    }

    void deploy(const std::string& id, const std::string& actor) {
        Release& release = get(id);

        if (release.state != ReleaseState::Approved) {
            throw GovernanceError("Release is not approved.");
        }

        if (release.environment != Environment::Production) {
            throw GovernanceError("Target is not production.");
        }

        auto current = production_.find(release.product);

        if (current != production_.end() &&
            release.version <= current->second) {
            throw GovernanceError("Production version regression.");
        }

        published_[release.product].insert(release.version);
        production_[release.product] = release.version;

        release.state = ReleaseState::Released;

        log(
            release,
            actor,
            "DEPLOYED",
            release.version.str()
        );
    }

    void rollback(
        const std::string& id,
        const std::string& previousVersion,
        const std::string& actor
    ) {
        Release& release = get(id);

        if (release.state != ReleaseState::Released) {
            throw GovernanceError("Release is not deployed.");
        }

        Version target = Version::parse(previousVersion);

        auto it = published_.find(release.product);

        if (it == published_.end() || !it->second.count(target)) {
            throw GovernanceError("Rollback target was never published.");
        }

        if (target == release.version) {
            throw GovernanceError("Rollback target equals current release.");
        }

        release.rollbackVersion = target.str();
        release.state = ReleaseState::RolledBack;
        production_[release.product] = target;

        log(release, actor, "ROLLBACK", target.str());
    }

    void reject(
        const std::string& id,
        const std::string& actor,
        const std::string& reason
    ) {
        Release& release = get(id);

        if (
            release.state != ReleaseState::Draft &&
            release.state != ReleaseState::Candidate
        ) {
            throw GovernanceError("Invalid rejection transition.");
        }

        if (reason.empty()) {
            throw GovernanceError("Rejection reason is required.");
        }

        release.state = ReleaseState::Rejected;
        log(release, actor, "REJECTED", reason);
    }

    void printReport(const std::string& id) {
        const Release& release = get(id);

        std::cout << "\nRelease Governance Report\n"
                  << "-------------------------\n"
                  << "Release ID: " << release.id << '\n'
                  << "Product: " << release.product << '\n'
                  << "Version: " << release.version.str() << '\n'
                  << "State: " << toString(release.state) << '\n'
                  << "Commit: " << release.sourceCommit << '\n'
                  << "Digest: " << release.artifactDigest << '\n'
                  << "Approvals: " << release.approvals.size() << '\n';

        std::cout << "\nQuality checks:\n";

        for (const auto& [name, check] : release.checks) {
            std::cout << "  " << name << ": "
                      << toString(check.status) << '\n';
        }

        std::cout << "\nAudit history:\n";

        for (const auto& event : release.audit) {
            std::cout << "  #" << event.sequence
                      << " " << event.actor
                      << " | " << event.action
                      << " | " << event.details << '\n';
        }
    }
};

int main() {
    try {
        ReleasePolicy policy;
        ReleaseGovernanceEngine engine(policy);

        const std::string digest(64, 'a');

        engine.createRelease(
            "REL-2026-001",
            "CoreBanking",
            "4.1.0",
            std::string(40, 'b'),
            digest,
            "Transaction reliability and security improvements.",
            Environment::Production
        );

        engine.submitCandidate("REL-2026-001");

        engine.recordCheck(
            "REL-2026-001", "unit_tests",
            CheckStatus::Passed, "All unit tests passed."
        );

        engine.recordCheck(
            "REL-2026-001", "integration_tests",
            CheckStatus::Passed, "Integration tests passed."
        );

        engine.recordCheck(
            "REL-2026-001", "security_scan",
            CheckStatus::Passed, "No critical findings."
        );

        engine.recordCheck(
            "REL-2026-001", "dependency_audit",
            CheckStatus::Passed, "Dependencies verified."
        );

        engine.recordApproval(
            "REL-2026-001",
            "security_reviewer",
            "security_lead",
            Decision::Approved,
            "Security assessment complete."
        );

        engine.recordApproval(
            "REL-2026-001",
            "engineering_reviewer",
            "engineering_lead",
            Decision::Approved,
            "Build verified."
        );

        Evaluation result = engine.evaluate("REL-2026-001");

        std::cout << "Release eligible: "
                  << (result.eligible ? "YES" : "NO") << '\n';

        if (!result.eligible) {
            for (const auto& blocker : result.blockers) {
                std::cout << "BLOCKED: " << blocker << '\n';
            }
        } else {
            engine.approveForDeployment("REL-2026-001");
            engine.deploy("REL-2026-001", "deployment_service");
        }

        engine.printReport("REL-2026-001");

        // Demonstrate governance failure for an incomplete candidate.
        engine.createRelease(
            "REL-2026-002",
            "CoreBanking",
            "4.2.0",
            std::string(40, 'c'),
            digest,
            "New account processing functionality.",
            Environment::Production
        );

        engine.submitCandidate("REL-2026-002");

        Evaluation incomplete = engine.evaluate("REL-2026-002");

        std::cout << "\nIncomplete release eligible: "
                  << (incomplete.eligible ? "YES" : "NO") << '\n';

        for (const auto& blocker : incomplete.blockers) {
            std::cout << "BLOCKED: " << blocker << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Governance error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

/*
 * Git Branching Case Study
 * ========================
 *
 * Industry-style scenario:
 *
 * A software company maintains a web service on the `main` branch. Developers
 * create feature branches for isolated work. The system models commits,
 * branches, HEAD, working files, fast-forward merges, three-way merges,
 * conflicts, conflict resolution, branch deletion, and pre-merge validation.
 *
 * This is an educational simulation of Git's branching concepts. It does not
 * execute the Git command-line program.
 *
 * Compile:
 *
 *     g++ -std=c++17 -Wall -Wextra -pedantic git_branching.cpp -o git_branching
 *
 * Run:
 *
 *     ./git_branching
 */

#include <algorithm>
#include <cstddef>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// 1. COMMIT
// ============================================================================

struct Commit {
    string id;
    string message;
    vector<string> parents;
    map<string, string> files;

    string shortId() const {
        return id.substr(0, min<size_t>(8, id.size()));
    }
};


// ============================================================================
// 2. MERGE RESULT
// ============================================================================

enum class MergeType {
    AlreadyUpToDate,
    FastForward,
    MergeCommit,
    Conflict
};

struct MergeResult {
    MergeType type;
    vector<string> conflicts;
};


// ============================================================================
// 3. REPOSITORY
// ============================================================================

class Repository {
private:
    map<string, Commit> commits;
    map<string, string> branches;

    string headBranch;
    string detachedHead;

    map<string, string> workingTree;
    map<string, string> stagingArea;

    unsigned long long sequence = 0;

    /*
     * A real Git object ID is derived from object content and metadata.
     * This educational implementation uses a deterministic lightweight ID.
     */
    string generateId(
        const string& message,
        const vector<string>& parents,
        const map<string, string>& files
    ) {
        ++sequence;

        string data = to_string(sequence) + "|" + message + "|";

        for (const auto& parent : parents) {
            data += parent + "|";
        }

        for (const auto& [path, content] : files) {
            data += path + "=" + content + "|";
        }

        size_t hashValue = hash<string>{}(data);

        stringstream output;
        output << hex << hashValue;

        return output.str();
    }

    const Commit& commitAt(const string& id) const {
        auto iterator = commits.find(id);

        if (iterator == commits.end()) {
            throw runtime_error("Unknown commit: " + id);
        }

        return iterator->second;
    }

    Commit& mutableCommitAt(const string& id) {
        auto iterator = commits.find(id);

        if (iterator == commits.end()) {
            throw runtime_error("Unknown commit: " + id);
        }

        return iterator->second;
    }

public:
    // ========================================================================
    // Repository initialization
    // ========================================================================

    void initialize() {
        map<string, string> files{
            {"README.md", "# Branching Case Study\n"},
            {"service.cpp", "int health() { return 200; }\n"}
        };

        vector<string> parents;
        string id = generateId("Initial commit", parents, files);

        commits.emplace(
            id,
            Commit{id, "Initial commit", parents, files}
        );

        branches["main"] = id;
        headBranch = "main";
        detachedHead.clear();
        workingTree = files;
        stagingArea.clear();
    }

    // ========================================================================
    // HEAD
    // ========================================================================

    string headCommitId() const {
        if (!headBranch.empty()) {
            auto iterator = branches.find(headBranch);

            if (iterator == branches.end()) {
                throw runtime_error("HEAD references a missing branch.");
            }

            return iterator->second;
        }

        if (!detachedHead.empty()) {
            return detachedHead;
        }

        throw runtime_error("HEAD has no valid location.");
    }

    const Commit& headCommit() const {
        return commitAt(headCommitId());
    }

    // ========================================================================
    // Branch operations
    // ========================================================================

    void createBranch(const string& name) {
        if (branches.count(name)) {
            throw runtime_error("Branch already exists: " + name);
        }

        branches[name] = headCommitId();
    }

    void switchBranch(const string& name) {
        /*
         * This models:
         *
         *     git switch <branch>
         *
         * HEAD becomes attached to the named branch.
         */
        if (!branches.count(name)) {
            throw runtime_error("Unknown branch: " + name);
        }

        headBranch = name;
        detachedHead.clear();

        workingTree = commitAt(branches[name]).files;
        stagingArea.clear();
    }

    void createAndSwitch(const string& name) {
        /*
         * Equivalent conceptually to:
         *
         *     git switch -c <name>
         */
        createBranch(name);
        switchBranch(name);
    }

    void checkout(const string& target) {
        /*
         * checkout is historically multi-purpose.
         *
         * If target is a branch, HEAD attaches to it.
         * If target is a commit, HEAD becomes detached.
         */
        if (branches.count(target)) {
            switchBranch(target);
            return;
        }

        if (commits.count(target)) {
            headBranch.clear();
            detachedHead = target;
            workingTree = commitAt(target).files;
            stagingArea.clear();
            return;
        }

        throw runtime_error("Unknown checkout target: " + target);
    }

    // ========================================================================
    // Working tree and staging area
    // ========================================================================

    void editFile(
        const string& path,
        const string& content
    ) {
        workingTree[path] = content;
    }

    void stageFile(const string& path) {
        if (!workingTree.count(path)) {
            throw runtime_error(
                "Cannot stage missing file: " + path
            );
        }

        stagingArea[path] = workingTree[path];
    }

    void stageAll() {
        stagingArea = workingTree;
    }

    string commit(const string& message) {
        if (headBranch.empty()) {
            throw runtime_error(
                "Cannot create a normal branch commit from detached HEAD."
            );
        }

        if (stagingArea.empty()) {
            throw runtime_error("Nothing is staged.");
        }

        map<string, string> files = headCommit().files;

        for (const auto& [path, content] : stagingArea) {
            files[path] = content;
        }

        vector<string> parents{headCommitId()};

        string id = generateId(message, parents, files);

        commits.emplace(
            id,
            Commit{id, message, parents, files}
        );

        branches[headBranch] = id;
        workingTree = files;
        stagingArea.clear();

        return id;
    }

    string commitAll(const string& message) {
        stageAll();
        return commit(message);
    }

    // ========================================================================
    // Ancestor analysis
    // ========================================================================

    set<string> ancestors(const string& commitId) const {
        set<string> visited;
        queue<string> pending;

        pending.push(commitId);

        while (!pending.empty()) {
            string current = pending.front();
            pending.pop();

            if (visited.count(current)) {
                continue;
            }

            visited.insert(current);

            const Commit& commit = commitAt(current);

            for (const string& parent : commit.parents) {
                pending.push(parent);
            }
        }

        return visited;
    }

    bool isAncestor(
        const string& ancestor,
        const string& descendant
    ) const {
        set<string> history = ancestors(descendant);
        return history.count(ancestor) > 0;
    }

    string findMergeBase(
        const string& first,
        const string& second
    ) const {
        set<string> firstHistory = ancestors(first);

        queue<string> pending;
        set<string> visited;

        pending.push(second);

        while (!pending.empty()) {
            string current = pending.front();
            pending.pop();

            if (visited.count(current)) {
                continue;
            }

            visited.insert(current);

            if (firstHistory.count(current)) {
                return current;
            }

            for (const string& parent : commitAt(current).parents) {
                pending.push(parent);
            }
        }

        return "";
    }

    // ========================================================================
    // Merge
    // ========================================================================

    MergeResult merge(
        const string& targetBranch,
        const map<string, string>& resolutions = {}
    ) {
        if (headBranch.empty()) {
            throw runtime_error("Cannot merge while HEAD is detached.");
        }

        if (!branches.count(targetBranch)) {
            throw runtime_error(
                "Unknown branch: " + targetBranch
            );
        }

        string currentId = headCommitId();
        string targetId = branches[targetBranch];

        if (currentId == targetId) {
            return {
                MergeType::AlreadyUpToDate,
                {}
            };
        }

        /*
         * If target is already part of current history, no new work is needed.
         */
        if (isAncestor(targetId, currentId)) {
            return {
                MergeType::AlreadyUpToDate,
                {}
            };
        }

        /*
         * Fast-forward:
         *
         * A---B---C  target
         *     ^
         *     main
         *
         * main can simply move to C.
         */
        if (isAncestor(currentId, targetId)) {
            branches[headBranch] = targetId;
            workingTree = commitAt(targetId).files;
            stagingArea.clear();

            return {
                MergeType::FastForward,
                {}
            };
        }

        /*
         * A three-way merge compares:
         *
         *     merge base
         *     current branch tip
         *     target branch tip
         */
        string baseId = findMergeBase(currentId, targetId);

        if (baseId.empty()) {
            throw runtime_error("No common merge base found.");
        }

        const Commit& base = commitAt(baseId);
        const Commit& current = commitAt(currentId);
        const Commit& target = commitAt(targetId);

        map<string, string> merged = base.files;
        set<string> paths;

        for (const auto& [path, content] : base.files) {
            paths.insert(path);
        }

        for (const auto& [path, content] : current.files) {
            paths.insert(path);
        }

        for (const auto& [path, content] : target.files) {
            paths.insert(path);
        }

        vector<string> conflicts;

        for (const string& path : paths) {
            auto baseIterator = base.files.find(path);
            auto currentIterator = current.files.find(path);
            auto targetIterator = target.files.find(path);

            string baseValue =
                baseIterator == base.files.end()
                    ? ""
                    : baseIterator->second;

            string currentValue =
                currentIterator == current.files.end()
                    ? ""
                    : currentIterator->second;

            string targetValue =
                targetIterator == target.files.end()
                    ? ""
                    : targetIterator->second;

            bool currentChanged =
                currentValue != baseValue;

            bool targetChanged =
                targetValue != baseValue;

            if (currentChanged && targetChanged) {
                if (currentValue == targetValue) {
                    merged[path] = currentValue;
                } else if (resolutions.count(path)) {
                    merged[path] = resolutions.at(path);
                } else {
                    conflicts.push_back(path);

                    merged[path] =
                        "<<<<<<< CURRENT\n" +
                        currentValue +
                        "=======\n" +
                        targetValue +
                        ">>>>>>> TARGET\n";
                }
            } else if (currentChanged) {
                merged[path] = currentValue;
            } else if (targetChanged) {
                merged[path] = targetValue;
            }
        }

        if (!conflicts.empty()) {
            workingTree = merged;

            return {
                MergeType::Conflict,
                conflicts
            };
        }

        string message =
            "Merge branch '" +
            targetBranch +
            "' into '" +
            headBranch +
            "'";

        vector<string> parents{
            currentId,
            targetId
        };

        string mergeId = generateId(
            message,
            parents,
            merged
        );

        commits.emplace(
            mergeId,
            Commit{
                mergeId,
                message,
                parents,
                merged
            }
        );

        branches[headBranch] = mergeId;
        workingTree = merged;
        stagingArea.clear();

        return {
            MergeType::MergeCommit,
            {}
        };
    }

    // ========================================================================
    // Branch deletion
    // ========================================================================

    void deleteBranch(
        const string& name,
        bool force = false
    ) {
        if (!branches.count(name)) {
            throw runtime_error(
                "Branch does not exist: " + name
            );
        }

        if (name == headBranch) {
            throw runtime_error(
                "Cannot delete the current branch."
            );
        }

        string branchCommit = branches[name];

        if (!force &&
            !isAncestor(branchCommit, headCommitId())) {
            throw runtime_error(
                "Branch contains unmerged work. "
                "Use forced deletion only intentionally."
            );
        }

        branches.erase(name);
    }

    // ========================================================================
    // Reporting
    // ========================================================================

    void status() const {
        cout
            << "Branch: "
            << (headBranch.empty() ? "(detached HEAD)" : headBranch)
            << '\n';

        cout
            << "HEAD: "
            << headCommit().shortId()
            << '\n';

        bool changed = false;

        set<string> paths;

        for (const auto& [path, content] : headCommit().files) {
            paths.insert(path);
        }

        for (const auto& [path, content] : workingTree) {
            paths.insert(path);
        }

        for (const string& path : paths) {
            string committed;
            string working;

            if (headCommit().files.count(path)) {
                committed = headCommit().files.at(path);
            }

            if (workingTree.count(path)) {
                working = workingTree.at(path);
            }

            if (committed != working) {
                cout << "Modified: " << path << '\n';
                changed = true;
            }
        }

        if (!changed) {
            cout << "Working tree clean.\n";
        }
    }

    void showBranches() const {
        cout << "\nBranches:\n";

        for (const auto& [name, id] : branches) {
            string marker =
                name == headBranch ? "*" : " ";

            cout
                << marker
                << " "
                << left
                << setw(24)
                << name
                << " -> "
                << commitAt(id).shortId()
                << " "
                << commitAt(id).message
                << '\n';
        }
    }

    void graph() const {
        cout << "\nCommit graph:\n";

        map<string, vector<string>> labels;

        for (const auto& [branch, id] : branches) {
            labels[id].push_back(branch);
        }

        set<string> visited;
        queue<string> pending;

        pending.push(headCommitId());

        while (!pending.empty()) {
            string id = pending.front();
            pending.pop();

            if (visited.count(id)) {
                continue;
            }

            visited.insert(id);

            const Commit& commit = commitAt(id);

            cout
                << "* "
                << commit.shortId();

            if (labels.count(id)) {
                cout << " [";

                for (size_t index = 0;
                     index < labels[id].size();
                     ++index) {
                    if (index > 0) {
                        cout << ", ";
                    }

                    cout << labels[id][index];
                }

                cout << "]";
            }

            cout
                << " "
                << commit.message
                << '\n';

            for (const string& parent : commit.parents) {
                pending.push(parent);
            }
        }
    }

    string currentBranch() const {
        return headBranch;
    }

    const map<string, string>& currentFiles() const {
        return workingTree;
    }
};


// ============================================================================
// 4. RESULT PRINTING
// ============================================================================

string mergeTypeToString(MergeType type) {
    switch (type) {
        case MergeType::AlreadyUpToDate:
            return "already up-to-date";

        case MergeType::FastForward:
            return "fast-forward";

        case MergeType::MergeCommit:
            return "merge commit";

        case MergeType::Conflict:
            return "conflict";
    }

    return "unknown";
}


// ============================================================================
// 5. APPLICATION DOMAIN
// ============================================================================

class ReleaseValidator {
public:
    static bool validate(
        const map<string, string>& files,
        string& reason
    ) {
        if (!files.count("README.md")) {
            reason = "README.md is missing.";
            return false;
        }

        if (!files.count("service.cpp")) {
            reason = "service.cpp is missing.";
            return false;
        }

        const string& service = files.at("service.cpp");

        if (service.find("health") == string::npos) {
            reason = "Health endpoint implementation is missing.";
            return false;
        }

        reason = "All release checks passed.";
        return true;
    }
};


// ============================================================================
// 6. CASE STUDY
// ============================================================================

void runCaseStudy() {
    cout
        << "\n"
        << string(78, '=')
        << "\n"
        << "Git Branching Industry-Style Case Study\n"
        << string(78, '=')
        << "\n";

    /*
     * Scenario:
     *
     * The main branch represents the production-ready line of development.
     *
     * A developer is asked to add authentication. The developer creates a
     * feature branch and works independently.
     *
     * Meanwhile, another developer improves service metadata on main.
     *
     * The authentication branch is later merged into main.
     */

    Repository repository;
    repository.initialize();

    cout << "\nInitial repository:\n";
    repository.status();
    repository.showBranches();

    // ------------------------------------------------------------------------
    // Stable baseline
    // ------------------------------------------------------------------------

    repository.editFile(
        "service.cpp",
        "int health() { return 200; }\n"
        "const char* version() { return \"1.0\"; }\n"
    );

    repository.commitAll(
        "Add service health and version information"
    );

    // ------------------------------------------------------------------------
    // Feature branch
    // ------------------------------------------------------------------------

    repository.createAndSwitch(
        "feature/authentication"
    );

    repository.editFile(
        "auth.cpp",
        "bool authenticate("
        "const string& username, "
        "const string& password) {\n"
        "    return !username.empty() && !password.empty();\n"
        "}\n"
    );

    repository.commitAll(
        "Add authentication service"
    );

    repository.editFile(
        "auth.cpp",
        "bool authenticate("
        "const string& username, "
        "const string& password) {\n"
        "    if (username.empty() || password.empty()) {\n"
        "        return false;\n"
        "    }\n"
        "    return username == \"admin\" && password == \"demo\";\n"
        "}\n"
    );

    repository.commitAll(
        "Validate authentication credentials"
    );

    // ------------------------------------------------------------------------
    // Main develops independently
    // ------------------------------------------------------------------------

    repository.switchBranch("main");

    repository.editFile(
        "service.cpp",
        "int health() { return 200; }\n"
        "const char* version() { return \"1.1\"; }\n"
        "const char* environment() { return \"production\"; }\n"
    );

    repository.commitAll(
        "Add production service metadata"
    );

    cout << "\nBefore merge:\n";
    repository.graph();

    // ------------------------------------------------------------------------
    // Pre-merge validation
    // ------------------------------------------------------------------------

    string validationReason;

    bool valid = ReleaseValidator::validate(
        repository.currentFiles(),
        validationReason
    );

    cout
        << "\nPre-merge validation: "
        << (valid ? "PASS" : "FAIL")
        << '\n';

    cout
        << "Reason: "
        << validationReason
        << '\n';

    if (!valid) {
        throw runtime_error(
            "Repository cannot proceed to integration."
        );
    }

    // ------------------------------------------------------------------------
    // Merge feature into main
    // ------------------------------------------------------------------------

    MergeResult result =
        repository.merge("feature/authentication");

    cout
        << "\nMerge result: "
        << mergeTypeToString(result.type)
        << '\n';

    if (!result.conflicts.empty()) {
        cout << "Conflicts:\n";

        for (const string& conflict : result.conflicts) {
            cout << "  " << conflict << '\n';
        }
    }

    repository.graph();

    // ------------------------------------------------------------------------
    // Delete completed branch
    // ------------------------------------------------------------------------

    repository.deleteBranch(
        "feature/authentication"
    );

    cout << "\nAfter feature branch deletion:\n";
    repository.showBranches();
}


// ============================================================================
// 7. CONFLICT CASE STUDY
// ============================================================================

void runConflictCase() {
    cout
        << "\n"
        << string(78, '=')
        << "\n"
        << "Conflict Resolution Case\n"
        << string(78, '=')
        << "\n";

    Repository repository;
    repository.initialize();

    repository.editFile(
        "config.txt",
        "environment=development\n"
    );

    repository.commitAll(
        "Add environment configuration"
    );

    repository.createAndSwitch(
        "feature/configuration"
    );

    repository.editFile(
        "config.txt",
        "environment=feature\n"
    );

    repository.commitAll(
        "Configure feature environment"
    );

    repository.switchBranch("main");

    repository.editFile(
        "config.txt",
        "environment=production\n"
    );

    repository.commitAll(
        "Configure production environment"
    );

    MergeResult firstAttempt =
        repository.merge(
            "feature/configuration"
        );

    cout
        << "\nFirst merge attempt: "
        << mergeTypeToString(firstAttempt.type)
        << '\n';

    for (const string& conflict : firstAttempt.conflicts) {
        cout << "Conflict: " << conflict << '\n';
    }

    /*
     * The application owner decides the intended final configuration.
     * The simulation then performs the equivalent of resolving the conflict,
     * staging the resolution, and recording the merge result.
     */
    map<string, string> resolutions{
        {
            "config.txt",
            "environment=production\n"
            "feature_mode=true\n"
        }
    };

    /*
     * For this demonstration, recreate the pre-merge state by using a fresh
     * repository and apply the resolution during the merge operation.
     */
    Repository resolvedRepository;
    resolvedRepository.initialize();

    resolvedRepository.editFile(
        "config.txt",
        "environment=development\n"
    );

    resolvedRepository.commitAll(
        "Add environment configuration"
    );

    resolvedRepository.createAndSwitch(
        "feature/configuration"
    );

    resolvedRepository.editFile(
        "config.txt",
        "environment=feature\n"
    );

    resolvedRepository.commitAll(
        "Configure feature environment"
    );

    resolvedRepository.switchBranch("main");

    resolvedRepository.editFile(
        "config.txt",
        "environment=production\n"
    );

    resolvedRepository.commitAll(
        "Configure production environment"
    );

    MergeResult resolved =
        resolvedRepository.merge(
            "feature/configuration",
            resolutions
        );

    cout
        << "\nResolved merge: "
        << mergeTypeToString(resolved.type)
        << '\n';

    cout
        << "Final configuration:\n"
        << resolvedRepository.currentFiles().at("config.txt");
}


// ============================================================================
// 8. DETACHED HEAD CASE
// ============================================================================

void runDetachedHeadCase() {
    cout
        << "\n"
        << string(78, '=')
        << "\n"
        << "Detached HEAD Case\n"
        << string(78, '=')
        << "\n";

    Repository repository;
    repository.initialize();

    string historicalCommit =
        repository.headCommitId();

    repository.editFile(
        "service.cpp",
        "int health() { return 200; }\n"
    );

    repository.commitAll(
        "Add service implementation"
    );

    repository.checkout(historicalCommit);

    cout
        << "HEAD is detached at commit "
        << historicalCommit.substr(
            0,
            min<size_t>(8, historicalCommit.size())
        )
        << ".\n";

    cout
        << "The repository can now inspect historical code without moving "
        << "the main branch pointer.\n";
}


// ============================================================================
// 9. SELF-TESTS
// ============================================================================

void runSelfTests() {
    cout
        << "\n"
        << string(78, '=')
        << "\n"
        << "Self-Tests\n"
        << string(78, '=')
        << "\n";

    // Test branch creation.
    Repository repository;
    repository.initialize();

    repository.createAndSwitch("feature");

    if (repository.currentBranch() != "feature") {
        throw runtime_error(
            "Self-test failed: branch switching."
        );
    }

    // Test feature commit.
    string featureCommit = repository.commitAll(
        "Feature commit after empty staging"
    );

    if (featureCommit.empty()) {
        throw runtime_error(
            "Self-test failed: commit creation."
        );
    }

    // Test fast-forward merge.
    repository.switchBranch("main");

    MergeResult result =
        repository.merge("feature");

    if (result.type != MergeType::FastForward) {
        throw runtime_error(
            "Self-test failed: fast-forward merge."
        );
    }

    if (repository.headCommitId() != featureCommit) {
        throw runtime_error(
            "Self-test failed: branch pointer movement."
        );
    }

    // Test safe branch deletion.
    repository.deleteBranch("feature");

    cout
        << "All C++ self-tests passed.\n";
}


// ============================================================================
// 10. MAIN
// ============================================================================

int main() {
    try {
        runCaseStudy();
        runConflictCase();
        runDetachedHeadCase();
        runSelfTests();

        cout
            << "\n"
            << "Program completed successfully.\n";

        return 0;
    }
    catch (const exception& error) {
        cerr
            << "\nProgram error: "
            << error.what()
            << '\n';

        return 1;
    }
}

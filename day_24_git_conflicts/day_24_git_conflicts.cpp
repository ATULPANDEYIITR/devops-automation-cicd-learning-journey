/*
    Git Conflicts: Conflict Detection, Resolution, and Merge Strategies
    ====================================================================

    C++17 industry-style case study:

    A repository maintenance system receives configuration changes from
    multiple engineering branches. The system models a three-way merge,
    identifies conflict classes, resolves conflicts using explicit policies,
    validates the resulting configuration, records resolution history, and
    reports complexity and operational considerations.

    Compile:
        g++ -std=c++17 -O2 -Wall -Wextra -pedantic git_conflicts.cpp -o git_conflicts

    Run:
        ./git_conflicts

    The implementation intentionally uses only the C++ standard library.
*/

#include <algorithm>
#include <cassert>
#include <cctype>
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
#include <utility>
#include <vector>

using namespace std;

// ---------------------------------------------------------------------------
// Domain model
// ---------------------------------------------------------------------------

struct FileState {
    optional<string> content;

    static FileState present(const string& value) {
        return FileState{value};
    }

    static FileState deleted() {
        return FileState{nullopt};
    }

    bool exists() const {
        return content.has_value();
    }
};

bool sameState(const FileState& left, const FileState& right) {
    return left.content == right.content;
}

enum class ConflictType {
    Content,
    AddAdd,
    ModifyDelete,
    DeleteModify
};

string conflictTypeName(ConflictType type) {
    switch (type) {
        case ConflictType::Content:
            return "content";
        case ConflictType::AddAdd:
            return "add/add";
        case ConflictType::ModifyDelete:
            return "modify/delete";
        case ConflictType::DeleteModify:
            return "delete/modify";
    }

    return "unknown";
}

struct Conflict {
    string path;
    FileState base;
    FileState ours;
    FileState theirs;
    ConflictType type;
    string explanation;
};

struct MergeResult {
    map<string, FileState> mergedTree;
    vector<Conflict> conflicts;

    bool clean() const {
        return conflicts.empty();
    }
};

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

string createConflictMarkers(
    const FileState& ours,
    const FileState& theirs
) {
    const string oursText = ours.content.value_or("");
    const string theirsText = theirs.content.value_or("");

    string result;
    result += "<<<<<<< HEAD\n";
    result += oursText;

    if (!oursText.empty() && oursText.back() != '\n') {
        result += '\n';
    }

    result += "=======\n";
    result += theirsText;

    if (!theirsText.empty() && theirsText.back() != '\n') {
        result += '\n';
    }

    result += ">>>>>>> incoming\n";

    return result;
}

string classifyChange(
    const FileState& base,
    const FileState& side
) {
    if (sameState(base, side)) {
        return "unchanged";
    }

    if (!base.exists() && side.exists()) {
        return "added";
    }

    if (base.exists() && !side.exists()) {
        return "deleted";
    }

    return "modified";
}

void printTree(
    const string& title,
    const map<string, FileState>& tree
) {
    cout << '\n' << title << '\n';
    cout << string(title.size(), '-') << '\n';

    for (const auto& [path, state] : tree) {
        cout << path << ": ";

        if (state.exists()) {
            cout << '"' << *state.content << '"';
        } else {
            cout << "<deleted>";
        }

        cout << '\n';
    }
}

// ---------------------------------------------------------------------------
// Three-way merge engine
// ---------------------------------------------------------------------------

optional<Conflict> detectConflict(
    const string& path,
    const FileState& base,
    const FileState& ours,
    const FileState& theirs
) {
    /*
        Core three-way merge rule:

        1. Both sides equal -> no conflict.
        2. Ours equals base -> accept theirs.
        3. Theirs equals base -> accept ours.
        4. Otherwise both sides changed differently -> conflict.

        Git performs substantially more sophisticated line-level and
        tree-level processing, but this is the essential decision model.
    */

    if (sameState(ours, theirs)) {
        return nullopt;
    }

    if (sameState(ours, base)) {
        return nullopt;
    }

    if (sameState(theirs, base)) {
        return nullopt;
    }

    ConflictType type;
    string explanation;

    if (!base.exists() && ours.exists() && theirs.exists()) {
        type = ConflictType::AddAdd;
        explanation =
            "Both branches created the same path with different content.";
    } else if (base.exists() && !ours.exists() && theirs.exists()) {
        type = ConflictType::DeleteModify;
        explanation =
            "Ours deleted the file while theirs modified it.";
    } else if (base.exists() && ours.exists() && !theirs.exists()) {
        type = ConflictType::ModifyDelete;
        explanation =
            "Ours modified the file while theirs deleted it.";
    } else {
        type = ConflictType::Content;
        explanation =
            "Both branches modified the same base state differently.";
    }

    return Conflict{
        path,
        base,
        ours,
        theirs,
        type,
        explanation
    };
}

MergeResult threeWayMerge(
    const map<string, FileState>& base,
    const map<string, FileState>& ours,
    const map<string, FileState>& theirs
) {
    /*
        std::set gives us the union of all paths. Complexity is approximately
        O(P log P), where P is the number of unique paths, excluding the cost
        of comparing file contents.
    */

    set<string> paths;

    for (const auto& [path, _] : base) {
        paths.insert(path);
    }

    for (const auto& [path, _] : ours) {
        paths.insert(path);
    }

    for (const auto& [path, _] : theirs) {
        paths.insert(path);
    }

    MergeResult result;

    for (const string& path : paths) {
        const auto baseIt = base.find(path);
        const auto oursIt = ours.find(path);
        const auto theirsIt = theirs.find(path);

        const FileState baseState =
            baseIt == base.end() ? FileState::deleted() : baseIt->second;

        const FileState oursState =
            oursIt == ours.end() ? FileState::deleted() : oursIt->second;

        const FileState theirsState =
            theirsIt == theirs.end() ? FileState::deleted() : theirsIt->second;

        auto conflict = detectConflict(
            path,
            baseState,
            oursState,
            theirsState
        );

        if (conflict.has_value()) {
            result.conflicts.push_back(*conflict);
            continue;
        }

        // If ours did not change, incoming content is safe to accept.
        const FileState& selected =
            sameState(oursState, baseState)
                ? theirsState
                : oursState;

        if (selected.exists()) {
            result.mergedTree[path] = selected;
        }
    }

    return result;
}

// ---------------------------------------------------------------------------
// Resolution policies
// ---------------------------------------------------------------------------

enum class ResolutionPolicy {
    Ours,
    Theirs,
    Manual
};

FileState resolveConflict(
    const Conflict& conflict,
    ResolutionPolicy policy,
    const optional<string>& manualContent = nullopt
) {
    switch (policy) {
        case ResolutionPolicy::Ours:
            return conflict.ours;

        case ResolutionPolicy::Theirs:
            return conflict.theirs;

        case ResolutionPolicy::Manual:
            if (!manualContent.has_value()) {
                throw invalid_argument(
                    "Manual resolution requires explicit content."
                );
            }

            return FileState::present(*manualContent);
    }

    throw invalid_argument("Unsupported resolution policy.");
}

map<string, FileState> applyResolutions(
    const MergeResult& merge,
    const map<string, FileState>& resolutions
) {
    set<string> conflictPaths;

    for (const Conflict& conflict : merge.conflicts) {
        conflictPaths.insert(conflict.path);
    }

    set<string> resolutionPaths;

    for (const auto& [path, _] : resolutions) {
        resolutionPaths.insert(path);
    }

    if (conflictPaths != resolutionPaths) {
        throw invalid_argument(
            "Every conflicted path must have exactly one resolution."
        );
    }

    map<string, FileState> resolved = merge.mergedTree;

    for (const auto& [path, state] : resolutions) {
        if (state.exists()) {
            resolved[path] = state;
        } else {
            resolved.erase(path);
        }
    }

    return resolved;
}

// ---------------------------------------------------------------------------
// Configuration parser and validator
// ---------------------------------------------------------------------------

class Configuration {
private:
    map<string, string> values_;

public:
    void parse(const string& text) {
        istringstream input(text);
        string line;
        size_t lineNumber = 0;

        while (getline(input, line)) {
            ++lineNumber;

            if (line.empty()) {
                continue;
            }

            const size_t separator = line.find('=');

            if (separator == string::npos) {
                throw invalid_argument(
                    "Invalid configuration at line " +
                    to_string(lineNumber)
                );
            }

            string key = line.substr(0, separator);
            string value = line.substr(separator + 1);

            if (key.empty()) {
                throw invalid_argument(
                    "Empty configuration key at line " +
                    to_string(lineNumber)
                );
            }

            values_[key] = value;
        }
    }

    optional<string> get(const string& key) const {
        const auto it = values_.find(key);

        if (it == values_.end()) {
            return nullopt;
        }

        return it->second;
    }

    bool validate() const {
        const auto workers = get("workers");
        const auto timeout = get("timeout");

        if (!workers.has_value() || !timeout.has_value()) {
            return false;
        }

        try {
            const int workerCount = stoi(*workers);
            const int timeoutSeconds = stoi(*timeout);

            return workerCount >= 1 &&
                   workerCount <= 1024 &&
                   timeoutSeconds >= 1 &&
                   timeoutSeconds <= 3600;
        } catch (const exception&) {
            return false;
        }
    }

    void print() const {
        for (const auto& [key, value] : values_) {
            cout << key << '=' << value << '\n';
        }
    }
};

// ---------------------------------------------------------------------------
// Conflict resolution cache
// ---------------------------------------------------------------------------

class ResolutionCache {
private:
    map<string, string> resolutions_;

    static string makeKey(const Conflict& conflict) {
        /*
            Production Git uses rerere data with carefully defined conflict
            representations. This educational key combines the path and
            three file states.
        */
        ostringstream material;

        material << conflict.path << '\0';

        if (conflict.base.content.has_value()) {
            material << *conflict.base.content;
        }

        material << '\0';

        if (conflict.ours.content.has_value()) {
            material << *conflict.ours.content;
        }

        material << '\0';

        if (conflict.theirs.content.has_value()) {
            material << *conflict.theirs.content;
        }

        return material.str();
    }

public:
    void record(
        const Conflict& conflict,
        const string& resolution
    ) {
        resolutions_[makeKey(conflict)] = resolution;
    }

    optional<string> lookup(const Conflict& conflict) const {
        const auto it = resolutions_.find(makeKey(conflict));

        if (it == resolutions_.end()) {
            return nullopt;
        }

        return it->second;
    }
};

// ---------------------------------------------------------------------------
// Commit graph
// ---------------------------------------------------------------------------

struct Commit {
    string id;
    vector<string> parents;
    string message;
    map<string, FileState> tree;
};

class RepositoryGraph {
private:
    map<string, Commit> commits_;

    map<string, int> distancesFrom(const string& start) const {
        map<string, int> distances;
        queue<string> pending;

        distances[start] = 0;
        pending.push(start);

        while (!pending.empty()) {
            const string current = pending.front();
            pending.pop();

            const int distance = distances[current];

            const auto commitIt = commits_.find(current);

            if (commitIt == commits_.end()) {
                continue;
            }

            for (const string& parent : commitIt->second.parents) {
                if (!distances.contains(parent)) {
                    distances[parent] = distance + 1;
                    pending.push(parent);
                }
            }
        }

        return distances;
    }

public:
    void addCommit(const Commit& commit) {
        commits_[commit.id] = commit;
    }

    optional<string> mergeBase(
        const string& ours,
        const string& theirs
    ) const {
        const auto oursDistances = distancesFrom(ours);
        const auto theirsDistances = distancesFrom(theirs);

        optional<string> best;
        int bestScore = numeric_limits<int>::max();

        for (const auto& [id, oursDistance] : oursDistances) {
            const auto theirsIt = theirsDistances.find(id);

            if (theirsIt == theirsDistances.end()) {
                continue;
            }

            const int score = oursDistance + theirsIt->second;

            if (score < bestScore) {
                bestScore = score;
                best = id;
            }
        }

        return best;
    }
};

Commit makeCommit(
    const string& id,
    const vector<string>& parents,
    const string& message,
    const map<string, FileState>& tree
) {
    return Commit{id, parents, message, tree};
}

// ---------------------------------------------------------------------------
// Strategy descriptions
// ---------------------------------------------------------------------------

enum class MergeStrategy {
    FastForward,
    RecursiveOrOrtStyleThreeWay,
    Ours,
    Theirs
};

string describeStrategy(MergeStrategy strategy) {
    switch (strategy) {
        case MergeStrategy::FastForward:
            return
                "Moves the branch pointer when the target is an ancestor.";

        case MergeStrategy::RecursiveOrOrtStyleThreeWay:
            return
                "Performs a three-way merge using a merge base and divergent trees.";

        case MergeStrategy::Ours:
            return
                "An ours strategy can record a merge relationship while selecting the current tree.";

        case MergeStrategy::Theirs:
            return
                "Incoming content can be selected as a resolution policy; exact semantics depend on operation/options.";
    }

    return "Unknown strategy.";
}

// ---------------------------------------------------------------------------
// Conflict marker validation
// ---------------------------------------------------------------------------

vector<string> unresolvedMarkerFiles(
    const map<string, FileState>& tree
) {
    const vector<string> markers{
        "<<<<<<<",
        "=======",
        ">>>>>>>"
    };

    vector<string> files;

    for (const auto& [path, state] : tree) {
        if (!state.exists()) {
            continue;
        }

        for (const string& marker : markers) {
            if (state.content->find(marker) != string::npos) {
                files.push_back(path);
                break;
            }
        }
    }

    return files;
}

// ---------------------------------------------------------------------------
// Case study
// ---------------------------------------------------------------------------

class DeploymentConfigurationService {
private:
    map<string, FileState> productionBase_;
    map<string, FileState> releaseBranch_;
    map<string, FileState> featureBranch_;

public:
    DeploymentConfigurationService() {
        productionBase_ = {
            {
                "service.conf",
                FileState::present(
                    "workers=4\n"
                    "timeout=30\n"
                    "mode=standard\n"
                )
            },
            {
                "README.md",
                FileState::present("# Deployment Configuration\n")
            }
        };

        /*
            Release branch changes the operational timeout.
        */
        releaseBranch_ = productionBase_;
        releaseBranch_["service.conf"] =
            FileState::present(
                "workers=4\n"
                "timeout=60\n"
                "mode=standard\n"
            );

        /*
            Feature branch changes workers and independently changes timeout.
            The worker change is compatible, but timeout creates a conflict.
        */
        featureBranch_ = productionBase_;
        featureBranch_["service.conf"] =
            FileState::present(
                "workers=8\n"
                "timeout=120\n"
                "mode=standard\n"
            );
    }

    MergeResult mergeReleaseWithFeature() const {
        return threeWayMerge(
            productionBase_,
            releaseBranch_,
            featureBranch_
        );
    }

    map<string, FileState> resolve(
        const MergeResult& merge
    ) const {
        map<string, FileState> resolutions;

        for (const Conflict& conflict : merge.conflicts) {
            /*
                Business decision:
                - Keep the feature's worker count.
                - Adopt a reviewed timeout of 90 seconds.
                The important lesson is that conflict resolution is a
                semantic engineering decision, not merely a textual action.
            */
            if (conflict.path == "service.conf") {
                resolutions[conflict.path] =
                    FileState::present(
                        "workers=8\n"
                        "timeout=90\n"
                        "mode=standard\n"
                    );
            }
        }

        return applyResolutions(merge, resolutions);
    }

    void run() const {
        cout << "\n=== INDUSTRY-STYLE CASE STUDY ===\n";

        cout <<
            "Scenario: two engineering branches modify a deployment "
            "configuration from the same base.\n";

        const MergeResult merge = mergeReleaseWithFeature();

        cout << "Initial merge clean: "
             << boolalpha
             << merge.clean()
             << '\n';

        for (const Conflict& conflict : merge.conflicts) {
            cout << "\nConflict path: " << conflict.path << '\n';
            cout << "Conflict type: "
                 << conflictTypeName(conflict.type)
                 << '\n';
            cout << "Reason: " << conflict.explanation << '\n';
            cout << "Conflict markers:\n";
            cout << createConflictMarkers(
                conflict.ours,
                conflict.theirs
            );
        }

        const auto resolved = resolve(merge);

        cout << "\nResolved configuration:\n";
        cout << *resolved.at("service.conf").content;

        Configuration configuration;
        configuration.parse(*resolved.at("service.conf").content);

        cout << "\nConfiguration validation: "
             << (configuration.validate() ? "PASS" : "FAIL")
             << '\n';

        const auto markerFiles = unresolvedMarkerFiles(resolved);

        cout << "Unresolved conflict markers: "
             << markerFiles.size()
             << '\n';

        printTree("Final merged tree", resolved);
    }
};

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

void testCleanMerge() {
    const map<string, FileState> base{
        {"a.txt", FileState::present("base\n")}
    };

    const map<string, FileState> ours{
        {"a.txt", FileState::present("ours\n")}
    };

    const map<string, FileState> theirs{
        {"a.txt", FileState::present("base\n")}
    };

    const MergeResult result =
        threeWayMerge(base, ours, theirs);

    assert(result.clean());
    assert(result.mergedTree.at("a.txt").content == "ours\n");
}

void testIdenticalChange() {
    const map<string, FileState> base{
        {"a.txt", FileState::present("base\n")}
    };

    const map<string, FileState> ours{
        {"a.txt", FileState::present("same\n")}
    };

    const map<string, FileState> theirs{
        {"a.txt", FileState::present("same\n")}
    };

    const MergeResult result =
        threeWayMerge(base, ours, theirs);

    assert(result.clean());
    assert(result.mergedTree.at("a.txt").content == "same\n");
}

void testContentConflict() {
    const map<string, FileState> base{
        {"a.txt", FileState::present("base\n")}
    };

    const map<string, FileState> ours{
        {"a.txt", FileState::present("ours\n")}
    };

    const map<string, FileState> theirs{
        {"a.txt", FileState::present("theirs\n")}
    };

    const MergeResult result =
        threeWayMerge(base, ours, theirs);

    assert(!result.clean());
    assert(
        result.conflicts.front().type == ConflictType::Content
    );
}

void testAddAddConflict() {
    const map<string, FileState> base{};

    const map<string, FileState> ours{
        {"new.txt", FileState::present("ours\n")}
    };

    const map<string, FileState> theirs{
        {"new.txt", FileState::present("theirs\n")}
    };

    const MergeResult result =
        threeWayMerge(base, ours, theirs);

    assert(!result.clean());
    assert(
        result.conflicts.front().type == ConflictType::AddAdd
    );
}

void testModifyDeleteConflict() {
    const map<string, FileState> base{
        {"a.txt", FileState::present("base\n")}
    };

    const map<string, FileState> ours{
        {"a.txt", FileState::present("changed\n")}
    };

    const map<string, FileState> theirs{};

    const MergeResult result =
        threeWayMerge(base, ours, theirs);

    assert(!result.clean());
    assert(
        result.conflicts.front().type == ConflictType::ModifyDelete
    );
}

void testResolutionCache() {
    const Conflict conflict{
        "settings.conf",
        FileState::present("timeout=30\n"),
        FileState::present("timeout=60\n"),
        FileState::present("timeout=120\n"),
        ConflictType::Content,
        "Different timeout values."
    };

    ResolutionCache cache;

    cache.record(
        conflict,
        "timeout=90\n"
    );

    const auto result = cache.lookup(conflict);

    assert(result.has_value());
    assert(*result == "timeout=90\n");
}

void runTests() {
    cout << "\n=== C++ TEST SUITE ===\n";

    testCleanMerge();
    cout << "PASS: clean merge\n";

    testIdenticalChange();
    cout << "PASS: identical change\n";

    testContentConflict();
    cout << "PASS: content conflict\n";

    testAddAddConflict();
    cout << "PASS: add/add conflict\n";

    testModifyDeleteConflict();
    cout << "PASS: modify/delete conflict\n";

    testResolutionCache();
    cout << "PASS: resolution cache\n";

    cout << "All tests passed.\n";
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    try {
        cout << string(78, '=') << '\n';
        cout << "GIT CONFLICTS: DETECTION, RESOLUTION, AND MERGE STRATEGIES\n";
        cout << string(78, '=') << '\n';

        cout <<
            "\nCore model: Git compares a merge base with the two divergent "
            "branch states. A conflict occurs when automatic combination "
            "cannot safely determine a result.\n";

        cout << "\n=== STRATEGIES ===\n";

        cout << "Fast-forward: "
             << describeStrategy(MergeStrategy::FastForward)
             << '\n';

        cout << "Three-way: "
             << describeStrategy(
                    MergeStrategy::RecursiveOrOrtStyleThreeWay)
             << '\n';

        cout << "Ours: "
             << describeStrategy(MergeStrategy::Ours)
             << '\n';

        cout << "Theirs: "
             << describeStrategy(MergeStrategy::Theirs)
             << '\n';

        DeploymentConfigurationService service;
        service.run();

        cout << "\n=== MERGE-BASE GRAPH ===\n";

        RepositoryGraph graph;

        graph.addCommit(
            makeCommit(
                "A",
                {},
                "initial",
                {{"app.txt", FileState::present("v1\n")}}
            )
        );

        graph.addCommit(
            makeCommit(
                "B",
                {"A"},
                "main change",
                {{"app.txt", FileState::present("main\n")}}
            )
        );

        graph.addCommit(
            makeCommit(
                "C",
                {"A"},
                "feature change",
                {{"app.txt", FileState::present("feature\n")}}
            )
        );

        const auto base = graph.mergeBase("B", "C");

        cout << "Merge base of B and C: "
             << base.value_or("<none>")
             << '\n';

        runTests();

        cout << "\n=== OPERATIONAL COMMANDS ===\n";
        cout << "git status\n";
        cout << "git diff\n";
        cout << "git diff --cc\n";
        cout << "git diff --name-only --diff-filter=U\n";
        cout << "git ls-files -u\n";
        cout << "git add <resolved-file>\n";
        cout << "git merge --continue\n";
        cout << "git merge --abort\n";
        cout << "git rebase --continue\n";
        cout << "git rebase --abort\n";

        cout << "\nProgram completed successfully.\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}

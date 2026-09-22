/*
 * Git Commands Case Study
 *
 * Topic:
 *     init, clone, status, add, commit, push, pull
 *
 * Language:
 *     C++17 or later
 *
 * This program models a small software-development organization that uses
 * Git repositories to track a project called "Incident Analytics".
 *
 * The program intentionally implements the Git concepts as a controlled
 * repository simulation instead of invoking the user's real Git executable.
 * This makes the case study portable and allows the important states and
 * transitions to be inspected directly.
 *
 * The simulation models:
 *
 *     working tree
 *         |
 *         | add
 *         v
 *     staging area
 *         |
 *         | commit
 *         v
 *     local repository
 *         |
 *         | push
 *         v
 *     remote repository
 *
 * It also models clone and pull, non-fast-forward push rejection, commit
 * history, status reporting, validation, and complexity considerations.
 */

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

string join(const vector<string>& values, const string& separator) {
    ostringstream output;

    for (size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            output << separator;
        }

        output << values[index];
    }

    return output.str();
}

string repeat(char character, size_t count) {
    return string(count, character);
}

void section(const string& title) {
    cout << "\n" << repeat('=', 78) << "\n";
    cout << title << "\n";
    cout << repeat('=', 78) << "\n";
}

// ---------------------------------------------------------------------------
// Repository data model
// ---------------------------------------------------------------------------

enum class FileState {
    Untracked,
    Clean,
    Modified,
    Staged
};

string stateName(FileState state) {
    switch (state) {
        case FileState::Untracked:
            return "untracked";
        case FileState::Clean:
            return "clean";
        case FileState::Modified:
            return "modified";
        case FileState::Staged:
            return "staged";
    }

    return "unknown";
}

struct FileRecord {
    string path;
    string workingContent;
    string committedContent;
    string stagedContent;
    FileState state = FileState::Untracked;
};

struct Commit {
    string id;
    string message;
    string author;
    vector<string> parents;
    map<string, string> snapshot;
};

struct RemoteRepository {
    string name;
    map<string, Commit> commits;
    string branchName = "main";
    optional<string> headCommit;
};

class GitSimulationError : public runtime_error {
public:
    explicit GitSimulationError(const string& message)
        : runtime_error(message) {}
};

// ---------------------------------------------------------------------------
// Repository class
// ---------------------------------------------------------------------------

class Repository {
private:
    string repositoryName;
    string currentBranch = "main";

    map<string, FileRecord> files;
    map<string, Commit> commits;

    optional<string> headCommit;

    /*
     * staging contains file paths selected for the next commit.
     *
     * The actual staged contents live in FileRecord::stagedContent.
     */
    set<string> staging;

    /*
     * remoteBranch stores the locally known remote commit identifier.
     *
     * In a real Git repository this role is related to remote-tracking
     * references such as origin/main.
     */
    optional<string> remoteBranch;

    RemoteRepository* origin = nullptr;

    static string generateCommitId(
        const string& repositoryName,
        size_t commitNumber,
        const string& message
    ) {
        /*
         * This is intentionally not a cryptographic hash. It is a deterministic
         * simulation identifier for the educational model.
         */
        hash<string> hasher;

        size_t value = hasher(
            repositoryName
            + ":"
            + to_string(commitNumber)
            + ":"
            + message
        );

        ostringstream output;
        output << hex << value;

        return output.str().substr(0, 10);
    }

    map<string, string> buildSnapshot() const {
        map<string, string> snapshot;

        for (const auto& [path, record] : files) {
            if (record.state != FileState::Untracked) {
                snapshot[path] = record.workingContent;
            }
        }

        return snapshot;
    }

    bool hasCommit(const string& id) const {
        return commits.find(id) != commits.end();
    }

    bool remoteHasCommit(const string& id) const {
        if (!origin) {
            return false;
        }

        return origin->commits.find(id) != origin->commits.end();
    }

    bool isAncestor(
        const string& possibleAncestor,
        const string& descendant
    ) const {
        if (possibleAncestor == descendant) {
            return true;
        }

        auto iterator = commits.find(descendant);

        if (iterator == commits.end()) {
            return false;
        }

        for (const string& parent : iterator->second.parents) {
            if (isAncestor(possibleAncestor, parent)) {
                return true;
            }
        }

        return false;
    }

    bool remoteIsAncestorOfLocal() const {
        if (!origin || !remoteBranch || !headCommit) {
            return false;
        }

        if (*remoteBranch == *headCommit) {
            return true;
        }

        /*
         * In the simulation, the local commit graph may not contain a remote
         * commit until pull. A common push scenario can therefore be evaluated
         * by comparing the remote head against the local ancestry when the
         * object is available locally.
         */
        return hasCommit(*remoteBranch)
            && isAncestor(*remoteBranch, *headCommit);
    }

public:
    explicit Repository(string name)
        : repositoryName(std::move(name)) {}

    const string& name() const {
        return repositoryName;
    }

    const string& branch() const {
        return currentBranch;
    }

    void init() {
        section("git init");

        cout << "Initializing repository: " << repositoryName << "\n";
        cout << "A new local repository is now available.\n";
        cout << "Current branch: " << currentBranch << "\n";
        cout << "Initial HEAD: none\n";
    }

    void createFile(const string& path, const string& content) {
        if (path.empty()) {
            throw GitSimulationError("A file path cannot be empty.");
        }

        if (files.find(path) != files.end()) {
            throw GitSimulationError(
                "File already exists: " + path
            );
        }

        FileRecord record;
        record.path = path;
        record.workingContent = content;
        record.state = FileState::Untracked;

        files[path] = record;
    }

    void modifyFile(const string& path, const string& newContent) {
        auto iterator = files.find(path);

        if (iterator == files.end()) {
            throw GitSimulationError(
                "Cannot modify missing file: " + path
            );
        }

        FileRecord& record = iterator->second;

        record.workingContent = newContent;

        if (record.state != FileState::Staged) {
            record.state = FileState::Modified;
        }
    }

    void status() const {
        cout << "\nRepository: " << repositoryName << "\n";
        cout << "Branch: " << currentBranch << "\n";

        if (headCommit) {
            cout << "HEAD: " << *headCommit << "\n";
        } else {
            cout << "HEAD: no commits yet\n";
        }

        cout << "\nFile status:\n";

        if (files.empty()) {
            cout << "  Working tree is empty.\n";
            return;
        }

        for (const auto& [path, record] : files) {
            cout << "  "
                 << left
                 << setw(28)
                 << path
                 << stateName(record.state)
                 << "\n";
        }

        if (staging.empty()) {
            cout << "\nStaging area: empty\n";
        } else {
            cout << "\nStaging area:\n";

            for (const string& path : staging) {
                cout << "  " << path << "\n";
            }
        }
    }

    void add(const vector<string>& paths) {
        if (paths.empty()) {
            throw GitSimulationError(
                "git add requires at least one path."
            );
        }

        for (const string& path : paths) {
            auto iterator = files.find(path);

            if (iterator == files.end()) {
                throw GitSimulationError(
                    "Path does not exist: " + path
                );
            }

            FileRecord& record = iterator->second;

            /*
             * git add captures the current working-tree contents in the
             * staging area. If the file is modified again later, the newer
             * working-tree version can differ from the staged snapshot.
             */
            record.stagedContent = record.workingContent;
            record.state = FileState::Staged;

            staging.insert(path);
        }

        cout << "Staged: " << join(paths, ", ") << "\n";
    }

    string commit(
        const string& message,
        const string& author
    ) {
        if (message.empty()) {
            throw GitSimulationError(
                "A commit message cannot be empty."
            );
        }

        if (author.empty()) {
            throw GitSimulationError(
                "An author is required for a commit."
            );
        }

        if (staging.empty()) {
            throw GitSimulationError(
                "Nothing is staged for commit."
            );
        }

        Commit newCommit;

        newCommit.message = message;
        newCommit.author = author;

        if (headCommit) {
            newCommit.parents.push_back(*headCommit);
        }

        newCommit.id = generateCommitId(
            repositoryName,
            commits.size() + 1,
            message
        );

        /*
         * Start with the previous snapshot when one exists.
         */
        if (headCommit) {
            newCommit.snapshot =
                commits.at(*headCommit).snapshot;
        }

        /*
         * Replace the staged paths with their staged contents.
         */
        for (const string& path : staging) {
            newCommit.snapshot[path] =
                files.at(path).stagedContent;
        }

        commits[newCommit.id] = newCommit;
        headCommit = newCommit.id;

        /*
         * After a successful commit, the working tree content represented by
         * the staged version becomes the committed version.
         */
        for (const string& path : staging) {
            FileRecord& record = files.at(path);

            record.committedContent = record.stagedContent;
            record.state = FileState::Clean;
        }

        staging.clear();

        cout << "Created commit "
             << newCommit.id
             << ": "
             << message
             << "\n";

        return newCommit.id;
    }

    void log() const {
        cout << "\nCommit history:\n";

        if (!headCommit) {
            cout << "  No commits.\n";
            return;
        }

        optional<string> current = headCommit;

        while (current) {
            const Commit& commit = commits.at(*current);

            cout << "  "
                 << commit.id
                 << "  "
                 << commit.message
                 << "  ["
                 << commit.author
                 << "]\n";

            if (commit.parents.empty()) {
                current.reset();
            } else {
                current = commit.parents.front();
            }
        }
    }

    void addRemote(RemoteRepository& remote) {
        origin = &remote;

        cout << "Remote 'origin' configured for repository '"
             << repositoryName
             << "'.\n";
    }

    void push() {
        if (!origin) {
            throw GitSimulationError(
                "No remote named origin is configured."
            );
        }

        if (!headCommit) {
            throw GitSimulationError(
                "Cannot push because the local repository has no commits."
            );
        }

        if (origin->headCommit) {
            /*
             * A remote branch with a different tip can reject a push when
             * the local history does not contain the remote tip.
             */
            const string& remoteHead = *origin->headCommit;

            if (remoteHead != *headCommit) {
                if (!hasCommit(remoteHead)
                    || !isAncestor(remoteHead, *headCommit)) {
                    throw GitSimulationError(
                        "Push rejected: non-fast-forward update."
                    );
                }
            }
        }

        origin->commits = commits;
        origin->headCommit = headCommit;
        origin->branchName = currentBranch;

        remoteBranch = headCommit;

        cout << "Push successful.\n";
        cout << "Remote branch: "
             << origin->branchName
             << "\n";
        cout << "Remote HEAD: "
             << *origin->headCommit
             << "\n";
    }

    void pull() {
        if (!origin) {
            throw GitSimulationError(
                "No remote named origin is configured."
            );
        }

        if (!origin->headCommit) {
            cout << "Remote has no commits.\n";
            return;
        }

        const string remoteHead = *origin->headCommit;

        /*
         * If the local repository has no commits, clone the remote history.
         */
        if (!headCommit) {
            commits = origin->commits;
            headCommit = remoteHead;
            remoteBranch = remoteHead;

            for (auto& [path, record] : files) {
                auto snapshotIterator =
                    commits.at(remoteHead).snapshot.find(path);

                if (snapshotIterator !=
                    commits.at(remoteHead).snapshot.end()) {

                    record.workingContent =
                        snapshotIterator->second;

                    record.committedContent =
                        snapshotIterator->second;

                    record.state = FileState::Clean;
                }
            }

            cout << "Pull completed from an empty local branch.\n";
            return;
        }

        if (*headCommit == remoteHead) {
            remoteBranch = remoteHead;

            cout << "Already up to date.\n";
            return;
        }

        /*
         * Fast-forward case.
         *
         * In a production Git implementation, pulling can also perform a
         * merge or rebase. This case study first demonstrates the simplest
         * synchronization case: the local branch has no divergent commits.
         */
        const auto remoteCommitIterator =
            origin->commits.find(remoteHead);

        if (remoteCommitIterator == origin->commits.end()) {
            throw GitSimulationError(
                "Remote HEAD object is unavailable."
            );
        }

        const Commit& remoteCommit =
            remoteCommitIterator->second;

        bool localContainsRemoteParent = false;

        if (!remoteCommit.parents.empty()) {
            localContainsRemoteParent =
                hasCommit(remoteCommit.parents.front())
                && isAncestor(
                    remoteCommit.parents.front(),
                    *headCommit
                );
        }

        if (localContainsRemoteParent) {
            commits = origin->commits;
            headCommit = remoteHead;
            remoteBranch = remoteHead;

            /*
             * Update the working tree to the pulled snapshot.
             */
            for (auto& [path, record] : files) {
                auto snapshotIterator =
                    remoteCommit.snapshot.find(path);

                if (snapshotIterator != remoteCommit.snapshot.end()) {
                    record.workingContent =
                        snapshotIterator->second;

                    record.committedContent =
                        snapshotIterator->second;

                    record.state = FileState::Clean;
                }
            }

            /*
             * Create records for files that exist remotely but not locally.
             */
            for (const auto& [path, content] :
                 remoteCommit.snapshot) {

                if (files.find(path) == files.end()) {
                    FileRecord record;

                    record.path = path;
                    record.workingContent = content;
                    record.committedContent = content;
                    record.state = FileState::Clean;

                    files[path] = record;
                }
            }

            cout << "Pull completed using fast-forward.\n";
            return;
        }

        throw GitSimulationError(
            "Pull requires history integration; this simulation does not "
            "automatically resolve a divergent merge."
        );
    }

    Repository cloneFrom(
        const string& newName,
        RemoteRepository& remote
    ) const {
        Repository cloned(newName);

        cloned.origin = &remote;
        cloned.currentBranch = remote.branchName;
        cloned.commits = remote.commits;
        cloned.headCommit = remote.headCommit;
        cloned.remoteBranch = remote.headCommit;

        if (remote.headCommit) {
            const Commit& latest =
                remote.commits.at(*remote.headCommit);

            for (const auto& [path, content] :
                 latest.snapshot) {

                FileRecord record;

                record.path = path;
                record.workingContent = content;
                record.committedContent = content;
                record.state = FileState::Clean;

                cloned.files[path] = record;
            }
        }

        return cloned;
    }

    const optional<string>& head() const {
        return headCommit;
    }

    size_t commitCount() const {
        return commits.size();
    }
};

// ---------------------------------------------------------------------------
// Case-study scenario
// ---------------------------------------------------------------------------

void basicDevelopmentScenario() {
    section("1. Case study: Incident Analytics repository");

    cout << R"(
Scenario
--------
A small engineering team is developing an internal Incident Analytics
application. The application contains:

    README.md
    src/main.cpp
    config/application.conf

The team needs a repeatable workflow for:

    - creating the repository,
    - inspecting changes,
    - staging selected files,
    - committing logical changes,
    - publishing commits,
    - cloning the project,
    - receiving later changes with pull.

The simulation below models those operations as repository state transitions.
)" << "\n";

    Repository repository("incident-analytics");

    repository.init();

    repository.createFile(
        "README.md",
        "# Incident Analytics\n"
    );

    repository.createFile(
        "src/main.cpp",
        "int main() { return 0; }\n"
    );

    repository.createFile(
        "config/application.conf",
        "environment=development\n"
    );

    repository.status();

    section("2. Stage selected project files");

    /*
     * The team intentionally stages the README and source file first.
     * This demonstrates that git add can select only part of the working
     * tree instead of committing every changed file automatically.
     */
    repository.add({
        "README.md",
        "src/main.cpp"
    });

    repository.status();

    section("3. Commit staged work");

    repository.commit(
        "Create initial Incident Analytics structure",
        "Atul Developer"
    );

    repository.status();
    repository.log();

    section("4. Modify an existing file");

    repository.modifyFile(
        "src/main.cpp",
        R"(#include <iostream>

int main() {
    std::cout << "Incident Analytics started\n";
    return 0;
}
)"
    );

    repository.status();

    section("5. Stage and commit the application change");

    repository.add({"src/main.cpp"});

    repository.commit(
        "Add application startup behavior",
        "Atul Developer"
    );

    repository.log();
}

// ---------------------------------------------------------------------------
// Remote publishing scenario
// ---------------------------------------------------------------------------

void remoteWorkflowScenario() {
    section("6. Remote workflow: push and clone");

    RemoteRepository githubLikeRemote;
    githubLikeRemote.name = "origin";
    githubLikeRemote.branchName = "main";

    Repository developer("incident-analytics-local");

    developer.init();

    developer.createFile(
        "README.md",
        "# Incident Analytics\n"
    );

    developer.createFile(
        "src/main.cpp",
        "int main() { return 0; }\n"
    );

    developer.add({
        "README.md",
        "src/main.cpp"
    });

    developer.commit(
        "Create project foundation",
        "Developer A"
    );

    developer.addRemote(githubLikeRemote);

    cout << "\nPublishing the initial commit:\n";
    developer.push();

    cout << "\nRemote repository now contains "
         << githubLikeRemote.commits.size()
         << " commit(s).\n";

    section("7. Clone the remote repository");

    Repository cloned =
        developer.cloneFrom(
            "incident-analytics-clone",
            githubLikeRemote
        );

    cloned.status();
    cloned.log();

    cout << R"(
Clone behavior
--------------
A clone creates a new local repository containing the remote history and
working-tree files.

The clone normally also receives a remote configuration named origin.

This is different from git init:

    init
        Create a new repository here.

    clone
        Create a new local copy from an existing repository.
)" << "\n";

    section("8. Developer A publishes another change");

    developer.modifyFile(
        "README.md",
        "# Incident Analytics\n\n"
        "Internal event analysis platform.\n"
    );

    developer.add({"README.md"});

    developer.commit(
        "Document the project purpose",
        "Developer A"
    );

    developer.push();

    cout << "\nRemote HEAD after Developer A push: "
         << *githubLikeRemote.headCommit
         << "\n";

    section("9. Clone pulls the new commit");

    /*
     * The clone's local commit graph currently contains the previous commit.
     * Pull sees the remote's newer commit and fast-forwards the local branch.
     */
    cloned.pull();

    cloned.status();
    cloned.log();
}

// ---------------------------------------------------------------------------
// Staging edge case
// ---------------------------------------------------------------------------

void stagingEdgeCaseScenario() {
    section("10. Edge case: staged content versus working-tree content");

    Repository repository("staging-edge-case");

    repository.init();

    repository.createFile(
        "notes.txt",
        "Line 1\n"
    );

    repository.add({"notes.txt"});

    repository.commit(
        "Create notes",
        "Developer B"
    );

    repository.modifyFile(
        "notes.txt",
        "Line 1\nLine 2\n"
    );

    repository.add({"notes.txt"});

    /*
     * The file is staged at the Line 2 version.
     *
     * It is then modified again before commit. The simulation changes the
     * working tree but preserves the staged snapshot.
     *
     * This is one of the most important behaviors for understanding why
     * git status can report staged and unstaged changes simultaneously.
     */
    repository.modifyFile(
        "notes.txt",
        "Line 1\nLine 2\nLine 3\n"
    );

    repository.status();

    cout << R"(
Interpretation
--------------
The staged version contains:

    Line 1
    Line 2

The working tree contains:

    Line 1
    Line 2
    Line 3

Therefore, committing immediately would record the staged snapshot rather
than automatically including the newer unstaged Line 3 change.
)" << "\n";
}

// ---------------------------------------------------------------------------
// Non-fast-forward scenario
// ---------------------------------------------------------------------------

void nonFastForwardScenario() {
    section("11. Edge case: non-fast-forward push");

    RemoteRepository remote;
    remote.name = "origin";
    remote.branchName = "main";

    Repository developerA("developer-a");
    developerA.init();

    developerA.createFile(
        "shared.txt",
        "Initial shared content\n"
    );

    developerA.add({"shared.txt"});

    developerA.commit(
        "Create shared file",
        "Developer A"
    );

    developerA.addRemote(remote);
    developerA.push();

    /*
     * Developer B clones the remote at the same point in history.
     */
    Repository developerB =
        developerA.cloneFrom(
            "developer-b",
            remote
        );

    /*
     * Developer A publishes another commit.
     */
    developerA.modifyFile(
        "shared.txt",
        "Initial shared content\n"
        "Change from Developer A\n"
    );

    developerA.add({"shared.txt"});

    developerA.commit(
        "Update shared file from A",
        "Developer A"
    );

    developerA.push();

    /*
     * Developer B has not pulled A's new commit. B creates a local commit
     * from the old history and attempts to push.
     */
    developerB.modifyFile(
        "shared.txt",
        "Initial shared content\n"
        "Change from Developer B\n"
    );

    developerB.add({"shared.txt"});

    developerB.commit(
        "Update shared file from B",
        "Developer B"
    );

    cout << R"(
Developer B now has a local commit based on an older remote state.

Attempting to push such divergent history should not silently replace the
remote branch. A real Git server normally rejects the push as
non-fast-forward.
)" << "\n";

    try {
        developerB.push();
    } catch (const GitSimulationError& error) {
        cout << "\nExpected failure:\n";
        cout << error.what() << "\n";
    }

    cout << R"(
The correct engineering response depends on the team's workflow, but the
essential sequence is:

    inspect the remote changes
    synchronize the local repository
    integrate the histories
    resolve conflicts if necessary
    test the result
    push the integrated history

This simulation deliberately does not invent an automatic conflict
resolution policy.
)" << "\n";
}

// ---------------------------------------------------------------------------
// Complexity and design analysis
// ---------------------------------------------------------------------------

void complexityAnalysis() {
    section("12. Complexity and implementation analysis");

    cout << R"(
Repository lookup
-----------------
The simulation stores files in std::map.

Lookup:
    O(log F)

Insertion:
    O(log F)

where F is the number of tracked files.

The staging set also uses an ordered std::set:

    insertion: O(log S)
    lookup:    O(log S)

where S is the number of staged paths.

Commit snapshot
---------------
The simulation uses std::map for snapshots. Building a snapshot is
approximately:

    O(F log F)

for F tracked files in the ordered representation.

Commit history
--------------
The demonstration follows the first parent of each commit. For a linear
history containing C commits, log traversal is approximately:

    O(C)

Real Git uses specialized storage structures and content-addressed objects
rather than this simplified in-memory model.

Push
----
The simulated push checks whether the remote tip is compatible with the
local history. Real Git performs considerably more sophisticated object
negotiation, reachability analysis, pack generation, and transport.

Pull
----
The case study demonstrates a fast-forward pull and deliberately rejects
unhandled divergent histories rather than pretending that merge conflict
resolution is trivial.

Design trade-offs
-----------------
std::map:
    Predictable ordered behavior and logarithmic lookup.

std::unordered_map:
    Average constant-time lookup, but without ordering.

std::set:
    Useful when unique staged paths and ordered traversal are desirable.

vector:
    Useful for ordered sequences such as commit parent lists.

optional:
    Explicitly represents states such as "repository has no HEAD commit".
)" << "\n";
}

// ---------------------------------------------------------------------------
// Security and production considerations
// ---------------------------------------------------------------------------

void securityConsiderations() {
    section("13. Security and production considerations");

    cout << R"(
1. Never commit secrets
   Passwords, API keys, access tokens, private certificates, and private keys
   should not be stored in source control.

2. .gitignore is not a security boundary
   A .gitignore rule prevents intended tracking of matching files, but it
   does not remove a secret that has already been staged or committed.

3. History matters
   Removing a secret from the latest commit does not necessarily remove it
   from older commits.

4. Push permissions matter
   A local commit can be created without permission to publish it. Remote
   authorization is a separate concern.

5. Review before push
   git status, git diff, and appropriate repository review mechanisms help
   identify accidental changes.

6. Protected branches
   Hosted Git services can require reviews, checks, or other conditions
   before changes reach protected branches.

7. Reproducibility
   Commit history should contain meaningful, reviewable changes. Very large
   unrelated commits make debugging and review harder.

8. Conflict resolution
   A conflict should be resolved based on the intended application behavior,
   not merely by choosing one side mechanically.

9. Backup expectations
   A local commit is not a remote backup until it has been successfully
   transferred to an appropriate remote repository.

10. Authentication credentials
    SSH keys, tokens, and credential helpers should be managed outside the
    source files being committed.
)" << "\n";
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    try {
        section("GIT COMMANDS CASE STUDY");

        cout << R"(
Topic:
    git init
    git clone
    git status
    git add
    git commit
    git push
    git pull

Scenario:
    An engineering team maintains an Incident Analytics application using
    Git for local version control and remote collaboration.
)" << "\n";

        basicDevelopmentScenario();
        remoteWorkflowScenario();
        stagingEdgeCaseScenario();
        nonFastForwardScenario();
        complexityAnalysis();
        securityConsiderations();

        section("14. Case study completed");

        cout << R"(
The case study demonstrated:

    init
        Repository creation.

    clone
        Creation of a working copy from an existing remote.

    status
        Inspection of working-tree and staging state.

    add
        Selection of content for the next commit.

    commit
        Creation of local project history.

    push
        Publication of compatible local history to a remote.

    pull
        Synchronization and fast-forward integration of remote history.

The simulation also demonstrated why the separation between working tree,
staging area, local repository, and remote repository is central to
understanding Git.
)" << "\n";

        return 0;
    } catch (const GitSimulationError& error) {
        cerr << "\nGit simulation error: "
             << error.what()
             << "\n";

        return 1;
    } catch (const exception& error) {
        cerr << "\nUnexpected error: "
             << error.what()
             << "\n";

        return 2;
    }
}

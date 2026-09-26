/*
 * Git Advanced: rebase, cherry-pick, stash, and reflog
 * =====================================================
 *
 * C++17 industry-style case study:
 *
 * A release engineering utility manages a software project's release branch.
 * The utility uses Git commands through std::system-like process execution
 * provided by portable standard-library facilities through temporary shell
 * command construction.
 *
 * The case study demonstrates:
 *
 *   - repository initialization
 *   - commits and branches
 *   - feature integration with rebase
 *   - selective release fixes with cherry-pick
 *   - temporary work preservation with stash
 *   - recovery analysis using reflog
 *   - validation and error handling
 *   - command-result checking
 *   - modular C++ design
 *   - complexity and operational trade-offs
 *
 * Compile:
 *
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic git_advanced.cpp -o git_advanced
 *
 * Run:
 *
 *   ./git_advanced
 *
 * Git must be installed and available on PATH.
 */

#include <array>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;


// ---------------------------------------------------------------------------
// SECTION 1: PROCESS EXECUTION
// ---------------------------------------------------------------------------

struct CommandResult {
    int exitCode{};
    std::string command;
};


class GitException : public std::runtime_error {
public:
    explicit GitException(const std::string& message)
        : std::runtime_error(message) {}
};


/*
 * This case study uses std::system for portability across standard C++17
 * environments. The command strings are generated internally and use
 * repository paths created by the program itself.
 *
 * A production application accepting arbitrary user input should avoid
 * constructing shell commands from untrusted strings. A platform-specific
 * process API or a carefully designed subprocess library is preferable for
 * untrusted input.
 */
CommandResult runCommand(
    const fs::path& workingDirectory,
    const std::string& command,
    bool allowFailure = false
) {
    std::ostringstream fullCommand;

#ifdef _WIN32
    fullCommand << "cd /d \"" << workingDirectory.string()
                << "\" && " << command;
#else
    fullCommand << "cd \"" << workingDirectory.string()
                << "\" && " << command;
#endif

    const std::string commandText = fullCommand.str();
    const int exitCode = std::system(commandText.c_str());

    if (exitCode != 0 && !allowFailure) {
        throw GitException(
            "Command failed with exit code " +
            std::to_string(exitCode) +
            ": " +
            commandText
        );
    }

    return {exitCode, commandText};
}


void runGit(
    const fs::path& repo,
    const std::string& arguments
) {
    runCommand(repo, "git " + arguments);
}


void printCommand(
    const fs::path& repo,
    const std::string& arguments
) {
    std::cout << "\n$ git " << arguments << "\n";
    runGit(repo, arguments);
}


// ---------------------------------------------------------------------------
// SECTION 2: OUTPUT AND FILE UTILITIES
// ---------------------------------------------------------------------------

void section(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}


void subsection(const std::string& title) {
    std::cout << "\n" << std::string(70, '-') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(70, '-') << "\n";
}


void writeFile(
    const fs::path& repo,
    const std::string& filename,
    const std::string& content
) {
    const fs::path filePath = repo / filename;

    if (filePath.has_parent_path()) {
        fs::create_directories(filePath.parent_path());
    }

    std::ofstream output(filePath);

    if (!output) {
        throw std::runtime_error(
            "Unable to write file: " + filePath.string()
        );
    }

    output << content;
}


void appendFile(
    const fs::path& repo,
    const std::string& filename,
    const std::string& content
) {
    std::ofstream output(repo / filename, std::ios::app);

    if (!output) {
        throw std::runtime_error(
            "Unable to append file: " + (repo / filename).string()
        );
    }

    output << content;
}


fs::path createTemporaryRepository() {
    const auto timestamp =
        std::chrono::high_resolution_clock::now()
            .time_since_epoch()
            .count();

    const fs::path repository =
        fs::temp_directory_path() /
        ("git-advanced-cpp-" + std::to_string(timestamp));

    fs::create_directories(repository);

    runGit(repository, "init -b main");

    runGit(
        repository,
        "config user.name \"Git Advanced C++ Case Study\""
    );

    runGit(
        repository,
        "config user.email \"cpp-git-study@example.invalid\""
    );

    writeFile(
        repository,
        "service.txt",
        "service version 1\n"
    );

    writeFile(
        repository,
        "README.txt",
        "Release engineering case study\n"
    );

    runGit(repository, "add .");
    runGit(repository, "commit -m \"Initial release project\"");

    return repository;
}


// ---------------------------------------------------------------------------
// SECTION 3: ARCHITECTURAL MODEL
// ---------------------------------------------------------------------------

class ReleaseRepository {
private:
    fs::path repositoryPath;

public:
    explicit ReleaseRepository(fs::path path)
        : repositoryPath(std::move(path)) {}

    const fs::path& path() const {
        return repositoryPath;
    }

    void status() const {
        printCommand(repositoryPath, "status --short --branch");
    }

    void graph() const {
        printCommand(
            repositoryPath,
            "log --graph --oneline --decorate --all"
        );
    }

    void switchBranch(const std::string& branch) const {
        runGit(
            repositoryPath,
            "switch " + branch
        );
    }

    void createBranch(const std::string& branch) const {
        runGit(
            repositoryPath,
            "switch -c " + branch
        );
    }

    void commit(const std::string& message) const {
        runGit(repositoryPath, "add .");

        /*
         * Messages in this controlled case study are internal constants.
         * Production code receiving arbitrary commit messages should escape
         * arguments safely or use a subprocess API with argument arrays.
         */
        runGit(
            repositoryPath,
            "commit -m \"" + message + "\""
        );
    }

    void rebaseOnto(const std::string& base) const {
        runGit(
            repositoryPath,
            "rebase " + base
        );
    }

    void cherryPick(const std::string& commit) const {
        runGit(
            repositoryPath,
            "cherry-pick " + commit
        );
    }

    void stash(const std::string& message) const {
        runGit(
            repositoryPath,
            "stash push -u -m \"" + message + "\""
        );
    }

    void stashList() const {
        printCommand(repositoryPath, "stash list");
    }

    void reflog() const {
        printCommand(repositoryPath, "reflog --oneline -15");
    }

    void resetHard(const std::string& reference) const {
        runGit(
            repositoryPath,
            "reset --hard " + reference
        );
    }
};


// ---------------------------------------------------------------------------
// SECTION 4: BUSINESS SCENARIO
// ---------------------------------------------------------------------------

void explainScenario() {
    section("1. Release Engineering Case Study");

    std::cout << R"(
Scenario
--------
A software organization maintains a main branch and a release branch.

Three operational problems occur:

1. Developers need to keep a feature branch synchronized with main without
   introducing unnecessary merge commits.

2. A critical security or validation fix exists on one branch but must be
   transferred selectively to the release line.

3. A developer is interrupted by urgent release work while carrying unfinished
   local changes.

A final recovery exercise demonstrates how reflog can help locate a previous
reference position after an accidental reset.

The utility therefore models four complementary Git mechanisms:

    rebase       -> synchronize and rewrite a feature line
    cherry-pick  -> selectively transfer a fix
    stash        -> temporarily preserve unfinished work
    reflog       -> investigate local reference movement
)";
}


// ---------------------------------------------------------------------------
// SECTION 5: REBASE WORKFLOW
// ---------------------------------------------------------------------------

void demonstrateRebaseWorkflow(ReleaseRepository& repository) {
    section("2. Feature Synchronization with Rebase");

    std::cout << R"(
Initial conceptual history:

    A ---------------- M1             main
     \
      F1 ----------- F2               feature

Rebase transforms the feature history conceptually into:

    A ---------------- M1 --- F1' --- F2'     feature

F1' and F2' are new commits. The original F1 and F2 are not modified in
place. Git creates new commits whose parent relationship starts from M1.
)";

    repository.createBranch("feature/reporting");

    writeFile(
        repository.path(),
        "reporting.txt",
        "reporting engine\n"
    );

    repository.commit("Add reporting engine");

    appendFile(
        repository.path(),
        "reporting.txt",
        "report validation\n"
    );

    repository.commit("Add report validation");

    repository.switchBranch("main");

    appendFile(
        repository.path(),
        "service.txt",
        "main service optimization\n"
    );

    repository.commit("Optimize main service");

    repository.switchBranch("feature/reporting");

    repository.rebaseOnto("main");

    subsection("Resulting history");

    repository.graph();

    subsection("Conflict handling");

    std::cout << R"(
If a rebase encounters a conflict, the correct operational sequence is:

    git status
    resolve conflicted files
    git add <resolved-files>
    git rebase --continue

If the entire operation should be abandoned:

    git rebase --abort

If the current patch needs inspection:

    git rebase --show-current-patch

A release engineering utility should never automatically resolve arbitrary
source conflicts because semantic correctness cannot be inferred safely from
exit status alone.
)";
}


// ---------------------------------------------------------------------------
// SECTION 6: CHERRY-PICK WORKFLOW
// ---------------------------------------------------------------------------

void demonstrateCherryPickWorkflow(ReleaseRepository& repository) {
    section("3. Selective Release Fix with Cherry-pick");

    /*
     * The source branch represents development where a critical fix is
     * implemented independently of unrelated feature work.
     */
    repository.switchBranch("main");
    repository.createBranch("feature/critical-fix");

    writeFile(
        repository.path(),
        "input_validation.txt",
        "reject malformed production input\n"
    );

    repository.commit("Fix production input validation");

    /*
     * Obtain the source commit through a Git-generated shell expression.
     * In this controlled educational repository, the value is used only as a
     * Git revision argument.
     */
    runCommand(
        repository.path(),
        "git rev-parse --short HEAD"
    );

    /*
     * Return to main and create unrelated release preparation work.
     */
    repository.switchBranch("main");

    writeFile(
        repository.path(),
        "release-notes.txt",
        "Release preparation\n"
    );

    repository.commit("Prepare release notes");

    std::cout << R"(
The critical fix now exists on feature/critical-fix but not on main.

The release branch can selectively apply that change using:

    git cherry-pick <fix-commit>

The source branch remains intact. The target branch receives a new commit
representing the selected change.
)";

    /*
     * The demonstration uses a symbolic revision that Git resolves to the
     * previous feature tip. The commit is known by topology:
     *
     * main:
     *   ... --- release preparation
     *
     * feature/critical-fix:
     *   ... --- critical fix
     *
     * Because main was created before the feature commit, the feature commit
     * can be referenced as feature/critical-fix.
     */
    repository.cherryPick("feature/critical-fix");

    repository.graph();

    subsection("Cherry-pick conflict model");

    std::cout << R"(
A cherry-pick conflict means the selected patch cannot be cleanly applied to
the current target.

Normal resolution:

    git status
    resolve the files
    git add <resolved-files>
    git cherry-pick --continue

Abort:

    git cherry-pick --abort

Skip an empty or intentionally unnecessary selected commit:

    git cherry-pick --skip

A successful cherry-pick does not prove semantic correctness. Tests and
review are still required.
)";
}


// ---------------------------------------------------------------------------
// SECTION 7: STASH WORKFLOW
// ---------------------------------------------------------------------------

void demonstrateStashWorkflow(ReleaseRepository& repository) {
    section("4. Interrupting Work with Stash");

    repository.switchBranch("main");

    appendFile(
        repository.path(),
        "service.txt",
        "unfinished developer change\n"
    );

    writeFile(
        repository.path(),
        "unfinished.txt",
        "draft implementation\n"
    );

    repository.status();

    repository.stash(
        "WIP: unfinished service implementation"
    );

    subsection("Clean state after stash");

    repository.status();

    repository.stashList();

    std::cout << R"(
The stash now contains unfinished work.

Two important commands behave differently:

    git stash apply
        Restores the changes and keeps the stash entry.

    git stash pop
        Restores the changes and normally removes the entry.

For cautious recovery, `apply` can be preferable because the original stash
remains available while the result is inspected.
)";

    subsection("Untracked files");

    writeFile(
        repository.path(),
        "tracked-example.txt",
        "tracked example\n"
    );

    repository.commit("Add stash demonstration file");

    appendFile(
        repository.path(),
        "tracked-example.txt",
        "unfinished modification\n"
    );

    writeFile(
        repository.path(),
        "untracked-example.txt",
        "untracked release work\n"
    );

    repository.status();

    /*
     * -u includes untracked files.
     *
     * Ignored files require -a, which should be used carefully because
     * generated artifacts can be large.
     */
    repository.stash(
        "WIP: tracked and untracked release work"
    );

    repository.stashList();

    std::cout << R"(
Stash is appropriate for short-lived interruption management. It is not a
substitute for durable commits when the work has meaningful historical value.
)";
}


// ---------------------------------------------------------------------------
// SECTION 8: REFLOG RECOVERY WORKFLOW
// ---------------------------------------------------------------------------

void demonstrateReflogWorkflow(ReleaseRepository& repository) {
    section("5. Recovery Investigation with Reflog");

    writeFile(
        repository.path(),
        "recoverable-change.txt",
        "important local change\n"
    );

    repository.commit("Create recoverable change");

    repository.reflog();

    subsection("Simulated accidental reset");

    writeFile(
        repository.path(),
        "accidental-change.txt",
        "change that will be hidden by reset\n"
    );

    repository.commit("Create accidental reset target");

    std::cout << R"(
Before the reset, HEAD points to the latest commit.

An accidental command such as:

    git reset --hard HEAD~1

moves the current branch reference backward.

The commit is no longer the current branch tip, but its previous reference
position is commonly visible through:

    git reflog

)";
    
    repository.resetHard("HEAD~1");

    subsection("Inspect current history");

    repository.graph();

    subsection("Inspect reflog");

    repository.reflog();

    std::cout << R"(
Recovery procedure:

1. Inspect the reflog.
2. Identify the previous commit.
3. Verify it with git show.
4. Create a recovery branch first when practical:

       git switch -c recovery <commit>

5. After verification, decide whether an existing branch should be moved.

This illustrates why reflog is different from normal history inspection.

git log asks:
    "Which commits are reachable from this reference?"

git reflog asks:
    "Where has this local reference pointed recently?"

Reflog is local and subject to expiration. It is therefore a recovery aid,
not a replacement for backups or remote repository copies.
)";
}


// ---------------------------------------------------------------------------
// SECTION 9: DESIGN AND COMPLEXITY
// ---------------------------------------------------------------------------

void explainDesignAndComplexity() {
    section("6. Algorithms, Complexity, and Design Trade-offs");

    std::cout << R"(
REBASE
------
If N commits are replayed, the conceptual work is proportional to the number
of commits and the cost of applying their patches.

A simplified model is:

    O(N + P)

where P represents the total size/complexity of the patches Git must process.
Conflict resolution can dominate human effort.

CHERRY-PICK
----------
For K selected commits, the operation is roughly proportional to the work
required to apply those K patches:

    O(K + P_selected)

The practical challenge is dependency correctness rather than merely runtime.

STASH
-----
Stash records a representation of changes relative to the current repository
state. Its cost depends on the amount of changed data and repository state.

REFLOG
------
Reflog inspection is primarily a reference-history lookup. The practical cost
is affected by the number of retained entries and repository metadata.

DATA STRUCTURES
---------------
Git itself uses sophisticated content-addressed objects and reference
structures internally. This C++ case study does not reimplement Git's object
database. It models Git as an external system because reimplementing Git's
storage and transfer protocols would obscure the advanced operations being
studied.

ARCHITECTURE
------------
The ReleaseRepository class centralizes Git operations. This keeps the case
study modular:

    file operations
          |
    ReleaseRepository
          |
      Git process
          |
      repository

This separation makes it easier to replace command execution with a stronger
platform-specific subprocess implementation in production software.
)";
}


// ---------------------------------------------------------------------------
// SECTION 10: SECURITY CONSIDERATIONS
// ---------------------------------------------------------------------------

void explainSecurity() {
    section("7. Security Considerations");

    std::cout << R"(
1. Never concatenate untrusted user input into shell commands.

2. This educational program uses internally controlled branch names and
   messages. A production system should pass arguments through a subprocess
   API rather than constructing shell syntax.

3. Git history can contain secrets even after a later commit deletes them.

4. If credentials are committed:
       - revoke or rotate them
       - assess exposure
       - rewrite history when required
       - coordinate cleanup of affected copies

5. Rebase and force push can rewrite shared history. Access control and branch
   protection should be part of the repository's operational design.

6. `git push --force-with-lease` is generally safer than unconditional
   `git push --force` after intentional rewriting because it checks whether
   the remote reference changed unexpectedly.

7. Stashes can contain sensitive unfinished work. Treat repository directories
   and local Git metadata as potentially sensitive.
)";
}


// ---------------------------------------------------------------------------
// SECTION 11: PRODUCTION CHECKLIST
// ---------------------------------------------------------------------------

void productionChecklist() {
    section("8. Production Checklist");

    const std::array<std::string, 12> checklist = {
        "Verify the current branch before destructive operations.",
        "Keep meaningful work in commits rather than indefinite stashes.",
        "Use focused commits when changes may need selective cherry-picking.",
        "Rebase private/local work according to team policy.",
        "Avoid rebasing shared history without explicit coordination.",
        "Use --force-with-lease instead of unconditional force when rewriting.",
        "Inspect conflicts manually rather than assuming Git chose correctly.",
        "Use reflog as a local recovery mechanism.",
        "Maintain remote backups for durable recovery.",
        "Rotate credentials that entered Git history.",
        "Validate successful Git commands by their exit status.",
        "Use safe process APIs when handling untrusted command arguments."
    };

    for (std::size_t index = 0; index < checklist.size(); ++index) {
        std::cout
            << "  "
            << (index + 1)
            << ". "
            << checklist[index]
            << "\n";
    }
}


// ---------------------------------------------------------------------------
// SECTION 12: MAIN
// ---------------------------------------------------------------------------

int main() {
    fs::path repositoryPath;

    try {
        section("Git Advanced C++ Release Engineering Utility");

        /*
         * Confirm Git exists before creating the study repository.
         */
        runCommand(
            fs::current_path(),
            "git --version"
        );

        repositoryPath = createTemporaryRepository();

        std::cout
            << "\nTemporary repository: "
            << repositoryPath.string()
            << "\n";

        ReleaseRepository repository(repositoryPath);

        explainScenario();
        demonstrateRebaseWorkflow(repository);
        demonstrateCherryPickWorkflow(repository);
        demonstrateStashWorkflow(repository);
        demonstrateReflogWorkflow(repository);
        explainDesignAndComplexity();
        explainSecurity();
        productionChecklist();

        section("Case Study Complete");

        std::cout << R"(
The implementation demonstrated:

    Rebase
        Replays a feature's commits on a different base.

    Cherry-pick
        Selectively applies a commit's change to another branch.

    Stash
        Temporarily preserves unfinished working-tree changes.

    Reflog
        Records local reference movement and assists recovery.

The temporary repository will be removed.
)";

        fs::remove_all(repositoryPath);

        return 0;
    }
    catch (const GitException& error) {
        std::cerr
            << "\nGit operation failed:\n"
            << error.what()
            << "\n";

        if (!repositoryPath.empty()) {
            fs::remove_all(repositoryPath);
        }

        return 1;
    }
    catch (const std::exception& error) {
        std::cerr
            << "\nProgram failed:\n"
            << error.what()
            << "\n";

        if (!repositoryPath.empty()) {
            fs::remove_all(repositoryPath);
        }

        return 1;
    }
}

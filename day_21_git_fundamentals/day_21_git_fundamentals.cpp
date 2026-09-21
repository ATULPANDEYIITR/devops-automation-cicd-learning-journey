```cpp
/*
 * Git Fundamentals: Repository, Working Tree, and Staging Area
 *
 * C++17 case study:
 * A small local version-control engine for a document management system.
 *
 * The program models:
 *   - a working tree
 *   - an index / staging area
 *   - commits
 *   - branches
 *   - HEAD
 *   - content-addressed objects
 *   - status and diff operations
 *   - validation and failure handling
 *   - commit history
 *
 * It intentionally uses only the C++ standard library.
 */

#include <algorithm>
#include <cstdint>
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


// ---------------------------------------------------------------------------
// 1. Utility functions
// ---------------------------------------------------------------------------

std::string repeat(char character, std::size_t count)
{
    return std::string(count, character);
}

void printSection(const std::string& title)
{
    std::cout << "\n" << repeat('=', 78) << "\n";
    std::cout << title << "\n";
    std::cout << repeat('=', 78) << "\n";
}


// ---------------------------------------------------------------------------
// 2. A deterministic educational hash
// ---------------------------------------------------------------------------

/*
 * This is not a cryptographic hash and is not intended to reproduce Git's
 * object IDs. It exists only so the case study can demonstrate the concept
 * of content-addressed identity without an external cryptography library.
 *
 * Real Git historically uses SHA-1 object IDs and also supports SHA-256
 * repositories. A production implementation must use an appropriate
 * cryptographic hash implementation rather than this teaching hash.
 */
std::string educationalHash(const std::string& input)
{
    std::uint64_t hash = 1469598103934665603ULL;

    for (unsigned char character : input)
    {
        hash ^= static_cast<std::uint64_t>(character);
        hash *= 1099511628211ULL;
    }

    std::ostringstream output;
    output << std::hex << std::setw(16) << std::setfill('0') << hash;
    return output.str();
}


// ---------------------------------------------------------------------------
// 3. File snapshot representation
// ---------------------------------------------------------------------------

using FileMap = std::map<std::string, std::string>;

struct Difference
{
    std::string path;
    std::optional<std::string> oldContent;
    std::optional<std::string> newContent;
};

std::vector<Difference> calculateDiff(
    const FileMap& oldState,
    const FileMap& newState)
{
    std::set<std::string> paths;

    for (const auto& [path, content] : oldState)
    {
        paths.insert(path);
    }

    for (const auto& [path, content] : newState)
    {
        paths.insert(path);
    }

    std::vector<Difference> differences;

    for (const auto& path : paths)
    {
        std::optional<std::string> oldContent;
        std::optional<std::string> newContent;

        if (auto iterator = oldState.find(path); iterator != oldState.end())
        {
            oldContent = iterator->second;
        }

        if (auto iterator = newState.find(path); iterator != newState.end())
        {
            newContent = iterator->second;
        }

        if (oldContent != newContent)
        {
            differences.push_back(
                {
                    path,
                    oldContent,
                    newContent
                }
            );
        }
    }

    return differences;
}

void printDiff(
    const std::vector<Difference>& differences,
    const std::string& title)
{
    std::cout << "\n" << title << "\n";

    if (differences.empty())
    {
        std::cout << "  No differences.\n";
        return;
    }

    for (const auto& difference : differences)
    {
        std::cout << "\n  File: " << difference.path << "\n";

        if (difference.oldContent.has_value())
        {
            std::cout << "    OLD: " << std::quoted(*difference.oldContent) << "\n";
        }
        else
        {
            std::cout << "    OLD: <absent>\n";
        }

        if (difference.newContent.has_value())
        {
            std::cout << "    NEW: " << std::quoted(*difference.newContent) << "\n";
        }
        else
        {
            std::cout << "    NEW: <absent>\n";
        }
    }
}


// ---------------------------------------------------------------------------
// 4. Commit representation
// ---------------------------------------------------------------------------

struct Commit
{
    std::string id;
    std::string message;
    std::vector<std::string> parents;
    FileMap tree;
};

class CommitStore
{
private:
    std::map<std::string, Commit> commits_;

public:
    std::string createCommit(
        const FileMap& tree,
        const std::string& message,
        const std::vector<std::string>& parents)
    {
        if (message.empty())
        {
            throw std::invalid_argument(
                "A commit message cannot be empty."
            );
        }

        std::ostringstream material;
        material << message << "|";

        for (const auto& parent : parents)
        {
            material << parent << "|";
        }

        for (const auto& [path, content] : tree)
        {
            material << path << "=" << content << "|";
        }

        const std::string id = educationalHash(material.str());

        commits_.emplace(
            id,
            Commit{
                id,
                message,
                parents,
                tree
            }
        );

        return id;
    }

    const Commit& get(const std::string& id) const
    {
        auto iterator = commits_.find(id);

        if (iterator == commits_.end())
        {
            throw std::out_of_range(
                "Unknown commit: " + id
            );
        }

        return iterator->second;
    }

    bool contains(const std::string& id) const
    {
        return commits_.find(id) != commits_.end();
    }

    void printHistory(const std::string& startId) const
    {
        std::string current = startId;

        while (!current.empty())
        {
            const Commit& commit = get(current);

            std::cout
                << commit.id
                << "  "
                << commit.message
                << "  parents=";

            if (commit.parents.empty())
            {
                std::cout << "none";
            }
            else
            {
                std::cout << "[";

                for (std::size_t index = 0;
                     index < commit.parents.size();
                     ++index)
                {
                    if (index > 0)
                    {
                        std::cout << ", ";
                    }

                    std::cout << commit.parents[index];
                }

                std::cout << "]";
            }

            std::cout << "\n";

            if (commit.parents.empty())
            {
                break;
            }

            // A linear history follows the first parent. A merge-aware
            // history walker would need to traverse all parents.
            current = commit.parents.front();
        }
    }
};


// ---------------------------------------------------------------------------
// 5. Branch references
// ---------------------------------------------------------------------------

class BranchManager
{
private:
    std::map<std::string, std::string> branches_;
    std::string headBranch_;

public:
    BranchManager(
        const std::string& initialBranch,
        const std::string& initialCommit)
        : branches_{{initialBranch, initialCommit}},
          headBranch_(initialBranch)
    {
    }

    void createBranch(const std::string& name)
    {
        if (name.empty())
        {
            throw std::invalid_argument(
                "Branch name cannot be empty."
            );
        }

        if (branches_.contains(name))
        {
            throw std::invalid_argument(
                "Branch already exists: " + name
            );
        }

        branches_[name] = headCommit();
    }

    void switchBranch(const std::string& name)
    {
        if (!branches_.contains(name))
        {
            throw std::invalid_argument(
                "Unknown branch: " + name
            );
        }

        headBranch_ = name;
    }

    void advanceHead(const std::string& commitId)
    {
        branches_[headBranch_] = commitId;
    }

    const std::string& headBranch() const
    {
        return headBranch_;
    }

    const std::string& headCommit() const
    {
        return branches_.at(headBranch_);
    }

    void printBranches() const
    {
        for (const auto& [name, commit] : branches_)
        {
            std::cout
                << (name == headBranch_ ? "* " : "  ")
                << name
                << " -> "
                << commit
                << "\n";
        }
    }
};


// ---------------------------------------------------------------------------
// 6. Content-addressed object database
// ---------------------------------------------------------------------------

enum class ObjectType
{
    Blob,
    Tree,
    Commit
};

std::string objectTypeName(ObjectType type)
{
    switch (type)
    {
        case ObjectType::Blob:
            return "blob";

        case ObjectType::Tree:
            return "tree";

        case ObjectType::Commit:
            return "commit";
    }

    throw std::logic_error("Unknown object type.");
}

struct GitObject
{
    std::string id;
    ObjectType type;
    std::string content;
};

class ObjectDatabase
{
private:
    std::map<std::string, GitObject> objects_;

public:
    std::string write(
        ObjectType type,
        const std::string& content)
    {
        const std::string material =
            objectTypeName(type)
            + " "
            + std::to_string(content.size())
            + "\0"
            + content;

        const std::string id = educationalHash(material);

        objects_[id] =
            GitObject{
                id,
                type,
                content
            };

        return id;
    }

    const GitObject& read(const std::string& id) const
    {
        auto iterator = objects_.find(id);

        if (iterator == objects_.end())
        {
            throw std::out_of_range(
                "Unknown object: " + id
            );
        }

        return iterator->second;
    }

    std::size_t size() const
    {
        return objects_.size();
    }
};


// ---------------------------------------------------------------------------
// 7. The version-control engine
// ---------------------------------------------------------------------------

class VersionControlEngine
{
private:
    FileMap workingTree_;
    FileMap index_;

    CommitStore commits_;
    BranchManager branches_;

    ObjectDatabase objects_;

public:
    VersionControlEngine()
        : branches_("main", "")
    {
    }

    void createFile(
        const std::string& path,
        const std::string& content)
    {
        validatePath(path);

        workingTree_[path] = content;
    }

    void editFile(
        const std::string& path,
        const std::string& content)
    {
        validatePath(path);

        if (!workingTree_.contains(path))
        {
            throw std::out_of_range(
                "Cannot edit missing working-tree file: " + path
            );
        }

        workingTree_[path] = content;
    }

    void deleteFile(const std::string& path)
    {
        validatePath(path);

        if (!workingTree_.contains(path))
        {
            throw std::out_of_range(
                "Cannot delete missing working-tree file: " + path
            );
        }

        workingTree_.erase(path);
    }

    void add(const std::string& path)
    {
        validatePath(path);

        auto iterator = workingTree_.find(path);

        if (iterator == workingTree_.end())
        {
            /*
             * Real Git can stage deletion by recording the path's absence
             * in the index. This simplified implementation handles deletion
             * explicitly by removing the path from the index.
             */
            index_.erase(path);
            return;
        }

        index_[path] = iterator->second;
    }

    void addAll()
    {
        index_ = workingTree_;
    }

    void unstage(const std::string& path)
    {
        validatePath(path);

        const Commit* head = currentCommit();

        if (head != nullptr && head->tree.contains(path))
        {
            index_[path] = head->tree.at(path);
        }
        else
        {
            index_.erase(path);
        }
    }

    void restoreWorkingFile(const std::string& path)
    {
        validatePath(path);

        auto iterator = index_.find(path);

        if (iterator != index_.end())
        {
            workingTree_[path] = iterator->second;
            return;
        }

        const Commit* head = currentCommit();

        if (head != nullptr && head->tree.contains(path))
        {
            workingTree_[path] = head->tree.at(path);
            return;
        }

        workingTree_.erase(path);
    }

    std::string commit(const std::string& message)
    {
        if (message.empty())
        {
            throw std::invalid_argument(
                "Commit message cannot be empty."
            );
        }

        if (index_ == currentTree())
        {
            throw std::logic_error(
                "Nothing staged for commit."
            );
        }

        std::vector<std::string> parents;

        if (!branches_.headCommit().empty())
        {
            parents.push_back(branches_.headCommit());
        }

        /*
         * Create educational objects corresponding conceptually to Git's
         * content-addressed storage:
         *
         *   file contents -> blobs
         *   directory state -> tree
         *   metadata + tree -> commit
         */
        std::ostringstream treeMaterial;

        for (const auto& [path, content] : index_)
        {
            const std::string blobId =
                objects_.write(
                    ObjectType::Blob,
                    content
                );

            treeMaterial
                << path
                << ":"
                << blobId
                << "\n";
        }

        const std::string treeId =
            objects_.write(
                ObjectType::Tree,
                treeMaterial.str()
            );

        std::ostringstream commitMaterial;

        commitMaterial
            << "tree "
            << treeId
            << "\n";

        for (const auto& parent : parents)
        {
            commitMaterial
                << "parent "
                << parent
                << "\n";
        }

        commitMaterial
            << "\n"
            << message;

        const std::string commitObjectId =
            objects_.write(
                ObjectType::Commit,
                commitMaterial.str()
            );

        const std::string commitId =
            commits_.createCommit(
                index_,
                message,
                parents
            );

        /*
         * The educational object ID and the commit-store ID are intentionally
         * separate because this program focuses on the architecture rather
         * than implementing Git's exact byte-level storage format.
         */
        (void)commitObjectId;

        branches_.advanceHead(commitId);

        return commitId;
    }

    void createBranch(const std::string& name)
    {
        branches_.createBranch(name);
    }

    void switchBranch(const std::string& name)
    {
        branches_.switchBranch(name);

        const std::string& commitId =
            branches_.headCommit();

        if (commitId.empty())
        {
            index_.clear();
            workingTree_.clear();
            return;
        }

        const Commit& commit =
            commits_.get(commitId);

        index_ = commit.tree;
        workingTree_ = commit.tree;
    }

    void printStatus() const
    {
        const FileMap& headTree =
            currentTree();

        const auto stagedDifferences =
            calculateDiff(
                headTree,
                index_
            );

        const auto workingDifferences =
            calculateDiff(
                index_,
                workingTree_
            );

        std::set<std::string> paths;

        for (const auto& difference : stagedDifferences)
        {
            paths.insert(difference.path);
        }

        for (const auto& difference : workingDifferences)
        {
            paths.insert(difference.path);
        }

        for (const auto& path : workingTree_)
        {
            if (!headTree.contains(path)
                && !index_.contains(path))
            {
                paths.insert(path);
            }
        }

        if (paths.empty())
        {
            std::cout << "  Working tree clean.\n";
            return;
        }

        for (const auto& path : paths)
        {
            const bool changedInStage =
                containsPath(stagedDifferences, path);

            const bool changedInWorking =
                containsPath(workingDifferences, path);

            const bool tracked =
                headTree.contains(path);

            if (!tracked
                && !changedInStage
                && workingTree_.contains(path))
            {
                std::cout
                    << "  ?? "
                    << path
                    << "  untracked\n";

                continue;
            }

            if (changedInStage && changedInWorking)
            {
                std::cout
                    << "  AM "
                    << path
                    << "  staged and additionally modified\n";
            }
            else if (changedInStage)
            {
                std::cout
                    << "  M  "
                    << path
                    << "  modified and staged\n";
            }
            else if (changedInWorking)
            {
                std::cout
                    << "   M "
                    << path
                    << "  modified but unstaged\n";
            }
        }
    }

    void printDiffs() const
    {
        printDiff(
            calculateDiff(
                index_,
                workingTree_
            ),
            "Working tree versus staging area"
        );

        printDiff(
            calculateDiff(
                currentTree(),
                index_
            ),
            "Current commit versus staging area"
        );
    }

    void printHistory() const
    {
        if (branches_.headCommit().empty())
        {
            std::cout << "No commits yet.\n";
            return;
        }

        commits_.printHistory(
            branches_.headCommit()
        );
    }

    void printBranches() const
    {
        branches_.printBranches();
    }

    std::size_t objectCount() const
    {
        return objects_.size();
    }

private:
    static void validatePath(const std::string& path)
    {
        if (path.empty())
        {
            throw std::invalid_argument(
                "File path cannot be empty."
            );
        }

        if (path == "." || path == "..")
        {
            throw std::invalid_argument(
                "Invalid file path."
            );
        }
    }

    const Commit* currentCommit() const
    {
        if (branches_.headCommit().empty())
        {
            return nullptr;
        }

        return &commits_.get(
            branches_.headCommit()
        );
    }

    const FileMap& currentTree() const
    {
        static const FileMap emptyTree;

        const Commit* head =
            currentCommit();

        if (head == nullptr)
        {
            return emptyTree;
        }

        return head->tree;
    }

    static bool containsPath(
        const std::vector<Difference>& differences,
        const std::string& path)
    {
        return std::any_of(
            differences.begin(),
            differences.end(),
            [&](const Difference& difference)
            {
                return difference.path == path;
            }
        );
    }
};


// ---------------------------------------------------------------------------
// 8. Case study
// ---------------------------------------------------------------------------

void runDocumentManagementCaseStudy()
{
    printSection(
        "Git case study: controlled document publishing"
    );

    VersionControlEngine repository;

    std::cout
        << "\nScenario:\n"
        << "A small organization maintains policy documents in a repository.\n"
        << "Editors need to prepare changes, review selected changes, and\n"
        << "record stable snapshots without mixing unrelated work.\n";

    std::cout << "\nCreate initial documents.\n";

    repository.createFile(
        "README.md",
        "# Policy Repository\n"
    );

    repository.createFile(
        "policy.txt",
        "Version 1: access requires authorization.\n"
    );

    repository.addAll();

    std::cout << "\nStatus before first commit:\n";
    repository.printStatus();

    const std::string initialCommit =
        repository.commit(
            "Create initial policy repository"
        );

    std::cout
        << "\nInitial commit: "
        << initialCommit
        << "\n";

    std::cout << "\nStatus after first commit:\n";
    repository.printStatus();

    std::cout
        << "\nStep 2: modify the policy.\n";

    repository.editFile(
        "policy.txt",
        "Version 2: access requires authorization and auditing.\n"
    );

    std::cout << "\nUnstaged change:\n";
    repository.printStatus();

    std::cout
        << "\nStep 3: stage the policy change.\n";

    repository.add("policy.txt");

    repository.printStatus();

    std::cout
        << "\nStep 4: edit README separately after staging.\n";

    repository.editFile(
        "README.md",
        "# Policy Repository\n"
        "\n"
        "Managed document collection.\n"
    );

    repository.printStatus();

    std::cout
        << "\nThis is the key staging-area situation:\n"
        << "policy.txt is staged, while README.md remains unstaged.\n";

    repository.printDiffs();

    std::cout
        << "\nStep 5: commit only the staged policy change.\n";

    const std::string policyCommit =
        repository.commit(
            "Update access-control policy"
        );

    std::cout
        << "Created commit: "
        << policyCommit
        << "\n";

    std::cout
        << "\nThe README edit remains in the working tree.\n";

    repository.printStatus();

    std::cout
        << "\nStep 6: stage and commit README.\n";

    repository.add("README.md");

    const std::string documentationCommit =
        repository.commit(
            "Document repository purpose"
        );

    std::cout
        << "Created commit: "
        << documentationCommit
        << "\n";

    std::cout
        << "\nHistory:\n";

    repository.printHistory();

    std::cout
        << "\nStep 7: create a feature branch.\n";

    repository.createBranch(
        "feature/audit-policy"
    );

    repository.printBranches();

    std::cout
        << "\nThe new branch initially points to the current commit.\n";
}


// ---------------------------------------------------------------------------
// 9. Branch case study
// ---------------------------------------------------------------------------

void demonstrateBranchBehavior()
{
    printSection("Branch references and isolated development");

    VersionControlEngine repository;

    repository.createFile(
        "app.txt",
        "main version\n"
    );

    repository.addAll();

    repository.commit(
        "Initial application"
    );

    repository.createBranch(
        "feature"
    );

    std::cout << "\nBranches immediately after creation:\n";
    repository.printBranches();

    std::cout
        << "\nSwitch to feature and make a change.\n";

    repository.switchBranch("feature");

    repository.editFile(
        "app.txt",
        "feature version\n"
    );

    repository.add("app.txt");

    const std::string featureCommit =
        repository.commit(
            "Implement feature"
        );

    std::cout
        << "Feature commit: "
        << featureCommit
        << "\n";

    std::cout << "\nBranch references:\n";
    repository.printBranches();

    std::cout
        << "\nThe feature branch advanced while the main branch reference "
        << "remained at its earlier commit.\n";
}


// ---------------------------------------------------------------------------
// 10. Edge cases
// ---------------------------------------------------------------------------

void demonstrateEdgeCases()
{
    printSection("Edge cases and failure conditions");

    VersionControlEngine repository;

    try
    {
        repository.add("missing.txt");
    }
    catch (const std::exception& error)
    {
        std::cout
            << "Handled missing-file operation: "
            << error.what()
            << "\n";
    }

    repository.createFile(
        "data.txt",
        "A\n"
    );

    repository.add("data.txt");

    try
    {
        repository.commit("");
    }
    catch (const std::exception& error)
    {
        std::cout
            << "Handled empty commit message: "
            << error.what()
            << "\n";
    }

    repository.commit(
        "Create data file"
    );

    try
    {
        repository.commit(
            "Nothing changed"
        );
    }
    catch (const std::exception& error)
    {
        std::cout
            << "Handled empty staging state: "
            << error.what()
            << "\n";
    }

    repository.editFile(
        "data.txt",
        "B\n"
    );

    repository.add("data.txt");

    repository.editFile(
        "data.txt",
        "C\n"
    );

    std::cout
        << "\nAfter staging B and then editing the working tree to C:\n";

    repository.printStatus();
    repository.printDiffs();
}


// ---------------------------------------------------------------------------
// 11. Complexity discussion
// ---------------------------------------------------------------------------

void printComplexityAnalysis()
{
    printSection("Complexity and design considerations");

    std::cout
        << "\nStatus and diff:\n"
        << "  The teaching implementation compares maps of paths.\n"
        << "  With N distinct paths, collecting and comparing paths is roughly\n"
        << "  O(N log N) because std::map/std::set are ordered trees.\n";

    std::cout
        << "\nAlternative data structures:\n"
        << "  unordered_map can provide average O(1) lookup, but iteration order\n"
        << "  is not naturally sorted and worst-case lookup can degrade.\n";

    std::cout
        << "\nCommit creation:\n"
        << "  The educational object database hashes file contents and creates\n"
        << "  tree and commit representations. Real Git uses highly optimized\n"
        << "  object storage, indexing, packing, compression, and filesystem\n"
        << "  optimizations that are not reproduced here.\n";

    std::cout
        << "\nBranch operations:\n"
        << "  Creating a branch is conceptually inexpensive because a branch is\n"
        << "  a reference to a commit rather than a complete directory copy.\n";
}


// ---------------------------------------------------------------------------
// 12. Security analysis
// ---------------------------------------------------------------------------

void printSecurityAnalysis()
{
    printSection("Security considerations");

    const std::vector<std::string> rules =
    {
        "Do not store passwords, private keys, or API credentials in commits.",
        "Review staged content before creating a commit.",
        ".gitignore reduces accidental tracking but is not a security boundary.",
        "Removing a secret from the latest commit does not automatically remove it from older history.",
        "Remote access controls are distinct from local Git permissions.",
        "Commit signing can authenticate an association between a signer and a commit, but does not prove that the committed code is safe.",
        "Object hashes provide integrity-oriented identification and do not grant permission to access a repository."
    };

    for (std::size_t index = 0;
         index < rules.size();
         ++index)
    {
        std::cout
            << index + 1
            << ". "
            << rules[index]
            << "\n";
    }
}


// ---------------------------------------------------------------------------
// 13. Assertions
// ---------------------------------------------------------------------------

void require(
    bool condition,
    const std::string& message)
{
    if (!condition)
    {
        throw std::runtime_error(
            "Self-test failed: " + message
        );
    }
}

void runSelfTests()
{
    printSection("Self-tests");

    VersionControlEngine repository;

    repository.createFile(
        "test.txt",
        "one"
    );

    repository.add("test.txt");

    const std::string firstCommit =
        repository.commit(
            "Initial test"
        );

    require(
        !firstCommit.empty(),
        "Initial commit should have an ID."
    );

    repository.editFile(
        "test.txt",
        "two"
    );

    repository.add("test.txt");

    repository.editFile(
        "test.txt",
        "three"
    );

    const auto firstHash =
        educationalHash("two");

    const auto secondHash =
        educationalHash("three");

    require(
        firstHash != secondHash,
        "Different content should normally produce different educational hashes."
    );

    require(
        repository.objectCount() > 0,
        "Committing should create objects in the object database."
    );

    std::cout
        << "All C++ self-tests passed.\n";
}


// ---------------------------------------------------------------------------
// 14. Main
// ---------------------------------------------------------------------------

int main()
{
    try
    {
        std::cout
            << repeat('=', 78)
            << "\n"
            << "GIT FUNDAMENTALS\n"
            << "Repository, Working Tree, and Staging Area\n"
            << repeat('=', 78)
            << "\n";

        printSection("Core model");

        std::cout
            << "\n"
            << "Working tree\n"
            << "     |\n"
            << "     | git add\n"
            << "     v\n"
            << "Staging area / index\n"
            << "     |\n"
            << "     | git commit\n"
            << "     v\n"
            << "Repository history\n";

        std::cout
            << "\n"
            << "The staging area allows a developer to select exactly which\n"
            << "working-tree changes become part of the next commit.\n";

        runDocumentManagementCaseStudy();
        demonstrateBranchBehavior();
        demonstrateEdgeCases();
        printComplexityAnalysis();
        printSecurityAnalysis();
        runSelfTests();

        printSection("Important command relationships");

        std::cout
            << "\ngit status\n"
            << "  Shows the relationship between the working tree, index, and HEAD.\n";

        std::cout
            << "\ngit diff\n"
            << "  Compares working-tree content with the index.\n";

        std::cout
            << "\ngit diff --cached\n"
            << "  Compares index content with the current commit.\n";

        std::cout
            << "\ngit add <path>\n"
            << "  Copies the selected working-tree content into the index.\n";

        std::cout
            << "\ngit commit\n"
            << "  Records the staged snapshot as a new commit.\n";

        std::cout
            << "\ngit branch <name>\n"
            << "  Creates a branch reference at the current commit.\n";

        std::cout
            << "\ngit switch <name>\n"
            << "  Changes the current branch/working context.\n";

        std::cout
            << "\ngit restore --staged <path>\n"
            << "  Moves the index representation toward the current commit\n"
            << "  while normally preserving the working-tree edit.\n";

        std::cout
            << "\ngit restore <path>\n"
            << "  Can replace working-tree content from the index, so careless\n"
            << "  use can discard uncommitted changes.\n";

        std::cout
            << "\nCase study complete.\n";
    }
    catch (const std::exception& error)
    {
        std::cerr
            << "\nProgram error: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
```

/*
    Git Tags & Releases: C++17 Industry-Style Case Study
    =====================================================

    Scenario
    --------
    This program models a release-management service for a software project.

    The service:
      1. Parses and validates Semantic Versions.
      2. Applies a project release-tag policy.
      3. Represents commits and release notes.
      4. Classifies commits into changelog categories.
      5. Determines the next version from an explicit change classification.
      6. Validates release conditions.
      7. Demonstrates immutable release-tag policy.
      8. Produces machine-readable release metadata.
      9. Demonstrates complexity, validation, and failure handling.

    The program does not require an external library.

    Compile:
        g++ -std=c++17 -Wall -Wextra -pedantic git_tags_releases.cpp -o release_demo

    Run:
        ./release_demo

    The case study is intentionally self-contained. It models Git operations
    rather than invoking Git, allowing the core release-management logic to
    be studied without requiring a particular repository layout.
*/

#include <algorithm>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// 1. Utility functions
// ============================================================================

string trim(const string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");

    if (first == string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}


bool isDigits(const string& value) {
    if (value.empty()) {
        return false;
    }

    return all_of(
        value.begin(),
        value.end(),
        [](unsigned char character) {
            return std::isdigit(character) != 0;
        }
    );
}


bool isNumericIdentifierValid(const string& value) {
    if (!isDigits(value)) {
        return false;
    }

    // SemVer forbids leading zeroes in numeric identifiers.
    return value == "0" || value.front() != '0';
}


vector<string> split(const string& value, char delimiter) {
    vector<string> parts;
    string current;

    for (char character : value) {
        if (character == delimiter) {
            parts.push_back(current);
            current.clear();
        } else {
            current += character;
        }
    }

    parts.push_back(current);
    return parts;
}


string join(const vector<string>& values, const string& delimiter) {
    ostringstream output;

    for (size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            output << delimiter;
        }

        output << values[index];
    }

    return output.str();
}


// ============================================================================
// 2. Semantic Version
// ============================================================================

class SemanticVersion {
public:
    int major;
    int minor;
    int patch;
    vector<string> prerelease;
    vector<string> build;

    SemanticVersion(
        int majorValue,
        int minorValue,
        int patchValue,
        vector<string> prereleaseValue = {},
        vector<string> buildValue = {}
    )
        : major(majorValue),
          minor(minorValue),
          patch(patchValue),
          prerelease(move(prereleaseValue)),
          build(move(buildValue)) {}

    static SemanticVersion parse(const string& input) {
        const string value = trim(input);

        /*
            SemVer is easier to validate by separating:
              1. build metadata
              2. prerelease
              3. core MAJOR.MINOR.PATCH

            This also keeps the implementation understandable for learners.
        */

        string withoutBuild = value;
        vector<string> buildIdentifiers;

        const size_t plusPosition = withoutBuild.find('+');

        if (plusPosition != string::npos) {
            if (withoutBuild.find('+', plusPosition + 1) != string::npos) {
                throw invalid_argument(
                    "Semantic Version contains multiple '+' characters."
                );
            }

            const string buildText =
                withoutBuild.substr(plusPosition + 1);

            if (buildText.empty()) {
                throw invalid_argument(
                    "Build metadata cannot be empty."
                );
            }

            buildIdentifiers = split(buildText, '.');

            for (const string& identifier : buildIdentifiers) {
                if (identifier.empty()) {
                    throw invalid_argument(
                        "Build identifiers cannot be empty."
                    );
                }

                for (unsigned char character : identifier) {
                    if (!isalnum(character) &&
                        character != '-') {
                        throw invalid_argument(
                            "Invalid character in build metadata."
                        );
                    }
                }
            }

            withoutBuild = withoutBuild.substr(0, plusPosition);
        }

        vector<string> prereleaseIdentifiers;
        const size_t dashPosition = withoutBuild.find('-');

        if (dashPosition != string::npos) {
            const string prereleaseText =
                withoutBuild.substr(dashPosition + 1);

            if (prereleaseText.empty()) {
                throw invalid_argument(
                    "Prerelease section cannot be empty."
                );
            }

            prereleaseIdentifiers = split(
                prereleaseText,
                '.'
            );

            for (const string& identifier : prereleaseIdentifiers) {
                if (identifier.empty()) {
                    throw invalid_argument(
                        "Prerelease identifiers cannot be empty."
                    );
                }

                for (unsigned char character : identifier) {
                    if (!isalnum(character) &&
                        character != '-') {
                        throw invalid_argument(
                            "Invalid character in prerelease identifier."
                        );
                    }
                }

                if (isDigits(identifier) &&
                    !isNumericIdentifierValid(identifier)) {
                    throw invalid_argument(
                        "Numeric prerelease identifiers cannot "
                        "contain leading zeroes."
                    );
                }
            }

            withoutBuild = withoutBuild.substr(0, dashPosition);
        }

        const vector<string> core = split(withoutBuild, '.');

        if (core.size() != 3) {
            throw invalid_argument(
                "Semantic Version must contain MAJOR.MINOR.PATCH."
            );
        }

        for (const string& identifier : core) {
            if (!isNumericIdentifierValid(identifier)) {
                throw invalid_argument(
                    "Core version components must be non-negative "
                    "integers without leading zeroes."
                );
            }
        }

        return SemanticVersion(
            stoi(core[0]),
            stoi(core[1]),
            stoi(core[2]),
            prereleaseIdentifiers,
            buildIdentifiers
        );
    }

    bool isPrerelease() const {
        return !prerelease.empty();
    }

    string toString() const {
        ostringstream output;

        output << major
               << '.'
               << minor
               << '.'
               << patch;

        if (!prerelease.empty()) {
            output << '-'
                   << join(prerelease, ".");
        }

        if (!build.empty()) {
            output << '+'
                   << join(build, ".");
        }

        return output.str();
    }

    /*
        SemVer precedence intentionally ignores build metadata.

        Therefore:
            1.0.0+linux == 1.0.0+windows

        for precedence purposes.
    */
    int compare(const SemanticVersion& other) const {
        if (major != other.major) {
            return major < other.major ? -1 : 1;
        }

        if (minor != other.minor) {
            return minor < other.minor ? -1 : 1;
        }

        if (patch != other.patch) {
            return patch < other.patch ? -1 : 1;
        }

        if (prerelease.empty() && other.prerelease.empty()) {
            return 0;
        }

        if (prerelease.empty()) {
            return 1;
        }

        if (other.prerelease.empty()) {
            return -1;
        }

        const size_t sharedLength = min(
            prerelease.size(),
            other.prerelease.size()
        );

        for (size_t index = 0; index < sharedLength; ++index) {
            const string& left = prerelease[index];
            const string& right = other.prerelease[index];

            if (left == right) {
                continue;
            }

            const bool leftNumeric = isDigits(left);
            const bool rightNumeric = isDigits(right);

            if (leftNumeric && rightNumeric) {
                const long long leftNumber = stoll(left);
                const long long rightNumber = stoll(right);

                return leftNumber < rightNumber ? -1 : 1;
            }

            if (leftNumeric != rightNumeric) {
                return leftNumeric ? -1 : 1;
            }

            return left < right ? -1 : 1;
        }

        if (prerelease.size() == other.prerelease.size()) {
            return 0;
        }

        return prerelease.size() < other.prerelease.size() ? -1 : 1;
    }

    bool operator<(const SemanticVersion& other) const {
        return compare(other) < 0;
    }

    bool operator==(const SemanticVersion& other) const {
        return compare(other) == 0;
    }

    bool operator!=(const SemanticVersion& other) const {
        return !(*this == other);
    }

    SemanticVersion bumpMajor() const {
        return SemanticVersion(major + 1, 0, 0);
    }

    SemanticVersion bumpMinor() const {
        return SemanticVersion(major, minor + 1, 0);
    }

    SemanticVersion bumpPatch() const {
        return SemanticVersion(major, minor, patch + 1);
    }
};


// ============================================================================
// 3. Git object and tag models
// ============================================================================

enum class TagType {
    Lightweight,
    Annotated
};


string tagTypeName(TagType type) {
    return type == TagType::Annotated
        ? "annotated"
        : "lightweight";
}


struct Commit {
    string hash;
    string subject;
    string author;
};


struct GitTag {
    string name;
    string targetCommit;
    TagType type;
    string tagger;
    string message;
};


struct ReleaseArtifact {
    string filename;
    string checksum;
    uint64_t sizeBytes;
};


struct Release {
    SemanticVersion version;
    string tagName;
    string title;
    bool prerelease;
    vector<string> notes;
    vector<ReleaseArtifact> artifacts;

    string toJson() const {
        /*
            This is deliberately small JSON generation for the fixed internal
            model. A production service should use a JSON library when it
            needs arbitrary user-controlled strings or complex schemas.
        */
        ostringstream output;

        output << "{\n";
        output << "  \"version\": \""
               << version.toString()
               << "\",\n";
        output << "  \"tag\": \""
               << tagName
               << "\",\n";
        output << "  \"title\": \""
               << title
               << "\",\n";
        output << "  \"prerelease\": "
               << (prerelease ? "true" : "false")
               << ",\n";

        output << "  \"notes\": [";

        for (size_t index = 0; index < notes.size(); ++index) {
            if (index > 0) {
                output << ", ";
            }

            output << "\""
                   << notes[index]
                   << "\"";
        }

        output << "],\n";

        output << "  \"artifacts\": [\n";

        for (size_t index = 0; index < artifacts.size(); ++index) {
            const auto& artifact = artifacts[index];

            output << "    {\n";
            output << "      \"filename\": \""
                   << artifact.filename
                   << "\",\n";
            output << "      \"checksum\": \""
                   << artifact.checksum
                   << "\",\n";
            output << "      \"sizeBytes\": "
                   << artifact.sizeBytes
                   << "\n";
            output << "    }";

            if (index + 1 < artifacts.size()) {
                output << ',';
            }

            output << '\n';
        }

        output << "  ]\n";
        output << "}";

        return output.str();
    }
};


// ============================================================================
// 4. Release policy
// ============================================================================

class ReleasePolicy {
private:
    string prefix;
    bool requireAnnotated;
    bool requireCleanWorkingTree;
    bool immutableTags;

public:
    ReleasePolicy(
        string prefixValue = "v",
        bool requireAnnotatedValue = true,
        bool requireCleanWorkingTreeValue = true,
        bool immutableTagsValue = true
    )
        : prefix(move(prefixValue)),
          requireAnnotated(requireAnnotatedValue),
          requireCleanWorkingTree(requireCleanWorkingTreeValue),
          immutableTags(immutableTagsValue) {}

    SemanticVersion parseTag(const string& tagName) const {
        if (tagName.empty()) {
            throw invalid_argument(
                "Release tag cannot be empty."
            );
        }

        if (!prefix.empty()) {
            if (tagName.rfind(prefix, 0) != 0) {
                throw invalid_argument(
                    "Release tag does not use the required prefix."
                );
            }
        }

        const string versionText = prefix.empty()
            ? tagName
            : tagName.substr(prefix.size());

        return SemanticVersion::parse(versionText);
    }

    bool requiresAnnotated() const {
        return requireAnnotated;
    }

    bool requiresCleanWorkingTree() const {
        return requireCleanWorkingTree;
    }

    bool requiresImmutableTags() const {
        return immutableTags;
    }
};


// ============================================================================
// 5. Repository model
// ============================================================================

class Repository {
private:
    string currentCommit;
    bool workingTreeClean;
    vector<Commit> commits;
    vector<GitTag> tags;

public:
    explicit Repository(
        string currentCommitValue = "0000000000000000000000000000000000000000",
        bool workingTreeCleanValue = true
    )
        : currentCommit(move(currentCommitValue)),
          workingTreeClean(workingTreeCleanValue) {}

    void addCommit(Commit commit) {
        commits.push_back(move(commit));
    }

    void addTag(GitTag tag) {
        tags.push_back(move(tag));
    }

    const vector<Commit>& getCommits() const {
        return commits;
    }

    const vector<GitTag>& getTags() const {
        return tags;
    }

    bool isWorkingTreeClean() const {
        return workingTreeClean;
    }

    const string& head() const {
        return currentCommit;
    }

    bool hasTag(const string& name) const {
        return any_of(
            tags.begin(),
            tags.end(),
            [&](const GitTag& tag) {
                return tag.name == name;
            }
        );
    }

    optional<GitTag> findTag(const string& name) const {
        for (const auto& tag : tags) {
            if (tag.name == name) {
                return tag;
            }
        }

        return nullopt;
    }

    void setWorkingTreeClean(bool clean) {
        workingTreeClean = clean;
    }

    void createAnnotatedTag(
        const string& name,
        const string& message,
        const string& tagger,
        const ReleasePolicy& policy
    ) {
        if (policy.requiresImmutableTags() && hasTag(name)) {
            throw runtime_error(
                "Immutable release policy forbids moving an existing tag."
            );
        }

        if (policy.requiresCleanWorkingTree() &&
            !workingTreeClean) {
            throw runtime_error(
                "Cannot create release tag with a dirty working tree."
            );
        }

        if (policy.requiresAnnotated()) {
            tags.push_back(
                GitTag{
                    name,
                    currentCommit,
                    TagType::Annotated,
                    tagger,
                    message
                }
            );
        } else {
            tags.push_back(
                GitTag{
                    name,
                    currentCommit,
                    TagType::Lightweight,
                    tagger,
                    message
                }
            );
        }
    }
};


// ============================================================================
// 6. Commit classification and changelog
// ============================================================================

string classifyCommit(const string& subject) {
    string lowered = subject;

    transform(
        lowered.begin(),
        lowered.end(),
        lowered.begin(),
        [](unsigned char character) {
            return static_cast<char>(tolower(character));
        }
    );

    if (lowered.rfind("feat", 0) == 0) {
        return "Features";
    }

    if (lowered.rfind("fix", 0) == 0) {
        return "Bug Fixes";
    }

    if (lowered.rfind("docs", 0) == 0) {
        return "Documentation";
    }

    if (lowered.rfind("perf", 0) == 0) {
        return "Performance";
    }

    if (lowered.rfind("refactor", 0) == 0) {
        return "Refactoring";
    }

    if (lowered.rfind("test", 0) == 0) {
        return "Tests";
    }

    if (lowered.rfind("build", 0) == 0 ||
        lowered.rfind("ci", 0) == 0) {
        return "Build and CI";
    }

    return "Other Changes";
}


string generateChangelog(
    const vector<Commit>& commits,
    const SemanticVersion& version
) {
    map<string, vector<Commit>> groups;

    for (const auto& commit : commits) {
        groups[classifyCommit(commit.subject)].push_back(commit);
    }

    const vector<string> order = {
        "Breaking Changes",
        "Features",
        "Bug Fixes",
        "Performance",
        "Refactoring",
        "Documentation",
        "Tests",
        "Build and CI",
        "Other Changes"
    };

    ostringstream output;

    output << "## " << version.toString() << "\n\n";
    output << "Release changelog\n\n";

    for (const string& category : order) {
        const auto iterator = groups.find(category);

        if (iterator == groups.end()) {
            continue;
        }

        output << "### " << category << "\n\n";

        for (const auto& commit : iterator->second) {
            output << "- "
                   << commit.subject
                   << " ("
                   << commit.hash.substr(0, min<size_t>(8, commit.hash.size()))
                   << ")\n";
        }

        output << '\n';
    }

    return output.str();
}


// ============================================================================
// 7. Release validation
// ============================================================================

struct ValidationResult {
    vector<string> errors;

    bool valid() const {
        return errors.empty();
    }

    void print() const {
        if (valid()) {
            cout << "Release validation: PASSED\n";
            return;
        }

        cout << "Release validation: FAILED\n";

        for (const string& error : errors) {
            cout << "  - " << error << '\n';
        }
    }
};


ValidationResult validateRelease(
    const Repository& repository,
    const ReleasePolicy& policy,
    const string& tagName
) {
    ValidationResult result;

    try {
        policy.parseTag(tagName);
    } catch (const exception& error) {
        result.errors.push_back(error.what());
    }

    if (policy.requiresAnnotated()) {
        // The policy is enforced when the tag is created.
        // Existing tags are checked separately below.
    }

    if (policy.requiresCleanWorkingTree() &&
        !repository.isWorkingTreeClean()) {
        result.errors.push_back(
            "The working tree contains uncommitted changes."
        );
    }

    if (policy.requiresImmutableTags() &&
        repository.hasTag(tagName)) {
        result.errors.push_back(
            "The proposed release tag already exists."
        );
    }

    return result;
}


// ============================================================================
// 8. Version selection
// ============================================================================

optional<pair<SemanticVersion, GitTag>> latestStableTag(
    const Repository& repository
) {
    optional<pair<SemanticVersion, GitTag>> latest;

    for (const auto& tag : repository.getTags()) {
        try {
            string versionText = tag.name;

            if (!versionText.empty() &&
                versionText.front() == 'v') {
                versionText.erase(versionText.begin());
            }

            SemanticVersion version =
                SemanticVersion::parse(versionText);

            if (version.isPrerelease()) {
                continue;
            }

            if (!latest.has_value() ||
                latest->first < version) {
                latest = make_pair(version, tag);
            }
        } catch (const exception&) {
            // Non-SemVer tags are ignored by the release-version scanner.
        }
    }

    return latest;
}


SemanticVersion nextVersion(
    const SemanticVersion& current,
    const string& changeType
) {
    if (changeType == "major") {
        return current.bumpMajor();
    }

    if (changeType == "minor") {
        return current.bumpMinor();
    }

    if (changeType == "patch") {
        return current.bumpPatch();
    }

    throw invalid_argument(
        "Change type must be major, minor, or patch."
    );
}


// ============================================================================
// 9. Release manager
// ============================================================================

class ReleaseManager {
private:
    Repository& repository;
    ReleasePolicy policy;

public:
    ReleaseManager(
        Repository& repositoryValue,
        ReleasePolicy policyValue
    )
        : repository(repositoryValue),
          policy(move(policyValue)) {}

    Release prepareRelease(
        const SemanticVersion& version,
        string title,
        vector<string> notes,
        vector<ReleaseArtifact> artifacts
    ) const {
        const string tagName = "v" + version.toString();

        ValidationResult validation =
            validateRelease(
                repository,
                policy,
                tagName
            );

        if (!validation.valid()) {
            ostringstream error;

            error << "Cannot prepare release:\n";

            for (const string& problem : validation.errors) {
                error << " - " << problem << '\n';
            }

            throw runtime_error(error.str());
        }

        return Release{
            version,
            tagName,
            move(title),
            version.isPrerelease(),
            move(notes),
            move(artifacts)
        };
    }

    void publishTag(
        const Release& release,
        const string& tagger
    ) {
        /*
            This operation models the local Git tag creation step.

            In a real service, publication would also require:
              - authenticated remote access
              - CI validation
              - artifact storage
              - release API calls
              - audit logging
              - retry handling
        */
        repository.createAnnotatedTag(
            release.tagName,
            release.title,
            tagger,
            policy
        );
    }
};


// ============================================================================
// 10. Demonstration helpers
// ============================================================================

void printSeparator(const string& title) {
    cout << "\n"
         << string(78, '=')
         << "\n"
         << title
         << "\n"
         << string(78, '=')
         << "\n";
}


void demonstrateSemVer() {
    printSeparator("1. Semantic Versioning");

    const vector<string> values = {
        "0.1.0",
        "1.0.0",
        "1.2.3",
        "2.0.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-rc.1",
        "1.0.0+build.17"
    };

    for (const string& value : values) {
        const SemanticVersion version =
            SemanticVersion::parse(value);

        cout << setw(24)
             << left
             << value
             << " major="
             << version.major
             << " minor="
             << version.minor
             << " patch="
             << version.patch
             << " prerelease="
             << (version.prerelease.empty()
                 ? "-"
                 : join(version.prerelease, "."))
             << '\n';
    }
}


void demonstratePrecedence() {
    printSeparator("2. SemVer Precedence");

    const vector<string> orderedValues = {
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0"
    };

    vector<SemanticVersion> versions;

    for (const string& value : orderedValues) {
        versions.push_back(
            SemanticVersion::parse(value)
        );
    }

    for (size_t index = 0; index + 1 < versions.size(); ++index) {
        cout << versions[index].toString()
             << " < "
             << versions[index + 1].toString()
             << '\n';
    }

    const auto linux =
        SemanticVersion::parse("1.0.0+linux");

    const auto windows =
        SemanticVersion::parse("1.0.0+windows");

    cout << "\nBuild metadata comparison: "
         << linux.toString()
         << " == "
         << windows.toString()
         << " -> "
         << boolalpha
         << (linux == windows)
         << '\n';
}


void demonstrateInvalidVersions() {
    printSeparator("3. Invalid Semantic Versions");

    const vector<string> invalidValues = {
        "1",
        "1.2",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-",
        "1.2.3+",
        "1.2.3..build"
    };

    for (const string& value : invalidValues) {
        try {
            const auto version =
                SemanticVersion::parse(value);

            cout << "Unexpectedly accepted: "
                 << version.toString()
                 << '\n';
        } catch (const exception& error) {
            cout << "Rejected: "
                 << value
                 << " -> "
                 << error.what()
                 << '\n';
        }
    }
}


void demonstrateRepository() {
    printSeparator("4. Repository and Tag Model");

    Repository repository(
        "abcdef1234567890abcdef1234567890abcdef12"
    );

    repository.addCommit({
        "1111111111111111111111111111111111111111",
        "feat: add release dashboard",
        "Release Team"
    });

    repository.addCommit({
        "2222222222222222222222222222222222222222",
        "fix: reject invalid version",
        "Release Team"
    });

    repository.addCommit({
        "3333333333333333333333333333333333333333",
        "docs: document tag policy",
        "Documentation Team"
    });

    repository.addTag({
        "v1.0.0",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        TagType::Annotated,
        "Release Team",
        "Release v1.0.0"
    });

    repository.addTag({
        "development-start",
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        TagType::Lightweight,
        "",
        ""
    });

    for (const auto& tag : repository.getTags()) {
        cout << tag.name
             << " | "
             << tagTypeName(tag.type)
             << " | target="
             << tag.targetCommit.substr(0, 12)
             << '\n';
    }

    const auto latest =
        latestStableTag(repository);

    if (latest.has_value()) {
        cout << "\nLatest stable version: "
             << latest->first.toString()
             << " at "
             << latest->second.name
             << '\n';
    }
}


void demonstrateChangelog(const Repository& repository) {
    printSeparator("5. Generated Changelog");

    const auto version =
        SemanticVersion::parse("1.1.0");

    cout << generateChangelog(
        repository.getCommits(),
        version
    );
}


void demonstrateReleaseWorkflow() {
    printSeparator("6. Industry-Style Release Workflow");

    Repository repository(
        "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    );

    repository.addCommit({
        "1111111111111111111111111111111111111111",
        "feat: add release manifest",
        "Engineering"
    });

    repository.addCommit({
        "2222222222222222222222222222222222222222",
        "fix: validate release names",
        "Engineering"
    });

    repository.addCommit({
        "3333333333333333333333333333333333333333",
        "docs: document publishing procedure",
        "Engineering"
    });

    repository.addTag({
        "v1.0.0",
        "9999999999999999999999999999999999999999",
        TagType::Annotated,
        "Release Bot",
        "Release v1.0.0"
    });

    ReleasePolicy policy(
        "v",
        true,
        true,
        true
    );

    ReleaseManager manager(
        repository,
        policy
    );

    const auto current =
        latestStableTag(repository)->first;

    cout << "Current stable version: "
         << current.toString()
         << '\n';

    const auto next =
        nextVersion(current, "minor");

    cout << "Planned next version:   "
         << next.toString()
         << '\n';

    const string tagName =
        "v" + next.toString();

    const ValidationResult validation =
        validateRelease(
            repository,
            policy,
            tagName
        );

    validation.print();

    if (!validation.valid()) {
        return;
    }

    const vector<string> notes = {
        "Added release manifest support.",
        "Improved release-tag validation.",
        "Expanded documentation."
    };

    const vector<ReleaseArtifact> artifacts = {
        {
            "project-1.1.0.tar.gz",
            "sha256-example-checksum-001",
            15432
        },
        {
            "project-1.1.0.zip",
            "sha256-example-checksum-002",
            18241
        }
    };

    Release release =
        manager.prepareRelease(
            next,
            "Release v1.1.0",
            notes,
            artifacts
        );

    cout << "\nPrepared release:\n";
    cout << release.toJson() << '\n';

    /*
        The tag is now created only after validation succeeds.
    */
    manager.publishTag(
        release,
        "Release Bot"
    );

    cout << "\nPublished local tag: "
         << release.tagName
         << '\n';

    const auto created =
        repository.findTag(release.tagName);

    if (created.has_value()) {
        cout << "Tag target: "
             << created->targetCommit.substr(0, 12)
             << '\n';

        cout << "Tag type: "
             << tagTypeName(created->type)
             << '\n';
    }

    /*
        Attempting to create the same release again demonstrates the
        immutable-tag failure condition.
    */
    try {
        manager.publishTag(
            release,
            "Another Release Bot"
        );

        cout << "Unexpectedly moved an immutable tag.\n";
    } catch (const exception& error) {
        cout << "\nExpected duplicate-tag rejection:\n"
             << error.what()
             << '\n';
    }
}


void demonstrateDirtyRepository() {
    printSeparator("7. Dirty Working Tree Failure");

    Repository repository(
        "abcdefabcdefabcdefabcdefabcdefabcdefabcd",
        false
    );

    ReleasePolicy policy;

    const ValidationResult result =
        validateRelease(
            repository,
            policy,
            "v2.0.0"
        );

    result.print();
}


void demonstratePrerelease() {
    printSeparator("8. Prerelease Lifecycle");

    const vector<string> lifecycle = {
        "2.0.0-alpha",
        "2.0.0-alpha.1",
        "2.0.0-beta",
        "2.0.0-rc.1",
        "2.0.0"
    };

    SemanticVersion previous =
        SemanticVersion::parse(lifecycle.front());

    cout << previous.toString() << '\n';

    for (size_t index = 1; index < lifecycle.size(); ++index) {
        SemanticVersion current =
            SemanticVersion::parse(lifecycle[index]);

        cout << previous.toString()
             << " < "
             << current.toString()
             << " -> "
             << boolalpha
             << (previous < current)
             << '\n';

        previous = current;
    }
}


// ============================================================================
// 11. Automated tests
// ============================================================================

void assertTrue(bool condition, const string& message) {
    if (!condition) {
        throw runtime_error(
            "Assertion failed: " + message
        );
    }
}


void runTests() {
    printSeparator("9. Automated Tests");

    {
        const auto version =
            SemanticVersion::parse("1.2.3");

        assertTrue(
            version.toString() == "1.2.3",
            "basic SemVer round trip"
        );
    }

    {
        const auto version =
            SemanticVersion::parse(
                "1.2.3-alpha.1+build.7"
            );

        assertTrue(
            version.isPrerelease(),
            "prerelease detection"
        );

        assertTrue(
            version.toString() ==
            "1.2.3-alpha.1+build.7",
            "complex SemVer round trip"
        );
    }

    {
        const auto first =
            SemanticVersion::parse("1.0.0-alpha");

        const auto second =
            SemanticVersion::parse("1.0.0");

        assertTrue(
            first < second,
            "prerelease must precede stable release"
        );
    }

    {
        const auto first =
            SemanticVersion::parse("1.0.0+linux");

        const auto second =
            SemanticVersion::parse("1.0.0+windows");

        assertTrue(
            first == second,
            "build metadata must not affect precedence"
        );
    }

    {
        const auto current =
            SemanticVersion::parse("3.4.9");

        assertTrue(
            current.bumpPatch() ==
            SemanticVersion::parse("3.4.10"),
            "patch bump"
        );

        assertTrue(
            current.bumpMinor() ==
            SemanticVersion::parse("3.5.0"),
            "minor bump"
        );

        assertTrue(
            current.bumpMajor() ==
            SemanticVersion::parse("4.0.0"),
            "major bump"
        );
    }

    {
        bool rejected = false;

        try {
            SemanticVersion::parse("01.2.3");
        } catch (const exception&) {
            rejected = true;
        }

        assertTrue(
            rejected,
            "leading zero must be rejected"
        );
    }

    {
        Repository repository;

        repository.addTag({
            "v1.0.0",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            TagType::Annotated,
            "Bot",
            "Release"
        });

        ReleasePolicy policy;

        const ValidationResult result =
            validateRelease(
                repository,
                policy,
                "v1.0.0"
            );

        assertTrue(
            !result.valid(),
            "duplicate immutable tag must fail"
        );
    }

    {
        Repository repository;

        ReleasePolicy policy;

        repository.setWorkingTreeClean(false);

        const ValidationResult result =
            validateRelease(
                repository,
                policy,
                "v1.1.0"
            );

        assertTrue(
            !result.valid(),
            "dirty tree must fail release validation"
        );
    }

    {
        assertTrue(
            classifyCommit("feat: add API") ==
            "Features",
            "feature classification"
        );

        assertTrue(
            classifyCommit("fix: repair crash") ==
            "Bug Fixes",
            "bug-fix classification"
        );
    }

    cout << "All C++ tests passed.\n";
}


// ============================================================================
// 12. Main
// ============================================================================

int main() {
    try {
        demonstrateSemVer();
        demonstratePrecedence();
        demonstrateInvalidVersions();

        Repository repository(
            "abcdef1234567890abcdef1234567890abcdef12"
        );

        repository.addCommit({
            "1111111111111111111111111111111111111111",
            "feat: add release dashboard",
            "Engineering"
        });

        repository.addCommit({
            "2222222222222222222222222222222222222222",
            "fix: reject invalid tags",
            "Engineering"
        });

        repository.addCommit({
            "3333333333333333333333333333333333333333",
            "docs: document release process",
            "Documentation"
        });

        repository.addTag({
            "v1.0.0",
            "9999999999999999999999999999999999999999",
            TagType::Annotated,
            "Release Bot",
            "Release v1.0.0"
        });

        demonstrateRepository();
        demonstrateChangelog(repository);
        demonstrateReleaseWorkflow();
        demonstrateDirtyRepository();
        demonstratePrerelease();
        runTests();

        printSeparator("10. Complexity and Design Notes");

        cout
            << "SemVer parsing: O(L), where L is version-string length.\n"
            << "Prerelease comparison: O(P), where P is the number of shared identifiers.\n"
            << "Tag lookup in this educational vector model: O(T), where T is tag count.\n"
            << "Latest-version scan: O(T log T) if sorting is used, or O(T) with one-pass maximum.\n"
            << "Changelog grouping: O(C), excluding string-processing costs, where C is commit count.\n"
            << "\n"
            << "Production systems should also address authentication, remote\n"
            << "publication, artifact integrity, CI/CD authorization, audit logs,\n"
            << "concurrent release requests, and persistent storage.\n";

        return 0;
    } catch (const exception& error) {
        cerr << "\nFatal error: "
             << error.what()
             << '\n';

        return 1;
    }
}

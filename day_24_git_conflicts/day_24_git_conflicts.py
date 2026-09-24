"""
Git Conflicts: Conflict Detection, Resolution, and Merge Strategies
====================================================================

A standalone educational program covering Git conflict mechanics from
beginner through advanced concepts.

The demonstrations model Git's three-way merge behavior in Python without
requiring a real Git repository. The final section can optionally inspect
a real repository through subprocess if Git is installed.

Topics demonstrated:
- commits, branches, and snapshots
- fast-forward and three-way merges
- conflict detection
- textual conflict markers
- same-line and different-line conflicts
- add/add, modify/delete, delete/modify, and rename-style conflicts
- ours/theirs semantics
- manual resolution
- merge strategies
- merge-base reasoning
- conflict classification
- resolution validation
- rerere concepts
- merge vs rebase vs squash
- octopus-style considerations
- performance and production practices
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import difflib
import hashlib
import os
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Fundamental data model
# ---------------------------------------------------------------------------

class FileState(Enum):
    ABSENT = "absent"
    PRESENT = "present"


@dataclass(frozen=True)
class FileSnapshot:
    """Represents the state of one file in a commit snapshot."""

    content: Optional[str]

    @property
    def exists(self) -> bool:
        return self.content is not None


@dataclass
class Commit:
    """A simplified Git commit containing a full tree snapshot."""

    commit_id: str
    parents: Tuple[str, ...]
    message: str
    tree: Dict[str, FileSnapshot]


@dataclass
class Conflict:
    """Describes a conflict detected during a three-way merge."""

    path: str
    base: FileSnapshot
    ours: FileSnapshot
    theirs: FileSnapshot
    conflict_type: str
    explanation: str
    markers: str = ""


@dataclass
class MergeResult:
    """Result of merging two snapshots."""

    merged_tree: Dict[str, FileSnapshot]
    conflicts: List[Conflict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.conflicts


# ---------------------------------------------------------------------------
# Basic snapshot helpers
# ---------------------------------------------------------------------------

def snapshot(content: str) -> FileSnapshot:
    return FileSnapshot(content)


def absent() -> FileSnapshot:
    return FileSnapshot(None)


def same_state(left: FileSnapshot, right: FileSnapshot) -> bool:
    """Two file states are equal when existence and content are equal."""
    return left.content == right.content


def sha1_text(text: str) -> str:
    """Git uses SHA-1 historically for object identity; SHA-256 repositories
    are also supported by modern Git. This function models SHA-1 only."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def show_snapshot(name: str, tree: Dict[str, FileSnapshot]) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    for path in sorted(tree):
        state = tree[path]
        if state.exists:
            print(f"{path}: {state.content!r}")
        else:
            print(f"{path}: <deleted>")


# ---------------------------------------------------------------------------
# Three-way merge fundamentals
# ---------------------------------------------------------------------------

def conflict_markers(
    ours: Optional[str],
    theirs: Optional[str],
    ours_label: str = "HEAD",
    theirs_label: str = "incoming",
) -> str:
    """Construct familiar Git-style conflict markers.

    Real Git's exact marker formatting can vary with configuration and merge
    machinery. The representation below captures the essential semantics.
    """
    ours_text = "" if ours is None else ours
    theirs_text = "" if theirs is None else theirs

    return (
        f"<<<<<<< {ours_label}\n"
        f"{ours_text}"
        f"{'' if ours_text.endswith(chr(10)) or not ours_text else chr(10)}"
        f"=======\n"
        f"{theirs_text}"
        f"{'' if theirs_text.endswith(chr(10)) or not theirs_text else chr(10)}"
        f">>>>>>> {theirs_label}\n"
    )


def classify_file_change(
    base: FileSnapshot,
    side: FileSnapshot,
) -> str:
    """Classify how one side differs from the merge base."""
    if same_state(base, side):
        return "unchanged"
    if not base.exists and side.exists:
        return "added"
    if base.exists and not side.exists:
        return "deleted"
    return "modified"


def detect_file_conflict(
    path: str,
    base: FileSnapshot,
    ours: FileSnapshot,
    theirs: FileSnapshot,
) -> Optional[Conflict]:
    """
    Apply the central three-way merge rule.

    If only one side changed relative to the base, that change can normally
    be accepted automatically. If both sides changed to the same result,
    that result is also safe. A conflict exists when both sides changed the
    same base state differently.
    """
    base_change = classify_file_change(base, ours)
    theirs_change = classify_file_change(base, theirs)

    if same_state(ours, theirs):
        return None

    if same_state(ours, base):
        return None

    if same_state(theirs, base):
        return None

    if base.exists and not ours.exists and not theirs.exists:
        return None

    if not base.exists and ours.exists and theirs.exists:
        conflict_type = "add/add"
        explanation = "Both branches created the same path with different content."
    elif base.exists and not ours.exists and theirs.exists:
        conflict_type = "delete/modify"
        explanation = "Ours deleted the file while theirs modified it."
    elif base.exists and ours.exists and not theirs.exists:
        conflict_type = "modify/delete"
        explanation = "Ours modified the file while theirs deleted it."
    else:
        conflict_type = "content"
        explanation = "Both branches modified the file differently."

    markers = conflict_markers(
        ours.content,
        theirs.content,
        "HEAD",
        "incoming",
    )

    return Conflict(
        path=path,
        base=base,
        ours=ours,
        theirs=theirs,
        conflict_type=conflict_type,
        explanation=explanation,
        markers=markers,
    )


def three_way_merge(
    base_tree: Dict[str, FileSnapshot],
    ours_tree: Dict[str, FileSnapshot],
    theirs_tree: Dict[str, FileSnapshot],
) -> MergeResult:
    """Perform a simplified file-level three-way merge."""
    all_paths = set(base_tree) | set(ours_tree) | set(theirs_tree)
    merged: Dict[str, FileSnapshot] = {}
    conflicts: List[Conflict] = []

    for path in sorted(all_paths):
        base = base_tree.get(path, absent())
        ours = ours_tree.get(path, absent())
        theirs = theirs_tree.get(path, absent())

        conflict = detect_file_conflict(path, base, ours, theirs)

        if conflict:
            conflicts.append(conflict)
            # A real Git index can temporarily contain multiple stages for a
            # conflicted path. Here we keep the base and sides in Conflict.
            continue

        if same_state(ours, base):
            result = theirs
        else:
            result = ours

        if result.exists:
            merged[path] = result

    return MergeResult(merged, conflicts)


# ---------------------------------------------------------------------------
# Demonstration: clean merge
# ---------------------------------------------------------------------------

def demo_clean_three_way_merge() -> None:
    print("\n=== CLEAN THREE-WAY MERGE ===")

    base = {
        "README.md": snapshot("# Project\n"),
        "app.py": snapshot("print('hello')\n"),
    }

    ours = {
        "README.md": snapshot("# Project\n\nPython implementation\n"),
        "app.py": base["app.py"],
    }

    theirs = {
        "README.md": base["README.md"],
        "app.py": snapshot("print('hello world')\n"),
    }

    result = three_way_merge(base, ours, theirs)

    print(f"Clean merge: {result.clean}")
    show_snapshot("Merged tree", result.merged_tree)


# ---------------------------------------------------------------------------
# Demonstration: conflict
# ---------------------------------------------------------------------------

def demo_content_conflict() -> None:
    print("\n=== CONTENT CONFLICT ===")

    base = {
        "config.txt": snapshot("timeout=30\nmode=standard\n"),
    }

    ours = {
        "config.txt": snapshot("timeout=60\nmode=standard\n"),
    }

    theirs = {
        "config.txt": snapshot("timeout=120\nmode=standard\n"),
    }

    result = three_way_merge(base, ours, theirs)

    print(f"Clean merge: {result.clean}")

    for conflict in result.conflicts:
        print(f"Path: {conflict.path}")
        print(f"Type: {conflict.conflict_type}")
        print(f"Reason: {conflict.explanation}")
        print("Conflict representation:")
        print(conflict.markers)


# ---------------------------------------------------------------------------
# Line-level conflict analysis
# ---------------------------------------------------------------------------

def line_level_overlap(
    base: str,
    ours: str,
    theirs: str,
) -> List[Tuple[int, int]]:
    """
    Identify broad regions where both branches modified the base.

    This is an educational approximation, not a replacement for Git's merge
    algorithms. Git performs sophisticated line-oriented merging and can
    use different merge backends and diff algorithms.
    """
    base_lines = base.splitlines()
    ours_lines = ours.splitlines()
    theirs_lines = theirs.splitlines()

    ours_changes = list(
        difflib.SequenceMatcher(None, base_lines, ours_lines).get_opcodes()
    )
    theirs_changes = list(
        difflib.SequenceMatcher(None, base_lines, theirs_lines).get_opcodes()
    )

    overlaps: List[Tuple[int, int]] = []

    for _, i1, i2, _, _ in ours_changes:
        if i1 == i2:
            continue

        for _, j1, j2, _, _ in theirs_changes:
            if j1 == j2:
                continue

            start = max(i1, j1)
            end = min(i2, j2)

            if start < end:
                overlaps.append((start, end))

    return overlaps


def demo_line_level_reasoning() -> None:
    print("\n=== LINE-LEVEL REASONING ===")

    base = """name=service
port=8000
workers=2
debug=false
"""

    ours = """name=service
port=9000
workers=2
debug=false
"""

    theirs = """name=service
port=7000
workers=2
debug=false
"""

    overlap = line_level_overlap(base, ours, theirs)

    print("Potential overlapping base ranges:", overlap)
    print(
        "Both branches changed the same logical line, so a textual merge "
        "cannot safely choose one value without project-specific knowledge."
    )


# ---------------------------------------------------------------------------
# Conflict categories
# ---------------------------------------------------------------------------

def demo_conflict_types() -> None:
    print("\n=== IMPORTANT CONFLICT TYPES ===")

    cases = {
        "add/add": (
            absent(),
            snapshot("ours\n"),
            snapshot("theirs\n"),
        ),
        "modify/delete": (
            snapshot("original\n"),
            snapshot("changed by ours\n"),
            absent(),
        ),
        "delete/modify": (
            snapshot("original\n"),
            absent(),
            snapshot("changed by theirs\n"),
        ),
        "content": (
            snapshot("original\n"),
            snapshot("ours\n"),
            snapshot("theirs\n"),
        ),
    }

    for expected, (base, ours, theirs) in cases.items():
        conflict = detect_file_conflict(
            f"{expected}.txt",
            base,
            ours,
            theirs,
        )
        actual = conflict.conflict_type if conflict else "none"
        print(f"{expected:15} -> detected: {actual}")


# ---------------------------------------------------------------------------
# Resolution policies
# ---------------------------------------------------------------------------

class ResolutionPolicy(Enum):
    OURS = "ours"
    THEIRS = "theirs"
    MANUAL = "manual"


def resolve_conflict(
    conflict: Conflict,
    policy: ResolutionPolicy,
    manual_content: Optional[str] = None,
) -> FileSnapshot:
    """
    Resolve one conflict according to an explicit policy.

    'ours' and 'theirs' are useful only when the entire conflicted file can
    legitimately follow one side. They should not be treated as universally
    correct choices.
    """
    if policy is ResolutionPolicy.OURS:
        return conflict.ours

    if policy is ResolutionPolicy.THEIRS:
        return conflict.theirs

    if policy is ResolutionPolicy.MANUAL:
        if manual_content is None:
            raise ValueError("Manual resolution requires manual_content.")
        return snapshot(manual_content)

    raise ValueError(f"Unsupported resolution policy: {policy}")


def apply_resolutions(
    result: MergeResult,
    resolutions: Dict[str, FileSnapshot],
) -> Dict[str, FileSnapshot]:
    """Create a resolved tree after all conflicts have been addressed."""
    if set(resolutions) != {c.path for c in result.conflicts}:
        missing = {c.path for c in result.conflicts} - set(resolutions)
        extra = set(resolutions) - {c.path for c in result.conflicts}
        raise ValueError(f"Resolution mismatch. Missing={missing}, extra={extra}")

    merged = dict(result.merged_tree)

    for path, file_state in resolutions.items():
        if file_state.exists:
            merged[path] = file_state
        else:
            merged.pop(path, None)

    return merged


def demo_resolution() -> None:
    print("\n=== CONFLICT RESOLUTION ===")

    base = {"settings.ini": snapshot("workers=2\n")}
    ours = {"settings.ini": snapshot("workers=4\n")}
    theirs = {"settings.ini": snapshot("workers=8\n")}

    result = three_way_merge(base, ours, theirs)

    conflict = result.conflicts[0]

    manual = resolve_conflict(
        conflict,
        ResolutionPolicy.MANUAL,
        "workers=6\n",
    )

    resolved_tree = apply_resolutions(
        result,
        {"settings.ini": manual},
    )

    print("Manual resolution:")
    show_snapshot("Resolved tree", resolved_tree)


# ---------------------------------------------------------------------------
# Merge-base and commit graph
# ---------------------------------------------------------------------------

@dataclass
class RepositoryGraph:
    commits: Dict[str, Commit]

    def ancestors(self, commit_id: str) -> set[str]:
        """Return all ancestors, including the supplied commit."""
        visited: set[str] = set()
        stack = [commit_id]

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            commit = self.commits[current]
            stack.extend(commit.parents)

        return visited

    def merge_base(self, ours: str, theirs: str) -> Optional[str]:
        """
        Find a common ancestor.

        Git's actual merge-base selection has nuanced rules for criss-cross
        histories and multiple best common ancestors. This educational
        implementation chooses the first common ancestor with minimum total
        graph distance.
        """
        ours_dist = self._distances(ours)
        theirs_dist = self._distances(theirs)

        common = set(ours_dist) & set(theirs_dist)

        if not common:
            return None

        return min(
            common,
            key=lambda commit_id: (
                ours_dist[commit_id] + theirs_dist[commit_id],
                ours_dist[commit_id],
                commit_id,
            ),
        )

    def _distances(self, start: str) -> Dict[str, int]:
        distances = {start: 0}
        queue = [start]

        while queue:
            current = queue.pop(0)
            current_distance = distances[current]

            for parent in self.commits[current].parents:
                if parent not in distances:
                    distances[parent] = current_distance + 1
                    queue.append(parent)

        return distances


def make_commit(
    message: str,
    parents: Sequence[str],
    tree: Dict[str, FileSnapshot],
) -> Commit:
    serialized = message + "|" + "|".join(
        f"{path}={tree[path].content!r}" for path in sorted(tree)
    )
    commit_id = sha1_text(serialized)[:12]
    return Commit(
        commit_id=commit_id,
        parents=tuple(parents),
        message=message,
        tree=dict(tree),
    )


def demo_merge_base() -> None:
    print("\n=== MERGE BASE ===")

    root = make_commit(
        "initial",
        [],
        {"app.txt": snapshot("version 1\n")},
    )

    main = make_commit(
        "main change",
        [root.commit_id],
        {"app.txt": snapshot("version 2 from main\n")},
    )

    feature = make_commit(
        "feature change",
        [root.commit_id],
        {"app.txt": snapshot("version 2 from feature\n")},
    )

    graph = RepositoryGraph(
        {
            root.commit_id: root,
            main.commit_id: main,
            feature.commit_id: feature,
        }
    )

    base_id = graph.merge_base(main.commit_id, feature.commit_id)

    print(f"Root commit:  {root.commit_id}")
    print(f"Main commit:  {main.commit_id}")
    print(f"Feature:      {feature.commit_id}")
    print(f"Merge base:   {base_id}")


# ---------------------------------------------------------------------------
# Merge strategy simulation
# ---------------------------------------------------------------------------

class MergeStrategy(Enum):
    FAST_FORWARD = "fast-forward"
    THREE_WAY = "three-way"
    OURS = "ours"
    THEIRS = "theirs"


def explain_strategy(strategy: MergeStrategy) -> str:
    explanations = {
        MergeStrategy.FAST_FORWARD:
            "Move the branch pointer when the target is an ancestor of the incoming commit.",
        MergeStrategy.THREE_WAY:
            "Compare merge base, current branch, and incoming branch, then create a merge result.",
        MergeStrategy.OURS:
            "Use an ours-oriented result while recording the merge relationship; this is not the same as resolving every file manually.",
        MergeStrategy.THEIRS:
            "In ordinary conflict-resolution language, choose incoming content. Exact command behavior depends on Git operation and strategy/options.",
    }
    return explanations[strategy]


def demo_strategies() -> None:
    print("\n=== MERGE STRATEGIES ===")

    for strategy in MergeStrategy:
        print(f"{strategy.value:14} -> {explain_strategy(strategy)}")


# ---------------------------------------------------------------------------
# Rebase conceptual model
# ---------------------------------------------------------------------------

def rebase_simulation(
    base_tree: Dict[str, FileSnapshot],
    upstream_tree: Dict[str, FileSnapshot],
    feature_commits: Sequence[Dict[str, FileSnapshot]],
) -> List[Dict[str, FileSnapshot]]:
    """
    Educational rebase model.

    A rebase conceptually replays feature commits on top of a new upstream
    base. Real Git creates new commit objects with new identities.
    """
    current = dict(upstream_tree)
    replayed: List[Dict[str, FileSnapshot]] = []

    for feature_tree in feature_commits:
        # This simplified demonstration assumes each feature snapshot already
        # describes the resulting tree of a single change.
        result = three_way_merge(base_tree, current, feature_tree)

        if not result.clean:
            raise RuntimeError(
                "A replayed commit would require conflict resolution."
            )

        current = result.merged_tree
        replayed.append(dict(current))

    return replayed


def demo_rebase_model() -> None:
    print("\n=== REBASE CONCEPT ===")

    old_base = {"app.py": snapshot("version=1\n")}
    upstream = {"app.py": snapshot("version=2\n")}
    feature_commit = {"app.py": snapshot("version=3-feature\n")}

    try:
        replayed = rebase_simulation(
            old_base,
            upstream,
            [feature_commit],
        )
        show_snapshot("Replayed feature tree", replayed[-1])
    except RuntimeError as error:
        print(error)


# ---------------------------------------------------------------------------
# Validation after resolution
# ---------------------------------------------------------------------------

def validate_no_conflict_markers(
    tree: Dict[str, FileSnapshot],
) -> List[str]:
    """
    Search for unresolved marker strings.

    This is only a safeguard. A valid source file could theoretically contain
    these strings intentionally, and a file can be semantically incorrect
    without containing markers.
    """
    suspicious = []

    marker_tokens = (
        "<<<<<<<",
        "=======",
        ">>>>>>>",
    )

    for path, state in tree.items():
        if not state.exists:
            continue

        if any(token in state.content for token in marker_tokens):
            suspicious.append(path)

    return suspicious


def validate_python_syntax(source: str) -> Tuple[bool, str]:
    """Compile Python source without executing it."""
    try:
        compile(source, "<merged-file>", "exec")
        return True, "Python syntax is valid."
    except SyntaxError as error:
        return False, (
            f"Syntax error at line {error.lineno}: {error.msg}"
        )


def demo_validation() -> None:
    print("\n=== POST-RESOLUTION VALIDATION ===")

    tree = {
        "good.py": snapshot("value = 42\n"),
        "bad.py": snapshot(
            "<<<<<<< HEAD\nvalue = 1\n=======\nvalue = 2\n>>>>>>> incoming\n"
        ),
    }

    print("Files containing unresolved markers:")
    for path in validate_no_conflict_markers(tree):
        print(f"  - {path}")

    good, message = validate_python_syntax(tree["good.py"].content)
    print(message)

    bad, message = validate_python_syntax(
        "def broken(:\n    pass\n"
    )
    print(message)


# ---------------------------------------------------------------------------
# Rerere concept
# ---------------------------------------------------------------------------

class ConflictResolutionCache:
    """
    Small in-memory model of Git's rerere concept.

    Git can record how a user resolved a conflict and reuse the recorded
    resolution when Git encounters an equivalent conflict later.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}

    @staticmethod
    def conflict_key(conflict: Conflict) -> str:
        material = (
            conflict.path
            + "\0"
            + str(conflict.base.content)
            + "\0"
            + str(conflict.ours.content)
            + "\0"
            + str(conflict.theirs.content)
        )
        return sha1_text(material)

    def record(self, conflict: Conflict, resolution: str) -> None:
        self._cache[self.conflict_key(conflict)] = resolution

    def lookup(self, conflict: Conflict) -> Optional[str]:
        return self._cache.get(self.conflict_key(conflict))


def demo_rerere() -> None:
    print("\n=== RERERE CONCEPT ===")

    base = {"policy.txt": snapshot("mode=standard\n")}
    ours = {"policy.txt": snapshot("mode=fast\n")}
    theirs = {"policy.txt": snapshot("mode=safe\n")}

    result = three_way_merge(base, ours, theirs)
    conflict = result.conflicts[0]

    cache = ConflictResolutionCache()
    cache.record(conflict, "mode=balanced\n")

    repeated_lookup = cache.lookup(conflict)

    print("Recorded resolution:", "mode=balanced")
    print("Reusable resolution:", repeated_lookup.strip() if repeated_lookup else None)


# ---------------------------------------------------------------------------
# Rename detection discussion
# ---------------------------------------------------------------------------

def similarity_ratio(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left, right).ratio()


def demonstrate_rename_detection() -> None:
    print("\n=== RENAME DETECTION MODEL ===")

    old_path = "legacy_config.txt"
    new_path = "config.txt"
    old_content = "timeout=30\nretries=3\n"
    new_content = "timeout=60\nretries=3\n"

    ratio = similarity_ratio(old_content, new_content)

    print(f"Old path: {old_path}")
    print(f"New path: {new_path}")
    print(f"Content similarity: {ratio:.3f}")
    print(
        "Git can detect renames by comparing deleted and added paths. "
        "Rename detection is a similarity-based inference rather than a "
        "special immutable rename object."
    )


# ---------------------------------------------------------------------------
# Real Git command integration
# ---------------------------------------------------------------------------

def run_git_command(
    args: Sequence[str],
    cwd: Optional[Path] = None,
) -> Tuple[int, str, str]:
    """Run Git safely without invoking a shell."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "Git executable was not found."

    return completed.returncode, completed.stdout, completed.stderr


def inspect_real_repository(repository: Path) -> None:
    """
    Display useful conflict diagnostics for an existing Git repository.

    The function does not modify the repository.
    """
    print("\n=== REAL REPOSITORY INSPECTION ===")
    print(f"Repository: {repository}")

    commands = [
        ["status", "--short", "--branch"],
        ["diff", "--name-only", "--diff-filter=U"],
        ["branch", "--show-current"],
    ]

    for command in commands:
        code, stdout, stderr = run_git_command(command, repository)
        print(f"\n$ git {' '.join(command)}")
        if stdout.strip():
            print(stdout.rstrip())
        if stderr.strip():
            print(stderr.rstrip())
        print(f"exit code: {code}")


def create_temporary_conflict_repository() -> Path:
    """
    Build a small real repository to demonstrate an actual Git conflict.

    The caller owns the temporary directory and should remove it when done.
    """
    temporary_directory = Path(tempfile.mkdtemp(prefix="git-conflict-demo-"))

    commands = [
        ["init", "-b", "main"],
        ["config", "user.name", "Git Conflict Demo"],
        ["config", "user.email", "demo@example.invalid"],
    ]

    for command in commands:
        code, _, stderr = run_git_command(command, temporary_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or "Git command failed.")

    (temporary_directory / "settings.txt").write_text(
        "timeout=30\n",
        encoding="utf-8",
    )

    for command in (
        ["add", "settings.txt"],
        ["commit", "-m", "Initial settings"],
        ["switch", "-c", "feature"],
    ):
        code, _, stderr = run_git_command(command, temporary_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or "Git command failed.")

    (temporary_directory / "settings.txt").write_text(
        "timeout=60\n",
        encoding="utf-8",
    )

    for command in (
        ["add", "settings.txt"],
        ["commit", "-m", "Feature timeout"],
        ["switch", "main"],
    ):
        code, _, stderr = run_git_command(command, temporary_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or "Git command failed.")

    (temporary_directory / "settings.txt").write_text(
        "timeout=120\n",
        encoding="utf-8",
    )

    for command in (
        ["add", "settings.txt"],
        ["commit", "-m", "Main timeout"],
    ):
        code, _, stderr = run_git_command(command, temporary_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or "Git command failed.")

    return temporary_directory


def demonstrate_real_git_conflict() -> None:
    """
    Create and inspect a genuine Git conflict.

    This section is intentionally optional and only runs when explicitly
    enabled through the environment variable RUN_REAL_GIT_DEMO=1.
    """
    if os.environ.get("RUN_REAL_GIT_DEMO") != "1":
        print(
            "\nReal Git demo skipped. Set RUN_REAL_GIT_DEMO=1 to run it."
        )
        return

    repository = create_temporary_conflict_repository()

    try:
        code, stdout, stderr = run_git_command(
            ["merge", "feature"],
            repository,
        )

        print("\n=== ACTUAL GIT MERGE ===")
        print(f"merge exit code: {code}")

        if stdout.strip():
            print(stdout.rstrip())

        if stderr.strip():
            print(stderr.rstrip())

        inspect_real_repository(repository)

        code, stdout, stderr = run_git_command(
            ["diff", "--", "settings.txt"],
            repository,
        )

        print("\n=== ACTUAL CONFLICT DIFF ===")
        if stdout.strip():
            print(stdout.rstrip())
        if stderr.strip():
            print(stderr.rstrip())

        # Abort so this educational demonstration leaves no conflicted
        # repository state behind inside the temporary directory.
        run_git_command(["merge", "--abort"], repository)
    finally:
        # The temporary repository is deliberately left on disk so that the
        # user can inspect it after the program exits.
        print(f"\nTemporary repository retained at: {repository}")


# ---------------------------------------------------------------------------
# Educational tests
# ---------------------------------------------------------------------------

def test_clean_merge() -> None:
    base = {"a.txt": snapshot("base\n")}
    ours = {"a.txt": snapshot("ours\n")}
    theirs = {"a.txt": snapshot("base\n")}

    result = three_way_merge(base, ours, theirs)

    assert result.clean
    assert result.merged_tree["a.txt"].content == "ours\n"


def test_same_change_merges_cleanly() -> None:
    base = {"a.txt": snapshot("base\n")}
    ours = {"a.txt": snapshot("same\n")}
    theirs = {"a.txt": snapshot("same\n")}

    result = three_way_merge(base, ours, theirs)

    assert result.clean
    assert result.merged_tree["a.txt"].content == "same\n"


def test_content_conflict_is_detected() -> None:
    base = {"a.txt": snapshot("base\n")}
    ours = {"a.txt": snapshot("ours\n")}
    theirs = {"a.txt": snapshot("theirs\n")}

    result = three_way_merge(base, ours, theirs)

    assert not result.clean
    assert result.conflicts[0].conflict_type == "content"


def test_add_add_conflict_is_detected() -> None:
    base = {}
    ours = {"new.txt": snapshot("ours\n")}
    theirs = {"new.txt": snapshot("theirs\n")}

    result = three_way_merge(base, ours, theirs)

    assert not result.clean
    assert result.conflicts[0].conflict_type == "add/add"


def test_delete_modify_conflict_is_detected() -> None:
    base = {"a.txt": snapshot("base\n")}
    ours = {}
    theirs = {"a.txt": snapshot("changed\n")}

    result = three_way_merge(base, ours, theirs)

    assert not result.clean
    assert result.conflicts[0].conflict_type == "delete/modify"


def run_tests() -> None:
    print("\n=== BUILT-IN TESTS ===")

    tests = [
        test_clean_merge,
        test_same_change_merges_cleanly,
        test_content_conflict_is_detected,
        test_add_add_conflict_is_detected,
        test_delete_modify_conflict_is_detected,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print(f"{len(tests)} tests passed.")


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("GIT CONFLICTS: DETECTION, RESOLUTION, AND MERGE STRATEGIES")
    print("=" * 78)

    print(
        "\nCore principle: a merge conflict is not simply 'two people edited "
        "a file'. It occurs when Git cannot safely combine the resulting "
        "changes from the merge base using its available merge rules."
    )

    demo_clean_three_way_merge()
    demo_content_conflict()
    demo_line_level_reasoning()
    demo_conflict_types()
    demo_resolution()
    demo_merge_base()
    demo_strategies()
    demo_rebase_model()
    demo_validation()
    demo_rerere()
    demonstrate_rename_detection()
    run_tests()
    demonstrate_real_git_conflict()

    print("\n=== PRACTICAL DIAGNOSTIC COMMANDS ===")
    print("git status")
    print("git diff")
    print("git diff --cc")
    print("git diff --name-only --diff-filter=U")
    print("git ls-files -u")
    print("git merge --abort")
    print("git add <resolved-file>")
    print("git commit")
    print("git merge --continue")
    print("git rebase --abort")
    print("git rebase --continue")

    print("\nThe program completed without modifying a normal repository.")


if __name__ == "__main__":
    main()

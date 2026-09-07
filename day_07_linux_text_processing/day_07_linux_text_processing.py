#!/usr/bin/env python3
"""
Linux Text Processing: grep, sort, uniq, cut, awk, sed, xargs

This self-contained Python script teaches common Linux command-line text
processing tools through executable simulations and demonstrations.

The script does not require Linux or external Python packages. It implements
small educational equivalents of selected behaviors so the concepts can be
studied on any system.

Covered tools:
    - grep
    - sort
    - uniq
    - cut
    - awk
    - sed
    - xargs

The demonstrations use Python to model important command-line behavior,
including pipelines, regular expressions, field processing, filtering,
sorting, grouping, substitution, and command argument construction.

Important:
    These Python implementations are educational simulations, not complete
    replacements for GNU grep, GNU sort, awk, sed, or xargs.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional, Sequence


# =============================================================================
# SAMPLE DATA
# =============================================================================

EMPLOYEES = """\
id,name,department,salary,city
101,Alice,Engineering,85000,Delhi
102,Bob,Sales,65000,Mumbai
103,Charlie,Engineering,92000,Bengaluru
104,Diana,HR,70000,Delhi
105,Eve,Sales,65000,Mumbai
106,Frank,Engineering,78000,Chennai
107,Grace,HR,72000,Pune
108,Heidi,Engineering,92000,Bengaluru
"""

LOGS = """\
2026-09-01 INFO Server started
2026-09-01 INFO User login user=alice
2026-09-01 ERROR Database connection failed
2026-09-01 WARNING Disk usage at 85 percent
2026-09-02 INFO User login user=bob
2026-09-02 ERROR Invalid password user=unknown
2026-09-02 INFO Server stopped
2026-09-03 ERROR Database connection failed
"""

MESSY_NAMES = """\
alice
Bob
charlie
Alice
bob
ALICE
Bob
"""

WORDS = """\
apple
banana
apple
orange
banana
apple
grape
orange
"""


def section(title: str) -> None:
    """Print a clearly separated section."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def show_lines(lines: Iterable[str]) -> None:
    """Print lines without adding extra blank lines."""
    for line in lines:
        print(line)


def split_text(text: str) -> list[str]:
    """Convert multiline text into a list of lines."""
    return text.rstrip("\n").splitlines()


# =============================================================================
# 1. THE UNIX TEXT PROCESSING MODEL
# =============================================================================

def demonstrate_unix_pipeline_model() -> None:
    section("1. UNIX TEXT PROCESSING MODEL")

    print(
        """
Linux text processing commonly follows a pipeline model:

    input -> command -> command -> command -> output

Each command usually performs one focused transformation. The output of one
command can become the input of the next command.

Typical shell pipeline:

    cat employees.csv | grep Engineering | sort | uniq

The Python demonstrations below model the same idea using functions and
iterables.
""".strip()
    )

    lines = split_text(EMPLOYEES)

    def contains_engineering(items: Iterable[str]) -> Iterator[str]:
        for item in items:
            if "Engineering" in item:
                yield item

    pipeline_result = sorted(contains_engineering(lines))

    print("\nPipeline result:")
    show_lines(pipeline_result)


# =============================================================================
# 2. GREP
# =============================================================================

@dataclass
class GrepOptions:
    ignore_case: bool = False
    invert_match: bool = False
    line_numbers: bool = False
    count_only: bool = False
    whole_word: bool = False
    fixed_string: bool = False


def grep(
    pattern: str,
    lines: Iterable[str],
    options: Optional[GrepOptions] = None,
) -> list[str] | int:
    """
    Educational grep implementation.

    Supported ideas:
        - Regular expression matching
        - Fixed-string matching
        - Case-insensitive matching
        - Inverted matching
        - Line numbering
        - Match counting
        - Whole-word matching
    """
    if options is None:
        options = GrepOptions()

    flags = re.IGNORECASE if options.ignore_case else 0

    if options.fixed_string:
        search_pattern = re.escape(pattern)
    else:
        search_pattern = pattern

    if options.whole_word:
        search_pattern = r"\b(?:" + search_pattern + r")\b"

    regex = re.compile(search_pattern, flags)

    results: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        matched = regex.search(line) is not None

        if options.invert_match:
            matched = not matched

        if matched:
            if options.line_numbers:
                results.append(f"{line_number}:{line}")
            else:
                results.append(line)

    if options.count_only:
        return len(results)

    return results


def demonstrate_grep() -> None:
    section("2. grep: SEARCHING AND FILTERING TEXT")

    lines = split_text(LOGS)

    print("\nBasic search: grep ERROR")
    show_lines(grep("ERROR", lines))

    print("\nCase-insensitive search: grep -i error")
    show_lines(
        grep(
            "error",
            lines,
            GrepOptions(ignore_case=True),
        )
    )

    print("\nInverse matching: grep -v ERROR")
    show_lines(
        grep(
            "ERROR",
            lines,
            GrepOptions(invert_match=True),
        )
    )

    print("\nLine numbers: grep -n ERROR")
    show_lines(
        grep(
            "ERROR",
            lines,
            GrepOptions(line_numbers=True),
        )
    )

    print("\nCount matching lines: grep -c ERROR")
    count = grep(
        "ERROR",
        lines,
        GrepOptions(count_only=True),
    )
    print(count)

    print("\nRegular expression: lines containing INFO or WARNING")
    show_lines(grep(r"INFO|WARNING", lines))

    print("\nWhole-word matching:")
    whole_word_lines = [
        "cat",
        "concatenate",
        "a cat sleeps",
        "category",
    ]
    show_lines(
        grep(
            "cat",
            whole_word_lines,
            GrepOptions(whole_word=True),
        )
    )

    print(
        """
Important grep concepts:

- A pattern can be a literal string or a regular expression.
- grep normally prints entire matching lines, not only the matched substring.
- grep -v selects lines that do not match.
- grep -i ignores letter case.
- grep -n adds input line numbers.
- grep -c counts matching lines.
- Regular expressions can introduce special meanings for characters such as:
  .  *  +  ?  ^  $  [ ]  ( )  |

A common mistake is assuming all grep implementations support identical
regular expression features. Basic grep, extended grep, and Perl-compatible
grep modes can differ.
""".strip()
    )


# =============================================================================
# 3. SORT
# =============================================================================

def sort_lines(
    lines: Iterable[str],
    reverse: bool = False,
    numeric: bool = False,
    case_insensitive: bool = False,
    unique: bool = False,
    key_function: Optional[Callable[[str], object]] = None,
) -> list[str]:
    """
    Educational sorting function.

    Demonstrates:
        - Lexicographic sorting
        - Numeric sorting
        - Reverse sorting
        - Case-insensitive sorting
        - Unique output
        - Custom key extraction
    """
    values = list(lines)

    if key_function is not None:
        values.sort(key=key_function, reverse=reverse)

    elif numeric:
        def numeric_key(value: str) -> float:
            try:
                return float(value)
            except ValueError:
                return float("inf")

        values.sort(key=numeric_key, reverse=reverse)

    elif case_insensitive:
        values.sort(key=str.casefold, reverse=reverse)

    else:
        values.sort(reverse=reverse)

    if unique:
        deduplicated: list[str] = []
        previous: Optional[str] = None

        for value in values:
            if value != previous:
                deduplicated.append(value)
                previous = value

        return deduplicated

    return values


def demonstrate_sort() -> None:
    section("3. sort: ORDERING TEXT")

    values = ["100", "20", "3", "11", "2"]

    print("\nLexicographic sorting:")
    print(sort_lines(values))

    print("\nNumeric sorting:")
    print(sort_lines(values, numeric=True))

    names = ["alice", "Bob", "charlie", "Alice", "bob"]

    print("\nDefault case-sensitive sorting:")
    print(sort_lines(names))

    print("\nCase-insensitive sorting:")
    print(sort_lines(names, case_insensitive=True))

    print("\nReverse numeric sorting:")
    print(sort_lines(values, numeric=True, reverse=True))

    print("\nSort employees by salary, descending:")

    employee_lines = split_text(EMPLOYEES)
    header = employee_lines[0]
    records = employee_lines[1:]

    sorted_records = sort_lines(
        records,
        reverse=True,
        key_function=lambda row: int(row.split(",")[3]),
    )

    print(header)
    show_lines(sorted_records)

    print(
        """
Important distinction:

Lexicographic sorting compares characters.

    "100" < "20"

because character "1" is compared with character "2".

Numeric sorting compares numerical values.

    20 < 100

In shell usage, sort -n is commonly required for numbers.

Common mistakes:
- Sorting numeric data without numeric mode.
- Forgetting that locale settings can influence textual ordering.
- Assuming sort removes duplicates automatically.

sort and uniq are frequently used together:

    sort input.txt | uniq
""".strip()
    )


# =============================================================================
# 4. UNIQ
# =============================================================================

def uniq(
    lines: Iterable[str],
    count: bool = False,
    repeated_only: bool = False,
    unique_only: bool = False,
    ignore_case: bool = False,
) -> list[str]:
    """
    Educational uniq implementation.

    uniq removes or analyzes adjacent duplicate lines.

    This adjacency rule is essential:
        uniq does not detect duplicate lines separated by other lines unless
        the input is sorted or otherwise grouped first.
    """
    values = list(lines)

    def normalize(value: str) -> str:
        return value.casefold() if ignore_case else value

    grouped: list[tuple[str, int]] = []

    if not values:
        return []

    current = values[0]
    current_normalized = normalize(current)
    current_count = 1

    for value in values[1:]:
        normalized = normalize(value)

        if normalized == current_normalized:
            current_count += 1
        else:
            grouped.append((current, current_count))
            current = value
            current_normalized = normalized
            current_count = 1

    grouped.append((current, current_count))

    results: list[str] = []

    for value, occurrences in grouped:
        if repeated_only and occurrences < 2:
            continue

        if unique_only and occurrences != 1:
            continue

        if count:
            results.append(f"{occurrences:7d} {value}")
        else:
            results.append(value)

    return results


def demonstrate_uniq() -> None:
    section("4. uniq: HANDLING ADJACENT DUPLICATES")

    unsorted_words = split_text(WORDS)

    print("\nOriginal input:")
    show_lines(unsorted_words)

    print("\nuniq without sorting:")
    show_lines(uniq(unsorted_words))

    print("\nsort | uniq:")
    sorted_words = sort_lines(unsorted_words)
    show_lines(uniq(sorted_words))

    print("\nsort | uniq -c:")
    show_lines(uniq(sorted_words, count=True))

    print("\nsort | uniq -d, repeated values only:")
    show_lines(uniq(sorted_words, repeated_only=True))

    print("\nsort | uniq -u, values appearing once:")
    show_lines(uniq(sorted_words, unique_only=True))

    print(
        """
The key behavior is adjacency.

Given:

    apple
    banana
    apple

uniq sees two separate apple groups and does not know that they represent the
same value globally.

The standard pattern is:

    sort input.txt | uniq

For frequency analysis:

    sort input.txt | uniq -c | sort -nr

This pattern groups equal values, counts each group, and then sorts counts in
descending numeric order.
""".strip()
    )


# =============================================================================
# 5. CUT
# =============================================================================

def parse_field_list(specification: str) -> list[int]:
    """
    Parse a simple cut-style field specification.

    Supported examples:
        1
        1,3,5
        2-4
        1,3-5
    """
    fields: list[int] = []

    for part in specification.split(","):
        part = part.strip()

        if not part:
            raise ValueError("Empty field specification")

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)

            if start < 1 or end < start:
                raise ValueError(f"Invalid field range: {part}")

            fields.extend(range(start, end + 1))

        else:
            field = int(part)

            if field < 1:
                raise ValueError("Field numbers start at 1")

            fields.append(field)

    return fields


def cut_fields(
    lines: Iterable[str],
    delimiter: str,
    fields: str,
    only_delimited: bool = False,
) -> list[str]:
    """
    Educational simulation of cut -d DELIMITER -f FIELDS.

    Field numbering begins at 1.
    """
    requested_fields = parse_field_list(fields)
    results: list[str] = []

    for line in lines:
        if delimiter not in line:
            if only_delimited:
                continue
            results.append(line)
            continue

        parts = line.split(delimiter)

        selected = [
            parts[index - 1]
            for index in requested_fields
            if index <= len(parts)
        ]

        results.append(delimiter.join(selected))

    return results


def cut_characters(
    lines: Iterable[str],
    positions: str,
) -> list[str]:
    """
    Educational simulation of cut -c using character positions.
    """
    requested_positions = parse_field_list(positions)
    results: list[str] = []

    for line in lines:
        selected = [
            line[position - 1]
            for position in requested_positions
            if position <= len(line)
        ]
        results.append("".join(selected))

    return results


def demonstrate_cut() -> None:
    section("5. cut: EXTRACTING FIELDS AND CHARACTERS")

    employee_lines = split_text(EMPLOYEES)

    print("\nExtract fields 2 and 3 from CSV:")
    show_lines(
        cut_fields(
            employee_lines,
            delimiter=",",
            fields="2,3",
        )
    )

    print("\nExtract fields 2 through 4:")
    show_lines(
        cut_fields(
            employee_lines,
            delimiter=",",
            fields="2-4",
        )
    )

    print("\nCharacter extraction:")
    examples = ["abcdef", "Linux", "Text Processing"]
    show_lines(cut_characters(examples, "1-3,6"))

    print(
        """
cut is designed for simple positional extraction.

Typical shell forms:

    cut -d ',' -f 1,3 file.csv
    cut -d ':' -f 1 /etc/passwd
    cut -c 1-10 file.txt

Limitations:

cut is not a complete CSV parser. A CSV value may legally contain commas inside
quoted fields. A simple delimiter split will interpret those commas incorrectly.

For complex structured formats, a format-aware parser is safer.
""".strip()
    )


# =============================================================================
# 6. AWK FUNDAMENTALS
# =============================================================================

@dataclass
class AwkRecord:
    """
    Represents one input record and its fields.

    In traditional awk terminology:
        $0  -> complete record
        $1  -> first field
        $2  -> second field
        NF  -> number of fields
        NR  -> record number
    """

    text: str
    fields: list[str]
    record_number: int

    @property
    def nf(self) -> int:
        return len(self.fields)

    def field(self, number: int) -> str:
        """
        Return an awk-style field.

        field(0) returns the entire record.
        """
        if number == 0:
            return self.text

        if number < 1 or number > len(self.fields):
            return ""

        return self.fields[number - 1]


def awk_records(
    lines: Iterable[str],
    field_separator_pattern: str = r"\s+",
) -> Iterator[AwkRecord]:
    """
    Convert lines into awk-style records.

    The default separator is whitespace.
    """
    separator = re.compile(field_separator_pattern)

    for number, line in enumerate(lines, start=1):
        if field_separator_pattern == r"\s+":
            fields = line.split()
        else:
            fields = separator.split(line)

        yield AwkRecord(
            text=line,
            fields=fields,
            record_number=number,
        )


def demonstrate_awk_fundamentals() -> None:
    section("6. awk: RECORDS, FIELDS, CONDITIONS, AND ACTIONS")

    print("\nInput log records with default whitespace fields:")

    for record in list(awk_records(split_text(LOGS)))[:3]:
        print(
            f"NR={record.record_number}, "
            f"$0={record.field(0)!r}, "
            f"$1={record.field(1)!r}, "
            f"$2={record.field(2)!r}, "
            f"NF={record.nf}"
        )

    print("\nEquivalent concept to: awk '/ERROR/ { print $1, $2, $3 }'")

    for record in awk_records(split_text(LOGS)):
        if record.field(3) == "ERROR":
            print(
                record.field(1),
                record.field(2),
                record.field(3),
            )

    print("\nProcess CSV data with comma as field separator:")

    for record in awk_records(
        split_text(EMPLOYEES)[1:],
        field_separator_pattern=",",
    ):
        name = record.field(2)
        department = record.field(3)
        salary = int(record.field(4))

        if department == "Engineering" and salary >= 85000:
            print(
                f"{name} earns {salary} in {department}"
            )

    print(
        """
The conceptual awk model is:

    pattern { action }

The action runs for records matching the pattern.

Examples of patterns:
- Regular expression matching
- Numeric comparisons
- String comparisons
- Arbitrary expressions

Examples of actions:
- Print selected fields
- Perform arithmetic
- Update counters
- Transform fields
- Produce reports

awk is especially powerful when each input line contains structured fields.
""".strip()
    )


# =============================================================================
# 7. AWK AGGREGATION
# =============================================================================

def demonstrate_awk_aggregation() -> None:
    section("7. awk: AGGREGATION AND REPORTING")

    records = list(
        awk_records(
            split_text(EMPLOYEES)[1:],
            field_separator_pattern=",",
        )
    )

    total_salary = 0
    employee_count = 0

    for record in records:
        total_salary += int(record.field(4))
        employee_count += 1

    average_salary = total_salary / employee_count

    print(f"\nTotal salary: {total_salary}")
    print(f"Employee count: {employee_count}")
    print(f"Average salary: {average_salary:.2f}")

    department_totals: defaultdict[str, int] = defaultdict(int)
    department_counts: defaultdict[str, int] = defaultdict(int)

    for record in records:
        department = record.field(3)
        salary = int(record.field(4))

        department_totals[department] += salary
        department_counts[department] += 1

    print("\nAverage salary by department:")

    for department in sorted(department_totals):
        average = (
            department_totals[department]
            / department_counts[department]
        )
        print(f"{department}: {average:.2f}")

    print(
        """
This models a common awk pattern:

- Initialize accumulators.
- Process every record.
- Update totals and counters.
- Produce final output after all input has been processed.

In actual awk, BEGIN and END blocks support initialization and final reporting.

Conceptually:

    BEGIN { initialize variables }

    { process each record }

    END { print final report }
""".strip()
    )


# =============================================================================
# 8. AWK ASSOCIATIVE ARRAYS
# =============================================================================

def demonstrate_awk_associative_arrays() -> None:
    section("8. awk: GROUPING WITH ASSOCIATIVE ARRAYS")

    records = list(
        awk_records(
            split_text(EMPLOYEES)[1:],
            field_separator_pattern=",",
        )
    )

    city_counts: defaultdict[str, int] = defaultdict(int)

    for record in records:
        city = record.field(5)
        city_counts[city] += 1

    print("\nEmployees by city:")

    for city, count in sorted(city_counts.items()):
        print(f"{city}: {count}")

    print(
        """
awk associative arrays are conceptually similar to Python dictionaries.

For example, an awk counting pattern can be expressed conceptually as:

    count[$3]++

Each distinct field value becomes a key.

This is useful for:
- Frequency analysis
- Grouped totals
- Histograms
- Category-based reports
- Duplicate detection
""".strip()
    )


# =============================================================================
# 9. SED FUNDAMENTALS
# =============================================================================

def sed_substitute(
    lines: Iterable[str],
    pattern: str,
    replacement: str,
    global_replace: bool = False,
    ignore_case: bool = False,
) -> list[str]:
    """
    Educational simulation of sed substitution.

    Concept:
        sed 's/pattern/replacement/'
        sed 's/pattern/replacement/g'
    """
    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    count = 0 if global_replace else 1

    return [
        regex.sub(replacement, line, count=count)
        for line in lines
    ]


def sed_delete(
    lines: Iterable[str],
    pattern: str,
) -> list[str]:
    """
    Simulate deleting lines matching a pattern.

    Concept:
        sed '/pattern/d'
    """
    regex = re.compile(pattern)
    return [
        line
        for line in lines
        if regex.search(line) is None
    ]


def sed_replace_line_number(
    lines: Iterable[str],
    line_number: int,
    replacement: str,
) -> list[str]:
    """
    Replace one specific line.

    Conceptually similar to a sed address followed by c.
    """
    results = list(lines)

    if 1 <= line_number <= len(results):
        results[line_number - 1] = replacement

    return results


def demonstrate_sed() -> None:
    section("9. sed: STREAM EDITING")

    text = [
        "color color color",
        "The server is running",
        "ERROR something failed",
        "INFO request completed",
    ]

    print("\nReplace first occurrence only:")
    show_lines(
        sed_substitute(
            text,
            pattern="color",
            replacement="colour",
        )
    )

    print("\nReplace all occurrences:")
    show_lines(
        sed_substitute(
            text,
            pattern="color",
            replacement="colour",
            global_replace=True,
        )
    )

    print("\nDelete ERROR lines:")
    show_lines(
        sed_delete(
            text,
            pattern="ERROR",
        )
    )

    print("\nReplace line 2:")
    show_lines(
        sed_replace_line_number(
            text,
            line_number=2,
            replacement="The server is healthy",
        )
    )

    print(
        """
sed processes text as a stream and applies editing commands.

A classic substitution command has the form:

    s/pattern/replacement/flags

Common flags include:
- g: replace all occurrences on the line
- i: case-insensitive matching in implementations supporting this extension

sed is particularly useful for:
- Search and replacement
- Removing matching lines
- Editing selected line ranges
- Automated configuration transformations
- Stream transformations in pipelines

Important limitation:
sed commands and extensions can vary between GNU sed, BSD sed, and other
implementations. Scripts intended for multiple systems should avoid assuming
non-portable extensions unless portability is handled explicitly.
""".strip()
    )


# =============================================================================
# 10. SED ADDRESSING AND RANGE PROCESSING
# =============================================================================

def sed_print_range(
    lines: Iterable[str],
    start: int,
    end: int,
) -> list[str]:
    """Return an inclusive line-number range."""
    values = list(lines)

    if start < 1 or end < start:
        raise ValueError("Invalid line range")

    return values[start - 1:end]


def sed_delete_range(
    lines: Iterable[str],
    start: int,
    end: int,
) -> list[str]:
    """Delete an inclusive line-number range."""
    values = list(lines)

    if start < 1 or end < start:
        raise ValueError("Invalid line range")

    return [
        line
        for number, line in enumerate(values, start=1)
        if not start <= number <= end
    ]


def demonstrate_sed_ranges() -> None:
    section("10. sed: ADDRESSES AND LINE RANGES")

    lines = [
        "line 1",
        "line 2",
        "line 3",
        "line 4",
        "line 5",
        "line 6",
    ]

    print("\nPrint lines 2 through 4:")
    show_lines(sed_print_range(lines, 2, 4))

    print("\nDelete lines 2 through 4:")
    show_lines(sed_delete_range(lines, 2, 4))

    print(
        """
sed addresses determine which input lines a command affects.

Addresses may conceptually represent:
- Specific line numbers
- Ranges of line numbers
- Regular expression matches
- Combinations of these forms

Addressing is one of the reasons sed can apply targeted transformations without
loading and manually editing an entire file in an interactive editor.
""".strip()
    )


# =============================================================================
# 11. XARGS
# =============================================================================

def xargs_build_commands(
    input_items: Iterable[str],
    base_command: Sequence[str],
    max_arguments: Optional[int] = None,
    replace_token: Optional[str] = None,
) -> list[list[str]]:
    """
    Educational simulation of selected xargs behavior.

    Two major modes are demonstrated:

    1. Append input items as command arguments.

    2. Replace a placeholder token for each input item.

    This implementation uses Python lists rather than shell execution to make
    command construction visible.
    """
    items = list(input_items)

    if replace_token is not None:
        commands: list[list[str]] = []

        for item in items:
            command = [
                item if argument == replace_token else argument
                for argument in base_command
            ]
            commands.append(command)

        return commands

    if max_arguments is None or max_arguments <= 0:
        return [list(base_command) + items]

    commands = []

    for start in range(0, len(items), max_arguments):
        group = items[start:start + max_arguments]
        commands.append(list(base_command) + group)

    return commands


def demonstrate_xargs() -> None:
    section("11. xargs: CONVERTING INPUT INTO COMMAND ARGUMENTS")

    files = [
        "report one.txt",
        "report two.txt",
        "report three.txt",
        "report four.txt",
        "report five.txt",
    ]

    print("\nAppend all items to a command:")
    commands = xargs_build_commands(
        files,
        base_command=["echo"],
    )

    for command in commands:
        print(command)

    print("\nLimit each command to two input arguments:")
    commands = xargs_build_commands(
        files,
        base_command=["echo"],
        max_arguments=2,
    )

    for command in commands:
        print(command)

    print("\nReplace placeholder for each item:")
    commands = xargs_build_commands(
        files,
        base_command=["process-file", "{}"],
        replace_token="{}",
    )

    for command in commands:
        print(command)

    print(
        """
xargs converts standard input into command arguments.

Conceptual shell examples:

    printf '%s\\n' file1 file2 file3 | xargs rm

    printf '%s\\n' file1 file2 | xargs -n 1 echo

    printf '%s\\n' file1 file2 | xargs -I {} echo Processing {}

A major security and correctness concern is input parsing.

Filenames can contain:
- Spaces
- Tabs
- Quotes
- Wildcards
- Newlines

For arbitrary filenames, null-delimited processing is safer:

    producer -print0 | xargs -0 command

This avoids treating whitespace as a filename separator.
""".strip()
    )


# =============================================================================
# 12. XARGS AND SAFE COMMAND EXECUTION
# =============================================================================

def safe_subprocess_example() -> None:
    section("12. xargs CONCEPTS: SAFE COMMAND EXECUTION")

    filenames = [
        "normal.txt",
        "file with spaces.txt",
        "dangerous;name.txt",
    ]

    print("\nSafe Python subprocess argument construction:")

    for filename in filenames:
        command = ["echo", "Processing:", filename]

        # shell=False means the shell does not interpret semicolons, spaces,
        # command substitutions, or other shell metacharacters.
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            shell=False,
        )

        print(completed.stdout.strip())

    print(
        """
Security principle:

Do not construct shell commands by concatenating untrusted text.

Unsafe conceptual pattern:

    command = "rm " + filename

If the resulting string is executed through a shell, shell metacharacters may
change the meaning of the command.

Safer pattern:

    subprocess.run(["rm", filename], shell=False)

The same principle applies when xargs is part of a pipeline: understand whether
input is merely an argument or can be interpreted by an additional shell layer.
""".strip()
    )


# =============================================================================
# 13. COMBINING grep, sort, uniq, cut, awk, sed, AND xargs
# =============================================================================

def demonstrate_combined_pipeline() -> None:
    section("13. COMBINING TOOLS INTO PIPELINES")

    employee_lines = split_text(EMPLOYEES)[1:]

    print("\nGoal: count employees in each department.")

    # Conceptual shell pipeline:
    #
    # cut -d ',' -f 3 employees.csv | sort | uniq -c

    departments = cut_fields(
        employee_lines,
        delimiter=",",
        fields="3",
    )

    sorted_departments = sort_lines(departments)

    department_counts = uniq(
        sorted_departments,
        count=True,
    )

    print("\nPipeline output:")
    show_lines(department_counts)

    print(
        """
Another goal: find ERROR messages and count each distinct message.

Conceptual process:
1. grep ERROR
2. Extract relevant fields
3. sort
4. uniq -c
5. Sort counts numerically

Python model follows.
""".strip()
    )

    error_lines = grep("ERROR", split_text(LOGS))
    messages = [
        " ".join(line.split()[3:])
        for line in error_lines
    ]

    counted = Counter(messages)

    ranked = sorted(
        counted.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )

    print("\nError frequency report:")
    for message, count in ranked:
        print(f"{count:7d} {message}")


# =============================================================================
# 14. PRACTICAL LOG ANALYSIS
# =============================================================================

def demonstrate_log_analysis() -> None:
    section("14. PRACTICAL APPLICATION: LOG ANALYSIS")

    lines = split_text(LOGS)

    # Filter error records.
    error_lines = grep(
        "ERROR",
        lines,
    )

    print("\nAll ERROR records:")
    show_lines(error_lines)

    # Extract dates and count errors per date.
    error_dates = [
        line.split()[0]
        for line in error_lines
    ]

    counts = Counter(error_dates)

    print("\nErrors by date:")
    for date in sorted(counts):
        print(f"{date}: {counts[date]}")

    # Extract unique error messages.
    error_messages = [
        " ".join(line.split()[3:])
        for line in error_lines
    ]

    print("\nUnique error messages with frequency:")
    for message, count in Counter(error_messages).most_common():
        print(f"{count:7d} {message}")


# =============================================================================
# 15. PRACTICAL CSV ANALYSIS
# =============================================================================

def demonstrate_csv_analysis() -> None:
    section("15. PRACTICAL APPLICATION: STRUCTURED DATA ANALYSIS")

    lines = split_text(EMPLOYEES)
    header = lines[0]
    records = lines[1:]

    print("\nOriginal header:")
    print(header)

    print("\nEmployees earning at least 80000:")

    selected: list[str] = []

    for record in records:
        fields = record.split(",")
        salary = int(fields[3])

        if salary >= 80000:
            selected.append(record)

    print(header)
    show_lines(selected)

    print("\nSort selected employees by name:")
    sorted_selected = sort_lines(
        selected,
        key_function=lambda row: row.split(",")[1],
    )
    show_lines(sorted_selected)

    print("\nCities represented among high earners:")
    cities = [
        row.split(",")[4]
        for row in selected
    ]

    show_lines(
        uniq(
            sort_lines(cities),
        )
    )


# =============================================================================
# 16. REGULAR EXPRESSIONS IN TEXT PROCESSING
# =============================================================================

def demonstrate_regular_expressions() -> None:
    section("16. REGULAR EXPRESSIONS USED BY TEXT PROCESSING TOOLS")

    examples = {
        r"^ERROR": "Line begins with ERROR",
        r"ERROR$": "Line ends with ERROR",
        r"ERR.OR": "Any one character replaces the dot",
        r"[0-9]+": "One or more digits",
        r"user=\w+": "user= followed by word characters",
        r"(ERROR|WARNING)": "Either ERROR or WARNING",
    }

    sample_lines = [
        "ERROR connection failed",
        "INFO status=200",
        "WARNING disk space low",
        "user=alice",
        "user=bob",
        "ERROR42",
    ]

    for pattern, meaning in examples.items():
        print(f"\nPattern: {pattern}")
        print(f"Meaning: {meaning}")

        try:
            matches = grep(pattern, sample_lines)
            show_lines(matches)
        except re.error as error:
            print(f"Regex error: {error}")

    print(
        """
Regular expression dialects differ.

grep, sed, and awk may support:
- Basic regular expressions
- Extended regular expressions
- Implementation-specific extensions

A pattern that works in one tool mode may require escaping or rewriting in
another mode.

For portable scripts, test the target environment and avoid assuming that every
regular expression feature is universally available.
""".strip()
    )


# =============================================================================
# 17. COMMON MISTAKES AND EDGE CASES
# =============================================================================

def demonstrate_common_mistakes() -> None:
    section("17. COMMON MISTAKES AND EDGE CASES")

    print("\n1. uniq without sorting:")
    values = ["A", "B", "A", "B", "B"]
    print("Input:", values)
    print("uniq:", uniq(values))
    print("sort | uniq:", uniq(sort_lines(values)))

    print("\n2. Numeric values sorted lexicographically:")
    numbers = ["9", "10", "100", "2"]
    print("Default:", sort_lines(numbers))
    print("Numeric:", sort_lines(numbers, numeric=True))

    print("\n3. cut cannot safely parse complex CSV:")
    complex_csv = '101,"Alice, Smith",Engineering,85000'
    print("Input:", complex_csv)
    print("Simple comma split:", complex_csv.split(","))

    print("\n4. Missing fields:")
    incomplete = ["a,b,c", "d,e", "f"]
    show_lines(
        cut_fields(
            incomplete,
            delimiter=",",
            fields="2,3",
        )
    )

    print("\n5. Empty input:")
    print("grep:", grep("x", []))
    print("sort:", sort_lines([]))
    print("uniq:", uniq([]))

    print("\n6. Regex metacharacters:")
    literal_lines = ["a.b", "acb", "aXb"]
    print("Regex a.b matches:")
    show_lines(grep("a.b", literal_lines))

    print("Fixed string a.b matches:")
    show_lines(
        grep(
            "a.b",
            literal_lines,
            GrepOptions(fixed_string=True),
        )
    )


# =============================================================================
# 18. PERFORMANCE CONSIDERATIONS
# =============================================================================

def demonstrate_performance_considerations() -> None:
    section("18. PERFORMANCE CONSIDERATIONS")

    print(
        """
Important performance characteristics:

grep:
- Usually streams input line by line.
- Can stop early when a consumer terminates the pipeline.
- Fixed-string searches may be faster than complex regular expressions.

sort:
- Sorting generally requires O(n log n) comparisons.
- Large datasets may require temporary files and external sorting.
- Memory usage depends on implementation and available resources.

uniq:
- Usually streams efficiently after equal records are adjacent.
- Global duplicate detection without sorting requires memory proportional to the
  number of distinct values.

cut:
- Simple field extraction is generally inexpensive.
- Complex structured formats require more sophisticated parsers.

awk:
- Suitable for streaming transformations and aggregation.
- Associative arrays can consume substantial memory when the number of unique
  keys is very large.

sed:
- Designed for streaming transformations.
- Some advanced multi-line operations require pattern-space management.

xargs:
- Reduces process creation overhead by grouping multiple input values into one
  command invocation.
- Argument length limits require batching for large input sets.

Pipeline design:
- Filter early when possible.
- Avoid sorting data that can be reduced first.
- Use precise field extraction.
- Avoid unnecessary temporary files when a pipeline is sufficient.
""".strip()
    )


# =============================================================================
# 19. DEBUGGING TEXT PROCESSING PIPELINES
# =============================================================================

def demonstrate_debugging() -> None:
    section("19. DEBUGGING TEXT PROCESSING PIPELINES")

    lines = split_text(EMPLOYEES)[1:]

    print("\nStage 1: Original record count")
    print(len(lines))

    engineering = grep("Engineering", lines)

    print("\nStage 2: Engineering records")
    show_lines(engineering)

    salaries = [
        row.split(",")[3]
        for row in engineering
    ]

    print("\nStage 3: Extracted salaries")
    print(salaries)

    sorted_salaries = sort_lines(
        salaries,
        numeric=True,
    )

    print("\nStage 4: Numeric sort")
    print(sorted_salaries)

    print(
        """
A practical debugging strategy is to inspect pipeline stages independently.

Useful shell debugging habits include:
- Run each command separately.
- Print intermediate output.
- Count records before and after filtering.
- Check delimiters and field numbers.
- Test regular expressions on representative input.
- Inspect whitespace using tools that reveal invisible characters.
- Quote shell variables when their values may contain whitespace.
- Check command exit status.
""".strip()
    )


# =============================================================================
# 20. TEMPORARY FILE AND REAL SUBPROCESS DEMONSTRATION
# =============================================================================

def demonstrate_real_shell_commands_if_available() -> None:
    section("20. OPTIONAL REAL COMMAND DEMONSTRATION")

    required_commands = ["grep", "sort", "uniq", "cut"]

    available = all(
        subprocess.run(
            ["which", command],
            text=True,
            capture_output=True,
            shell=False,
        ).returncode == 0
        for command in required_commands
    )

    if not available:
        print(
            "Required Linux text-processing commands are not all available "
            "in this environment. Educational simulations above remain valid."
        )
        return

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "words.txt")

        with open(path, "w", encoding="utf-8") as file:
            file.write(WORDS)

        print("\nRunning a real pipeline through subprocess:")
        print("grep 'apple' | sort | uniq -c")

        # This uses subprocess pipelines without shell=True.
        grep_process = subprocess.Popen(
            ["grep", "apple", path],
            stdout=subprocess.PIPE,
            text=True,
        )

        sort_process = subprocess.Popen(
            ["sort"],
            stdin=grep_process.stdout,
            stdout=subprocess.PIPE,
            text=True,
        )

        if grep_process.stdout is not None:
            grep_process.stdout.close()

        uniq_process = subprocess.run(
            ["uniq", "-c"],
            stdin=sort_process.stdout,
            text=True,
            capture_output=True,
            check=True,
        )

        if sort_process.stdout is not None:
            sort_process.stdout.close()

        grep_process.wait()
        sort_process.wait()

        print(uniq_process.stdout.rstrip())


# =============================================================================
# 21. ADVANCED PIPELINE DESIGN EXAMPLE
# =============================================================================

def demonstrate_advanced_pipeline_design() -> None:
    section("21. ADVANCED PIPELINE DESIGN EXAMPLE")

    print(
        """
Problem:
Create a report showing the number of employees in each department and city.

Conceptual Unix solution:

1. Remove the CSV header.
2. Extract department and city.
3. Sort the pairs.
4. Count identical pairs.
5. Sort the frequency report.

Python implementation:
""".strip()
    )

    records = split_text(EMPLOYEES)[1:]

    pairs = [
        ",".join([
            row.split(",")[2],
            row.split(",")[4],
        ])
        for row in records
    ]

    sorted_pairs = sort_lines(pairs)

    pair_counts = Counter(sorted_pairs)

    report = sorted(
        pair_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )

    for pair, count in report:
        department, city = pair.split(",")
        print(
            f"{count:3d} employee(s) | "
            f"department={department:<12} | "
            f"city={city}"
        )


# =============================================================================
# 22. TOOL COMPARISON
# =============================================================================

def demonstrate_tool_comparison() -> None:
    section("22. WHEN EACH TOOL IS MOST APPROPRIATE")

    comparisons = [
        (
            "grep",
            "Filter lines by text or regular-expression matches",
            "Searching logs and selecting relevant records",
        ),
        (
            "sort",
            "Order records",
            "Preparing grouped data or producing ordered reports",
        ),
        (
            "uniq",
            "Remove or count adjacent duplicate records",
            "Frequency analysis after sorting",
        ),
        (
            "cut",
            "Extract simple positional fields or character ranges",
            "Colon-separated or delimiter-separated data",
        ),
        (
            "awk",
            "Field-based processing, conditions, arithmetic, and reports",
            "Structured text analysis and aggregation",
        ),
        (
            "sed",
            "Stream-oriented text editing",
            "Substitution, deletion, and automated transformations",
        ),
        (
            "xargs",
            "Convert input into command arguments",
            "Batching command execution over generated item lists",
        ),
    ]

    for tool, purpose, use_case in comparisons:
        print(f"\n{tool}")
        print(f"  Primary purpose: {purpose}")
        print(f"  Typical use:     {use_case}")


# =============================================================================
# 23. BEST PRACTICES
# =============================================================================

def demonstrate_best_practices() -> None:
    section("23. BEST PRACTICES")

    print(
        """
1. Understand input structure before selecting a tool.
   Whitespace-separated, CSV, JSON, and arbitrary binary data require
   different approaches.

2. Quote shell variables and filenames.
   Whitespace and shell metacharacters can change argument boundaries.

3. Prefer null-delimited filename pipelines for arbitrary filenames.

4. Use fixed-string searching when regular expressions are unnecessary.

5. Sort before uniq when global duplicate detection is required.

6. Use numeric sorting for numerical data.

7. Verify field numbering.
   cut and awk field numbers commonly begin at 1.

8. Test pipelines with representative edge cases:
   - Empty lines
   - Missing fields
   - Repeated records
   - Spaces
   - Tabs
   - Special characters
   - Large values
   - Unexpected encodings

9. Avoid parsing complex structured formats with simplistic delimiters.

10. Avoid shell=True when constructing commands from external or untrusted data.

11. Preserve intermediate data while debugging complex pipelines.

12. Consider portability between GNU/Linux, BSD/macOS, and other Unix-like
    environments.
""".strip()
    )


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """
    Run the complete study sequence.

    Each demonstration is intentionally independent enough to be read,
    modified, and executed separately.
    """
    demonstrate_unix_pipeline_model()
    demonstrate_grep()
    demonstrate_sort()
    demonstrate_uniq()
    demonstrate_cut()
    demonstrate_awk_fundamentals()
    demonstrate_awk_aggregation()
    demonstrate_awk_associative_arrays()
    demonstrate_sed()
    demonstrate_sed_ranges()
    demonstrate_xargs()
    safe_subprocess_example()
    demonstrate_combined_pipeline()
    demonstrate_log_analysis()
    demonstrate_csv_analysis()
    demonstrate_regular_expressions()
    demonstrate_common_mistakes()
    demonstrate_performance_considerations()
    demonstrate_debugging()
    demonstrate_real_shell_commands_if_available()
    demonstrate_advanced_pipeline_design()
    demonstrate_tool_comparison()
    demonstrate_best_practices()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Advanced recurrences, recursion trees, and the Master Theorem.

Demonstrates recurrence evaluation, divide-and-conquer algorithms, recursion-tree
cost accounting, Master Theorem cases, and numerical validation.
Uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import ceil, floor, log2
from typing import Callable, Iterable
import sys


class RecurrenceError(ValueError):
    """Raised when a recurrence is malformed or violates its domain."""


@dataclass(frozen=True)
class MasterResult:
    recurrence: str
    case: str
    asymptotic_bound: str
    explanation: str


def validate_integer(value: int, name: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RecurrenceError(f"{name} must be an integer >= {minimum}")


def recurrence_levels(
    a: int, b: float, n: int, leaf_cost: float = 1.0
) -> list[dict[str, float]]:
    """Build a recursion tree for T(n) = aT(n/b) + leaf_cost."""
    validate_integer(a, "a", 1)
    validate_integer(n, "n", 1)
    if b <= 1:
        raise RecurrenceError("b must be greater than 1")
    if leaf_cost < 0:
        raise RecurrenceError("leaf_cost cannot be negative")

    levels: list[dict[str, float]] = []
    nodes = 1
    problem_size = float(n)
    depth = 0

    while problem_size > 1:
        levels.append({
            "depth": depth,
            "nodes": float(nodes),
            "subproblem_size": problem_size,
            "level_work": float(nodes),
        })
        nodes *= a
        problem_size /= b
        depth += 1

    levels.append({
        "depth": depth,
        "nodes": float(nodes),
        "subproblem_size": problem_size,
        "level_work": nodes * leaf_cost,
    })
    return levels


def print_recursion_tree(
    a: int, b: float, n: int, leaf_cost: float = 1.0
) -> None:
    levels = recurrence_levels(a, b, n, leaf_cost)
    print(f"\nRecursion tree: T(n) = {a}T(n/{b:g}) + f(n)")
    print(f"{'Depth':>7} {'Nodes':>12} {'Problem size':>15} {'Level work':>15}")
    for level in levels:
        print(
            f"{int(level['depth']):>7} "
            f"{level['nodes']:>12.0f} "
            f"{level['subproblem_size']:>15.4g} "
            f"{level['level_work']:>15.4g}"
        )


def master_theorem(
    a: int,
    b: float,
    k: float,
    logarithmic_power: float = 0.0,
) -> MasterResult:
    """Classify T(n) = aT(n/b) + Theta(n^k log^p(n)).

    Handles the standard polynomial comparison and the regular logarithmic
    extension for polynomial toll functions. It intentionally rejects cases
    whose regularity or asymptotic behavior is not established by this model.
    """
    validate_integer(a, "a", 1)
    if b <= 1:
        raise RecurrenceError("b must be greater than 1")

    critical_exponent = log2(a) / log2(b)
    difference = k - critical_exponent
    tolerance = 1e-10

    if difference < -tolerance:
        return MasterResult(
            f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g} log^{logarithmic_power:g} n)",
            "Case 1: recursive leaves dominate",
            f"Theta(n^{critical_exponent:.6g})",
            "The non-recursive work is polynomially smaller than "
            "n^(log_b(a)); the leaf level determines the asymptotic order.",
        )

    if difference > tolerance:
        return MasterResult(
            f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g} log^{logarithmic_power:g} n)",
            "Case 3: non-recursive work dominates",
            f"Theta(n^{k:g} log^{logarithmic_power:g} n)",
            "The toll function is polynomially larger than "
            "n^(log_b(a)); the regularity condition is assumed to hold.",
        )

    p = logarithmic_power
    if p > -1:
        bound = f"Theta(n^{critical_exponent:.6g} log^{p + 1:g} n)"
    elif abs(p + 1) <= tolerance:
        bound = f"Theta(n^{critical_exponent:.6g} log log n)"
    else:
        bound = f"Theta(n^{critical_exponent:.6g})"

    return MasterResult(
        f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g} log^{p:g} n)",
        "Case 2: balanced recursive and non-recursive work",
        bound,
        "The polynomial exponent of the toll matches log_b(a). "
        "Summing the toll across the recursion levels introduces the "
        "corresponding logarithmic factor.",
    )


def master_theorem_polynomial(a: int, b: float, k: float) -> MasterResult:
    """Apply the three classical Master Theorem cases to f(n)=Theta(n^k)."""
    validate_integer(a, "a", 1)
    if b <= 1:
        raise RecurrenceError("b must be greater than 1")

    critical = log2(a) / log2(b)
    epsilon = 1e-10

    if k < critical - epsilon:
        return MasterResult(
            f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g})",
            "Case 1",
            f"Theta(n^{critical:.6g})",
            "The recursive contribution grows faster than the toll function.",
        )
    if k > critical + epsilon:
        return MasterResult(
            f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g})",
            "Case 3",
            f"Theta(n^{k:g})",
            "The toll dominates polynomially, provided the regularity "
            "condition a*f(n/b) <= c*f(n) holds for some constant c < 1.",
        )
    return MasterResult(
        f"T(n) = {a}T(n/{b:g}) + Theta(n^{k:g})",
        "Case 2",
        f"Theta(n^{critical:.6g} log n)",
        "Each level contributes the same asymptotic amount of work.",
    )


def solve_exact_recurrence(
    n: int,
    a: int,
    base_cost: Callable[[int], int],
    toll: Callable[[int], int],
    shrink: Callable[[int], int],
) -> int:
    """Evaluate T(n)=a*T(shrink(n))+toll(n), with an explicit base case."""
    validate_integer(n, "n", 0)
    validate_integer(a, "a", 1)

    @lru_cache(maxsize=None)
    def solve(size: int) -> int:
        if size <= 1:
            result = base_cost(size)
            if result < 0:
                raise RecurrenceError("Base cost must be non-negative")
            return result

        child_size = shrink(size)
        if child_size < 0 or child_size >= size:
            raise RecurrenceError(
                "Shrink function must produce a non-negative smaller size"
            )

        local_work = toll(size)
        if local_work < 0:
            raise RecurrenceError("Toll must be non-negative")
        return a * solve(child_size) + local_work

    return solve(n)


def binary_search(values: list[int], target: int) -> tuple[int, int]:
    """Return (index, comparisons); sorted input is required."""
    if any(values[i] > values[i + 1] for i in range(len(values) - 1)):
        raise ValueError("Binary search requires sorted input")

    left, right = 0, len(values) - 1
    comparisons = 0

    while left <= right:
        middle = left + (right - left) // 2
        comparisons += 1

        if values[middle] == target:
            return middle, comparisons
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle - 1

    return -1, comparisons


def merge_sort(values: list[int]) -> tuple[list[int], int]:
    """Return a sorted copy and the number of element comparisons."""
    comparisons = 0

    def sort(items: list[int]) -> list[int]:
        nonlocal comparisons
        if len(items) <= 1:
            return items.copy()

        middle = len(items) // 2
        left = sort(items[:middle])
        right = sort(items[middle:])
        merged: list[int] = []
        i = j = 0

        while i < len(left) and j < len(right):
            comparisons += 1
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1

        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged

    return sort(values), comparisons


def karatsuba(x: int, y: int) -> int:
    """Multiply non-negative integers using divide-and-conquer."""
    if x < 0 or y < 0:
        raise ValueError("This implementation accepts non-negative integers")
    if x < 10 or y < 10:
        return x * y

    digits = max(len(str(x)), len(str(y)))
    split = digits // 2
    power = 10 ** split
    high_x, low_x = divmod(x, power)
    high_y, low_y = divmod(y, power)

    z0 = karatsuba(low_x, low_y)
    z2 = karatsuba(high_x, high_y)
    z1 = karatsuba(low_x + high_x, low_y + high_y) - z0 - z2

    return z2 * power * power + z1 * power + z0


def count_recursive_calls(
    n: int, a: int, shrink: Callable[[int], int]
) -> int:
    """Count total invocations in a recurrence tree."""
    validate_integer(n, "n", 0)
    validate_integer(a, "a", 1)
    calls = 0

    def visit(size: int) -> None:
        nonlocal calls
        calls += 1
        if size <= 1:
            return
        child = shrink(size)
        if child < 0 or child >= size:
            raise RecurrenceError("Invalid recursive subproblem size")
        for _ in range(a):
            visit(child)

    visit(n)
    return calls


def compare_growth(n_values: Iterable[int]) -> None:
    print("\nGrowth comparison")
    print(f"{'n':>8} {'n log2 n':>14} {'n^2':>14} {'n^3':>14}")
    for n in n_values:
        print(
            f"{n:>8} {n * log2(n):>14.2f} "
            f"{n ** 2:>14} {n ** 3:>14}"
        )


def demonstrate_master_theorem() -> None:
    examples = [
        (2, 2.0, 0.0, "Binary search: T(n)=T(n/2)+Theta(1)"),
        (2, 2.0, 1.0, "Merge sort: T(n)=2T(n/2)+Theta(n)"),
        (4, 2.0, 1.0, "Four subproblems: T(n)=4T(n/2)+Theta(n)"),
        (2, 2.0, 2.0, "Quadratic toll: T(n)=2T(n/2)+Theta(n^2)"),
    ]

    print("\nClassical Master Theorem examples")
    for a, b, k, description in examples:
        result = master_theorem_polynomial(a, b, k)
        print(f"\n{description}")
        print(f"  {result.case}: {result.asymptotic_bound}")
        print(f"  {result.explanation}")

    print("\nLogarithmic toll extension")
    for p in (-2.0, -1.0, 0.0, 2.0):
        result = master_theorem(2, 2.0, 1.0, p)
        print(f"  p={p:g}: {result.asymptotic_bound}")


def run_tests() -> None:
    assert binary_search([1, 3, 5, 7, 9], 7)[0] == 3
    assert binary_search([1, 3, 5], 4)[0] == -1
    assert merge_sort([8, 2, 5, 2, -1])[0] == [-1, 2, 2, 5, 8]
    assert karatsuba(123456789, 987654321) == 123456789 * 987654321
    assert solve_exact_recurrence(
        8, 2, lambda n: 1, lambda n: n, lambda n: n // 2
    ) == 56
    assert master_theorem_polynomial(2, 2, 1).asymptotic_bound == "Theta(n^1 log n)"

    try:
        binary_search([3, 1, 2], 1)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsorted input should be rejected")

    try:
        recurrence_levels(2, 1.0, 8)
    except RecurrenceError:
        pass
    else:
        raise AssertionError("Invalid shrink factor should be rejected")

    print("\nAll tests passed.")


def main() -> None:
    print("ADVANCED RECURRENCES")
    print("A recurrence describes the cost of a problem in terms of smaller problems.")

    print("\nA recurrence evaluated exactly")
    exact = solve_exact_recurrence(
        16,
        2,
        base_cost=lambda n: 1,
        toll=lambda n: n,
        shrink=lambda n: n // 2,
    )
    print(f"T(16) = 2*T(8)+16, recursively evaluated result: {exact}")

    print_recursion_tree(2, 2, 16)
    demonstrate_master_theorem()

    values = [31, 4, 18, 9, 2, 42, 18, 7, 11, 0, 25]
    ordered, comparisons = merge_sort(values)
    print("\nMerge sort")
    print(f"Input: {values}")
    print(f"Sorted: {ordered}")
    print(f"Element comparisons: {comparisons}")

    index, binary_comparisons = binary_search(ordered, 18)
    print("\nBinary search")
    print(f"Target index: {index}")
    print(f"Element comparisons: {binary_comparisons}")

    left, right = 123456789, 987654321
    product = karatsuba(left, right)
    print("\nKaratsuba multiplication")
    print(f"{left} * {right} = {product}")
    print(f"Verified with native multiplication: {product == left * right}")

    print("\nRecursion call count")
    print(
        "T(n) = 2T(n/2) + O(1), n=8: "
        f"{count_recursive_calls(8, 2, lambda n: n // 2)} calls"
    )

    compare_growth([8, 16, 32, 64, 128])
    run_tests()


if __name__ == "__main__":
    main()

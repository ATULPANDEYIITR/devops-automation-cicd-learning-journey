"use strict";

/*
 * Advanced recurrences using JavaScript:
 * recursive evaluation with memoization, recursion-tree accounting,
 * Master Theorem classification, and instrumented divide-and-conquer.
 */

class RecurrenceError extends Error {}

function assertPositiveInteger(value, name) {
    if (!Number.isSafeInteger(value) || value < 1) {
        throw new RecurrenceError(`${name} must be a positive safe integer`);
    }
}

function recursionTree({ a, b, n, toll = size => size }) {
    assertPositiveInteger(a, "a");
    assertPositiveInteger(n, "n");

    if (!(b > 1) || !Number.isFinite(b)) {
        throw new RecurrenceError("b must be finite and greater than 1");
    }

    const levels = [];
    let nodes = 1;
    let size = n;
    let depth = 0;

    while (size > 1) {
        const work = toll(size);
        if (!Number.isFinite(work) || work < 0) {
            throw new RecurrenceError("Toll must be finite and non-negative");
        }

        levels.push({ depth, nodes, size, work: nodes * work });
        nodes *= a;
        size /= b;
        depth += 1;

        if (!Number.isSafeInteger(nodes) && depth > 30) {
            throw new RecurrenceError("Tree exceeds safe numeric accounting");
        }
    }

    levels.push({ depth, nodes, size, work: nodes });
    return levels;
}

function masterTheorem(a, b, k, p = 0) {
    assertPositiveInteger(a, "a");
    if (!(b > 1) || !Number.isFinite(b)) {
        throw new RecurrenceError("b must be greater than 1");
    }
    if (![k, p].every(Number.isFinite)) {
        throw new RecurrenceError("Exponents must be finite");
    }

    const critical = Math.log(a) / Math.log(b);
    const difference = k - critical;
    const epsilon = 1e-10;
    let caseName;
    let bound;

    if (difference < -epsilon) {
        caseName = "Case 1: recursive work dominates";
        bound = `Theta(n^${critical.toFixed(4)})`;
    } else if (difference > epsilon) {
        caseName = "Case 3: toll function dominates";
        bound = `Theta(n^${k} log^${p} n)`;
    } else {
        caseName = "Case 2: balanced work";
        if (p > -1) {
            bound = `Theta(n^${critical.toFixed(4)} log^${p + 1} n)`;
        } else if (Math.abs(p + 1) <= epsilon) {
            bound = `Theta(n^${critical.toFixed(4)} log log n)`;
        } else {
            bound = `Theta(n^${critical.toFixed(4)})`;
        }
    }

    return { a, b, k, p, criticalExponent: critical, caseName, bound };
}

function evaluateRecurrence(n, { a, toll, shrink, baseCost }) {
    assertPositiveInteger(n, "n");
    assertPositiveInteger(a, "a");

    const memo = new Map();

    function solve(size) {
        if (memo.has(size)) return memo.get(size);

        if (size <= 1) {
            const base = baseCost(size);
            if (!Number.isFinite(base) || base < 0) {
                throw new RecurrenceError("Invalid base cost");
            }
            memo.set(size, base);
            return base;
        }

        const child = shrink(size);
        if (!Number.isSafeInteger(child) || child < 0 || child >= size) {
            throw new RecurrenceError("Shrink must return a smaller integer");
        }

        const local = toll(size);
        if (!Number.isFinite(local) || local < 0) {
            throw new RecurrenceError("Invalid toll");
        }

        const result = a * solve(child) + local;
        memo.set(size, result);
        return result;
    }

    return { value: solve(n), memoizedStates: memo.size };
}

function mergeSortWithMetrics(input) {
    let comparisons = 0;
    let allocations = 0;

    function sort(values) {
        if (values.length <= 1) return values.slice();

        const middle = Math.floor(values.length / 2);
        const left = sort(values.slice(0, middle));
        const right = sort(values.slice(middle));
        const merged = [];
        allocations += 1;

        let i = 0;
        let j = 0;
        while (i < left.length && j < right.length) {
            comparisons += 1;
            if (left[i] <= right[j]) merged.push(left[i++]);
            else merged.push(right[j++]);
        }

        merged.push(...left.slice(i), ...right.slice(j));
        return merged;
    }

    return { sorted: sort(input), comparisons, mergeAllocations: allocations };
}

function karatsuba(x, y) {
    if (!Number.isSafeInteger(x) || !Number.isSafeInteger(y) || x < 0 || y < 0) {
        throw new RangeError("Inputs must be non-negative safe integers");
    }

    // BigInt prevents precision loss during multiplication and recombination.
    function multiply(left, right) {
        if (left < 10n || right < 10n) return left * right;

        const digits = Math.max(left.toString().length, right.toString().length);
        const split = Math.floor(digits / 2);
        const power = 10n ** BigInt(split);

        const highLeft = left / power;
        const lowLeft = left % power;
        const highRight = right / power;
        const lowRight = right % power;

        const z0 = multiply(lowLeft, lowRight);
        const z2 = multiply(highLeft, highRight);
        const z1 = multiply(lowLeft + highLeft, lowRight + highRight) - z0 - z2;

        return z2 * power * power + z1 * power + z0;
    }

    return multiply(BigInt(x), BigInt(y));
}

function runAssertions() {
    const merged = mergeSortWithMetrics([8, 2, 5, 2, -1]);
    console.assert(
        JSON.stringify(merged.sorted) === JSON.stringify([-1, 2, 2, 5, 8]),
        "Merge sort failed"
    );

    console.assert(
        masterTheorem(2, 2, 1).bound.includes("log^1"),
        "Merge sort Master Theorem case failed"
    );

    console.assert(
        karatsuba(123456789, 987654321) === 121932631112635269n,
        "Karatsuba multiplication failed"
    );

    const evaluated = evaluateRecurrence(16, {
        a: 2,
        toll: size => size,
        shrink: size => Math.floor(size / 2),
        baseCost: () => 1
    });

    console.assert(evaluated.value === 80, "Recurrence evaluation failed");
    console.log("Assertions completed.");
}

function main() {
    console.log("Recursion tree for T(n) = 2T(n/2) + n");
    console.table(recursionTree({ a: 2, b: 2, n: 16 }));

    console.log("Master Theorem classifications");
    for (const example of [
        { a: 2, b: 2, k: 0 },
        { a: 2, b: 2, k: 1 },
        { a: 4, b: 2, k: 1 },
        { a: 2, b: 2, k: 2 }
    ]) {
        console.log(masterTheorem(example.a, example.b, example.k));
    }

    const source = [34, 8, 19, 2, 19, -5, 42, 11, 7];
    console.log("Instrumented merge sort:", mergeSortWithMetrics(source));

    console.log(
        "Karatsuba:",
        karatsuba(123456789, 987654321).toString()
    );

    runAssertions();
}

if (require.main === module) {
    try {
        main();
    } catch (error) {
        console.error(`${error.name}: ${error.message}`);
        process.exitCode = 1;
    }
}

module.exports = {
    recursionTree,
    masterTheorem,
    evaluateRecurrence,
    mergeSortWithMetrics,
    karatsuba
};

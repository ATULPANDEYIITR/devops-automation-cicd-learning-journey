# Advanced Recurrences and Divide-and-Conquer Analysis

## Topic overview

A recurrence expresses the cost of solving a problem in terms of the costs of smaller instances. Divide-and-conquer algorithms use this relationship to divide a problem, solve its subproblems, and combine their results.

A common recurrence is

\[
T(n)=aT(n/b)+f(n)
\]

where:

- \(n\) is the input size.
- \(a\) is the number of recursive subproblems.
- \(b>1\) is the factor by which each subproblem's size decreases.
- \(f(n)\) is the work performed outside the recursive calls.
- \(T(n)\) is the total cost, including recursive work and combination work.

The three central techniques in this project are related but serve different purposes. Recurrence evaluation computes costs for particular inputs. Recursion trees expose how work is distributed across recursive levels. The Master Theorem derives asymptotic bounds for specific classes of recurrences.

## Recursion trees

A recursion tree represents each invocation as a node. Its children represent recursive subproblems, and the node's local cost represents work performed by that invocation outside its children.

For

\[
T(n)=2T(n/2)+n
\]

the root performs \(n\) units of work. The next level contains two subproblems, each of size \(n/2\), so its total work is

\[
2(n/2)=n.
\]

At depth \(i\), there are \(2^i\) nodes, each processing approximately \(n/2^i\) elements. The total work at that level remains approximately \(n\).

The recursion reaches constant-size subproblems after approximately \(\log_2 n\) levels. Summing the non-recursive work gives

\[
n+n+\cdots+n=\Theta(n\log n).
\]

The leaves also contribute to the total cost. For merge sort, there are approximately \(n\) constant-size leaves, so their aggregate cost is \(\Theta(n)\). The internal levels contribute \(\Theta(n\log n)\), which dominates.

For a general recurrence \(T(n)=aT(n/b)+f(n)\), the number of nodes at depth \(i\) is \(a^i\), while the size of each subproblem is \(n/b^i\). The total work at that level is

\[
a^i f(n/b^i).
\]

This expression is the basis for comparing the recursive contribution with the work performed at each level.

## The Master Theorem

The classical Master Theorem applies to recurrences of the form

\[
T(n)=aT(n/b)+\Theta(n^k)
\]

for constants \(a\geq1\), \(b>1\), and a polynomial exponent \(k\).

Define the critical exponent

\[
c=\log_b a.
\]

The term \(n^c\) describes the polynomial growth associated with the branching structure of the recursion tree. Comparing \(k\) with \(c\) identifies which source of work dominates.

### Case 1: recursive work dominates

When \(k<c\),

\[
T(n)=\Theta(n^c).
\]

The non-recursive work is polynomially smaller than the recursive contribution. The leaves collectively determine the asymptotic growth.

Binary recursive structures with constant work at each invocation are typical examples. Binary search follows \(T(n)=T(n/2)+\Theta(1)\), giving \(\Theta(\log n)\).

### Case 2: the work is balanced

When \(k=c\),

\[
T(n)=\Theta(n^c\log n).
\]

Each level contributes the same asymptotic amount of work. The number of levels introduces the logarithmic factor.

Merge sort satisfies

\[
T(n)=2T(n/2)+\Theta(n).
\]

Here, \(a=2\), \(b=2\), and \(c=\log_2 2=1\). The linear combination work matches the critical exponent, giving \(\Theta(n\log n)\).

### Case 3: non-recursive work dominates

When \(k>c\), the polynomial toll is asymptotically larger than the recursive contribution, provided the regularity condition holds.

A typical regularity condition is

\[
a f(n/b)\leq qf(n)
\]

for a constant \(q<1\) and sufficiently large \(n\).

Under the classical conditions,

\[
T(n)=\Theta(n^k).
\]

The condition matters because a polynomial comparison by itself does not establish every requirement of the theorem.

### Logarithmic extensions

For recurrences with a toll of the form

\[
f(n)=\Theta(n^c\log^p n),
\]

an extended form of Case 2 gives

\[
T(n)=
\begin{cases}
\Theta(n^c\log^{p+1}n), & p>-1,\\
\Theta(n^c\log\log n), & p=-1,\\
\Theta(n^c), & p<-1.
\end{cases}
\]

This extension is useful for studying toll functions containing logarithmic factors. It should not be confused with the three-case classical theorem for polynomial tolls.

## Implementation architecture

The implementations approach recurrence analysis from different computational perspectives.

| File | Primary purpose | Distinctive implementation |
|---|---|---|
| Python | Mathematical analysis and executable examples | Exact recurrence evaluation, tree accounting, Master Theorem classification, merge sort, binary search, and Karatsuba multiplication |
| JavaScript | Instrumented algorithm execution | Memoized recurrence evaluation, structured tree output, merge metrics, and BigInt-based multiplication |
| C++ | Performance-oriented divide-and-conquer case study | Merge-sort service, comparison counting, recursion-tree reporting, and checked integer multiplication |
| Java | Enterprise-oriented complexity analysis | Immutable recurrence records, explicit classification states, checked arithmetic, and analytics batch processing |
| SQL | Persisted complexity models and observations | Relational recurrence definitions, measured runs, analytical views, recursive CTEs, and integrity constraints |

## Python implementation

The Python script begins with validated recurrence parameters and a function that constructs a level-by-level recursion tree. Each level records its depth, node count, subproblem size, and aggregate work.

The `master_theorem_polynomial` function classifies recurrences with polynomial tolls. It compares the toll exponent with \(\log_b a\) and returns the appropriate asymptotic bound. A separate `master_theorem` function supports logarithmic toll factors under its stated model.

The `solve_exact_recurrence` function evaluates a concrete recurrence with a memoized nested function. Its shrink function must return a smaller non-negative integer, and costs must remain non-negative. Memoization avoids repeated evaluation of identical subproblem sizes in this single-child recurrence model.

The algorithm examples connect theoretical bounds to executable behavior:

- **Binary search** halves the remaining search interval and uses logarithmic time on sorted input.
- **Merge sort** recursively sorts two halves and combines them through a merge operation, producing a comparison count and a sorted result.
- **Karatsuba multiplication** splits integers into high and low parts and reduces four half-size products to three recursive products.

The built-in assertions check representative results and invalid inputs. These tests validate concrete behavior, although passing a finite set of assertions is not a proof of an asymptotic bound.

## JavaScript implementation

The JavaScript file uses structured objects to represent recursion-tree levels and Master Theorem classifications. Its memoized evaluator uses a `Map`, making cached states explicit.

The merge-sort implementation measures comparisons and merge allocations. These metrics provide an empirical view of the algorithm, but they do not capture every source of runtime cost, such as memory allocation overhead, garbage collection, and CPU cache behavior.

Karatsuba multiplication uses `BigInt` internally because JavaScript's ordinary `Number` type cannot represent all large integers exactly. The public example accepts safe integer inputs and converts them to `BigInt` before recursive multiplication.

The implementation also exports its functions through CommonJS. This makes the analysis functions reusable in Node.js modules rather than restricting them to a single demonstration run.

## C++ case study

The C++ program models the sorting of a batch of telemetry measurements. A `MergeService` recursively partitions the input range, sorts both halves, and merges the ordered results.

The service counts element comparisons, which offers a useful operational metric for comparing different input sizes. The recursion tree separately models the theoretical work for a specified recurrence.

The `RecurrenceAnalyzer` compares the toll exponent with the critical exponent and reports the corresponding classical case. Its Case 3 classification is conditional on the regularity requirements of the Master Theorem.

The Karatsuba implementation demonstrates a second divide-and-conquer structure. It splits operands by decimal digits, computes three recursive products, and combines the intermediate results. Checked operations reject several forms of unsigned integer overflow.

The multiplication example intentionally uses values small enough to fit in the chosen integer type. This implementation is not a general arbitrary-precision arithmetic library; a production implementation would need a broader overflow analysis or an arbitrary-precision representation.

## Java implementation

The Java program uses a `Recurrence` record to keep recurrence parameters immutable after construction. Validation occurs when the record is created, preventing invalid branching factors and shrink factors from silently entering later analysis.

The `MasterCase` enum represents the three classification states explicitly. The recurrence record derives the critical exponent and reports a bound based on the classification.

`TreeLevel` records each level of a recursion tree. The tree builder checks node-count multiplication before updating the number of nodes, making overflow an explicit failure rather than allowing a corrupted count.

The `RecurrenceEvaluator` separates the recurrence definition from the evaluation algorithm through functional interfaces for base cost, toll, and shrink behavior. It uses checked arithmetic with `Math.multiplyExact` and `Math.addExact`.

The `ReviewBatch` record models a batch of measurements and returns an immutable copy of its sorted results. Its merge-sort routine operates on subranges, limiting unnecessary copying of recursive input segments. The program therefore connects recurrence-based reasoning to a realistic batch-processing workload without making the measured runtime equivalent to the theoretical operation count.

## SQL data model

The PostgreSQL script stores recurrence definitions in `recurrence_models` and observed executions in `algorithm_runs`.

A recurrence model records the algorithm name, branching factor, shrink factor, polynomial toll exponent, logarithmic toll exponent, base cost, and explanatory description. Each execution references a valid model through a foreign key and stores its input size, elapsed time, operation count, environment, and measurement timestamp.

The schema uses check constraints to reject invalid parameter ranges and negative measurements. A unique constraint prevents duplicate combinations of recurrence, input size, environment, and timestamp. Indexes support filtering observations by recurrence and input size and retrieving recent measurements.

The `recurrence_analysis` view calculates the critical exponent and classifies each stored model. Its Case 3 label explicitly notes the need for regularity rather than treating the exponent comparison as sufficient proof.

A window-function query compares measurements at successive input sizes. The ratio of elapsed times can reveal empirical growth patterns, but measurements are affected by implementation details, runtime conditions, and hardware.

A recursive common table expression constructs a binary recursion tree for a perfect-halving example. It calculates the number of nodes and aggregate work at each level.

The transaction includes a savepoint and an exception-handling block that demonstrates rejection of a negative elapsed time. The failed insertion is caught, and the transaction can continue without retaining an invalid measurement.

## Complexity distinctions and limitations

Asymptotic analysis describes growth as input size increases. It does not directly predict elapsed time for a particular machine or input.

For merge sort, the recurrence

\[
T(n)=2T(n/2)+\Theta(n)
\]

establishes \(\Theta(n\log n)\) time under the standard model. Its auxiliary merge storage is linear in the input size for the implementations shown.

Binary search has logarithmic time complexity because each comparison eliminates approximately half the remaining search interval. Its iterative implementation uses constant auxiliary space.

Karatsuba multiplication follows the recurrence

\[
T(n)=3T(n/2)+\Theta(n),
\]

which yields

\[
T(n)=\Theta(n^{\log_2 3}).
\]

Its asymptotic advantage over the classical quadratic multiplication method becomes more significant as operand sizes grow, although implementation overhead influences the practical crossover point.

The Master Theorem does not cover every recurrence. Unequal subproblem sizes, non-polynomial toll functions, oscillating costs, and recurrences without the required regularity may need recursion-tree summation, substitution, or another analysis method.

## Practical interpretation

A recurrence is useful when the recursive structure and local work can be stated clearly. The recursion tree explains why the work grows, while the Master Theorem supplies a bound when its assumptions match the recurrence.

Executable counters and measured runtimes help test an implementation against that mathematical model. Database constraints preserve the validity of recorded observations, but neither a timing ratio nor a stored classification replaces a proof of the algorithm's asymptotic behavior.

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class AdvancedRecurrences {

    enum MasterCase {
        RECURSIVE_DOMINANT,
        BALANCED,
        TOLL_DOMINANT
    }

    record Recurrence(int a, double b, double k) {
        Recurrence {
            if (a < 1) {
                throw new IllegalArgumentException("a must be at least 1");
            }
            if (!Double.isFinite(b) || b <= 1.0) {
                throw new IllegalArgumentException("b must be finite and greater than 1");
            }
            if (!Double.isFinite(k)) {
                throw new IllegalArgumentException("k must be finite");
            }
        }

        double criticalExponent() {
            return Math.log(a) / Math.log(b);
        }

        MasterCase classify() {
            double difference = k - criticalExponent();
            if (difference < -1e-10) return MasterCase.RECURSIVE_DOMINANT;
            if (difference > 1e-10) return MasterCase.TOLL_DOMINANT;
            return MasterCase.BALANCED;
        }

        String asymptoticBound() {
            double critical = criticalExponent();
            return switch (classify()) {
                case RECURSIVE_DOMINANT ->
                    String.format("Theta(n^%.4f)", critical);
                case BALANCED ->
                    String.format("Theta(n^%.4f log n)", critical);
                case TOLL_DOMINANT ->
                    String.format("Theta(n^%.4f)", k);
            };
        }
    }

    record TreeLevel(int depth, long nodes, double problemSize, double work) {}

    static List<TreeLevel> buildRecursionTree(
            int a, double b, int n, double tollExponent) {
        if (a < 1 || b <= 1 || n < 1 || tollExponent < 0) {
            throw new IllegalArgumentException("Invalid recursion-tree parameters");
        }

        List<TreeLevel> levels = new ArrayList<>();
        long nodes = 1;
        double size = n;
        int depth = 0;

        while (size > 1) {
            double localWork = Math.pow(size, tollExponent);
            levels.add(new TreeLevel(depth, nodes, size, nodes * localWork));

            if (nodes > Long.MAX_VALUE / a) {
                throw new ArithmeticException("Node count exceeds long range");
            }
            nodes *= a;
            size /= b;
            depth++;

            if (depth > 1000) {
                throw new IllegalStateException("Recursion tree depth limit exceeded");
            }
        }

        levels.add(new TreeLevel(depth, nodes, size, nodes));
        return Collections.unmodifiableList(levels);
    }

    @FunctionalInterface
    interface CostFunction {
        long apply(int n);
    }

    @FunctionalInterface
    interface ShrinkFunction {
        int apply(int n);
    }

    static final class RecurrenceEvaluator {
        private final int branchingFactor;
        private final CostFunction baseCost;
        private final CostFunction toll;
        private final ShrinkFunction shrink;

        RecurrenceEvaluator(
                int branchingFactor,
                CostFunction baseCost,
                CostFunction toll,
                ShrinkFunction shrink) {
            if (branchingFactor < 1) {
                throw new IllegalArgumentException("Branching factor must be positive");
            }
            this.branchingFactor = branchingFactor;
            this.baseCost = Objects.requireNonNull(baseCost);
            this.toll = Objects.requireNonNull(toll);
            this.shrink = Objects.requireNonNull(shrink);
        }

        long evaluate(int n) {
            if (n < 0) throw new IllegalArgumentException("n cannot be negative");
            return solve(n, 0);
        }

        private long solve(int n, int depth) {
            if (depth > 1000) {
                throw new IllegalStateException("Recursion depth limit exceeded");
            }
            if (n <= 1) {
                long cost = baseCost.apply(n);
                if (cost < 0) throw new IllegalArgumentException("Negative base cost");
                return cost;
            }

            int child = shrink.apply(n);
            if (child < 0 || child >= n) {
                throw new IllegalArgumentException("Shrink function must decrease n");
            }

            long local = toll.apply(n);
            if (local < 0) throw new IllegalArgumentException("Negative toll");

            // Checked arithmetic makes integer overflow an explicit failure.
            long recursive = Math.multiplyExact(
                branchingFactor, solve(child, depth + 1));
            return Math.addExact(recursive, local);
        }
    }

    record ReviewBatch(String name, List<Integer> measurements) {
        ReviewBatch {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Batch name is required");
            }
            measurements = List.copyOf(measurements);
        }

        List<Integer> sortedMeasurements() {
            List<Integer> sorted = new ArrayList<>(measurements);
            mergeSort(sorted, 0, sorted.size());
            return List.copyOf(sorted);
        }

        private static void mergeSort(List<Integer> values, int from, int to) {
            if (to - from <= 1) return;

            int middle = from + (to - from) / 2;
            mergeSort(values, from, middle);
            mergeSort(values, middle, to);

            List<Integer> merged = new ArrayList<>(to - from);
            int i = from;
            int j = middle;

            while (i < middle && j < to) {
                if (values.get(i) <= values.get(j)) merged.add(values.get(i++));
                else merged.add(values.get(j++));
            }
            while (i < middle) merged.add(values.get(i++));
            while (j < to) merged.add(values.get(j++));

            for (int index = 0; index < merged.size(); index++) {
                values.set(from + index, merged.get(index));
            }
        }
    }

    private static void printTree(List<TreeLevel> levels) {
        System.out.printf("%-8s %-16s %-18s %-18s%n",
                "Depth", "Nodes", "Problem size", "Level work");
        for (TreeLevel level : levels) {
            System.out.printf("%-8d %-16d %-18.3f %-18.3f%n",
                    level.depth(), level.nodes(),
                    level.problemSize(), level.work());
        }
    }

    private static void verify(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        System.out.println("Enterprise analytics: recurrence-based capacity analysis");

        List<Recurrence> scenarios = List.of(
            new Recurrence(2, 2, 0),
            new Recurrence(2, 2, 1),
            new Recurrence(4, 2, 1),
            new Recurrence(2, 2, 2)
        );

        for (Recurrence recurrence : scenarios) {
            System.out.printf(
                "a=%d, b=%.1f, k=%.1f: %s -> %s%n",
                recurrence.a(), recurrence.b(), recurrence.k(),
                recurrence.classify(), recurrence.asymptoticBound()
            );
        }

        System.out.println("\nMerge-sort recursion tree");
        printTree(buildRecursionTree(2, 2, 32, 1));

        RecurrenceEvaluator evaluator = new RecurrenceEvaluator(
            2,
            ignored -> 1,
            n -> n,
            n -> n / 2
        );

        long measuredCost = evaluator.evaluate(8);
        verify(measuredCost == 36, "Recurrence evaluation failed");
        System.out.println("\nExact modeled cost T(8): " + measuredCost);

        ReviewBatch batch = new ReviewBatch(
            "Regional processing batch",
            List.of(340, 85, 610, 85, 220, 17, 999)
        );

        List<Integer> ordered = batch.sortedMeasurements();
        verify(ordered.equals(List.of(17, 85, 85, 220, 340, 610, 999)),
                "Merge sort failed");

        System.out.println("Batch: " + batch.name());
        System.out.println("Ordered measurements: " + ordered);

        try {
            new Recurrence(2, 1, 1);
            throw new AssertionError("Invalid b should have failed");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid recurrence rejected: " + expected.getMessage());
        }

        System.out.println("\nThe merge-sort recurrence is T(n)=2T(n/2)+Theta(n).");
        System.out.println("Its logarithmic depth and linear work per level give Theta(n log n).");
    }
}

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

struct Level {
    int depth;
    long double subproblemSize;
    long double nodes;
    long double localWork;
    long double totalWork;
};

struct MasterResult {
    string caseName;
    string bound;
    long double criticalExponent;
};

class RecurrenceAnalyzer {
public:
    static vector<Level> buildTree(
        int a,
        long double b,
        long double n,
        long double tollExponent
    ) {
        if (a < 1 || !(b > 1) || !(n >= 1) || tollExponent < 0) {
            throw invalid_argument("Invalid recurrence parameters");
        }

        vector<Level> levels;
        long double size = n;
        long double nodes = 1;
        int depth = 0;

        while (size > 1.0L) {
            long double local = pow(size, tollExponent);
            levels.push_back({
                depth, size, nodes, local, nodes * local
            });

            size /= b;
            nodes *= a;
            ++depth;

            if (depth > 10000) {
                throw runtime_error("Recursion tree depth limit exceeded");
            }
        }

        levels.push_back({depth, size, nodes, 1.0L, nodes});
        return levels;
    }

    static MasterResult classify(int a, long double b, long double k) {
        if (a < 1 || !(b > 1)) {
            throw invalid_argument("Require a >= 1 and b > 1");
        }

        const long double critical = log(static_cast<long double>(a)) / log(b);
        const long double epsilon = 1e-10L;

        if (k < critical - epsilon) {
            return {
                "Case 1: recursive contribution dominates",
                "Theta(n^" + to_string(static_cast<double>(critical)) + ")",
                critical
            };
        }

        if (k > critical + epsilon) {
            return {
                "Case 3: polynomial toll dominates",
                "Theta(n^" + to_string(static_cast<double>(k)) + ")",
                critical
            };
        }

        return {
            "Case 2: equal polynomial exponents",
            "Theta(n^" + to_string(static_cast<double>(critical)) + " log n)",
            critical
        };
    }
};

class MergeService {
private:
    uint64_t comparisons = 0;

    vector<int> mergeSortRange(const vector<int>& input, size_t begin, size_t end) {
        if (end - begin <= 1) {
            return vector<int>(input.begin() + static_cast<ptrdiff_t>(begin),
                               input.begin() + static_cast<ptrdiff_t>(end));
        }

        const size_t middle = begin + (end - begin) / 2;
        vector<int> left = mergeSortRange(input, begin, middle);
        vector<int> right = mergeSortRange(input, middle, end);
        vector<int> output;
        output.reserve(end - begin);

        size_t i = 0;
        size_t j = 0;

        while (i < left.size() && j < right.size()) {
            ++comparisons;
            if (left[i] <= right[j]) output.push_back(left[i++]);
            else output.push_back(right[j++]);
        }

        output.insert(output.end(), left.begin() + static_cast<ptrdiff_t>(i), left.end());
        output.insert(output.end(), right.begin() + static_cast<ptrdiff_t>(j), right.end());
        return output;
    }

public:
    vector<int> sort(const vector<int>& input) {
        comparisons = 0;
        return mergeSortRange(input, 0, input.size());
    }

    uint64_t comparisonCount() const {
        return comparisons;
    }
};

class KaratsubaMultiplier {
private:
    static unsigned long long power10(unsigned int exponent) {
        unsigned long long value = 1;
        for (unsigned int i = 0; i < exponent; ++i) {
            if (value > numeric_limits<unsigned long long>::max() / 10) {
                throw overflow_error("Power of ten exceeds integer range");
            }
            value *= 10;
        }
        return value;
    }

    static unsigned int digits(unsigned long long value) {
        unsigned int count = 1;
        while (value >= 10) {
            value /= 10;
            ++count;
        }
        return count;
    }

public:
    static unsigned long long multiply(unsigned long long x, unsigned long long y) {
        if (x < 10 || y < 10) {
            if (y != 0 && x > numeric_limits<unsigned long long>::max() / y) {
                throw overflow_error("Product exceeds integer range");
            }
            return x * y;
        }

        const unsigned int split = max(digits(x), digits(y)) / 2;
        const unsigned long long power = power10(split);
        const unsigned long long highX = x / power;
        const unsigned long long lowX = x % power;
        const unsigned long long highY = y / power;
        const unsigned long long lowY = y % power;

        const unsigned long long z0 = multiply(lowX, lowY);
        const unsigned long long z2 = multiply(highX, highY);

        // Intermediate addition and recombination can overflow even when
        // the original operands fit; this implementation rejects such cases.
        if (lowX > numeric_limits<unsigned long long>::max() - highX ||
            lowY > numeric_limits<unsigned long long>::max() - highY) {
            throw overflow_error("Karatsuba intermediate sum overflow");
        }

        const unsigned long long sumProduct =
            multiply(lowX + highX, lowY + highY);

        if (sumProduct < z0 || sumProduct - z0 < z2) {
            throw overflow_error("Karatsuba intermediate subtraction failed");
        }

        const unsigned long long z1 = sumProduct - z0 - z2;
        if (z2 > numeric_limits<unsigned long long>::max() / power / power) {
            throw overflow_error("Karatsuba recombination overflow");
        }

        const unsigned long long highPart = z2 * power * power;
        if (z1 > (numeric_limits<unsigned long long>::max() - highPart) / power) {
            throw overflow_error("Karatsuba middle term overflow");
        }

        const unsigned long long middlePart = z1 * power;
        if (lowX != 0 && highPart > numeric_limits<unsigned long long>::max() -
                                     middlePart - z0) {
            throw overflow_error("Karatsuba result overflow");
        }

        return highPart + middlePart + z0;
    }
};

void printTree(const vector<Level>& levels) {
    cout << left << setw(8) << "Depth"
         << setw(18) << "Subproblem"
         << setw(18) << "Nodes"
         << setw(18) << "Level work" << '\n';

    for (const auto& level : levels) {
        cout << setw(8) << level.depth
             << setw(18) << static_cast<double>(level.subproblemSize)
             << setw(18) << static_cast<double>(level.nodes)
             << setw(18) << static_cast<double>(level.totalWork) << '\n';
    }
}

int main() {
    try {
        cout << "Repository-scale data sorting case study\n";
        cout << "The service sorts batches of telemetry measurements.\n\n";

        const vector<int> telemetry = {
            950, 120, 450, 120, 780, 32, 610, 250, 450, 999, 5
        };

        MergeService service;
        const vector<int> sorted = service.sort(telemetry);

        cout << "Sorted measurements: ";
        for (int value : sorted) cout << value << ' ';
        cout << "\nComparisons: " << service.comparisonCount() << "\n\n";

        cout << "Recursion tree for T(n) = 2T(n/2) + n\n";
        printTree(RecurrenceAnalyzer::buildTree(2, 2.0L, 16.0L, 1.0L));

        cout << "\nMaster Theorem analysis\n";
        for (const auto& example : vector<vector<long double>>{
                 {2, 2, 0}, {2, 2, 1}, {4, 2, 1}, {2, 2, 2}}) {
            const auto result = RecurrenceAnalyzer::classify(
                static_cast<int>(example[0]), example[1], example[2]);
            cout << result.caseName << " -> " << result.bound << '\n';
        }

        cout << "\nKaratsuba multiplication\n";
        const auto product = KaratsubaMultiplier::multiply(123456ULL, 654321ULL);
        cout << "123456 * 654321 = " << product << '\n';
        if (product != 123456ULL * 654321ULL) {
            throw runtime_error("Multiplication verification failed");
        }

        cout << "\nComplexity interpretation\n";
        cout << "Merge sort has two half-size subproblems and linear merge work.\n";
        cout << "The recurrence is T(n)=2T(n/2)+Theta(n), yielding Theta(n log n).\n";
        cout << "Auxiliary merge buffers use O(n) additional memory per active "
                "level of the implementation's recursion.\n";

    } catch (const exception& error) {
        cerr << "Failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

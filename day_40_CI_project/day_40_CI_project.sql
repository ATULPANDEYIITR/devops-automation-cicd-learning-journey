-- PostgreSQL 14+
-- Advanced recurrences: model recursive algorithms and compare theoretical
-- recurrence classifications with measured algorithm runs.

BEGIN;

DROP VIEW IF EXISTS recurrence_analysis;
DROP TABLE IF EXISTS algorithm_runs;
DROP TABLE IF EXISTS recurrence_models;

CREATE TABLE recurrence_models (
    recurrence_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    algorithm_name TEXT NOT NULL UNIQUE,
    branching_factor INTEGER NOT NULL CHECK (branching_factor >= 1),
    shrink_factor NUMERIC(12, 6) NOT NULL CHECK (shrink_factor > 1),
    toll_exponent NUMERIC(12, 6) NOT NULL,
    toll_log_power NUMERIC(12, 6) NOT NULL DEFAULT 0,
    base_cost NUMERIC(24, 6) NOT NULL DEFAULT 1 CHECK (base_cost >= 0),
    description TEXT NOT NULL,
    CHECK (toll_exponent > -100)
);

CREATE TABLE algorithm_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recurrence_id BIGINT NOT NULL
        REFERENCES recurrence_models(recurrence_id) ON DELETE CASCADE,
    input_size BIGINT NOT NULL CHECK (input_size >= 1),
    elapsed_microseconds NUMERIC(24, 6) NOT NULL
        CHECK (elapsed_microseconds >= 0),
    operation_count BIGINT CHECK (operation_count >= 0),
    run_environment TEXT NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (recurrence_id, input_size, run_environment, measured_at)
);

CREATE INDEX algorithm_runs_recurrence_size_idx
    ON algorithm_runs (recurrence_id, input_size);

CREATE INDEX algorithm_runs_measured_at_idx
    ON algorithm_runs (measured_at DESC);

INSERT INTO recurrence_models
    (algorithm_name, branching_factor, shrink_factor,
     toll_exponent, toll_log_power, description)
VALUES
    ('Binary search', 1, 2, 0, 0,
     'One smaller subproblem and constant work per level'),
    ('Merge sort', 2, 2, 1, 0,
     'Two half-size subproblems and linear merge work'),
    ('Four-way decomposition', 4, 2, 1, 0,
     'Four half-size subproblems and linear combination work'),
    ('Quadratic toll', 2, 2, 2, 0,
     'Two half-size subproblems with quadratic non-recursive work'),
    ('Logarithmic toll', 2, 2, 1, 1,
     'Two half-size subproblems with n log n non-recursive work');

INSERT INTO algorithm_runs
    (recurrence_id, input_size, elapsed_microseconds,
     operation_count, run_environment)
SELECT
    model.recurrence_id,
    sample.input_size,
    sample.elapsed_microseconds,
    sample.operation_count,
    'reference-lab'
FROM recurrence_models AS model
CROSS JOIN (
    VALUES
        (256::BIGINT, 42.0::NUMERIC, 2048::BIGINT),
        (512::BIGINT, 91.0::NUMERIC, 4608::BIGINT),
        (1024::BIGINT, 190.0::NUMERIC, 10240::BIGINT),
        (2048::BIGINT, 407.0::NUMERIC, 22528::BIGINT)
) AS sample(input_size, elapsed_microseconds, operation_count)
WHERE model.algorithm_name = 'Merge sort';

CREATE VIEW recurrence_analysis AS
WITH parameters AS (
    SELECT
        recurrence_id,
        algorithm_name,
        branching_factor,
        shrink_factor,
        toll_exponent,
        toll_log_power,
        LN(branching_factor::NUMERIC) /
            LN(shrink_factor) AS critical_exponent
    FROM recurrence_models
),
classification AS (
    SELECT
        *,
        CASE
            WHEN toll_exponent < critical_exponent
                THEN 'Case 1: recursive contribution dominates'
            WHEN toll_exponent > critical_exponent
                THEN 'Case 3: toll function dominates'
            ELSE 'Case 2: balanced polynomial exponents'
        END AS master_case,
        CASE
            WHEN toll_exponent < critical_exponent
                THEN 'Theta(n^log_b(a))'
            WHEN toll_exponent > critical_exponent
                THEN 'Theta(n^k log^p(n)), subject to regularity'
            WHEN toll_log_power > -1
                THEN 'Theta(n^log_b(a) log^(p+1)(n))'
            WHEN toll_log_power = -1
                THEN 'Theta(n^log_b(a) log log(n))'
            ELSE 'Theta(n^log_b(a))'
        END AS asymptotic_bound
    FROM parameters
)
SELECT
    recurrence_id,
    algorithm_name,
    branching_factor,
    shrink_factor,
    toll_exponent,
    toll_log_power,
    ROUND(critical_exponent, 6) AS critical_exponent,
    master_case,
    asymptotic_bound
FROM classification;

-- Compare the polynomial exponent of the toll with log_b(a).
-- Case 3 requires a regularity condition; the label alone does not prove it.
SELECT
    algorithm_name,
    critical_exponent,
    master_case,
    asymptotic_bound
FROM recurrence_analysis
ORDER BY recurrence_id;

-- Estimate empirical doubling ratios. A ratio near 2 is consistent with
-- linear growth; a ratio near 2 with an additional logarithmic factor can
-- be slightly larger than 2 over finite sample sizes.
WITH ordered_runs AS (
    SELECT
        r.algorithm_name,
        run.input_size,
        run.elapsed_microseconds,
        LAG(run.input_size) OVER (
            PARTITION BY r.recurrence_id, run.run_environment
            ORDER BY run.input_size
        ) AS previous_size,
        LAG(run.elapsed_microseconds) OVER (
            PARTITION BY r.recurrence_id, run.run_environment
            ORDER BY run.input_size
        ) AS previous_elapsed
    FROM algorithm_runs AS run
    JOIN recurrence_models AS r USING (recurrence_id)
)
SELECT
    algorithm_name,
    previous_size,
    input_size,
    ROUND(elapsed_microseconds / NULLIF(previous_elapsed, 0), 4)
        AS elapsed_time_ratio
FROM ordered_runs
WHERE previous_size IS NOT NULL
ORDER BY algorithm_name, input_size;

-- Compute predicted per-level work for a perfect binary recursion tree.
-- This query uses integer input sizes and assumes exact halving for display.
WITH RECURSIVE tree(depth, subproblem_size, nodes) AS (
    SELECT 0, 32::NUMERIC, 1::NUMERIC
    UNION ALL
    SELECT
        depth + 1,
        subproblem_size / 2,
        nodes * 2
    FROM tree
    WHERE subproblem_size > 1
)
SELECT
    depth,
    subproblem_size,
    nodes,
    nodes * subproblem_size AS total_level_work
FROM tree
ORDER BY depth;

-- A negative elapsed time or negative operation count violates the table
-- constraints. The transaction below demonstrates a recoverable rejection.
SAVEPOINT invalid_measurement;

DO $$
BEGIN
    BEGIN
        INSERT INTO algorithm_runs (
            recurrence_id,
            input_size,
            elapsed_microseconds,
            operation_count,
            run_environment
        )
        SELECT recurrence_id, 16, -1, 20, 'invalid-test'
        FROM recurrence_models
        WHERE algorithm_name = 'Merge sort';

        RAISE EXCEPTION 'Expected elapsed-time constraint to reject the row';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Correctly rejected a negative elapsed time';
    END;
END;
$$;

ROLLBACK TO SAVEPOINT invalid_measurement;
RELEASE SAVEPOINT invalid_measurement;

COMMIT;

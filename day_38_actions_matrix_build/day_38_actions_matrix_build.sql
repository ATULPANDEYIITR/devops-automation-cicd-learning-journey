-- Actions Matrix Builds
-- PostgreSQL-compatible relational model for multi-version CI testing.
--
-- The schema models:
-- repositories
-- branches
-- commits
-- pull requests
-- matrix dimensions
-- concrete matrix jobs
-- job attempts
-- test results
-- workflow status
-- matrix exclusions
-- experimental combinations
--
-- Database-level constraints protect the integrity of matrix data while
-- application-level policy determines whether a particular combination is
-- meaningful for a repository.

DROP SCHEMA IF EXISTS actions_matrix CASCADE;
CREATE SCHEMA actions_matrix;

SET search_path = actions_matrix;

CREATE TYPE workflow_status AS ENUM (
    'queued',
    'running',
    'passed',
    'failed',
    'cancelled'
);

CREATE TYPE dependency_mode AS ENUM (
    'minimum',
    'locked',
    'latest'
);

CREATE TYPE job_result AS ENUM (
    'passed',
    'failed',
    'cancelled',
    'skipped'
);

CREATE TABLE repository (
    repository_id BIGSERIAL PRIMARY KEY,
    owner_name TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_name, repository_name)
);

CREATE TABLE branch (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE commit (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    sha CHAR(40) NOT NULL,
    message TEXT NOT NULL,
    author_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, sha)
);

CREATE TABLE pull_request (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL
        REFERENCES branch(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branch(branch_id),
    head_commit_id BIGINT NOT NULL
        REFERENCES commit(commit_id),
    title TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('open', 'closed', 'merged')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    merged_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id),
    CHECK (
        (state = 'merged' AND merged_at IS NOT NULL)
        OR
        (state <> 'merged' AND merged_at IS NULL)
    )
);

CREATE TABLE matrix_configuration (
    matrix_configuration_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    configuration_name TEXT NOT NULL,
    fail_fast BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id, configuration_name)
);

CREATE TABLE python_version (
    python_version TEXT PRIMARY KEY,
    CHECK (python_version ~ '^[0-9]+\.[0-9]+$')
);

CREATE TABLE operating_system (
    operating_system TEXT PRIMARY KEY
        CHECK (operating_system IN ('ubuntu', 'windows', 'macos'))
);

CREATE TABLE matrix_dependency (
    dependency_mode dependency_mode PRIMARY KEY
);

CREATE TABLE matrix_exclusion (
    matrix_configuration_id BIGINT NOT NULL
        REFERENCES matrix_configuration(matrix_configuration_id)
        ON DELETE CASCADE,
    python_version TEXT NOT NULL
        REFERENCES python_version(python_version),
    operating_system TEXT NOT NULL
        REFERENCES operating_system(operating_system),
    dependency_mode dependency_mode NOT NULL
        REFERENCES matrix_dependency(dependency_mode),
    PRIMARY KEY (
        matrix_configuration_id,
        python_version,
        operating_system,
        dependency_mode
    )
);

CREATE TABLE matrix_job (
    matrix_job_id BIGSERIAL PRIMARY KEY,
    matrix_configuration_id BIGINT NOT NULL
        REFERENCES matrix_configuration(matrix_configuration_id)
        ON DELETE CASCADE,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    python_version TEXT NOT NULL
        REFERENCES python_version(python_version),
    operating_system TEXT NOT NULL
        REFERENCES operating_system(operating_system),
    dependency_mode dependency_mode NOT NULL
        REFERENCES matrix_dependency(dependency_mode),
    experimental BOOLEAN NOT NULL DEFAULT FALSE,
    status workflow_status NOT NULL DEFAULT 'queued',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (
        pull_request_id,
        python_version,
        operating_system,
        dependency_mode
    )
);

CREATE TABLE matrix_job_attempt (
    attempt_id BIGSERIAL PRIMARY KEY,
    matrix_job_id BIGINT NOT NULL
        REFERENCES matrix_job(matrix_job_id)
        ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL
        CHECK (attempt_number > 0),
    result job_result NOT NULL,
    failure_reason TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CHECK (
        result = 'failed'
        OR failure_reason IS NULL
    ),
    UNIQUE (matrix_job_id, attempt_number)
);

CREATE TABLE test_result (
    test_result_id BIGSERIAL PRIMARY KEY,
    matrix_job_id BIGINT NOT NULL
        REFERENCES matrix_job(matrix_job_id)
        ON DELETE CASCADE,
    suite_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    tests_run INTEGER NOT NULL CHECK (tests_run >= 0),
    failures INTEGER NOT NULL CHECK (failures >= 0),
    duration_seconds NUMERIC(12,3) NOT NULL
        CHECK (duration_seconds >= 0),
    UNIQUE (matrix_job_id, suite_name),
    CHECK (failures <= tests_run)
);

CREATE INDEX idx_matrix_job_pr
    ON matrix_job (pull_request_id);

CREATE INDEX idx_matrix_job_status
    ON matrix_job (status);

CREATE INDEX idx_matrix_job_dimensions
    ON matrix_job (
        python_version,
        operating_system,
        dependency_mode
    );

CREATE INDEX idx_attempt_job
    ON matrix_job_attempt (matrix_job_id, attempt_number);

CREATE INDEX idx_test_result_job
    ON test_result (matrix_job_id);

INSERT INTO repository (
    owner_name,
    repository_name,
    default_branch
)
VALUES (
    'example-org',
    'multi-version-service',
    'main'
);

INSERT INTO branch (
    repository_id,
    branch_name,
    protected
)
VALUES
    (1, 'main', TRUE),
    (1, 'feature/runtime-upgrade', FALSE);

INSERT INTO commit (
    repository_id,
    sha,
    message,
    author_name
)
VALUES
(
    1,
    '1111111111111111111111111111111111111111',
    'Update runtime compatibility',
    'Atul'
),
(
    1,
    '2222222222222222222222222222222222222222',
    'Update main branch',
    'Release Bot'
);

INSERT INTO pull_request (
    repository_id,
    source_branch_id,
    target_branch_id,
    head_commit_id,
    title,
    state
)
VALUES (
    1,
    2,
    1,
    1,
    'Expand supported runtime matrix',
    'open'
);

INSERT INTO matrix_configuration (
    repository_id,
    configuration_name,
    fail_fast
)
VALUES (
    1,
    'python-compatibility',
    FALSE
);

INSERT INTO python_version (python_version)
VALUES
    ('3.10'),
    ('3.11'),
    ('3.12'),
    ('3.13');

INSERT INTO operating_system (operating_system)
VALUES
    ('ubuntu'),
    ('windows'),
    ('macos');

INSERT INTO matrix_dependency (dependency_mode)
VALUES
    ('minimum'),
    ('locked'),
    ('latest');

INSERT INTO matrix_exclusion (
    matrix_configuration_id,
    python_version,
    operating_system,
    dependency_mode
)
VALUES
(
    1,
    '3.10',
    'macos',
    'minimum'
),
(
    1,
    '3.13',
    'windows',
    'minimum'
);

-- Generate the Cartesian product and remove explicitly excluded combinations.
INSERT INTO matrix_job (
    matrix_configuration_id,
    pull_request_id,
    python_version,
    operating_system,
    dependency_mode
)
SELECT
    1,
    1,
    pv.python_version,
    os.operating_system,
    dm.dependency_mode
FROM python_version pv
CROSS JOIN operating_system os
CROSS JOIN matrix_dependency dm
WHERE NOT EXISTS (
    SELECT 1
    FROM matrix_exclusion exclusion
    WHERE exclusion.matrix_configuration_id = 1
      AND exclusion.python_version = pv.python_version
      AND exclusion.operating_system = os.operating_system
      AND exclusion.dependency_mode = dm.dependency_mode
);

-- Mark a canary combination explicitly as experimental. Its failure remains
-- visible but can be treated differently from release-blocking combinations.
UPDATE matrix_job
SET experimental = TRUE
WHERE pull_request_id = 1
  AND python_version = '3.13'
  AND operating_system = 'ubuntu'
  AND dependency_mode = 'latest';

-- Populate deterministic compatibility results.
INSERT INTO matrix_job_attempt (
    matrix_job_id,
    attempt_number,
    result,
    failure_reason,
    completed_at
)
SELECT
    matrix_job_id,
    1,
    CASE
        WHEN python_version = '3.10'
             AND dependency_mode = 'latest'
            THEN 'failed'::job_result
        WHEN operating_system = 'windows'
             AND python_version = '3.10'
            THEN 'failed'::job_result
        WHEN operating_system = 'macos'
             AND python_version = '3.13'
            THEN 'failed'::job_result
        WHEN python_version = '3.13'
             AND dependency_mode = 'minimum'
            THEN 'failed'::job_result
        ELSE 'passed'::job_result
    END,
    CASE
        WHEN python_version = '3.10'
             AND dependency_mode = 'latest'
            THEN 'Latest dependencies do not support Python 3.10.'
        WHEN operating_system = 'windows'
             AND python_version = '3.10'
            THEN 'Legacy Windows compatibility test failed.'
        WHEN operating_system = 'macos'
             AND python_version = '3.13'
            THEN 'Native extension compatibility test failed.'
        WHEN python_version = '3.13'
             AND dependency_mode = 'minimum'
            THEN 'Minimum dependency set is incompatible with Python 3.13.'
        ELSE NULL
    END,
    CURRENT_TIMESTAMP
FROM matrix_job
WHERE pull_request_id = 1;

UPDATE matrix_job job
SET status = CASE attempt.result
    WHEN 'passed' THEN 'passed'::workflow_status
    WHEN 'failed' THEN 'failed'::workflow_status
    ELSE 'cancelled'::workflow_status
END
FROM matrix_job_attempt attempt
WHERE attempt.matrix_job_id = job.matrix_job_id
  AND attempt.attempt_number = 1;

INSERT INTO test_result (
    matrix_job_id,
    suite_name,
    passed,
    tests_run,
    failures,
    duration_seconds
)
SELECT
    matrix_job_id,
    'compatibility',
    status = 'passed',
    CASE
        WHEN status = 'passed' THEN 128
        ELSE 128
    END,
    CASE
        WHEN status = 'passed' THEN 0
        ELSE 1
    END,
    CASE
        WHEN status = 'passed' THEN 14.275
        ELSE 11.904
    END
FROM matrix_job
WHERE pull_request_id = 1;

-- Matrix coverage query.
SELECT
    python_version,
    operating_system,
    dependency_mode,
    experimental,
    status
FROM matrix_job
WHERE pull_request_id = 1
ORDER BY
    python_version,
    operating_system,
    dependency_mode;

-- Find runtime versions with at least one blocking failure.
SELECT
    python_version,
    COUNT(*) AS failed_jobs
FROM matrix_job
WHERE pull_request_id = 1
  AND status = 'failed'
  AND experimental = FALSE
GROUP BY python_version
ORDER BY python_version;

-- Evaluate whether the complete matrix is merge-safe according to the
-- application-level interpretation of release-blocking matrix failures.
SELECT
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM matrix_job
            WHERE pull_request_id = 1
              AND status = 'failed'
              AND experimental = FALSE
        )
        THEN 'BLOCKED'
        WHEN EXISTS (
            SELECT 1
            FROM matrix_job
            WHERE pull_request_id = 1
              AND status IN ('queued', 'running')
        )
        THEN 'WAITING'
        ELSE 'PASS'
    END AS matrix_merge_gate;

-- Demonstrate a transaction for recording a retry. The retry is only valid
-- after a previous attempt exists, and the uniqueness constraint prevents
-- duplicate attempt numbers for the same matrix job.
BEGIN;

WITH failed_job AS (
    SELECT matrix_job_id
    FROM matrix_job
    WHERE pull_request_id = 1
      AND python_version = '3.10'
      AND operating_system = 'ubuntu'
      AND dependency_mode = 'latest'
    LIMIT 1
)
INSERT INTO matrix_job_attempt (
    matrix_job_id,
    attempt_number,
    result,
    failure_reason,
    completed_at
)
SELECT
    failed_job.matrix_job_id,
    2,
    'failed',
    'Retry reproduced the dependency compatibility failure.',
    CURRENT_TIMESTAMP
FROM failed_job
WHERE EXISTS (
    SELECT 1
    FROM matrix_job_attempt previous_attempt
    WHERE previous_attempt.matrix_job_id = failed_job.matrix_job_id
      AND previous_attempt.attempt_number = 1
);

COMMIT;

-- Aggregate test quality by operating system.
SELECT
    operating_system,
    COUNT(*) AS matrix_jobs,
    COUNT(*) FILTER (WHERE status = 'passed') AS passed_jobs,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_jobs,
    COUNT(*) FILTER (WHERE experimental) AS experimental_jobs
FROM matrix_job
WHERE pull_request_id = 1
GROUP BY operating_system
ORDER BY operating_system;

-- Identify combinations where the matrix dimension itself reveals a
-- compatibility boundary.
SELECT
    python_version,
    dependency_mode,
    COUNT(*) AS affected_operating_systems
FROM matrix_job
WHERE status = 'failed'
  AND experimental = FALSE
GROUP BY
    python_version,
    dependency_mode
ORDER BY
    python_version,
    dependency_mode;

-- PostgreSQL 15+ testing automation laboratory.
-- Models test definitions, executions, release candidates, test evidence,
-- deployment attempts, and quality gates for unit, integration, smoke,
-- and regression testing.

BEGIN;

CREATE SCHEMA IF NOT EXISTS testing_lab;
SET search_path TO testing_lab, public;

CREATE TYPE test_kind AS ENUM (
    'unit',
    'integration',
    'smoke',
    'regression'
);

CREATE TYPE test_status AS ENUM (
    'queued',
    'running',
    'passed',
    'failed',
    'skipped',
    'cancelled'
);

CREATE TYPE release_status AS ENUM (
    'created',
    'testing',
    'blocked',
    'approved',
    'deploying',
    'deployed',
    'failed',
    'rolled_back'
);

CREATE TABLE IF NOT EXISTS projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_key TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    production_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT project_key_nonempty CHECK (length(trim(project_key)) > 0),
    CONSTRAINT project_name_nonempty CHECK (length(trim(project_name)) > 0)
);

CREATE TABLE IF NOT EXISTS test_suites (
    suite_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    suite_name TEXT NOT NULL,
    test_type test_kind NOT NULL,
    execution_scope TEXT NOT NULL,
    critical BOOLEAN NOT NULL DEFAULT true,
    enabled BOOLEAN NOT NULL DEFAULT true,
    timeout_seconds INTEGER NOT NULL DEFAULT 60,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_suite_per_project UNIQUE (project_id, suite_name),
    CONSTRAINT suite_name_nonempty CHECK (length(trim(suite_name)) > 0),
    CONSTRAINT valid_timeout CHECK (timeout_seconds BETWEEN 1 AND 3600),
    CONSTRAINT valid_execution_scope CHECK (
        execution_scope IN ('isolated', 'database', 'deployed_service', 'history')
    )
);

CREATE TABLE IF NOT EXISTS test_cases (
    test_case_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suite_id BIGINT NOT NULL REFERENCES test_suites(suite_id) ON DELETE CASCADE,
    case_key TEXT NOT NULL,
    description TEXT NOT NULL,
    critical BOOLEAN NOT NULL DEFAULT true,
    automated BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT unique_case_per_suite UNIQUE (suite_id, case_key),
    CONSTRAINT case_key_nonempty CHECK (length(trim(case_key)) > 0),
    CONSTRAINT description_nonempty CHECK (length(trim(description)) > 0)
);

CREATE TABLE IF NOT EXISTS release_candidates (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    version TEXT NOT NULL,
    commit_sha CHAR(40) NOT NULL,
    target_environment TEXT NOT NULL,
    status release_status NOT NULL DEFAULT 'created',
    artifact_signed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deployed_at TIMESTAMPTZ,
    CONSTRAINT unique_project_version UNIQUE (project_id, version),
    CONSTRAINT valid_commit_sha CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT valid_environment CHECK (
        target_environment IN ('development', 'test', 'staging', 'production')
    ),
    CONSTRAINT deployment_timestamp_consistency CHECK (
        (status = 'deployed' AND deployed_at IS NOT NULL)
        OR (status <> 'deployed' AND deployed_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS test_runs (
    test_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id BIGINT NOT NULL REFERENCES release_candidates(release_id),
    suite_id BIGINT NOT NULL REFERENCES test_suites(suite_id),
    status test_status NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    tests_executed INTEGER NOT NULL DEFAULT 0,
    tests_passed INTEGER NOT NULL DEFAULT 0,
    tests_failed INTEGER NOT NULL DEFAULT 0,
    tests_skipped INTEGER NOT NULL DEFAULT 0,
    environment_fingerprint TEXT,
    failure_message TEXT,
    CONSTRAINT nonnegative_test_counts CHECK (
        tests_executed >= 0
        AND tests_passed >= 0
        AND tests_failed >= 0
        AND tests_skipped >= 0
    ),
    CONSTRAINT test_count_consistency CHECK (
        tests_passed + tests_failed + tests_skipped <= tests_executed
    ),
    CONSTRAINT completion_after_start CHECK (
        completed_at IS NULL OR
        (started_at IS NOT NULL AND completed_at >= started_at)
    ),
    CONSTRAINT completed_run_has_timestamp CHECK (
        status NOT IN ('passed', 'failed', 'skipped', 'cancelled')
        OR completed_at IS NOT NULL
    ),
    CONSTRAINT failure_requires_detail CHECK (
        status <> 'failed' OR failure_message IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS test_case_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_run_id BIGINT NOT NULL REFERENCES test_runs(test_run_id)
        ON DELETE CASCADE,
    test_case_id BIGINT NOT NULL REFERENCES test_cases(test_case_id),
    status test_status NOT NULL,
    duration_ms BIGINT NOT NULL DEFAULT 0,
    assertion_detail TEXT,
    error_type TEXT,
    error_message TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT one_result_per_case_per_run UNIQUE (test_run_id, test_case_id),
    CONSTRAINT nonnegative_duration CHECK (duration_ms >= 0),
    CONSTRAINT failure_has_error CHECK (
        status <> 'failed' OR error_message IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS release_gate_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    environment TEXT NOT NULL,
    test_type test_kind NOT NULL,
    minimum_passing_runs INTEGER NOT NULL DEFAULT 1,
    require_zero_failures BOOLEAN NOT NULL DEFAULT true,
    maximum_evidence_age INTERVAL NOT NULL DEFAULT INTERVAL '24 hours',
    enabled BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT unique_environment_gate
        UNIQUE (project_id, environment, test_type),
    CONSTRAINT positive_required_runs CHECK (minimum_passing_runs >= 1),
    CONSTRAINT valid_evidence_age CHECK (maximum_evidence_age > INTERVAL '0')
);

CREATE TABLE IF NOT EXISTS deployment_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id BIGINT NOT NULL REFERENCES release_candidates(release_id),
    attempt_number INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    detail TEXT,
    CONSTRAINT unique_release_attempt UNIQUE (release_id, attempt_number),
    CONSTRAINT positive_attempt_number CHECK (attempt_number > 0),
    CONSTRAINT valid_deployment_outcome CHECK (
        outcome IN ('started', 'succeeded', 'failed', 'rolled_back')
    ),
    CONSTRAINT valid_attempt_timing CHECK (
        finished_at IS NULL OR finished_at >= started_at
    )
);

CREATE INDEX IF NOT EXISTS idx_test_runs_release_suite
    ON test_runs(release_id, suite_id, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_test_runs_failed
    ON test_runs(completed_at DESC)
    WHERE status = 'failed';

CREATE INDEX IF NOT EXISTS idx_test_case_results_run_status
    ON test_case_results(test_run_id, status);

CREATE INDEX IF NOT EXISTS idx_release_candidates_project_created
    ON release_candidates(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deployment_attempts_release
    ON deployment_attempts(release_id, attempt_number DESC);

INSERT INTO projects(project_key, project_name, production_branch)
VALUES ('ORDER_API', 'Order Processing API', 'main')
ON CONFLICT (project_key) DO NOTHING;

INSERT INTO test_suites(
    project_id, suite_name, test_type, execution_scope, critical, timeout_seconds
)
SELECT project_id, data.suite_name, data.test_type::test_kind,
       data.execution_scope, data.critical, data.timeout_seconds
FROM projects
CROSS JOIN (
    VALUES
        ('money-and-validation', 'unit', 'isolated', true, 20),
        ('order-database-contract', 'integration', 'database', true, 90),
        ('staging-health-check', 'smoke', 'deployed_service', true, 30),
        ('duplicate-order-regression', 'regression', 'history', true, 60)
) AS data(suite_name, test_type, execution_scope, critical, timeout_seconds)
WHERE project_key = 'ORDER_API'
ON CONFLICT (project_id, suite_name) DO NOTHING;

INSERT INTO test_cases(suite_id, case_key, description, critical)
SELECT suite_id, data.case_key, data.description, data.critical
FROM test_suites
CROSS JOIN (
    VALUES
        ('decimal-total', 'Verify exact order totals at cent precision', true),
        ('reject-zero-quantity', 'Reject zero and negative quantities', true),
        ('atomic-reservation', 'Rollback stock changes when order insertion fails', true),
        ('health-ready', 'Verify that the deployed API readiness endpoint responds', true),
        ('duplicate-submit', 'Prevent a repeated request from reserving stock twice', true)
) AS data(case_key, description, critical)
WHERE suite_name IN (
    'money-and-validation',
    'order-database-contract',
    'staging-health-check',
    'duplicate-order-regression'
)
ON CONFLICT (suite_id, case_key) DO NOTHING;

INSERT INTO release_gate_policies(
    project_id, environment, test_type, minimum_passing_runs,
    require_zero_failures, maximum_evidence_age
)
SELECT project_id, 'staging', data.test_type::test_kind, 1, true, INTERVAL '24 hours'
FROM projects
CROSS JOIN (
    VALUES ('unit'), ('integration'), ('smoke'), ('regression')
) AS data(test_type)
WHERE project_key = 'ORDER_API'
ON CONFLICT (project_id, environment, test_type) DO NOTHING;

INSERT INTO release_candidates(
    project_id, version, commit_sha, target_environment, status, artifact_signed
)
SELECT project_id, '2026.10.12-rc1',
       '0123456789abcdef0123456789abcdef01234567',
       'staging', 'testing', true
FROM projects
WHERE project_key = 'ORDER_API'
ON CONFLICT (project_id, version) DO NOTHING;

-- The sample runs intentionally include successful, failed, and skipped evidence.
-- A failed smoke test prevents release even if unit tests pass.
INSERT INTO test_runs(
    release_id, suite_id, status, started_at, completed_at,
    tests_executed, tests_passed, tests_failed, tests_skipped,
    environment_fingerprint, failure_message
)
SELECT rc.release_id, ts.suite_id, sample.status::test_status,
       now() - sample.elapsed,
       now() - sample.elapsed + INTERVAL '2 seconds',
       sample.executed, sample.passed, sample.failed, sample.skipped,
       sample.fingerprint, sample.failure_message
FROM release_candidates rc
JOIN projects p ON p.project_id = rc.project_id
CROSS JOIN (
    VALUES
        ('money-and-validation', 'passed', INTERVAL '15 minutes',
         20, 20, 0, 0, 'python-3.13-linux-x86_64', NULL::TEXT),
        ('order-database-contract', 'passed', INTERVAL '12 minutes',
         12, 12, 0, 0, 'postgres-18-test-db', NULL::TEXT),
        ('staging-health-check', 'failed', INTERVAL '8 minutes',
         4, 3, 1, 0, 'staging-build-rc1', 'Readiness endpoint returned HTTP 503'),
        ('duplicate-order-regression', 'passed', INTERVAL '6 minutes',
         9, 9, 0, 0, 'python-3.13-linux-x86_64', NULL::TEXT)
) AS sample(
    suite_name, status, elapsed, executed, passed, failed, skipped,
    fingerprint, failure_message
)
JOIN test_suites ts
  ON ts.project_id = p.project_id
 AND ts.suite_name = sample.suite_name
WHERE rc.version = '2026.10.12-rc1'
  AND p.project_key = 'ORDER_API'
  AND NOT EXISTS (
      SELECT 1
      FROM test_runs existing
      WHERE existing.release_id = rc.release_id
        AND existing.suite_id = ts.suite_id
  );

-- View: one row per release and required test category.
CREATE OR REPLACE VIEW release_test_summary AS
SELECT
    rc.release_id,
    p.project_key,
    rc.version,
    rc.target_environment,
    ts.test_type,
    COUNT(tr.test_run_id) AS run_count,
    COUNT(*) FILTER (WHERE tr.status = 'passed') AS passing_runs,
    COUNT(*) FILTER (WHERE tr.status = 'failed') AS failing_runs,
    MAX(tr.completed_at) AS latest_completion,
    COALESCE(SUM(tr.tests_executed), 0) AS tests_executed,
    COALESCE(SUM(tr.tests_failed), 0) AS failed_test_cases
FROM release_candidates rc
JOIN projects p ON p.project_id = rc.project_id
JOIN test_suites ts ON ts.project_id = p.project_id
LEFT JOIN test_runs tr
       ON tr.release_id = rc.release_id
      AND tr.suite_id = ts.suite_id
GROUP BY
    rc.release_id, p.project_key, rc.version,
    rc.target_environment, ts.test_type;

-- View: policy evaluation for every required test category.
CREATE OR REPLACE VIEW release_gate_evaluation AS
SELECT
    rc.release_id,
    rc.version,
    rc.target_environment,
    policy.test_type,
    policy.minimum_passing_runs,
    policy.require_zero_failures,
    policy.maximum_evidence_age,
    COALESCE(summary.passing_runs, 0) AS passing_runs,
    COALESCE(summary.failing_runs, 0) AS failing_runs,
    summary.latest_completion,
    CASE
        WHEN NOT policy.enabled THEN true
        WHEN COALESCE(summary.passing_runs, 0) < policy.minimum_passing_runs
            THEN false
        WHEN policy.require_zero_failures
             AND COALESCE(summary.failing_runs, 0) > 0
            THEN false
        WHEN summary.latest_completion IS NULL THEN false
        WHEN summary.latest_completion < now() - policy.maximum_evidence_age
            THEN false
        ELSE true
    END AS gate_passed
FROM release_candidates rc
JOIN release_gate_policies policy
  ON policy.project_id = rc.project_id
 AND policy.environment = rc.target_environment
LEFT JOIN release_test_summary summary
  ON summary.release_id = rc.release_id
 AND summary.test_type = policy.test_type;

-- Deployment eligibility includes the test gate and artifact provenance.
CREATE OR REPLACE VIEW release_deployment_eligibility AS
SELECT
    rc.release_id,
    p.project_key,
    rc.version,
    rc.target_environment,
    rc.status,
    rc.artifact_signed,
    COUNT(e.test_type) FILTER (WHERE NOT e.gate_passed) AS failed_gates,
    BOOL_AND(e.gate_passed) AS all_test_gates_passed,
    (
        BOOL_AND(e.gate_passed)
        AND rc.artifact_signed
        AND rc.status IN ('testing', 'approved')
    ) AS deployment_eligible
FROM release_candidates rc
JOIN projects p ON p.project_id = rc.project_id
LEFT JOIN release_gate_evaluation e ON e.release_id = rc.release_id
GROUP BY
    rc.release_id, p.project_key, rc.version, rc.target_environment,
    rc.status, rc.artifact_signed;

-- Investigate test failures with suite names and release metadata.
SELECT
    rc.version,
    ts.test_type,
    ts.suite_name,
    tr.status,
    tr.tests_executed,
    tr.tests_failed,
    tr.failure_message,
    tr.environment_fingerprint
FROM test_runs tr
JOIN release_candidates rc ON rc.release_id = tr.release_id
JOIN test_suites ts ON ts.suite_id = tr.suite_id
WHERE tr.status = 'failed'
ORDER BY tr.completed_at DESC;

-- Compare the release's test coverage across all four test categories.
SELECT
    version,
    test_type,
    run_count,
    passing_runs,
    failing_runs,
    tests_executed,
    failed_test_cases
FROM release_test_summary
WHERE version = '2026.10.12-rc1'
ORDER BY test_type;

-- Determine exactly which category blocks the deployment.
SELECT
    version,
    test_type,
    passing_runs,
    failing_runs,
    latest_completion,
    gate_passed
FROM release_gate_evaluation
WHERE version = '2026.10.12-rc1'
ORDER BY test_type;

SELECT *
FROM release_deployment_eligibility
WHERE version = '2026.10.12-rc1';

-- A failed release is intentionally not marked deployed. This guarded update
-- illustrates database-side deployment state management without bypassing gates.
UPDATE release_candidates rc
SET status = 'approved'
WHERE rc.version = '2026.10.12-rc1'
  AND rc.status = 'testing'
  AND EXISTS (
      SELECT 1
      FROM release_deployment_eligibility eligibility
      WHERE eligibility.release_id = rc.release_id
        AND eligibility.deployment_eligible
  );

-- The following query should return no rows while the smoke test is failing.
SELECT rc.version
FROM release_candidates rc
JOIN release_deployment_eligibility eligibility
  ON eligibility.release_id = rc.release_id
WHERE rc.version = '2026.10.12-rc1'
  AND eligibility.deployment_eligible;

COMMIT;

-- PostgreSQL constraint demonstration:
-- A negative duration or a completed test run without completed_at is rejected.
-- A production CI integration should write test evidence with a dedicated role
-- and restrict direct modifications to completed results.

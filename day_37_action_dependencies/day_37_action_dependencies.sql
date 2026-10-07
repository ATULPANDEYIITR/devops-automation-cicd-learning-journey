DROP SCHEMA IF EXISTS actions_dependency_demo CASCADE;
CREATE SCHEMA actions_dependency_demo;
SET search_path TO actions_dependency_demo;

-- PostgreSQL model for GitHub Actions-style workflow dependencies.
-- The database separates workflow structure, job dependency edges,
-- execution results, conditions, and environment-specific release policy.

CREATE TYPE job_status AS ENUM (
    'pending',
    'running',
    'success',
    'failure',
    'skipped',
    'cancelled'
);

CREATE TYPE workflow_event_type AS ENUM (
    'push',
    'pull_request',
    'workflow_dispatch'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workflow_runs (
    workflow_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    workflow_name TEXT NOT NULL,
    event_type workflow_event_type NOT NULL,
    source_branch TEXT NOT NULL,
    release_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE TABLE workflow_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL
        REFERENCES workflow_runs(workflow_run_id)
        ON DELETE CASCADE,
    job_name TEXT NOT NULL,
    status job_status NOT NULL DEFAULT 'pending',
    condition_expression TEXT,
    allow_failure BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (workflow_run_id, job_name)
);

-- A directed edge A -> B means B needs A.
CREATE TABLE job_dependencies (
    workflow_run_id BIGINT NOT NULL
        REFERENCES workflow_runs(workflow_run_id)
        ON DELETE CASCADE,
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id)
        ON DELETE CASCADE,
    dependency_job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id)
        ON DELETE CASCADE,
    PRIMARY KEY (job_id, dependency_job_id),
    CHECK (job_id <> dependency_job_id)
);

CREATE TABLE job_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id)
        ON DELETE CASCADE,
    output_name TEXT NOT NULL,
    output_value TEXT NOT NULL,
    UNIQUE (job_id, output_name)
);

CREATE TABLE workflow_job_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id)
        ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    status job_status NOT NULL,
    message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (job_id, attempt_number)
);

CREATE TABLE conditional_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL
        REFERENCES workflow_runs(workflow_run_id)
        ON DELETE CASCADE,
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id)
        ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    expression TEXT NOT NULL,
    expected_result BOOLEAN NOT NULL,
    actual_result BOOLEAN,
    evaluated_at TIMESTAMPTZ,
    UNIQUE (job_id, rule_name)
);

CREATE INDEX idx_workflow_jobs_run_status
    ON workflow_jobs(workflow_run_id, status);

CREATE INDEX idx_job_dependencies_dependency
    ON job_dependencies(dependency_job_id);

CREATE INDEX idx_job_outputs_job
    ON job_outputs(job_id);

CREATE INDEX idx_attempts_job_status
    ON workflow_job_attempts(job_id, status);

INSERT INTO repositories (repository_name, default_branch)
VALUES ('payments-service', 'main');

INSERT INTO workflow_runs (
    repository_id,
    workflow_name,
    event_type,
    source_branch,
    release_enabled
)
SELECT
    repository_id,
    'production-ci',
    'push',
    'main',
    TRUE
FROM repositories
WHERE repository_name = 'payments-service';

INSERT INTO workflow_jobs (
    workflow_run_id,
    job_name,
    condition_expression
)
SELECT
    workflow_run_id,
    job_name,
    condition_expression
FROM workflow_runs
CROSS JOIN (
    VALUES
        ('build', NULL),
        ('lint', NULL),
        ('unit-tests', NULL),
        ('security', NULL),
        (
            'package',
            'all required validation jobs succeeded'
        ),
        (
            'deploy',
            'main branch AND release enabled'
        ),
        (
            'diagnostics',
            'always eligible after dependency reaches terminal state'
        )
) AS definitions(job_name, condition_expression)
WHERE workflow_name = 'production-ci';

-- Insert the dependency graph after all jobs exist.
INSERT INTO job_dependencies (
    workflow_run_id,
    job_id,
    dependency_job_id
)
SELECT
    wr.workflow_run_id,
    child.job_id,
    parent.job_id
FROM workflow_runs wr
JOIN workflow_jobs child
    ON child.workflow_run_id = wr.workflow_run_id
JOIN workflow_jobs parent
    ON parent.workflow_run_id = wr.workflow_run_id
JOIN (
    VALUES
        ('lint', 'build'),
        ('unit-tests', 'build'),
        ('security', 'build'),
        ('package', 'lint'),
        ('package', 'unit-tests'),
        ('package', 'security'),
        ('deploy', 'package'),
        ('diagnostics', 'deploy')
) AS edges(child_name, parent_name)
    ON child.job_name = edges.child_name
   AND parent.job_name = edges.parent_name
WHERE wr.workflow_name = 'production-ci';

-- Initial execution states.
UPDATE workflow_jobs
SET
    status = CASE job_name
        WHEN 'build' THEN 'success'::job_status
        WHEN 'lint' THEN 'success'::job_status
        WHEN 'unit-tests' THEN 'success'::job_status
        WHEN 'security' THEN 'success'::job_status
        WHEN 'package' THEN 'success'::job_status
        WHEN 'deploy' THEN 'success'::job_status
        WHEN 'diagnostics' THEN 'success'::job_status
    END,
    started_at = CURRENT_TIMESTAMP,
    completed_at = CURRENT_TIMESTAMP
WHERE workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
);

INSERT INTO job_outputs (job_id, output_name, output_value)
SELECT
    job_id,
    'artifact',
    'dist/payments-service.tar.gz'
FROM workflow_jobs
WHERE job_name = 'build';

INSERT INTO job_outputs (job_id, output_name, output_value)
SELECT
    job_id,
    'coverage',
    '94.1'
FROM workflow_jobs
WHERE job_name = 'unit-tests';

INSERT INTO conditional_rules (
    workflow_run_id,
    job_id,
    rule_name,
    expression,
    expected_result,
    actual_result,
    evaluated_at
)
SELECT
    wr.workflow_run_id,
    j.job_id,
    'production-release-policy',
    'event is push AND source branch is main AND release_enabled is true',
    TRUE,
    TRUE,
    CURRENT_TIMESTAMP
FROM workflow_runs wr
JOIN workflow_jobs j
    ON j.workflow_run_id = wr.workflow_run_id
WHERE wr.workflow_name = 'production-ci'
  AND j.job_name = 'deploy';

-- Jobs that have all dependencies satisfied can be identified with a
-- relational aggregate. This query distinguishes dependency ordering from
-- job eligibility.
SELECT
    j.job_name,
    j.status,
    COUNT(d.dependency_job_id) AS dependency_count,
    COUNT(d.dependency_job_id)
        FILTER (
            WHERE parent.status = 'success'
        ) AS successful_dependencies,
    CASE
        WHEN COUNT(d.dependency_job_id) = 0 THEN TRUE
        ELSE COUNT(d.dependency_job_id)
             = COUNT(d.dependency_job_id)
                 FILTER (
                     WHERE parent.status = 'success'
                 )
    END AS default_dependency_gate
FROM workflow_jobs j
LEFT JOIN job_dependencies d
    ON d.job_id = j.job_id
LEFT JOIN workflow_jobs parent
    ON parent.job_id = d.dependency_job_id
WHERE j.workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
GROUP BY j.job_id, j.job_name, j.status
ORDER BY j.job_id;

-- Find jobs that are blocked by at least one unsuccessful dependency.
SELECT
    child.job_name AS blocked_job,
    parent.job_name AS blocking_dependency,
    parent.status AS dependency_status
FROM workflow_jobs child
JOIN job_dependencies d
    ON d.job_id = child.job_id
JOIN workflow_jobs parent
    ON parent.job_id = d.dependency_job_id
WHERE child.workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
AND parent.status <> 'success'
ORDER BY child.job_name, parent.job_name;

-- Fan-in analysis identifies jobs that depend on multiple independent
-- validation branches.
SELECT
    j.job_name,
    COUNT(d.dependency_job_id) AS required_dependencies,
    ARRAY_AGG(parent.job_name ORDER BY parent.job_name) AS dependencies
FROM workflow_jobs j
JOIN job_dependencies d
    ON d.job_id = j.job_id
JOIN workflow_jobs parent
    ON parent.job_id = d.dependency_job_id
GROUP BY j.job_id, j.job_name
HAVING COUNT(d.dependency_job_id) > 1
ORDER BY j.job_name;

-- Determine which jobs are eligible under the default success-only rule.
SELECT
    j.job_name,
    CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM job_dependencies d
            JOIN workflow_jobs dependency_job
                ON dependency_job.job_id = d.dependency_job_id
            WHERE d.job_id = j.job_id
              AND dependency_job.status <> 'success'
        )
        THEN TRUE
        ELSE FALSE
    END AS eligible_by_default_dependency_rule
FROM workflow_jobs j
WHERE j.workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
ORDER BY j.job_name;

-- Transactional example: a job result and its attempt record should be
-- persisted together so an execution record cannot be separated from its
-- corresponding attempt history.
BEGIN;

WITH target AS (
    SELECT job_id
    FROM workflow_jobs
    WHERE job_name = 'package'
      AND workflow_run_id = (
          SELECT workflow_run_id
          FROM workflow_runs
          WHERE workflow_name = 'production-ci'
      )
)
UPDATE workflow_jobs
SET
    status = 'success',
    completed_at = CURRENT_TIMESTAMP
WHERE job_id = (SELECT job_id FROM target);

INSERT INTO workflow_job_attempts (
    job_id,
    attempt_number,
    status,
    message,
    completed_at
)
SELECT
    job_id,
    1,
    'success',
    'Package created after all validation dependencies passed.',
    CURRENT_TIMESTAMP
FROM workflow_jobs
WHERE job_name = 'package'
  AND workflow_run_id = (
      SELECT workflow_run_id
      FROM workflow_runs
      WHERE workflow_name = 'production-ci'
  );

COMMIT;

-- Demonstrate a blocked downstream path by changing one independent
-- validation job to failure. Package and deployment then become ineligible
-- under the default success-only dependency rule.
BEGIN;

UPDATE workflow_jobs
SET
    status = 'failure',
    completed_at = CURRENT_TIMESTAMP
WHERE workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
AND job_name = 'security';

UPDATE workflow_jobs
SET
    status = 'skipped',
    completed_at = CURRENT_TIMESTAMP
WHERE workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
AND job_name IN ('package', 'deploy');

COMMIT;

-- A diagnostic job may intentionally run after an unsuccessful dependency.
-- This query demonstrates why "dependency failed" and "job must not run"
-- are separate policy decisions.
UPDATE workflow_jobs
SET
    status = 'success',
    completed_at = CURRENT_TIMESTAMP
WHERE workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
AND job_name = 'diagnostics';

SELECT
    j.job_name,
    j.status,
    CASE
        WHEN j.job_name = 'diagnostics'
             AND EXISTS (
                 SELECT 1
                 FROM job_dependencies d
                 JOIN workflow_jobs parent
                     ON parent.job_id = d.dependency_job_id
                 WHERE d.job_id = j.job_id
                   AND parent.status = 'failure'
             )
        THEN 'explicit failure-tolerant policy'
        WHEN j.status = 'skipped'
        THEN 'default dependency propagation'
        ELSE 'normal execution'
    END AS execution_reason
FROM workflow_jobs j
WHERE j.workflow_run_id = (
    SELECT workflow_run_id
    FROM workflow_runs
    WHERE workflow_name = 'production-ci'
)
ORDER BY j.job_id;

-- Recursive dependency expansion provides the complete upstream ancestry
-- of a selected job. This is useful for debugging unexpectedly skipped jobs.
WITH RECURSIVE dependency_tree AS (
    SELECT
        j.job_id,
        j.job_name,
        j.job_name AS root_job,
        0 AS depth
    FROM workflow_jobs j
    WHERE j.job_name = 'deploy'
      AND j.workflow_run_id = (
          SELECT workflow_run_id
          FROM workflow_runs
          WHERE workflow_name = 'production-ci'
      )

    UNION ALL

    SELECT
        parent.job_id,
        parent.job_name,
        tree.root_job,
        tree.depth + 1
    FROM dependency_tree tree
    JOIN job_dependencies d
        ON d.job_id = tree.job_id
    JOIN workflow_jobs parent
        ON parent.job_id = d.dependency_job_id
)
SELECT
    root_job,
    depth,
    job_name
FROM dependency_tree
ORDER BY depth, job_name;

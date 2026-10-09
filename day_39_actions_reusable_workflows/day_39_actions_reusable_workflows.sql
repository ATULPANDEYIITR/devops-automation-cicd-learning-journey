-- PostgreSQL 15+
-- Relational model of reusable GitHub Actions workflows and composite actions.
--
-- The schema distinguishes workflow-level calls, action-level step reuse,
-- caller-supplied inputs, job dependencies, execution results, and governance
-- checks. The data represents a shared release workflow used by application
-- repositories with different deployment policies.

BEGIN;

CREATE TABLE IF NOT EXISTS repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    visibility TEXT NOT NULL
        CHECK (visibility IN ('public', 'private', 'internal')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_name, repository_name)
);

CREATE TABLE IF NOT EXISTS workflow_definitions (
    workflow_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    workflow_path TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    workflow_kind TEXT NOT NULL
        CHECK (workflow_kind IN ('reusable', 'caller')),
    version_ref TEXT NOT NULL,
    immutable_revision TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id, workflow_path, version_ref),
    CHECK (
        workflow_kind <> 'reusable'
        OR workflow_path LIKE '.github/workflows/%'
    ),
    CHECK (
        immutable_revision IS NULL
        OR immutable_revision ~ '^[0-9a-fA-F]{40}$'
    )
);

CREATE TABLE IF NOT EXISTS composite_actions (
    action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    action_path TEXT NOT NULL,
    action_name TEXT NOT NULL,
    version_ref TEXT NOT NULL,
    immutable_revision TEXT,
    UNIQUE (repository_id, action_path, version_ref),
    CHECK (action_path NOT LIKE '.github/workflows/%'),
    CHECK (
        immutable_revision IS NULL
        OR immutable_revision ~ '^[0-9a-fA-F]{40}$'
    )
);

CREATE TABLE IF NOT EXISTS workflow_inputs (
    input_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_id BIGINT NOT NULL
        REFERENCES workflow_definitions(workflow_id) ON DELETE CASCADE,
    input_name TEXT NOT NULL,
    input_type TEXT NOT NULL
        CHECK (input_type IN ('string', 'boolean', 'number')),
    required BOOLEAN NOT NULL DEFAULT FALSE,
    default_value TEXT,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (workflow_id, input_name),
    CHECK (NOT required OR default_value IS NULL)
);

CREATE TABLE IF NOT EXISTS action_inputs (
    input_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id BIGINT NOT NULL
        REFERENCES composite_actions(action_id) ON DELETE CASCADE,
    input_name TEXT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    default_value TEXT,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (action_id, input_name),
    CHECK (NOT required OR default_value IS NULL)
);

CREATE TABLE IF NOT EXISTS workflow_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_id BIGINT NOT NULL
        REFERENCES workflow_definitions(workflow_id) ON DELETE CASCADE,
    output_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (workflow_id, output_name)
);

CREATE TABLE IF NOT EXISTS action_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id BIGINT NOT NULL
        REFERENCES composite_actions(action_id) ON DELETE CASCADE,
    output_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (action_id, output_name)
);

CREATE TABLE IF NOT EXISTS workflow_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workflow_id BIGINT NOT NULL
        REFERENCES workflow_definitions(workflow_id) ON DELETE CASCADE,
    job_name TEXT NOT NULL,
    execution_kind TEXT NOT NULL
        CHECK (execution_kind IN ('normal', 'reusable_workflow_call')),
    runner_label TEXT,
    UNIQUE (workflow_id, job_name),
    CHECK (
        execution_kind <> 'reusable_workflow_call'
        OR runner_label IS NULL
    )
);

CREATE TABLE IF NOT EXISTS job_dependencies (
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id) ON DELETE CASCADE,
    dependency_job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, dependency_job_id),
    CHECK (job_id <> dependency_job_id)
);

CREATE TABLE IF NOT EXISTS workflow_action_calls (
    call_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id) ON DELETE CASCADE,
    action_id BIGINT NOT NULL
        REFERENCES composite_actions(action_id),
    step_name TEXT NOT NULL,
    UNIQUE (job_id, step_name)
);

CREATE TABLE IF NOT EXISTS workflow_invocations (
    invocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caller_workflow_id BIGINT NOT NULL
        REFERENCES workflow_definitions(workflow_id),
    callee_workflow_id BIGINT NOT NULL
        REFERENCES workflow_definitions(workflow_id),
    caller_job_id BIGINT NOT NULL
        REFERENCES workflow_jobs(job_id),
    source_revision TEXT NOT NULL
        CHECK (source_revision ~ '^[0-9a-fA-F]{7,64}$'),
    invoked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN (
            'queued', 'running', 'succeeded', 'failed', 'cancelled'
        )),
    CHECK (caller_workflow_id <> callee_workflow_id)
);

CREATE TABLE IF NOT EXISTS invocation_input_values (
    invocation_id BIGINT NOT NULL
        REFERENCES workflow_invocations(invocation_id) ON DELETE CASCADE,
    input_id BIGINT NOT NULL
        REFERENCES workflow_inputs(input_id),
    supplied_value TEXT NOT NULL,
    PRIMARY KEY (invocation_id, input_id)
);

CREATE TABLE IF NOT EXISTS invocation_secret_grants (
    invocation_id BIGINT NOT NULL
        REFERENCES workflow_invocations(invocation_id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    grant_mode TEXT NOT NULL
        CHECK (grant_mode IN ('explicit', 'inherited')),
    PRIMARY KEY (invocation_id, secret_name)
);

CREATE TABLE IF NOT EXISTS job_executions (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invocation_id BIGINT NOT NULL
        REFERENCES workflow_invocations(invocation_id) ON DELETE CASCADE,
    job_id BIGINT NOT NULL REFERENCES workflow_jobs(job_id),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN (
            'queued', 'running', 'succeeded', 'failed', 'skipped', 'cancelled'
        )),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    failure_message TEXT,
    UNIQUE (invocation_id, job_id),
    CHECK (
        finished_at IS NULL
        OR started_at IS NULL
        OR finished_at >= started_at
    ),
    CHECK (
        state <> 'failed'
        OR failure_message IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS execution_outputs (
    execution_id BIGINT NOT NULL
        REFERENCES job_executions(execution_id) ON DELETE CASCADE,
    output_name TEXT NOT NULL,
    output_value TEXT NOT NULL,
    PRIMARY KEY (execution_id, output_name)
);

CREATE TABLE IF NOT EXISTS workflow_status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invocation_id BIGINT NOT NULL
        REFERENCES workflow_invocations(invocation_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    conclusion TEXT NOT NULL
        CHECK (conclusion IN (
            'queued', 'in_progress', 'success', 'failure', 'cancelled', 'skipped'
        )),
    checked_at TIMESTAMPTZ,
    details TEXT NOT NULL DEFAULT '',
    UNIQUE (invocation_id, check_name)
);

CREATE INDEX IF NOT EXISTS idx_workflow_jobs_workflow
    ON workflow_jobs(workflow_id);

CREATE INDEX IF NOT EXISTS idx_job_dependencies_dependency
    ON job_dependencies(dependency_job_id);

CREATE INDEX IF NOT EXISTS idx_invocations_callee_state
    ON workflow_invocations(callee_workflow_id, state, invoked_at DESC);

CREATE INDEX IF NOT EXISTS idx_job_executions_invocation_state
    ON job_executions(invocation_id, state);

CREATE INDEX IF NOT EXISTS idx_status_checks_invocation_conclusion
    ON workflow_status_checks(invocation_id, conclusion);

-- This trigger enforces same-workflow job dependencies and prevents dependency
-- edges from linking unrelated workflow definitions.
CREATE OR REPLACE FUNCTION enforce_same_workflow_dependency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_workflow BIGINT;
    dependency_workflow BIGINT;
BEGIN
    SELECT workflow_id INTO source_workflow
    FROM workflow_jobs
    WHERE job_id = NEW.job_id;

    SELECT workflow_id INTO dependency_workflow
    FROM workflow_jobs
    WHERE job_id = NEW.dependency_job_id;

    IF source_workflow IS NULL OR dependency_workflow IS NULL THEN
        RAISE EXCEPTION 'Both dependency jobs must exist';
    END IF;

    IF source_workflow <> dependency_workflow THEN
        RAISE EXCEPTION
            'A job dependency must reference a job in the same workflow';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_same_workflow_dependency
    ON job_dependencies;

CREATE TRIGGER trg_same_workflow_dependency
BEFORE INSERT OR UPDATE ON job_dependencies
FOR EACH ROW
EXECUTE FUNCTION enforce_same_workflow_dependency();

-- Example repository catalogue.
INSERT INTO repositories (owner_name, repository_name, visibility)
VALUES
    ('acme', 'shared-automation', 'private'),
    ('acme', 'inventory-service', 'private'),
    ('acme', 'billing-service', 'private')
ON CONFLICT (owner_name, repository_name) DO NOTHING;

INSERT INTO workflow_definitions (
    repository_id, workflow_path, workflow_name, workflow_kind,
    version_ref, immutable_revision
)
SELECT r.repository_id,
       '.github/workflows/release.yml',
       'Shared Release',
       'reusable',
       'v2.1.0',
       'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
FROM repositories r
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
ON CONFLICT (repository_id, workflow_path, version_ref) DO NOTHING;

INSERT INTO workflow_definitions (
    repository_id, workflow_path, workflow_name, workflow_kind,
    version_ref, immutable_revision
)
SELECT r.repository_id,
       '.github/workflows/ci.yml',
       'Inventory CI',
       'caller',
       'main',
       NULL
FROM repositories r
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'inventory-service'
ON CONFLICT (repository_id, workflow_path, version_ref) DO NOTHING;

INSERT INTO workflow_definitions (
    repository_id, workflow_path, workflow_name, workflow_kind,
    version_ref, immutable_revision
)
SELECT r.repository_id,
       '.github/workflows/ci.yml',
       'Billing CI',
       'caller',
       'main',
       NULL
FROM repositories r
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'billing-service'
ON CONFLICT (repository_id, workflow_path, version_ref) DO NOTHING;

INSERT INTO composite_actions (
    repository_id, action_path, action_name, version_ref, immutable_revision
)
SELECT repository_id,
       'actions/deploy-service',
       'Deploy Service',
       'v1.3.0',
       'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
FROM repositories
WHERE owner_name = 'acme'
  AND repository_name = 'shared-automation'
ON CONFLICT (repository_id, action_path, version_ref) DO NOTHING;

INSERT INTO workflow_inputs (
    workflow_id, input_name, input_type, required, default_value, description
)
SELECT w.workflow_id, 'release-version', 'string', TRUE, NULL,
       'Semantic release version'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, input_name) DO NOTHING;

INSERT INTO workflow_inputs (
    workflow_id, input_name, input_type, required, default_value, description
)
SELECT w.workflow_id, 'target-environment', 'string', FALSE, 'staging',
       'Deployment destination'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, input_name) DO NOTHING;

INSERT INTO action_inputs (
    action_id, input_name, required, default_value, description
)
SELECT a.action_id, 'target-environment', TRUE, NULL,
       'Deployment destination'
FROM composite_actions a
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
ON CONFLICT (action_id, input_name) DO NOTHING;

INSERT INTO action_inputs (
    action_id, input_name, required, default_value, description
)
SELECT a.action_id, 'release-version', TRUE, NULL,
       'Release version to package'
FROM composite_actions a
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
ON CONFLICT (action_id, input_name) DO NOTHING;

INSERT INTO action_outputs (action_id, output_name, description)
SELECT a.action_id, 'artifact-name', 'Name of the prepared release artifact'
FROM composite_actions a
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
ON CONFLICT (action_id, output_name) DO NOTHING;

INSERT INTO action_outputs (action_id, output_name, description)
SELECT a.action_id, 'deployment-target', 'Validated deployment destination'
FROM composite_actions a
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
ON CONFLICT (action_id, output_name) DO NOTHING;

INSERT INTO workflow_outputs (workflow_id, output_name, description)
SELECT w.workflow_id, 'artifact-name', 'Release artifact produced by the workflow'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, output_name) DO NOTHING;

INSERT INTO workflow_jobs (
    workflow_id, job_name, execution_kind, runner_label
)
SELECT w.workflow_id, 'test', 'normal', 'ubuntu-latest'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, job_name) DO NOTHING;

INSERT INTO workflow_jobs (
    workflow_id, job_name, execution_kind, runner_label
)
SELECT w.workflow_id, 'release', 'normal', 'ubuntu-latest'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, job_name) DO NOTHING;

INSERT INTO workflow_jobs (
    workflow_id, job_name, execution_kind, runner_label
)
SELECT w.workflow_id, 'audit', 'normal', 'ubuntu-latest'
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND w.workflow_name = 'Shared Release'
ON CONFLICT (workflow_id, job_name) DO NOTHING;

INSERT INTO job_dependencies (job_id, dependency_job_id)
SELECT release_job.job_id, test_job.job_id
FROM workflow_jobs release_job
JOIN workflow_jobs test_job
  ON test_job.workflow_id = release_job.workflow_id
WHERE release_job.job_name = 'release'
  AND test_job.job_name = 'test'
ON CONFLICT DO NOTHING;

INSERT INTO job_dependencies (job_id, dependency_job_id)
SELECT audit_job.job_id, release_job.job_id
FROM workflow_jobs audit_job
JOIN workflow_jobs release_job
  ON release_job.workflow_id = audit_job.workflow_id
WHERE audit_job.job_name = 'audit'
  AND release_job.job_name = 'release'
ON CONFLICT DO NOTHING;

INSERT INTO workflow_action_calls (job_id, action_id, step_name)
SELECT j.job_id, a.action_id, 'deploy-service'
FROM workflow_jobs j
JOIN workflow_definitions w USING (workflow_id)
JOIN repositories r ON r.repository_id = w.repository_id
JOIN composite_actions a ON a.repository_id = r.repository_id
WHERE r.owner_name = 'acme'
  AND r.repository_name = 'shared-automation'
  AND j.job_name = 'release'
  AND a.action_name = 'Deploy Service'
ON CONFLICT (job_id, step_name) DO NOTHING;

-- Create representative invocation records for successful staging and blocked
-- production attempts. The latter is failed at the policy layer in this sample.
WITH workflow_ids AS (
    SELECT
        MAX(w.workflow_id) FILTER (
            WHERE w.workflow_name = 'Shared Release'
        ) AS reusable_id,
        MAX(w.workflow_id) FILTER (
            WHERE r.repository_name = 'inventory-service'
        ) AS inventory_id,
        MAX(j.job_id) FILTER (
            WHERE r.repository_name = 'inventory-service'
              AND j.job_name = 'release'
        ) AS caller_job_id
    FROM workflow_definitions w
    JOIN repositories r USING (repository_id)
    LEFT JOIN workflow_jobs j ON j.workflow_id = w.workflow_id
)
INSERT INTO workflow_invocations (
    caller_workflow_id, callee_workflow_id, caller_job_id,
    source_revision, state
)
SELECT inventory_id, reusable_id, caller_job_id,
       'c1234567890abcdef1234567890abcdef1234567', 'succeeded'
FROM workflow_ids
WHERE reusable_id IS NOT NULL
  AND inventory_id IS NOT NULL
  AND caller_job_id IS NOT NULL
ON CONFLICT DO NOTHING;

WITH workflow_ids AS (
    SELECT
        MAX(w.workflow_id) FILTER (
            WHERE w.workflow_name = 'Shared Release'
        ) AS reusable_id,
        MAX(w.workflow_id) FILTER (
            WHERE r.repository_name = 'billing-service'
        ) AS billing_id,
        MAX(j.job_id) FILTER (
            WHERE r.repository_name = 'billing-service'
              AND j.job_name = 'release'
        ) AS caller_job_id
    FROM workflow_definitions w
    JOIN repositories r USING (repository_id)
    LEFT JOIN workflow_jobs j ON j.workflow_id = w.workflow_id
)
INSERT INTO workflow_invocations (
    caller_workflow_id, callee_workflow_id, caller_job_id,
    source_revision, state
)
SELECT billing_id, reusable_id, caller_job_id,
       'd2345678901abcdef1234567890abcdef12345678', 'failed'
FROM workflow_ids
WHERE reusable_id IS NOT NULL
  AND billing_id IS NOT NULL
  AND caller_job_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- The queries below are the executable reporting interface.

-- Inspect reusable workflows and their immutable revision pins.
SELECT r.owner_name,
       r.repository_name,
       w.workflow_path,
       w.version_ref,
       w.immutable_revision,
       w.enabled
FROM workflow_definitions w
JOIN repositories r USING (repository_id)
WHERE w.workflow_kind = 'reusable'
ORDER BY r.repository_name, w.workflow_path;

-- Show each reusable workflow's callable interface.
SELECT w.workflow_name,
       i.input_name,
       i.input_type,
       i.required,
       i.default_value,
       i.description
FROM workflow_definitions w
JOIN workflow_inputs i USING (workflow_id)
WHERE w.workflow_kind = 'reusable'
ORDER BY w.workflow_name, i.input_name;

-- Distinguish job-level workflow reuse from step-level action reuse.
SELECT r.repository_name,
       w.workflow_name,
       j.job_name,
       j.execution_kind,
       j.runner_label,
       a.action_name,
       c.step_name
FROM workflow_jobs j
JOIN workflow_definitions w USING (workflow_id)
JOIN repositories r USING (repository_id)
LEFT JOIN workflow_action_calls c USING (job_id)
LEFT JOIN composite_actions a USING (action_id)
ORDER BY r.repository_name, w.workflow_name, j.job_name;

-- Dependency edges describe the workflow's job execution graph.
SELECT w.workflow_name,
       source_job.job_name AS dependent_job,
       dependency_job.job_name AS required_job
FROM job_dependencies d
JOIN workflow_jobs source_job ON source_job.job_id = d.job_id
JOIN workflow_jobs dependency_job
  ON dependency_job.job_id = d.dependency_job_id
JOIN workflow_definitions w
  ON w.workflow_id = source_job.workflow_id
ORDER BY w.workflow_name, dependent_job;

-- Invocation outcomes by caller and shared workflow.
SELECT caller.repository_name AS caller_repository,
       reusable.workflow_name AS reusable_workflow,
       invocation.source_revision,
       invocation.state,
       invocation.invoked_at
FROM workflow_invocations invocation
JOIN workflow_definitions caller_workflow
  ON caller_workflow.workflow_id = invocation.caller_workflow_id
JOIN repositories caller
  ON caller.repository_id = caller_workflow.repository_id
JOIN workflow_definitions reusable
  ON reusable.workflow_id = invocation.callee_workflow_id
ORDER BY invocation.invoked_at DESC;

-- Aggregate reliability by shared workflow.
SELECT reusable.workflow_name,
       COUNT(*) AS total_invocations,
       COUNT(*) FILTER (WHERE invocation.state = 'succeeded') AS succeeded,
       COUNT(*) FILTER (WHERE invocation.state = 'failed') AS failed,
       ROUND(
           100.0 * COUNT(*) FILTER (
               WHERE invocation.state = 'succeeded'
           ) / NULLIF(COUNT(*), 0),
           2
       ) AS success_percentage
FROM workflow_invocations invocation
JOIN workflow_definitions reusable
  ON reusable.workflow_id = invocation.callee_workflow_id
GROUP BY reusable.workflow_name;

-- Input contracts can be audited without revealing secret values.
SELECT w.workflow_name,
       input.input_name,
       input.required,
       input.default_value,
       CASE
           WHEN input.required AND input.default_value IS NOT NULL
               THEN 'review required/default conflict'
           WHEN input.required
               THEN 'caller must supply value'
           ELSE 'optional input'
       END AS contract_status
FROM workflow_inputs input
JOIN workflow_definitions w USING (workflow_id)
ORDER BY w.workflow_name, input.input_name;

-- Demonstrate a database-enforced rejection. The exception is caught so the
-- complete sample script can finish successfully in psql.
DO $$
DECLARE
    existing_job BIGINT;
    unrelated_job BIGINT;
BEGIN
    SELECT j.job_id INTO existing_job
    FROM workflow_jobs j
    JOIN workflow_definitions w USING (workflow_id)
    JOIN repositories r USING (repository_id)
    WHERE r.repository_name = 'shared-automation'
      AND j.job_name = 'test'
    LIMIT 1;

    SELECT j.job_id INTO unrelated_job
    FROM workflow_jobs j
    JOIN workflow_definitions w USING (workflow_id)
    JOIN repositories r USING (repository_id)
    WHERE r.repository_name = 'inventory-service'
    LIMIT 1;

    IF existing_job IS NOT NULL AND unrelated_job IS NOT NULL THEN
        BEGIN
            INSERT INTO job_dependencies (job_id, dependency_job_id)
            VALUES (existing_job, unrelated_job);

            RAISE EXCEPTION
                'Expected cross-workflow dependency to be rejected';
        EXCEPTION
            WHEN check_violation OR raise_exception THEN
                RAISE NOTICE
                    'Invalid cross-workflow dependency was rejected.';
        END;
    END IF;
END;
$$;

COMMIT;

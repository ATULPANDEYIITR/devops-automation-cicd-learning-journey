-- ============================================================
-- JENKINSFILE PIPELINE MANAGEMENT DATABASE
-- PostgreSQL 14+
--
-- Models:
--   Jenkins projects
--   Pipeline definitions
--   Pipeline environment variables
--   Stages and steps
--   Build executions
--   Stage executions
--   Step executions
--   Post-build actions
--   Build artifacts
--   Execution events
--   Build eligibility and reporting
--
-- Sensitive environment values are represented by secret
-- references. Actual secret values belong in a secret manager.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS jenkins_lab;

SET search_path TO jenkins_lab, public;

-- ------------------------------------------------------------
-- Enumerated workflow states
-- ------------------------------------------------------------

CREATE TYPE build_status AS ENUM (
    'CREATED',
    'RUNNING',
    'SUCCESS',
    'FAILURE',
    'UNSTABLE',
    'ABORTED'
);

CREATE TYPE stage_status AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCESS',
    'FAILURE',
    'SKIPPED'
);

CREATE TYPE post_condition AS ENUM (
    'ALWAYS',
    'SUCCESS',
    'FAILURE',
    'UNSTABLE',
    'CLEANUP'
);

CREATE TYPE step_status AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCESS',
    'FAILURE',
    'SKIPPED'
);

-- ------------------------------------------------------------
-- Projects
-- ------------------------------------------------------------

CREATE TABLE projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_key VARCHAR(80) NOT NULL UNIQUE,
    project_name VARCHAR(200) NOT NULL,
    repository_url TEXT NOT NULL,
    default_branch VARCHAR(150) NOT NULL DEFAULT 'main',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT project_key_format
        CHECK (project_key ~ '^[A-Za-z0-9_-]+$'),

    CONSTRAINT project_name_nonempty
        CHECK (LENGTH(TRIM(project_name)) > 0),

    CONSTRAINT repository_url_valid
        CHECK (repository_url ~ '^https?://')
);

-- ------------------------------------------------------------
-- Pipeline definitions
-- ------------------------------------------------------------

CREATE TABLE pipelines (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL
        REFERENCES projects(project_id)
        ON DELETE CASCADE,

    pipeline_name VARCHAR(150) NOT NULL,
    definition_version INTEGER NOT NULL DEFAULT 1,
    definition_source VARCHAR(40) NOT NULL DEFAULT 'JENKINSFILE',
    jenkinsfile_path TEXT NOT NULL DEFAULT 'Jenkinsfile',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_pipeline_name
        UNIQUE (project_id, pipeline_name),

    CONSTRAINT valid_definition_version
        CHECK (definition_version > 0),

    CONSTRAINT valid_definition_source
        CHECK (definition_source IN (
            'JENKINSFILE',
            'SHARED_LIBRARY'
        ))
);

-- ------------------------------------------------------------
-- Environment configuration
-- ------------------------------------------------------------

CREATE TABLE pipeline_environment (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id)
        ON DELETE CASCADE,

    variable_name VARCHAR(150) NOT NULL,
    variable_value TEXT,
    secret_reference TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    scope VARCHAR(20) NOT NULL DEFAULT 'GLOBAL',

    CONSTRAINT unique_pipeline_variable
        UNIQUE (pipeline_id, variable_name, scope),

    CONSTRAINT valid_variable_name
        CHECK (
            variable_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'
        ),

    CONSTRAINT valid_environment_scope
        CHECK (scope IN ('GLOBAL', 'STAGE')),

    CONSTRAINT secret_storage_rule
        CHECK (
            (is_secret = TRUE AND secret_reference IS NOT NULL
                AND variable_value IS NULL)
            OR
            (is_secret = FALSE AND variable_value IS NOT NULL
                AND secret_reference IS NULL)
        )
);

-- ------------------------------------------------------------
-- Pipeline stages
-- ------------------------------------------------------------

CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id)
        ON DELETE CASCADE,

    stage_name VARCHAR(150) NOT NULL,
    stage_order INTEGER NOT NULL,
    condition_expression TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 600,
    retry_count INTEGER NOT NULL DEFAULT 0,
    continue_on_error BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_stage_name
        UNIQUE (pipeline_id, stage_name),

    CONSTRAINT unique_stage_order
        UNIQUE (pipeline_id, stage_order),

    CONSTRAINT valid_stage_order
        CHECK (stage_order > 0),

    CONSTRAINT valid_stage_timeout
        CHECK (timeout_seconds > 0),

    CONSTRAINT valid_retry_count
        CHECK (retry_count BETWEEN 0 AND 10)
);

-- Stage dependencies support explicit workflow ordering.
CREATE TABLE stage_dependencies (
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id)
        ON DELETE CASCADE,

    depends_on_stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id)
        ON DELETE CASCADE,

    PRIMARY KEY (stage_id, depends_on_stage_id),

    CONSTRAINT no_self_dependency
        CHECK (stage_id <> depends_on_stage_id)
);

-- ------------------------------------------------------------
-- Pipeline steps
-- ------------------------------------------------------------

CREATE TABLE pipeline_steps (
    step_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id)
        ON DELETE CASCADE,

    step_name VARCHAR(150) NOT NULL,
    step_order INTEGER NOT NULL,
    step_type VARCHAR(40) NOT NULL,
    command_reference TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 120,
    continue_on_error BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT unique_step_order
        UNIQUE (stage_id, step_order),

    CONSTRAINT valid_step_order
        CHECK (step_order > 0),

    CONSTRAINT valid_step_timeout
        CHECK (timeout_seconds > 0),

    CONSTRAINT valid_step_type
        CHECK (step_type IN (
            'SHELL',
            'BATCH',
            'POWERSHELL',
            'SCRIPT',
            'ARCHIVE',
            'TEST',
            'PUBLISH'
        ))
);

-- ------------------------------------------------------------
-- Post-build actions
-- ------------------------------------------------------------

CREATE TABLE post_actions (
    post_action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id)
        ON DELETE CASCADE,

    action_name VARCHAR(150) NOT NULL,
    condition post_condition NOT NULL,
    action_type VARCHAR(40) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    action_order INTEGER NOT NULL,

    CONSTRAINT unique_post_action_order
        UNIQUE (pipeline_id, action_order),

    CONSTRAINT valid_post_action_type
        CHECK (action_type IN (
            'NOTIFICATION',
            'ARCHIVE',
            'CLEANUP',
            'REPORT',
            'PUBLISH'
        ))
);

-- ------------------------------------------------------------
-- Build executions
-- ------------------------------------------------------------

CREATE TABLE builds (
    build_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),

    build_number BIGINT NOT NULL,
    triggered_by VARCHAR(150) NOT NULL,
    source_branch VARCHAR(200) NOT NULL,
    commit_sha VARCHAR(64) NOT NULL,
    status build_status NOT NULL DEFAULT 'CREATED',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_build_number
        UNIQUE (pipeline_id, build_number),

    CONSTRAINT valid_build_number
        CHECK (build_number > 0),

    CONSTRAINT valid_commit_sha
        CHECK (commit_sha ~ '^[a-fA-F0-9]{7,64}$'),

    CONSTRAINT valid_build_duration
        CHECK (duration_ms IS NULL OR duration_ms >= 0),

    CONSTRAINT valid_build_timestamps
        CHECK (
            completed_at IS NULL
            OR (
                started_at IS NOT NULL
                AND completed_at >= started_at
            )
        )
);

-- ------------------------------------------------------------
-- Stage execution history
-- ------------------------------------------------------------

CREATE TABLE stage_executions (
    stage_execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id BIGINT NOT NULL
        REFERENCES builds(build_id)
        ON DELETE CASCADE,

    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id),

    status stage_status NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    error_message TEXT,

    CONSTRAINT unique_build_stage
        UNIQUE (build_id, stage_id),

    CONSTRAINT valid_stage_duration
        CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

-- ------------------------------------------------------------
-- Step execution history
-- ------------------------------------------------------------

CREATE TABLE step_executions (
    step_execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_execution_id BIGINT NOT NULL
        REFERENCES stage_executions(stage_execution_id)
        ON DELETE CASCADE,

    step_id BIGINT NOT NULL
        REFERENCES pipeline_steps(step_id),

    status step_status NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    output_summary TEXT,
    error_message TEXT,

    CONSTRAINT unique_stage_step
        UNIQUE (stage_execution_id, step_id),

    CONSTRAINT valid_step_duration
        CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

-- ------------------------------------------------------------
-- Build artifacts
-- ------------------------------------------------------------

CREATE TABLE build_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id BIGINT NOT NULL
        REFERENCES builds(build_id)
        ON DELETE CASCADE,

    artifact_name VARCHAR(200) NOT NULL,
    storage_uri TEXT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_build_artifact
        UNIQUE (build_id, artifact_name),

    CONSTRAINT valid_artifact_size
        CHECK (size_bytes >= 0),

    CONSTRAINT valid_artifact_checksum
        CHECK (sha256 ~ '^[a-fA-F0-9]{64}$')
);

-- ------------------------------------------------------------
-- Execution events
-- ------------------------------------------------------------

CREATE TABLE execution_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id BIGINT NOT NULL
        REFERENCES builds(build_id)
        ON DELETE CASCADE,

    event_type VARCHAR(60) NOT NULL,
    stage_name VARCHAR(150),
    step_name VARCHAR(150),
    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------

CREATE INDEX idx_pipelines_project
    ON pipelines(project_id, enabled);

CREATE INDEX idx_stages_pipeline_order
    ON pipeline_stages(pipeline_id, stage_order);

CREATE INDEX idx_steps_stage_order
    ON pipeline_steps(stage_id, step_order);

CREATE INDEX idx_builds_pipeline_created
    ON builds(pipeline_id, created_at DESC);

CREATE INDEX idx_builds_status
    ON builds(status, created_at DESC);

CREATE INDEX idx_builds_branch
    ON builds(pipeline_id, source_branch, created_at DESC);

CREATE INDEX idx_stage_executions_status
    ON stage_executions(status, build_id);

CREATE INDEX idx_step_executions_status
    ON step_executions(status, stage_execution_id);

CREATE INDEX idx_events_build_time
    ON execution_events(build_id, occurred_at);

CREATE INDEX idx_events_details
    ON execution_events USING GIN(event_details);

-- ------------------------------------------------------------
-- Validate stage dependency graph
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_stage_dependencies()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_pipeline BIGINT;
    target_pipeline BIGINT;
    cycle_found BOOLEAN;
BEGIN
    SELECT pipeline_id
    INTO source_pipeline
    FROM pipeline_stages
    WHERE stage_id = NEW.stage_id;

    SELECT pipeline_id
    INTO target_pipeline
    FROM pipeline_stages
    WHERE stage_id = NEW.depends_on_stage_id;

    IF source_pipeline IS NULL OR target_pipeline IS NULL THEN
        RAISE EXCEPTION 'Referenced stage does not exist';
    END IF;

    IF source_pipeline <> target_pipeline THEN
        RAISE EXCEPTION
            'Stage dependencies must belong to the same pipeline';
    END IF;

    WITH RECURSIVE dependency_path(stage_id) AS (
        SELECT NEW.depends_on_stage_id

        UNION

        SELECT dependency.depends_on_stage_id
        FROM stage_dependencies dependency
        JOIN dependency_path path
          ON dependency.stage_id = path.stage_id
    )
    SELECT EXISTS (
        SELECT 1
        FROM dependency_path
        WHERE stage_id = NEW.stage_id
    )
    INTO cycle_found;

    IF cycle_found THEN
        RAISE EXCEPTION
            'Circular pipeline stage dependency detected';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_stage_dependencies
BEFORE INSERT OR UPDATE
ON stage_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_stage_dependencies();

-- ------------------------------------------------------------
-- Prevent invalid build state transitions
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_build_status_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN (
        'SUCCESS',
        'FAILURE',
        'UNSTABLE',
        'ABORTED'
    ) AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION
            'Terminal build status cannot be changed';
    END IF;

    IF OLD.status = 'CREATED'
       AND NEW.status NOT IN ('CREATED', 'RUNNING', 'ABORTED') THEN
        RAISE EXCEPTION
            'Invalid transition from CREATED';
    END IF;

    IF OLD.status = 'RUNNING'
       AND NEW.status NOT IN (
           'RUNNING',
           'SUCCESS',
           'FAILURE',
           'UNSTABLE',
           'ABORTED'
       ) THEN
        RAISE EXCEPTION
            'Invalid transition from RUNNING';
    END IF;

    IF NEW.status = 'RUNNING'
       AND NEW.started_at IS NULL THEN
        RAISE EXCEPTION
            'Running builds require started_at';
    END IF;

    IF NEW.status IN (
        'SUCCESS',
        'FAILURE',
        'UNSTABLE',
        'ABORTED'
    ) AND NEW.completed_at IS NULL THEN
        RAISE EXCEPTION
            'Terminal builds require completed_at';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_build_status_transition
BEFORE UPDATE OF status
ON builds
FOR EACH ROW
EXECUTE FUNCTION validate_build_status_transition();

-- ------------------------------------------------------------
-- Build completion reporting function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION complete_build(
    p_build_id BIGINT,
    p_final_status build_status,
    p_failure_reason TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    build_started TIMESTAMPTZ;
BEGIN
    IF p_final_status NOT IN (
        'SUCCESS',
        'FAILURE',
        'UNSTABLE',
        'ABORTED'
    ) THEN
        RAISE EXCEPTION
            'Invalid terminal build status: %',
            p_final_status;
    END IF;

    SELECT started_at
    INTO build_started
    FROM builds
    WHERE build_id = p_build_id
      AND status = 'RUNNING'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Build % is not running',
            p_build_id;
    END IF;

    UPDATE builds
    SET status = p_final_status,
        completed_at = NOW(),
        duration_ms = GREATEST(
            0,
            (EXTRACT(EPOCH FROM (NOW() - build_started))
                * 1000)::BIGINT
        ),
        failure_reason = p_failure_reason
    WHERE build_id = p_build_id;

    INSERT INTO execution_events (
        build_id,
        event_type,
        event_details
    )
    VALUES (
        p_build_id,
        'BUILD_COMPLETED',
        jsonb_build_object(
            'status', p_final_status,
            'failure_reason', p_failure_reason
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- Build eligibility evaluation
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_build_eligibility(
    p_build_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    failed_conditions TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_status build_status;
    pipeline_enabled BOOLEAN;
    pending_count BIGINT;
    failed_count BIGINT;
    skipped_count BIGINT;
    reasons TEXT[] := ARRAY[]::TEXT[];
BEGIN
    SELECT b.status, p.enabled
    INTO current_status, pipeline_enabled
    FROM builds b
    JOIN pipelines p
      ON p.pipeline_id = b.pipeline_id
    WHERE b.build_id = p_build_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Build % does not exist', p_build_id;
    END IF;

    IF NOT pipeline_enabled THEN
        reasons := array_append(
            reasons,
            'Pipeline is disabled'
        );
    END IF;

    IF current_status <> 'SUCCESS' THEN
        reasons := array_append(
            reasons,
            'Build did not complete successfully'
        );
    END IF;

    SELECT
        COUNT(*) FILTER (WHERE se.status = 'PENDING'),
        COUNT(*) FILTER (WHERE se.status = 'FAILURE'),
        COUNT(*) FILTER (WHERE se.status = 'SKIPPED')
    INTO pending_count, failed_count, skipped_count
    FROM stage_executions se
    WHERE se.build_id = p_build_id;

    IF pending_count > 0 THEN
        reasons := array_append(
            reasons,
            'Pending stages remain'
        );
    END IF;

    IF failed_count > 0 THEN
        reasons := array_append(
            reasons,
            'One or more stages failed'
        );
    END IF;

    RETURN QUERY
    SELECT
        cardinality(reasons) = 0,
        reasons;
END;
$$;

-- ------------------------------------------------------------
-- Views
-- ------------------------------------------------------------

CREATE VIEW v_pipeline_stage_configuration AS
SELECT
    p.pipeline_name,
    s.stage_id,
    s.stage_name,
    s.stage_order,
    s.timeout_seconds,
    s.retry_count,
    COUNT(ps.step_id) AS configured_steps
FROM pipelines p
JOIN pipeline_stages s
    ON s.pipeline_id = p.pipeline_id
LEFT JOIN pipeline_steps ps
    ON ps.stage_id = s.stage_id
GROUP BY
    p.pipeline_name,
    s.stage_id,
    s.stage_name,
    s.stage_order,
    s.timeout_seconds,
    s.retry_count;

CREATE VIEW v_build_execution_summary AS
SELECT
    p.pipeline_name,
    b.build_id,
    b.build_number,
    b.source_branch,
    b.status,
    b.triggered_by,
    b.started_at,
    b.completed_at,
    b.duration_ms,
    COUNT(DISTINCT se.stage_execution_id) AS executed_stages,
    COUNT(DISTINCT se.stage_execution_id)
        FILTER (WHERE se.status = 'SUCCESS') AS successful_stages,
    COUNT(DISTINCT se.stage_execution_id)
        FILTER (WHERE se.status = 'FAILURE') AS failed_stages
FROM builds b
JOIN pipelines p
    ON p.pipeline_id = b.pipeline_id
LEFT JOIN stage_executions se
    ON se.build_id = b.build_id
GROUP BY
    p.pipeline_name,
    b.build_id,
    b.build_number,
    b.source_branch,
    b.status,
    b.triggered_by,
    b.started_at,
    b.completed_at,
    b.duration_ms;

-- ------------------------------------------------------------
-- Sample project and pipeline
-- ------------------------------------------------------------

INSERT INTO projects (
    project_key,
    project_name,
    repository_url,
    default_branch
)
VALUES (
    'INVENTORY_API',
    'Inventory Management API',
    'https://github.com/example/inventory-api',
    'main'
);

INSERT INTO pipelines (
    project_id,
    pipeline_name,
    definition_version
)
SELECT
    project_id,
    'Inventory CI/CD',
    1
FROM projects
WHERE project_key = 'INVENTORY_API';

-- Global environment values and stage-level configuration.

INSERT INTO pipeline_environment (
    pipeline_id,
    variable_name,
    variable_value,
    is_secret,
    scope
)
SELECT
    pipeline_id,
    'APPLICATION_NAME',
    'inventory-api',
    FALSE,
    'GLOBAL'
FROM pipelines
WHERE pipeline_name = 'Inventory CI/CD';

INSERT INTO pipeline_environment (
    pipeline_id,
    variable_name,
    secret_reference,
    is_secret,
    scope
)
SELECT
    pipeline_id,
    'DEPLOYMENT_TOKEN',
    'vault://ci/inventory/deployment-token',
    TRUE,
    'GLOBAL'
FROM pipelines
WHERE pipeline_name = 'Inventory CI/CD';

INSERT INTO pipeline_stages (
    pipeline_id,
    stage_name,
    stage_order,
    timeout_seconds
)
SELECT
    pipeline_id,
    stage_name,
    stage_order,
    600
FROM pipelines
CROSS JOIN (
    VALUES
        ('Checkout', 1),
        ('Build', 2),
        ('Test', 3),
        ('Security Scan', 4),
        ('Deploy', 5)
) AS stages(stage_name, stage_order)
WHERE pipeline_name = 'Inventory CI/CD';

INSERT INTO pipeline_steps (
    stage_id,
    step_name,
    step_order,
    step_type,
    command_reference
)
SELECT
    s.stage_id,
    steps.step_name,
    steps.step_order,
    steps.step_type,
    steps.command_reference
FROM pipeline_stages s
JOIN pipelines p
    ON p.pipeline_id = s.pipeline_id
JOIN (
    VALUES
        ('Checkout', 'Clone repository', 1, 'SHELL', 'git clone'),
        ('Build', 'Compile application', 1, 'SHELL', 'mvn package'),
        ('Test', 'Run unit tests', 1, 'TEST', 'mvn test'),
        ('Security Scan', 'Scan dependencies', 1, 'SHELL', 'dependency-check'),
        ('Deploy', 'Deploy to staging', 1, 'PUBLISH', 'deploy-staging')
) AS steps(stage_name, step_name, step_order, step_type, command_reference)
    ON steps.stage_name = s.stage_name
WHERE p.pipeline_name = 'Inventory CI/CD';

-- Create sequential stage dependencies.

INSERT INTO stage_dependencies (
    stage_id,
    depends_on_stage_id
)
SELECT
    current_stage.stage_id,
    previous_stage.stage_id
FROM pipeline_stages current_stage
JOIN pipeline_stages previous_stage
    ON previous_stage.pipeline_id = current_stage.pipeline_id
   AND previous_stage.stage_order =
       current_stage.stage_order - 1
WHERE current_stage.stage_order > 1;

-- Post-build conditions.

INSERT INTO post_actions (
    pipeline_id,
    action_name,
    condition,
    action_type,
    action_order
)
SELECT
    pipeline_id,
    action_name,
    condition,
    action_type,
    action_order
FROM pipelines
CROSS JOIN (
    VALUES
        ('Notify build completion', 'ALWAYS'::post_condition, 'NOTIFICATION', 1),
        ('Archive successful artifacts', 'SUCCESS'::post_condition, 'ARCHIVE', 2),
        ('Send failure alert', 'FAILURE'::post_condition, 'NOTIFICATION', 3),
        ('Clean workspace', 'CLEANUP'::post_condition, 'CLEANUP', 4)
) AS actions(action_name, condition, action_type, action_order)
WHERE pipeline_name = 'Inventory CI/CD';

-- ------------------------------------------------------------
-- Sample build executions
-- ------------------------------------------------------------

INSERT INTO builds (
    pipeline_id,
    build_number,
    triggered_by,
    source_branch,
    commit_sha,
    status,
    started_at
)
SELECT
    pipeline_id,
    101,
    'developer@example.com',
    'main',
    repeat('a', 40),
    'RUNNING',
    NOW() - INTERVAL '30 seconds'
FROM pipelines
WHERE pipeline_name = 'Inventory CI/CD';

INSERT INTO builds (
    pipeline_id,
    build_number,
    triggered_by,
    source_branch,
    commit_sha,
    status,
    started_at,
    completed_at,
    duration_ms,
    failure_reason
)
SELECT
    pipeline_id,
    102,
    'ci-bot',
    'feature/payment',
    repeat('b', 40),
    'FAILURE',
    NOW() - INTERVAL '15 minutes',
    NOW() - INTERVAL '14 minutes',
    45000,
    'Unit tests failed'
FROM pipelines
WHERE pipeline_name = 'Inventory CI/CD';

-- Record stage executions for the failed build.

INSERT INTO stage_executions (
    build_id,
    stage_id,
    status,
    duration_ms,
    error_message
)
SELECT
    b.build_id,
    s.stage_id,
    CASE
        WHEN s.stage_name IN ('Checkout', 'Build') THEN 'SUCCESS'
        WHEN s.stage_name = 'Test' THEN 'FAILURE'
        ELSE 'SKIPPED'
    END::stage_status,
    CASE
        WHEN s.stage_name = 'Checkout' THEN 1200
        WHEN s.stage_name = 'Build' THEN 8000
        WHEN s.stage_name = 'Test' THEN 5000
        ELSE NULL
    END,
    CASE
        WHEN s.stage_name = 'Test' THEN 'Assertion failure'
        ELSE NULL
    END
FROM builds b
JOIN pipelines p
    ON p.pipeline_id = b.pipeline_id
JOIN pipeline_stages s
    ON s.pipeline_id = p.pipeline_id
WHERE b.build_number = 102
  AND p.pipeline_name = 'Inventory CI/CD';

-- Successful stages for the running build are initially pending.

INSERT INTO stage_executions (
    build_id,
    stage_id,
    status
)
SELECT
    b.build_id,
    s.stage_id,
    'PENDING'
FROM builds b
JOIN pipelines p
    ON p.pipeline_id = b.pipeline_id
JOIN pipeline_stages s
    ON s.pipeline_id = p.pipeline_id
WHERE b.build_number = 101
  AND p.pipeline_name = 'Inventory CI/CD';

-- Record execution events.

INSERT INTO execution_events (
    build_id,
    event_type,
    stage_name,
    event_details
)
SELECT
    build_id,
    'BUILD_TRIGGERED',
    NULL,
    jsonb_build_object(
        'trigger', triggered_by,
        'branch', source_branch
    )
FROM builds
WHERE build_number IN (101, 102);

INSERT INTO execution_events (
    build_id,
    event_type,
    stage_name,
    event_details
)
SELECT
    b.build_id,
    'STAGE_FAILED',
    'Test',
    jsonb_build_object(
        'reason',
        'Unit test assertion failure'
    )
FROM builds b
WHERE b.build_number = 102;

-- ------------------------------------------------------------
-- Retrieval queries
-- ------------------------------------------------------------

SELECT *
FROM v_pipeline_stage_configuration
ORDER BY stage_order;

SELECT *
FROM v_build_execution_summary
ORDER BY build_number DESC;

SELECT
    b.build_number,
    b.status,
    s.stage_name,
    se.status AS stage_status,
    se.duration_ms
FROM builds b
JOIN stage_executions se
    ON se.build_id = b.build_id
JOIN pipeline_stages s
    ON s.stage_id = se.stage_id
ORDER BY b.build_number, s.stage_order;

-- ------------------------------------------------------------
-- Validation queries
-- ------------------------------------------------------------

-- Identify steps without an executable command reference.
SELECT
    s.stage_name,
    ps.step_name
FROM pipeline_steps ps
JOIN pipeline_stages s
    ON s.stage_id = ps.stage_id
WHERE ps.step_type IN ('SHELL', 'BATCH', 'POWERSHELL')
  AND ps.command_reference IS NULL;

-- Identify disabled pipelines.
SELECT
    project_name,
    pipeline_name
FROM projects p
JOIN pipelines pl
    ON pl.project_id = p.project_id
WHERE pl.enabled = FALSE;

-- Detect stages without configured steps.
SELECT
    stage_name
FROM pipeline_stages s
LEFT JOIN pipeline_steps ps
    ON ps.stage_id = s.stage_id
GROUP BY s.stage_id, s.stage_name
HAVING COUNT(ps.step_id) = 0;

-- Verify secret references without exposing secret values.
SELECT
    p.pipeline_name,
    e.variable_name,
    e.secret_reference
FROM pipeline_environment e
JOIN pipelines p
    ON p.pipeline_id = e.pipeline_id
WHERE e.is_secret = TRUE;

-- ------------------------------------------------------------
-- Aggregation and reporting
-- ------------------------------------------------------------

SELECT
    pipeline_name,
    COUNT(*) AS total_builds,
    COUNT(*) FILTER (
        WHERE status = 'SUCCESS'
    ) AS successful_builds,
    COUNT(*) FILTER (
        WHERE status = 'FAILURE'
    ) AS failed_builds,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE status = 'SUCCESS'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_percentage,
    ROUND(AVG(duration_ms), 2) AS average_duration_ms
FROM v_build_execution_summary
GROUP BY pipeline_name;

SELECT
    s.stage_name,
    COUNT(*) AS execution_count,
    COUNT(*) FILTER (
        WHERE se.status = 'FAILURE'
    ) AS failures,
    ROUND(AVG(se.duration_ms), 2) AS average_duration_ms
FROM stage_executions se
JOIN pipeline_stages s
    ON s.stage_id = se.stage_id
GROUP BY s.stage_name
ORDER BY failures DESC, average_duration_ms DESC;

-- ------------------------------------------------------------
-- Eligibility evaluation
-- ------------------------------------------------------------

SELECT *
FROM evaluate_build_eligibility(
    (
        SELECT build_id
        FROM builds
        WHERE build_number = 102
    )
);

-- ------------------------------------------------------------
-- Transactional build completion
-- ------------------------------------------------------------

DO $$
DECLARE
    running_build_id BIGINT;
BEGIN
    SELECT build_id
    INTO running_build_id
    FROM builds
    WHERE build_number = 101
      AND status = 'RUNNING'
    FOR UPDATE;

    IF running_build_id IS NOT NULL THEN

        UPDATE stage_executions
        SET status = 'SUCCESS',
            started_at = NOW(),
            completed_at = NOW(),
            duration_ms = 1500
        WHERE build_id = running_build_id
          AND status = 'PENDING'
          AND stage_id = (
              SELECT stage_id
              FROM pipeline_stages
              WHERE stage_name = 'Checkout'
                AND pipeline_id = (
                    SELECT pipeline_id
                    FROM builds
                    WHERE build_id = running_build_id
                )
          );

        INSERT INTO build_artifacts (
            build_id,
            artifact_name,
            storage_uri,
            sha256,
            size_bytes
        )
        VALUES (
            running_build_id,
            'inventory-api.jar',
            's3://ci-artifacts/inventory-api/build-101.jar',
            repeat('c', 64),
            2048000
        );

        PERFORM complete_build(
            running_build_id,
            'SUCCESS',
            NULL
        );
    END IF;
END;
$$;

COMMIT;

-- ------------------------------------------------------------
-- Final reporting
-- ------------------------------------------------------------

SELECT
    build_number,
    pipeline_name,
    source_branch,
    status,
    duration_ms,
    successful_stages,
    failed_stages
FROM v_build_execution_summary
ORDER BY build_number DESC;

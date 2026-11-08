/*
 * Jenkins + Docker deployment pipeline database.
 *
 * PostgreSQL 14+
 *
 * Models:
 * - Jenkins jobs
 * - Source repositories and branches
 * - Pipeline executions
 * - Build stages
 * - Docker images
 * - Container tests
 * - Security scans
 * - Docker registries
 * - Deployment environments
 * - Deployment records
 * - Release eligibility
 * - Pipeline audit events
 *
 * The database stores pipeline metadata and audit results.
 * Actual Docker and Jenkins operations execute outside PostgreSQL.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS cicd;

SET search_path TO cicd, public;

-- -------------------------------------------------------
-- ENUM TYPES
-- -------------------------------------------------------

CREATE TYPE pipeline_status AS ENUM (
    'CREATED',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'ABORTED'
);

CREATE TYPE stage_status AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'SKIPPED'
);

CREATE TYPE stage_type AS ENUM (
    'CHECKOUT',
    'BUILD',
    'TEST',
    'SECURITY_SCAN',
    'PUSH',
    'DEPLOY'
);

CREATE TYPE environment_type AS ENUM (
    'DEVELOPMENT',
    'STAGING',
    'PRODUCTION'
);

CREATE TYPE deployment_status AS ENUM (
    'PENDING',
    'DEPLOYING',
    'DEPLOYED',
    'FAILED',
    'ROLLED_BACK'
);

-- -------------------------------------------------------
-- REPOSITORIES
-- -------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(150) NOT NULL UNIQUE,
    remote_url TEXT NOT NULL,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_repository_name
        CHECK (repository_name ~ '^[a-zA-Z0-9_.-]+$'),

    CONSTRAINT valid_remote_url
        CHECK (remote_url ~ '^https://')
);

CREATE TABLE repository_branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    branch_name VARCHAR(150) NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    latest_commit VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, branch_name)
);

-- -------------------------------------------------------
-- JENKINS JOBS
-- -------------------------------------------------------

CREATE TABLE jenkins_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    job_name VARCHAR(150) NOT NULL UNIQUE,
    jenkinsfile_path VARCHAR(250) NOT NULL DEFAULT 'Jenkinsfile',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    timeout_seconds INTEGER NOT NULL DEFAULT 1800,
    max_retries INTEGER NOT NULL DEFAULT 2,

    CONSTRAINT valid_timeout
        CHECK (timeout_seconds > 0),

    CONSTRAINT valid_retries
        CHECK (max_retries >= 0)
);

-- -------------------------------------------------------
-- DOCKER REGISTRIES
-- -------------------------------------------------------

CREATE TABLE docker_registries (
    registry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_name VARCHAR(150) NOT NULL UNIQUE,
    registry_url TEXT NOT NULL,
    credential_reference VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT valid_registry_url
        CHECK (registry_url ~ '^https://')
);

-- Credential references identify secrets in an external
-- secret manager. Actual passwords are never stored here.

-- -------------------------------------------------------
-- PIPELINE EXECUTIONS
-- -------------------------------------------------------

CREATE TABLE pipeline_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jenkins_jobs(job_id),
    branch_id BIGINT NOT NULL REFERENCES repository_branches(branch_id),
    build_number INTEGER NOT NULL,
    commit_hash VARCHAR(64) NOT NULL,
    triggered_by VARCHAR(150) NOT NULL,
    status pipeline_status NOT NULL DEFAULT 'CREATED',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (job_id, build_number),

    CONSTRAINT valid_build_number
        CHECK (build_number > 0),

    CONSTRAINT valid_commit_hash
        CHECK (commit_hash ~ '^[a-fA-F0-9]{7,64}$'),

    CONSTRAINT valid_run_times
        CHECK (
            finished_at IS NULL
            OR started_at IS NULL
            OR finished_at >= started_at
        )
);

-- -------------------------------------------------------
-- PIPELINE STAGES
-- -------------------------------------------------------

CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES pipeline_runs(run_id)
        ON DELETE CASCADE,
    stage stage_type NOT NULL,
    execution_order INTEGER NOT NULL,
    status stage_status NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    duration_ms BIGINT,

    UNIQUE (run_id, stage),
    UNIQUE (run_id, execution_order),

    CHECK (execution_order > 0),
    CHECK (attempts >= 0),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (
        finished_at IS NULL
        OR started_at IS NULL
        OR finished_at >= started_at
    )
);

CREATE INDEX idx_pipeline_stages_run_status
ON pipeline_stages(run_id, status);

-- -------------------------------------------------------
-- DOCKER IMAGES
-- -------------------------------------------------------

CREATE TABLE docker_images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL UNIQUE
        REFERENCES pipeline_runs(run_id),
    registry_id BIGINT
        REFERENCES docker_registries(registry_id),
    repository_name VARCHAR(200) NOT NULL,
    image_tag VARCHAR(128) NOT NULL,
    digest VARCHAR(100),
    image_size_bytes BIGINT,
    built_at TIMESTAMPTZ,
    pushed_at TIMESTAMPTZ,
    scan_passed BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (repository_name, image_tag),

    CHECK (image_tag ~ '^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$'),
    CHECK (image_size_bytes IS NULL OR image_size_bytes >= 0)
);

-- -------------------------------------------------------
-- CONTAINER TEST RESULTS
-- -------------------------------------------------------

CREATE TABLE container_tests (
    test_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id BIGINT NOT NULL REFERENCES docker_images(image_id)
        ON DELETE CASCADE,
    test_name VARCHAR(150) NOT NULL,
    passed BOOLEAN NOT NULL,
    exit_code INTEGER NOT NULL,
    duration_ms BIGINT NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    output_summary TEXT,

    UNIQUE (image_id, test_name),

    CHECK (duration_ms >= 0)
);

CREATE INDEX idx_container_tests_image
ON container_tests(image_id, passed);

-- -------------------------------------------------------
-- SECURITY SCAN RESULTS
-- -------------------------------------------------------

CREATE TABLE security_scans (
    scan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id BIGINT NOT NULL REFERENCES docker_images(image_id)
        ON DELETE CASCADE,
    scanner VARCHAR(100) NOT NULL,
    critical_count INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    medium_count INTEGER NOT NULL DEFAULT 0,
    low_count INTEGER NOT NULL DEFAULT 0,
    passed BOOLEAN NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (critical_count >= 0),
    CHECK (high_count >= 0),
    CHECK (medium_count >= 0),
    CHECK (low_count >= 0)
);

-- -------------------------------------------------------
-- DEPLOYMENT ENVIRONMENTS
-- -------------------------------------------------------

CREATE TABLE deployment_environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_name VARCHAR(100) NOT NULL UNIQUE,
    environment environment_type NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    requires_security_scan BOOLEAN NOT NULL DEFAULT TRUE,
    requires_tests BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- -------------------------------------------------------
-- DEPLOYMENTS
-- -------------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES pipeline_runs(run_id),
    image_id BIGINT NOT NULL REFERENCES docker_images(image_id),
    environment_id BIGINT NOT NULL
        REFERENCES deployment_environments(environment_id),
    status deployment_status NOT NULL DEFAULT 'PENDING',
    deployment_strategy VARCHAR(30) NOT NULL DEFAULT 'ROLLING',
    deployed_by VARCHAR(150),
    deployed_at TIMESTAMPTZ,
    previous_image_id BIGINT REFERENCES docker_images(image_id),
    error_message TEXT,

    UNIQUE (run_id, environment_id),

    CHECK (
        deployment_strategy IN ('ROLLING', 'RECREATE', 'BLUE_GREEN')
    )
);

CREATE INDEX idx_deployments_environment_status
ON deployments(environment_id, status);

-- -------------------------------------------------------
-- DEPLOYMENT APPROVALS
-- -------------------------------------------------------

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,
    approver VARCHAR(150) NOT NULL,
    approved BOOLEAN NOT NULL,
    decision_reason TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------
-- AUDIT EVENTS
-- -------------------------------------------------------

CREATE TABLE pipeline_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES pipeline_runs(run_id),
    event_type VARCHAR(100) NOT NULL,
    actor VARCHAR(150) NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pipeline_audit_run_date
ON pipeline_audit(run_id, created_at DESC);

-- -------------------------------------------------------
-- PIPELINE STATUS TRANSITION TRIGGER
-- -------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_pipeline_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('SUCCESS', 'FAILED', 'ABORTED')
       AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION
            'Terminal pipeline status cannot be changed.';
    END IF;

    IF NEW.status = 'RUNNING' AND NEW.started_at IS NULL THEN
        NEW.started_at := NOW();
    END IF;

    IF NEW.status IN ('SUCCESS', 'FAILED', 'ABORTED') THEN
        NEW.finished_at := COALESCE(NEW.finished_at, NOW());
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pipeline_transition
BEFORE UPDATE ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION validate_pipeline_transition();

-- -------------------------------------------------------
-- STAGE TRANSITION TRIGGER
-- -------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_stage_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('SUCCESS', 'FAILED', 'SKIPPED')
       AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION
            'Completed pipeline stages cannot be modified.';
    END IF;

    IF NEW.status = 'RUNNING' AND OLD.status = 'PENDING' THEN
        NEW.started_at := COALESCE(NEW.started_at, NOW());
        NEW.attempts := NEW.attempts + 1;
    END IF;

    IF NEW.status IN ('SUCCESS', 'FAILED', 'SKIPPED') THEN
        NEW.finished_at := COALESCE(NEW.finished_at, NOW());
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_stage_transition
BEFORE UPDATE ON pipeline_stages
FOR EACH ROW
EXECUTE FUNCTION validate_stage_transition();

-- -------------------------------------------------------
-- DEPLOYMENT ELIGIBILITY FUNCTION
-- -------------------------------------------------------

CREATE OR REPLACE FUNCTION can_deploy(
    p_image_id BIGINT,
    p_environment_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_tests_required BOOLEAN;
    v_scan_required BOOLEAN;
    v_tests_passed BOOLEAN;
    v_scan_passed BOOLEAN;
    v_published BOOLEAN;
    v_image_exists BOOLEAN;
BEGIN
    SELECT
        e.requires_tests,
        e.requires_security_scan
    INTO
        v_tests_required,
        v_scan_required
    FROM deployment_environments e
    WHERE e.environment_id = p_environment_id
      AND e.active = TRUE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    SELECT
        TRUE,
        d.pushed_at IS NOT NULL,
        d.scan_passed,
        COALESCE(
            (
                SELECT BOOL_AND(t.passed)
                FROM container_tests t
                WHERE t.image_id = d.image_id
            ),
            FALSE
        )
    INTO
        v_image_exists,
        v_published,
        v_scan_passed,
        v_tests_passed
    FROM docker_images d
    WHERE d.image_id = p_image_id;

    IF NOT FOUND OR NOT v_image_exists THEN
        RETURN FALSE;
    END IF;

    IF v_tests_required AND NOT v_tests_passed THEN
        RETURN FALSE;
    END IF;

    IF v_scan_required AND NOT v_scan_passed THEN
        RETURN FALSE;
    END IF;

    IF NOT v_published THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$;

-- -------------------------------------------------------
-- DEPLOYMENT PROCESSING PROCEDURE
-- -------------------------------------------------------

CREATE OR REPLACE PROCEDURE process_deployment(
    p_deployment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_image_id BIGINT;
    v_environment_id BIGINT;
    v_approval_required BOOLEAN;
    v_approved BOOLEAN;
BEGIN
    SELECT
        d.image_id,
        d.environment_id,
        e.requires_approval
    INTO
        v_image_id,
        v_environment_id,
        v_approval_required
    FROM deployments d
    JOIN deployment_environments e
      ON e.environment_id = d.environment_id
    WHERE d.deployment_id = p_deployment_id
    FOR UPDATE OF d;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment does not exist.';
    END IF;

    IF NOT can_deploy(v_image_id, v_environment_id) THEN
        UPDATE deployments
        SET status = 'FAILED',
            error_message = 'Deployment eligibility checks failed.'
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF v_approval_required THEN
        SELECT COALESCE(BOOL_OR(approved), FALSE)
        INTO v_approved
        FROM deployment_approvals
        WHERE deployment_id = p_deployment_id;

        IF NOT v_approved THEN
            UPDATE deployments
            SET status = 'FAILED',
                error_message = 'Required approval is missing.'
            WHERE deployment_id = p_deployment_id;

            RETURN;
        END IF;
    END IF;

    UPDATE deployments
    SET status = 'DEPLOYING'
    WHERE deployment_id = p_deployment_id;

    -- This procedure records deployment authorization.
    -- A Jenkins deployment agent performs the real deployment.

    UPDATE deployments
    SET status = 'DEPLOYED',
        deployed_at = NOW(),
        error_message = NULL
    WHERE deployment_id = p_deployment_id;

    INSERT INTO pipeline_audit (
        run_id,
        event_type,
        actor,
        event_details
    )
    SELECT
        run_id,
        'DEPLOYMENT_AUTHORIZED',
        COALESCE(deployed_by, 'jenkins-agent'),
        jsonb_build_object(
            'deployment_id', p_deployment_id,
            'image_id', image_id,
            'environment_id', environment_id
        )
    FROM deployments
    WHERE deployment_id = p_deployment_id;

END;
$$;

-- -------------------------------------------------------
-- REPORTING VIEW
-- -------------------------------------------------------

CREATE OR REPLACE VIEW pipeline_execution_report AS
SELECT
    r.run_id,
    j.job_name,
    repo.repository_name,
    b.branch_name,
    r.build_number,
    r.commit_hash,
    r.status,
    COUNT(s.stage_id) AS total_stages,
    COUNT(s.stage_id) FILTER (
        WHERE s.status = 'SUCCESS'
    ) AS successful_stages,
    COUNT(s.stage_id) FILTER (
        WHERE s.status = 'FAILED'
    ) AS failed_stages,
    MAX(r.finished_at) AS completed_at
FROM pipeline_runs r
JOIN jenkins_jobs j ON j.job_id = r.job_id
JOIN repositories repo ON repo.repository_id = j.repository_id
JOIN repository_branches b ON b.branch_id = r.branch_id
LEFT JOIN pipeline_stages s ON s.run_id = r.run_id
GROUP BY
    r.run_id,
    j.job_name,
    repo.repository_name,
    b.branch_name,
    r.build_number,
    r.commit_hash,
    r.status;

-- -------------------------------------------------------
-- SAMPLE DATA
-- -------------------------------------------------------

INSERT INTO repositories (
    repository_name,
    remote_url,
    default_branch
)
VALUES (
    'inventory-api',
    'https://github.com/example/inventory-api',
    'main'
);

INSERT INTO repository_branches (
    repository_id,
    branch_name,
    protected,
    latest_commit
)
SELECT
    repository_id,
    'main',
    TRUE,
    'a83f9c2'
FROM repositories
WHERE repository_name = 'inventory-api';

INSERT INTO jenkins_jobs (
    repository_id,
    job_name,
    jenkinsfile_path,
    max_retries
)
SELECT
    repository_id,
    'inventory-api-main',
    'Jenkinsfile',
    2
FROM repositories
WHERE repository_name = 'inventory-api';

INSERT INTO docker_registries (
    registry_name,
    registry_url,
    credential_reference
)
VALUES (
    'production-registry',
    'https://registry.example.com',
    'vault/jenkins/docker-production'
);

INSERT INTO deployment_environments (
    environment_name,
    environment,
    requires_approval,
    requires_security_scan,
    requires_tests
)
VALUES
    ('development', 'DEVELOPMENT', FALSE, FALSE, TRUE),
    ('staging', 'STAGING', FALSE, TRUE, TRUE),
    ('production', 'PRODUCTION', TRUE, TRUE, TRUE);

-- -------------------------------------------------------
-- CREATE PIPELINE EXECUTION
-- -------------------------------------------------------

INSERT INTO pipeline_runs (
    job_id,
    branch_id,
    build_number,
    commit_hash,
    triggered_by,
    status,
    started_at
)
SELECT
    j.job_id,
    b.branch_id,
    101,
    'a83f9c2',
    'jenkins-webhook',
    'RUNNING',
    NOW()
FROM jenkins_jobs j
JOIN repository_branches b
  ON b.repository_id = j.repository_id
WHERE j.job_name = 'inventory-api-main'
  AND b.branch_name = 'main';

-- -------------------------------------------------------
-- REGISTER STAGES
-- -------------------------------------------------------

INSERT INTO pipeline_stages (
    run_id,
    stage,
    execution_order,
    status
)
SELECT
    run_id,
    stage,
    execution_order,
    'PENDING'
FROM pipeline_runs
CROSS JOIN (
    VALUES
        ('CHECKOUT'::stage_type, 1),
        ('BUILD'::stage_type, 2),
        ('TEST'::stage_type, 3),
        ('SECURITY_SCAN'::stage_type, 4),
        ('PUSH'::stage_type, 5),
        ('DEPLOY'::stage_type, 6)
) AS stages(stage, execution_order)
WHERE build_number = 101;

-- -------------------------------------------------------
-- UPDATE STAGE EXECUTION RESULTS
-- -------------------------------------------------------

UPDATE pipeline_stages s
SET status = 'SUCCESS',
    started_at = NOW(),
    finished_at = NOW(),
    attempts = 1,
    duration_ms = 150
FROM pipeline_runs r
WHERE s.run_id = r.run_id
  AND r.build_number = 101
  AND s.stage IN ('CHECKOUT', 'BUILD', 'TEST', 'SECURITY_SCAN');

UPDATE pipeline_stages s
SET status = 'SUCCESS',
    started_at = NOW(),
    finished_at = NOW(),
    attempts = 1,
    duration_ms = 100
FROM pipeline_runs r
WHERE s.run_id = r.run_id
  AND r.build_number = 101
  AND s.stage = 'PUSH';

-- -------------------------------------------------------
-- REGISTER DOCKER IMAGE
-- -------------------------------------------------------

INSERT INTO docker_images (
    run_id,
    registry_id,
    repository_name,
    image_tag,
    digest,
    image_size_bytes,
    built_at,
    pushed_at,
    scan_passed
)
SELECT
    r.run_id,
    dr.registry_id,
    'inventory-api',
    '1.0.0',
    'sha256:0123456789abcdef',
    125000000,
    NOW(),
    NOW(),
    TRUE
FROM pipeline_runs r
CROSS JOIN docker_registries dr
WHERE r.build_number = 101
  AND dr.registry_name = 'production-registry';

-- -------------------------------------------------------
-- REGISTER TEST RESULTS
-- -------------------------------------------------------

INSERT INTO container_tests (
    image_id,
    test_name,
    passed,
    exit_code,
    duration_ms,
    output_summary
)
SELECT
    image_id,
    test_name,
    TRUE,
    0,
    duration_ms,
    'Container test passed.'
FROM docker_images
CROSS JOIN (
    VALUES
        ('container-startup', 120),
        ('health-endpoint', 90),
        ('configuration-validation', 65)
) AS tests(test_name, duration_ms)
WHERE image_tag = '1.0.0';

-- -------------------------------------------------------
-- REGISTER SECURITY SCAN
-- -------------------------------------------------------

INSERT INTO security_scans (
    image_id,
    scanner,
    critical_count,
    high_count,
    medium_count,
    low_count,
    passed
)
SELECT
    image_id,
    'container-security-scanner',
    0,
    0,
    2,
    4,
    TRUE
FROM docker_images
WHERE image_tag = '1.0.0';

-- -------------------------------------------------------
-- REGISTER DEPLOYMENT
-- -------------------------------------------------------

INSERT INTO deployments (
    run_id,
    image_id,
    environment_id,
    status,
    deployment_strategy,
    deployed_by
)
SELECT
    d.run_id,
    d.image_id,
    e.environment_id,
    'PENDING',
    'ROLLING',
    'jenkins-agent'
FROM docker_images d
JOIN pipeline_runs r ON r.run_id = d.run_id
JOIN deployment_environments e
  ON e.environment_name = 'production'
WHERE r.build_number = 101;

-- Required production approval.
INSERT INTO deployment_approvals (
    deployment_id,
    approver,
    approved,
    decision_reason
)
SELECT
    deployment_id,
    'release-manager',
    TRUE,
    'Production release authorized.'
FROM deployments;

-- -------------------------------------------------------
-- EXECUTE DEPLOYMENT TRANSACTION
-- -------------------------------------------------------

DO $$
DECLARE
    v_deployment_id BIGINT;
BEGIN
    SELECT deployment_id
    INTO v_deployment_id
    FROM deployments
    WHERE status = 'PENDING'
    ORDER BY deployment_id DESC
    LIMIT 1;

    IF v_deployment_id IS NOT NULL THEN
        CALL process_deployment(v_deployment_id);
    END IF;
END;
$$;

-- -------------------------------------------------------
-- COMPLETE PIPELINE
-- -------------------------------------------------------

UPDATE pipeline_stages
SET status = 'SUCCESS',
    started_at = NOW(),
    finished_at = NOW(),
    attempts = 1
WHERE stage = 'DEPLOY'
  AND run_id = (
      SELECT run_id
      FROM pipeline_runs
      WHERE build_number = 101
  )
  AND EXISTS (
      SELECT 1
      FROM deployments
      WHERE status = 'DEPLOYED'
  );

UPDATE pipeline_runs r
SET status = CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM pipeline_stages s
            WHERE s.run_id = r.run_id
              AND s.status IN ('FAILED', 'PENDING', 'RUNNING')
        )
        THEN 'SUCCESS'::pipeline_status
        ELSE 'FAILED'::pipeline_status
    END,
    finished_at = NOW()
WHERE build_number = 101;

-- -------------------------------------------------------
-- RETRIEVAL QUERIES
-- -------------------------------------------------------

SELECT *
FROM pipeline_execution_report
ORDER BY run_id DESC;

SELECT
    stage,
    status,
    attempts,
    duration_ms,
    error_message
FROM pipeline_stages
WHERE run_id = (
    SELECT run_id
    FROM pipeline_runs
    WHERE build_number = 101
)
ORDER BY execution_order;

-- -------------------------------------------------------
-- VALIDATION QUERY
-- -------------------------------------------------------

SELECT
    d.deployment_id,
    e.environment_name,
    can_deploy(d.image_id, d.environment_id) AS eligible,
    d.status
FROM deployments d
JOIN deployment_environments e
  ON e.environment_id = d.environment_id;

-- -------------------------------------------------------
-- AGGREGATION QUERY
-- -------------------------------------------------------

SELECT
    j.job_name,
    COUNT(r.run_id) AS total_builds,
    COUNT(*) FILTER (
        WHERE r.status = 'SUCCESS'
    ) AS successful_builds,
    COUNT(*) FILTER (
        WHERE r.status = 'FAILED'
    ) AS failed_builds,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE r.status = 'SUCCESS'
        ) / NULLIF(COUNT(r.run_id), 0),
        2
    ) AS success_percentage
FROM jenkins_jobs j
LEFT JOIN pipeline_runs r ON r.job_id = j.job_id
GROUP BY j.job_id, j.job_name;

-- -------------------------------------------------------
-- DOCKER IMAGE REPORT
-- -------------------------------------------------------

SELECT
    repository_name,
    image_tag,
    digest,
    image_size_bytes,
    scan_passed,
    pushed_at
FROM docker_images
ORDER BY built_at DESC;

-- -------------------------------------------------------
-- SECURITY SCAN REPORT
-- -------------------------------------------------------

SELECT
    scanner,
    SUM(critical_count) AS critical_findings,
    SUM(high_count) AS high_findings,
    SUM(medium_count) AS medium_findings,
    SUM(low_count) AS low_findings
FROM security_scans
GROUP BY scanner;

-- -------------------------------------------------------
-- COMMON TABLE EXPRESSION: RELEASE READINESS
-- -------------------------------------------------------

WITH release_checks AS (
    SELECT
        r.run_id,
        r.build_number,
        r.status AS pipeline_status,
        COUNT(s.stage_id) FILTER (
            WHERE s.status = 'SUCCESS'
        ) AS successful_stages,
        COUNT(s.stage_id) AS total_stages,
        BOOL_AND(
            s.status IN ('SUCCESS', 'SKIPPED')
        ) AS all_stages_complete
    FROM pipeline_runs r
    JOIN pipeline_stages s ON s.run_id = r.run_id
    GROUP BY r.run_id
)
SELECT
    run_id,
    build_number,
    pipeline_status,
    successful_stages,
    total_stages,
    all_stages_complete,
    CASE
        WHEN pipeline_status = 'SUCCESS'
             AND all_stages_complete
        THEN 'RELEASE_READY'
        ELSE 'NOT_READY'
    END AS release_decision
FROM release_checks;

-- -------------------------------------------------------
-- FAILURE ANALYSIS
-- -------------------------------------------------------

SELECT
    r.run_id,
    j.job_name,
    s.stage,
    s.error_message,
    s.attempts
FROM pipeline_stages s
JOIN pipeline_runs r ON r.run_id = s.run_id
JOIN jenkins_jobs j ON j.job_id = r.job_id
WHERE s.status = 'FAILED'
ORDER BY r.created_at DESC;

-- -------------------------------------------------------
-- AUDIT EVENT
-- -------------------------------------------------------

INSERT INTO pipeline_audit (
    run_id,
    event_type,
    actor,
    event_details
)
SELECT
    run_id,
    'PIPELINE_COMPLETED',
    'jenkins-agent',
    jsonb_build_object(
        'build_number', build_number,
        'status', status
    )
FROM pipeline_runs
WHERE build_number = 101;

COMMIT;

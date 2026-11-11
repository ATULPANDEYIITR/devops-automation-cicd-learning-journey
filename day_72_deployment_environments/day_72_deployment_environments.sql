-- ============================================================
-- DEPLOYMENT ENVIRONMENT GOVERNANCE DATABASE
-- PostgreSQL 15+
--
-- Environments:
-- DEVELOPMENT -> QA -> STAGING -> PRODUCTION
--
-- Features:
-- Immutable artifact identity
-- Environment-specific policies
-- Deployment approvals
-- Automated validation checks
-- Deployment history
-- Health verification
-- Rollback tracking
-- Audit logging
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS deployment;

SET search_path TO deployment, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE environment_type AS ENUM (
    'development',
    'qa',
    'staging',
    'production'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'succeeded',
    'failed',
    'rolled_back'
);

CREATE TYPE deployment_strategy AS ENUM (
    'rolling',
    'blue_green',
    'canary'
);

CREATE TYPE approval_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'revoked'
);

CREATE TYPE check_status AS ENUM (
    'pending',
    'passed',
    'failed',
    'skipped'
);

-- ------------------------------------------------------------
-- REPOSITORIES
-- ------------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(120) NOT NULL UNIQUE,
    owner_name VARCHAR(120) NOT NULL,
    default_branch VARCHAR(120) NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT repository_name_valid
        CHECK (repository_name ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$')
);

-- ------------------------------------------------------------
-- USERS AND ROLES
-- ------------------------------------------------------------

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    role_name VARCHAR(60) NOT NULL,

    PRIMARY KEY (user_id, role_name)
);

-- ------------------------------------------------------------
-- ENVIRONMENTS
-- ------------------------------------------------------------

CREATE TABLE environments (
    environment_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_name environment_type NOT NULL UNIQUE,
    sequence_number SMALLINT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    replica_count INTEGER NOT NULL DEFAULT 1,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    deployment_strategy deployment_strategy NOT NULL DEFAULT 'rolling',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT environment_sequence_valid
        CHECK (sequence_number BETWEEN 1 AND 4),

    CONSTRAINT environment_replica_valid
        CHECK (replica_count BETWEEN 1 AND 100),

    CONSTRAINT environment_endpoint_https
        CHECK (endpoint ~ '^https://')
);

-- ------------------------------------------------------------
-- IMMUTABLE RELEASE ARTIFACTS
-- ------------------------------------------------------------

CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    artifact_name VARCHAR(120) NOT NULL,
    version VARCHAR(60) NOT NULL,
    commit_sha VARCHAR(40) NOT NULL,
    sha256_checksum CHAR(64) NOT NULL,
    build_number BIGINT NOT NULL,
    build_status VARCHAR(20) NOT NULL DEFAULT 'succeeded',
    built_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT artifact_version_valid
        CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.-]+)?$'),

    CONSTRAINT artifact_commit_valid
        CHECK (commit_sha ~ '^[a-fA-F0-9]{7,40}$'),

    CONSTRAINT artifact_checksum_valid
        CHECK (sha256_checksum ~ '^[a-f0-9]{64}$'),

    CONSTRAINT artifact_build_status_valid
        CHECK (build_status IN ('succeeded', 'failed')),

    UNIQUE (repository_id, artifact_name, version),
    UNIQUE (repository_id, commit_sha, artifact_name)
);

CREATE INDEX idx_artifacts_repository
    ON artifacts(repository_id, built_at DESC);

-- ------------------------------------------------------------
-- ENVIRONMENT-SPECIFIC CONFIGURATION
-- ------------------------------------------------------------

CREATE TABLE environment_variables (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id SMALLINT NOT NULL
        REFERENCES environments(environment_id),
    variable_name VARCHAR(120) NOT NULL,
    variable_value TEXT,
    secret_reference TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT environment_variable_storage
        CHECK (
            (is_secret AND secret_reference IS NOT NULL
                AND variable_value IS NULL)
            OR
            (NOT is_secret AND variable_value IS NOT NULL
                AND secret_reference IS NULL)
        ),

    UNIQUE (environment_id, variable_name)
);

-- Secret values are never stored in this table.
-- secret_reference identifies an external secret-manager entry.

-- ------------------------------------------------------------
-- ENVIRONMENT DEPLOYMENT POLICIES
-- ------------------------------------------------------------

CREATE TABLE deployment_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id SMALLINT NOT NULL
        REFERENCES environments(environment_id),
    minimum_approval_count INTEGER NOT NULL DEFAULT 0,
    required_successful_checks INTEGER NOT NULL DEFAULT 1,
    require_health_check BOOLEAN NOT NULL DEFAULT TRUE,
    allow_rollback BOOLEAN NOT NULL DEFAULT TRUE,
    maximum_error_rate NUMERIC(5,2) NOT NULL DEFAULT 5.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT approval_count_valid
        CHECK (minimum_approval_count BETWEEN 0 AND 20),

    CONSTRAINT check_count_valid
        CHECK (required_successful_checks >= 0),

    CONSTRAINT error_rate_valid
        CHECK (maximum_error_rate BETWEEN 0 AND 100),

    UNIQUE (environment_id)
);

CREATE TABLE required_checks (
    required_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id SMALLINT NOT NULL
        REFERENCES environments(environment_id),
    check_name VARCHAR(100) NOT NULL,
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (environment_id, check_name)
);

-- ------------------------------------------------------------
-- DEPLOYMENT APPROVALS
-- ------------------------------------------------------------

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id BIGINT NOT NULL REFERENCES artifacts(artifact_id),
    environment_id SMALLINT NOT NULL
        REFERENCES environments(environment_id),
    approver_id BIGINT NOT NULL REFERENCES users(user_id),
    approval_state approval_status NOT NULL DEFAULT 'pending',
    change_reference VARCHAR(100) NOT NULL,
    comments TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT approval_timestamp_valid
        CHECK (
            (approval_state = 'approved' AND approved_at IS NOT NULL)
            OR
            (approval_state <> 'approved')
        ),

    UNIQUE (artifact_id, environment_id, approver_id)
);

CREATE INDEX idx_approvals_eligibility
    ON deployment_approvals(
        artifact_id,
        environment_id,
        approval_state
    );

-- ------------------------------------------------------------
-- DEPLOYMENTS
-- ------------------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id BIGINT NOT NULL REFERENCES artifacts(artifact_id),
    environment_id SMALLINT NOT NULL
        REFERENCES environments(environment_id),
    deployment_number BIGINT NOT NULL,
    deployment_status deployment_status NOT NULL DEFAULT 'pending',
    deployed_by BIGINT NOT NULL REFERENCES users(user_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    previous_deployment_id BIGINT REFERENCES deployments(deployment_id),
    rollback_of_deployment_id BIGINT REFERENCES deployments(deployment_id),
    failure_reason TEXT,
    release_notes TEXT,

    CONSTRAINT deployment_number_valid
        CHECK (deployment_number > 0),

    CONSTRAINT deployment_completion_valid
        CHECK (
            (deployment_status = 'pending' AND completed_at IS NULL)
            OR
            (deployment_status <> 'pending' AND completed_at IS NOT NULL)
        ),

    CONSTRAINT deployment_failure_valid
        CHECK (
            deployment_status <> 'failed'
            OR failure_reason IS NOT NULL
        ),

    CONSTRAINT deployment_time_valid
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        ),

    UNIQUE (environment_id, deployment_number)
);

CREATE INDEX idx_deployments_environment_history
    ON deployments(environment_id, started_at DESC);

CREATE INDEX idx_deployments_artifact
    ON deployments(artifact_id, environment_id);

CREATE INDEX idx_deployments_status
    ON deployments(deployment_status, started_at DESC);

-- ------------------------------------------------------------
-- AUTOMATED CHECK RESULTS
-- ------------------------------------------------------------

CREATE TABLE deployment_checks (
    deployment_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    check_name VARCHAR(100) NOT NULL,
    status check_status NOT NULL DEFAULT 'pending',
    execution_duration_ms BIGINT,
    details TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT check_duration_valid
        CHECK (
            execution_duration_ms IS NULL
            OR execution_duration_ms >= 0
        ),

    UNIQUE (deployment_id, check_name)
);

CREATE INDEX idx_deployment_checks_status
    ON deployment_checks(deployment_id, status);

-- ------------------------------------------------------------
-- DEPLOYMENT HEALTH OBSERVATIONS
-- ------------------------------------------------------------

CREATE TABLE deployment_health (
    health_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),
    healthy BOOLEAN NOT NULL,
    error_rate NUMERIC(5,2) NOT NULL,
    response_time_ms NUMERIC(12,2) NOT NULL,
    availability_percent NUMERIC(5,2) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT health_error_rate_valid
        CHECK (error_rate BETWEEN 0 AND 100),

    CONSTRAINT response_time_valid
        CHECK (response_time_ms >= 0),

    CONSTRAINT availability_valid
        CHECK (availability_percent BETWEEN 0 AND 100)
);

CREATE INDEX idx_deployment_health_recent
    ON deployment_health(deployment_id, observed_at DESC);

-- ------------------------------------------------------------
-- AUDIT LOG
-- ------------------------------------------------------------

CREATE TABLE deployment_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT REFERENCES deployments(deployment_id),
    actor_id BIGINT REFERENCES users(user_id),
    event_type VARCHAR(100) NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployment_audit_timeline
    ON deployment_audit(created_at DESC);

-- ------------------------------------------------------------
-- TRIGGER: RECORD DEPLOYMENT STATUS CHANGES
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION audit_deployment_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.deployment_status IS DISTINCT FROM NEW.deployment_status THEN
        INSERT INTO deployment_audit (
            deployment_id,
            actor_id,
            event_type,
            event_details
        )
        VALUES (
            NEW.deployment_id,
            NEW.deployed_by,
            'deployment_status_changed',
            jsonb_build_object(
                'previous_status', OLD.deployment_status,
                'new_status', NEW.deployment_status,
                'environment_id', NEW.environment_id
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_status_audit
AFTER UPDATE OF deployment_status ON deployments
FOR EACH ROW
EXECUTE FUNCTION audit_deployment_changes();

-- ------------------------------------------------------------
-- TRIGGER: PREVENT ARTIFACT MODIFICATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Release artifacts are immutable. Register a new artifact version.';
END;
$$;

CREATE TRIGGER trg_artifact_immutable
BEFORE UPDATE OR DELETE ON artifacts
FOR EACH ROW
EXECUTE FUNCTION prevent_artifact_mutation();

-- ------------------------------------------------------------
-- FUNCTION: CHECK DEPLOYMENT ELIGIBILITY
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION check_deployment_eligibility(
    p_artifact_id BIGINT,
    p_environment_id SMALLINT,
    p_deployer_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_environment environment_type;
    v_sequence SMALLINT;
    v_previous_artifact BIGINT;
    v_approval_required BOOLEAN;
    v_min_approvals INTEGER;
    v_required_count INTEGER;
    v_passed_count INTEGER;
    v_failed_count INTEGER;
    v_approval_count INTEGER;
    v_build_status VARCHAR(20);
BEGIN
    SELECT
        e.environment_name,
        e.sequence_number,
        e.approval_required,
        p.minimum_approval_count,
        p.required_successful_checks
    INTO
        v_environment,
        v_sequence,
        v_approval_required,
        v_min_approvals,
        v_required_count
    FROM environments e
    JOIN deployment_policies p
        ON p.environment_id = e.environment_id
    WHERE e.environment_id = p_environment_id
      AND e.is_active = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Environment or policy unavailable';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM users
        WHERE user_id = p_deployer_id
          AND is_active = TRUE
    ) THEN
        RETURN QUERY SELECT FALSE, 'Inactive or unknown deployer';
        RETURN;
    END IF;

    SELECT build_status
    INTO v_build_status
    FROM artifacts
    WHERE artifact_id = p_artifact_id;

    IF NOT FOUND OR v_build_status <> 'succeeded' THEN
        RETURN QUERY SELECT FALSE, 'Artifact build unsuccessful or missing';
        RETURN;
    END IF;

    -- A later environment must receive the same artifact that was
    -- successfully deployed to the immediately preceding environment.
    IF v_sequence > 1 THEN
        SELECT d.artifact_id
        INTO v_previous_artifact
        FROM environments previous_environment
        JOIN deployments d
            ON d.environment_id = previous_environment.environment_id
        WHERE previous_environment.sequence_number = v_sequence - 1
          AND d.deployment_status = 'succeeded'
        ORDER BY d.completed_at DESC
        LIMIT 1;

        IF v_previous_artifact IS NULL
           OR v_previous_artifact <> p_artifact_id THEN
            RETURN QUERY SELECT FALSE, 'Previous environment artifact mismatch';
            RETURN;
        END IF;
    END IF;

    SELECT COUNT(*)
    INTO v_passed_count
    FROM required_checks rc
    WHERE rc.environment_id = p_environment_id
      AND rc.is_mandatory = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM deployment_checks dc
          JOIN deployments d
            ON d.deployment_id = dc.deployment_id
          WHERE d.artifact_id = p_artifact_id
            AND d.environment_id = p_environment_id
            AND dc.check_name = rc.check_name
            AND dc.status = 'passed'
      );

    IF v_passed_count > 0 THEN
        RETURN QUERY SELECT FALSE, 'One or more mandatory checks are missing';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_failed_count
    FROM deployment_checks dc
    JOIN deployments d
        ON d.deployment_id = dc.deployment_id
    WHERE d.artifact_id = p_artifact_id
      AND d.environment_id = p_environment_id
      AND dc.status = 'failed';

    IF v_failed_count > 0 THEN
        RETURN QUERY SELECT FALSE, 'A deployment check has failed';
        RETURN;
    END IF;

    SELECT COUNT(DISTINCT approver_id)
    INTO v_approval_count
    FROM deployment_approvals
    WHERE artifact_id = p_artifact_id
      AND environment_id = p_environment_id
      AND approval_state = 'approved'
      AND approver_id <> p_deployer_id;

    IF v_approval_required
       AND v_approval_count < GREATEST(v_min_approvals, 1) THEN
        RETURN QUERY SELECT FALSE, 'Insufficient independent approvals';
        RETURN;
    END IF;

    RETURN QUERY SELECT TRUE, 'All deployment policies satisfied';
END;
$$;

-- ------------------------------------------------------------
-- PROCEDURE: CREATE DEPLOYMENT ATTEMPT
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE create_deployment(
    p_artifact_id BIGINT,
    p_environment_id SMALLINT,
    p_deployer_id BIGINT,
    p_deployment_number BIGINT,
    OUT p_deployment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_eligible BOOLEAN;
    v_reason TEXT;
BEGIN
    SELECT eligible, reason
    INTO v_eligible, v_reason
    FROM check_deployment_eligibility(
        p_artifact_id,
        p_environment_id,
        p_deployer_id
    );

    IF NOT v_eligible THEN
        RAISE EXCEPTION 'Deployment rejected: %', v_reason;
    END IF;

    INSERT INTO deployments (
        artifact_id,
        environment_id,
        deployment_number,
        deployment_status,
        deployed_by
    )
    VALUES (
        p_artifact_id,
        p_environment_id,
        p_deployment_number,
        'pending',
        p_deployer_id
    )
    RETURNING deployment_id INTO p_deployment_id;

    INSERT INTO deployment_audit (
        deployment_id,
        actor_id,
        event_type,
        event_details
    )
    VALUES (
        p_deployment_id,
        p_deployer_id,
        'deployment_created',
        jsonb_build_object(
            'artifact_id', p_artifact_id,
            'environment_id', p_environment_id
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- VIEW: ACTIVE DEPLOYMENT STATE
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW active_environment_deployments AS
SELECT DISTINCT ON (d.environment_id)
    e.environment_name,
    a.artifact_name,
    a.version,
    a.commit_sha,
    a.sha256_checksum,
    d.deployment_id,
    d.deployment_status,
    d.deployed_by,
    d.completed_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN artifacts a
    ON a.artifact_id = d.artifact_id
WHERE d.deployment_status = 'succeeded'
ORDER BY d.environment_id, d.completed_at DESC NULLS LAST;

-- ------------------------------------------------------------
-- VIEW: DEPLOYMENT HEALTH REPORT
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW deployment_health_report AS
SELECT
    e.environment_name,
    a.artifact_name,
    a.version,
    d.deployment_id,
    d.deployment_status,
    h.healthy,
    h.error_rate,
    h.response_time_ms,
    h.availability_percent,
    h.observed_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN artifacts a
    ON a.artifact_id = d.artifact_id
LEFT JOIN LATERAL (
    SELECT *
    FROM deployment_health health
    WHERE health.deployment_id = d.deployment_id
    ORDER BY observed_at DESC
    LIMIT 1
) h ON TRUE;

-- ------------------------------------------------------------
-- SAMPLE DATA
-- ------------------------------------------------------------

INSERT INTO repositories (
    repository_name,
    owner_name
)
VALUES (
    'enterprise-payment-platform',
    'platform-engineering'
);

INSERT INTO users (
    username,
    email
)
VALUES
    ('developer', 'developer@example.com'),
    ('qa-engineer', 'qa@example.com'),
    ('release-bot', 'release-bot@example.com'),
    ('release-manager', 'manager@example.com'),
    ('production-operator', 'operator@example.com');

INSERT INTO user_roles (user_id, role_name)
SELECT user_id,
       CASE username
           WHEN 'developer' THEN 'developer'
           WHEN 'qa-engineer' THEN 'qa_engineer'
           WHEN 'release-bot' THEN 'deployment_service'
           WHEN 'release-manager' THEN 'release_approver'
           ELSE 'production_operator'
       END
FROM users;

INSERT INTO environments (
    environment_name,
    sequence_number,
    endpoint,
    replica_count,
    approval_required,
    deployment_strategy
)
VALUES
    ('development', 1, 'https://dev.example.internal', 1, FALSE, 'rolling'),
    ('qa', 2, 'https://qa.example.internal', 2, FALSE, 'rolling'),
    ('staging', 3, 'https://staging.example.internal', 3, TRUE, 'blue_green'),
    ('production', 4, 'https://production.example.com', 5, TRUE, 'canary');

INSERT INTO deployment_policies (
    environment_id,
    minimum_approval_count,
    required_successful_checks,
    require_health_check,
    maximum_error_rate
)
SELECT
    environment_id,
    CASE environment_name
        WHEN 'staging' THEN 1
        WHEN 'production' THEN 2
        ELSE 0
    END,
    1,
    TRUE,
    CASE environment_name
        WHEN 'production' THEN 1.00
        ELSE 5.00
    END
FROM environments;

INSERT INTO required_checks (
    environment_id,
    check_name
)
SELECT e.environment_id, checks.check_name
FROM environments e
CROSS JOIN LATERAL (
    SELECT unnest(
        CASE e.environment_name
            WHEN 'development'::environment_type
                THEN ARRAY['build', 'unit_tests']
            WHEN 'qa'::environment_type
                THEN ARRAY[
                    'build',
                    'unit_tests',
                    'integration_tests',
                    'security_scan'
                ]
            WHEN 'staging'::environment_type
                THEN ARRAY[
                    'build',
                    'unit_tests',
                    'integration_tests',
                    'security_scan',
                    'load_tests'
                ]
            ELSE ARRAY[
                'build',
                'unit_tests',
                'integration_tests',
                'security_scan',
                'load_tests',
                'acceptance_tests'
            ]
        END
    ) AS check_name
) checks;

INSERT INTO environment_variables (
    environment_id,
    variable_name,
    variable_value,
    is_secret
)
SELECT environment_id, 'LOG_LEVEL',
       CASE environment_name
           WHEN 'development' THEN 'DEBUG'
           ELSE 'INFO'
       END,
       FALSE
FROM environments;

INSERT INTO environment_variables (
    environment_id,
    variable_name,
    secret_reference,
    is_secret
)
SELECT environment_id,
       'DATABASE_PASSWORD',
       'vault://payment-platform/' || environment_name || '/database-password',
       TRUE
FROM environments;

INSERT INTO artifacts (
    repository_id,
    artifact_name,
    version,
    commit_sha,
    sha256_checksum,
    build_number
)
SELECT
    repository_id,
    'payment-api',
    '1.0.0',
    repeat('a', 40),
    repeat('b', 64),
    1001
FROM repositories;

INSERT INTO artifacts (
    repository_id,
    artifact_name,
    version,
    commit_sha,
    sha256_checksum,
    build_number
)
SELECT
    repository_id,
    'payment-api',
    '1.1.0',
    repeat('c', 40),
    repeat('d', 64),
    1002
FROM repositories;

-- ------------------------------------------------------------
-- APPROVAL RECORDS
-- ------------------------------------------------------------

INSERT INTO deployment_approvals (
    artifact_id,
    environment_id,
    approver_id,
    approval_state,
    change_reference,
    approved_at
)
SELECT
    a.artifact_id,
    e.environment_id,
    u.user_id,
    'approved',
    'CHG-2026-1001',
    NOW()
FROM artifacts a
JOIN environments e
    ON e.environment_name IN ('staging', 'production')
JOIN users u
    ON u.username = 'release-manager'
WHERE a.version = '1.0.0';

INSERT INTO deployment_approvals (
    artifact_id,
    environment_id,
    approver_id,
    approval_state,
    change_reference,
    approved_at
)
SELECT
    a.artifact_id,
    e.environment_id,
    u.user_id,
    'approved',
    'CHG-2026-1001',
    NOW()
FROM artifacts a
JOIN environments e
    ON e.environment_name = 'production'
JOIN users u
    ON u.username = 'production-operator'
WHERE a.version = '1.0.0';

-- ------------------------------------------------------------
-- DEPLOYMENT TRANSACTION
-- ------------------------------------------------------------

DO $$
DECLARE
    v_artifact BIGINT;
    v_environment BIGINT;
    v_deployer BIGINT;
    v_deployment BIGINT;
    v_check TEXT;
BEGIN
    SELECT artifact_id
    INTO v_artifact
    FROM artifacts
    WHERE version = '1.0.0';

    SELECT user_id
    INTO v_deployer
    FROM users
    WHERE username = 'release-bot';

    -- Promotion uses one immutable artifact across environments.
    FOR v_environment IN
        SELECT environment_id
        FROM environments
        ORDER BY sequence_number
    LOOP
        -- Validate eligibility and create the deployment.
        SELECT check_name
        INTO v_check
        FROM required_checks
        WHERE environment_id = v_environment
        ORDER BY required_check_id
        LIMIT 1;

        -- Insert a successful preceding deployment check record.
        -- The deployment itself remains pending until verified.
        CALL create_deployment(
            v_artifact,
            v_environment,
            v_deployer,
            (
                SELECT COALESCE(MAX(deployment_number), 0) + 1
                FROM deployments
                WHERE environment_id = v_environment
            ),
            v_deployment
        );

        INSERT INTO deployment_checks (
            deployment_id,
            check_name,
            status,
            execution_duration_ms,
            details
        )
        SELECT
            v_deployment,
            check_name,
            'passed',
            1200,
            'Automated pipeline verification passed'
        FROM required_checks
        WHERE environment_id = v_environment;

        INSERT INTO deployment_health (
            deployment_id,
            healthy,
            error_rate,
            response_time_ms,
            availability_percent
        )
        VALUES (
            v_deployment,
            TRUE,
            0.20,
            120.00,
            99.99
        );

        UPDATE deployments
        SET deployment_status = 'succeeded',
            completed_at = NOW()
        WHERE deployment_id = v_deployment;
    END LOOP;
END;
$$;

-- ------------------------------------------------------------
-- RETRIEVAL: ACTIVE ENVIRONMENT VERSIONS
-- ------------------------------------------------------------

SELECT
    environment_name,
    artifact_name,
    version,
    deployment_status,
    completed_at
FROM active_environment_deployments
ORDER BY environment_name;

-- ------------------------------------------------------------
-- VALIDATION: DEPLOYMENT ELIGIBILITY
-- ------------------------------------------------------------

SELECT *
FROM check_deployment_eligibility(
    (SELECT artifact_id FROM artifacts WHERE version = '1.0.0'),
    (SELECT environment_id FROM environments
     WHERE environment_name = 'production'),
    (SELECT user_id FROM users WHERE username = 'release-bot')
);

-- ------------------------------------------------------------
-- AGGREGATION: ENVIRONMENT DEPLOYMENT STATISTICS
-- ------------------------------------------------------------

SELECT
    e.environment_name,
    COUNT(d.deployment_id) AS deployment_count,
    COUNT(*) FILTER (
        WHERE d.deployment_status = 'succeeded'
    ) AS successful_deployments,
    COUNT(*) FILTER (
        WHERE d.deployment_status = 'failed'
    ) AS failed_deployments,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE d.deployment_status = 'succeeded'
        ) / NULLIF(COUNT(d.deployment_id), 0),
        2
    ) AS success_percentage
FROM environments e
LEFT JOIN deployments d
    ON d.environment_id = e.environment_id
GROUP BY e.environment_id, e.environment_name
ORDER BY MIN(e.sequence_number);

-- ------------------------------------------------------------
-- CTE: RELEASE PROMOTION CONSISTENCY
-- ------------------------------------------------------------

WITH latest_deployments AS (
    SELECT DISTINCT ON (environment_id)
        environment_id,
        artifact_id,
        deployment_status,
        completed_at
    FROM deployments
    WHERE deployment_status = 'succeeded'
    ORDER BY environment_id, completed_at DESC
),
release_state AS (
    SELECT
        e.environment_name,
        e.sequence_number,
        l.artifact_id,
        LAG(l.artifact_id) OVER (
            ORDER BY e.sequence_number
        ) AS previous_artifact_id
    FROM environments e
    LEFT JOIN latest_deployments l
        ON l.environment_id = e.environment_id
)
SELECT
    environment_name,
    artifact_id,
    previous_artifact_id,
    CASE
        WHEN sequence_number = 1 THEN 'INITIAL_ENVIRONMENT'
        WHEN artifact_id IS NULL THEN 'NOT_DEPLOYED'
        WHEN artifact_id = previous_artifact_id THEN 'CONSISTENT'
        ELSE 'ARTIFACT_MISMATCH'
    END AS promotion_state
FROM release_state
ORDER BY sequence_number;

-- ------------------------------------------------------------
-- REPORTING: HEALTH AND PERFORMANCE
-- ------------------------------------------------------------

SELECT
    environment_name,
    artifact_name,
    version,
    deployment_status,
    healthy,
    error_rate,
    response_time_ms,
    availability_percent
FROM deployment_health_report
ORDER BY environment_name;

-- ------------------------------------------------------------
-- FAILURE REPORT
-- ------------------------------------------------------------

SELECT
    d.deployment_id,
    e.environment_name,
    a.version,
    d.failure_reason,
    d.started_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN artifacts a
    ON a.artifact_id = d.artifact_id
WHERE d.deployment_status = 'failed'
ORDER BY d.started_at DESC;

-- ------------------------------------------------------------
-- AUDIT TRAIL
-- ------------------------------------------------------------

SELECT
    audit_id,
    deployment_id,
    event_type,
    event_details,
    created_at
FROM deployment_audit
ORDER BY audit_id;

COMMIT;

-- ============================================================
-- OPERATIONAL NOTES
--
-- 1. Artifacts are immutable. A new release creates a new row.
-- 2. Secret values are stored outside PostgreSQL.
-- 3. Approval records are separate from deployment execution.
-- 4. The eligibility function checks recorded check results.
-- 5. Deployment execution and real health verification belong
--    to a trusted deployment service.
-- 6. Database permissions should restrict writes to service roles.
-- 7. Production deployment should use serialized execution,
--    transaction boundaries, and concurrency control.
-- 8. Rollback must reference a previously verified artifact.
-- ============================================================

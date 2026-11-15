-- ============================================================
-- AUTOMATED ROLLBACK STRATEGIES AND RELEASE RECOVERY
-- PostgreSQL 15+
--
-- Models:
-- Repositories -> Releases -> Deployment attempts
-- -> Health observations -> Rollback decisions
-- -> Recovery events -> Operational reporting
--
-- All timestamps use timestamptz.
-- Production deployment credentials are not stored here.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS release_ops;

SET search_path TO release_ops, public;

-- ------------------------------------------------------------
-- DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE release_state AS ENUM (
    'created',
    'deploying',
    'active',
    'failed',
    'rolling_back',
    'rolled_back',
    'recovered'
);

CREATE TYPE deployment_strategy AS ENUM (
    'immediate',
    'blue_green',
    'canary',
    'progressive'
);

CREATE TYPE recovery_type AS ENUM (
    'automatic_rollback',
    'manual_rollback',
    'forward_recovery',
    'traffic_switch'
);

CREATE TYPE health_status AS ENUM (
    'healthy',
    'degraded',
    'critical'
);

-- ------------------------------------------------------------
-- REPOSITORIES AND ENVIRONMENTS
-- ------------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(150) NOT NULL UNIQUE,
    owner_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(repository_name)) > 0)
);

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_name VARCHAR(80) NOT NULL UNIQUE,
    is_production BOOLEAN NOT NULL DEFAULT false,
    region VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE environment_health_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    policy_version INTEGER NOT NULL,
    max_error_rate NUMERIC(6,5) NOT NULL DEFAULT 0.05,
    max_latency_ms NUMERIC(12,2) NOT NULL DEFAULT 500,
    min_availability NUMERIC(6,5) NOT NULL DEFAULT 0.99,
    max_failed_checks INTEGER NOT NULL DEFAULT 2,
    required_healthy_windows INTEGER NOT NULL DEFAULT 2,
    automatic_rollback BOOLEAN NOT NULL DEFAULT true,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(environment_id, policy_version),

    CHECK (max_error_rate BETWEEN 0 AND 1),
    CHECK (max_latency_ms > 0),
    CHECK (min_availability BETWEEN 0 AND 1),
    CHECK (max_failed_checks >= 0),
    CHECK (required_healthy_windows >= 1)
);

-- ------------------------------------------------------------
-- RELEASE ARTIFACTS
-- ------------------------------------------------------------

CREATE TABLE releases (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    version VARCHAR(60) NOT NULL,
    artifact_digest VARCHAR(71) NOT NULL,
    source_commit VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(repository_id, version),
    UNIQUE(repository_id, artifact_digest),

    CHECK (version <> ''),
    CHECK (artifact_digest ~ '^sha256:[a-fA-F0-9]{64}$'),
    CHECK (source_commit ~ '^[a-fA-F0-9]{40,64}$')
);

-- ------------------------------------------------------------
-- DEPLOYMENTS
-- ------------------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id BIGINT NOT NULL REFERENCES releases(release_id),
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    policy_id BIGINT NOT NULL
        REFERENCES environment_health_policies(policy_id),
    strategy deployment_strategy NOT NULL,
    state release_state NOT NULL DEFAULT 'created',
    traffic_percentage INTEGER NOT NULL DEFAULT 0,
    initiated_by VARCHAR(150) NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (traffic_percentage BETWEEN 0 AND 100),
    CHECK (completed_at IS NULL OR started_at IS NOT NULL)
);

CREATE INDEX idx_deployments_environment_state
    ON deployments(environment_id, state);

CREATE INDEX idx_deployments_release
    ON deployments(release_id);

CREATE INDEX idx_deployments_recent
    ON deployments(created_at DESC);

-- ------------------------------------------------------------
-- HEALTH OBSERVATIONS
-- ------------------------------------------------------------

CREATE TABLE health_observations (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),
    window_number INTEGER NOT NULL,
    error_rate NUMERIC(7,6) NOT NULL,
    latency_ms NUMERIC(12,2) NOT NULL,
    availability NUMERIC(7,6) NOT NULL,
    failed_checks INTEGER NOT NULL DEFAULT 0,
    evaluated_status health_status NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(deployment_id, window_number),

    CHECK (window_number >= 1),
    CHECK (error_rate BETWEEN 0 AND 1),
    CHECK (latency_ms >= 0),
    CHECK (availability BETWEEN 0 AND 1),
    CHECK (failed_checks >= 0)
);

CREATE INDEX idx_health_observations_deployment
    ON health_observations(deployment_id, window_number);

-- ------------------------------------------------------------
-- ROLLBACK EVENTS
-- ------------------------------------------------------------

CREATE TABLE recovery_events (
    recovery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    failed_deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),
    restored_deployment_id BIGINT
        REFERENCES deployments(deployment_id),
    recovery_method recovery_type NOT NULL,
    reason TEXT NOT NULL,
    initiated_by VARCHAR(150) NOT NULL,
    succeeded BOOLEAN NOT NULL DEFAULT false,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,

    CHECK (
        restored_deployment_id IS NULL
        OR restored_deployment_id <> failed_deployment_id
    )
);

CREATE INDEX idx_recovery_events_recent
    ON recovery_events(started_at DESC);

-- ------------------------------------------------------------
-- ENVIRONMENT ROUTING STATE
-- ------------------------------------------------------------

CREATE TABLE environment_routing (
    environment_id BIGINT PRIMARY KEY
        REFERENCES environments(environment_id),
    active_deployment_id BIGINT
        REFERENCES deployments(deployment_id),
    previous_deployment_id BIGINT
        REFERENCES deployments(deployment_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (
        active_deployment_id IS NULL
        OR previous_deployment_id IS NULL
        OR active_deployment_id <> previous_deployment_id
    )
);

-- ------------------------------------------------------------
-- AUDIT EVENTS
-- ------------------------------------------------------------

CREATE TABLE audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT REFERENCES environments(environment_id),
    deployment_id BIGINT REFERENCES deployments(deployment_id),
    event_type VARCHAR(100) NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor VARCHAR(150) NOT NULL
);

CREATE INDEX idx_audit_events_environment_time
    ON audit_events(environment_id, occurred_at DESC);

CREATE INDEX idx_audit_events_json
    ON audit_events USING GIN(event_details);

-- ------------------------------------------------------------
-- VALIDATION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_deployment_health(
    p_deployment_id BIGINT
)
RETURNS TABLE (
    total_windows BIGINT,
    healthy_windows BIGINT,
    unhealthy_windows BIGINT,
    eligible BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        COUNT(*)::BIGINT,
        COUNT(*) FILTER (
            WHERE ho.evaluated_status = 'healthy'
        )::BIGINT,
        COUNT(*) FILTER (
            WHERE ho.evaluated_status <> 'healthy'
        )::BIGINT,
        (
            COUNT(*) > 0
            AND COUNT(*) FILTER (
                WHERE ho.evaluated_status <> 'healthy'
            ) = 0
        )
    FROM health_observations ho
    WHERE ho.deployment_id = p_deployment_id;
$$;

-- ------------------------------------------------------------
-- DERIVE HEALTH STATUS FROM THE ACTIVE POLICY
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION classify_health(
    p_deployment_id BIGINT,
    p_error_rate NUMERIC,
    p_latency NUMERIC,
    p_availability NUMERIC,
    p_failed_checks INTEGER
)
RETURNS health_status
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_policy environment_health_policies%ROWTYPE;
BEGIN
    SELECT hp.*
    INTO STRICT v_policy
    FROM deployments d
    JOIN environment_health_policies hp
      ON hp.policy_id = d.policy_id
    WHERE d.deployment_id = p_deployment_id
      AND hp.enabled = true;

    IF p_error_rate > v_policy.max_error_rate
       OR p_latency > v_policy.max_latency_ms
       OR p_availability < v_policy.min_availability
       OR p_failed_checks > v_policy.max_failed_checks
    THEN
        RETURN 'critical';
    END IF;

    RETURN 'healthy';
END;
$$;

-- ------------------------------------------------------------
-- VALIDATE HEALTH OBSERVATIONS AUTOMATICALLY
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_observation_health()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy environment_health_policies%ROWTYPE;
BEGIN
    SELECT hp.*
    INTO STRICT v_policy
    FROM deployments d
    JOIN environment_health_policies hp
      ON hp.policy_id = d.policy_id
    WHERE d.deployment_id = NEW.deployment_id;

    IF NOT v_policy.enabled THEN
        RAISE EXCEPTION 'Deployment health policy is disabled';
    END IF;

    IF NEW.error_rate > v_policy.max_error_rate
       OR NEW.latency_ms > v_policy.max_latency_ms
       OR NEW.availability < v_policy.min_availability
       OR NEW.failed_checks > v_policy.max_failed_checks
    THEN
        NEW.evaluated_status := 'critical';
    ELSE
        NEW.evaluated_status := 'healthy';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_observation_health
BEFORE INSERT OR UPDATE OF
    error_rate,
    latency_ms,
    availability,
    failed_checks
ON health_observations
FOR EACH ROW
EXECUTE FUNCTION set_observation_health();

-- ------------------------------------------------------------
-- ENFORCE VALID DEPLOYMENT STATE TRANSITIONS
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION enforce_deployment_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.state = 'created'
            AND NEW.state IN ('deploying', 'failed'))
        OR
        (OLD.state = 'deploying'
            AND NEW.state IN ('active', 'failed', 'rolling_back'))
        OR
        (OLD.state = 'active'
            AND NEW.state IN ('rolling_back', 'failed'))
        OR
        (OLD.state = 'failed'
            AND NEW.state = 'rolling_back')
        OR
        (OLD.state = 'rolling_back'
            AND NEW.state IN ('rolled_back', 'failed'))
        OR
        (OLD.state = 'rolled_back'
            AND NEW.state IN ('deploying', 'recovered'))
        OR
        (OLD.state = 'recovered'
            AND NEW.state = 'rolling_back')
    ) THEN
        RAISE EXCEPTION
            'Invalid deployment transition: % -> %',
            OLD.state,
            NEW.state;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_transition
BEFORE UPDATE OF state ON deployments
FOR EACH ROW
EXECUTE FUNCTION enforce_deployment_transition();

-- ------------------------------------------------------------
-- RECORD AUDIT EVENTS
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION log_deployment_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit_events (
        environment_id,
        deployment_id,
        event_type,
        event_details,
        actor
    )
    VALUES (
        NEW.environment_id,
        NEW.deployment_id,
        'deployment_state_changed',
        jsonb_build_object(
            'old_state', OLD.state,
            'new_state', NEW.state,
            'traffic', NEW.traffic_percentage
        ),
        NEW.initiated_by
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_audit
AFTER UPDATE OF state ON deployments
FOR EACH ROW
WHEN (OLD.state IS DISTINCT FROM NEW.state)
EXECUTE FUNCTION log_deployment_state();

-- ------------------------------------------------------------
-- ELIGIBILITY DETERMINATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION check_rollback_eligibility(
    p_failed_deployment BIGINT,
    p_target_deployment BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_failed deployments%ROWTYPE;
    v_target deployments%ROWTYPE;
    v_required INTEGER;
    v_healthy BIGINT;
BEGIN
    SELECT * INTO STRICT v_failed
    FROM deployments
    WHERE deployment_id = p_failed_deployment;

    SELECT * INTO STRICT v_target
    FROM deployments
    WHERE deployment_id = p_target_deployment;

    IF v_failed.environment_id <> v_target.environment_id THEN
        RETURN false;
    END IF;

    IF v_failed.deployment_id = v_target.deployment_id THEN
        RETURN false;
    END IF;

    IF v_target.state NOT IN ('active', 'recovered', 'rolled_back') THEN
        RETURN false;
    END IF;

    SELECT required_healthy_windows
    INTO STRICT v_required
    FROM environment_health_policies
    WHERE policy_id = v_target.policy_id
      AND enabled = true;

    SELECT COUNT(*)
    INTO v_healthy
    FROM health_observations
    WHERE deployment_id = p_target_deployment
      AND evaluated_status = 'healthy';

    RETURN v_healthy >= v_required;
END;
$$;

-- ------------------------------------------------------------
-- ATOMIC ROLLBACK PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE execute_rollback(
    p_failed_deployment BIGINT,
    p_target_deployment BIGINT,
    p_actor VARCHAR(150),
    p_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_environment BIGINT;
    v_recovery_id BIGINT;
BEGIN
    -- Serialize routing changes for this environment.
    SELECT environment_id
    INTO STRICT v_environment
    FROM deployments
    WHERE deployment_id = p_failed_deployment
    FOR UPDATE;

    PERFORM 1
    FROM deployments
    WHERE deployment_id = p_target_deployment
      AND environment_id = v_environment
    FOR UPDATE;

    IF NOT check_rollback_eligibility(
        p_failed_deployment,
        p_target_deployment
    ) THEN
        RAISE EXCEPTION 'Rollback target is not eligible';
    END IF;

    INSERT INTO recovery_events (
        failed_deployment_id,
        restored_deployment_id,
        recovery_method,
        reason,
        initiated_by,
        succeeded
    )
    VALUES (
        p_failed_deployment,
        p_target_deployment,
        'automatic_rollback',
        p_reason,
        p_actor,
        false
    )
    RETURNING recovery_id INTO v_recovery_id;

    UPDATE deployments
    SET state = 'rolling_back',
        traffic_percentage = 0
    WHERE deployment_id = p_failed_deployment;

    UPDATE deployments
    SET traffic_percentage = 100
    WHERE deployment_id = p_target_deployment;

    INSERT INTO environment_routing (
        environment_id,
        active_deployment_id,
        previous_deployment_id
    )
    VALUES (
        v_environment,
        p_target_deployment,
        p_failed_deployment
    )
    ON CONFLICT (environment_id)
    DO UPDATE SET
        previous_deployment_id =
            environment_routing.active_deployment_id,
        active_deployment_id = EXCLUDED.active_deployment_id,
        updated_at = now();

    UPDATE deployments
    SET state = 'rolled_back',
        completed_at = now()
    WHERE deployment_id = p_failed_deployment;

    UPDATE recovery_events
    SET succeeded = true,
        completed_at = now()
    WHERE recovery_id = v_recovery_id;

    INSERT INTO audit_events (
        environment_id,
        deployment_id,
        event_type,
        event_details,
        actor
    )
    VALUES (
        v_environment,
        p_failed_deployment,
        'rollback_completed',
        jsonb_build_object(
            'restored_deployment', p_target_deployment,
            'recovery_id', v_recovery_id
        ),
        p_actor
    );

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$;

-- ------------------------------------------------------------
-- RELEASE DEPLOYMENT PROCESSING
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE activate_deployment(
    p_deployment_id BIGINT,
    p_actor VARCHAR(150)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment deployments%ROWTYPE;
    v_policy environment_health_policies%ROWTYPE;
    v_windows BIGINT;
    v_healthy BIGINT;
    v_previous BIGINT;
BEGIN
    SELECT * INTO STRICT v_deployment
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    SELECT * INTO STRICT v_policy
    FROM environment_health_policies
    WHERE policy_id = v_deployment.policy_id
      AND enabled = true;

    IF v_deployment.state NOT IN ('created', 'rolled_back') THEN
        RAISE EXCEPTION 'Deployment cannot be activated from state %',
            v_deployment.state;
    END IF;

    UPDATE deployments
    SET state = 'deploying',
        started_at = now()
    WHERE deployment_id = p_deployment_id;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE evaluated_status = 'healthy'
        )
    INTO v_windows, v_healthy
    FROM health_observations
    WHERE deployment_id = p_deployment_id;

    IF v_windows < v_policy.required_healthy_windows
       OR v_healthy <> v_windows
    THEN
        UPDATE deployments
        SET state = 'failed',
            failure_reason = 'Health gate rejected deployment',
            completed_at = now()
        WHERE deployment_id = p_deployment_id;

        RAISE EXCEPTION 'Health gate failed';
    END IF;

    SELECT active_deployment_id
    INTO v_previous
    FROM environment_routing
    WHERE environment_id = v_deployment.environment_id
    FOR UPDATE;

    UPDATE deployments
    SET traffic_percentage = 0
    WHERE deployment_id = v_previous;

    UPDATE deployments
    SET traffic_percentage = 100,
        state = 'active',
        completed_at = now()
    WHERE deployment_id = p_deployment_id;

    INSERT INTO environment_routing (
        environment_id,
        active_deployment_id,
        previous_deployment_id
    )
    VALUES (
        v_deployment.environment_id,
        p_deployment_id,
        v_previous
    )
    ON CONFLICT (environment_id)
    DO UPDATE SET
        previous_deployment_id =
            environment_routing.active_deployment_id,
        active_deployment_id = EXCLUDED.active_deployment_id,
        updated_at = now();

END;
$$;

-- ------------------------------------------------------------
-- OPERATIONAL REPORTING VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW release_health_report AS
SELECT
    r.repository_name,
    rel.version,
    e.environment_name,
    d.deployment_id,
    d.strategy,
    d.state,
    d.traffic_percentage,
    COUNT(ho.observation_id) AS observation_count,
    COUNT(ho.observation_id) FILTER (
        WHERE ho.evaluated_status = 'healthy'
    ) AS healthy_windows,
    COUNT(ho.observation_id) FILTER (
        WHERE ho.evaluated_status = 'critical'
    ) AS critical_windows,
    AVG(ho.error_rate) AS average_error_rate,
    AVG(ho.latency_ms) AS average_latency_ms,
    AVG(ho.availability) AS average_availability,
    d.failure_reason,
    d.started_at,
    d.completed_at
FROM deployments d
JOIN releases rel ON rel.release_id = d.release_id
JOIN repositories r ON r.repository_id = rel.repository_id
JOIN environments e ON e.environment_id = d.environment_id
LEFT JOIN health_observations ho
    ON ho.deployment_id = d.deployment_id
GROUP BY
    r.repository_name,
    rel.version,
    e.environment_name,
    d.deployment_id;

-- ------------------------------------------------------------
-- SAMPLE DATA
-- ------------------------------------------------------------

INSERT INTO repositories (
    repository_name,
    owner_name
)
VALUES
    ('payments-api', 'platform-engineering'),
    ('inventory-service', 'operations-engineering');

INSERT INTO environments (
    environment_name,
    is_production,
    region
)
VALUES
    ('production', true, 'ap-south-1'),
    ('staging', false, 'ap-south-1');

INSERT INTO environment_health_policies (
    environment_id,
    policy_version,
    max_error_rate,
    max_latency_ms,
    min_availability,
    max_failed_checks,
    required_healthy_windows
)
SELECT
    environment_id,
    1,
    0.05,
    500,
    0.99,
    2,
    2
FROM environments;

INSERT INTO releases (
    repository_id,
    version,
    artifact_digest,
    source_commit
)
SELECT
    repository_id,
    '1.0.0',
    'sha256:' || repeat('a', 64),
    repeat('1', 40)
FROM repositories
WHERE repository_name = 'payments-api';

INSERT INTO releases (
    repository_id,
    version,
    artifact_digest,
    source_commit
)
SELECT
    repository_id,
    '2.0.0',
    'sha256:' || repeat('b', 64),
    repeat('2', 40)
FROM repositories
WHERE repository_name = 'payments-api';

INSERT INTO releases (
    repository_id,
    version,
    artifact_digest,
    source_commit
)
SELECT
    repository_id,
    '2.0.1',
    'sha256:' || repeat('c', 64),
    repeat('3', 40)
FROM repositories
WHERE repository_name = 'payments-api';

-- Baseline production deployment.
INSERT INTO deployments (
    release_id,
    environment_id,
    policy_id,
    strategy,
    state,
    traffic_percentage,
    initiated_by,
    started_at,
    completed_at
)
SELECT
    r.release_id,
    e.environment_id,
    hp.policy_id,
    'immediate',
    'active',
    100,
    'release-manager',
    now(),
    now()
FROM releases r
JOIN repositories repo
    ON repo.repository_id = r.repository_id
JOIN environments e
    ON e.environment_name = 'production'
JOIN environment_health_policies hp
    ON hp.environment_id = e.environment_id
WHERE repo.repository_name = 'payments-api'
  AND r.version = '1.0.0';

-- Failed canary deployment.
INSERT INTO deployments (
    release_id,
    environment_id,
    policy_id,
    strategy,
    state,
    traffic_percentage,
    initiated_by,
    started_at,
    failure_reason
)
SELECT
    r.release_id,
    e.environment_id,
    hp.policy_id,
    'canary',
    'rolled_back',
    0,
    'automated-release-controller',
    now(),
    'Canary exceeded error-rate and latency thresholds'
FROM releases r
JOIN repositories repo
    ON repo.repository_id = r.repository_id
JOIN environments e
    ON e.environment_name = 'production'
JOIN environment_health_policies hp
    ON hp.environment_id = e.environment_id
WHERE repo.repository_name = 'payments-api'
  AND r.version = '2.0.0';

-- Forward recovery deployment.
INSERT INTO deployments (
    release_id,
    environment_id,
    policy_id,
    strategy,
    state,
    traffic_percentage,
    initiated_by,
    started_at,
    completed_at
)
SELECT
    r.release_id,
    e.environment_id,
    hp.policy_id,
    'canary',
    'recovered',
    0,
    'release-manager',
    now(),
    now()
FROM releases r
JOIN repositories repo
    ON repo.repository_id = r.repository_id
JOIN environments e
    ON e.environment_name = 'production'
JOIN environment_health_policies hp
    ON hp.environment_id = e.environment_id
WHERE repo.repository_name = 'payments-api'
  AND r.version = '2.0.1';

-- Healthy observations for the baseline.
INSERT INTO health_observations (
    deployment_id,
    window_number,
    error_rate,
    latency_ms,
    availability,
    failed_checks,
    evaluated_status
)
SELECT
    d.deployment_id,
    x.window_number,
    0.01,
    120 + x.window_number * 10,
    0.999,
    0,
    'healthy'
FROM deployments d
CROSS JOIN (VALUES (1), (2)) AS x(window_number)
JOIN releases r ON r.release_id = d.release_id
WHERE r.version = '1.0.0';

-- Critical observations for the failed canary.
INSERT INTO health_observations (
    deployment_id,
    window_number,
    error_rate,
    latency_ms,
    availability,
    failed_checks,
    evaluated_status
)
SELECT
    d.deployment_id,
    x.window_number,
    x.error_rate,
    x.latency_ms,
    x.availability,
    x.failed_checks,
    'healthy'
FROM deployments d
JOIN releases r ON r.release_id = d.release_id
CROSS JOIN (
    VALUES
        (1, 0.01::numeric, 120::numeric, 0.999::numeric, 0),
        (2, 0.02::numeric, 150::numeric, 0.998::numeric, 0),
        (3, 0.20::numeric, 1200::numeric, 0.90::numeric, 5),
        (4, 0.18::numeric, 950::numeric, 0.92::numeric, 4)
) AS x(window_number, error_rate, latency_ms, availability, failed_checks)
WHERE r.version = '2.0.0';

-- The trigger derives the actual status. The supplied value is overwritten.
UPDATE health_observations
SET error_rate = error_rate
WHERE deployment_id IN (
    SELECT deployment_id
    FROM deployments d
    JOIN releases r ON r.release_id = d.release_id
    WHERE r.version = '2.0.0'
);

-- Healthy observations for forward recovery.
INSERT INTO health_observations (
    deployment_id,
    window_number,
    error_rate,
    latency_ms,
    availability,
    failed_checks,
    evaluated_status
)
SELECT
    d.deployment_id,
    x.window_number,
    0.01,
    120 + x.window_number * 5,
    0.999,
    0,
    'healthy'
FROM deployments d
JOIN releases r ON r.release_id = d.release_id
CROSS JOIN (VALUES (1), (2), (3), (4)) AS x(window_number)
WHERE r.version = '2.0.1';

-- Recalculate the recovery observation states through the trigger.
UPDATE health_observations
SET latency_ms = latency_ms
WHERE deployment_id IN (
    SELECT deployment_id
    FROM deployments d
    JOIN releases r ON r.release_id = d.release_id
    WHERE r.version = '2.0.1'
);

-- Establish the production routing record.
INSERT INTO environment_routing (
    environment_id,
    active_deployment_id,
    previous_deployment_id
)
SELECT
    e.environment_id,
    current_deployment.deployment_id,
    previous_deployment.deployment_id
FROM environments e
JOIN deployments current_deployment
    ON current_deployment.environment_id = e.environment_id
JOIN releases current_release
    ON current_release.release_id = current_deployment.release_id
JOIN deployments previous_deployment
    ON previous_deployment.environment_id = e.environment_id
JOIN releases previous_release
    ON previous_release.release_id = previous_deployment.release_id
WHERE e.environment_name = 'production'
  AND current_release.version = '1.0.0'
  AND previous_release.version = '2.0.0';

INSERT INTO recovery_events (
    failed_deployment_id,
    restored_deployment_id,
    recovery_method,
    reason,
    initiated_by,
    succeeded,
    completed_at
)
SELECT
    failed.deployment_id,
    restored.deployment_id,
    'automatic_rollback',
    'Canary health thresholds violated',
    'automated-release-controller',
    true,
    now()
FROM deployments failed
JOIN releases failed_release
    ON failed_release.release_id = failed.release_id
JOIN deployments restored
    ON restored.environment_id = failed.environment_id
JOIN releases restored_release
    ON restored_release.release_id = restored.release_id
WHERE failed_release.version = '2.0.0'
  AND restored_release.version = '1.0.0';

-- ------------------------------------------------------------
-- RETRIEVAL QUERIES
-- ------------------------------------------------------------

SELECT *
FROM release_health_report
ORDER BY started_at DESC;

SELECT
    r.version,
    d.state,
    d.strategy,
    d.traffic_percentage,
    d.failure_reason
FROM deployments d
JOIN releases r ON r.release_id = d.release_id
ORDER BY d.created_at DESC;

-- ------------------------------------------------------------
-- VALIDATION QUERIES
-- ------------------------------------------------------------

SELECT
    d.deployment_id,
    r.version,
    evaluate_deployment_health(d.deployment_id)
FROM deployments d
JOIN releases r ON r.release_id = d.release_id;

-- Detect unhealthy observations.
SELECT
    d.deployment_id,
    r.version,
    ho.window_number,
    ho.error_rate,
    ho.latency_ms,
    ho.availability,
    ho.evaluated_status
FROM health_observations ho
JOIN deployments d ON d.deployment_id = ho.deployment_id
JOIN releases r ON r.release_id = d.release_id
WHERE ho.evaluated_status <> 'healthy';

-- ------------------------------------------------------------
-- AGGREGATION
-- ------------------------------------------------------------

SELECT
    e.environment_name,
    d.strategy,
    COUNT(*) AS deployments,
    COUNT(*) FILTER (
        WHERE d.state = 'active'
    ) AS active_deployments,
    COUNT(*) FILTER (
        WHERE d.state = 'rolled_back'
    ) AS rolled_back_deployments,
    AVG(d.traffic_percentage) AS average_traffic
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
GROUP BY e.environment_name, d.strategy;

-- ------------------------------------------------------------
-- RECOVERY REPORT
-- ------------------------------------------------------------

SELECT
    failed_release.version AS failed_version,
    restored_release.version AS restored_version,
    re.recovery_method,
    re.reason,
    re.succeeded,
    re.started_at,
    re.completed_at
FROM recovery_events re
JOIN deployments failed
    ON failed.deployment_id = re.failed_deployment_id
JOIN releases failed_release
    ON failed_release.release_id = failed.release_id
LEFT JOIN deployments restored
    ON restored.deployment_id = re.restored_deployment_id
LEFT JOIN releases restored_release
    ON restored_release.release_id = restored.release_id
ORDER BY re.started_at DESC;

-- ------------------------------------------------------------
-- CTE: IDENTIFY DEPLOYMENTS REQUIRING INVESTIGATION
-- ------------------------------------------------------------

WITH deployment_risk AS (
    SELECT
        d.deployment_id,
        r.version,
        e.environment_name,
        COUNT(*) FILTER (
            WHERE ho.evaluated_status = 'critical'
        ) AS critical_windows,
        AVG(ho.error_rate) AS average_error_rate,
        AVG(ho.latency_ms) AS average_latency
    FROM deployments d
    JOIN releases r ON r.release_id = d.release_id
    JOIN environments e ON e.environment_id = d.environment_id
    LEFT JOIN health_observations ho
        ON ho.deployment_id = d.deployment_id
    GROUP BY
        d.deployment_id,
        r.version,
        e.environment_name
)
SELECT *
FROM deployment_risk
WHERE critical_windows > 0
   OR average_error_rate > 0.05
ORDER BY critical_windows DESC;

-- ------------------------------------------------------------
-- TRANSACTIONAL ROLLBACK EXAMPLE
--
-- The demonstration is rolled back so sample data remains unchanged.
-- Actual recovery should use execute_rollback() in a controlled
-- operational transaction after confirming its target.
-- ------------------------------------------------------------

SAVEPOINT recovery_simulation;

DO $$
DECLARE
    v_failed BIGINT;
    v_target BIGINT;
BEGIN
    SELECT d.deployment_id
    INTO v_failed
    FROM deployments d
    JOIN releases r ON r.release_id = d.release_id
    WHERE r.version = '2.0.0'
    LIMIT 1;

    SELECT d.deployment_id
    INTO v_target
    FROM deployments d
    JOIN releases r ON r.release_id = d.release_id
    WHERE r.version = '1.0.0'
    LIMIT 1;

    RAISE NOTICE
        'Rollback simulation: failed deployment %, target %',
        v_failed,
        v_target;

    RAISE NOTICE
        'Target eligible: %',
        check_rollback_eligibility(v_failed, v_target);
END;
$$;

ROLLBACK TO SAVEPOINT recovery_simulation;

COMMIT;

-- ------------------------------------------------------------
-- PRODUCTION OPERATING NOTES
--
-- 1. Run deployment and routing updates under controlled transactions.
-- 2. Restrict procedure execution through database roles.
-- 3. Use external monitoring for real-time telemetry ingestion.
-- 4. Do not store deployment secrets or credentials in audit JSON.
-- 5. Database rollback does not reverse external infrastructure changes.
-- 6. Use expand-contract migrations and backward-compatible schemas.
-- 7. Validate artifacts and immutable digests before restoration.
-- 8. Protect audit records with restricted INSERT-only application roles.
-- ------------------------------------------------------------

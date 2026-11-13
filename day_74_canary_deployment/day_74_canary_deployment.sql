-- ============================================================
-- CANARY DEPLOYMENT MANAGEMENT AND GOVERNANCE
-- PostgreSQL 15+
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS canary;

SET search_path TO canary, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN STATES
-- ------------------------------------------------------------

CREATE TYPE deployment_state AS ENUM (
    'created',
    'running',
    'promoted',
    'rolled_back',
    'failed'
);

CREATE TYPE environment_type AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE check_state AS ENUM (
    'pending',
    'passed',
    'failed',
    'error'
);

CREATE TYPE deployment_event_type AS ENUM (
    'registered',
    'started',
    'health_passed',
    'traffic_increased',
    'promoted',
    'rolled_back',
    'failed',
    'manual_approval'
);

-- ------------------------------------------------------------
-- REPOSITORY OF APPLICATIONS
-- ------------------------------------------------------------

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_name VARCHAR(120) NOT NULL UNIQUE,
    owning_team VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE application_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES applications(application_id),
    version VARCHAR(50) NOT NULL,
    artifact_digest VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(application_id, version),
    UNIQUE(application_id, artifact_digest)
);

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_name environment_type NOT NULL,
    region VARCHAR(100) NOT NULL,
    UNIQUE(environment_name, region)
);

CREATE TABLE deployment_actors (
    actor_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_name VARCHAR(120) NOT NULL UNIQUE,
    actor_role VARCHAR(40) NOT NULL CHECK (
        actor_role IN (
            'release_engineer',
            'site_reliability_engineer',
            'security_reviewer',
            'administrator',
            'automation'
        )
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- RELEASE POLICIES
-- ------------------------------------------------------------

CREATE TABLE release_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name VARCHAR(120) NOT NULL UNIQUE,
    maximum_error_rate NUMERIC(8,6) NOT NULL
        CHECK (maximum_error_rate > 0 AND maximum_error_rate < 1),
    maximum_p95_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (maximum_p95_latency_ms > 0),
    maximum_error_regression NUMERIC(8,6) NOT NULL
        CHECK (maximum_error_regression >= 0),
    minimum_requests BIGINT NOT NULL CHECK (minimum_requests > 0),
    required_consecutive_passes INTEGER NOT NULL DEFAULT 1
        CHECK (required_consecutive_passes > 0),
    manual_approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE policy_traffic_stages (
    policy_id BIGINT NOT NULL
        REFERENCES release_policies(policy_id) ON DELETE CASCADE,
    stage_order INTEGER NOT NULL CHECK (stage_order > 0),
    traffic_percent INTEGER NOT NULL
        CHECK (traffic_percent BETWEEN 1 AND 100),

    PRIMARY KEY(policy_id, stage_order),
    UNIQUE(policy_id, traffic_percent)
);

-- ------------------------------------------------------------
-- DEPLOYMENT RECORDS
-- ------------------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_key UUID NOT NULL UNIQUE,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    version_id BIGINT NOT NULL
        REFERENCES application_versions(version_id),
    previous_version_id BIGINT
        REFERENCES application_versions(version_id),
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    policy_id BIGINT NOT NULL
        REFERENCES release_policies(policy_id),
    initiated_by BIGINT NOT NULL
        REFERENCES deployment_actors(actor_id),
    state deployment_state NOT NULL DEFAULT 'created',
    traffic_percent INTEGER NOT NULL DEFAULT 0
        CHECK (traffic_percent BETWEEN 0 AND 100),
    current_stage_order INTEGER NOT NULL DEFAULT 0
        CHECK (current_stage_order >= 0),
    consecutive_passes INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_passes >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    CHECK (
        previous_version_id IS NULL OR
        previous_version_id <> version_id
    ),

    CHECK (
        (state = 'running' AND traffic_percent > 0)
        OR
        (state = 'promoted' AND traffic_percent = 100)
        OR
        (state IN ('created', 'rolled_back', 'failed')
            AND traffic_percent = 0)
    )
);

CREATE UNIQUE INDEX one_active_deployment_per_application_environment
ON deployments(application_id, environment_id)
WHERE state = 'running';

CREATE INDEX idx_deployments_state_created
ON deployments(state, created_at DESC);

CREATE INDEX idx_deployments_application
ON deployments(application_id, created_at DESC);

-- ------------------------------------------------------------
-- BASELINE AND CANARY METRICS
-- ------------------------------------------------------------

CREATE TABLE deployment_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    observation_type VARCHAR(20) NOT NULL
        CHECK (observation_type IN ('baseline', 'canary')),
    requests BIGINT NOT NULL CHECK (requests >= 0),
    errors BIGINT NOT NULL CHECK (errors >= 0),
    p95_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (p95_latency_ms >= 0),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (errors <= requests)
);

CREATE INDEX idx_metrics_deployment_time
ON deployment_metrics(deployment_id, observed_at DESC);

CREATE TABLE deployment_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    metric_id BIGINT
        REFERENCES deployment_metrics(metric_id),
    check_name VARCHAR(100) NOT NULL,
    status check_state NOT NULL DEFAULT 'pending',
    measured_value NUMERIC(16,6),
    threshold_value NUMERIC(16,6),
    failure_reason TEXT,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_checks_deployment_status
ON deployment_checks(deployment_id, status);

-- ------------------------------------------------------------
-- HUMAN AND AUTOMATED APPROVALS
-- ------------------------------------------------------------

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    actor_id BIGINT NOT NULL
        REFERENCES deployment_actors(actor_id),
    approval_type VARCHAR(30) NOT NULL
        CHECK (approval_type IN (
            'release',
            'security',
            'operations'
        )),
    approved BOOLEAN NOT NULL,
    decision_reason TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(deployment_id, actor_id, approval_type)
);

CREATE INDEX idx_approvals_deployment
ON deployment_approvals(deployment_id, approval_type, approved);

-- ------------------------------------------------------------
-- IMMUTABLE AUDIT EVENTS
-- ------------------------------------------------------------

CREATE TABLE deployment_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    actor_id BIGINT REFERENCES deployment_actors(actor_id),
    event_type deployment_event_type NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_deployment_time
ON deployment_events(deployment_id, created_at);

CREATE INDEX idx_events_details
ON deployment_events USING GIN(event_details);

-- ------------------------------------------------------------
-- STATE TRANSITION ENFORCEMENT
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_deployment_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN

        IF NEW.state <> OLD.state AND NOT (
            (OLD.state = 'created' AND
                NEW.state IN ('running', 'failed'))
            OR
            (OLD.state = 'running' AND
                NEW.state IN ('promoted', 'rolled_back', 'failed'))
        ) THEN
            RAISE EXCEPTION
                'Invalid deployment transition: % -> %',
                OLD.state, NEW.state;
        END IF;

        IF OLD.state IN ('promoted', 'rolled_back', 'failed')
           AND NEW.state <> OLD.state THEN
            RAISE EXCEPTION 'Terminal deployment state is immutable';
        END IF;

        IF NEW.traffic_percent < OLD.traffic_percent
           AND NEW.state <> 'rolled_back' THEN
            RAISE EXCEPTION
                'Traffic cannot decrease without rollback';
        END IF;

        IF NEW.state = 'running' AND OLD.state = 'created' THEN
            NEW.started_at := now();
        END IF;

        IF NEW.state IN ('promoted', 'rolled_back', 'failed') THEN
            NEW.completed_at := now();
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_transition
BEFORE UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_transition();

-- ------------------------------------------------------------
-- AUDIT EVENT AUTOMATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_deployment_state_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_event deployment_event_type;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_event := 'registered';

        INSERT INTO deployment_events(
            deployment_id,
            actor_id,
            event_type,
            event_details
        )
        VALUES (
            NEW.deployment_id,
            NEW.initiated_by,
            v_event,
            jsonb_build_object(
                'state', NEW.state,
                'traffic_percent', NEW.traffic_percent
            )
        );

    ELSIF NEW.state IS DISTINCT FROM OLD.state THEN

        v_event := CASE NEW.state
            WHEN 'running' THEN 'started'
            WHEN 'promoted' THEN 'promoted'
            WHEN 'rolled_back' THEN 'rolled_back'
            WHEN 'failed' THEN 'failed'
            ELSE 'registered'
        END;

        INSERT INTO deployment_events(
            deployment_id,
            actor_id,
            event_type,
            event_details
        )
        VALUES (
            NEW.deployment_id,
            NEW.initiated_by,
            v_event,
            jsonb_build_object(
                'previous_state', OLD.state,
                'new_state', NEW.state,
                'traffic_percent', NEW.traffic_percent
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_audit
AFTER INSERT OR UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION record_deployment_state_event();

-- ------------------------------------------------------------
-- BASELINE AND CANARY METRIC VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_canary_health(
    p_deployment_id BIGINT,
    p_metric_id BIGINT
)
RETURNS TABLE (
    permitted BOOLEAN,
    failure_reasons TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy release_policies%ROWTYPE;
    v_candidate deployment_metrics%ROWTYPE;
    v_baseline deployment_metrics%ROWTYPE;
    v_deployment deployments%ROWTYPE;
    v_failures TEXT[] := ARRAY[]::TEXT[];
BEGIN
    SELECT *
    INTO v_deployment
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment does not exist';
    END IF;

    IF v_deployment.state <> 'running' THEN
        RAISE EXCEPTION 'Deployment is not running';
    END IF;

    SELECT *
    INTO v_policy
    FROM release_policies
    WHERE policy_id = v_deployment.policy_id
      AND enabled = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Release policy is missing or disabled';
    END IF;

    SELECT *
    INTO v_candidate
    FROM deployment_metrics
    WHERE metric_id = p_metric_id
      AND deployment_id = p_deployment_id
      AND observation_type = 'canary';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Canary metric does not exist';
    END IF;

    SELECT *
    INTO v_baseline
    FROM deployment_metrics
    WHERE deployment_id = p_deployment_id
      AND observation_type = 'baseline'
    ORDER BY observed_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Baseline metrics are missing';
    END IF;

    IF v_candidate.requests < v_policy.minimum_requests THEN
        v_failures := array_append(
            v_failures,
            'insufficient_requests'
        );
    END IF;

    IF v_candidate.requests = 0 THEN
        v_failures := array_append(
            v_failures,
            'zero_request_sample'
        );
    ELSE
        IF v_candidate.errors::NUMERIC /
            v_candidate.requests >
            v_policy.maximum_error_rate THEN

            v_failures := array_append(
                v_failures,
                'error_rate_threshold'
            );
        END IF;

        IF (
            v_candidate.errors::NUMERIC /
            v_candidate.requests
        ) - (
            v_baseline.errors::NUMERIC /
            GREATEST(v_baseline.requests, 1)
        ) > v_policy.maximum_error_regression THEN

            v_failures := array_append(
                v_failures,
                'baseline_regression'
            );
        END IF;
    END IF;

    IF v_candidate.p95_latency_ms >
       v_policy.maximum_p95_latency_ms THEN

        v_failures := array_append(
            v_failures,
            'latency_threshold'
        );
    END IF;

    INSERT INTO deployment_checks(
        deployment_id,
        metric_id,
        check_name,
        status,
        measured_value,
        threshold_value,
        failure_reason
    )
    VALUES
    (
        p_deployment_id,
        p_metric_id,
        'error_rate',
        CASE
            WHEN 'error_rate_threshold' = ANY(v_failures)
                THEN 'failed'::check_state
            WHEN v_candidate.requests = 0
                THEN 'failed'::check_state
            ELSE 'passed'::check_state
        END,
        CASE
            WHEN v_candidate.requests > 0
                THEN v_candidate.errors::NUMERIC /
                     v_candidate.requests
            ELSE NULL
        END,
        v_policy.maximum_error_rate,
        CASE
            WHEN 'error_rate_threshold' = ANY(v_failures)
                THEN 'Error rate exceeded policy'
            ELSE NULL
        END
    ),
    (
        p_deployment_id,
        p_metric_id,
        'p95_latency',
        CASE
            WHEN 'latency_threshold' = ANY(v_failures)
                THEN 'failed'::check_state
            ELSE 'passed'::check_state
        END,
        v_candidate.p95_latency_ms,
        v_policy.maximum_p95_latency_ms,
        CASE
            WHEN 'latency_threshold' = ANY(v_failures)
                THEN 'Latency exceeded policy'
            ELSE NULL
        END
    ),
    (
        p_deployment_id,
        p_metric_id,
        'minimum_sample',
        CASE
            WHEN 'insufficient_requests' = ANY(v_failures)
                THEN 'failed'::check_state
            ELSE 'passed'::check_state
        END,
        v_candidate.requests,
        v_policy.minimum_requests,
        CASE
            WHEN 'insufficient_requests' = ANY(v_failures)
                THEN 'Insufficient observations'
            ELSE NULL
        END
    );

    RETURN QUERY SELECT
        cardinality(v_failures) = 0,
        v_failures;
END;
$$;

-- ------------------------------------------------------------
-- MERGE-ELIGIBILITY STYLE RELEASE GATE
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION can_promote_deployment(
    p_deployment_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reasons TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment deployments%ROWTYPE;
    v_policy release_policies%ROWTYPE;
    v_latest_metric deployment_metrics%ROWTYPE;
    v_failures TEXT[] := ARRAY[]::TEXT[];
    v_required_approvals INTEGER;
    v_approved_count INTEGER;
BEGIN
    SELECT *
    INTO v_deployment
    FROM deployments
    WHERE deployment_id = p_deployment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown deployment';
    END IF;

    SELECT *
    INTO v_policy
    FROM release_policies
    WHERE policy_id = v_deployment.policy_id;

    IF v_deployment.state <> 'running' THEN
        v_failures := array_append(
            v_failures,
            'deployment_not_running'
        );
    END IF;

    SELECT *
    INTO v_latest_metric
    FROM deployment_metrics
    WHERE deployment_id = p_deployment_id
      AND observation_type = 'canary'
    ORDER BY observed_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
        v_failures := array_append(
            v_failures,
            'missing_canary_metrics'
        );
    ELSE
        IF NOT EXISTS (
            SELECT 1
            FROM deployment_checks
            WHERE deployment_id = p_deployment_id
              AND metric_id = v_latest_metric.metric_id
              AND status = 'failed'
        ) THEN
            NULL;
        ELSE
            v_failures := array_append(
                v_failures,
                'failed_health_checks'
            );
        END IF;
    END IF;

    IF v_policy.manual_approval_required THEN
        SELECT COUNT(*)
        INTO v_required_approvals
        FROM (
            VALUES ('release'::VARCHAR),
                   ('security'::VARCHAR)
        ) AS required_types(approval_type);

        SELECT COUNT(DISTINCT approval_type)
        INTO v_approved_count
        FROM deployment_approvals
        WHERE deployment_id = p_deployment_id
          AND approved = TRUE
          AND approval_type IN ('release', 'security');

        IF v_approved_count < v_required_approvals THEN
            v_failures := array_append(
                v_failures,
                'required_approvals_missing'
            );
        END IF;

        IF EXISTS (
            SELECT 1
            FROM deployment_approvals
            WHERE deployment_id = p_deployment_id
              AND approved = FALSE
              AND approval_type IN ('release', 'security')
        ) THEN
            v_failures := array_append(
                v_failures,
                'approval_rejected'
            );
        END IF;
    END IF;

    RETURN QUERY SELECT
        cardinality(v_failures) = 0,
        v_failures;
END;
$$;

-- ------------------------------------------------------------
-- CONTROLLED TRAFFIC ADVANCEMENT
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE advance_canary(
    p_deployment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment deployments%ROWTYPE;
    v_policy release_policies%ROWTYPE;
    v_next_stage INTEGER;
    v_metric deployment_metrics%ROWTYPE;
    v_gate RECORD;
BEGIN
    SELECT *
    INTO v_deployment
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND OR v_deployment.state <> 'running' THEN
        RAISE EXCEPTION 'Deployment cannot advance';
    END IF;

    SELECT *
    INTO v_policy
    FROM release_policies
    WHERE policy_id = v_deployment.policy_id
      AND enabled = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active policy required';
    END IF;

    SELECT *
    INTO v_metric
    FROM deployment_metrics
    WHERE deployment_id = p_deployment_id
      AND observation_type = 'canary'
    ORDER BY observed_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Canary observations are required';
    END IF;

    SELECT *
    INTO v_gate
    FROM evaluate_canary_health(
        p_deployment_id,
        v_metric.metric_id
    );

    IF NOT v_gate.permitted THEN
        UPDATE deployments
        SET state = 'rolled_back',
            traffic_percent = 0,
            consecutive_passes = 0
        WHERE deployment_id = p_deployment_id;

        INSERT INTO deployment_events(
            deployment_id,
            event_type,
            event_details
        )
        VALUES (
            p_deployment_id,
            'rolled_back',
            jsonb_build_object(
                'reason', v_gate.failure_reasons
            )
        );

        RETURN;
    END IF;

    UPDATE deployments
    SET consecutive_passes = consecutive_passes + 1
    WHERE deployment_id = p_deployment_id
    RETURNING * INTO v_deployment;

    IF v_deployment.consecutive_passes <
       v_policy.required_consecutive_passes THEN
        RETURN;
    END IF;

    SELECT traffic_percent
    INTO v_next_stage
    FROM policy_traffic_stages
    WHERE policy_id = v_policy.policy_id
      AND stage_order > v_deployment.current_stage_order
    ORDER BY stage_order
    LIMIT 1;

    IF v_next_stage IS NULL THEN
        RAISE EXCEPTION 'No further traffic stage exists';
    END IF;

    IF v_next_stage = 100 THEN
        SELECT *
        INTO v_gate
        FROM can_promote_deployment(p_deployment_id);

        IF NOT v_gate.eligible THEN
            RAISE EXCEPTION
                'Promotion blocked: %',
                v_gate.reasons;
        END IF;

        UPDATE deployments
        SET state = 'promoted',
            traffic_percent = 100,
            consecutive_passes = 0,
            current_stage_order = (
                SELECT MAX(stage_order)
                FROM policy_traffic_stages
                WHERE policy_id = v_policy.policy_id
            )
        WHERE deployment_id = p_deployment_id;

    ELSE
        UPDATE deployments
        SET traffic_percent = v_next_stage,
            current_stage_order = (
                SELECT stage_order
                FROM policy_traffic_stages
                WHERE policy_id = v_policy.policy_id
                  AND traffic_percent = v_next_stage
            ),
            consecutive_passes = 0
        WHERE deployment_id = p_deployment_id;

        INSERT INTO deployment_events(
            deployment_id,
            event_type,
            event_details
        )
        VALUES (
            p_deployment_id,
            'traffic_increased',
            jsonb_build_object(
                'traffic_percent',
                v_next_stage
            )
        );
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- CURRENT PRODUCTION RELEASE VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW active_production_releases AS
SELECT
    a.application_name,
    av.version,
    e.region,
    d.traffic_percent,
    d.state,
    d.started_at,
    d.deployment_id
FROM deployments d
JOIN applications a USING (application_id)
JOIN application_versions av USING (version_id)
JOIN environments e USING (environment_id)
WHERE e.environment_name = 'production'
  AND d.state IN ('running', 'promoted');

-- ------------------------------------------------------------
-- RELEASE HEALTH REPORT
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW deployment_health_report AS
SELECT
    d.deployment_id,
    a.application_name,
    av.version,
    d.state,
    d.traffic_percent,
    COUNT(m.metric_id) AS observation_count,
    COALESCE(SUM(m.requests), 0) AS total_requests,
    COALESCE(SUM(m.errors), 0) AS total_errors,
    CASE
        WHEN SUM(m.requests) > 0
        THEN ROUND(
            SUM(m.errors)::NUMERIC /
            SUM(m.requests),
            6
        )
        ELSE NULL
    END AS weighted_error_rate,
    MAX(m.p95_latency_ms) AS maximum_observed_p95_latency
FROM deployments d
JOIN applications a USING (application_id)
JOIN application_versions av USING (version_id)
LEFT JOIN deployment_metrics m
    ON m.deployment_id = d.deployment_id
   AND m.observation_type = 'canary'
GROUP BY
    d.deployment_id,
    a.application_name,
    av.version,
    d.state,
    d.traffic_percent;

-- ------------------------------------------------------------
-- SAMPLE APPLICATIONS AND VERSIONS
-- ------------------------------------------------------------

INSERT INTO applications(
    application_name,
    owning_team
)
VALUES
    ('payment-service', 'Payments Engineering'),
    ('inventory-service', 'Platform Engineering');

INSERT INTO application_versions(
    application_id,
    version,
    artifact_digest
)
SELECT
    application_id,
    'v1.0.0',
    'sha256:baseline-' || application_name
FROM applications;

INSERT INTO application_versions(
    application_id,
    version,
    artifact_digest
)
SELECT
    application_id,
    'v2.0.0',
    'sha256:candidate-' || application_name
FROM applications;

INSERT INTO application_versions(
    application_id,
    version,
    artifact_digest
)
SELECT
    application_id,
    'v3.0.0',
    'sha256:failed-' || application_name
FROM applications;

INSERT INTO environments(environment_name, region)
VALUES
    ('staging', 'ap-south-1'),
    ('production', 'ap-south-1'),
    ('production', 'eu-west-1');

INSERT INTO deployment_actors(actor_name, actor_role)
VALUES
    ('release.operator', 'release_engineer'),
    ('sre.operator', 'site_reliability_engineer'),
    ('security.reviewer', 'security_reviewer'),
    ('deployment.pipeline', 'automation');

INSERT INTO release_policies(
    policy_name,
    maximum_error_rate,
    maximum_p95_latency_ms,
    maximum_error_regression,
    minimum_requests,
    required_consecutive_passes,
    manual_approval_required
)
VALUES
    ('production-standard', 0.020000, 500, 0.015000, 100, 1, FALSE),
    ('production-controlled', 0.010000, 350, 0.005000, 500, 2, TRUE);

INSERT INTO policy_traffic_stages(
    policy_id,
    stage_order,
    traffic_percent
)
SELECT
    policy_id,
    stage_order,
    traffic_percent
FROM release_policies
CROSS JOIN (
    VALUES
        (1, 5),
        (2, 10),
        (3, 25),
        (4, 50),
        (5, 100)
) AS stages(stage_order, traffic_percent);

-- ------------------------------------------------------------
-- SAMPLE RELEASE CREATION
-- ------------------------------------------------------------

INSERT INTO deployments(
    release_key,
    application_id,
    version_id,
    previous_version_id,
    environment_id,
    policy_id,
    initiated_by
)
SELECT
    '10000000-0000-0000-0000-000000000001'::UUID,
    a.application_id,
    candidate.version_id,
    baseline.version_id,
    e.environment_id,
    p.policy_id,
    actor.actor_id
FROM applications a
JOIN application_versions candidate
    ON candidate.application_id = a.application_id
   AND candidate.version = 'v2.0.0'
JOIN application_versions baseline
    ON baseline.application_id = a.application_id
   AND baseline.version = 'v1.0.0'
JOIN environments e
    ON e.environment_name = 'production'
   AND e.region = 'ap-south-1'
JOIN release_policies p
    ON p.policy_name = 'production-standard'
CROSS JOIN deployment_actors actor
WHERE a.application_name = 'payment-service'
  AND actor.actor_name = 'release.operator';

-- Baseline observations are stored separately from canary samples.
INSERT INTO deployment_metrics(
    deployment_id,
    observation_type,
    requests,
    errors,
    p95_latency_ms
)
SELECT
    deployment_id,
    'baseline',
    5000,
    50,
    180
FROM deployments
WHERE release_key =
    '10000000-0000-0000-0000-000000000001';

-- ------------------------------------------------------------
-- TRANSACTIONAL CANARY WORKFLOW
-- ------------------------------------------------------------

DO $$
DECLARE
    v_deployment_id BIGINT;
    v_metric_id BIGINT;
BEGIN
    SELECT deployment_id
    INTO v_deployment_id
    FROM deployments
    WHERE release_key =
        '10000000-0000-0000-0000-000000000001';

    UPDATE deployments
    SET state = 'running',
        traffic_percent = 5,
        current_stage_order = 1
    WHERE deployment_id = v_deployment_id;

    INSERT INTO deployment_metrics(
        deployment_id,
        observation_type,
        requests,
        errors,
        p95_latency_ms
    )
    VALUES (
        v_deployment_id,
        'canary',
        1000,
        12,
        210
    )
    RETURNING metric_id INTO v_metric_id;

    CALL advance_canary(v_deployment_id);
END;
$$;

-- ------------------------------------------------------------
-- REPORTING AND EVALUATION QUERIES
-- ------------------------------------------------------------

-- Current releases.
SELECT *
FROM active_production_releases
ORDER BY application_name, region;

-- Health aggregation.
SELECT *
FROM deployment_health_report
ORDER BY deployment_id;

-- Failed automated checks.
SELECT
    d.deployment_id,
    c.check_name,
    c.measured_value,
    c.threshold_value,
    c.failure_reason
FROM deployment_checks c
JOIN deployments d USING (deployment_id)
WHERE c.status IN ('failed', 'error')
ORDER BY c.evaluated_at DESC;

-- Traffic distribution by environment and application.
SELECT
    a.application_name,
    e.environment_name,
    e.region,
    SUM(d.traffic_percent) AS allocated_percentage,
    COUNT(*) AS deployment_count
FROM deployments d
JOIN applications a USING (application_id)
JOIN environments e USING (environment_id)
WHERE d.state = 'running'
GROUP BY
    a.application_name,
    e.environment_name,
    e.region;

-- Audit history.
SELECT
    d.deployment_id,
    ev.event_type,
    ev.event_details,
    ev.created_at
FROM deployment_events ev
JOIN deployments d USING (deployment_id)
ORDER BY ev.created_at DESC;

-- Policy configuration.
SELECT
    p.policy_name,
    s.stage_order,
    s.traffic_percent
FROM release_policies p
JOIN policy_traffic_stages s USING (policy_id)
ORDER BY p.policy_name, s.stage_order;

-- Validation: active deployments without recent canary metrics.
SELECT d.deployment_id
FROM deployments d
WHERE d.state = 'running'
  AND NOT EXISTS (
      SELECT 1
      FROM deployment_metrics m
      WHERE m.deployment_id = d.deployment_id
        AND m.observation_type = 'canary'
        AND m.observed_at >= now() - INTERVAL '15 minutes'
  );

-- ------------------------------------------------------------
-- EXPLICIT FAILURE SCENARIO
-- ------------------------------------------------------------

-- A high-error observation must fail the health gate.
DO $$
DECLARE
    v_deployment_id BIGINT;
    v_metric_id BIGINT;
    v_result RECORD;
BEGIN
    SELECT deployment_id
    INTO v_deployment_id
    FROM deployments
    WHERE release_key =
        '10000000-0000-0000-0000-000000000001';

    INSERT INTO deployment_metrics(
        deployment_id,
        observation_type,
        requests,
        errors,
        p95_latency_ms
    )
    VALUES (
        v_deployment_id,
        'canary',
        1000,
        200,
        900
    )
    RETURNING metric_id INTO v_metric_id;

    SELECT *
    INTO v_result
    FROM evaluate_canary_health(
        v_deployment_id,
        v_metric_id
    );

    IF v_result.permitted THEN
        RAISE EXCEPTION
            'Failure scenario was incorrectly accepted';
    END IF;

    RAISE NOTICE
        'Failure correctly detected: %',
        v_result.failure_reasons;
END;
$$;

COMMIT;

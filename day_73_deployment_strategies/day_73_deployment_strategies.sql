/*
 * PostgreSQL Deployment Strategy Management System
 *
 * PostgreSQL 15+
 *
 * Models:
 *   - Applications and environments
 *   - Deployment strategies
 *   - Application releases
 *   - Infrastructure instances
 *   - Deployment executions
 *   - Rolling deployment batches
 *   - Blue-green environments
 *   - Traffic allocations
 *   - Health checks
 *   - Deployment policies
 *   - Rollbacks
 *   - Deployment events
 *
 * Run as a database owner in a development database.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS deployment;

SET search_path TO deployment, public;

-- =========================================================
-- 1. ENUM TYPES
-- =========================================================

CREATE TYPE deployment_strategy AS ENUM (
    'recreate',
    'rolling',
    'blue_green'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'provisioning',
    'validating',
    'switching',
    'succeeded',
    'failed',
    'rolled_back'
);

CREATE TYPE instance_status AS ENUM (
    'starting',
    'healthy',
    'unhealthy',
    'stopped'
);

CREATE TYPE environment_color AS ENUM (
    'blue',
    'green',
    'standard'
);

CREATE TYPE health_status AS ENUM (
    'passed',
    'failed',
    'warning'
);

-- =========================================================
-- 2. APPLICATIONS
-- =========================================================

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_name VARCHAR(120) NOT NULL UNIQUE,

    description TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (length(trim(application_name)) > 0)
);

-- =========================================================
-- 3. ENVIRONMENTS
-- =========================================================

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    environment_name VARCHAR(80) NOT NULL,

    environment_type environment_color NOT NULL
        DEFAULT 'standard',

    is_production BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (application_id, environment_name)
);

-- =========================================================
-- 4. RELEASES
-- =========================================================

CREATE TABLE releases (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    version VARCHAR(80) NOT NULL,

    artifact_digest VARCHAR(128) NOT NULL,

    artifact_uri TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (application_id, version),

    CHECK (length(trim(version)) > 0),

    CHECK (
        artifact_digest ~ '^[a-fA-F0-9]{64}$'
    ),

    CHECK (
        artifact_uri ~ '^https://'
    )
);

CREATE INDEX idx_releases_application
    ON releases(application_id, created_at DESC);

-- =========================================================
-- 5. DEPLOYMENT POLICIES
-- =========================================================

CREATE TABLE deployment_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    strategy deployment_strategy NOT NULL,

    max_capacity INTEGER NOT NULL,

    max_surge INTEGER NOT NULL DEFAULT 1,

    max_unavailable INTEGER NOT NULL DEFAULT 1,

    batch_size INTEGER NOT NULL DEFAULT 1,

    min_healthy_percent NUMERIC(5,2) NOT NULL DEFAULT 100,

    allow_recreate BOOLEAN NOT NULL DEFAULT TRUE,

    allow_blue_green BOOLEAN NOT NULL DEFAULT TRUE,

    allow_rollback BOOLEAN NOT NULL DEFAULT TRUE,

    require_health_checks BOOLEAN NOT NULL DEFAULT TRUE,

    require_manual_approval BOOLEAN NOT NULL DEFAULT FALSE,

    allow_production_deployment BOOLEAN NOT NULL DEFAULT TRUE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (environment_id, strategy),

    CHECK (max_capacity >= 1),

    CHECK (max_surge >= 0),

    CHECK (max_unavailable >= 0),

    CHECK (batch_size >= 1),

    CHECK (
        max_surge + max_unavailable >= 1
    ),

    CHECK (
        min_healthy_percent > 0
        AND min_healthy_percent <= 100
    )
);

-- =========================================================
-- 6. DEPLOYMENT EXECUTIONS
-- =========================================================

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    release_id BIGINT NOT NULL
        REFERENCES releases(release_id),

    policy_id BIGINT NOT NULL
        REFERENCES deployment_policies(policy_id),

    strategy deployment_strategy NOT NULL,

    status deployment_status NOT NULL DEFAULT 'pending',

    previous_release_id BIGINT
        REFERENCES releases(release_id),

    requested_replicas INTEGER NOT NULL,

    started_by VARCHAR(120) NOT NULL,

    error_message TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (requested_replicas >= 1),

    CHECK (length(trim(started_by)) > 0),

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_deployments_environment_status
    ON deployments(environment_id, status, started_at DESC);

CREATE INDEX idx_deployments_release
    ON deployments(release_id);

CREATE INDEX idx_deployments_active
    ON deployments(environment_id, started_at DESC)
    WHERE status IN (
        'pending',
        'provisioning',
        'validating',
        'switching'
    );

-- Only one unfinished deployment per environment.
CREATE UNIQUE INDEX uq_active_environment_deployment
    ON deployments(environment_id)
    WHERE status IN (
        'pending',
        'provisioning',
        'validating',
        'switching'
    );

-- =========================================================
-- 7. INFRASTRUCTURE INSTANCES
-- =========================================================

CREATE TABLE deployment_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    release_id BIGINT NOT NULL
        REFERENCES releases(release_id),

    deployment_id BIGINT
        REFERENCES deployments(deployment_id),

    instance_name VARCHAR(120) NOT NULL UNIQUE,

    color environment_color NOT NULL DEFAULT 'standard',

    status instance_status NOT NULL DEFAULT 'starting',

    started_at TIMESTAMPTZ,

    stopped_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        stopped_at IS NULL
        OR started_at IS NULL
        OR stopped_at >= started_at
    )
);

CREATE INDEX idx_instances_environment_status
    ON deployment_instances(environment_id, status);

CREATE INDEX idx_instances_release
    ON deployment_instances(release_id);

-- =========================================================
-- 8. ROLLING DEPLOYMENT BATCHES
-- =========================================================

CREATE TABLE deployment_batches (
    batch_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,

    batch_number INTEGER NOT NULL,

    planned_instances INTEGER NOT NULL,

    completed_instances INTEGER NOT NULL DEFAULT 0,

    healthy_instances INTEGER NOT NULL DEFAULT 0,

    status deployment_status NOT NULL DEFAULT 'pending',

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    UNIQUE (deployment_id, batch_number),

    CHECK (batch_number >= 1),

    CHECK (planned_instances >= 1),

    CHECK (completed_instances >= 0),

    CHECK (completed_instances <= planned_instances),

    CHECK (healthy_instances >= 0),

    CHECK (healthy_instances <= completed_instances)
);

-- =========================================================
-- 9. HEALTH CHECKS
-- =========================================================

CREATE TABLE deployment_health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,

    batch_id BIGINT
        REFERENCES deployment_batches(batch_id),

    instance_id BIGINT
        REFERENCES deployment_instances(instance_id),

    check_name VARCHAR(120) NOT NULL,

    check_status health_status NOT NULL,

    response_time_ms NUMERIC(12,3),

    error_rate NUMERIC(7,4),

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        response_time_ms IS NULL
        OR response_time_ms >= 0
    ),

    CHECK (
        error_rate IS NULL
        OR (error_rate >= 0 AND error_rate <= 100)
    )
);

CREATE INDEX idx_health_checks_deployment
    ON deployment_health_checks(
        deployment_id,
        checked_at DESC
    );

CREATE INDEX idx_health_checks_failed
    ON deployment_health_checks(deployment_id)
    WHERE check_status = 'failed';

-- =========================================================
-- 10. TRAFFIC ALLOCATION
-- =========================================================

CREATE TABLE traffic_allocations (
    allocation_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    release_id BIGINT NOT NULL
        REFERENCES releases(release_id),

    traffic_percent NUMERIC(5,2) NOT NULL,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    effective_until TIMESTAMPTZ,

    CHECK (
        traffic_percent >= 0
        AND traffic_percent <= 100
    ),

    CHECK (
        effective_until IS NULL
        OR effective_until > effective_from
    )
);

CREATE INDEX idx_traffic_active
    ON traffic_allocations(environment_id, active)
    WHERE active = TRUE;

-- =========================================================
-- 11. DEPLOYMENT EVENTS
-- =========================================================

CREATE TABLE deployment_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployment_events
    ON deployment_events(deployment_id, created_at);

-- =========================================================
-- 12. AUDIT FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION record_deployment_event(
    p_deployment_id BIGINT,
    p_event_type VARCHAR,
    p_details JSONB DEFAULT '{}'::JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        event_details
    )
    VALUES (
        p_deployment_id,
        p_event_type,
        COALESCE(p_details, '{}'::JSONB)
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;

-- =========================================================
-- 13. DEPLOYMENT STATUS VALIDATION
-- =========================================================

CREATE OR REPLACE FUNCTION validate_deployment_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status = 'succeeded'
       AND NEW.status NOT IN ('rolled_back') THEN
        RAISE EXCEPTION
            'Successful deployment cannot transition to %',
            NEW.status;
    END IF;

    IF OLD.status IN ('failed', 'rolled_back') THEN
        RAISE EXCEPTION
            'Terminal deployment cannot transition from %',
            OLD.status;
    END IF;

    IF OLD.status = 'pending'
       AND NEW.status NOT IN ('provisioning', 'failed') THEN
        RAISE EXCEPTION
            'Invalid transition from pending to %',
            NEW.status;
    END IF;

    IF OLD.status = 'provisioning'
       AND NEW.status NOT IN (
           'validating',
           'switching',
           'failed'
       ) THEN
        RAISE EXCEPTION
            'Invalid transition from provisioning to %',
            NEW.status;
    END IF;

    IF OLD.status = 'validating'
       AND NEW.status NOT IN (
           'switching',
           'succeeded',
           'failed'
       ) THEN
        RAISE EXCEPTION
            'Invalid transition from validating to %',
            NEW.status;
    END IF;

    IF OLD.status = 'switching'
       AND NEW.status NOT IN ('succeeded', 'failed') THEN
        RAISE EXCEPTION
            'Invalid transition from switching to %',
            NEW.status;
    END IF;

    IF NEW.status IN (
        'succeeded',
        'failed',
        'rolled_back'
    ) THEN
        NEW.completed_at := COALESCE(
            NEW.completed_at,
            NOW()
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_status_transition
BEFORE UPDATE OF status
ON deployments
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_transition();

-- =========================================================
-- 14. RELEASE APPLICATION CONSISTENCY
-- =========================================================

CREATE OR REPLACE FUNCTION validate_deployment_release()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_release_application BIGINT;
    v_environment_application BIGINT;
    v_policy_environment BIGINT;
    v_policy_strategy deployment_strategy;
BEGIN
    SELECT application_id
    INTO v_release_application
    FROM releases
    WHERE release_id = NEW.release_id;

    SELECT application_id
    INTO v_environment_application
    FROM environments
    WHERE environment_id = NEW.environment_id;

    SELECT environment_id, strategy
    INTO v_policy_environment, v_policy_strategy
    FROM deployment_policies
    WHERE policy_id = NEW.policy_id;

    IF v_release_application IS DISTINCT FROM
       v_environment_application THEN
        RAISE EXCEPTION
            'Release and environment belong to different applications';
    END IF;

    IF v_policy_environment IS DISTINCT FROM
       NEW.environment_id THEN
        RAISE EXCEPTION
            'Policy belongs to another environment';
    END IF;

    IF v_policy_strategy IS DISTINCT FROM NEW.strategy THEN
        RAISE EXCEPTION
            'Deployment strategy does not match policy';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_deployment_release
BEFORE INSERT OR UPDATE
ON deployments
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_release();

-- =========================================================
-- 15. DEPLOYMENT ELIGIBILITY FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION check_deployment_eligibility(
    p_deployment_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    d deployments%ROWTYPE;
    p deployment_policies%ROWTYPE;

    v_environment environments%ROWTYPE;

    v_healthy BIGINT;
    v_total BIGINT;
    v_previous_active BIGINT;
    v_failed_checks BIGINT;
    v_current_count BIGINT;
    v_active_traffic NUMERIC;
BEGIN
    SELECT *
    INTO d
    FROM deployments
    WHERE deployment_id = p_deployment_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Deployment does not exist';
        RETURN;
    END IF;

    SELECT *
    INTO p
    FROM deployment_policies
    WHERE policy_id = d.policy_id;

    SELECT *
    INTO v_environment
    FROM environments
    WHERE environment_id = d.environment_id;

    IF NOT p.enabled THEN
        RETURN QUERY SELECT FALSE, 'Deployment policy disabled';
        RETURN;
    END IF;

    IF d.requested_replicas > p.max_capacity THEN
        RETURN QUERY SELECT FALSE, 'Requested capacity exceeded';
        RETURN;
    END IF;

    IF v_environment.is_production
       AND NOT p.allow_production_deployment THEN
        RETURN QUERY SELECT FALSE, 'Production deployment prohibited';
        RETURN;
    END IF;

    IF d.strategy = 'recreate' AND NOT p.allow_recreate THEN
        RETURN QUERY SELECT FALSE, 'Recreate strategy prohibited';
        RETURN;
    END IF;

    IF d.strategy = 'blue_green' AND NOT p.allow_blue_green THEN
        RETURN QUERY SELECT FALSE, 'Blue-green strategy prohibited';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_current_count
    FROM deployment_instances
    WHERE environment_id = d.environment_id
      AND status IN ('starting', 'healthy', 'unhealthy');

    IF d.strategy = 'blue_green'
       AND v_current_count + d.requested_replicas >
           p.max_capacity THEN
        RETURN QUERY SELECT FALSE, 'Insufficient blue-green capacity';
        RETURN;
    END IF;

    IF p.require_health_checks THEN

        SELECT COUNT(*)
        INTO v_failed_checks
        FROM deployment_health_checks
        WHERE deployment_id = p_deployment_id
          AND check_status = 'failed';

        IF v_failed_checks > 0 THEN
            RETURN QUERY SELECT FALSE, 'Failed health checks exist';
            RETURN;
        END IF;

        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE check_status = 'passed'
            )
        INTO v_total, v_healthy
        FROM deployment_health_checks
        WHERE deployment_id = p_deployment_id;

        IF v_total = 0 THEN
            RETURN QUERY SELECT FALSE, 'No health checks recorded';
            RETURN;
        END IF;

        IF v_healthy::NUMERIC / v_total::NUMERIC <
            p.min_healthy_percent / 100 THEN
            RETURN QUERY SELECT FALSE, 'Health threshold not satisfied';
            RETURN;
        END IF;
    END IF;

    SELECT COUNT(*)
    INTO v_previous_active
    FROM deployments
    WHERE environment_id = d.environment_id
      AND deployment_id <> p_deployment_id
      AND status IN (
          'pending',
          'provisioning',
          'validating',
          'switching'
      );

    IF v_previous_active > 0 THEN
        RETURN QUERY SELECT FALSE, 'Another deployment is active';
        RETURN;
    END IF;

    SELECT COALESCE(SUM(traffic_percent), 0)
    INTO v_active_traffic
    FROM traffic_allocations
    WHERE environment_id = d.environment_id
      AND active = TRUE;

    IF v_active_traffic > 100 THEN
        RETURN QUERY SELECT FALSE, 'Traffic allocation exceeds 100%';
        RETURN;
    END IF;

    RETURN QUERY SELECT TRUE, 'Deployment policy satisfied';
END;
$$;

-- =========================================================
-- 16. CONTROLLED TRAFFIC SWITCH PROCEDURE
-- =========================================================

CREATE OR REPLACE PROCEDURE switch_deployment_traffic(
    p_deployment_id BIGINT,
    p_traffic_percent NUMERIC
)
LANGUAGE plpgsql
AS $$
DECLARE
    d deployments%ROWTYPE;
    v_eligibility RECORD;
BEGIN
    IF p_traffic_percent < 0 OR p_traffic_percent > 100 THEN
        RAISE EXCEPTION 'Invalid traffic percentage';
    END IF;

    SELECT *
    INTO d
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    IF d.status NOT IN ('validating', 'switching') THEN
        RAISE EXCEPTION
            'Deployment must be validating or switching';
    END IF;

    SELECT *
    INTO v_eligibility
    FROM check_deployment_eligibility(p_deployment_id);

    IF NOT v_eligibility.eligible THEN
        RAISE EXCEPTION
            'Deployment not eligible: %',
            v_eligibility.reason;
    END IF;

    UPDATE deployments
    SET status = 'switching'
    WHERE deployment_id = p_deployment_id
      AND status = 'validating';

    UPDATE traffic_allocations
    SET
        active = FALSE,
        effective_until = NOW()
    WHERE environment_id = d.environment_id
      AND active = TRUE;

    INSERT INTO traffic_allocations (
        environment_id,
        deployment_id,
        release_id,
        traffic_percent,
        active
    )
    VALUES (
        d.environment_id,
        d.deployment_id,
        d.release_id,
        p_traffic_percent,
        TRUE
    );

    PERFORM record_deployment_event(
        p_deployment_id,
        'TRAFFIC_SWITCHED',
        jsonb_build_object(
            'traffic_percent', p_traffic_percent
        )
    );
END;
$$;

-- =========================================================
-- 17. REPORTING VIEWS
-- =========================================================

CREATE OR REPLACE VIEW deployment_summary AS
SELECT
    d.deployment_id,
    a.application_name,
    e.environment_name,
    r.version,
    d.strategy,
    d.status,
    d.requested_replicas,
    d.started_by,
    d.started_at,
    d.completed_at,
    d.error_message,
    EXTRACT(
        EPOCH FROM (d.completed_at - d.started_at)
    ) AS duration_seconds
FROM deployments d
JOIN applications a
    ON a.application_id = d.application_id
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN releases r
    ON r.release_id = d.release_id;

CREATE OR REPLACE VIEW environment_instance_summary AS
SELECT
    e.environment_id,
    e.environment_name,
    a.application_name,
    COUNT(i.instance_id) FILTER (
        WHERE i.status = 'healthy'
    ) AS healthy_instances,
    COUNT(i.instance_id) FILTER (
        WHERE i.status = 'unhealthy'
    ) AS unhealthy_instances,
    COUNT(i.instance_id) AS total_instances
FROM environments e
JOIN applications a
    ON a.application_id = e.application_id
LEFT JOIN deployment_instances i
    ON i.environment_id = e.environment_id
GROUP BY
    e.environment_id,
    e.environment_name,
    a.application_name;

CREATE OR REPLACE VIEW deployment_success_metrics AS
SELECT
    application_id,
    environment_id,
    strategy,
    COUNT(*) AS total_deployments,
    COUNT(*) FILTER (
        WHERE status = 'succeeded'
    ) AS successful_deployments,
    COUNT(*) FILTER (
        WHERE status = 'failed'
    ) AS failed_deployments,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE status = 'succeeded'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_percentage
FROM deployments
GROUP BY
    application_id,
    environment_id,
    strategy;

-- =========================================================
-- 18. SAMPLE APPLICATIONS
-- =========================================================

INSERT INTO applications (
    application_name,
    description
)
VALUES
    (
        'payment-api',
        'Payment transaction processing service'
    ),
    (
        'inventory-api',
        'Inventory and stock management service'
    );

INSERT INTO environments (
    application_id,
    environment_name,
    environment_type,
    is_production
)
SELECT
    application_id,
    'production',
    'blue',
    TRUE
FROM applications
WHERE application_name = 'payment-api';

INSERT INTO environments (
    application_id,
    environment_name,
    environment_type,
    is_production
)
SELECT
    application_id,
    'staging',
    'standard',
    FALSE
FROM applications
WHERE application_name = 'payment-api';

INSERT INTO environments (
    application_id,
    environment_name,
    environment_type,
    is_production
)
SELECT
    application_id,
    'production',
    'blue',
    TRUE
FROM applications
WHERE application_name = 'inventory-api';

-- =========================================================
-- 19. SAMPLE RELEASES
-- =========================================================

INSERT INTO releases (
    application_id,
    version,
    artifact_digest,
    artifact_uri
)
SELECT
    application_id,
    '1.0.0',
    repeat('a', 64),
    'https://artifacts.example.com/payment/1.0.0'
FROM applications
WHERE application_name = 'payment-api';

INSERT INTO releases (
    application_id,
    version,
    artifact_digest,
    artifact_uri
)
SELECT
    application_id,
    '1.1.0',
    repeat('b', 64),
    'https://artifacts.example.com/payment/1.1.0'
FROM applications
WHERE application_name = 'payment-api';

INSERT INTO releases (
    application_id,
    version,
    artifact_digest,
    artifact_uri
)
SELECT
    application_id,
    '1.2.0',
    repeat('c', 64),
    'https://artifacts.example.com/payment/1.2.0'
FROM applications
WHERE application_name = 'payment-api';

INSERT INTO releases (
    application_id,
    version,
    artifact_digest,
    artifact_uri
)
SELECT
    application_id,
    '2.0.0',
    repeat('d', 64),
    'https://artifacts.example.com/inventory/2.0.0'
FROM applications
WHERE application_name = 'inventory-api';

-- =========================================================
-- 20. SAMPLE POLICIES
-- =========================================================

INSERT INTO deployment_policies (
    environment_id,
    strategy,
    max_capacity,
    max_surge,
    max_unavailable,
    batch_size,
    min_healthy_percent,
    allow_recreate,
    allow_blue_green,
    allow_rollback,
    require_health_checks,
    require_manual_approval,
    allow_production_deployment
)
SELECT
    e.environment_id,
    strategy.strategy,
    12,
    1,
    1,
    1,
    100,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    TRUE
FROM environments e
CROSS JOIN (
    VALUES
        ('recreate'::deployment_strategy),
        ('rolling'::deployment_strategy),
        ('blue_green'::deployment_strategy)
) AS strategy(strategy)
WHERE e.environment_name = 'production';

INSERT INTO deployment_policies (
    environment_id,
    strategy,
    max_capacity,
    max_surge,
    max_unavailable,
    batch_size,
    min_healthy_percent,
    allow_recreate,
    allow_blue_green,
    allow_rollback,
    require_health_checks
)
SELECT
    e.environment_id,
    strategy.strategy,
    10,
    1,
    1,
    1,
    100,
    TRUE,
    TRUE,
    TRUE,
    TRUE
FROM environments e
CROSS JOIN (
    VALUES
        ('recreate'::deployment_strategy),
        ('rolling'::deployment_strategy),
        ('blue_green'::deployment_strategy)
) AS strategy(strategy)
WHERE e.environment_name = 'staging';

-- =========================================================
-- 21. INITIAL DEPLOYMENT
-- =========================================================

INSERT INTO deployments (
    application_id,
    environment_id,
    release_id,
    policy_id,
    strategy,
    status,
    requested_replicas,
    started_by
)
SELECT
    a.application_id,
    e.environment_id,
    r.release_id,
    p.policy_id,
    'rolling',
    'pending',
    4,
    'deployment-admin'
FROM applications a
JOIN environments e
    ON e.application_id = a.application_id
JOIN releases r
    ON r.application_id = a.application_id
JOIN deployment_policies p
    ON p.environment_id = e.environment_id
   AND p.strategy = 'rolling'
WHERE a.application_name = 'payment-api'
  AND e.environment_name = 'production'
  AND r.version = '1.0.0';

INSERT INTO deployment_instances (
    application_id,
    environment_id,
    release_id,
    instance_name,
    color,
    status,
    started_at
)
SELECT
    a.application_id,
    e.environment_id,
    r.release_id,
    'payment-blue-' || n,
    'blue',
    'healthy',
    NOW()
FROM applications a
JOIN environments e
    ON e.application_id = a.application_id
JOIN releases r
    ON r.application_id = a.application_id
CROSS JOIN generate_series(1, 4) AS n
WHERE a.application_name = 'payment-api'
  AND e.environment_name = 'production'
  AND r.version = '1.0.0';

-- =========================================================
-- 22. SAMPLE SUCCESSFUL ROLLING DEPLOYMENT
-- =========================================================

INSERT INTO deployments (
    application_id,
    environment_id,
    release_id,
    policy_id,
    strategy,
    status,
    previous_release_id,
    requested_replicas,
    started_by,
    completed_at
)
SELECT
    a.application_id,
    e.environment_id,
    new_release.release_id,
    p.policy_id,
    'rolling',
    'succeeded',
    old_release.release_id,
    4,
    'release-engineer',
    NOW()
FROM applications a
JOIN environments e
    ON e.application_id = a.application_id
JOIN releases new_release
    ON new_release.application_id = a.application_id
JOIN releases old_release
    ON old_release.application_id = a.application_id
JOIN deployment_policies p
    ON p.environment_id = e.environment_id
   AND p.strategy = 'rolling'
WHERE a.application_name = 'payment-api'
  AND e.environment_name = 'production'
  AND new_release.version = '1.1.0'
  AND old_release.version = '1.0.0';

-- =========================================================
-- 23. SAMPLE ROLLING BATCHES
-- =========================================================

INSERT INTO deployment_batches (
    deployment_id,
    batch_number,
    planned_instances,
    completed_instances,
    healthy_instances,
    status,
    started_at,
    completed_at
)
SELECT
    deployment_id,
    n,
    1,
    1,
    1,
    'succeeded',
    NOW(),
    NOW()
FROM deployments
CROSS JOIN generate_series(1, 4) AS n
WHERE release_id = (
    SELECT release_id
    FROM releases
    WHERE version = '1.1.0'
      AND application_id = (
          SELECT application_id
          FROM applications
          WHERE application_name = 'payment-api'
      )
)
AND strategy = 'rolling';

-- =========================================================
-- 24. HEALTH CHECK RECORDS
-- =========================================================

INSERT INTO deployment_health_checks (
    deployment_id,
    check_name,
    check_status,
    response_time_ms,
    error_rate,
    details
)
SELECT
    d.deployment_id,
    checks.check_name,
    checks.check_status,
    checks.response_time,
    checks.error_rate,
    checks.details
FROM deployments d
CROSS JOIN (
    VALUES
        (
            'readiness',
            'passed'::health_status,
            45.0::NUMERIC,
            0.0::NUMERIC,
            '{"endpoint":"/health/ready"}'::JSONB
        ),
        (
            'liveness',
            'passed'::health_status,
            18.0::NUMERIC,
            0.0::NUMERIC,
            '{"endpoint":"/health/live"}'::JSONB
        ),
        (
            'smoke-test',
            'passed'::health_status,
            120.0::NUMERIC,
            0.0::NUMERIC,
            '{"test":"payment-transaction"}'::JSONB
        )
) AS checks(
    check_name,
    check_status,
    response_time,
    error_rate,
    details
)
WHERE d.status = 'succeeded'
  AND d.strategy = 'rolling'
  AND d.release_id = (
      SELECT release_id
      FROM releases
      WHERE version = '1.1.0'
        AND application_id = (
            SELECT application_id
            FROM applications
            WHERE application_name = 'payment-api'
        )
  );

-- =========================================================
-- 25. SAMPLE FAILED DEPLOYMENT
-- =========================================================

INSERT INTO deployments (
    application_id,
    environment_id,
    release_id,
    policy_id,
    strategy,
    status,
    previous_release_id,
    requested_replicas,
    started_by,
    error_message,
    completed_at
)
SELECT
    a.application_id,
    e.environment_id,
    new_release.release_id,
    p.policy_id,
    'blue_green',
    'failed',
    old_release.release_id,
    4,
    'deployment-engineer',
    'Green environment failed readiness validation',
    NOW()
FROM applications a
JOIN environments e
    ON e.application_id = a.application_id
JOIN releases new_release
    ON new_release.application_id = a.application_id
JOIN releases old_release
    ON old_release.application_id = a.application_id
JOIN deployment_policies p
    ON p.environment_id = e.environment_id
   AND p.strategy = 'blue_green'
WHERE a.application_name = 'payment-api'
  AND e.environment_name = 'production'
  AND new_release.version = '1.2.0'
  AND old_release.version = '1.1.0';

INSERT INTO deployment_health_checks (
    deployment_id,
    check_name,
    check_status,
    response_time_ms,
    error_rate,
    details
)
SELECT
    deployment_id,
    'green-readiness',
    'failed',
    2500,
    12.5,
    '{"reason":"Readiness timeout"}'::JSONB
FROM deployments
WHERE status = 'failed'
  AND strategy = 'blue_green';

-- =========================================================
-- 26. SAMPLE TRAFFIC ALLOCATION
-- =========================================================

INSERT INTO traffic_allocations (
    environment_id,
    deployment_id,
    release_id,
    traffic_percent,
    active
)
SELECT
    d.environment_id,
    d.deployment_id,
    d.release_id,
    100,
    TRUE
FROM deployments d
WHERE d.status = 'succeeded'
  AND d.strategy = 'rolling'
  AND d.release_id = (
      SELECT release_id
      FROM releases
      WHERE version = '1.1.0'
        AND application_id = (
            SELECT application_id
            FROM applications
            WHERE application_name = 'payment-api'
        )
  );

-- =========================================================
-- 27. SAMPLE EVENTS
-- =========================================================

INSERT INTO deployment_events (
    deployment_id,
    event_type,
    event_details
)
SELECT
    deployment_id,
    event_type,
    details
FROM deployments d
CROSS JOIN (
    VALUES
        (
            'DEPLOYMENT_STARTED',
            '{"stage":"provisioning"}'::JSONB
        ),
        (
            'HEALTH_VALIDATED',
            '{"healthy":4,"total":4}'::JSONB
        ),
        (
            'TRAFFIC_SWITCHED',
            '{"traffic_percent":100}'::JSONB
        ),
        (
            'DEPLOYMENT_SUCCEEDED',
            '{"status":"completed"}'::JSONB
        )
) AS events(event_type, details)
WHERE d.status = 'succeeded'
  AND d.strategy = 'rolling'
  AND d.release_id = (
      SELECT release_id
      FROM releases
      WHERE version = '1.1.0'
        AND application_id = (
            SELECT application_id
            FROM applications
            WHERE application_name = 'payment-api'
        )
  );

-- =========================================================
-- 28. RETRIEVAL QUERIES
-- =========================================================

-- Deployment history by application and environment.

SELECT *
FROM deployment_summary
ORDER BY started_at DESC;

-- Active infrastructure.

SELECT *
FROM environment_instance_summary
ORDER BY application_name, environment_name;

-- Deployment events.

SELECT
    d.deployment_id,
    e.event_type,
    e.event_details,
    e.created_at
FROM deployment_events e
JOIN deployments d
    ON d.deployment_id = e.deployment_id
ORDER BY e.created_at DESC;

-- =========================================================
-- 29. VALIDATION QUERIES
-- =========================================================

-- Identify unhealthy instances.

SELECT
    instance_name,
    environment_id,
    status,
    release_id
FROM deployment_instances
WHERE status = 'unhealthy';

-- Find deployments with failed health checks.

SELECT
    d.deployment_id,
    r.version,
    h.check_name,
    h.details
FROM deployments d
JOIN releases r
    ON r.release_id = d.release_id
JOIN deployment_health_checks h
    ON h.deployment_id = d.deployment_id
WHERE h.check_status = 'failed';

-- =========================================================
-- 30. AGGREGATION AND EVALUATION
-- =========================================================

SELECT *
FROM deployment_success_metrics
ORDER BY success_percentage DESC;

-- Average deployment duration.

SELECT
    strategy,
    COUNT(*) AS deployment_count,
    ROUND(
        AVG(
            EXTRACT(
                EPOCH FROM (completed_at - started_at)
            )
        ),
        2
    ) AS average_duration_seconds
FROM deployments
WHERE completed_at IS NOT NULL
GROUP BY strategy
ORDER BY average_duration_seconds;

-- Health-check success rates.

SELECT
    deployment_id,
    COUNT(*) AS total_checks,
    COUNT(*) FILTER (
        WHERE check_status = 'passed'
    ) AS passed_checks,
    COUNT(*) FILTER (
        WHERE check_status = 'failed'
    ) AS failed_checks
FROM deployment_health_checks
GROUP BY deployment_id;

-- =========================================================
-- 31. ELIGIBILITY EVALUATION
-- =========================================================

SELECT
    d.deployment_id,
    d.status,
    eligibility.eligible,
    eligibility.reason
FROM deployments d
CROSS JOIN LATERAL
    check_deployment_eligibility(d.deployment_id) eligibility
ORDER BY d.deployment_id;

-- =========================================================
-- 32. CTE: STRATEGY COMPARISON
-- =========================================================

WITH strategy_metrics AS (
    SELECT
        strategy,
        COUNT(*) AS total,
        COUNT(*) FILTER (
            WHERE status = 'succeeded'
        ) AS successful,
        COUNT(*) FILTER (
            WHERE status = 'failed'
        ) AS failed,
        AVG(
            EXTRACT(
                EPOCH FROM (completed_at - started_at)
            )
        ) AS avg_duration
    FROM deployments
    GROUP BY strategy
)
SELECT
    strategy,
    total,
    successful,
    failed,
    ROUND(
        100.0 * successful / NULLIF(total, 0),
        2
    ) AS success_rate,
    ROUND(avg_duration, 2) AS avg_duration_seconds
FROM strategy_metrics
ORDER BY success_rate DESC NULLS LAST;

-- =========================================================
-- 33. TRANSACTIONAL DEPLOYMENT WORKFLOW
-- =========================================================

/*
 * Demonstrates a controlled state transition.
 *
 * A production orchestration service must perform actual
 * provisioning and health probes before recording validation.
 */

DO $$
DECLARE
    v_deployment_id BIGINT;
    v_eligibility RECORD;
BEGIN
    SELECT deployment_id
    INTO v_deployment_id
    FROM deployments
    WHERE status = 'pending'
    ORDER BY deployment_id
    LIMIT 1
    FOR UPDATE;

    IF v_deployment_id IS NOT NULL THEN

        UPDATE deployments
        SET status = 'provisioning'
        WHERE deployment_id = v_deployment_id;

        PERFORM record_deployment_event(
            v_deployment_id,
            'PROVISIONING_STARTED'
        );

        RAISE NOTICE
            'Provisioning started for deployment %',
            v_deployment_id;

    END IF;
END;
$$;

COMMIT;

 * Example operational queries:
 *
 * -- Begin a new deployment:
 *
 * BEGIN;
 *
 * UPDATE deployments
 * SET status = 'validating'
 * WHERE deployment_id = 1
 *   AND status = 'provisioning';
 *
 * -- Record successful readiness, liveness and smoke checks.
 *
 * INSERT INTO deployment_health_checks (
 *     deployment_id,
 *     check_name,
 *     check_status
 * )
 * VALUES
 *     (1, 'readiness', 'passed'),
 *     (1, 'liveness', 'passed'),
 *     (1, 'smoke-test', 'passed');
 *
 * -- Determine eligibility:
 *
 * SELECT *
 * FROM check_deployment_eligibility(1);
 *
 * -- Switch traffic:
 *
 * CALL switch_deployment_traffic(1, 100);
 *
 * -- Complete deployment:
 *
 * UPDATE deployments
 * SET status = 'succeeded'
 * WHERE deployment_id = 1
 *   AND status = 'switching';
 *
 * COMMIT;
 *
 * -- On any error, execute ROLLBACK.
 *
 * Important:
 * The database records and enforces workflow state. It does not
 * itself provision containers, terminate processes, perform
 * network routing, or execute application health probes.
 * Those actions belong to a trusted deployment controller.
 */

DROP SCHEMA IF EXISTS container_ops CASCADE;
CREATE SCHEMA container_ops;

SET search_path = container_ops, public;

-- Resource limits are stored separately from health-check policy.
-- This prevents an application health result from being confused
-- with an infrastructure resource constraint.

CREATE TYPE container_state AS ENUM (
    'created',
    'running',
    'stopped',
    'restarting'
);

CREATE TYPE health_status AS ENUM (
    'starting',
    'healthy',
    'unhealthy'
);

CREATE TYPE restart_policy AS ENUM (
    'no',
    'on-failure',
    'always',
    'unless-stopped'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE services (
    service_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    image TEXT NOT NULL,
    desired_replicas INTEGER NOT NULL DEFAULT 1
        CHECK (desired_replicas > 0),
    UNIQUE (repository_id, name)
);

CREATE TABLE containers (
    container_id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,
    container_name TEXT NOT NULL UNIQUE,
    state container_state NOT NULL DEFAULT 'created',
    health health_status NOT NULL DEFAULT 'starting',
    restart_policy restart_policy NOT NULL DEFAULT 'no',
    restart_count INTEGER NOT NULL DEFAULT 0
        CHECK (restart_count >= 0),
    max_restarts INTEGER NOT NULL DEFAULT 5
        CHECK (max_restarts >= 0),
    manually_stopped BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ
);

CREATE TABLE resource_limits (
    container_id BIGINT PRIMARY KEY
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    cpu_millicores INTEGER NOT NULL
        CHECK (cpu_millicores > 0),
    memory_mb INTEGER NOT NULL
        CHECK (memory_mb > 0)
);

CREATE TABLE health_check_policies (
    container_id BIGINT PRIMARY KEY
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    interval_seconds INTEGER NOT NULL
        CHECK (interval_seconds > 0),
    timeout_seconds INTEGER NOT NULL
        CHECK (timeout_seconds > 0),
    retries INTEGER NOT NULL
        CHECK (retries > 0),
    start_period_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (start_period_seconds >= 0),
    CHECK (timeout_seconds <= interval_seconds)
);

CREATE TABLE health_check_results (
    result_id BIGSERIAL PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    success BOOLEAN NOT NULL,
    latency_ms NUMERIC(12, 3) NOT NULL
        CHECK (latency_ms >= 0),
    message TEXT NOT NULL
);

CREATE TABLE restart_events (
    restart_event_id BIGSERIAL PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    restart_number INTEGER NOT NULL
        CHECK (restart_number > 0),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_health_results_container_time
    ON health_check_results (container_id, checked_at DESC);

CREATE INDEX idx_restart_events_container_time
    ON restart_events (container_id, created_at DESC);

CREATE INDEX idx_containers_health_state
    ON containers (health, state);

-- The trigger enforces the relationship between state and timestamps.
CREATE OR REPLACE FUNCTION validate_container_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'running' AND NEW.started_at IS NULL THEN
        RAISE EXCEPTION
            'Running container % requires started_at',
            NEW.container_name;
    END IF;

    IF NEW.state = 'stopped' AND NEW.stopped_at IS NULL THEN
        RAISE EXCEPTION
            'Stopped container % requires stopped_at',
            NEW.container_name;
    END IF;

    IF NEW.restart_count > NEW.max_restarts THEN
        RAISE EXCEPTION
            'Container % exceeds max restart count',
            NEW.container_name;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_container_state
BEFORE INSERT OR UPDATE ON containers
FOR EACH ROW
EXECUTE FUNCTION validate_container_state();

-- Record a health result and calculate the resulting health state.
CREATE OR REPLACE FUNCTION record_health_result(
    p_container_id BIGINT,
    p_success BOOLEAN,
    p_latency_ms NUMERIC,
    p_message TEXT,
    p_checked_at TIMESTAMPTZ DEFAULT now()
)
RETURNS health_status
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy health_check_policies%ROWTYPE;
    v_container containers%ROWTYPE;
    v_recent_failures INTEGER;
    v_new_health health_status;
BEGIN
    IF p_latency_ms < 0 THEN
        RAISE EXCEPTION 'Latency cannot be negative';
    END IF;

    SELECT *
    INTO v_container
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Container % does not exist',
            p_container_id;
    END IF;

    IF v_container.state <> 'running' THEN
        RAISE EXCEPTION
            'Health check requires running container %',
            v_container.container_name;
    END IF;

    SELECT *
    INTO v_policy
    FROM health_check_policies
    WHERE container_id = p_container_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'No health-check policy for container %',
            p_container_id;
    END IF;

    INSERT INTO health_check_results (
        container_id,
        checked_at,
        success,
        latency_ms,
        message
    )
    VALUES (
        p_container_id,
        p_checked_at,
        p_success,
        p_latency_ms,
        p_message
    );

    /*
     * A result is considered successful only when the probe succeeds
     * and its latency remains within the configured timeout.
     */
    IF p_success
       AND p_latency_ms <= v_policy.timeout_seconds * 1000 THEN

        v_new_health := 'healthy';

    ELSE

        SELECT count(*)
        INTO v_recent_failures
        FROM (
            SELECT success, latency_ms
            FROM health_check_results
            WHERE container_id = p_container_id
            ORDER BY checked_at DESC
            LIMIT v_policy.retries
        ) recent
        WHERE NOT (
            recent.success
            AND recent.latency_ms <=
                v_policy.timeout_seconds * 1000
        );

        IF v_recent_failures >= v_policy.retries THEN
            v_new_health := 'unhealthy';
        ELSE
            v_new_health := 'starting';
        END IF;
    END IF;

    UPDATE containers
    SET health = v_new_health
    WHERE container_id = p_container_id;

    RETURN v_new_health;
END;
$$;

-- Determine whether a container is eligible for automatic restart.
CREATE OR REPLACE FUNCTION restart_eligible(
    p_container_id BIGINT,
    p_exit_code INTEGER
)
RETURNS BOOLEAN
LANGUAGE sql
AS $$
    SELECT
        NOT manually_stopped
        AND restart_count < max_restarts
        AND CASE restart_policy
            WHEN 'no' THEN FALSE
            WHEN 'always' THEN TRUE
            WHEN 'unless-stopped' THEN TRUE
            WHEN 'on-failure' THEN p_exit_code <> 0
        END
    FROM containers
    WHERE container_id = p_container_id;
$$;

-- Perform a restart atomically and record the recovery event.
CREATE OR REPLACE FUNCTION restart_container(
    p_container_id BIGINT,
    p_reason TEXT,
    p_exit_code INTEGER DEFAULT 1
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_container containers%ROWTYPE;
BEGIN
    SELECT *
    INTO v_container
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Container % does not exist',
            p_container_id;
    END IF;

    IF NOT restart_eligible(p_container_id, p_exit_code) THEN
        RETURN FALSE;
    END IF;

    UPDATE containers
    SET
        state = 'restarting',
        restart_count = restart_count + 1,
        stopped_at = now()
    WHERE container_id = p_container_id;

    INSERT INTO restart_events (
        container_id,
        restart_number,
        reason
    )
    VALUES (
        p_container_id,
        v_container.restart_count + 1,
        p_reason
    );

    UPDATE containers
    SET
        state = 'running',
        health = 'starting',
        started_at = now(),
        stopped_at = NULL,
        manually_stopped = FALSE
    WHERE container_id = p_container_id;

    RETURN TRUE;
END;
$$;

CREATE OR REPLACE VIEW container_health_report AS
SELECT
    c.container_id,
    c.container_name,
    s.name AS service_name,
    r.name AS repository_name,
    c.state,
    c.health,
    c.restart_policy,
    c.restart_count,
    c.max_restarts,
    rl.cpu_millicores,
    rl.memory_mb,
    hc.interval_seconds,
    hc.timeout_seconds,
    hc.retries,
    c.started_at
FROM containers c
JOIN services s
    ON s.service_id = c.service_id
JOIN repositories r
    ON r.repository_id = s.repository_id
JOIN resource_limits rl
    ON rl.container_id = c.container_id
JOIN health_check_policies hc
    ON hc.container_id = c.container_id;

INSERT INTO repositories (name, owner)
VALUES
    ('payments-platform', 'platform-team'),
    ('analytics-platform', 'data-team');

INSERT INTO services (
    repository_id,
    name,
    image,
    desired_replicas
)
SELECT
    repository_id,
    'api',
    'registry.example/payments-api:2.4',
    2
FROM repositories
WHERE name = 'payments-platform';

INSERT INTO services (
    repository_id,
    name,
    image,
    desired_replicas
)
SELECT
    repository_id,
    'worker',
    'registry.example/analytics-worker:4.1',
    1
FROM repositories
WHERE name = 'analytics-platform';

INSERT INTO containers (
    service_id,
    container_name,
    state,
    health,
    restart_policy,
    max_restarts,
    started_at
)
SELECT
    service_id,
    'payments-api-01',
    'running',
    'healthy',
    'unless-stopped',
    5,
    now()
FROM services
WHERE name = 'api';

INSERT INTO containers (
    service_id,
    container_name,
    state,
    health,
    restart_policy,
    max_restarts,
    started_at
)
SELECT
    service_id,
    'analytics-worker-01',
    'running',
    'unhealthy',
    'on-failure',
    2,
    now()
FROM services
WHERE name = 'worker';

INSERT INTO resource_limits (
    container_id,
    cpu_millicores,
    memory_mb
)
SELECT
    container_id,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 500
        ELSE 750
    END,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 512
        ELSE 1024
    END
FROM containers;

INSERT INTO health_check_policies (
    container_id,
    interval_seconds,
    timeout_seconds,
    retries,
    start_period_seconds
)
SELECT
    container_id,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 5
        ELSE 10
    END,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 2
        ELSE 3
    END,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 3
        ELSE 2
    END,
    CASE
        WHEN container_name = 'payments-api-01'
        THEN 5
        ELSE 0
    END
FROM containers;

-- Transactional health evaluation for the API.
BEGIN;

SELECT record_health_result(
    c.container_id,
    TRUE,
    42,
    'HTTP 200 /health'
)
FROM containers c
WHERE c.container_name = 'payments-api-01';

COMMIT;

-- Failure sequence for the worker.
BEGIN;

SELECT record_health_result(
    c.container_id,
    FALSE,
    5000,
    'database dependency unavailable'
)
FROM containers c
WHERE c.container_name = 'analytics-worker-01';

SELECT record_health_result(
    c.container_id,
    FALSE,
    5100,
    'database dependency unavailable'
)
FROM containers c
WHERE c.container_name = 'analytics-worker-01';

COMMIT;

-- Automatic recovery is evaluated against the configured policy.
BEGIN;

SELECT restart_container(
    c.container_id,
    'health check became unhealthy',
    1
)
FROM containers c
WHERE c.container_name = 'analytics-worker-01';

COMMIT;

-- Retrieval and reporting.
SELECT *
FROM container_health_report
ORDER BY repository_name, service_name, container_name;

-- Latest health result for every container.
WITH ranked_checks AS (
    SELECT
        h.*,
        row_number() OVER (
            PARTITION BY h.container_id
            ORDER BY h.checked_at DESC
        ) AS rn
    FROM health_check_results h
)
SELECT
    c.container_name,
    c.health,
    rc.success,
    rc.latency_ms,
    rc.message,
    rc.checked_at
FROM containers c
LEFT JOIN ranked_checks rc
    ON rc.container_id = c.container_id
   AND rc.rn = 1
ORDER BY c.container_name;

-- Restart-rate report.
SELECT
    c.container_name,
    c.restart_count,
    c.max_restarts,
    CASE
        WHEN c.max_restarts = 0 THEN 0
        ELSE round(
            100.0 * c.restart_count / c.max_restarts,
            2
        )
    END AS restart_budget_used_percent
FROM containers c
ORDER BY c.restart_count DESC;

-- Identify containers that are unhealthy or close to their restart budget.
SELECT
    container_name,
    state,
    health,
    restart_count,
    max_restarts,
    cpu_millicores,
    memory_mb
FROM container_health_report
WHERE health = 'unhealthy'
   OR restart_count >= greatest(max_restarts - 1, 0)
ORDER BY restart_count DESC, container_name;

-- Validate restart policy behavior without modifying data.
SELECT
    container_name,
    restart_policy,
    restart_eligible(container_id, 1)
        AS restart_after_failure,
    restart_eligible(container_id, 0)
        AS restart_after_success
FROM containers
ORDER BY container_name;

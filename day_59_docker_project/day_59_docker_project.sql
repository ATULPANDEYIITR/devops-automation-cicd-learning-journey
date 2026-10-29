DROP SCHEMA IF EXISTS docker_demo CASCADE;
CREATE SCHEMA docker_demo;

SET search_path TO docker_demo;

-- Docker-style service states are stored as constrained values so invalid
-- lifecycle states cannot enter the database.
CREATE TYPE service_state AS ENUM (
    'created',
    'starting',
    'healthy',
    'unhealthy',
    'stopped'
);

CREATE TYPE dependency_condition AS ENUM (
    'service_started',
    'service_healthy'
);

CREATE TYPE container_status AS ENUM (
    'created',
    'running',
    'stopped',
    'failed'
);

CREATE TABLE repository (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(name)) >= 2)
);

CREATE TABLE service (
    service_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    service_name TEXT NOT NULL,
    image_name TEXT NOT NULL,
    image_tag TEXT NOT NULL,
    host_port INTEGER,
    memory_limit_mb INTEGER NOT NULL DEFAULT 256,
    state service_state NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, service_name),
    CHECK (service_name ~ '^[a-z0-9][a-z0-9-]*$'),
    CHECK (image_tag <> ''),
    CHECK (
        host_port IS NULL
        OR host_port BETWEEN 1 AND 65535
    ),
    CHECK (memory_limit_mb >= 64)
);

CREATE INDEX idx_service_repository
    ON service(repository_id);

CREATE TABLE service_environment (
    service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    variable_name TEXT NOT NULL,
    variable_value TEXT NOT NULL,
    PRIMARY KEY (service_id, variable_name),
    CHECK (variable_name ~ '^[A-Z][A-Z0-9_]*$')
);

CREATE TABLE service_dependency (
    service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    depends_on_service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    condition dependency_condition NOT NULL DEFAULT 'service_started',
    PRIMARY KEY (service_id, depends_on_service_id),
    CHECK (service_id <> depends_on_service_id)
);

CREATE INDEX idx_dependency_target
    ON service_dependency(depends_on_service_id);

CREATE TABLE container (
    container_id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    container_name TEXT NOT NULL UNIQUE,
    container_status container_status NOT NULL DEFAULT 'created',
    restart_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    CHECK (restart_count >= 0),
    CHECK (
        stopped_at IS NULL
        OR started_at IS NULL
        OR stopped_at >= started_at
    )
);

CREATE TABLE health_check (
    health_check_id BIGSERIAL PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    endpoint TEXT,
    interval_seconds INTEGER NOT NULL DEFAULT 30,
    timeout_seconds INTEGER NOT NULL DEFAULT 5,
    retries INTEGER NOT NULL DEFAULT 3,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (service_id, check_name),
    CHECK (interval_seconds > 0),
    CHECK (timeout_seconds > 0),
    CHECK (retries > 0)
);

CREATE TABLE health_observation (
    observation_id BIGSERIAL PRIMARY KEY,
    health_check_id BIGINT NOT NULL
        REFERENCES health_check(health_check_id)
        ON DELETE CASCADE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    healthy BOOLEAN NOT NULL,
    response_ms INTEGER,
    failure_reason TEXT,
    CHECK (response_ms IS NULL OR response_ms >= 0),
    CHECK (
        healthy = TRUE
        OR failure_reason IS NOT NULL
    )
);

CREATE INDEX idx_health_observation_check_time
    ON health_observation(health_check_id, observed_at DESC);

CREATE TABLE network (
    network_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    network_name TEXT NOT NULL,
    driver TEXT NOT NULL DEFAULT 'bridge',
    UNIQUE (repository_id, network_name),
    CHECK (network_name <> ''),
    CHECK (driver IN ('bridge', 'overlay', 'host'))
);

CREATE TABLE network_membership (
    network_id BIGINT NOT NULL
        REFERENCES network(network_id)
        ON DELETE CASCADE,
    service_id BIGINT NOT NULL
        REFERENCES service(service_id)
        ON DELETE CASCADE,
    aliases TEXT[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (network_id, service_id)
);

CREATE TABLE deployment_policy (
    policy_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    policy_name TEXT NOT NULL,
    required_healthy_services INTEGER NOT NULL DEFAULT 0,
    max_total_memory_mb INTEGER NOT NULL,
    allow_direct_database_access BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, policy_name),
    CHECK (required_healthy_services >= 0),
    CHECK (max_total_memory_mb >= 64)
);

CREATE TABLE deployment (
    deployment_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    policy_id BIGINT NOT NULL
        REFERENCES deployment_policy(policy_id),
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE deployment_service (
    deployment_id BIGINT NOT NULL
        REFERENCES deployment(deployment_id)
        ON DELETE CASCADE,
    service_id BIGINT NOT NULL
        REFERENCES service(service_id),
    desired_state service_state NOT NULL,
    actual_state service_state NOT NULL,
    PRIMARY KEY (deployment_id, service_id)
);

CREATE OR REPLACE FUNCTION prevent_self_dependency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.service_id = NEW.depends_on_service_id THEN
        RAISE EXCEPTION
            'A service cannot depend on itself: service_id=%',
            NEW.service_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_self_dependency
BEFORE INSERT OR UPDATE ON service_dependency
FOR EACH ROW
EXECUTE FUNCTION prevent_self_dependency();

CREATE OR REPLACE FUNCTION enforce_unique_host_port()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.host_port IS NOT NULL AND EXISTS (
        SELECT 1
        FROM service existing
        WHERE existing.repository_id = NEW.repository_id
          AND existing.host_port = NEW.host_port
          AND existing.service_id <> NEW.service_id
    ) THEN
        RAISE EXCEPTION
            'Host port % is already assigned in repository %',
            NEW.host_port,
            NEW.repository_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_unique_host_port
BEFORE INSERT OR UPDATE ON service
FOR EACH ROW
EXECUTE FUNCTION enforce_unique_host_port();

CREATE OR REPLACE FUNCTION validate_container_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.container_status = 'stopped'
       AND NEW.container_status = 'running'
       AND NEW.restart_count <= OLD.restart_count THEN
        RAISE EXCEPTION
            'Restarting a stopped container must increment restart_count';
    END IF;

    IF NEW.container_status = 'running'
       AND NEW.started_at IS NULL THEN
        NEW.started_at := now();
    END IF;

    IF NEW.container_status = 'stopped'
       AND OLD.container_status <> 'stopped'
       AND NEW.stopped_at IS NULL THEN
        NEW.stopped_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_transition
BEFORE UPDATE ON container
FOR EACH ROW
EXECUTE FUNCTION validate_container_transition();

INSERT INTO repository (name, description)
VALUES (
    'orders-platform',
    'Multi-service order processing application'
);

INSERT INTO service (
    repository_id,
    service_name,
    image_name,
    image_tag,
    host_port,
    memory_limit_mb,
    state
)
SELECT
    repository_id,
    service_name,
    image_name,
    image_tag,
    host_port,
    memory_limit_mb,
    state
FROM (
    SELECT
        r.repository_id,
        'db'::TEXT AS service_name,
        'postgres'::TEXT AS image_name,
        '18'::TEXT AS image_tag,
        5432::INTEGER AS host_port,
        512::INTEGER AS memory_limit_mb,
        'healthy'::service_state AS state
    FROM repository r
    WHERE r.name = 'orders-platform'

    UNION ALL

    SELECT
        r.repository_id,
        'redis',
        'redis',
        '8',
        6379,
        256,
        'healthy'::service_state
    FROM repository r
    WHERE r.name = 'orders-platform'

    UNION ALL

    SELECT
        r.repository_id,
        'api',
        'orders-api',
        '1.0',
        8080,
        512,
        'healthy'::service_state
    FROM repository r
    WHERE r.name = 'orders-platform'

    UNION ALL

    SELECT
        r.repository_id,
        'worker',
        'orders-worker',
        '1.0',
        NULL,
        384,
        'healthy'::service_state
    FROM repository r
    WHERE r.name = 'orders-platform'

    UNION ALL

    SELECT
        r.repository_id,
        'frontend',
        'orders-frontend',
        '1.0',
        3000,
        256,
        'healthy'::service_state
    FROM repository r
    WHERE r.name = 'orders-platform'
) seed;

INSERT INTO service_environment (
    service_id,
    variable_name,
    variable_value
)
SELECT s.service_id, 'DATABASE_HOST', 'db'
FROM service s
WHERE s.service_name IN ('api', 'worker');

INSERT INTO service_environment (
    service_id,
    variable_name,
    variable_value
)
SELECT s.service_id, 'REDIS_HOST', 'redis'
FROM service s
WHERE s.service_name IN ('api', 'worker');

INSERT INTO service_environment (
    service_id,
    variable_name,
    variable_value
)
SELECT s.service_id, 'API_BASE_URL', 'http://api:8080'
FROM service s
WHERE s.service_name = 'frontend';

INSERT INTO service_dependency (
    service_id,
    depends_on_service_id,
    condition
)
SELECT api.service_id, db.service_id, 'service_healthy'
FROM service api
JOIN service db ON db.service_name = 'db'
WHERE api.service_name = 'api';

INSERT INTO service_dependency (
    service_id,
    depends_on_service_id,
    condition
)
SELECT api.service_id, redis.service_id, 'service_healthy'
FROM service api
JOIN service redis ON redis.service_name = 'redis'
WHERE api.service_name = 'api';

INSERT INTO service_dependency (
    service_id,
    depends_on_service_id,
    condition
)
SELECT worker.service_id, db.service_id, 'service_healthy'
FROM service worker
JOIN service db ON db.service_name = 'db'
WHERE worker.service_name = 'worker';

INSERT INTO service_dependency (
    service_id,
    depends_on_service_id,
    condition
)
SELECT worker.service_id, redis.service_id, 'service_healthy'
FROM service worker
JOIN service redis ON redis.service_name = 'redis'
WHERE worker.service_name = 'worker';

INSERT INTO service_dependency (
    service_id,
    depends_on_service_id,
    condition
)
SELECT frontend.service_id, api.service_id, 'service_healthy'
FROM service frontend
JOIN service api ON api.service_name = 'api'
WHERE frontend.service_name = 'frontend';

INSERT INTO health_check (
    service_id,
    check_name,
    endpoint,
    interval_seconds,
    timeout_seconds,
    retries
)
SELECT
    service_id,
    'container-health',
    CASE
        WHEN service_name = 'api' THEN '/health'
        WHEN service_name = 'frontend' THEN '/'
        ELSE NULL
    END,
    15,
    5,
    3
FROM service
WHERE service_name IN ('db', 'redis', 'api', 'worker', 'frontend');

INSERT INTO health_observation (
    health_check_id,
    healthy,
    response_ms,
    failure_reason
)
SELECT
    health_check_id,
    TRUE,
    12,
    NULL
FROM health_check;

INSERT INTO network (
    repository_id,
    network_name,
    driver
)
SELECT repository_id, 'orders-network', 'bridge'
FROM repository
WHERE name = 'orders-platform';

INSERT INTO network_membership (
    network_id,
    service_id,
    aliases
)
SELECT
    n.network_id,
    s.service_id,
    ARRAY[s.service_name]
FROM network n
JOIN service s
    ON s.repository_id = n.repository_id
WHERE n.network_name = 'orders-network';

INSERT INTO deployment_policy (
    repository_id,
    policy_name,
    required_healthy_services,
    max_total_memory_mb,
    allow_direct_database_access
)
SELECT
    repository_id,
    'production',
    5,
    2048,
    FALSE
FROM repository
WHERE name = 'orders-platform';

INSERT INTO deployment (
    repository_id,
    policy_id,
    status,
    started_at
)
SELECT
    r.repository_id,
    p.policy_id,
    'running',
    now()
FROM repository r
JOIN deployment_policy p
    ON p.repository_id = r.repository_id
WHERE r.name = 'orders-platform'
  AND p.policy_name = 'production';

INSERT INTO deployment_service (
    deployment_id,
    service_id,
    desired_state,
    actual_state
)
SELECT
    d.deployment_id,
    s.service_id,
    'healthy',
    s.state
FROM deployment d
JOIN service s
    ON s.repository_id = d.repository_id;

INSERT INTO container (
    service_id,
    container_name,
    container_status,
    restart_count,
    started_at
)
SELECT
    service_id,
    service_name || '-1',
    'running',
    0,
    now()
FROM service;

-- Demonstrate basic repository topology.
SELECT
    r.name AS repository,
    s.service_name,
    s.image_name || ':' || s.image_tag AS image,
    s.state,
    s.memory_limit_mb
FROM repository r
JOIN service s
    ON s.repository_id = r.repository_id
ORDER BY s.service_name;

-- Dependency graph with explicit health requirements.
SELECT
    dependent.service_name AS service,
    dependency.service_name AS depends_on,
    sd.condition
FROM service_dependency sd
JOIN service dependent
    ON dependent.service_id = sd.service_id
JOIN service dependency
    ON dependency.service_id = sd.depends_on_service_id
ORDER BY dependent.service_name, dependency.service_name;

-- Current health report uses the latest observation per check.
WITH latest_health AS (
    SELECT DISTINCT ON (health_check_id)
        health_check_id,
        healthy,
        observed_at,
        response_ms,
        failure_reason
    FROM health_observation
    ORDER BY health_check_id, observed_at DESC
)
SELECT
    s.service_name,
    hc.check_name,
    lh.healthy,
    lh.response_ms,
    lh.observed_at,
    lh.failure_reason
FROM health_check hc
JOIN service s
    ON s.service_id = hc.service_id
JOIN latest_health lh
    ON lh.health_check_id = hc.health_check_id
ORDER BY s.service_name;

-- Total memory requested by the application.
SELECT
    r.name AS repository,
    SUM(s.memory_limit_mb) AS requested_memory_mb,
    p.max_total_memory_mb,
    SUM(s.memory_limit_mb) <= p.max_total_memory_mb AS within_policy
FROM repository r
JOIN service s
    ON s.repository_id = r.repository_id
JOIN deployment_policy p
    ON p.repository_id = r.repository_id
WHERE p.policy_name = 'production'
GROUP BY r.name, p.max_total_memory_mb;

-- Evaluate whether each service's dependencies are healthy.
SELECT
    dependent.service_name,
    COUNT(*) AS dependency_count,
    COUNT(*) FILTER (
        WHERE dependency.state = 'healthy'
    ) AS healthy_dependencies,
    COUNT(*) = COUNT(*) FILTER (
        WHERE dependency.state = 'healthy'
    ) AS dependencies_satisfied
FROM service_dependency sd
JOIN service dependent
    ON dependent.service_id = sd.service_id
JOIN service dependency
    ON dependency.service_id = sd.depends_on_service_id
GROUP BY dependent.service_name
ORDER BY dependent.service_name;

-- Identify services with direct database dependencies.
-- The production policy disallows direct database access from the frontend.
SELECT
    frontend.service_name AS source_service,
    database_service.service_name AS database_service,
    p.allow_direct_database_access,
    CASE
        WHEN p.allow_direct_database_access THEN 'allowed'
        ELSE 'blocked'
    END AS policy_decision
FROM service_dependency sd
JOIN service frontend
    ON frontend.service_id = sd.service_id
JOIN service database_service
    ON database_service.service_id = sd.depends_on_service_id
JOIN deployment_policy p
    ON p.repository_id = frontend.repository_id
WHERE database_service.service_name = 'db';

-- Deployment eligibility combines health, memory, and actual state.
WITH service_health AS (
    SELECT
        s.repository_id,
        COUNT(*) FILTER (
            WHERE s.state = 'healthy'
        ) AS healthy_services,
        COUNT(*) AS total_services,
        SUM(s.memory_limit_mb) AS memory_requested
    FROM service s
    GROUP BY s.repository_id
),
policy_check AS (
    SELECT
        p.repository_id,
        p.required_healthy_services,
        p.max_total_memory_mb,
        h.healthy_services,
        h.total_services,
        h.memory_requested
    FROM deployment_policy p
    JOIN service_health h
        ON h.repository_id = p.repository_id
    WHERE p.policy_name = 'production'
)
SELECT
    r.name AS repository,
    pc.healthy_services,
    pc.total_services,
    pc.memory_requested,
    pc.required_healthy_services,
    pc.max_total_memory_mb,
    (
        pc.healthy_services >= pc.required_healthy_services
        AND pc.memory_requested <= pc.max_total_memory_mb
        AND pc.healthy_services = pc.total_services
    ) AS deployment_eligible
FROM policy_check pc
JOIN repository r
    ON r.repository_id = pc.repository_id;

-- Transactional recovery example.
BEGIN;

UPDATE service
SET state = 'unhealthy'
WHERE service_name = 'redis';

INSERT INTO health_observation (
    health_check_id,
    healthy,
    response_ms,
    failure_reason
)
SELECT
    hc.health_check_id,
    FALSE,
    NULL,
    'Redis connection refused'
FROM health_check hc
JOIN service s
    ON s.service_id = hc.service_id
WHERE s.service_name = 'redis';

-- The failed state is intentionally visible inside the transaction.
SELECT
    service_name,
    state
FROM service
WHERE service_name = 'redis';

-- Roll back the simulated outage so the sample database ends healthy.
ROLLBACK;

-- Confirm the restored state.
SELECT
    service_name,
    state
FROM service
ORDER BY service_name;

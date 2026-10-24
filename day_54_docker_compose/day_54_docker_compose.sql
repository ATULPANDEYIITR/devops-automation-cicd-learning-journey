-- Docker Compose multi-container application model.
-- PostgreSQL 18 compatible.
--
-- The database represents desired Compose configuration and an observed
-- deployment snapshot. It does not create containers or replace the Docker
-- Engine. Health and dependency records are explicit inputs to evaluation.

BEGIN;

CREATE SCHEMA IF NOT EXISTS compose_lab;
SET search_path TO compose_lab, public;

CREATE TYPE service_state AS ENUM (
    'created',
    'starting',
    'healthy',
    'unhealthy',
    'stopped',
    'failed'
);

CREATE TYPE dependency_condition AS ENUM (
    'service_started',
    'service_healthy'
);

CREATE TYPE restart_policy AS ENUM (
    'no',
    'on-failure',
    'always',
    'unless-stopped'
);

CREATE TABLE projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (project_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
);

CREATE TABLE networks (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id)
        ON DELETE CASCADE,
    network_name TEXT NOT NULL,
    driver TEXT NOT NULL DEFAULT 'bridge',
    internal BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (network_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'),
    CHECK (driver IN ('bridge', 'overlay')),
    UNIQUE (project_id, network_name),
    UNIQUE (project_id, network_id)
);

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id)
        ON DELETE CASCADE,
    service_name TEXT NOT NULL,
    image TEXT NOT NULL,
    desired_state service_state NOT NULL DEFAULT 'created',
    observed_state service_state NOT NULL DEFAULT 'created',
    healthcheck_configured BOOLEAN NOT NULL DEFAULT FALSE,
    restart_policy restart_policy NOT NULL DEFAULT 'no',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (service_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'),
    CHECK (length(trim(image)) > 0),
    UNIQUE (project_id, service_name),
    UNIQUE (project_id, service_id)
);

CREATE TABLE service_networks (
    project_id BIGINT NOT NULL,
    service_id BIGINT NOT NULL,
    network_id BIGINT NOT NULL,
    PRIMARY KEY (service_id, network_id),
    FOREIGN KEY (project_id, service_id)
        REFERENCES services(project_id, service_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, network_id)
        REFERENCES networks(project_id, network_id) ON DELETE CASCADE
);

CREATE TABLE service_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    service_id BIGINT NOT NULL,
    depends_on_service_id BIGINT NOT NULL,
    condition dependency_condition NOT NULL DEFAULT 'service_healthy',
    CHECK (service_id <> depends_on_service_id),
    FOREIGN KEY (project_id, service_id)
        REFERENCES services(project_id, service_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, depends_on_service_id)
        REFERENCES services(project_id, service_id) ON DELETE CASCADE,
    UNIQUE (service_id, depends_on_service_id)
);

CREATE TABLE service_environment (
    service_id BIGINT NOT NULL REFERENCES services(service_id)
        ON DELETE CASCADE,
    variable_name TEXT NOT NULL,
    variable_value TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (service_id, variable_name),
    CHECK (variable_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'),
    CHECK (
        is_secret = FALSE OR
        variable_value IS NULL OR
        length(variable_value) > 0
    )
);

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id)
        ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'running', 'failed', 'stopped')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (project_id, version_number),
    CHECK (
        finished_at IS NULL OR
        started_at IS NULL OR
        finished_at >= started_at
    )
);

CREATE TABLE deployment_service_status (
    deployment_id BIGINT NOT NULL REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,
    service_id BIGINT NOT NULL REFERENCES services(service_id)
        ON DELETE CASCADE,
    state service_state NOT NULL DEFAULT 'created',
    health_check_passed BOOLEAN,
    checked_at TIMESTAMPTZ,
    PRIMARY KEY (deployment_id, service_id),
    CHECK (
        health_check_passed IS NULL OR checked_at IS NOT NULL
    )
);

CREATE TABLE status_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,
    service_id BIGINT NOT NULL REFERENCES services(service_id)
        ON DELETE CASCADE,
    event_name TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(event_name)) > 0)
);

CREATE INDEX idx_dependencies_parent
    ON service_dependencies(depends_on_service_id);

CREATE INDEX idx_deployment_status
    ON deployments(project_id, status, version_number DESC);

CREATE INDEX idx_service_status
    ON deployment_service_status(deployment_id, state);

CREATE INDEX idx_status_events_timeline
    ON status_events(deployment_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION validate_service_network_membership()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM service_networks
    WHERE service_id = NEW.service_id;

    IF v_count = 0 THEN
        RAISE EXCEPTION 'Service % must join at least one network',
            NEW.service_id;
    END IF;

    RETURN NULL;
END;
$$;

-- A deferred constraint trigger permits the service and its network
-- memberships to be inserted within the same transaction.
CREATE CONSTRAINT TRIGGER service_requires_network
AFTER INSERT OR UPDATE ON services
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION validate_service_network_membership();

CREATE OR REPLACE FUNCTION validate_healthy_dependency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_healthcheck BOOLEAN;
BEGIN
    IF NEW.condition = 'service_healthy' THEN
        SELECT healthcheck_configured
        INTO v_healthcheck
        FROM services
        WHERE service_id = NEW.depends_on_service_id;

        IF v_healthcheck IS DISTINCT FROM TRUE THEN
            RAISE EXCEPTION
                'Dependency service % must have a health check',
                NEW.depends_on_service_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER dependency_healthcheck_guard
BEFORE INSERT OR UPDATE ON service_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_healthy_dependency();

CREATE OR REPLACE FUNCTION validate_dependency_graph()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_cycle BOOLEAN;
BEGIN
    WITH RECURSIVE walk(origin, current_service, path, cycle_found) AS (
        SELECT
            d.service_id,
            d.depends_on_service_id,
            ARRAY[d.service_id, d.depends_on_service_id]::BIGINT[],
            d.service_id = d.depends_on_service_id
        FROM service_dependencies d
        WHERE d.project_id = NEW.project_id

        UNION ALL

        SELECT
            w.origin,
            d.depends_on_service_id,
            w.path || d.depends_on_service_id,
            d.depends_on_service_id = ANY(w.path)
        FROM walk w
        JOIN service_dependencies d
          ON d.service_id = w.current_service
         AND d.project_id = NEW.project_id
        WHERE NOT w.cycle_found
          AND cardinality(w.path) <= 100
    )
    SELECT EXISTS (
        SELECT 1 FROM walk WHERE cycle_found
    )
    INTO v_cycle;

    IF v_cycle THEN
        RAISE EXCEPTION
            'Circular service dependency in project %',
            NEW.project_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER dependency_cycle_guard
AFTER INSERT OR UPDATE ON service_dependencies
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION validate_dependency_graph();

CREATE OR REPLACE FUNCTION validate_deployment_service()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_project BIGINT;
    v_expected_project BIGINT;
BEGIN
    SELECT project_id
    INTO v_project
    FROM deployments
    WHERE deployment_id = NEW.deployment_id;

    SELECT project_id
    INTO v_expected_project
    FROM services
    WHERE service_id = NEW.service_id;

    IF v_project IS DISTINCT FROM v_expected_project THEN
        RAISE EXCEPTION
            'Deployment and service must belong to the same project';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER deployment_service_project_guard
BEFORE INSERT OR UPDATE ON deployment_service_status
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_service();

CREATE OR REPLACE FUNCTION validate_status_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment_project BIGINT;
    v_service_project BIGINT;
BEGIN
    SELECT project_id
    INTO v_deployment_project
    FROM deployments
    WHERE deployment_id = NEW.deployment_id;

    SELECT project_id
    INTO v_service_project
    FROM services
    WHERE service_id = NEW.service_id;

    IF v_deployment_project IS DISTINCT FROM v_service_project THEN
        RAISE EXCEPTION
            'Event deployment and service must belong to the same project';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER status_event_project_guard
BEFORE INSERT OR UPDATE ON status_events
FOR EACH ROW
EXECUTE FUNCTION validate_status_event();

CREATE OR REPLACE FUNCTION can_start_service(
    p_deployment_id BIGINT,
    p_service_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM service_dependencies d
        LEFT JOIN deployment_service_status parent_status
          ON parent_status.deployment_id = p_deployment_id
         AND parent_status.service_id = d.depends_on_service_id
        WHERE d.service_id = p_service_id
          AND (
              parent_status.service_id IS NULL
              OR (
                  d.condition = 'service_healthy'
                  AND parent_status.state <> 'healthy'
              )
              OR (
                  d.condition = 'service_started'
                  AND parent_status.state = 'created'
              )
          )
    );
$$;

CREATE OR REPLACE FUNCTION evaluate_project_deployment(
    p_deployment_id BIGINT
)
RETURNS TABLE (
    service_name TEXT,
    observed_state service_state,
    dependencies_satisfied BOOLEAN,
    healthy BOOLEAN,
    eligible_to_serve BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        s.service_name,
        COALESCE(ds.state, 'created'::service_state),
        can_start_service(p_deployment_id, s.service_id),
        COALESCE(ds.health_check_passed, FALSE),
        (
            COALESCE(ds.state, 'created'::service_state) = 'healthy'
            AND can_start_service(p_deployment_id, s.service_id)
            AND COALESCE(ds.health_check_passed, FALSE)
        )
    FROM services s
    LEFT JOIN deployment_service_status ds
      ON ds.service_id = s.service_id
     AND ds.deployment_id = p_deployment_id
    JOIN deployments d ON d.deployment_id = p_deployment_id
    WHERE s.project_id = d.project_id
    ORDER BY s.service_name;
$$;

CREATE VIEW service_network_report AS
SELECT
    p.project_name,
    s.service_name,
    s.image,
    n.network_name,
    n.internal AS network_internal,
    n.driver AS network_driver
FROM services s
JOIN projects p ON p.project_id = s.project_id
JOIN service_networks sn ON sn.service_id = s.service_id
JOIN networks n ON n.network_id = sn.network_id;

CREATE VIEW latest_deployment_report AS
SELECT DISTINCT ON (d.project_id)
    p.project_name,
    d.deployment_id,
    d.version_number,
    d.status,
    d.started_at,
    d.finished_at
FROM deployments d
JOIN projects p ON p.project_id = d.project_id
ORDER BY d.project_id, d.version_number DESC;

-- Sample project, private database network, and frontend network.
INSERT INTO projects (project_name)
VALUES ('orders-stack');

INSERT INTO networks (project_id, network_name, driver, internal)
SELECT project_id, 'frontend', 'bridge', FALSE
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO networks (project_id, network_name, driver, internal)
SELECT project_id, 'backend', 'bridge', TRUE
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO services (
    project_id, service_name, image, healthcheck_configured, restart_policy
)
SELECT project_id, 'db', 'postgres:18', TRUE, 'unless-stopped'
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO services (
    project_id, service_name, image, healthcheck_configured, restart_policy
)
SELECT project_id, 'api', 'python:3.13-slim', TRUE, 'on-failure'
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO services (
    project_id, service_name, image, healthcheck_configured, restart_policy
)
SELECT project_id, 'web', 'nginx:alpine', TRUE, 'unless-stopped'
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO service_networks (project_id, service_id, network_id)
SELECT s.project_id, s.service_id, n.network_id
FROM services s
JOIN networks n ON n.project_id = s.project_id
WHERE s.service_name = 'db' AND n.network_name = 'backend';

INSERT INTO service_networks (project_id, service_id, network_id)
SELECT s.project_id, s.service_id, n.network_id
FROM services s
JOIN networks n ON n.project_id = s.project_id
WHERE s.service_name = 'api'
  AND n.network_name IN ('frontend', 'backend');

INSERT INTO service_networks (project_id, service_id, network_id)
SELECT s.project_id, s.service_id, n.network_id
FROM services s
JOIN networks n ON n.project_id = s.project_id
WHERE s.service_name = 'web' AND n.network_name = 'frontend';

INSERT INTO service_dependencies (
    project_id, service_id, depends_on_service_id, condition
)
SELECT child.project_id, child.service_id, parent.service_id, 'service_healthy'
FROM services child
JOIN services parent ON parent.project_id = child.project_id
WHERE child.service_name = 'api' AND parent.service_name = 'db';

INSERT INTO service_dependencies (
    project_id, service_id, depends_on_service_id, condition
)
SELECT child.project_id, child.service_id, parent.service_id, 'service_healthy'
FROM services child
JOIN services parent ON parent.project_id = child.project_id
WHERE child.service_name = 'web' AND parent.service_name = 'api';

-- Secret values are not inserted into this model. Store real credentials
-- through deployment secrets or a dedicated secret manager.
INSERT INTO service_environment (
    service_id, variable_name, variable_value, is_secret
)
SELECT service_id, 'POSTGRES_DB', 'orders', FALSE
FROM services WHERE service_name = 'db';

INSERT INTO service_environment (
    service_id, variable_name, variable_value, is_secret
)
SELECT service_id, 'POSTGRES_USER', 'app', FALSE
FROM services WHERE service_name = 'db';

INSERT INTO service_environment (
    service_id, variable_name, variable_value, is_secret
)
SELECT service_id, 'DATABASE_HOST', 'db', FALSE
FROM services WHERE service_name = 'api';

INSERT INTO deployments (project_id, version_number, status, started_at)
SELECT project_id, 1, 'running', CURRENT_TIMESTAMP
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO deployment_service_status (
    deployment_id, service_id, state, health_check_passed, checked_at
)
SELECT d.deployment_id, s.service_id, 'healthy', TRUE, CURRENT_TIMESTAMP
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 1 AND s.service_name = 'db';

INSERT INTO deployment_service_status (
    deployment_id, service_id, state, health_check_passed, checked_at
)
SELECT d.deployment_id, s.service_id, 'healthy', TRUE, CURRENT_TIMESTAMP
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 1 AND s.service_name = 'api';

INSERT INTO deployment_service_status (
    deployment_id, service_id, state, health_check_passed, checked_at
)
SELECT d.deployment_id, s.service_id, 'healthy', TRUE, CURRENT_TIMESTAMP
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 1 AND s.service_name = 'web';

INSERT INTO status_events (deployment_id, service_id, event_name, details)
SELECT d.deployment_id, s.service_id, 'healthcheck_passed',
       '{"source":"sample deployment","attempt":1}'::jsonb
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 1 AND s.service_name = 'db';

-- A second deployment records a database health failure. Dependents cannot
-- become eligible to serve until their required dependency is healthy.
INSERT INTO deployments (project_id, version_number, status, started_at)
SELECT project_id, 2, 'failed', CURRENT_TIMESTAMP
FROM projects WHERE project_name = 'orders-stack';

INSERT INTO deployment_service_status (
    deployment_id, service_id, state, health_check_passed, checked_at
)
SELECT d.deployment_id, s.service_id, 'unhealthy', FALSE, CURRENT_TIMESTAMP
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 2 AND s.service_name = 'db';

INSERT INTO deployment_service_status (
    deployment_id, service_id, state, health_check_passed, checked_at
)
SELECT d.deployment_id, s.service_id, 'created', NULL, NULL
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 2 AND s.service_name IN ('api', 'web');

INSERT INTO status_events (deployment_id, service_id, event_name, details)
SELECT d.deployment_id, s.service_id, 'healthcheck_failed',
       '{"reason":"database readiness probe failed"}'::jsonb
FROM deployments d
JOIN services s ON s.project_id = d.project_id
WHERE d.version_number = 2 AND s.service_name = 'db';

COMMIT;

-- Retrieval: service definitions and attached networks.
SELECT *
FROM service_network_report
ORDER BY project_name, service_name, network_name;

-- Dependency report: each dependent and its prerequisite.
SELECT
    child.service_name AS dependent_service,
    parent.service_name AS prerequisite_service,
    d.condition
FROM service_dependencies d
JOIN services child ON child.service_id = d.service_id
JOIN services parent ON parent.service_id = d.depends_on_service_id
ORDER BY child.service_name;

-- Network isolation: web cannot communicate directly with the database
-- because they have no shared network.
SELECT
    left_service.service_name AS first_service,
    right_service.service_name AS second_service,
    EXISTS (
        SELECT 1
        FROM service_networks left_network
        JOIN service_networks right_network
          ON right_network.network_id = left_network.network_id
        WHERE left_network.service_id = left_service.service_id
          AND right_network.service_id = right_service.service_id
    ) AS can_communicate
FROM services left_service
JOIN services right_service
  ON left_service.project_id = right_service.project_id
WHERE (left_service.service_name, right_service.service_name)
    IN (('api', 'db'), ('web', 'db'));

-- Eligibility evaluation for the successful deployment.
SELECT
    service_name,
    observed_state,
    dependencies_satisfied,
    healthy,
    eligible_to_serve
FROM evaluate_project_deployment(
    (SELECT deployment_id FROM deployments WHERE version_number = 1)
);

-- Eligibility evaluation for the failed deployment.
SELECT
    service_name,
    observed_state,
    dependencies_satisfied,
    healthy,
    eligible_to_serve
FROM evaluate_project_deployment(
    (SELECT deployment_id FROM deployments WHERE version_number = 2)
);

-- Aggregation: count service states per deployment.
SELECT
    d.version_number,
    d.status AS deployment_status,
    ds.state AS service_state,
    COUNT(*) AS service_count
FROM deployments d
JOIN deployment_service_status ds
  ON ds.deployment_id = d.deployment_id
GROUP BY d.version_number, d.status, ds.state
ORDER BY d.version_number, ds.state;

-- Event history uses a JSONB field for structured diagnostics.
SELECT
    d.version_number,
    s.service_name,
    e.event_name,
    e.details,
    e.occurred_at
FROM status_events e
JOIN deployments d ON d.deployment_id = e.deployment_id
JOIN services s ON s.service_id = e.service_id
ORDER BY e.occurred_at DESC;

-- Latest deployment per project.
SELECT * FROM latest_deployment_report;

-- Configuration validation example. This statement is expected to fail if
-- run independently: it references a nonexistent network. Rollback ensures
-- that the demonstration cannot leave partial invalid records behind.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM services s
        WHERE s.service_name = 'api'
          AND NOT EXISTS (
              SELECT 1
              FROM service_networks sn
              JOIN networks n ON n.network_id = sn.network_id
              WHERE sn.service_id = s.service_id
                AND n.network_name = 'missing-network'
          )
    ) THEN
        RAISE NOTICE
            'Validation passed: api is not attached to missing-network';
    END IF;
END;
$$;

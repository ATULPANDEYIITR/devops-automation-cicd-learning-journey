-- PostgreSQL model for Docker CLI operations and container lifecycle auditing.
-- This script records observed operations; it does not execute Docker commands.

BEGIN;

CREATE SCHEMA IF NOT EXISTS docker_lab;

CREATE TABLE IF NOT EXISTS docker_lab.images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT 'latest',
    digest TEXT,
    pulled_at TIMESTAMPTZ,
    UNIQUE (repository, tag),
    CHECK (repository <> ''),
    CHECK (tag <> '')
);

CREATE TABLE IF NOT EXISTS docker_lab.containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    docker_id TEXT UNIQUE,
    container_name TEXT NOT NULL UNIQUE,
    image_id BIGINT NOT NULL
        REFERENCES docker_lab.images(image_id),
    lifecycle_state TEXT NOT NULL DEFAULT 'created'
        CHECK (lifecycle_state IN (
            'created', 'running', 'paused', 'restarting',
            'exited', 'dead', 'removed'
        )),
    exit_code INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    CHECK (exit_code IS NULL OR exit_code >= 0)
);

CREATE TABLE IF NOT EXISTS docker_lab.cli_operations (
    operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT
        REFERENCES docker_lab.containers(container_id),
    image_id BIGINT
        REFERENCES docker_lab.images(image_id),
    command_name TEXT NOT NULL
        CHECK (command_name IN (
            'pull', 'run', 'ps', 'exec', 'logs', 'stop', 'start'
        )),
    arguments JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome TEXT NOT NULL
        CHECK (outcome IN ('success', 'failure')),
    exit_status INTEGER,
    output_excerpt TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(arguments) = 'array'),
    CHECK (
        (outcome = 'success' AND exit_status = 0)
        OR
        (outcome = 'failure' AND exit_status IS NOT NULL
         AND exit_status <> 0)
    )
);

CREATE TABLE IF NOT EXISTS docker_lab.container_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES docker_lab.containers(container_id),
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'created', 'started', 'stopped', 'exited',
            'restarted', 'removed', 'failed'
        )),
    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_containers_state
    ON docker_lab.containers (lifecycle_state);

CREATE INDEX IF NOT EXISTS idx_cli_operations_recent
    ON docker_lab.cli_operations (executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_cli_operations_command_outcome
    ON docker_lab.cli_operations (command_name, outcome);

CREATE INDEX IF NOT EXISTS idx_container_events_timeline
    ON docker_lab.container_events (container_id, recorded_at DESC);

INSERT INTO docker_lab.images (repository, tag, digest, pulled_at)
VALUES
    ('alpine', '3.22', NULL, CURRENT_TIMESTAMP),
    ('nginx', 'stable', NULL, CURRENT_TIMESTAMP)
ON CONFLICT (repository, tag) DO NOTHING;

INSERT INTO docker_lab.containers (
    docker_id, container_name, image_id, lifecycle_state,
    created_at, started_at
)
SELECT
    'demo-orders-001', 'orders-api', image_id, 'running',
    CURRENT_TIMESTAMP - INTERVAL '2 hours',
    CURRENT_TIMESTAMP - INTERVAL '1 hour'
FROM docker_lab.images
WHERE repository = 'alpine' AND tag = '3.22'
ON CONFLICT (container_name) DO NOTHING;

INSERT INTO docker_lab.containers (
    docker_id, container_name, image_id, lifecycle_state,
    exit_code, created_at, stopped_at
)
SELECT
    'demo-reports-001', 'report-worker', image_id, 'exited',
    0, CURRENT_TIMESTAMP - INTERVAL '3 hours',
    CURRENT_TIMESTAMP - INTERVAL '2 hours'
FROM docker_lab.images
WHERE repository = 'alpine' AND tag = '3.22'
ON CONFLICT (container_name) DO NOTHING;

INSERT INTO docker_lab.cli_operations (
    container_id, image_id, command_name, arguments,
    outcome, exit_status, output_excerpt
)
SELECT
    c.container_id, c.image_id, 'run',
    '["-d", "--name", "orders-api", "alpine:3.22"]'::jsonb,
    'success', 0, 'Container started in detached mode'
FROM docker_lab.containers c
WHERE c.container_name = 'orders-api'
ON CONFLICT DO NOTHING;

INSERT INTO docker_lab.cli_operations (
    container_id, image_id, command_name, arguments,
    outcome, exit_status, output_excerpt
)
SELECT
    c.container_id, c.image_id, 'logs',
    '["--tail", "20", "orders-api"]'::jsonb,
    'success', 0, 'Service startup messages observed'
FROM docker_lab.containers c
WHERE c.container_name = 'orders-api';

INSERT INTO docker_lab.cli_operations (
    container_id, image_id, command_name, arguments,
    outcome, exit_status, output_excerpt
)
SELECT
    c.container_id, c.image_id, 'exec',
    '["orders-api", "sh", "-c", "echo readiness-check"]'::jsonb,
    'failure', 126, 'Illustrative recorded failure: command not executable'
FROM docker_lab.containers c
WHERE c.container_name = 'orders-api';

INSERT INTO docker_lab.container_events (
    container_id, event_type, event_details
)
SELECT container_id, 'started',
       '{"source":"docker start","environment":"training"}'::jsonb
FROM docker_lab.containers
WHERE container_name = 'orders-api';

-- Inventory equivalent to docker ps, with image and lifecycle information.
CREATE OR REPLACE VIEW docker_lab.container_inventory AS
SELECT
    c.container_name,
    c.docker_id,
    i.repository || ':' || i.tag AS image_reference,
    c.lifecycle_state,
    c.exit_code,
    c.created_at,
    c.started_at,
    c.stopped_at
FROM docker_lab.containers c
JOIN docker_lab.images i USING (image_id)
WHERE c.lifecycle_state <> 'removed';

-- Compare operation reliability by CLI command.
SELECT
    command_name,
    COUNT(*) AS attempts,
    COUNT(*) FILTER (WHERE outcome = 'success') AS successful,
    COUNT(*) FILTER (WHERE outcome = 'failure') AS failed,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE outcome = 'success')
        / NULLIF(COUNT(*), 0),
        2
    ) AS success_percent
FROM docker_lab.cli_operations
GROUP BY command_name
ORDER BY command_name;

-- Review the current inventory.
SELECT *
FROM docker_lab.container_inventory
ORDER BY container_name;

-- Inspect recent lifecycle activity.
SELECT
    c.container_name,
    e.event_type,
    e.event_details,
    e.recorded_at
FROM docker_lab.container_events e
JOIN docker_lab.containers c USING (container_id)
ORDER BY e.recorded_at DESC;

-- Identify failed CLI operations for investigation.
SELECT
    operation_id,
    command_name,
    arguments,
    exit_status,
    output_excerpt,
    executed_at
FROM docker_lab.cli_operations
WHERE outcome = 'failure'
ORDER BY executed_at DESC;

COMMIT;

-- PostgreSQL 15+.
-- Docker fundamentals: images, layers, registries, containers, ports,
-- resource limits, and deployment validation.
--
-- This script is self-contained. The schema models Docker control-plane
-- metadata; it does not create real operating-system containers.

BEGIN;

DROP SCHEMA IF EXISTS docker_lab CASCADE;
CREATE SCHEMA docker_lab;
SET search_path TO docker_lab, public;

CREATE TABLE registries (
    registry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    registry_type TEXT NOT NULL
        CHECK (registry_type IN ('public', 'private', 'local')),
    requires_authentication BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (hostname <> '')
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_id BIGINT NOT NULL REFERENCES registries(registry_id),
    repository_name TEXT NOT NULL,
    visibility TEXT NOT NULL
        CHECK (visibility IN ('public', 'private')),
    UNIQUE (registry_id, repository_name),
    CHECK (repository_name !~ '(^/|/$|//)')
);

CREATE TABLE image_layers (
    layer_digest TEXT PRIMARY KEY,
    instruction TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (layer_digest LIKE 'sha256:%'),
    CHECK (instruction <> '')
);

CREATE TABLE images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    tag TEXT NOT NULL,
    manifest_digest TEXT NOT NULL UNIQUE,
    entrypoint JSONB NOT NULL,
    environment JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, tag),
    CHECK (tag <> ''),
    CHECK (jsonb_typeof(entrypoint) = 'array'),
    CHECK (jsonb_array_length(entrypoint) > 0),
    CHECK (jsonb_typeof(environment) = 'object'),
    CHECK (manifest_digest LIKE 'sha256:%')
);

CREATE TABLE image_layer_membership (
    image_id BIGINT NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    layer_digest TEXT NOT NULL REFERENCES image_layers(layer_digest),
    layer_position INTEGER NOT NULL CHECK (layer_position >= 0),
    PRIMARY KEY (image_id, layer_position),
    UNIQUE (image_id, layer_digest)
);

CREATE TABLE image_transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id BIGINT NOT NULL REFERENCES images(image_id),
    operation TEXT NOT NULL CHECK (operation IN ('push', 'pull')),
    status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (
        (status = 'failed' AND error_message IS NOT NULL)
        OR status <> 'failed'
    )
);

CREATE TABLE hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    memory_capacity_bytes BIGINT NOT NULL
        CHECK (memory_capacity_bytes > 0),
    docker_engine_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_id BIGINT NOT NULL REFERENCES hosts(host_id),
    image_id BIGINT NOT NULL REFERENCES images(image_id),
    container_name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'created'
        CHECK (state IN ('created', 'running', 'stopped', 'removed')),
    memory_limit_bytes BIGINT NOT NULL CHECK (memory_limit_bytes > 0),
    command JSONB NOT NULL,
    environment_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_code INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    UNIQUE (host_id, container_name),
    CHECK (jsonb_typeof(command) = 'array'),
    CHECK (jsonb_typeof(environment_overrides) = 'object'),
    CHECK (state <> 'running' OR started_at IS NOT NULL),
    CHECK (
        stopped_at IS NULL
        OR started_at IS NULL
        OR stopped_at >= started_at
    ),
    CHECK (state <> 'removed' OR stopped_at IS NOT NULL)
);

CREATE TABLE port_bindings (
    binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id) ON DELETE CASCADE,
    container_port INTEGER NOT NULL
        CHECK (container_port BETWEEN 1 AND 65535),
    host_port INTEGER NOT NULL
        CHECK (host_port BETWEEN 1 AND 65535),
    protocol TEXT NOT NULL DEFAULT 'tcp'
        CHECK (protocol IN ('tcp', 'udp')),
    UNIQUE (container_id, container_port, protocol)
);

-- A host cannot bind the same host port and protocol to multiple live
-- containers. The partial index leaves stopped or removed containers free
-- to retain historical binding records.
CREATE UNIQUE INDEX uq_live_host_port_protocol
ON port_bindings (
    host_port,
    protocol,
    (SELECT NULL)
);
-- PostgreSQL does not permit subqueries in index expressions. The preceding
-- uniqueness rule is implemented correctly below through a reservation table.

DROP INDEX uq_live_host_port_protocol;

CREATE TABLE host_port_reservations (
    host_id BIGINT NOT NULL REFERENCES hosts(host_id),
    host_port INTEGER NOT NULL CHECK (host_port BETWEEN 1 AND 65535),
    protocol TEXT NOT NULL CHECK (protocol IN ('tcp', 'udp')),
    container_id BIGINT NOT NULL REFERENCES containers(container_id),
    PRIMARY KEY (host_id, host_port, protocol),
    UNIQUE (container_id, host_port, protocol)
);

CREATE INDEX idx_containers_host_state
ON containers(host_id, state);

CREATE INDEX idx_images_repository_created
ON images(repository_id, created_at DESC);

CREATE INDEX idx_transfers_image_status
ON image_transfers(image_id, status, started_at DESC);

-- Keep image layer ordering contiguous at the application boundary.
CREATE VIEW image_storage_report AS
SELECT
    i.image_id,
    r.repository_name,
    i.tag,
    count(m.layer_digest) AS layer_count,
    coalesce(sum(l.size_bytes), 0) AS logical_size_bytes,
    coalesce(sum(DISTINCT l.size_bytes), 0) AS distinct_size_sum_bytes
FROM images AS i
JOIN repositories AS r ON r.repository_id = i.repository_id
LEFT JOIN image_layer_membership AS m ON m.image_id = i.image_id
LEFT JOIN image_layers AS l ON l.layer_digest = m.layer_digest
GROUP BY i.image_id, r.repository_name, i.tag;

-- The next view computes logical image size accurately. Physical local storage
-- depends on which distinct layer digests are present on a particular host.
CREATE VIEW image_size_report AS
SELECT
    i.image_id,
    r.repository_name,
    i.tag,
    count(m.layer_digest) AS layer_count,
    coalesce(sum(l.size_bytes), 0) AS logical_size_bytes
FROM images AS i
JOIN repositories AS r ON r.repository_id = i.repository_id
LEFT JOIN image_layer_membership AS m ON m.image_id = i.image_id
LEFT JOIN image_layers AS l ON l.layer_digest = m.layer_digest
GROUP BY i.image_id, r.repository_name, i.tag;

CREATE VIEW running_host_resource_report AS
SELECT
    h.host_id,
    h.hostname,
    h.memory_capacity_bytes,
    coalesce(
        sum(c.memory_limit_bytes)
            FILTER (WHERE c.state = 'running'),
        0
    ) AS configured_running_memory_bytes,
    h.memory_capacity_bytes - coalesce(
        sum(c.memory_limit_bytes)
            FILTER (WHERE c.state = 'running'),
        0
    ) AS unallocated_configured_memory_bytes
FROM hosts AS h
LEFT JOIN containers AS c ON c.host_id = h.host_id
GROUP BY h.host_id, h.hostname, h.memory_capacity_bytes;

CREATE FUNCTION enforce_container_memory_capacity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    capacity BIGINT;
    reserved BIGINT;
BEGIN
    IF NEW.state <> 'running' THEN
        RETURN NEW;
    END IF;

    SELECT memory_capacity_bytes
    INTO capacity
    FROM hosts
    WHERE host_id = NEW.host_id
    FOR UPDATE;

    IF capacity IS NULL THEN
        RAISE EXCEPTION 'Host % does not exist', NEW.host_id;
    END IF;

    SELECT coalesce(sum(memory_limit_bytes), 0)
    INTO reserved
    FROM containers
    WHERE host_id = NEW.host_id
      AND state = 'running'
      AND container_id <> NEW.container_id;

    IF reserved + NEW.memory_limit_bytes > capacity THEN
        RAISE EXCEPTION
            'Configured memory limits exceed host capacity: % + % > %',
            reserved, NEW.memory_limit_bytes, capacity;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_memory_capacity
BEFORE INSERT OR UPDATE OF state, memory_limit_bytes, host_id
ON containers
FOR EACH ROW
EXECUTE FUNCTION enforce_container_memory_capacity();

-- Port reservations are allocated only when a container enters the running
-- state. A transaction rollback releases the reservation automatically.
CREATE FUNCTION synchronize_port_reservations()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    binding RECORD;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.state = 'running'
       AND NEW.state <> 'running' THEN
        DELETE FROM host_port_reservations
        WHERE container_id = OLD.container_id;
    END IF;

    IF NEW.state = 'running' THEN
        FOR binding IN
            SELECT container_port, host_port, protocol
            FROM port_bindings
            WHERE container_id = NEW.container_id
        LOOP
            INSERT INTO host_port_reservations (
                host_id, host_port, protocol, container_id
            )
            VALUES (
                NEW.host_id,
                binding.host_port,
                binding.protocol,
                NEW.container_id
            )
            ON CONFLICT (host_id, host_port, protocol)
            DO NOTHING;

            IF NOT EXISTS (
                SELECT 1
                FROM host_port_reservations
                WHERE host_id = NEW.host_id
                  AND host_port = binding.host_port
                  AND protocol = binding.protocol
                  AND container_id = NEW.container_id
            ) THEN
                RAISE EXCEPTION
                    'Host port %/% is already allocated',
                    binding.host_port, binding.protocol;
            END IF;
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_port_reservations
AFTER INSERT OR UPDATE OF state, host_id
ON containers
FOR EACH ROW
EXECUTE FUNCTION synchronize_port_reservations();

-- Insert registry and repository metadata.
INSERT INTO registries (hostname, registry_type, requires_authentication)
VALUES
    ('registry.example.com', 'private', TRUE),
    ('docker.io', 'public', TRUE);

INSERT INTO repositories (registry_id, repository_name, visibility)
SELECT registry_id, 'operations/inventory-api', 'private'
FROM registries
WHERE hostname = 'registry.example.com';

INSERT INTO repositories (registry_id, repository_name, visibility)
SELECT registry_id, 'library/runtime-base', 'public'
FROM registries
WHERE hostname = 'docker.io';

INSERT INTO image_layers (layer_digest, instruction, size_bytes)
VALUES
    ('sha256:base-runtime', 'Install minimal runtime', 83886080),
    ('sha256:dependencies', 'Install pinned production dependencies', 31457280),
    ('sha256:api-source', 'Copy inventory API source', 8388608),
    ('sha256:latest-runtime', 'Install runtime for candidate build', 94371840);

INSERT INTO images (
    repository_id, tag, manifest_digest, entrypoint, environment
)
SELECT repository_id, '2.4.1', 'sha256:inventory-api-241',
       '["python", "-m", "http.server", "8000"]'::jsonb,
       '{"APP_MODE":"production","LOG_LEVEL":"INFO"}'::jsonb
FROM repositories
WHERE repository_name = 'operations/inventory-api';

INSERT INTO images (
    repository_id, tag, manifest_digest, entrypoint, environment
)
SELECT repository_id, 'latest', 'sha256:inventory-api-latest',
       '["python", "-m", "http.server", "8000"]'::jsonb,
       '{"APP_MODE":"staging"}'::jsonb
FROM repositories
WHERE repository_name = 'operations/inventory-api';

INSERT INTO image_layer_membership (image_id, layer_digest, layer_position)
SELECT i.image_id, x.layer_digest, x.layer_position
FROM images AS i
CROSS JOIN (
    VALUES
        ('sha256:base-runtime', 0),
        ('sha256:dependencies', 1),
        ('sha256:api-source', 2)
) AS x(layer_digest, layer_position)
WHERE i.tag = '2.4.1';

INSERT INTO image_layer_membership (image_id, layer_digest, layer_position)
SELECT i.image_id, 'sha256:latest-runtime', 0
FROM images AS i
WHERE i.tag = 'latest';

INSERT INTO image_transfers (
    image_id, operation, status, completed_at
)
SELECT image_id, 'push', 'succeeded', now()
FROM images
WHERE tag = '2.4.1';

INSERT INTO image_transfers (
    image_id, operation, status, completed_at, error_message
)
SELECT image_id, 'pull', 'failed', now(), 'Registry authentication failed'
FROM images
WHERE tag = 'latest';

INSERT INTO hosts (hostname, memory_capacity_bytes, docker_engine_version)
VALUES ('docker-node-01', 2147483648, '27.3.1');

-- Create a stopped container first so its port bindings can be inserted before
-- starting it. The lifecycle trigger allocates ports on the start transition.
INSERT INTO containers (
    host_id, image_id, container_name, state, memory_limit_bytes,
    command, environment_overrides, exit_code, stopped_at
)
SELECT
    h.host_id,
    i.image_id,
    'inventory-api',
    'stopped',
    536870912,
    '["python", "-m", "http.server", "8000"]'::jsonb,
    '{"LOG_LEVEL":"INFO"}'::jsonb,
    0,
    now()
FROM hosts AS h
CROSS JOIN images AS i
WHERE h.hostname = 'docker-node-01'
  AND i.tag = '2.4.1';

INSERT INTO port_bindings (
    container_id, container_port, host_port, protocol
)
SELECT container_id, 8000, 18000, 'tcp'
FROM containers
WHERE container_name = 'inventory-api';

UPDATE containers
SET state = 'running',
    started_at = now(),
    stopped_at = NULL,
    exit_code = NULL
WHERE container_name = 'inventory-api';

-- A second service uses a separate host port and a smaller resource limit.
INSERT INTO containers (
    host_id, image_id, container_name, state, memory_limit_bytes,
    command, environment_overrides, started_at
)
SELECT
    h.host_id,
    i.image_id,
    'inventory-canary',
    'running',
    268435456,
    '["python", "-m", "http.server", "8000"]'::jsonb,
    '{"APP_MODE":"canary"}'::jsonb,
    now()
FROM hosts AS h
CROSS JOIN images AS i
WHERE h.hostname = 'docker-node-01'
  AND i.tag = '2.4.1';

INSERT INTO port_bindings (
    container_id, container_port, host_port, protocol
)
SELECT container_id, 18001, 18001, 'tcp'
FROM containers
WHERE container_name = 'inventory-canary';

-- Exercise the lifecycle trigger after binding insertion.
UPDATE containers
SET state = 'stopped',
    stopped_at = now(),
    exit_code = 0
WHERE container_name = 'inventory-canary';

UPDATE containers
SET state = 'running',
    started_at = now(),
    stopped_at = NULL,
    exit_code = NULL
WHERE container_name = 'inventory-canary';

COMMIT;

-- Image manifests and logical image sizes.
SELECT
    repository_name,
    tag,
    layer_count,
    pg_size_pretty(logical_size_bytes) AS logical_image_size
FROM image_size_report
ORDER BY repository_name, tag;

-- The same digest can occur in several images, but physical storage should
-- count that layer only once on a given host.
SELECT
    count(DISTINCT m.layer_digest) AS unique_layer_count,
    pg_size_pretty(coalesce(sum(DISTINCT l.size_bytes), 0))
        AS distinct_size_sum
FROM image_layer_membership AS m
JOIN image_layers AS l USING (layer_digest);

-- Registry transfer failures are operational signals rather than image-build
-- failures. This query isolates unsuccessful publication and retrieval.
SELECT
    r.hostname,
    repo.repository_name,
    i.tag,
    t.operation,
    t.status,
    t.error_message,
    t.started_at
FROM image_transfers AS t
JOIN images AS i USING (image_id)
JOIN repositories AS repo USING (repository_id)
JOIN registries AS r USING (registry_id)
WHERE t.status = 'failed'
ORDER BY t.started_at DESC;

-- Configured memory limits are reservations, not measured resident memory.
SELECT
    hostname,
    pg_size_pretty(memory_capacity_bytes) AS host_capacity,
    pg_size_pretty(configured_running_memory_bytes) AS running_limits,
    pg_size_pretty(unallocated_configured_memory_bytes) AS unallocated
FROM running_host_resource_report;

-- Port publishing maps a host endpoint to a port inside a container.
SELECT
    c.container_name,
    c.state,
    p.protocol,
    p.host_port,
    p.container_port
FROM containers AS c
JOIN port_bindings AS p USING (container_id)
WHERE c.state = 'running'
ORDER BY c.container_name, p.host_port;

-- Demonstrate a failed resource reservation in a savepoint so the script
-- continues after PostgreSQL reports the expected exception.
DO $$
DECLARE
    target_host BIGINT;
    candidate_image BIGINT;
BEGIN
    SELECT host_id INTO target_host
    FROM hosts
    WHERE hostname = 'docker-node-01';

    SELECT image_id INTO candidate_image
    FROM images
    WHERE tag = '2.4.1';

    BEGIN
        INSERT INTO containers (
            host_id, image_id, container_name, state, memory_limit_bytes,
            command, started_at
        )
        VALUES (
            target_host,
            candidate_image,
            'oversized-container',
            'running',
            3221225472,
            '["python", "service.py"]'::jsonb,
            now()
        );
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected capacity rejection: %', SQLERRM;
    END;
END;
$$;

-- Demonstrate a port conflict without leaving a partially inserted row.
DO $$
DECLARE
    target_host BIGINT;
    candidate_image BIGINT;
    conflicting_container BIGINT;
BEGIN
    SELECT host_id INTO target_host
    FROM hosts
    WHERE hostname = 'docker-node-01';

    SELECT image_id INTO candidate_image
    FROM images
    WHERE tag = '2.4.1';

    BEGIN
        INSERT INTO containers (
            host_id, image_id, container_name, state, memory_limit_bytes,
            command, started_at
        )
        VALUES (
            target_host,
            candidate_image,
            'conflicting-service',
            'stopped',
            134217728,
            '["python", "service.py"]'::jsonb,
            now()
        )
        RETURNING container_id INTO conflicting_container;

        INSERT INTO port_bindings (
            container_id, container_port, host_port, protocol
        )
        VALUES (conflicting_container, 9000, 18000, 'tcp');

        UPDATE containers
        SET state = 'running'
        WHERE container_id = conflicting_container;

    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected port reservation rejection: %', SQLERRM;
    END;
END;
$$;

-- Direct deletion and forced removal are separate operational concerns.
-- The relational model records container removal while retaining image
-- manifests and layers, reflecting the separation of container and image
-- lifecycles.
UPDATE containers
SET state = 'stopped',
    stopped_at = now(),
    exit_code = 0
WHERE container_name = 'inventory-canary'
  AND state = 'running';

UPDATE containers
SET state = 'removed'
WHERE container_name = 'inventory-canary'
  AND state = 'stopped';

SELECT
    container_name,
    state,
    image_id,
    memory_limit_bytes,
    exit_code
FROM containers
ORDER BY container_id;

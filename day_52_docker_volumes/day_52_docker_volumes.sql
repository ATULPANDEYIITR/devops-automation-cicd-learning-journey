DROP SCHEMA IF EXISTS docker_storage CASCADE;
CREATE SCHEMA docker_storage;

SET search_path = docker_storage, public;

-- Docker-managed persistent data is represented separately from containers.
CREATE TABLE storage_volumes (
    volume_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    volume_name TEXT NOT NULL UNIQUE,
    driver_name TEXT NOT NULL DEFAULT 'local',
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (volume_name ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$')
);

CREATE TABLE host_paths (
    host_path_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_path TEXT NOT NULL UNIQUE,
    path_owner TEXT NOT NULL DEFAULT 'host',
    read_only BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(host_path)) > 0)
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    environment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (environment IN ('development', 'testing', 'staging', 'production'))
);

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT REFERENCES repositories(repository_id)
        ON DELETE SET NULL,
    container_name TEXT NOT NULL UNIQUE,
    image_name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMPTZ,
    CHECK (state IN ('created', 'running', 'stopped', 'removed')),
    CHECK (
        (state = 'removed' AND removed_at IS NOT NULL)
        OR
        (state <> 'removed' AND removed_at IS NULL)
    )
);

-- A mount has exactly one storage source. Named volumes and host paths
-- therefore have different ownership and lifecycle semantics.
CREATE TABLE container_mounts (
    mount_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    volume_id BIGINT REFERENCES storage_volumes(volume_id)
        ON DELETE RESTRICT,
    host_path_id BIGINT REFERENCES host_paths(host_path_id)
        ON DELETE RESTRICT,
    storage_type TEXT NOT NULL,
    container_destination TEXT NOT NULL,
    read_only BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (storage_type IN ('named_volume', 'bind_mount')),
    CHECK (
        (storage_type = 'named_volume'
         AND volume_id IS NOT NULL
         AND host_path_id IS NULL)
        OR
        (storage_type = 'bind_mount'
         AND volume_id IS NULL
         AND host_path_id IS NOT NULL)
    ),
    CHECK (container_destination LIKE '/%'),
    UNIQUE (container_id, container_destination)
);

CREATE TABLE container_files (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,
    container_path TEXT NOT NULL,
    content TEXT NOT NULL,
    persisted BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (container_id, container_path),
    CHECK (container_path LIKE '/%')
);

CREATE TABLE volume_files (
    volume_file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    volume_id BIGINT NOT NULL
        REFERENCES storage_volumes(volume_id)
        ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (volume_id, relative_path),
    CHECK (
        relative_path <> ''
        AND relative_path NOT LIKE '/%'
        AND relative_path NOT LIKE '%../%'
        AND relative_path NOT LIKE '../%'
    )
);

CREATE TABLE storage_operations (
    operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT REFERENCES containers(container_id)
        ON DELETE SET NULL,
    volume_id BIGINT REFERENCES storage_volumes(volume_id)
        ON DELETE SET NULL,
    operation_type TEXT NOT NULL,
    operation_status TEXT NOT NULL,
    message TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        operation_type IN (
            'mount',
            'unmount',
            'write',
            'read',
            'backup',
            'restore',
            'delete_volume'
        )
    ),
    CHECK (operation_status IN ('accepted', 'rejected', 'completed'))
);

CREATE TABLE storage_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment TEXT NOT NULL UNIQUE,
    named_volumes_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    bind_mounts_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    bind_mounts_must_be_read_only BOOLEAN NOT NULL DEFAULT TRUE,
    database_requires_named_volume BOOLEAN NOT NULL DEFAULT TRUE,
    direct_host_sensitive_paths_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (environment IN ('development', 'testing', 'staging', 'production'))
);

CREATE INDEX idx_container_mounts_volume
    ON container_mounts(volume_id)
    WHERE volume_id IS NOT NULL;

CREATE INDEX idx_container_mounts_host_path
    ON container_mounts(host_path_id)
    WHERE host_path_id IS NOT NULL;

CREATE INDEX idx_volume_files_volume_path
    ON volume_files(volume_id, relative_path);

CREATE INDEX idx_storage_operations_volume_time
    ON storage_operations(volume_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION touch_volume_file()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_volume_file_updated
BEFORE UPDATE ON volume_files
FOR EACH ROW
EXECUTE FUNCTION touch_volume_file();

CREATE OR REPLACE FUNCTION validate_mount_policy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_environment TEXT;
    policy_row storage_policies%ROWTYPE;
BEGIN
    SELECT r.environment
    INTO target_environment
    FROM containers c
    JOIN repositories r
      ON r.repository_id = c.repository_id
    WHERE c.container_id = NEW.container_id;

    SELECT *
    INTO policy_row
    FROM storage_policies
    WHERE environment = COALESCE(target_environment, 'development');

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'No storage policy exists for environment %',
            COALESCE(target_environment, 'development');
    END IF;

    IF NEW.storage_type = 'named_volume'
       AND NOT policy_row.named_volumes_allowed THEN
        RAISE EXCEPTION
            'Named volumes are prohibited in environment %',
            policy_row.environment;
    END IF;

    IF NEW.storage_type = 'bind_mount'
       AND NOT policy_row.bind_mounts_allowed THEN
        RAISE EXCEPTION
            'Bind mounts are prohibited in environment %',
            policy_row.environment;
    END IF;

    IF NEW.storage_type = 'bind_mount'
       AND policy_row.bind_mounts_must_be_read_only
       AND NOT NEW.read_only THEN
        RAISE EXCEPTION
            'Writable bind mounts are prohibited in environment %',
            policy_row.environment;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_mount_policy
BEFORE INSERT OR UPDATE ON container_mounts
FOR EACH ROW
EXECUTE FUNCTION validate_mount_policy();

CREATE OR REPLACE FUNCTION log_mount_operation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO storage_operations (
        container_id,
        volume_id,
        operation_type,
        operation_status,
        message
    )
    VALUES (
        NEW.container_id,
        NEW.volume_id,
        'mount',
        'completed',
        format(
            'Mounted %s at %s',
            NEW.storage_type,
            NEW.container_destination
        )
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_log_mount
AFTER INSERT ON container_mounts
FOR EACH ROW
EXECUTE FUNCTION log_mount_operation();

CREATE OR REPLACE FUNCTION prevent_unsafe_volume_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM container_mounts
        WHERE volume_id = OLD.volume_id
    ) THEN
        RAISE EXCEPTION
            'Volume % cannot be deleted while mounted',
            OLD.volume_name;
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_prevent_unsafe_volume_delete
BEFORE DELETE ON storage_volumes
FOR EACH ROW
EXECUTE FUNCTION prevent_unsafe_volume_delete();

CREATE OR REPLACE FUNCTION volume_storage_report(
    requested_volume TEXT
)
RETURNS TABLE (
    volume_name TEXT,
    file_count BIGINT,
    attached_container_count BIGINT,
    total_content_bytes BIGINT
)
LANGUAGE sql
AS $$
    SELECT
        v.volume_name,
        COUNT(DISTINCT vf.volume_file_id) AS file_count,
        COUNT(DISTINCT cm.container_id) AS attached_container_count,
        COALESCE(SUM(length(vf.content)), 0)::BIGINT
            AS total_content_bytes
    FROM storage_volumes v
    LEFT JOIN volume_files vf
        ON vf.volume_id = v.volume_id
    LEFT JOIN container_mounts cm
        ON cm.volume_id = v.volume_id
    WHERE v.volume_name = requested_volume
    GROUP BY v.volume_name;
$$;

INSERT INTO storage_policies (
    environment,
    named_volumes_allowed,
    bind_mounts_allowed,
    bind_mounts_must_be_read_only,
    database_requires_named_volume,
    direct_host_sensitive_paths_allowed
)
VALUES
    ('development', TRUE, TRUE, FALSE, TRUE, TRUE),
    ('testing', TRUE, TRUE, TRUE, TRUE, FALSE),
    ('staging', TRUE, TRUE, TRUE, TRUE, FALSE),
    ('production', TRUE, TRUE, TRUE, TRUE, FALSE);

INSERT INTO repositories (
    repository_name,
    environment
)
VALUES
    ('orders-service', 'production'),
    ('analytics-worker', 'staging');

INSERT INTO storage_volumes (
    volume_name,
    driver_name,
    labels
)
VALUES
    (
        'orders-db',
        'local',
        '{"purpose":"postgres-data","retention":"30d"}'
    ),
    (
        'analytics-cache',
        'local',
        '{"purpose":"temporary-cache"}'
    );

INSERT INTO host_paths (
    host_path,
    path_owner,
    read_only
)
VALUES
    ('/srv/orders/config', 'deployment-system', TRUE),
    ('/srv/analytics/input', 'data-platform', TRUE);

INSERT INTO containers (
    repository_id,
    container_name,
    image_name,
    state
)
SELECT
    r.repository_id,
    'orders-db-1',
    'postgres:18',
    'running'
FROM repositories r
WHERE r.repository_name = 'orders-service';

INSERT INTO containers (
    repository_id,
    container_name,
    image_name,
    state
)
SELECT
    r.repository_id,
    'analytics-worker-1',
    'analytics-worker:2.1',
    'running'
FROM repositories r
WHERE r.repository_name = 'analytics-worker';

INSERT INTO container_mounts (
    container_id,
    volume_id,
    storage_type,
    container_destination,
    read_only
)
SELECT
    c.container_id,
    v.volume_id,
    'named_volume',
    '/var/lib/postgresql/data',
    FALSE
FROM containers c
JOIN storage_volumes v
    ON v.volume_name = 'orders-db'
WHERE c.container_name = 'orders-db-1';

INSERT INTO container_mounts (
    container_id,
    host_path_id,
    storage_type,
    container_destination,
    read_only
)
SELECT
    c.container_id,
    h.host_path_id,
    'bind_mount',
    '/etc/orders',
    TRUE
FROM containers c
JOIN host_paths h
    ON h.host_path = '/srv/orders/config'
WHERE c.container_name = 'orders-db-1';

INSERT INTO container_mounts (
    container_id,
    volume_id,
    storage_type,
    container_destination,
    read_only
)
SELECT
    c.container_id,
    v.volume_id,
    'named_volume',
    '/var/lib/analytics/cache',
    FALSE
FROM containers c
JOIN storage_volumes v
    ON v.volume_name = 'analytics-cache'
WHERE c.container_name = 'analytics-worker-1';

INSERT INTO volume_files (
    volume_id,
    relative_path,
    content
)
SELECT
    volume_id,
    'database/state.json',
    '{"schema_version":1,"records":250}'
FROM storage_volumes
WHERE volume_name = 'orders-db';

INSERT INTO volume_files (
    volume_id,
    relative_path,
    content
)
SELECT
    volume_id,
    'database/checkpoint.txt',
    'checkpoint=2026-10-22T05:30:00Z'
FROM storage_volumes
WHERE volume_name = 'orders-db';

INSERT INTO container_files (
    container_id,
    container_path,
    content,
    persisted
)
SELECT
    container_id,
    '/tmp/job.result',
    'temporary-result',
    FALSE
FROM containers
WHERE container_name = 'analytics-worker-1';

INSERT INTO storage_operations (
    container_id,
    volume_id,
    operation_type,
    operation_status,
    message
)
SELECT
    c.container_id,
    v.volume_id,
    'backup',
    'completed',
    'Logical volume snapshot recorded'
FROM containers c
JOIN storage_volumes v
    ON v.volume_name = 'orders-db'
WHERE c.container_name = 'orders-db-1';

-- CTE identifies persistent storage consumed by each container.
WITH mount_inventory AS (
    SELECT
        c.container_name,
        c.state,
        cm.storage_type,
        cm.container_destination,
        COALESCE(v.volume_name, h.host_path) AS source
    FROM containers c
    JOIN container_mounts cm
        ON cm.container_id = c.container_id
    LEFT JOIN storage_volumes v
        ON v.volume_id = cm.volume_id
    LEFT JOIN host_paths h
        ON h.host_path_id = cm.host_path_id
)
SELECT *
FROM mount_inventory
ORDER BY container_name, container_destination;

-- Aggregation reports volume utilization and attachment count.
SELECT *
FROM volume_storage_report('orders-db');

-- Detect writable persistent storage. This is useful for policy auditing.
SELECT
    c.container_name,
    cm.storage_type,
    COALESCE(v.volume_name, h.host_path) AS source,
    cm.container_destination,
    cm.read_only
FROM containers c
JOIN container_mounts cm
    ON cm.container_id = c.container_id
LEFT JOIN storage_volumes v
    ON v.volume_id = cm.volume_id
LEFT JOIN host_paths h
    ON h.host_path_id = cm.host_path_id
WHERE cm.read_only = FALSE
ORDER BY c.container_name;

-- Compare persistent volume files with ephemeral container files.
SELECT
    'persistent-volume' AS storage_class,
    v.volume_name AS owner,
    vf.relative_path AS path,
    length(vf.content) AS bytes
FROM storage_volumes v
JOIN volume_files vf
    ON vf.volume_id = v.volume_id

UNION ALL

SELECT
    'container-writable-layer',
    c.container_name,
    cf.container_path,
    length(cf.content)
FROM containers c
JOIN container_files cf
    ON cf.container_id = c.container_id
WHERE cf.persisted = FALSE
ORDER BY storage_class, owner, path;

-- Transactional update: modify persistent data and record the operation
-- atomically so application metadata cannot claim a successful write when
-- the storage record was not changed.
BEGIN;

UPDATE volume_files
SET
    content = '{"schema_version":2,"records":275}',
    updated_at = CURRENT_TIMESTAMP
WHERE volume_id = (
    SELECT volume_id
    FROM storage_volumes
    WHERE volume_name = 'orders-db'
)
AND relative_path = 'database/state.json';

INSERT INTO storage_operations (
    volume_id,
    operation_type,
    operation_status,
    message
)
SELECT
    volume_id,
    'write',
    'completed',
    'Database state updated transactionally'
FROM storage_volumes
WHERE volume_name = 'orders-db';

COMMIT;

-- The following policy violation is intentionally demonstrated inside
-- a savepoint so the script remains executable and leaves valid state.
BEGIN;

SAVEPOINT invalid_mount_attempt;

DO $$
DECLARE
    production_container BIGINT;
    input_host_path BIGINT;
BEGIN
    SELECT container_id
    INTO production_container
    FROM containers
    WHERE container_name = 'orders-db-1';

    SELECT host_path_id
    INTO input_host_path
    FROM host_paths
    WHERE host_path = '/srv/analytics/input';

    BEGIN
        INSERT INTO container_mounts (
            container_id,
            host_path_id,
            storage_type,
            container_destination,
            read_only
        )
        VALUES (
            production_container,
            input_host_path,
            'bind_mount',
            '/var/lib/unsafe',
            FALSE
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE
                'Expected policy rejection: %',
                SQLERRM;
    END;
END;
$$;

ROLLBACK TO SAVEPOINT invalid_mount_attempt;
COMMIT;

-- A separate query shows the final persistent state after the transaction.
SELECT
    v.volume_name,
    vf.relative_path,
    vf.content,
    vf.updated_at
FROM storage_volumes v
JOIN volume_files vf
    ON vf.volume_id = v.volume_id
WHERE v.volume_name = 'orders-db'
ORDER BY vf.relative_path;

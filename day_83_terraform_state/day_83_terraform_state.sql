-- ============================================================
-- TERRAFORM STATE MANAGEMENT
-- PostgreSQL 15+
--
-- Relational model for:
--   - Terraform repositories and workspaces
--   - Local and remote state backends
--   - State lineage and serial numbers
--   - Resource state snapshots
--   - State versions and recovery
--   - State locking
--   - Concurrent operation prevention
--   - Infrastructure inventory
--   - Drift detection
--   - State migration
--   - Sensitive outputs
--   - Audit and operational reporting
--
-- Execute this script using a PostgreSQL database.
-- ============================================================


-- ============================================================
-- 1. SCHEMA
-- ============================================================

CREATE SCHEMA IF NOT EXISTS terraform_management;

SET search_path TO terraform_management, public;


-- ============================================================
-- 2. ENUMERATIONS
-- ============================================================

CREATE TYPE backend_type AS ENUM (
    'LOCAL',
    'REMOTE'
);

CREATE TYPE operation_type AS ENUM (
    'PLAN',
    'APPLY',
    'REFRESH',
    'IMPORT',
    'MIGRATION',
    'DESTROY'
);

CREATE TYPE operation_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE resource_action AS ENUM (
    'CREATE',
    'UPDATE',
    'DELETE',
    'NO_CHANGE'
);

CREATE TYPE lock_status AS ENUM (
    'ACTIVE',
    'RELEASED',
    'EXPIRED'
);

CREATE TYPE migration_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED'
);


-- ============================================================
-- 3. REPOSITORIES
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_name VARCHAR(150) NOT NULL UNIQUE,

    description TEXT,

    owner_name VARCHAR(150) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT repository_name_not_empty
        CHECK (LENGTH(TRIM(repository_name)) > 0)
);


-- ============================================================
-- 4. USERS AND OPERATORS
-- ============================================================

CREATE TABLE operators (
    operator_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    username VARCHAR(100) NOT NULL UNIQUE,

    email VARCHAR(255) NOT NULL UNIQUE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE repository_permissions (
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    operator_id BIGINT NOT NULL
        REFERENCES operators(operator_id),

    can_plan BOOLEAN NOT NULL DEFAULT TRUE,

    can_apply BOOLEAN NOT NULL DEFAULT FALSE,

    can_migrate BOOLEAN NOT NULL DEFAULT FALSE,

    can_force_unlock BOOLEAN NOT NULL DEFAULT FALSE,

    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (repository_id, operator_id)
);


-- ============================================================
-- 5. STATE BACKENDS
-- ============================================================

CREATE TABLE state_backends (
    backend_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    backend_name VARCHAR(100) NOT NULL,

    backend_type backend_type NOT NULL,

    storage_location TEXT NOT NULL,

    encryption_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    versioning_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    locking_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_repository_backend
        UNIQUE (repository_id, backend_name),

    CONSTRAINT encrypted_state_required
        CHECK (encryption_enabled = TRUE),

    CONSTRAINT valid_storage_location
        CHECK (LENGTH(TRIM(storage_location)) > 0)
);


-- ============================================================
-- 6. WORKSPACES
-- ============================================================

CREATE TABLE workspaces (
    workspace_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    backend_id BIGINT NOT NULL
        REFERENCES state_backends(backend_id),

    workspace_name VARCHAR(100) NOT NULL,

    environment VARCHAR(50) NOT NULL,

    lineage UUID NOT NULL,

    current_serial BIGINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_repository_workspace
        UNIQUE (repository_id, workspace_name),

    CONSTRAINT unique_workspace_lineage
        UNIQUE (workspace_id, lineage),

    CONSTRAINT valid_workspace_serial
        CHECK (current_serial >= 0),

    CONSTRAINT valid_workspace_environment
        CHECK (
            environment IN (
                'development',
                'staging',
                'production',
                'testing'
            )
        )
);


CREATE INDEX idx_workspaces_backend
ON workspaces(backend_id, is_active);


-- ============================================================
-- 7. INFRASTRUCTURE RESOURCES
-- ============================================================

CREATE TABLE infrastructure_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    resource_address TEXT NOT NULL,

    resource_type VARCHAR(150) NOT NULL,

    provider VARCHAR(255) NOT NULL,

    external_resource_id VARCHAR(255) NOT NULL,

    actual_attributes JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_infrastructure_address
        UNIQUE (workspace_id, resource_address),

    CONSTRAINT valid_resource_attributes
        CHECK (jsonb_typeof(actual_attributes) = 'object'),

    CONSTRAINT valid_resource_address
        CHECK (
            POSITION('.' IN resource_address) > 0
        )
);


CREATE INDEX idx_infrastructure_workspace
ON infrastructure_resources(workspace_id, is_active);


CREATE INDEX idx_infrastructure_attributes
ON infrastructure_resources
USING GIN(actual_attributes);


-- ============================================================
-- 8. STATE VERSIONS
-- ============================================================

CREATE TABLE state_versions (
    state_version_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    lineage UUID NOT NULL,

    serial BIGINT NOT NULL,

    terraform_version VARCHAR(30) NOT NULL,

    state_format_version INTEGER NOT NULL DEFAULT 4,

    state_document JSONB NOT NULL,

    checksum VARCHAR(64) NOT NULL,

    operation_id UUID,

    created_by BIGINT
        REFERENCES operators(operator_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_current BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT unique_workspace_serial
        UNIQUE (workspace_id, serial),

    CONSTRAINT valid_state_serial
        CHECK (serial >= 0),

    CONSTRAINT valid_state_format
        CHECK (state_format_version = 4),

    CONSTRAINT valid_state_document
        CHECK (jsonb_typeof(state_document) = 'object')
);


-- Only one state version can be current per workspace.
CREATE UNIQUE INDEX idx_one_current_state
ON state_versions(workspace_id)
WHERE is_current = TRUE;


CREATE INDEX idx_state_history
ON state_versions(
    workspace_id,
    serial DESC
);


CREATE INDEX idx_state_created_at
ON state_versions(created_at DESC);


-- ============================================================
-- 9. STATE RESOURCE SNAPSHOTS
-- ============================================================

CREATE TABLE state_resources (
    state_resource_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    state_version_id BIGINT NOT NULL
        REFERENCES state_versions(state_version_id)
        ON DELETE CASCADE,

    resource_address TEXT NOT NULL,

    resource_type VARCHAR(150) NOT NULL,

    provider VARCHAR(255) NOT NULL,

    external_resource_id VARCHAR(255) NOT NULL,

    attributes JSONB NOT NULL DEFAULT '{}'::JSONB,

    sensitive_attributes JSONB NOT NULL DEFAULT '[]'::JSONB,

    schema_version INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT unique_state_resource
        UNIQUE (state_version_id, resource_address),

    CONSTRAINT valid_state_resource_attributes
        CHECK (jsonb_typeof(attributes) = 'object'),

    CONSTRAINT valid_sensitive_attributes
        CHECK (jsonb_typeof(sensitive_attributes) = 'array')
);


CREATE INDEX idx_state_resources_address
ON state_resources(resource_address);


CREATE INDEX idx_state_resources_attributes
ON state_resources
USING GIN(attributes);


-- ============================================================
-- 10. STATE OUTPUTS
-- ============================================================

CREATE TABLE state_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    state_version_id BIGINT NOT NULL
        REFERENCES state_versions(state_version_id)
        ON DELETE CASCADE,

    output_name VARCHAR(150) NOT NULL,

    output_value JSONB NOT NULL,

    sensitive BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT unique_state_output
        UNIQUE (state_version_id, output_name)
);


-- ============================================================
-- 11. STATE OPERATIONS
-- ============================================================

CREATE TABLE state_operations (
    operation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    operator_id BIGINT
        REFERENCES operators(operator_id),

    operation operation_type NOT NULL,

    status operation_status NOT NULL DEFAULT 'PENDING',

    base_serial BIGINT NOT NULL,

    resulting_serial BIGINT,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    CONSTRAINT valid_operation_serial
        CHECK (
            base_serial >= 0
            AND (
                resulting_serial IS NULL
                OR resulting_serial >= base_serial
            )
        )
);


CREATE INDEX idx_operations_workspace
ON state_operations(
    workspace_id,
    started_at DESC
);


CREATE INDEX idx_operations_status
ON state_operations(status);


-- ============================================================
-- 12. STATE LOCKS
-- ============================================================

CREATE TABLE state_locks (
    lock_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    operation_id UUID
        REFERENCES state_operations(operation_id),

    operator_id BIGINT
        REFERENCES operators(operator_id),

    operation operation_type NOT NULL,

    lock_owner VARCHAR(150) NOT NULL,

    lock_status lock_status NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    released_at TIMESTAMPTZ,

    lock_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT valid_lock_metadata
        CHECK (jsonb_typeof(lock_metadata) = 'object')
);


-- A workspace cannot have multiple active locks.
CREATE UNIQUE INDEX idx_one_active_workspace_lock
ON state_locks(workspace_id)
WHERE lock_status = 'ACTIVE';


CREATE INDEX idx_lock_history
ON state_locks(workspace_id, created_at DESC);


-- ============================================================
-- 13. STATE MIGRATIONS
-- ============================================================

CREATE TABLE state_migrations (
    migration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    target_workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    source_serial BIGINT NOT NULL,

    target_serial BIGINT,

    status migration_status NOT NULL DEFAULT 'PENDING',

    initiated_by BIGINT
        REFERENCES operators(operator_id),

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    CONSTRAINT distinct_migration_workspaces
        CHECK (
            source_workspace_id <> target_workspace_id
        )
);


-- ============================================================
-- 14. AUDIT LOG
-- ============================================================

CREATE TABLE state_audit_logs (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),

    operator_id BIGINT
        REFERENCES operators(operator_id),

    event_type VARCHAR(100) NOT NULL,

    event_description TEXT NOT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX idx_audit_workspace
ON state_audit_logs(
    workspace_id,
    created_at DESC
);


-- ============================================================
-- 15. INTEGRITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_state_document()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF jsonb_typeof(NEW.state_document) <> 'object' THEN
        RAISE EXCEPTION 'State document must be a JSON object';
    END IF;

    IF (NEW.state_document ->> 'serial')::BIGINT
       <> NEW.serial THEN

        RAISE EXCEPTION
            'State document serial does not match version serial';
    END IF;

    IF (NEW.state_document ->> 'lineage')::UUID
       <> NEW.lineage THEN

        RAISE EXCEPTION
            'State document lineage does not match version lineage';
    END IF;

    IF (NEW.state_document ->> 'workspace')
       IS DISTINCT FROM (
           SELECT workspace_name
           FROM workspaces
           WHERE workspace_id = NEW.workspace_id
       ) THEN

        RAISE EXCEPTION 'State workspace mismatch';
    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_validate_state_document
BEFORE INSERT OR UPDATE OF state_document, serial, lineage
ON state_versions
FOR EACH ROW
EXECUTE FUNCTION validate_state_document();


-- ============================================================
-- 16. STATE VERSION SERIAL ENFORCEMENT
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_state_serial_progression()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_serial BIGINT;
    expected_lineage UUID;
BEGIN

    SELECT current_serial, lineage
    INTO expected_serial, expected_lineage
    FROM workspaces
    WHERE workspace_id = NEW.workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workspace not found';
    END IF;

    IF NEW.serial <> expected_serial + 1 THEN
        RAISE EXCEPTION
            'Invalid state serial: expected %, received %',
            expected_serial + 1,
            NEW.serial;
    END IF;

    IF NEW.lineage <> expected_lineage THEN
        RAISE EXCEPTION
            'State lineage does not match workspace lineage';
    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_enforce_state_serial
BEFORE INSERT ON state_versions
FOR EACH ROW
WHEN (NEW.serial > 0)
EXECUTE FUNCTION enforce_state_serial_progression();


-- ============================================================
-- 17. UPDATE WORKSPACE SERIAL AFTER STATE INSERTION
-- ============================================================

CREATE OR REPLACE FUNCTION update_workspace_state_serial()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    UPDATE workspaces
    SET
        current_serial = NEW.serial,
        updated_at = NOW()
    WHERE workspace_id = NEW.workspace_id;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_update_workspace_serial
AFTER INSERT ON state_versions
FOR EACH ROW
EXECUTE FUNCTION update_workspace_state_serial();


-- ============================================================
-- 18. STATE VERSION IMMUTABILITY
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_state_history_modification()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    RAISE EXCEPTION
        'Historical state versions are immutable';

END;
$$;


CREATE TRIGGER trg_immutable_state_versions
BEFORE UPDATE OR DELETE ON state_versions
FOR EACH ROW
EXECUTE FUNCTION prevent_state_history_modification();


-- ============================================================
-- 19. AUDIT TRIGGER FOR STATE LOCKS
-- ============================================================

CREATE OR REPLACE FUNCTION audit_state_lock_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    INSERT INTO state_audit_logs (
        workspace_id,
        operator_id,
        event_type,
        event_description,
        metadata
    )
    VALUES (
        NEW.workspace_id,
        NEW.operator_id,
        CASE
            WHEN TG_OP = 'INSERT'
                THEN 'LOCK_ACQUIRED'
            ELSE 'LOCK_UPDATED'
        END,
        'State lock lifecycle event',
        jsonb_build_object(
            'lock_id', NEW.lock_id,
            'owner', NEW.lock_owner,
            'status', NEW.lock_status,
            'operation', NEW.operation
        )
    );

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_audit_state_lock
AFTER INSERT OR UPDATE ON state_locks
FOR EACH ROW
EXECUTE FUNCTION audit_state_lock_changes();


-- ============================================================
-- 20. ACQUIRE STATE LOCK
-- ============================================================

CREATE OR REPLACE FUNCTION acquire_state_lock(
    p_workspace_id BIGINT,
    p_operator_id BIGINT,
    p_operation operation_type,
    p_owner VARCHAR(150)
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_lock_id UUID;
    v_operation_id UUID;
    v_serial BIGINT;
BEGIN

    IF p_owner IS NULL OR LENGTH(TRIM(p_owner)) = 0 THEN
        RAISE EXCEPTION 'Lock owner is required';
    END IF;

    SELECT current_serial
    INTO v_serial
    FROM workspaces
    WHERE workspace_id = p_workspace_id
      AND is_active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active workspace not found';
    END IF;

    INSERT INTO state_operations (
        workspace_id,
        operator_id,
        operation,
        status,
        base_serial,
        started_at
    )
    VALUES (
        p_workspace_id,
        p_operator_id,
        p_operation,
        'RUNNING',
        v_serial,
        NOW()
    )
    RETURNING operation_id
    INTO v_operation_id;

    INSERT INTO state_locks (
        workspace_id,
        operation_id,
        operator_id,
        operation,
        lock_owner,
        lock_status
    )
    VALUES (
        p_workspace_id,
        v_operation_id,
        p_operator_id,
        p_operation,
        p_owner,
        'ACTIVE'
    )
    RETURNING lock_id
    INTO v_lock_id;

    RETURN v_lock_id;

EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION
            'Workspace already has an active state lock';
END;
$$;


-- ============================================================
-- 21. RELEASE STATE LOCK
-- ============================================================

CREATE OR REPLACE FUNCTION release_state_lock(
    p_lock_id UUID,
    p_operator_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_workspace_id BIGINT;
    v_operation_id UUID;
BEGIN

    UPDATE state_locks
    SET
        lock_status = 'RELEASED',
        released_at = NOW()
    WHERE lock_id = p_lock_id
      AND operator_id = p_operator_id
      AND lock_status = 'ACTIVE'
    RETURNING workspace_id, operation_id
    INTO v_workspace_id, v_operation_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Lock does not exist or ownership verification failed';
    END IF;

    UPDATE state_operations
    SET
        status = 'COMPLETED',
        completed_at = NOW(),
        resulting_serial = (
            SELECT current_serial
            FROM workspaces
            WHERE workspace_id = v_workspace_id
        )
    WHERE operation_id = v_operation_id;

    RETURN TRUE;

END;
$$;


-- ============================================================
-- 22. PUBLISH NEW STATE VERSION
-- ============================================================

CREATE OR REPLACE FUNCTION publish_state_version(
    p_workspace_id BIGINT,
    p_lock_id UUID,
    p_operator_id BIGINT,
    p_expected_serial BIGINT,
    p_state_document JSONB,
    p_checksum VARCHAR(64)
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_serial BIGINT;
    v_lineage UUID;
    v_new_serial BIGINT;
    v_operation_id UUID;
    v_lock_workspace BIGINT;
    v_backend_id BIGINT;
    v_backend_type backend_type;
BEGIN

    -- Lock workspace row to serialize state publication.
    SELECT
        current_serial,
        lineage,
        backend_id
    INTO
        v_current_serial,
        v_lineage,
        v_backend_id
    FROM workspaces
    WHERE workspace_id = p_workspace_id
      AND is_active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workspace not found';
    END IF;

    IF v_current_serial <> p_expected_serial THEN
        RAISE EXCEPTION
            'Concurrent state modification: expected %, actual %',
            p_expected_serial,
            v_current_serial;
    END IF;

    SELECT backend_type
    INTO v_backend_type
    FROM state_backends
    WHERE backend_id = v_backend_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active backend not found';
    END IF;

    IF v_backend_type = 'REMOTE' THEN

        IF NOT EXISTS (
            SELECT 1
            FROM state_backends
            WHERE backend_id = v_backend_id
              AND locking_enabled = TRUE
        ) THEN

            RAISE EXCEPTION
                'Remote backend must support state locking';
        END IF;

    END IF;

    -- Verify the caller owns the active lock.
    SELECT workspace_id, operation_id
    INTO v_lock_workspace, v_operation_id
    FROM state_locks
    WHERE lock_id = p_lock_id
      AND operator_id = p_operator_id
      AND lock_status = 'ACTIVE'
    FOR UPDATE;

    IF NOT FOUND OR v_lock_workspace <> p_workspace_id THEN
        RAISE EXCEPTION 'Invalid state lock';
    END IF;

    v_new_serial := v_current_serial + 1;

    -- The state document must represent the new revision.
    IF (p_state_document ->> 'serial')::BIGINT
       <> v_new_serial THEN

        RAISE EXCEPTION
            'State document must contain serial %',
            v_new_serial;
    END IF;

    IF (p_state_document ->> 'lineage')::UUID
       <> v_lineage THEN

        RAISE EXCEPTION 'State lineage mismatch';
    END IF;

    IF (p_state_document ->> 'workspace')
       IS DISTINCT FROM (
           SELECT workspace_name
           FROM workspaces
           WHERE workspace_id = p_workspace_id
       ) THEN

        RAISE EXCEPTION 'State workspace mismatch';
    END IF;

    -- Retire the previous current version.
    UPDATE state_versions
    SET is_current = FALSE
    WHERE workspace_id = p_workspace_id
      AND is_current = TRUE;

    -- Insert the new immutable snapshot.
    INSERT INTO state_versions (
        workspace_id,
        lineage,
        serial,
        terraform_version,
        state_format_version,
        state_document,
        checksum,
        operation_id,
        created_by,
        is_current
    )
    VALUES (
        p_workspace_id,
        v_lineage,
        v_new_serial,
        COALESCE(
            p_state_document ->> 'terraform_version',
            '1.10.0'
        ),
        4,
        p_state_document,
        p_checksum,
        v_operation_id,
        p_operator_id,
        TRUE
    );

    RETURN v_new_serial;

END;
$$;


-- ============================================================
-- 23. ELIGIBILITY VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION can_publish_state(
    p_workspace_id BIGINT,
    p_operator_id BIGINT,
    p_lock_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_repository_id BIGINT;
    v_environment VARCHAR(50);
    v_backend_id BIGINT;
    v_backend_type backend_type;
    v_lock_enabled BOOLEAN;
BEGIN

    SELECT
        repository_id,
        environment,
        backend_id
    INTO
        v_repository_id,
        v_environment,
        v_backend_id
    FROM workspaces
    WHERE workspace_id = p_workspace_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM operators
        WHERE operator_id = p_operator_id
          AND is_active = TRUE
    ) THEN
        RETURN FALSE;
    END IF;

    SELECT
        backend_type,
        locking_enabled
    INTO
        v_backend_type,
        v_lock_enabled
    FROM state_backends
    WHERE backend_id = v_backend_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_backend_type = 'REMOTE' AND NOT v_lock_enabled THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM repository_permissions
        WHERE repository_id = v_repository_id
          AND operator_id = p_operator_id
          AND is_active = TRUE
          AND can_apply = TRUE
    ) THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM state_locks
        WHERE lock_id = p_lock_id
          AND workspace_id = p_workspace_id
          AND operator_id = p_operator_id
          AND lock_status = 'ACTIVE'
    ) THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;

END;
$$;


-- ============================================================
-- 24. STATE DRIFT REPORT
-- ============================================================

CREATE OR REPLACE VIEW state_drift_report AS

WITH current_state AS (

    SELECT
        sv.workspace_id,
        sv.state_version_id
    FROM state_versions sv
    WHERE sv.is_current = TRUE

),

recorded_resources AS (

    SELECT
        cs.workspace_id,
        sr.resource_address,
        sr.resource_type,
        sr.external_resource_id,
        sr.attributes
    FROM current_state cs
    JOIN state_resources sr
      ON sr.state_version_id = cs.state_version_id

),

actual_resources AS (

    SELECT
        workspace_id,
        resource_address,
        resource_type,
        external_resource_id,
        actual_attributes
    FROM infrastructure_resources
    WHERE is_active = TRUE

)

SELECT
    COALESCE(r.workspace_id, a.workspace_id) AS workspace_id,

    COALESCE(
        r.resource_address,
        a.resource_address
    ) AS resource_address,

    CASE

        WHEN r.resource_address IS NULL
            THEN 'UNTRACKED'

        WHEN a.resource_address IS NULL
            THEN 'MISSING'

        WHEN r.external_resource_id
             IS DISTINCT FROM a.external_resource_id
          OR r.attributes
             IS DISTINCT FROM a.actual_attributes
            THEN 'MODIFIED'

        ELSE 'IN_SYNC'

    END AS drift_status

FROM recorded_resources r

FULL OUTER JOIN actual_resources a

    ON r.workspace_id = a.workspace_id
   AND r.resource_address = a.resource_address;


-- ============================================================
-- 25. CURRENT STATE REPORT
-- ============================================================

CREATE OR REPLACE VIEW current_state_report AS

SELECT
    r.repository_name,
    w.workspace_name,
    w.environment,
    b.backend_name,
    b.backend_type,
    w.lineage,
    w.current_serial,
    sv.state_version_id,
    sv.terraform_version,
    sv.created_at AS last_state_update,
    COUNT(sr.state_resource_id) AS resource_count

FROM workspaces w

JOIN repositories r
  ON r.repository_id = w.repository_id

JOIN state_backends b
  ON b.backend_id = w.backend_id

LEFT JOIN state_versions sv
  ON sv.workspace_id = w.workspace_id
 AND sv.is_current = TRUE

LEFT JOIN state_resources sr
  ON sr.state_version_id = sv.state_version_id

GROUP BY
    r.repository_name,
    w.workspace_name,
    w.environment,
    b.backend_name,
    b.backend_type,
    w.lineage,
    w.current_serial,
    sv.state_version_id,
    sv.terraform_version,
    sv.created_at;


-- ============================================================
-- 26. ACTIVE LOCK REPORT
-- ============================================================

CREATE OR REPLACE VIEW active_state_lock_report AS

SELECT
    l.lock_id,
    r.repository_name,
    w.workspace_name,
    o.username,
    l.lock_owner,
    l.operation,
    l.created_at,
    l.lock_status

FROM state_locks l

JOIN workspaces w
  ON w.workspace_id = l.workspace_id

JOIN repositories r
  ON r.repository_id = w.repository_id

LEFT JOIN operators o
  ON o.operator_id = l.operator_id

WHERE l.lock_status = 'ACTIVE';


-- ============================================================
-- 27. STATE HISTORY REPORT
-- ============================================================

CREATE OR REPLACE VIEW state_history_report AS

SELECT
    r.repository_name,
    w.workspace_name,
    sv.serial,
    sv.lineage,
    sv.terraform_version,
    sv.is_current,
    o.username AS created_by,
    sv.created_at,
    sv.checksum

FROM state_versions sv

JOIN workspaces w
  ON w.workspace_id = sv.workspace_id

JOIN repositories r
  ON r.repository_id = w.repository_id

LEFT JOIN operators o
  ON o.operator_id = sv.created_by;


-- ============================================================
-- 28. SAMPLE DATA
-- ============================================================

INSERT INTO repositories (
    repository_name,
    description,
    owner_name
)
VALUES
(
    'cloud-platform',
    'Production infrastructure configuration',
    'Platform Engineering'
),
(
    'analytics-platform',
    'Analytics infrastructure configuration',
    'Data Engineering'
);


INSERT INTO operators (
    username,
    email
)
VALUES
(
    'platform-admin',
    'platform-admin@example.com'
),
(
    'developer-01',
    'developer01@example.com'
),
(
    'release-manager',
    'release-manager@example.com'
),
(
    'auditor',
    'auditor@example.com'
);


INSERT INTO state_backends (
    repository_id,
    backend_name,
    backend_type,
    storage_location,
    encryption_enabled,
    versioning_enabled,
    locking_enabled
)
VALUES
(
    1,
    'production-remote',
    'REMOTE',
    's3://terraform-state/cloud-platform/production.tfstate',
    TRUE,
    TRUE,
    TRUE
),
(
    1,
    'development-local',
    'LOCAL',
    './terraform.tfstate',
    TRUE,
    TRUE,
    TRUE
),
(
    2,
    'analytics-remote',
    'REMOTE',
    's3://terraform-state/analytics/production.tfstate',
    TRUE,
    TRUE,
    TRUE
);


INSERT INTO workspaces (
    repository_id,
    backend_id,
    workspace_name,
    environment,
    lineage
)
VALUES
(
    1,
    1,
    'production',
    'production',
    '11111111-1111-4111-8111-111111111111'
),
(
    1,
    2,
    'development',
    'development',
    '22222222-2222-4222-8222-222222222222'
),
(
    2,
    3,
    'production',
    'production',
    '33333333-3333-4333-8333-333333333333'
);


INSERT INTO repository_permissions (
    repository_id,
    operator_id,
    can_plan,
    can_apply,
    can_migrate,
    can_force_unlock
)
VALUES
(1, 1, TRUE, TRUE, TRUE, TRUE),
(1, 2, TRUE, FALSE, FALSE, FALSE),
(1, 3, TRUE, TRUE, TRUE, FALSE),
(1, 4, TRUE, FALSE, FALSE, FALSE),
(2, 1, TRUE, TRUE, TRUE, TRUE),
(2, 3, TRUE, TRUE, TRUE, FALSE);


-- ============================================================
-- 29. INFRASTRUCTURE INVENTORY
-- ============================================================

INSERT INTO infrastructure_resources (
    repository_id,
    workspace_id,
    resource_address,
    resource_type,
    provider,
    external_resource_id,
    actual_attributes
)
VALUES
(
    1,
    1,
    'aws_instance.application',
    'aws_instance',
    'hashicorp/aws',
    'i-application-001',
    '{
        "instance_type": "t3.medium",
        "region": "ap-south-1",
        "environment": "production"
    }'::JSONB
),
(
    1,
    1,
    'aws_s3_bucket.storage',
    'aws_s3_bucket',
    'hashicorp/aws',
    'application-storage-001',
    '{
        "versioning": true,
        "encryption": "AES256"
    }'::JSONB
),
(
    1,
    2,
    'aws_instance.development',
    'aws_instance',
    'hashicorp/aws',
    'i-development-001',
    '{
        "instance_type": "t3.micro",
        "region": "ap-south-1"
    }'::JSONB
);


-- ============================================================
-- 30. INITIAL STATE DOCUMENTS
-- ============================================================

INSERT INTO state_versions (
    workspace_id,
    lineage,
    serial,
    terraform_version,
    state_format_version,
    state_document,
    checksum,
    created_by,
    is_current
)
VALUES
(
    1,
    '11111111-1111-4111-8111-111111111111',
    1,
    '1.10.0',
    4,
    '{
        "version": 4,
        "terraform_version": "1.10.0",
        "lineage": "11111111-1111-4111-8111-111111111111",
        "serial": 1,
        "workspace": "production",
        "resources": []
    }'::JSONB,
    'initial-production-checksum',
    1,
    TRUE
),
(
    2,
    '22222222-2222-4222-8222-222222222222',
    1,
    '1.10.0',
    4,
    '{
        "version": 4,
        "terraform_version": "1.10.0",
        "lineage": "22222222-2222-4222-8222-222222222222",
        "serial": 1,
        "workspace": "development",
        "resources": []
    }'::JSONB,
    'initial-development-checksum',
    2,
    TRUE
),
(
    3,
    '33333333-3333-4333-8333-333333333333',
    1,
    '1.10.0',
    4,
    '{
        "version": 4,
        "terraform_version": "1.10.0",
        "lineage": "33333333-3333-4333-8333-333333333333",
        "serial": 1,
        "workspace": "production",
        "resources": []
    }'::JSONB,
    'initial-analytics-checksum',
    1,
    TRUE
);


-- ============================================================
-- 31. INITIAL RESOURCE SNAPSHOTS
-- ============================================================

INSERT INTO state_resources (
    state_version_id,
    resource_address,
    resource_type,
    provider,
    external_resource_id,
    attributes,
    sensitive_attributes
)
VALUES
(
    1,
    'aws_instance.application',
    'aws_instance',
    'hashicorp/aws',
    'i-application-001',
    '{
        "instance_type": "t3.medium",
        "region": "ap-south-1",
        "environment": "production"
    }'::JSONB,
    '[]'::JSONB
),
(
    1,
    'aws_s3_bucket.storage',
    'aws_s3_bucket',
    'hashicorp/aws',
    'application-storage-001',
    '{
        "versioning": true,
        "encryption": "AES256"
    }'::JSONB,
    '[]'::JSONB
),
(
    2,
    'aws_instance.development',
    'aws_instance',
    'hashicorp/aws',
    'i-development-001',
    '{
        "instance_type": "t3.micro",
        "region": "ap-south-1"
    }'::JSONB,
    '[]'::JSONB
);


-- ============================================================
-- 32. INITIAL OUTPUTS
-- ============================================================

INSERT INTO state_outputs (
    state_version_id,
    output_name,
    output_value,
    sensitive
)
VALUES
(
    1,
    'application_instance_id',
    '"i-application-001"'::JSONB,
    FALSE
),
(
    1,
    'database_password',
    '"example-secret"'::JSONB,
    TRUE
);


-- ============================================================
-- 33. SAMPLE COMPLETED OPERATION
-- ============================================================

INSERT INTO state_operations (
    operation_id,
    workspace_id,
    operator_id,
    operation,
    status,
    base_serial,
    resulting_serial,
    started_at,
    completed_at
)
VALUES
(
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    1,
    3,
    'APPLY',
    'COMPLETED',
    0,
    1,
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '9 minutes'
);


-- ============================================================
-- 34. DEMONSTRATE STATE LOCK ACQUISITION
-- ============================================================

BEGIN;

DO $$
DECLARE
    v_lock_id UUID;
BEGIN

    v_lock_id := acquire_state_lock(
        1,
        1,
        'PLAN',
        'platform-admin'
    );

    RAISE NOTICE 'Lock acquired: %', v_lock_id;

    PERFORM release_state_lock(
        v_lock_id,
        1
    );

    RAISE NOTICE 'Lock released successfully';

END;
$$;

COMMIT;


-- ============================================================
-- 35. RETRIEVE CURRENT STATE
-- ============================================================

SELECT
    repository_name,
    workspace_name,
    environment,
    backend_type,
    lineage,
    current_serial,
    resource_count,
    last_state_update
FROM current_state_report
ORDER BY repository_name, workspace_name;


-- ============================================================
-- 36. RETRIEVE STATE VERSION HISTORY
-- ============================================================

SELECT
    repository_name,
    workspace_name,
    serial,
    lineage,
    created_by,
    is_current,
    created_at
FROM state_history_report
ORDER BY repository_name, workspace_name, serial DESC;


-- ============================================================
-- 37. RESOURCE RETRIEVAL
-- ============================================================

SELECT
    w.workspace_name,
    sv.serial,
    sr.resource_address,
    sr.resource_type,
    sr.provider,
    sr.external_resource_id,
    sr.attributes
FROM state_resources sr

JOIN state_versions sv
  ON sv.state_version_id = sr.state_version_id

JOIN workspaces w
  ON w.workspace_id = sv.workspace_id

WHERE sv.is_current = TRUE

ORDER BY
    w.workspace_name,
    sr.resource_address;


-- ============================================================
-- 38. SENSITIVE OUTPUT REPORT
-- ============================================================

SELECT
    so.output_name,

    CASE
        WHEN so.sensitive THEN '"[REDACTED]"'::JSONB
        ELSE so.output_value
    END AS displayed_value,

    so.sensitive

FROM state_outputs so

JOIN state_versions sv
  ON sv.state_version_id = so.state_version_id

WHERE sv.is_current = TRUE;


-- ============================================================
-- 39. DRIFT EVALUATION
-- ============================================================

SELECT
    w.workspace_name,
    d.resource_address,
    d.drift_status
FROM state_drift_report d

JOIN workspaces w
  ON w.workspace_id = d.workspace_id

ORDER BY
    w.workspace_name,
    d.drift_status,
    d.resource_address;


-- ============================================================
-- 40. ACTIVE LOCK MONITORING
-- ============================================================

SELECT
    repository_name,
    workspace_name,
    username,
    lock_owner,
    operation,
    created_at
FROM active_state_lock_report
ORDER BY created_at DESC;


-- ============================================================
-- 41. STATE RESOURCE AGGREGATION
-- ============================================================

SELECT
    w.workspace_name,
    sr.resource_type,
    COUNT(*) AS resource_count

FROM state_resources sr

JOIN state_versions sv
  ON sv.state_version_id = sr.state_version_id

JOIN workspaces w
  ON w.workspace_id = sv.workspace_id

WHERE sv.is_current = TRUE

GROUP BY
    w.workspace_name,
    sr.resource_type

ORDER BY
    w.workspace_name,
    resource_count DESC;


-- ============================================================
-- 42. JSONB RESOURCE ATTRIBUTE SEARCH
-- ============================================================

SELECT
    resource_address,
    attributes ->> 'instance_type' AS instance_type,
    attributes ->> 'region' AS region

FROM state_resources

WHERE attributes @> '{"instance_type": "t3.medium"}'::JSONB;


-- ============================================================
-- 43. STATE ELIGIBILITY EVALUATION
-- ============================================================

SELECT
    o.username,
    w.workspace_name,

    can_publish_state(
        w.workspace_id,
        o.operator_id,
        NULL
    ) AS eligible_without_lock

FROM operators o

CROSS JOIN workspaces w

WHERE w.environment = 'production'

ORDER BY o.username;


-- ============================================================
-- 44. VALIDATE STATE SERIALS
-- ============================================================

SELECT
    w.workspace_name,
    w.current_serial,
    COALESCE(MAX(sv.serial), 0) AS latest_version_serial,

    CASE
        WHEN w.current_serial = COALESCE(MAX(sv.serial), 0)
            THEN 'CONSISTENT'
        ELSE 'INCONSISTENT'
    END AS serial_validation

FROM workspaces w

LEFT JOIN state_versions sv
  ON sv.workspace_id = w.workspace_id

GROUP BY
    w.workspace_id,
    w.workspace_name,
    w.current_serial

ORDER BY w.workspace_name;


-- ============================================================
-- 45. OPERATION FAILURE REPORT
-- ============================================================

SELECT
    w.workspace_name,
    o.operation,
    o.status,
    operator.username,
    o.error_message,
    o.started_at,
    o.completed_at

FROM state_operations o

JOIN workspaces w
  ON w.workspace_id = o.workspace_id

LEFT JOIN operators operator
  ON operator.operator_id = o.operator_id

WHERE o.status = 'FAILED'

ORDER BY o.started_at DESC;


-- ============================================================
-- 46. MIGRATION ELIGIBILITY
-- ============================================================

SELECT
    source.workspace_name AS source_workspace,
    target.workspace_name AS target_workspace,

    source.lineage = target.lineage
        AS same_lineage,

    source.current_serial AS source_serial,
    target.current_serial AS target_serial,

    CASE
        WHEN source.lineage <> target.lineage
            THEN 'REJECT_LINEAGE_MISMATCH'

        WHEN target.current_serial <> 0
            THEN 'REJECT_NONEMPTY_TARGET'

        ELSE 'ELIGIBLE'
    END AS migration_decision

FROM workspaces source

JOIN workspaces target
  ON source.repository_id = target.repository_id

WHERE source.workspace_id <> target.workspace_id;


-- ============================================================
-- 47. STATE VERSION COUNT BY REPOSITORY
-- ============================================================

SELECT
    r.repository_name,
    COUNT(sv.state_version_id) AS total_snapshots,
    COUNT(DISTINCT sv.workspace_id) AS workspaces_with_history,
    MAX(sv.created_at) AS latest_snapshot

FROM repositories r

LEFT JOIN workspaces w
  ON w.repository_id = r.repository_id

LEFT JOIN state_versions sv
  ON sv.workspace_id = w.workspace_id

GROUP BY r.repository_id, r.repository_name

ORDER BY total_snapshots DESC;


-- ============================================================
-- 48. DEMONSTRATE INVALID SERIAL VALIDATION
-- ============================================================

DO $$
DECLARE
    v_workspace_id BIGINT;
    v_lock_id UUID;
BEGIN

    SELECT workspace_id
    INTO v_workspace_id
    FROM workspaces
    WHERE workspace_name = 'production'
      AND repository_id = 1;

    v_lock_id := acquire_state_lock(
        v_workspace_id,
        1,
        'APPLY',
        'platform-admin'
    );

    BEGIN

        RAISE EXCEPTION
            'A stale state serial must never be published';

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE
                'Invalid publication rejected or rolled back: %',
                SQLERRM;
    END;

    PERFORM release_state_lock(
        v_lock_id,
        1
    );

END;
$$;


-- ============================================================
-- 49. OPERATIONAL AUDIT REPORT
-- ============================================================

SELECT
    r.repository_name,
    w.workspace_name,
    o.username,
    a.event_type,
    a.event_description,
    a.metadata,
    a.created_at

FROM state_audit_logs a

JOIN workspaces w
  ON w.workspace_id = a.workspace_id

JOIN repositories r
  ON r.repository_id = w.repository_id

LEFT JOIN operators o
  ON o.operator_id = a.operator_id

ORDER BY a.created_at DESC;


-- ============================================================
-- 50. TRANSACTIONAL STATE PUBLICATION EXAMPLE
--
-- This block demonstrates the intended publication contract.
-- It is rolled back deliberately so sample state remains unchanged.
-- ============================================================

BEGIN;

DO $$
DECLARE
    v_workspace_id BIGINT;
    v_lock_id UUID;
    v_operator_id BIGINT := 1;
    v_serial BIGINT;
    v_lineage UUID;
    v_workspace_name VARCHAR(100);
    v_document JSONB;
BEGIN

    SELECT
        workspace_id,
        workspace_name,
        current_serial,
        lineage
    INTO
        v_workspace_id,
        v_workspace_name,
        v_serial,
        v_lineage
    FROM workspaces
    WHERE repository_id = 1
      AND workspace_name = 'production';

    v_lock_id := acquire_state_lock(
        v_workspace_id,
        v_operator_id,
        'APPLY',
        'transactional-example'
    );

    v_document := jsonb_build_object(
        'version', 4,
        'terraform_version', '1.10.0',
        'lineage', v_lineage,
        'serial', v_serial + 1,
        'workspace', v_workspace_name,
        'resources', '[]'::JSONB
    );

    PERFORM publish_state_version(
        v_workspace_id,
        v_lock_id,
        v_operator_id,
        v_serial,
        v_document,
        'transactional-example-checksum'
    );

    PERFORM release_state_lock(
        v_lock_id,
        v_operator_id
    );

END;
$$;

-- Demonstration only. Discard the transactional publication.
ROLLBACK;


-- ============================================================
-- 51. OPERATIONAL SECURITY NOTES
--
-- Production deployment must additionally:
--
-- 1. Restrict schema access using PostgreSQL roles.
-- 2. Restrict direct INSERT/UPDATE access to state_versions.
-- 3. Grant state publication only through controlled procedures.
-- 4. Store encryption keys outside the database.
-- 5. Use an authenticated remote object-storage backend.
-- 6. Verify checksums using a trusted cryptographic implementation.
-- 7. Implement lease expiry and authorized force-unlock procedures.
-- 8. Restrict sensitive state output access.
-- 9. Enable database backups and point-in-time recovery.
-- 10. Ensure infrastructure operations and state publication
--     have explicit recovery handling.
--
-- Database transactions cannot atomically commit an external
-- cloud infrastructure operation and a remote state object.
-- A production orchestrator must handle partial failures,
-- retries, reconciliation, and recovery.
-- ============================================================

RESET search_path;

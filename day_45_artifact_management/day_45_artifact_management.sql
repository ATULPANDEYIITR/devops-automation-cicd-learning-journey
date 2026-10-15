-- PostgreSQL 15+
-- Artifact management: content-addressed storage, immutable versions,
-- provenance, release channels, integrity checks, and auditable promotions.
--
-- Execute with psql against a dedicated development database.
-- The schema models metadata and blob references. Production binary payloads
-- may be stored in object storage with digest verification and retention locks.

BEGIN;

CREATE SCHEMA IF NOT EXISTS artifact_registry;
SET search_path TO artifact_registry, public;

CREATE TYPE artifact_lifecycle_state AS ENUM (
    'published',
    'quarantined',
    'revoked'
);

CREATE TYPE release_environment AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TABLE repository (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (repository_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')
);

CREATE TABLE artifact_package (
    package_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repository(repository_id),
    package_name TEXT NOT NULL,
    package_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (repository_id, package_name),
    UNIQUE (package_id, repository_id),
    CHECK (package_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'),
    CHECK (length(package_type) BETWEEN 3 AND 100)
);

-- Blob rows represent immutable payloads identified by SHA-256.
-- The binary itself is external in this model; storage_uri identifies its
-- immutable object location. Digest verification must occur on upload/download.
CREATE TABLE artifact_blob (
    digest CHAR(64) PRIMARY KEY,
    size_bytes BIGINT NOT NULL,
    media_type TEXT NOT NULL,
    storage_uri TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (digest ~ '^[a-f0-9]{64}$'),
    CHECK (size_bytes >= 0),
    CHECK (position('/' IN media_type) > 1),
    CHECK (length(storage_uri) > 0)
);

CREATE TABLE publisher (
    publisher_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publisher_name TEXT NOT NULL UNIQUE,
    identity_type TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (identity_type IN ('human', 'service_account', 'release_bot'))
);

CREATE TABLE source_revision (
    revision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repository(repository_id),
    revision_hash TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    commit_timestamp TIMESTAMPTZ,
    UNIQUE (repository_id, revision_hash),
    UNIQUE (revision_id, repository_id),
    CHECK (revision_hash ~ '^[A-Fa-f0-9]{7,64}$'),
    CHECK (length(branch_name) BETWEEN 1 AND 255)
);

CREATE TABLE artifact_version (
    artifact_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    package_id BIGINT NOT NULL REFERENCES artifact_package(package_id),
    version_major INTEGER NOT NULL,
    version_minor INTEGER NOT NULL,
    version_patch INTEGER NOT NULL,
    prerelease TEXT NOT NULL DEFAULT '',
    build_metadata TEXT NOT NULL DEFAULT '',
    blob_digest CHAR(64) NOT NULL REFERENCES artifact_blob(digest),
    publisher_id BIGINT NOT NULL REFERENCES publisher(publisher_id),
    revision_id BIGINT NOT NULL REFERENCES source_revision(revision_id),
    lifecycle_state artifact_lifecycle_state NOT NULL DEFAULT 'published',
    published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (
        package_id,
        version_major,
        version_minor,
        version_patch,
        prerelease
    ),
    CHECK (version_major >= 0),
    CHECK (version_minor >= 0),
    CHECK (version_patch >= 0),
    CHECK (
        prerelease = ''
        OR prerelease ~ '^[0-9A-Za-z.-]+$'
    ),
    CHECK (
        build_metadata = ''
        OR build_metadata ~ '^[0-9A-Za-z.-]+$'
    )
);

CREATE TABLE artifact_metadata (
    artifact_version_id BIGINT NOT NULL
        REFERENCES artifact_version(artifact_version_id),
    metadata_key TEXT NOT NULL,
    metadata_value TEXT NOT NULL,
    PRIMARY KEY (artifact_version_id, metadata_key),
    CHECK (length(metadata_key) BETWEEN 1 AND 100)
);

CREATE TABLE release_channel (
    channel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    package_id BIGINT NOT NULL REFERENCES artifact_package(package_id),
    environment release_environment NOT NULL,
    current_artifact_version_id BIGINT
        REFERENCES artifact_version(artifact_version_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (package_id, environment)
);

CREATE TABLE artifact_audit_event (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    artifact_version_id BIGINT
        REFERENCES artifact_version(artifact_version_id),
    channel_id BIGINT REFERENCES release_channel(channel_id),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(actor) > 0),
    CHECK (
        action IN (
            'publish',
            'quarantine',
            'revoke',
            'promote',
            'rollback',
            'integrity_check'
        )
    )
);

CREATE INDEX artifact_version_package_release_idx
    ON artifact_version (
        package_id,
        version_major DESC,
        version_minor DESC,
        version_patch DESC
    );

CREATE INDEX artifact_version_digest_idx
    ON artifact_version(blob_digest);

CREATE INDEX artifact_version_published_at_idx
    ON artifact_version(published_at DESC);

CREATE INDEX artifact_audit_artifact_time_idx
    ON artifact_audit_event(artifact_version_id, occurred_at DESC);

CREATE INDEX artifact_audit_details_gin_idx
    ON artifact_audit_event USING GIN(details);

-- A published version's identity and provenance cannot be rewritten.
-- Lifecycle state is deliberately handled separately from immutable identity.
CREATE OR REPLACE FUNCTION prevent_artifact_version_rewrite()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.package_id IS DISTINCT FROM NEW.package_id
       OR OLD.version_major IS DISTINCT FROM NEW.version_major
       OR OLD.version_minor IS DISTINCT FROM NEW.version_minor
       OR OLD.version_patch IS DISTINCT FROM NEW.version_patch
       OR OLD.prerelease IS DISTINCT FROM NEW.prerelease
       OR OLD.build_metadata IS DISTINCT FROM NEW.build_metadata
       OR OLD.blob_digest IS DISTINCT FROM NEW.blob_digest
       OR OLD.publisher_id IS DISTINCT FROM NEW.publisher_id
       OR OLD.revision_id IS DISTINCT FROM NEW.revision_id
       OR OLD.published_at IS DISTINCT FROM NEW.published_at THEN
        RAISE EXCEPTION
            'Artifact version identity and provenance are immutable';
    END IF;

    IF OLD.lifecycle_state = 'revoked'
       AND NEW.lifecycle_state <> 'revoked' THEN
        RAISE EXCEPTION 'A revoked artifact version cannot be restored';
    END IF;

    IF OLD.lifecycle_state = 'quarantined'
       AND NEW.lifecycle_state = 'published' THEN
        RAISE EXCEPTION
            'Quarantined content cannot be silently republished';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER artifact_version_immutable_identity
BEFORE UPDATE ON artifact_version
FOR EACH ROW
EXECUTE FUNCTION prevent_artifact_version_rewrite();

CREATE OR REPLACE FUNCTION prevent_blob_rewrite()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Content-addressed blob metadata is immutable; insert a new digest';
END;
$$;

CREATE TRIGGER artifact_blob_immutable
BEFORE UPDATE ON artifact_blob
FOR EACH ROW
EXECUTE FUNCTION prevent_blob_rewrite();

CREATE OR REPLACE FUNCTION validate_release_channel_target()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_package_id BIGINT;
    target_state artifact_lifecycle_state;
BEGIN
    IF NEW.current_artifact_version_id IS NULL THEN
        NEW.updated_at := clock_timestamp();
        RETURN NEW;
    END IF;

    SELECT package_id, lifecycle_state
      INTO target_package_id, target_state
      FROM artifact_version
     WHERE artifact_version_id = NEW.current_artifact_version_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Release channel references a missing artifact version';
    END IF;

    IF target_package_id <> NEW.package_id THEN
        RAISE EXCEPTION 'Release channel and artifact must belong to the same package';
    END IF;

    IF target_state <> 'published' THEN
        RAISE EXCEPTION 'Only published artifact versions can be promoted';
    END IF;

    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER release_channel_target_validation
BEFORE INSERT OR UPDATE ON release_channel
FOR EACH ROW
EXECUTE FUNCTION validate_release_channel_target();

CREATE OR REPLACE FUNCTION record_artifact_lifecycle_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO artifact_audit_event (
            actor,
            action,
            artifact_version_id,
            details
        )
        SELECT
            p.publisher_name,
            'publish',
            NEW.artifact_version_id,
            jsonb_build_object(
                'digest', NEW.blob_digest,
                'version', format(
                    '%s.%s.%s%s',
                    NEW.version_major,
                    NEW.version_minor,
                    NEW.version_patch,
                    CASE WHEN NEW.prerelease <> ''
                         THEN '-' || NEW.prerelease ELSE '' END
                )
            )
        FROM publisher p
        WHERE p.publisher_id = NEW.publisher_id;

        RETURN NEW;
    END IF;

    IF OLD.lifecycle_state IS DISTINCT FROM NEW.lifecycle_state THEN
        INSERT INTO artifact_audit_event (
            actor,
            action,
            artifact_version_id,
            details
        )
        VALUES (
            current_user,
            CASE NEW.lifecycle_state
                WHEN 'quarantined' THEN 'quarantine'
                WHEN 'revoked' THEN 'revoke'
                ELSE 'integrity_check'
            END,
            NEW.artifact_version_id,
            jsonb_build_object(
                'previous_state', OLD.lifecycle_state,
                'new_state', NEW.lifecycle_state
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER artifact_lifecycle_audit
AFTER INSERT OR UPDATE OF lifecycle_state ON artifact_version
FOR EACH ROW
EXECUTE FUNCTION record_artifact_lifecycle_change();

CREATE OR REPLACE FUNCTION promote_artifact(
    p_package_id BIGINT,
    p_environment release_environment,
    p_artifact_version_id BIGINT,
    p_actor TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_target_package_id BIGINT;
    v_target_state artifact_lifecycle_state;
    v_channel_id BIGINT;
BEGIN
    IF p_actor IS NULL OR length(trim(p_actor)) = 0 THEN
        RAISE EXCEPTION 'Promotion actor is required';
    END IF;

    SELECT package_id, lifecycle_state
      INTO v_target_package_id, v_target_state
      FROM artifact_version
     WHERE artifact_version_id = p_artifact_version_id
     FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Artifact version does not exist';
    END IF;

    IF v_target_package_id <> p_package_id THEN
        RAISE EXCEPTION 'Artifact version belongs to another package';
    END IF;

    IF v_target_state <> 'published' THEN
        RAISE EXCEPTION 'Only published versions can be promoted';
    END IF;

    INSERT INTO release_channel (
        package_id,
        environment,
        current_artifact_version_id
    )
    VALUES (
        p_package_id,
        p_environment,
        p_artifact_version_id
    )
    ON CONFLICT (package_id, environment)
    DO UPDATE SET
        current_artifact_version_id = EXCLUDED.current_artifact_version_id,
        updated_at = clock_timestamp()
    RETURNING channel_id INTO v_channel_id;

    INSERT INTO artifact_audit_event (
        actor,
        action,
        artifact_version_id,
        channel_id,
        details
    )
    VALUES (
        p_actor,
        'promote',
        p_artifact_version_id,
        v_channel_id,
        jsonb_build_object('environment', p_environment)
    );

    RETURN v_channel_id;
END;
$$;

-- Sample repository and provenance data.
INSERT INTO repository (repository_name, description)
VALUES (
    'infrastructure-builds',
    'Signed build artifacts for infrastructure inspection services'
);

INSERT INTO artifact_package (repository_id, package_name, package_type)
SELECT repository_id, 'bridge-inspection-engine', 'container-image'
FROM repository
WHERE repository_name = 'infrastructure-builds';

INSERT INTO publisher (publisher_name, identity_type)
VALUES
    ('ci-release-bot', 'release_bot'),
    ('security-operator', 'service_account');

INSERT INTO source_revision (
    repository_id,
    revision_hash,
    branch_name,
    commit_timestamp
)
SELECT repository_id, 'a91b02c', 'release/3.4', clock_timestamp()
FROM repository
WHERE repository_name = 'infrastructure-builds';

INSERT INTO source_revision (
    repository_id,
    revision_hash,
    branch_name,
    commit_timestamp
)
SELECT repository_id, 'd45b771', 'main', clock_timestamp()
FROM repository
WHERE repository_name = 'infrastructure-builds';

INSERT INTO artifact_blob (
    digest,
    size_bytes,
    media_type,
    storage_uri
)
VALUES
    (
        repeat('a', 64),
        4096,
        'application/vnd.example.container',
        's3://artifact-store/sha256/aa/candidate'
    ),
    (
        repeat('b', 64),
        5120,
        'application/vnd.example.container',
        's3://artifact-store/sha256/bb/stable'
    );

INSERT INTO artifact_version (
    package_id,
    version_major,
    version_minor,
    version_patch,
    prerelease,
    blob_digest,
    publisher_id,
    revision_id
)
SELECT
    ap.package_id,
    3,
    4,
    0,
    'rc.1',
    repeat('a', 64),
    pub.publisher_id,
    sr.revision_id
FROM artifact_package ap
JOIN repository r ON r.repository_id = ap.repository_id
JOIN publisher pub ON pub.publisher_name = 'ci-release-bot'
JOIN source_revision sr
  ON sr.repository_id = r.repository_id
 AND sr.revision_hash = 'a91b02c'
WHERE ap.package_name = 'bridge-inspection-engine';

INSERT INTO artifact_version (
    package_id,
    version_major,
    version_minor,
    version_patch,
    prerelease,
    blob_digest,
    publisher_id,
    revision_id
)
SELECT
    ap.package_id,
    3,
    4,
    0,
    '',
    repeat('b', 64),
    pub.publisher_id,
    sr.revision_id
FROM artifact_package ap
JOIN repository r ON r.repository_id = ap.repository_id
JOIN publisher pub ON pub.publisher_name = 'ci-release-bot'
JOIN source_revision sr
  ON sr.repository_id = r.repository_id
 AND sr.revision_hash = 'd45b771'
WHERE ap.package_name = 'bridge-inspection-engine';

INSERT INTO artifact_metadata (
    artifact_version_id,
    metadata_key,
    metadata_value
)
SELECT artifact_version_id, 'build_pipeline', 'production-release'
FROM artifact_version
WHERE version_major = 3
  AND version_minor = 4
  AND version_patch = 0
  AND prerelease = '';

-- Promoting the stable release updates a mutable channel pointer without
-- changing the immutable artifact version or its content digest.
SELECT promote_artifact(
    ap.package_id,
    'production',
    av.artifact_version_id,
    'release-manager'
)
FROM artifact_package ap
JOIN artifact_version av ON av.package_id = ap.package_id
WHERE ap.package_name = 'bridge-inspection-engine'
  AND av.version_major = 3
  AND av.version_minor = 4
  AND av.version_patch = 0
  AND av.prerelease = '';

-- Inventory with normalized semantic-version columns and provenance.
SELECT
    r.repository_name,
    ap.package_name,
    format(
        '%s.%s.%s%s',
        av.version_major,
        av.version_minor,
        av.version_patch,
        CASE WHEN av.prerelease <> '' THEN '-' || av.prerelease ELSE '' END
    ) AS version,
    av.blob_digest,
    ab.size_bytes,
    pub.publisher_name,
    sr.revision_hash,
    av.lifecycle_state,
    av.published_at
FROM artifact_version av
JOIN artifact_package ap ON ap.package_id = av.package_id
JOIN repository r ON r.repository_id = ap.repository_id
JOIN artifact_blob ab ON ab.digest = av.blob_digest
JOIN publisher pub ON pub.publisher_id = av.publisher_id
JOIN source_revision sr ON sr.revision_id = av.revision_id
ORDER BY
    ap.package_name,
    av.version_major,
    av.version_minor,
    av.version_patch,
    av.prerelease;

-- Identify payloads reused by multiple package versions.
SELECT
    blob_digest,
    COUNT(*) AS version_count,
    SUM(size_bytes) AS referenced_bytes,
    ARRAY_AGG(artifact_version_id ORDER BY artifact_version_id) AS version_ids
FROM artifact_version av
JOIN artifact_blob ab ON ab.digest = av.blob_digest
GROUP BY blob_digest
HAVING COUNT(*) > 1
ORDER BY version_count DESC;

-- Resolve production channel to its currently published artifact.
SELECT
    ap.package_name,
    rc.environment,
    av.artifact_version_id,
    av.blob_digest,
    rc.updated_at
FROM release_channel rc
JOIN artifact_package ap ON ap.package_id = rc.package_id
JOIN artifact_version av
  ON av.artifact_version_id = rc.current_artifact_version_id
WHERE rc.environment = 'production';

-- Detect manifests whose referenced blobs are absent. A foreign key should
-- prevent this state in normal operations; this query is also useful when
-- reconciling a migrated catalog against external object storage.
SELECT
    av.artifact_version_id,
    av.blob_digest
FROM artifact_version av
LEFT JOIN artifact_blob ab ON ab.digest = av.blob_digest
WHERE ab.digest IS NULL;

-- Quarantine the release candidate. This preserves its manifest for audit
-- while preventing future promotion through the database trigger.
UPDATE artifact_version
SET lifecycle_state = 'quarantined'
WHERE version_major = 3
  AND version_minor = 4
  AND version_patch = 0
  AND prerelease = 'rc.1';

-- Verify that the release candidate cannot become the production target.
-- The block catches the expected exception so the demonstration can continue.
DO $$
DECLARE
    v_package_id BIGINT;
    v_candidate_id BIGINT;
BEGIN
    SELECT package_id
      INTO v_package_id
      FROM artifact_package
     WHERE package_name = 'bridge-inspection-engine';

    SELECT artifact_version_id
      INTO v_candidate_id
      FROM artifact_version
     WHERE package_id = v_package_id
       AND version_major = 3
       AND version_minor = 4
       AND version_patch = 0
       AND prerelease = 'rc.1';

    BEGIN
        PERFORM promote_artifact(
            v_package_id,
            'staging',
            v_candidate_id,
            'release-manager'
        );
        RAISE EXCEPTION 'Expected quarantined artifact promotion to fail';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM = 'Expected quarantined artifact promotion to fail' THEN
                RAISE;
            END IF;
            RAISE NOTICE 'Promotion rejected as expected: %', SQLERRM;
    END;
END;
$$;

-- Review the audit trail for publication, promotion, and quarantine events.
SELECT
    occurred_at,
    actor,
    action,
    artifact_version_id,
    channel_id,
    details
FROM artifact_audit_event
ORDER BY occurred_at, event_id;

COMMIT;

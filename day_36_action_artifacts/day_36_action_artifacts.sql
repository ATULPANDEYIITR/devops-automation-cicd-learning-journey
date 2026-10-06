-- PostgreSQL-compatible build artifact repository and lifecycle model.
--
-- The schema separates:
--   build artifacts: immutable build outputs and provenance
--   artifact files: individual files represented by an artifact manifest
--   storage objects: physical uploaded/downloadable representations
--   status checks: publication quality gates
--   retention: lifecycle and cleanup policy
--
-- PostgreSQL-specific features used here include UUID generation, JSONB,
-- CHECK constraints, partial indexes, CTEs, triggers, and transactional locking.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP VIEW IF EXISTS artifact_merge_eligibility;
DROP VIEW IF EXISTS artifact_inventory;
DROP FUNCTION IF EXISTS prevent_artifact_mutation();
DROP FUNCTION IF EXISTS validate_artifact_upload();
DROP FUNCTION IF EXISTS refresh_artifact_updated_at();
DROP TABLE IF EXISTS artifact_downloads CASCADE;
DROP TABLE IF EXISTS artifact_storage_objects CASCADE;
DROP TABLE IF EXISTS artifact_status_checks CASCADE;
DROP TABLE IF EXISTS artifact_files CASCADE;
DROP TABLE IF EXISTS artifacts CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;

CREATE TABLE repositories (
    repository_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT repository_name_not_blank
        CHECK (btrim(repository_name) <> ''),
    CONSTRAINT default_branch_not_blank
        CHECK (btrim(default_branch) <> '')
);

CREATE TABLE artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(repository_id),
    artifact_name TEXT NOT NULL,
    build_number INTEGER NOT NULL,
    commit_sha TEXT NOT NULL,
    pipeline_name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'created',
    archive_format TEXT NOT NULL DEFAULT 'tar.gz',
    archive_size_bytes BIGINT NOT NULL DEFAULT 0,
    archive_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retention_until TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT artifact_name_not_blank
        CHECK (btrim(artifact_name) <> ''),
    CONSTRAINT commit_sha_not_blank
        CHECK (btrim(commit_sha) <> ''),
    CONSTRAINT pipeline_name_not_blank
        CHECK (btrim(pipeline_name) <> ''),
    CONSTRAINT artifact_state_valid
        CHECK (
            state IN (
                'created',
                'uploaded',
                'verified',
                'retained',
                'expired',
                'deleted'
            )
        ),
    CONSTRAINT archive_format_valid
        CHECK (archive_format IN ('tar.gz', 'zip', 'jar', 'whl')),
    CONSTRAINT archive_size_valid
        CHECK (archive_size_bytes >= 0),
    CONSTRAINT sha256_format_valid
        CHECK (archive_sha256 ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT retention_after_creation
        CHECK (retention_until >= created_at),
    CONSTRAINT unique_build_artifact
        UNIQUE (repository_id, build_number, artifact_name)
);

CREATE TABLE artifact_files (
    artifact_file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,

    CONSTRAINT artifact_file_path_not_blank
        CHECK (btrim(relative_path) <> ''),
    CONSTRAINT artifact_file_size_valid
        CHECK (size_bytes >= 0),
    CONSTRAINT artifact_file_sha256_valid
        CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT artifact_file_path_safe
        CHECK (
            relative_path !~ '^/'
            AND relative_path !~ '(^|/)\.\.(/|$)'
        ),
    CONSTRAINT unique_artifact_file_path
        UNIQUE (artifact_id, relative_path)
);

CREATE TABLE artifact_status_checks (
    status_check_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_name_not_blank
        CHECK (btrim(check_name) <> ''),
    CONSTRAINT check_status_valid
        CHECK (status IN ('passed', 'failed', 'cancelled', 'pending')),
    CONSTRAINT unique_artifact_check
        UNIQUE (artifact_id, check_name)
);

CREATE TABLE artifact_storage_objects (
    storage_object_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    storage_provider TEXT NOT NULL,
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ,
    downloaded_at TIMESTAMPTZ,
    storage_class TEXT NOT NULL DEFAULT 'standard',
    object_etag TEXT,
    encryption_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT storage_provider_not_blank
        CHECK (btrim(storage_provider) <> ''),
    CONSTRAINT bucket_name_not_blank
        CHECK (btrim(bucket_name) <> ''),
    CONSTRAINT object_key_not_blank
        CHECK (btrim(object_key) <> ''),
    CONSTRAINT storage_class_valid
        CHECK (storage_class IN ('standard', 'infrequent_access', 'archive')),
    CONSTRAINT object_key_unique
        UNIQUE (storage_provider, bucket_name, object_key)
);

CREATE TABLE artifact_downloads (
    download_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consumer TEXT NOT NULL,
    observed_sha256 TEXT,
    verification_status TEXT NOT NULL,

    CONSTRAINT consumer_not_blank
        CHECK (btrim(consumer) <> ''),
    CONSTRAINT verification_status_valid
        CHECK (
            verification_status IN (
                'pending',
                'verified',
                'failed'
            )
        )
);

CREATE INDEX idx_artifacts_repository_created
    ON artifacts(repository_id, created_at DESC);

CREATE INDEX idx_artifacts_retention
    ON artifacts(retention_until)
    WHERE state IN ('verified', 'retained');

CREATE INDEX idx_artifact_files_artifact
    ON artifact_files(artifact_id);

CREATE INDEX idx_status_checks_artifact_status
    ON artifact_status_checks(artifact_id, status);

CREATE INDEX idx_downloads_artifact_requested
    ON artifact_downloads(artifact_id, requested_at DESC);

CREATE INDEX idx_artifacts_metadata
    ON artifacts USING GIN(metadata);

CREATE OR REPLACE FUNCTION refresh_artifact_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER artifacts_updated_at
BEFORE UPDATE ON artifacts
FOR EACH ROW
EXECUTE FUNCTION refresh_artifact_updated_at();

CREATE OR REPLACE FUNCTION prevent_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.archive_sha256 <> NEW.archive_sha256
       OR OLD.commit_sha <> NEW.commit_sha
       OR OLD.build_number <> NEW.build_number
       OR OLD.archive_format <> NEW.archive_format THEN
        RAISE EXCEPTION
            'Immutable artifact provenance or content metadata cannot be changed';
    END IF;

    IF OLD.state = 'deleted' AND NEW.state <> 'deleted' THEN
        RAISE EXCEPTION
            'Deleted artifacts cannot return to an active state';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER artifacts_immutability_guard
BEFORE UPDATE ON artifacts
FOR EACH ROW
EXECUTE FUNCTION prevent_artifact_mutation();

CREATE OR REPLACE FUNCTION validate_artifact_upload()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    failed_checks INTEGER;
    pending_checks INTEGER;
    file_count INTEGER;
BEGIN
    IF NEW.state IN ('uploaded', 'verified', 'retained') THEN

        SELECT COUNT(*)
        INTO file_count
        FROM artifact_files
        WHERE artifact_id = NEW.artifact_id;

        IF file_count = 0 THEN
            RAISE EXCEPTION
                'Artifact % cannot become active without files',
                NEW.artifact_id;
        END IF;

        SELECT COUNT(*)
        INTO failed_checks
        FROM artifact_status_checks
        WHERE artifact_id = NEW.artifact_id
          AND status IN ('failed', 'cancelled');

        SELECT COUNT(*)
        INTO pending_checks
        FROM artifact_status_checks
        WHERE artifact_id = NEW.artifact_id
          AND status = 'pending';

        IF failed_checks > 0 OR pending_checks > 0 THEN
            RAISE EXCEPTION
                'Artifact % has failed or pending quality checks',
                NEW.artifact_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER artifact_upload_validation
BEFORE UPDATE OF state ON artifacts
FOR EACH ROW
EXECUTE FUNCTION validate_artifact_upload();

INSERT INTO repositories (
    repository_name,
    default_branch
)
VALUES
    ('platform/payments-api', 'main'),
    ('platform/web-frontend', 'main');

-- The SHA-256 values below are valid 64-character hexadecimal examples.
-- They represent checksums supplied by a build/package process.

INSERT INTO artifacts (
    repository_id,
    artifact_name,
    build_number,
    commit_sha,
    pipeline_name,
    state,
    archive_format,
    archive_size_bytes,
    archive_sha256,
    retention_until,
    metadata
)
SELECT
    repository_id,
    'payments-api-release',
    184,
    '7f3d8a2b91c4',
    'production-release',
    'created',
    'tar.gz',
    5827133,
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    CURRENT_TIMESTAMP + INTERVAL '30 days',
    jsonb_build_object(
        'environment', 'production',
        'language', 'java',
        'release_channel', 'stable'
    )
FROM repositories
WHERE repository_name = 'platform/payments-api';

INSERT INTO artifacts (
    repository_id,
    artifact_name,
    build_number,
    commit_sha,
    pipeline_name,
    state,
    archive_format,
    archive_size_bytes,
    archive_sha256,
    retention_until,
    metadata
)
SELECT
    repository_id,
    'web-frontend-release',
    208,
    'd20c9f13b8aa',
    'frontend-release',
    'created',
    'tar.gz',
    215042,
    'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
    CURRENT_TIMESTAMP + INTERVAL '7 days',
    jsonb_build_object(
        'environment', 'production',
        'framework', 'web',
        'release_channel', 'stable'
    )
FROM repositories
WHERE repository_name = 'platform/web-frontend';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'bin/payments-api',
    4821032,
    '1111111111111111111111111111111111111111111111111111111111111111'
FROM artifacts
WHERE artifact_name = 'payments-api-release';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'config/runtime.json',
    1290,
    '2222222222222222222222222222222222222222222222222222222222222222'
FROM artifacts
WHERE artifact_name = 'payments-api-release';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'docs/release-notes.txt',
    4811,
    '3333333333333333333333333333333333333333333333333333333333333333'
FROM artifacts
WHERE artifact_name = 'payments-api-release';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'dist/index.html',
    8032,
    '4444444444444444444444444444444444444444444444444444444444444444'
FROM artifacts
WHERE artifact_name = 'web-frontend-release';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'dist/app.js',
    184203,
    '5555555555555555555555555555555555555555555555555555555555555555'
FROM artifacts
WHERE artifact_name = 'web-frontend-release';

INSERT INTO artifact_files (
    artifact_id,
    relative_path,
    size_bytes,
    sha256
)
SELECT
    artifact_id,
    'dist/app.css',
    22810,
    '6666666666666666666666666666666666666666666666666666666666666666'
FROM artifacts
WHERE artifact_name = 'web-frontend-release';

INSERT INTO artifact_status_checks (
    artifact_id,
    check_name,
    status,
    details
)
SELECT
    artifact_id,
    check_name,
    'passed',
    jsonb_build_object('duration_seconds', duration_seconds)
FROM artifacts
CROSS JOIN (
    VALUES
        ('unit-tests', 94),
        ('security-scan', 38),
        ('dependency-audit', 21),
        ('package-validation', 7)
) AS checks(check_name, duration_seconds)
WHERE artifact_name = 'payments-api-release';

INSERT INTO artifact_status_checks (
    artifact_id,
    check_name,
    status,
    details
)
SELECT
    artifact_id,
    check_name,
    'passed',
    '{}'::jsonb
FROM artifacts
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('dependency-audit'),
        ('package-validation')
) AS checks(check_name)
WHERE artifact_name = 'web-frontend-release';

-- Upload and store the immutable object only after all quality checks pass.
BEGIN;

SELECT artifact_id
FROM artifacts
WHERE artifact_name = 'payments-api-release'
FOR UPDATE;

UPDATE artifacts
SET state = 'uploaded'
WHERE artifact_name = 'payments-api-release'
  AND state = 'created';

INSERT INTO artifact_storage_objects (
    artifact_id,
    storage_provider,
    bucket_name,
    object_key,
    uploaded_at,
    storage_class,
    encryption_enabled
)
SELECT
    artifact_id,
    'object-storage',
    'build-artifacts-production',
    'platform/payments-api/184/payments-api-release.tar.gz',
    CURRENT_TIMESTAMP,
    'standard',
    TRUE
FROM artifacts
WHERE artifact_name = 'payments-api-release'
  AND state = 'uploaded';

COMMIT;

-- Verify an uploaded artifact before allowing it to become deployment-ready.
BEGIN;

UPDATE artifacts
SET state = 'verified'
WHERE artifact_name = 'payments-api-release'
  AND state = 'uploaded'
  AND archive_sha256 =
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

INSERT INTO artifact_downloads (
    artifact_id,
    consumer,
    observed_sha256,
    verification_status
)
SELECT
    artifact_id,
    'deployment-controller',
    archive_sha256,
    'verified'
FROM artifacts
WHERE artifact_name = 'payments-api-release'
  AND state = 'verified';

COMMIT;

CREATE OR REPLACE VIEW artifact_inventory AS
SELECT
    a.artifact_id,
    r.repository_name,
    a.artifact_name,
    a.build_number,
    a.commit_sha,
    a.state,
    a.archive_format,
    a.archive_size_bytes,
    a.archive_sha256,
    a.created_at,
    a.retention_until,
    COUNT(af.artifact_file_id) AS file_count,
    COUNT(*) FILTER (
        WHERE sc.status = 'passed'
    ) AS passed_checks,
    COUNT(*) FILTER (
        WHERE sc.status IN ('failed', 'cancelled')
    ) AS failed_checks
FROM artifacts a
JOIN repositories r
    ON r.repository_id = a.repository_id
LEFT JOIN artifact_files af
    ON af.artifact_id = a.artifact_id
LEFT JOIN artifact_status_checks sc
    ON sc.artifact_id = a.artifact_id
GROUP BY
    a.artifact_id,
    r.repository_name,
    a.artifact_name,
    a.build_number,
    a.commit_sha,
    a.state,
    a.archive_format,
    a.archive_size_bytes,
    a.archive_sha256,
    a.created_at,
    a.retention_until;

-- Inspect artifact inventory and provenance.
SELECT *
FROM artifact_inventory
ORDER BY created_at DESC;

-- Detect artifacts whose files do not account for the recorded archive payload.
SELECT
    a.artifact_id,
    a.artifact_name,
    a.archive_size_bytes,
    COALESCE(SUM(af.size_bytes), 0) AS declared_file_bytes
FROM artifacts a
LEFT JOIN artifact_files af
    ON af.artifact_id = a.artifact_id
GROUP BY
    a.artifact_id,
    a.artifact_name,
    a.archive_size_bytes
HAVING COALESCE(SUM(af.size_bytes), 0) > a.archive_size_bytes;

-- Find artifacts blocked by quality checks.
SELECT
    a.artifact_name,
    a.build_number,
    sc.check_name,
    sc.status,
    sc.details
FROM artifacts a
JOIN artifact_status_checks sc
    ON sc.artifact_id = a.artifact_id
WHERE sc.status <> 'passed'
ORDER BY a.build_number DESC;

-- Identify verified artifacts that are approaching or past retention.
SELECT
    artifact_id,
    artifact_name,
    state,
    retention_until,
    retention_until - CURRENT_TIMESTAMP AS remaining_retention
FROM artifacts
WHERE state IN ('verified', 'retained')
ORDER BY retention_until;

-- Record a failed download verification without altering the immutable artifact.
INSERT INTO artifact_downloads (
    artifact_id,
    consumer,
    observed_sha256,
    verification_status
)
SELECT
    artifact_id,
    'test-deployment-controller',
    '9999999999999999999999999999999999999999999999999999999999999999',
    'failed'
FROM artifacts
WHERE artifact_name = 'web-frontend-release';

-- A failed download does not make the stored artifact itself invalid.
SELECT
    a.artifact_name,
    a.state,
    d.consumer,
    d.verification_status
FROM artifacts a
JOIN artifact_downloads d
    ON d.artifact_id = a.artifact_id
WHERE d.verification_status = 'failed';

-- CTE-based lifecycle report.
WITH check_summary AS (
    SELECT
        artifact_id,
        COUNT(*) AS total_checks,
        COUNT(*) FILTER (WHERE status = 'passed') AS passed_checks,
        COUNT(*) FILTER (
            WHERE status IN ('failed', 'cancelled')
        ) AS failed_checks,
        COUNT(*) FILTER (WHERE status = 'pending') AS pending_checks
    FROM artifact_status_checks
    GROUP BY artifact_id
)
SELECT
    a.artifact_name,
    a.build_number,
    a.state,
    COALESCE(cs.total_checks, 0) AS total_checks,
    COALESCE(cs.passed_checks, 0) AS passed_checks,
    COALESCE(cs.failed_checks, 0) AS failed_checks,
    COALESCE(cs.pending_checks, 0) AS pending_checks,
    CASE
        WHEN a.state = 'verified'
         AND COALESCE(cs.failed_checks, 0) = 0
         AND COALESCE(cs.pending_checks, 0) = 0
        THEN 'deployable'
        ELSE 'blocked'
    END AS deployment_status
FROM artifacts a
LEFT JOIN check_summary cs
    ON cs.artifact_id = a.artifact_id
ORDER BY a.build_number DESC;

-- Retention cleanup is performed transactionally and only for artifacts whose
-- retention period has expired. Storage objects use RESTRICT deletion so an
-- accidental artifact delete cannot silently orphan a stored object.
BEGIN;

WITH expired AS (
    SELECT artifact_id
    FROM artifacts
    WHERE state IN ('verified', 'retained')
      AND retention_until <= CURRENT_TIMESTAMP
    FOR UPDATE
)
UPDATE artifacts a
SET state = 'expired'
FROM expired e
WHERE a.artifact_id = e.artifact_id;

COMMIT;

-- Deployment eligibility is intentionally separate from upload status.
-- An uploaded artifact that has not been integrity-verified is not deployable.
CREATE OR REPLACE VIEW artifact_merge_eligibility AS
SELECT
    a.artifact_id,
    r.repository_name,
    a.artifact_name,
    a.build_number,
    a.commit_sha,
    a.state,
    CASE
        WHEN a.state IN ('verified', 'retained')
         AND EXISTS (
             SELECT 1
             FROM artifact_storage_objects so
             WHERE so.artifact_id = a.artifact_id
               AND so.uploaded_at IS NOT NULL
               AND so.encryption_enabled = TRUE
         )
         AND NOT EXISTS (
             SELECT 1
             FROM artifact_status_checks sc
             WHERE sc.artifact_id = a.artifact_id
               AND sc.status IN ('failed', 'cancelled', 'pending')
         )
        THEN TRUE
        ELSE FALSE
    END AS deployable
FROM artifacts a
JOIN repositories r
    ON r.repository_id = a.repository_id;

SELECT *
FROM artifact_merge_eligibility
ORDER BY build_number DESC;

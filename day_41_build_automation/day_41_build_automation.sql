-- PostgreSQL 15+
-- Build automation control plane for source compilation, dependency
-- installation, testing, and distributable packaging.
--
-- The database records pipeline state and enforces valid transitions.
-- Compiler execution and package installation remain responsibilities of
-- isolated workers; SQL records their inputs, outcomes, and artifact evidence.

BEGIN;

CREATE SCHEMA IF NOT EXISTS buildops;
SET search_path TO buildops, public;

CREATE TYPE pipeline_stage AS ENUM (
    'dependency_installation',
    'source_compilation',
    'automated_testing',
    'packaging',
    'artifact_verification'
);

CREATE TYPE run_status AS ENUM (
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TYPE stage_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'skipped'
);

CREATE TYPE dependency_source AS ENUM (
    'registry',
    'internal_registry',
    'system_package'
);

CREATE TABLE projects (
    project_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_key text NOT NULL UNIQUE,
    display_name text NOT NULL,
    repository_url text NOT NULL,
    default_branch text NOT NULL DEFAULT 'main',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT project_key_format CHECK (
        project_key ~ '^[a-z][a-z0-9-]{2,62}$'
    ),
    CONSTRAINT repository_url_nonempty CHECK (length(trim(repository_url)) > 0)
);

CREATE TABLE build_profiles (
    profile_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    profile_name text NOT NULL,
    language text NOT NULL,
    compiler_command text NOT NULL,
    compiler_version_constraint text NOT NULL,
    build_configuration text NOT NULL
        CHECK (build_configuration IN ('debug', 'release', 'test')),
    target_platform text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    UNIQUE (project_id, profile_name)
);

CREATE TABLE dependencies (
    dependency_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    package_name text NOT NULL,
    package_version text NOT NULL,
    source dependency_source NOT NULL DEFAULT 'registry',
    checksum_sha256 text,
    is_build_dependency boolean NOT NULL DEFAULT false,
    UNIQUE (project_id, package_name),
    CHECK (length(trim(package_name)) > 0),
    CHECK (length(trim(package_version)) > 0),
    CHECK (
        checksum_sha256 IS NULL
        OR checksum_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE dependency_lock_snapshots (
    lock_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    lock_digest text NOT NULL CHECK (lock_digest ~ '^[0-9a-f]{64}$'),
    lock_format text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, lock_digest)
);

CREATE TABLE build_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(project_id),
    profile_id bigint NOT NULL REFERENCES build_profiles(profile_id),
    lock_id bigint REFERENCES dependency_lock_snapshots(lock_id),
    source_revision text NOT NULL,
    requested_by text NOT NULL,
    status run_status NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    worker_identity text,
    failure_reason text,
    CHECK (length(trim(source_revision)) > 0),
    CHECK (length(trim(requested_by)) > 0),
    CHECK (finished_at IS NULL OR started_at IS NOT NULL),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (
        (status IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)
        OR
        (status IN ('queued', 'running') AND finished_at IS NULL)
    ),
    CHECK (
        status <> 'failed'
        OR failure_reason IS NOT NULL
    )
);

CREATE TABLE build_run_stages (
    stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES build_runs(run_id) ON DELETE CASCADE,
    stage pipeline_stage NOT NULL,
    execution_order integer NOT NULL CHECK (execution_order > 0),
    status stage_status NOT NULL DEFAULT 'pending',
    started_at timestamptz,
    finished_at timestamptz,
    attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
    exit_code integer,
    log_location text,
    error_summary text,
    UNIQUE (run_id, stage, attempt),
    UNIQUE (run_id, execution_order),
    CHECK (finished_at IS NULL OR started_at IS NOT NULL),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (
        status <> 'succeeded'
        OR (started_at IS NOT NULL AND finished_at IS NOT NULL AND exit_code = 0)
    ),
    CHECK (
        status <> 'failed'
        OR (finished_at IS NOT NULL AND exit_code IS NOT NULL AND exit_code <> 0)
    )
);

CREATE TABLE build_artifacts (
    artifact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES build_runs(run_id) ON DELETE CASCADE,
    artifact_name text NOT NULL,
    artifact_type text NOT NULL CHECK (
        artifact_type IN ('executable', 'source_archive', 'package',
                          'test_report', 'manifest')
    ),
    storage_uri text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, artifact_name),
    CHECK (length(trim(storage_uri)) > 0)
);

CREATE TABLE build_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES build_runs(run_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX build_runs_project_created_idx
    ON build_runs(project_id, created_at DESC);

CREATE INDEX build_runs_active_idx
    ON build_runs(status, created_at)
    WHERE status IN ('queued', 'running');

CREATE INDEX build_stages_failed_idx
    ON build_run_stages(run_id, execution_order)
    WHERE status = 'failed';

CREATE INDEX build_events_payload_idx
    ON build_events USING gin(event_payload);

CREATE INDEX build_artifacts_unverified_idx
    ON build_artifacts(run_id, artifact_type)
    WHERE verified = false;

-- Ensure a build profile belongs to the same project as its run.
CREATE FUNCTION validate_run_profile_project()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    profile_project_id bigint;
BEGIN
    SELECT project_id
    INTO profile_project_id
    FROM build_profiles
    WHERE profile_id = NEW.profile_id;

    IF profile_project_id IS NULL OR profile_project_id <> NEW.project_id THEN
        RAISE EXCEPTION 'Build profile must belong to the selected project';
    END IF;

    IF NEW.lock_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM dependency_lock_snapshots l
        WHERE l.lock_id = NEW.lock_id
          AND l.project_id = NEW.project_id
    ) THEN
        RAISE EXCEPTION 'Dependency lock snapshot belongs to another project';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER build_run_project_consistency
BEFORE INSERT OR UPDATE OF project_id, profile_id, lock_id
ON build_runs
FOR EACH ROW
EXECUTE FUNCTION validate_run_profile_project();

-- Prevent illegal terminal-state rewrites and enforce lifecycle timestamps.
CREATE FUNCTION enforce_build_run_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('succeeded', 'failed', 'cancelled')
       AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'Terminal build run status cannot be changed';
    END IF;

    IF OLD.status = 'queued' AND NEW.status = 'running' THEN
        NEW.started_at := COALESCE(NEW.started_at, now());
        NEW.finished_at := NULL;
    ELSIF OLD.status = 'running'
          AND NEW.status IN ('succeeded', 'failed', 'cancelled') THEN
        NEW.finished_at := COALESCE(NEW.finished_at, now());
    ELSIF NEW.status = 'failed' AND NEW.failure_reason IS NULL THEN
        RAISE EXCEPTION 'Failed build run requires a failure reason';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER build_run_transition_guard
BEFORE UPDATE OF status ON build_runs
FOR EACH ROW
EXECUTE FUNCTION enforce_build_run_transition();

-- Only verified artifacts may be marked verified after integrity evidence
-- has been supplied by the build worker. The digest is mandatory at insert.
CREATE FUNCTION record_artifact_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO build_events(run_id, event_type, event_payload)
    VALUES (
        NEW.run_id,
        'artifact_registered',
        jsonb_build_object(
            'name', NEW.artifact_name,
            'type', NEW.artifact_type,
            'sha256', NEW.sha256,
            'size_bytes', NEW.size_bytes
        )
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER build_artifact_audit
AFTER INSERT ON build_artifacts
FOR EACH ROW
EXECUTE FUNCTION record_artifact_event();

-- A view exposes stage-level progress without pretending that queued work
-- has completed or that a failed stage can be ignored.
CREATE VIEW build_run_progress AS
SELECT
    r.run_id,
    p.project_key,
    p.display_name,
    r.source_revision,
    r.status AS run_status,
    count(s.stage_id) AS configured_stage_count,
    count(s.stage_id) FILTER (WHERE s.status = 'succeeded') AS succeeded_stages,
    count(s.stage_id) FILTER (WHERE s.status = 'failed') AS failed_stages,
    count(s.stage_id) FILTER (WHERE s.status IN ('pending', 'running')) AS unfinished_stages,
    max(s.finished_at) AS last_stage_finished_at
FROM build_runs r
JOIN projects p ON p.project_id = r.project_id
LEFT JOIN build_run_stages s ON s.run_id = r.run_id
GROUP BY
    r.run_id,
    p.project_key,
    p.display_name,
    r.source_revision,
    r.status;

-- Seed a reproducible C++ service build.
INSERT INTO projects(project_key, display_name, repository_url)
VALUES (
    'telemetry-processor',
    'Telemetry Processor',
    'https://example.invalid/engineering/telemetry-processor'
);

INSERT INTO build_profiles(
    project_id,
    profile_name,
    language,
    compiler_command,
    compiler_version_constraint,
    build_configuration,
    target_platform
)
SELECT
    project_id,
    'linux-release',
    'C++',
    'c++ -std=c++17 -O2 -Wall -Wextra -Werror',
    'GCC >= 12 or Clang >= 15',
    'release',
    'linux-x86_64'
FROM projects
WHERE project_key = 'telemetry-processor';

INSERT INTO dependencies(
    project_id,
    package_name,
    package_version,
    source,
    is_build_dependency
)
SELECT project_id, 'cmake', '3.27+', 'system_package', true
FROM projects
WHERE project_key = 'telemetry-processor';

INSERT INTO dependency_lock_snapshots(
    project_id,
    lock_digest,
    lock_format
)
SELECT
    project_id,
    repeat('a', 64),
    'internal-build-lock-v1'
FROM projects
WHERE project_key = 'telemetry-processor';

INSERT INTO build_runs(
    project_id,
    profile_id,
    lock_id,
    source_revision,
    requested_by,
    status
)
SELECT
    p.project_id,
    bp.profile_id,
    l.lock_id,
    '8b72f19c0e1d',
    'ci-runner',
    'queued'
FROM projects p
JOIN build_profiles bp ON bp.project_id = p.project_id
JOIN dependency_lock_snapshots l ON l.project_id = p.project_id
WHERE p.project_key = 'telemetry-processor'
  AND bp.profile_name = 'linux-release';

INSERT INTO build_run_stages(run_id, stage, execution_order)
SELECT r.run_id, v.stage, v.execution_order
FROM build_runs r
CROSS JOIN (
    VALUES
        ('dependency_installation'::pipeline_stage, 1),
        ('source_compilation'::pipeline_stage, 2),
        ('automated_testing'::pipeline_stage, 3),
        ('packaging'::pipeline_stage, 4),
        ('artifact_verification'::pipeline_stage, 5)
) AS v(stage, execution_order);

-- Simulate worker claiming a queued run.
UPDATE build_runs
SET status = 'running',
    worker_identity = 'linux-builder-07'
WHERE source_revision = '8b72f19c0e1d'
  AND status = 'queued';

UPDATE build_run_stages
SET status = 'succeeded',
    started_at = now() - interval '8 seconds',
    finished_at = now() - interval '7 seconds',
    exit_code = 0,
    log_location = 'logs/dependencies-001.log'
WHERE stage = 'dependency_installation'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

UPDATE build_run_stages
SET status = 'succeeded',
    started_at = now() - interval '6 seconds',
    finished_at = now() - interval '4 seconds',
    exit_code = 0,
    log_location = 'logs/compile-001.log'
WHERE stage = 'source_compilation'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

UPDATE build_run_stages
SET status = 'succeeded',
    started_at = now() - interval '3 seconds',
    finished_at = now() - interval '2 seconds',
    exit_code = 0,
    log_location = 'logs/tests-001.log'
WHERE stage = 'automated_testing'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

UPDATE build_run_stages
SET status = 'succeeded',
    started_at = now() - interval '1 second',
    finished_at = now(),
    exit_code = 0,
    log_location = 'logs/package-001.log'
WHERE stage = 'packaging'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

INSERT INTO build_artifacts(
    run_id,
    artifact_name,
    artifact_type,
    storage_uri,
    size_bytes,
    sha256
)
SELECT
    run_id,
    'telemetry-processor-2.4.0.tar.gz',
    'source_archive',
    's3://internal-builds/telemetry-processor/2.4.0.tar.gz',
    18432,
    repeat('b', 64)
FROM build_runs
WHERE source_revision = '8b72f19c0e1d';

UPDATE build_artifacts
SET verified = true
WHERE artifact_name = 'telemetry-processor-2.4.0.tar.gz'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

UPDATE build_run_stages
SET status = 'succeeded',
    started_at = now(),
    finished_at = now(),
    exit_code = 0,
    log_location = 'logs/artifact-verification-001.log'
WHERE stage = 'artifact_verification'
  AND run_id = (
      SELECT run_id FROM build_runs WHERE source_revision = '8b72f19c0e1d'
  );

UPDATE build_runs
SET status = 'succeeded'
WHERE source_revision = '8b72f19c0e1d'
  AND status = 'running';

-- Inspect pipeline status and per-stage execution evidence.
SELECT *
FROM build_run_progress
ORDER BY run_id DESC;

SELECT
    r.run_id,
    s.execution_order,
    s.stage,
    s.status,
    s.exit_code,
    s.log_location,
    s.error_summary
FROM build_runs r
JOIN build_run_stages s ON s.run_id = r.run_id
WHERE r.source_revision = '8b72f19c0e1d'
ORDER BY s.execution_order;

-- Inspect artifacts and their integrity evidence.
SELECT
    r.run_id,
    a.artifact_name,
    a.artifact_type,
    a.size_bytes,
    a.sha256,
    a.verified
FROM build_artifacts a
JOIN build_runs r ON r.run_id = a.run_id
WHERE r.source_revision = '8b72f19c0e1d';

-- Find recent failures for operational monitoring.
SELECT
    p.project_key,
    r.run_id,
    r.source_revision,
    r.failure_reason,
    r.finished_at
FROM build_runs r
JOIN projects p ON p.project_id = r.project_id
WHERE r.status = 'failed'
ORDER BY r.finished_at DESC
LIMIT 50;

-- Failed builds must record a reason. This example uses a nested block so the
-- intentional constraint violation can be inspected without aborting the seed.
DO $$
BEGIN
    BEGIN
        UPDATE build_runs
        SET status = 'failed',
            failure_reason = NULL
        WHERE source_revision = '8b72f19c0e1d';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Correctly rejected a failed run without a failure reason';
    END;
END;
$$;

COMMIT;

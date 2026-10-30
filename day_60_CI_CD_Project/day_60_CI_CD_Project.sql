BEGIN;

DROP SCHEMA IF EXISTS cicd CASCADE;
CREATE SCHEMA cicd;

CREATE TYPE cicd.run_status AS ENUM (
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TYPE cicd.stage_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'skipped'
);

CREATE TYPE cicd.test_status AS ENUM (
    'passed',
    'failed',
    'skipped'
);

CREATE TYPE cicd.severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TABLE cicd.pipeline_definitions (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name TEXT NOT NULL UNIQUE,
    application_name TEXT NOT NULL,
    application_version TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pipeline_name_not_blank CHECK (btrim(pipeline_name) <> ''),
    CONSTRAINT application_name_not_blank CHECK (btrim(application_name) <> '')
);

CREATE TABLE cicd.stage_definitions (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES cicd.pipeline_definitions(pipeline_id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    timeout_seconds INTEGER NOT NULL DEFAULT 600
        CHECK (timeout_seconds BETWEEN 1 AND 86400),
    CONSTRAINT valid_stage_name CHECK (
        stage_name IN ('build', 'test', 'scan', 'package', 'dockerize')
    ),
    CONSTRAINT unique_pipeline_stage UNIQUE (pipeline_id, stage_name),
    CONSTRAINT unique_pipeline_sequence UNIQUE (pipeline_id, sequence_no)
);

CREATE TABLE cicd.pipeline_policies (
    pipeline_id BIGINT PRIMARY KEY
        REFERENCES cicd.pipeline_definitions(pipeline_id) ON DELETE CASCADE,
    require_tests BOOLEAN NOT NULL DEFAULT TRUE,
    require_package BOOLEAN NOT NULL DEFAULT TRUE,
    require_docker_image BOOLEAN NOT NULL DEFAULT TRUE,
    blocking_severity cicd.severity NOT NULL DEFAULT 'high',
    minimum_pass_rate NUMERIC(5, 2) NOT NULL DEFAULT 100.00
        CHECK (minimum_pass_rate BETWEEN 0 AND 100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE cicd.pipeline_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES cicd.pipeline_definitions(pipeline_id),
    commit_sha TEXT NOT NULL,
    source_branch TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    status cicd.run_status NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT valid_commit_sha CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT valid_source_branch CHECK (
        btrim(source_branch) <> '' AND length(source_branch) <= 255
    ),
    CONSTRAINT valid_triggered_by CHECK (btrim(triggered_by) <> ''),
    CONSTRAINT valid_run_timestamps CHECK (
        (status IN ('queued', 'running') AND finished_at IS NULL)
        OR
        (status IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)
    ),
    CONSTRAINT running_run_has_start CHECK (
        status <> 'running' OR started_at IS NOT NULL
    )
);

CREATE TABLE cicd.stage_executions (
    stage_execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL
        REFERENCES cicd.pipeline_runs(run_id) ON DELETE CASCADE,
    stage_id BIGINT NOT NULL
        REFERENCES cicd.stage_definitions(stage_id),
    status cicd.stage_status NOT NULL DEFAULT 'pending',
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    exit_code INTEGER,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT one_execution_per_stage_per_run UNIQUE (run_id, stage_id),
    CONSTRAINT valid_stage_execution_timestamps CHECK (
        (status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
        OR
        (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
        OR
        (status IN ('succeeded', 'failed', 'skipped')
            AND finished_at IS NOT NULL)
    )
);

CREATE TABLE cicd.test_results (
    test_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_execution_id BIGINT NOT NULL
        REFERENCES cicd.stage_executions(stage_execution_id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    status cicd.test_status NOT NULL,
    duration_ms NUMERIC(12, 3) NOT NULL DEFAULT 0
        CHECK (duration_ms >= 0),
    failure_message TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT non_blank_test_name CHECK (btrim(test_name) <> ''),
    CONSTRAINT unique_test_per_execution UNIQUE (stage_execution_id, test_name),
    CONSTRAINT failure_message_matches_status CHECK (
        (status = 'failed' AND failure_message IS NOT NULL)
        OR
        (status <> 'failed')
    )
);

CREATE TABLE cicd.security_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_execution_id BIGINT NOT NULL
        REFERENCES cicd.stage_executions(stage_execution_id) ON DELETE CASCADE,
    rule_code TEXT NOT NULL,
    severity cicd.severity NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number IS NULL OR line_number > 0),
    fingerprint TEXT NOT NULL,
    description TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT unique_finding_fingerprint
        UNIQUE (stage_execution_id, fingerprint),
    CONSTRAINT valid_finding_text CHECK (
        btrim(rule_code) <> ''
        AND btrim(file_path) <> ''
        AND btrim(fingerprint) <> ''
        AND btrim(description) <> ''
    )
);

CREATE TABLE cicd.build_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_execution_id BIGINT NOT NULL
        REFERENCES cicd.stage_executions(stage_execution_id),
    artifact_name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    storage_location TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT valid_artifact_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT unique_artifact_name_per_execution
        UNIQUE (stage_execution_id, artifact_name),
    CONSTRAINT non_blank_artifact_fields CHECK (
        btrim(artifact_name) <> ''
        AND btrim(artifact_type) <> ''
        AND btrim(storage_location) <> ''
    )
);

CREATE TABLE cicd.docker_images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_execution_id BIGINT NOT NULL
        REFERENCES cicd.stage_executions(stage_execution_id),
    image_tag TEXT NOT NULL,
    image_digest TEXT NOT NULL,
    base_image TEXT NOT NULL,
    runs_as_non_root BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT valid_image_digest CHECK (
        image_digest ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT valid_image_fields CHECK (
        btrim(image_tag) <> '' AND btrim(base_image) <> ''
    ),
    CONSTRAINT unique_image_per_execution UNIQUE (stage_execution_id, image_tag)
);

-- These indexes support run history, stage-status inspection and security gating.
CREATE INDEX idx_pipeline_runs_history
    ON cicd.pipeline_runs (pipeline_id, created_at DESC);

CREATE INDEX idx_stage_executions_run_status
    ON cicd.stage_executions (run_id, status);

CREATE INDEX idx_security_findings_severity
    ON cicd.security_findings (severity, stage_execution_id);

CREATE INDEX idx_test_results_status
    ON cicd.test_results (stage_execution_id, status);

-- Enforce stage ordering and legal state transitions.
CREATE OR REPLACE FUNCTION cicd.enforce_stage_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_pipeline_id BIGINT;
    v_sequence_no INTEGER;
    v_blocking_prior_stages INTEGER;
BEGIN
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.status = 'pending' AND NEW.status IN ('running', 'skipped'))
        OR
        (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed'))
        OR
        (OLD.status = 'failed' AND NEW.status = 'running')
    ) THEN
        RAISE EXCEPTION
            'Invalid stage transition from % to %',
            OLD.status,
            NEW.status;
    END IF;

    SELECT sd.pipeline_id, sd.sequence_no
      INTO v_pipeline_id, v_sequence_no
      FROM cicd.stage_definitions sd
     WHERE sd.stage_id = NEW.stage_id;

    IF NEW.status = 'running' THEN
        SELECT COUNT(*)
          INTO v_blocking_prior_stages
          FROM cicd.stage_definitions prior
          LEFT JOIN cicd.stage_executions previous_execution
            ON previous_execution.stage_id = prior.stage_id
           AND previous_execution.run_id = NEW.run_id
         WHERE prior.pipeline_id = v_pipeline_id
           AND prior.sequence_no < v_sequence_no
           AND prior.is_required = TRUE
           AND COALESCE(previous_execution.status, 'pending') <> 'succeeded';

        IF v_blocking_prior_stages > 0 THEN
            RAISE EXCEPTION
                'Stage cannot start before all preceding required stages succeed';
        END IF;

        NEW.started_at := COALESCE(NEW.started_at, clock_timestamp());
        NEW.finished_at := NULL;
        NEW.exit_code := NULL;

        IF OLD.status = 'failed' THEN
            NEW.attempt := OLD.attempt + 1;
        END IF;

    ELSIF NEW.status = 'succeeded' THEN
        IF NEW.exit_code IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION 'A successful stage must have exit code zero';
        END IF;

        NEW.started_at := COALESCE(NEW.started_at, OLD.started_at);
        NEW.finished_at := clock_timestamp();

    ELSIF NEW.status = 'failed' THEN
        NEW.finished_at := clock_timestamp();
        NEW.exit_code := COALESCE(NEW.exit_code, 1);

    ELSIF NEW.status = 'skipped' THEN
        NEW.finished_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_enforce_stage_transition
BEFORE UPDATE OF status ON cicd.stage_executions
FOR EACH ROW
EXECUTE FUNCTION cicd.enforce_stage_transition();

-- Keep the overall run state synchronized with required stage executions.
CREATE OR REPLACE FUNCTION cicd.synchronize_run_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    IF NEW.status = 'running' THEN
        UPDATE cicd.pipeline_runs
           SET status = 'running',
               started_at = COALESCE(started_at, clock_timestamp())
         WHERE run_id = NEW.run_id
           AND status = 'queued';

    ELSIF NEW.status = 'failed' THEN
        UPDATE cicd.pipeline_runs
           SET status = 'failed',
               started_at = COALESCE(started_at, clock_timestamp()),
               finished_at = clock_timestamp()
         WHERE run_id = NEW.run_id
           AND status IN ('queued', 'running');

    ELSIF NEW.status = 'succeeded' THEN
        SELECT COUNT(*)
          INTO v_remaining
          FROM cicd.stage_executions se
          JOIN cicd.stage_definitions sd
            ON sd.stage_id = se.stage_id
         WHERE se.run_id = NEW.run_id
           AND sd.is_required = TRUE
           AND se.status <> 'succeeded';

        IF v_remaining = 0 THEN
            UPDATE cicd.pipeline_runs
               SET status = 'succeeded',
                   started_at = COALESCE(started_at, clock_timestamp()),
                   finished_at = clock_timestamp()
             WHERE run_id = NEW.run_id
               AND status = 'running';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_synchronize_run_status
AFTER UPDATE OF status ON cicd.stage_executions
FOR EACH ROW
EXECUTE FUNCTION cicd.synchronize_run_status();

-- Validate that a test result belongs to a test stage.
CREATE OR REPLACE FUNCTION cicd.validate_test_result_stage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_stage_name TEXT;
BEGIN
    SELECT sd.stage_name
      INTO v_stage_name
      FROM cicd.stage_executions se
      JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
     WHERE se.stage_execution_id = NEW.stage_execution_id;

    IF v_stage_name <> 'test' THEN
        RAISE EXCEPTION 'Test results can only belong to a test stage';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_test_result_stage
BEFORE INSERT OR UPDATE ON cicd.test_results
FOR EACH ROW
EXECUTE FUNCTION cicd.validate_test_result_stage();

-- Validate that security findings belong to an active or completed scan stage.
CREATE OR REPLACE FUNCTION cicd.validate_security_finding_stage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_stage_name TEXT;
    v_status cicd.stage_status;
BEGIN
    SELECT sd.stage_name, se.status
      INTO v_stage_name, v_status
      FROM cicd.stage_executions se
      JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
     WHERE se.stage_execution_id = NEW.stage_execution_id;

    IF v_stage_name <> 'scan' OR v_status NOT IN ('running', 'succeeded', 'failed') THEN
        RAISE EXCEPTION
            'Security findings must reference an active or completed scan stage';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_security_finding_stage
BEFORE INSERT OR UPDATE ON cicd.security_findings
FOR EACH ROW
EXECUTE FUNCTION cicd.validate_security_finding_stage();

-- Artifacts are accepted only after a successful package stage.
CREATE OR REPLACE FUNCTION cicd.validate_package_artifact()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_stage_name TEXT;
    v_status cicd.stage_status;
BEGIN
    SELECT sd.stage_name, se.status
      INTO v_stage_name, v_status
      FROM cicd.stage_executions se
      JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
     WHERE se.stage_execution_id = NEW.stage_execution_id;

    IF v_stage_name <> 'package' OR v_status <> 'succeeded' THEN
        RAISE EXCEPTION 'Artifacts require a successful package stage';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_package_artifact
BEFORE INSERT OR UPDATE ON cicd.build_artifacts
FOR EACH ROW
EXECUTE FUNCTION cicd.validate_package_artifact();

-- Container metadata is accepted only after successful Dockerization.
CREATE OR REPLACE FUNCTION cicd.validate_docker_image()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_stage_name TEXT;
    v_status cicd.stage_status;
BEGIN
    SELECT sd.stage_name, se.status
      INTO v_stage_name, v_status
      FROM cicd.stage_executions se
      JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
     WHERE se.stage_execution_id = NEW.stage_execution_id;

    IF v_stage_name <> 'dockerize' OR v_status <> 'succeeded' THEN
        RAISE EXCEPTION 'Docker images require a successful dockerize stage';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_docker_image
BEFORE INSERT OR UPDATE ON cicd.docker_images
FOR EACH ROW
EXECUTE FUNCTION cicd.validate_docker_image();

-- Create a run and all its pending stage executions atomically.
CREATE OR REPLACE FUNCTION cicd.create_run(
    p_pipeline_id BIGINT,
    p_commit_sha TEXT,
    p_source_branch TEXT,
    p_triggered_by TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_id BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM cicd.pipeline_definitions
         WHERE pipeline_id = p_pipeline_id
           AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'Pipeline does not exist or is inactive';
    END IF;

    IF p_commit_sha !~ '^[0-9a-f]{40}$' THEN
        RAISE EXCEPTION 'Commit SHA must contain 40 lowercase hexadecimal characters';
    END IF;

    IF btrim(p_source_branch) = '' OR btrim(p_triggered_by) = '' THEN
        RAISE EXCEPTION 'Source branch and trigger identity are required';
    END IF;

    INSERT INTO cicd.pipeline_runs (
        pipeline_id,
        commit_sha,
        source_branch,
        triggered_by
    )
    VALUES (
        p_pipeline_id,
        p_commit_sha,
        p_source_branch,
        p_triggered_by
    )
    RETURNING run_id INTO v_run_id;

    INSERT INTO cicd.stage_executions (run_id, stage_id)
    SELECT v_run_id, stage_id
      FROM cicd.stage_definitions
     WHERE pipeline_id = p_pipeline_id
     ORDER BY sequence_no;

    RETURN v_run_id;
END;
$$;

-- Evaluate the full release policy rather than relying on the run status alone.
CREATE OR REPLACE FUNCTION cicd.evaluate_run(p_run_id BIGINT)
RETURNS TABLE (
    eligible BOOLEAN,
    blockers TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pipeline_id BIGINT;
    v_run_status cicd.run_status;
    v_policy cicd.pipeline_policies%ROWTYPE;
    v_blockers TEXT[] := ARRAY[]::TEXT[];
    v_rank INTEGER;
BEGIN
    SELECT pr.pipeline_id, pr.status
      INTO v_pipeline_id, v_run_status
      FROM cicd.pipeline_runs pr
     WHERE pr.run_id = p_run_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, ARRAY['Pipeline run does not exist']::TEXT[];
        RETURN;
    END IF;

    SELECT *
      INTO v_policy
      FROM cicd.pipeline_policies
     WHERE pipeline_id = v_pipeline_id;

    IF v_run_status <> 'succeeded' THEN
        v_blockers := array_append(
            v_blockers,
            format('Pipeline run status is %s', v_run_status)
        );
    END IF;

    FOR v_rank IN
        SELECT COUNT(*)::INTEGER
          FROM cicd.stage_definitions sd
          LEFT JOIN cicd.stage_executions se
            ON se.stage_id = sd.stage_id
           AND se.run_id = p_run_id
         WHERE sd.pipeline_id = v_pipeline_id
           AND sd.is_required = TRUE
           AND COALESCE(se.status, 'pending') <> 'succeeded'
    LOOP
        IF v_rank > 0 THEN
            v_blockers := array_append(
                v_blockers,
                format('%s required stage(s) have not succeeded', v_rank)
            );
        END IF;
    END LOOP;

    IF v_policy.require_tests THEN
        IF NOT EXISTS (
            SELECT 1
              FROM cicd.stage_executions se
              JOIN cicd.stage_definitions sd
                ON sd.stage_id = se.stage_id
             WHERE se.run_id = p_run_id
               AND sd.stage_name = 'test'
               AND se.status = 'succeeded'
        ) THEN
            v_blockers := array_append(
                v_blockers,
                'Required test stage has not succeeded'
            );
        END IF;

        IF NOT EXISTS (
            SELECT 1
              FROM cicd.test_results tr
              JOIN cicd.stage_executions se
                ON se.stage_execution_id = tr.stage_execution_id
              JOIN cicd.stage_definitions sd
                ON sd.stage_id = se.stage_id
             WHERE se.run_id = p_run_id
               AND sd.stage_name = 'test'
        ) THEN
            v_blockers := array_append(
                v_blockers,
                'No test results were recorded'
            );
        END IF;

        IF EXISTS (
            SELECT 1
              FROM cicd.test_results tr
              JOIN cicd.stage_executions se
                ON se.stage_execution_id = tr.stage_execution_id
             WHERE se.run_id = p_run_id
               AND tr.status = 'failed'
        ) THEN
            v_blockers := array_append(
                v_blockers,
                'One or more automated tests failed'
            );
        END IF;

        IF EXISTS (
            SELECT 1
              FROM cicd.test_results tr
              JOIN cicd.stage_executions se
                ON se.stage_execution_id = tr.stage_execution_id
             WHERE se.run_id = p_run_id
               AND tr.status = 'skipped'
        ) THEN
            v_blockers := array_append(
                v_blockers,
                'One or more required test cases were skipped'
            );
        END IF;
    END IF;

    IF v_policy.minimum_pass_rate > 0 THEN
        IF EXISTS (
            SELECT 1
              FROM cicd.test_results tr
              JOIN cicd.stage_executions se
                ON se.stage_execution_id = tr.stage_execution_id
             WHERE se.run_id = p_run_id
             GROUP BY se.run_id
            HAVING
                100.0 * COUNT(*) FILTER (WHERE tr.status = 'passed')
                / NULLIF(COUNT(*), 0) < v_policy.minimum_pass_rate
        ) THEN
            v_blockers := array_append(
                v_blockers,
                format(
                    'Test pass rate is below the required %s percent',
                    v_policy.minimum_pass_rate
                )
            );
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM cicd.security_findings sf
          JOIN cicd.stage_executions se
            ON se.stage_execution_id = sf.stage_execution_id
         WHERE se.run_id = p_run_id
           AND CASE sf.severity
               WHEN 'low' THEN 1
               WHEN 'medium' THEN 2
               WHEN 'high' THEN 3
               WHEN 'critical' THEN 4
           END >=
           CASE v_policy.blocking_severity
               WHEN 'low' THEN 1
               WHEN 'medium' THEN 2
               WHEN 'high' THEN 3
               WHEN 'critical' THEN 4
           END
    ) THEN
        v_blockers := array_append(
            v_blockers,
            format(
                'Security findings meet or exceed blocking severity %s',
                v_policy.blocking_severity
            )
        );
    END IF;

    IF v_policy.require_package AND NOT EXISTS (
        SELECT 1
          FROM cicd.build_artifacts ba
          JOIN cicd.stage_executions se
            ON se.stage_execution_id = ba.stage_execution_id
          JOIN cicd.stage_definitions sd
            ON sd.stage_id = se.stage_id
         WHERE se.run_id = p_run_id
           AND sd.stage_name = 'package'
           AND se.status = 'succeeded'
    ) THEN
        v_blockers := array_append(
            v_blockers,
            'Required release package is missing'
        );
    END IF;

    IF v_policy.require_docker_image AND NOT EXISTS (
        SELECT 1
          FROM cicd.docker_images di
          JOIN cicd.stage_executions se
            ON se.stage_execution_id = di.stage_execution_id
         WHERE se.run_id = p_run_id
    ) THEN
        v_blockers := array_append(
            v_blockers,
            'Required Docker image is missing'
        );
    END IF;

    RETURN QUERY
    SELECT cardinality(v_blockers) = 0, v_blockers;
END;
$$;

CREATE VIEW cicd.v_run_stage_summary AS
SELECT
    pr.run_id,
    pr.pipeline_id,
    pr.source_branch,
    pr.commit_sha,
    pr.status AS run_status,
    jsonb_object_agg(
        sd.stage_name,
        jsonb_build_object(
            'status', se.status,
            'attempt', se.attempt,
            'started_at', se.started_at,
            'finished_at', se.finished_at,
            'exit_code', se.exit_code
        )
        ORDER BY sd.sequence_no
    ) AS stages
FROM cicd.pipeline_runs pr
JOIN cicd.stage_executions se ON se.run_id = pr.run_id
JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
GROUP BY
    pr.run_id,
    pr.pipeline_id,
    pr.source_branch,
    pr.commit_sha,
    pr.status;

CREATE VIEW cicd.v_pipeline_run_report AS
SELECT
    pr.run_id,
    pd.pipeline_name,
    pr.source_branch,
    pr.commit_sha,
    pr.status AS run_status,
    COUNT(DISTINCT se.stage_execution_id) AS stage_count,
    COUNT(DISTINCT se.stage_execution_id)
        FILTER (WHERE se.status = 'succeeded') AS successful_stages,
    COUNT(DISTINCT tr.test_result_id)
        FILTER (WHERE tr.status = 'passed') AS passed_tests,
    COUNT(DISTINCT tr.test_result_id)
        FILTER (WHERE tr.status = 'failed') AS failed_tests,
    COUNT(DISTINCT sf.finding_id) AS security_findings,
    COUNT(DISTINCT ba.artifact_id) AS package_artifacts,
    COUNT(DISTINCT di.image_id) AS docker_images,
    pr.created_at,
    pr.finished_at
FROM cicd.pipeline_runs pr
JOIN cicd.pipeline_definitions pd ON pd.pipeline_id = pr.pipeline_id
LEFT JOIN cicd.stage_executions se ON se.run_id = pr.run_id
LEFT JOIN cicd.test_results tr ON tr.stage_execution_id = se.stage_execution_id
LEFT JOIN cicd.security_findings sf ON sf.stage_execution_id = se.stage_execution_id
LEFT JOIN cicd.build_artifacts ba ON ba.stage_execution_id = se.stage_execution_id
LEFT JOIN cicd.docker_images di ON di.stage_execution_id = se.stage_execution_id
GROUP BY
    pr.run_id,
    pd.pipeline_name,
    pr.source_branch,
    pr.commit_sha,
    pr.status,
    pr.created_at,
    pr.finished_at;

-- Register a realistic application pipeline and its ordered stages.
INSERT INTO cicd.pipeline_definitions (
    pipeline_name,
    application_name,
    application_version
)
VALUES (
    'inventory-service-release',
    'inventory-health-service',
    '1.0.0'
);

INSERT INTO cicd.stage_definitions (
    pipeline_id,
    stage_name,
    sequence_no,
    is_required,
    timeout_seconds
)
SELECT
    pipeline_id,
    stage_name,
    sequence_no,
    TRUE,
    600
FROM cicd.pipeline_definitions
CROSS JOIN (
    VALUES
        ('build', 1),
        ('test', 2),
        ('scan', 3),
        ('package', 4),
        ('dockerize', 5)
) AS stages(stage_name, sequence_no)
WHERE pipeline_name = 'inventory-service-release';

INSERT INTO cicd.pipeline_policies (
    pipeline_id,
    require_tests,
    require_package,
    require_docker_image,
    blocking_severity,
    minimum_pass_rate
)
SELECT
    pipeline_id,
    TRUE,
    TRUE,
    TRUE,
    'high',
    100.00
FROM cicd.pipeline_definitions
WHERE pipeline_name = 'inventory-service-release';

-- Create two separate runs and initialize their five stage records atomically.
DO $$
DECLARE
    v_pipeline_id BIGINT;
    v_success_run BIGINT;
    v_failure_run BIGINT;
    v_stage RECORD;
    v_execution_id BIGINT;
BEGIN
    SELECT pipeline_id
      INTO v_pipeline_id
      FROM cicd.pipeline_definitions
     WHERE pipeline_name = 'inventory-service-release';

    v_success_run := cicd.create_run(
        v_pipeline_id,
        repeat('a', 40),
        'main',
        'release-bot'
    );

    v_failure_run := cicd.create_run(
        v_pipeline_id,
        repeat('b', 40),
        'feature/security-update',
        'developer-01'
    );

    -- Successful run: execute each required stage in order.
    FOR v_stage IN
        SELECT stage_id, stage_name
          FROM cicd.stage_definitions
         WHERE pipeline_id = v_pipeline_id
         ORDER BY sequence_no
    LOOP
        SELECT stage_execution_id
          INTO v_execution_id
          FROM cicd.stage_executions
         WHERE run_id = v_success_run
           AND stage_id = v_stage.stage_id;

        UPDATE cicd.stage_executions
           SET status = 'running'
         WHERE stage_execution_id = v_execution_id;

        UPDATE cicd.stage_executions
           SET status = 'succeeded',
               exit_code = 0,
               details = jsonb_build_object(
                   'runner', 'linux-x86_64',
                   'stage', v_stage.stage_name
               )
         WHERE stage_execution_id = v_execution_id;

        IF v_stage.stage_name = 'test' THEN
            INSERT INTO cicd.test_results (
                stage_execution_id,
                test_name,
                status,
                duration_ms
            )
            VALUES
                (v_execution_id, 'inventory_add_valid_item', 'passed', 3.5),
                (v_execution_id, 'inventory_reject_duplicate', 'passed', 2.1),
                (v_execution_id, 'inventory_reject_invalid_quantity', 'passed', 1.8);
        END IF;

        IF v_stage.stage_name = 'scan' THEN
            INSERT INTO cicd.security_findings (
                stage_execution_id,
                rule_code,
                severity,
                file_path,
                line_number,
                fingerprint,
                description
            )
            VALUES (
                v_execution_id,
                'DEP-LOW-001',
                'low',
                'src/service.py',
                18,
                'low-finding-001',
                'A low-severity maintenance advisory was recorded.'
            );
        END IF;

        IF v_stage.stage_name = 'package' THEN
            INSERT INTO cicd.build_artifacts (
                stage_execution_id,
                artifact_name,
                artifact_type,
                storage_location,
                sha256,
                size_bytes
            )
            VALUES (
                v_execution_id,
                'inventory-health-service-1.0.0.zip',
                'release-archive',
                'artifacts/inventory-health-service-1.0.0.zip',
                repeat('c', 64),
                18432
            );
        END IF;

        IF v_stage.stage_name = 'dockerize' THEN
            INSERT INTO cicd.docker_images (
                stage_execution_id,
                image_tag,
                image_digest,
                base_image,
                runs_as_non_root
            )
            VALUES (
                v_execution_id,
                'inventory-health-service:1.0.0',
                'sha256:' || repeat('d', 64),
                'python:3.12-slim',
                TRUE
            );
        END IF;
    END LOOP;

    -- Failure run: build and test pass, but the security gate blocks the run.
    SELECT stage_id
      INTO v_execution_id
      FROM cicd.stage_definitions
     WHERE pipeline_id = v_pipeline_id
       AND stage_name = 'build';

    UPDATE cicd.stage_executions
       SET status = 'running'
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;

    UPDATE cicd.stage_executions
       SET status = 'succeeded',
           exit_code = 0
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;

    SELECT stage_id
      INTO v_execution_id
      FROM cicd.stage_definitions
     WHERE pipeline_id = v_pipeline_id
       AND stage_name = 'test';

    UPDATE cicd.stage_executions
       SET status = 'running'
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;

    UPDATE cicd.stage_executions
       SET status = 'succeeded',
           exit_code = 0
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;

    INSERT INTO cicd.test_results (
        stage_execution_id,
        test_name,
        status,
        duration_ms
    )
    SELECT
        se.stage_execution_id,
        'inventory_regression_test',
        'passed',
        4.2
    FROM cicd.stage_executions se
    JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
    WHERE se.run_id = v_failure_run
      AND sd.stage_name = 'test';

    SELECT stage_id
      INTO v_execution_id
      FROM cicd.stage_definitions
     WHERE pipeline_id = v_pipeline_id
       AND stage_name = 'scan';

    UPDATE cicd.stage_executions
       SET status = 'running'
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;

    INSERT INTO cicd.security_findings (
        stage_execution_id,
        rule_code,
        severity,
        file_path,
        line_number,
        fingerprint,
        description
    )
    SELECT
        se.stage_execution_id,
        'CVE-HIGH-2026-001',
        'high',
        'dependencies.lock',
        42,
        'high-finding-001',
        'A high-severity dependency vulnerability blocks release packaging.'
    FROM cicd.stage_executions se
    JOIN cicd.stage_definitions sd ON sd.stage_id = se.stage_id
    WHERE se.run_id = v_failure_run
      AND sd.stage_name = 'scan';

    UPDATE cicd.stage_executions
       SET status = 'failed',
           exit_code = 1,
           details = jsonb_build_object(
               'reason', 'Blocking security finding',
               'policy', 'high severity findings prevent release'
           )
     WHERE run_id = v_failure_run
       AND stage_id = v_execution_id;
END;
$$;

-- Confirm that a stage-order violation is rejected without changing the database.
DO $$
DECLARE
    v_run_id BIGINT;
    v_pipeline_id BIGINT;
    v_package_stage_id BIGINT;
    v_rejected BOOLEAN := FALSE;
BEGIN
    SELECT pipeline_id
      INTO v_pipeline_id
      FROM cicd.pipeline_definitions
     WHERE pipeline_name = 'inventory-service-release';

    SELECT run_id
      INTO v_run_id
      FROM cicd.pipeline_runs
     WHERE source_branch = 'feature/security-update';

    SELECT stage_id
      INTO v_package_stage_id
      FROM cicd.stage_definitions
     WHERE pipeline_id = v_pipeline_id
       AND stage_name = 'package';

    BEGIN
        UPDATE cicd.stage_executions
           SET status = 'running'
         WHERE run_id = v_run_id
           AND stage_id = v_package_stage_id;
    EXCEPTION
        WHEN raise_exception THEN
            v_rejected := TRUE;
    END;

    IF NOT v_rejected THEN
        RAISE EXCEPTION 'Stage-order validation did not reject package execution';
    END IF;

    RAISE NOTICE 'Stage-order validation correctly rejected an early package stage.';
END;
$$;

-- Run-level report with counts for build, test, scan, package and Dockerize.
SELECT *
FROM cicd.v_pipeline_run_report
ORDER BY run_id;

-- Detailed stage states for each pipeline run.
SELECT
    run_id,
    source_branch,
    run_status,
    stages
FROM cicd.v_run_stage_summary
ORDER BY run_id;

-- Evaluate release eligibility for every recorded run.
SELECT
    pr.run_id,
    pr.source_branch,
    evaluation.eligible,
    evaluation.blockers
FROM cicd.pipeline_runs pr
CROSS JOIN LATERAL cicd.evaluate_run(pr.run_id) AS evaluation
ORDER BY pr.run_id;

-- Inspect all security findings and their stage relationships.
SELECT
    pr.run_id,
    pr.source_branch,
    sf.rule_code,
    sf.severity,
    sf.file_path,
    sf.line_number,
    sf.description
FROM cicd.security_findings sf
JOIN cicd.stage_executions se
    ON se.stage_execution_id = sf.stage_execution_id
JOIN cicd.pipeline_runs pr
    ON pr.run_id = se.run_id
ORDER BY pr.run_id, sf.severity DESC;

-- Inspect artifact metadata and release checksums.
SELECT
    pr.run_id,
    ba.artifact_name,
    ba.artifact_type,
    ba.storage_location,
    ba.sha256,
    ba.size_bytes
FROM cicd.build_artifacts ba
JOIN cicd.stage_executions se
    ON se.stage_execution_id = ba.stage_execution_id
JOIN cicd.pipeline_runs pr
    ON pr.run_id = se.run_id
ORDER BY pr.run_id;

-- Review the container properties required by the release policy.
SELECT
    pr.run_id,
    di.image_tag,
    di.image_digest,
    di.base_image,
    di.runs_as_non_root
FROM cicd.docker_images di
JOIN cicd.stage_executions se
    ON se.stage_execution_id = di.stage_execution_id
JOIN cicd.pipeline_runs pr
    ON pr.run_id = se.run_id
ORDER BY pr.run_id;

COMMIT;

DROP SCHEMA IF EXISTS jenkins_demo CASCADE;
CREATE SCHEMA jenkins_demo;

SET search_path = jenkins_demo, public;

CREATE TYPE job_status AS ENUM ('ENABLED', 'DISABLED');
CREATE TYPE build_status AS ENUM ('SUCCESS', 'FAILURE', 'ABORTED');
CREATE TYPE trigger_type AS ENUM ('MANUAL', 'TIMER', 'SCM', 'UPSTREAM');
CREATE TYPE parameter_type AS ENUM ('STRING', 'CHOICE', 'BOOLEAN');

CREATE TABLE jobs (
    job_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name        text NOT NULL UNIQUE,
    description     text NOT NULL DEFAULT '',
    status          job_status NOT NULL DEFAULT 'ENABLED',
    workspace_root  text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT jobs_name_format
        CHECK (job_name ~ '^[A-Za-z0-9._-]+$')
);

CREATE TABLE job_parameters (
    parameter_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id           bigint NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    parameter_name   text NOT NULL,
    parameter_type   parameter_type NOT NULL,
    default_value    text NOT NULL DEFAULT '',
    required         boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_job_parameter UNIQUE (job_id, parameter_name),
    CONSTRAINT parameter_name_format
        CHECK (parameter_name ~ '^[A-Za-z_][A-Za-z0-9_]*$')
);

CREATE TABLE parameter_choices (
    parameter_id bigint NOT NULL
        REFERENCES job_parameters(parameter_id) ON DELETE CASCADE,
    choice_value text NOT NULL,
    PRIMARY KEY (parameter_id, choice_value)
);

CREATE TABLE job_triggers (
    job_id       bigint NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    trigger_type trigger_type NOT NULL,
    PRIMARY KEY (job_id, trigger_type)
);

CREATE TABLE build_steps (
    step_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id        bigint NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    step_order    integer NOT NULL CHECK (step_order > 0),
    step_name     text NOT NULL,
    command_text  text NOT NULL,
    enabled       boolean NOT NULL DEFAULT true,
    UNIQUE (job_id, step_order),
    UNIQUE (job_id, step_name)
);

CREATE TABLE builds (
    build_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id         bigint NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    build_number   integer NOT NULL CHECK (build_number > 0),
    trigger_type   trigger_type NOT NULL,
    status         build_status NOT NULL DEFAULT 'ABORTED',
    workspace_path text NOT NULL,
    started_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at    timestamptz,
    UNIQUE (job_id, build_number),
    CONSTRAINT build_finish_after_start
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE build_parameters (
    build_id       bigint NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
    parameter_id   bigint NOT NULL
        REFERENCES job_parameters(parameter_id),
    parameter_value text NOT NULL,
    PRIMARY KEY (build_id, parameter_id)
);

CREATE TABLE build_step_results (
    result_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id       bigint NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
    step_id        bigint NOT NULL REFERENCES build_steps(step_id),
    status         build_status NOT NULL,
    output_text    text NOT NULL DEFAULT '',
    started_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at    timestamptz,
    UNIQUE (build_id, step_id),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_builds_job_started
    ON builds (job_id, started_at DESC);

CREATE INDEX idx_builds_status
    ON builds (status);

CREATE INDEX idx_build_parameters_value
    ON build_parameters (parameter_value);

CREATE OR REPLACE FUNCTION validate_choice_parameter()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    p_type parameter_type;
BEGIN
    SELECT parameter_type
    INTO p_type
    FROM job_parameters
    WHERE parameter_id = NEW.parameter_id;

    IF p_type = 'CHOICE'
       AND NOT EXISTS (
           SELECT 1
           FROM parameter_choices
           WHERE parameter_id = NEW.parameter_id
             AND choice_value = NEW.parameter_value
       )
    THEN
        RAISE EXCEPTION
            'Value "%" is not valid for choice parameter %',
            NEW.parameter_value,
            NEW.parameter_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_choice_parameter
BEFORE INSERT OR UPDATE ON build_parameters
FOR EACH ROW
EXECUTE FUNCTION validate_choice_parameter();

CREATE OR REPLACE FUNCTION next_build_number(
    p_job_id bigint
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    next_number integer;
BEGIN
    SELECT COALESCE(MAX(build_number), 0) + 1
    INTO next_number
    FROM builds
    WHERE job_id = p_job_id
    FOR UPDATE;

    RETURN next_number;
END;
$$;

CREATE OR REPLACE FUNCTION start_build(
    p_job_name text,
    p_trigger trigger_type,
    p_workspace text,
    p_parameter_values jsonb
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_job_id bigint;
    v_build_id bigint;
    v_build_number integer;
    v_parameter record;
    v_value text;
BEGIN
    SELECT job_id
    INTO v_job_id
    FROM jobs
    WHERE job_name = p_job_name
      AND status = 'ENABLED'
    FOR UPDATE;

    IF v_job_id IS NULL THEN
        RAISE EXCEPTION
            'Enabled job "%" was not found',
            p_job_name;
    END IF;

    IF p_trigger <> 'MANUAL'
       AND NOT EXISTS (
           SELECT 1
           FROM job_triggers
           WHERE job_id = v_job_id
             AND trigger_type = p_trigger
       )
    THEN
        RAISE EXCEPTION
            'Trigger % is not configured for job %',
            p_trigger,
            p_job_name;
    END IF;

    v_build_number := next_build_number(v_job_id);

    INSERT INTO builds (
        job_id,
        build_number,
        trigger_type,
        status,
        workspace_path
    )
    VALUES (
        v_job_id,
        v_build_number,
        p_trigger,
        'ABORTED',
        p_workspace
    )
    RETURNING build_id INTO v_build_id;

    FOR v_parameter IN
        SELECT *
        FROM job_parameters
        WHERE job_id = v_job_id
        ORDER BY parameter_id
    LOOP
        v_value :=
            COALESCE(
                p_parameter_values ->> v_parameter.parameter_name,
                v_parameter.default_value
            );

        IF v_parameter.required
           AND btrim(v_value) = ''
        THEN
            RAISE EXCEPTION
                'Required parameter "%" is empty',
                v_parameter.parameter_name;
        END IF;

        INSERT INTO build_parameters (
            build_id,
            parameter_id,
            parameter_value
        )
        VALUES (
            v_build_id,
            v_parameter.parameter_id,
            v_value
        );
    END LOOP;

    RETURN v_build_id;
END;
$$;

CREATE OR REPLACE PROCEDURE finish_build(
    p_build_id bigint,
    p_status build_status
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE builds
    SET status = p_status,
        finished_at = clock_timestamp()
    WHERE build_id = p_build_id
      AND finished_at IS NULL;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Build % does not exist or is already finished',
            p_build_id;
    END IF;
END;
$$;

CREATE VIEW v_job_build_history AS
SELECT
    j.job_name,
    b.build_number,
    b.trigger_type,
    b.status,
    b.workspace_path,
    b.started_at,
    b.finished_at,
    count(bp.parameter_id) AS parameter_count
FROM jobs j
JOIN builds b
  ON b.job_id = j.job_id
LEFT JOIN build_parameters bp
  ON bp.build_id = b.build_id
GROUP BY
    j.job_name,
    b.build_number,
    b.trigger_type,
    b.status,
    b.workspace_path,
    b.started_at,
    b.finished_at;

CREATE VIEW v_latest_build AS
SELECT DISTINCT ON (j.job_id)
    j.job_id,
    j.job_name,
    b.build_id,
    b.build_number,
    b.status,
    b.trigger_type,
    b.started_at,
    b.finished_at
FROM jobs j
JOIN builds b
  ON b.job_id = j.job_id
ORDER BY
    j.job_id,
    b.build_number DESC;

INSERT INTO jobs (
    job_name,
    description,
    workspace_root
)
VALUES (
    'release-application',
    'Parameterized release Freestyle job',
    '/var/lib/jenkins/workspace'
);

INSERT INTO job_parameters (
    job_id,
    parameter_name,
    parameter_type,
    default_value,
    required
)
SELECT
    job_id,
    'ENVIRONMENT',
    'CHOICE',
    'staging',
    true
FROM jobs
WHERE job_name = 'release-application';

INSERT INTO job_parameters (
    job_id,
    parameter_name,
    parameter_type,
    default_value,
    required
)
SELECT
    job_id,
    'VERSION',
    'STRING',
    '1.0.0',
    true
FROM jobs
WHERE job_name = 'release-application';

INSERT INTO parameter_choices (
    parameter_id,
    choice_value
)
SELECT
    parameter_id,
    choice_value
FROM job_parameters
CROSS JOIN (
    VALUES
        ('development'),
        ('staging'),
        ('production')
) AS choices(choice_value)
WHERE parameter_name = 'ENVIRONMENT';

INSERT INTO job_triggers (job_id, trigger_type)
SELECT job_id, trigger_type
FROM jobs
CROSS JOIN (
    VALUES
        ('TIMER'::trigger_type),
        ('SCM'::trigger_type),
        ('UPSTREAM'::trigger_type)
) AS configured(trigger_type)
WHERE job_name = 'release-application';

INSERT INTO build_steps (
    job_id,
    step_order,
    step_name,
    command_text
)
SELECT
    job_id,
    step_order,
    step_name,
    command_text
FROM jobs
CROSS JOIN (
    VALUES
        (
            1,
            'Validate Parameters',
            'validate environment and version'
        ),
        (
            2,
            'Prepare Workspace',
            'create build workspace and manifest'
        ),
        (
            3,
            'Package Artifact',
            'create versioned application artifact'
        )
) AS steps(step_order, step_name, command_text)
WHERE job_name = 'release-application';

BEGIN;

SELECT start_build(
    'release-application',
    'SCM',
    '/var/lib/jenkins/workspace/release-application/build-1',
    '{"ENVIRONMENT":"staging","VERSION":"1.4.0"}'::jsonb
);

UPDATE builds
SET status = 'SUCCESS',
    finished_at = clock_timestamp()
WHERE job_id = (
    SELECT job_id
    FROM jobs
    WHERE job_name = 'release-application'
)
AND build_number = 1;

COMMIT;

BEGIN;

SELECT start_build(
    'release-application',
    'UPSTREAM',
    '/var/lib/jenkins/workspace/release-application/build-2',
    '{"ENVIRONMENT":"production","VERSION":"dev-2.0.0"}'::jsonb
);

UPDATE builds
SET status = 'FAILURE',
    finished_at = clock_timestamp()
WHERE job_id = (
    SELECT job_id
    FROM jobs
    WHERE job_name = 'release-application'
)
AND build_number = 2;

COMMIT;

BEGIN;

SELECT start_build(
    'release-application',
    'MANUAL',
    '/var/lib/jenkins/workspace/release-application/build-3',
    '{"ENVIRONMENT":"production","VERSION":"2.0.0"}'::jsonb
);

UPDATE builds
SET status = 'SUCCESS',
    finished_at = clock_timestamp()
WHERE job_id = (
    SELECT job_id
    FROM jobs
    WHERE job_name = 'release-application'
)
AND build_number = 3;

COMMIT;

-- Retrieval: inspect configured Freestyle jobs and their triggers.
SELECT
    j.job_name,
    j.status,
    jt.trigger_type
FROM jobs j
LEFT JOIN job_triggers jt
    ON jt.job_id = j.job_id
ORDER BY j.job_name, jt.trigger_type;

-- Parameter validation: show the values captured by each build.
SELECT
    j.job_name,
    b.build_number,
    p.parameter_name,
    bp.parameter_value
FROM builds b
JOIN jobs j
    ON j.job_id = b.job_id
JOIN build_parameters bp
    ON bp.build_id = b.build_id
JOIN job_parameters p
    ON p.parameter_id = bp.parameter_id
ORDER BY
    j.job_name,
    b.build_number,
    p.parameter_name;

-- Aggregation: build outcomes by job and status.
SELECT
    j.job_name,
    b.status,
    count(*) AS build_count
FROM jobs j
JOIN builds b
    ON b.job_id = j.job_id
GROUP BY j.job_name, b.status
ORDER BY j.job_name, b.status;

-- Workflow reporting: most recent build per job.
SELECT *
FROM v_latest_build;

-- Evaluation: identify jobs whose latest build failed.
SELECT
    job_name,
    build_number,
    status,
    trigger_type
FROM v_latest_build
WHERE status = 'FAILURE';

-- State reporting: complete build history with duration.
SELECT
    job_name,
    build_number,
    trigger_type,
    status,
    finished_at - started_at AS duration
FROM v_job_build_history
ORDER BY job_name, build_number;

-- Eligibility-style query: a successful build is operationally usable
-- only when the job is enabled and the configured build reached SUCCESS.
SELECT
    j.job_name,
    b.build_number,
    (
        j.status = 'ENABLED'
        AND b.status = 'SUCCESS'
    ) AS eligible_for_artifact_use
FROM jobs j
JOIN v_latest_build b
    ON b.job_id = j.job_id;

-- Failure-case query: locate production builds using development versions.
SELECT
    j.job_name,
    b.build_number,
    b.status,
    bp.parameter_value AS version
FROM jobs j
JOIN builds b
    ON b.job_id = j.job_id
JOIN build_parameters bp
    ON bp.build_id = b.build_id
JOIN job_parameters p
    ON p.parameter_id = bp.parameter_id
WHERE p.parameter_name = 'VERSION'
  AND bp.parameter_value LIKE 'dev-%';

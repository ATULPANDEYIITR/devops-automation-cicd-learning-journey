-- Jenkins Fundamentals relational model:
-- controllers, agents, jobs, executors, queues, builds, workspaces,
-- job labels, build results, and operational reporting.

DROP SCHEMA IF EXISTS jenkins_fundamentals CASCADE;
CREATE SCHEMA jenkins_fundamentals;
SET search_path TO jenkins_fundamentals, public;

CREATE TYPE agent_status AS ENUM ('online', 'offline', 'temporarily_unavailable');
CREATE TYPE job_type AS ENUM ('freestyle', 'pipeline');
CREATE TYPE build_status AS ENUM ('queued', 'running', 'success', 'failure', 'aborted');
CREATE TYPE job_state AS ENUM ('enabled', 'disabled');

CREATE TABLE controllers (
    controller_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    controller_name TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL CHECK (version ~ '^[0-9]+(\.[0-9]+){1,2}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE agents (
    agent_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    controller_id BIGINT NOT NULL REFERENCES controllers(controller_id),
    agent_name TEXT NOT NULL,
    status agent_status NOT NULL DEFAULT 'online',
    executor_count INTEGER NOT NULL CHECK (executor_count > 0),
    os_name TEXT NOT NULL,
    architecture TEXT NOT NULL,
    last_connected_at TIMESTAMPTZ,
    UNIQUE (controller_id, agent_name)
);

CREATE TABLE agent_labels (
    agent_id BIGINT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    PRIMARY KEY (agent_id, label)
);

CREATE TABLE jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    controller_id BIGINT NOT NULL REFERENCES controllers(controller_id),
    job_name TEXT NOT NULL,
    job_type job_type NOT NULL,
    state job_state NOT NULL DEFAULT 'enabled',
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (controller_id, job_name)
);

CREATE TABLE job_required_labels (
    job_id BIGINT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    PRIMARY KEY (job_id, label)
);

CREATE TABLE commits (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sha CHAR(40) NOT NULL UNIQUE CHECK (sha ~ '^[0-9a-f]{40}$'),
    message TEXT NOT NULL CHECK (length(trim(message)) > 0),
    author_name TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE build_queue (
    queue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(job_id),
    commit_id BIGINT NOT NULL REFERENCES commits(commit_id),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    priority INTEGER NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
    UNIQUE (job_id, commit_id)
);

CREATE TABLE builds (
    build_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(job_id),
    build_number INTEGER NOT NULL CHECK (build_number > 0),
    commit_id BIGINT NOT NULL REFERENCES commits(commit_id),
    agent_id BIGINT REFERENCES agents(agent_id),
    status build_status NOT NULL DEFAULT 'queued',
    workspace_path TEXT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    failure_reason TEXT,
    UNIQUE (job_id, build_number),
    CHECK (
        finished_at IS NULL
        OR started_at IS NOT NULL
        AND finished_at >= started_at
    ),
    CHECK (
        status NOT IN ('success', 'failure', 'aborted')
        OR finished_at IS NOT NULL
    )
);

CREATE TABLE build_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id BIGINT NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'queued',
            'assigned',
            'workspace_created',
            'checkout',
            'validation',
            'started',
            'completed',
            'failed'
        )
    ),
    event_message TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agents_controller_status
    ON agents(controller_id, status);

CREATE INDEX idx_agent_labels_label
    ON agent_labels(label);

CREATE INDEX idx_jobs_controller_state
    ON jobs(controller_id, state);

CREATE INDEX idx_queue_priority
    ON build_queue(priority DESC, queued_at);

CREATE INDEX idx_builds_job_status
    ON builds(job_id, status);

CREATE INDEX idx_build_events_build_time
    ON build_events(build_id, event_at);

CREATE OR REPLACE FUNCTION next_build_number(p_job_id BIGINT)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    next_number INTEGER;
BEGIN
    SELECT COALESCE(MAX(build_number), 0) + 1
    INTO next_number
    FROM builds
    WHERE job_id = p_job_id;

    RETURN next_number;
END;
$$;

CREATE OR REPLACE FUNCTION validate_build_assignment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    required_label_count INTEGER;
    matching_label_count INTEGER;
    current_status agent_status;
BEGIN
    IF NEW.agent_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT status
    INTO current_status
    FROM agents
    WHERE agent_id = NEW.agent_id;

    IF current_status IS DISTINCT FROM 'online' THEN
        RAISE EXCEPTION
            'Build % cannot use agent % because the agent is not online',
            NEW.build_id,
            NEW.agent_id;
    END IF;

    SELECT COUNT(*)
    INTO required_label_count
    FROM job_required_labels
    WHERE job_id = NEW.job_id;

    SELECT COUNT(*)
    INTO matching_label_count
    FROM job_required_labels jrl
    JOIN agent_labels al
      ON al.label = jrl.label
     AND al.agent_id = NEW.agent_id
    WHERE jrl.job_id = NEW.job_id;

    IF required_label_count <> matching_label_count THEN
        RAISE EXCEPTION
            'Agent % does not satisfy required labels for job %',
            NEW.agent_id,
            NEW.job_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_build_assignment
BEFORE INSERT OR UPDATE OF agent_id, job_id
ON builds
FOR EACH ROW
EXECUTE FUNCTION validate_build_assignment();

CREATE OR REPLACE FUNCTION validate_build_timestamps()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.started_at IS NOT NULL
       AND NEW.started_at < NEW.queued_at THEN
        RAISE EXCEPTION
            'Build start time cannot precede queue time';
    END IF;

    IF NEW.finished_at IS NOT NULL
       AND NEW.started_at IS NULL THEN
        RAISE EXCEPTION
            'A finished build must have a start time';
    END IF;

    IF NEW.finished_at IS NOT NULL
       AND NEW.finished_at < NEW.started_at THEN
        RAISE EXCEPTION
            'Build finish time cannot precede start time';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_build_timestamps
BEFORE INSERT OR UPDATE
ON builds
FOR EACH ROW
EXECUTE FUNCTION validate_build_timestamps();

CREATE OR REPLACE VIEW build_execution_report AS
SELECT
    b.build_id,
    j.job_name,
    j.job_type,
    b.build_number,
    c.sha,
    c.message,
    a.agent_name,
    b.status,
    b.queued_at,
    b.started_at,
    b.finished_at,
    CASE
        WHEN b.started_at IS NOT NULL AND b.finished_at IS NOT NULL
        THEN ROUND(
            EXTRACT(EPOCH FROM (b.finished_at - b.started_at))::numeric,
            3
        )
        ELSE NULL
    END AS execution_seconds,
    b.failure_reason
FROM builds b
JOIN jobs j
  ON j.job_id = b.job_id
JOIN commits c
  ON c.commit_id = b.commit_id
LEFT JOIN agents a
  ON a.agent_id = b.agent_id;

CREATE OR REPLACE FUNCTION enqueue_build(
    p_job_id BIGINT,
    p_commit_id BIGINT,
    p_priority INTEGER DEFAULT 100
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    new_queue_id BIGINT;
    job_is_enabled BOOLEAN;
BEGIN
    SELECT state = 'enabled'
    INTO job_is_enabled
    FROM jobs
    WHERE job_id = p_job_id;

    IF job_is_enabled IS NULL THEN
        RAISE EXCEPTION 'Unknown job %', p_job_id;
    END IF;

    IF NOT job_is_enabled THEN
        RAISE EXCEPTION 'Job % is disabled', p_job_id;
    END IF;

    INSERT INTO build_queue (
        job_id,
        commit_id,
        priority
    )
    VALUES (
        p_job_id,
        p_commit_id,
        p_priority
    )
    RETURNING queue_id INTO new_queue_id;

    RETURN new_queue_id;
END;
$$;

CREATE OR REPLACE FUNCTION create_build_from_queue(
    p_queue_id BIGINT,
    p_agent_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    queue_row RECORD;
    new_build_id BIGINT;
    new_number INTEGER;
BEGIN
    SELECT *
    INTO queue_row
    FROM build_queue
    WHERE queue_id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Queue item % does not exist', p_queue_id;
    END IF;

    new_number := next_build_number(queue_row.job_id);

    INSERT INTO builds (
        job_id,
        build_number,
        commit_id,
        agent_id,
        status,
        started_at,
        workspace_path
    )
    VALUES (
        queue_row.job_id,
        new_number,
        queue_row.commit_id,
        p_agent_id,
        'running',
        CURRENT_TIMESTAMP,
        '/var/lib/jenkins/workspace/'
            || queue_row.job_id
            || '/'
            || new_number
    )
    RETURNING build_id INTO new_build_id;

    INSERT INTO build_events (
        build_id,
        event_type,
        event_message
    )
    VALUES (
        new_build_id,
        'assigned',
        'Build assigned to compatible online agent'
    );

    DELETE FROM build_queue
    WHERE queue_id = p_queue_id;

    RETURN new_build_id;
END;
$$;

INSERT INTO controllers (controller_name, version)
VALUES ('main-controller', '2.561.1');

INSERT INTO agents (
    controller_id,
    agent_name,
    status,
    executor_count,
    os_name,
    architecture,
    last_connected_at
)
VALUES
(
    1,
    'linux-python-01',
    'online',
    2,
    'Linux',
    'amd64',
    CURRENT_TIMESTAMP
),
(
    1,
    'linux-java-01',
    'online',
    1,
    'Linux',
    'amd64',
    CURRENT_TIMESTAMP
),
(
    1,
    'offline-python-01',
    'offline',
    1,
    'Linux',
    'amd64',
    CURRENT_TIMESTAMP - INTERVAL '2 days'
);

INSERT INTO agent_labels (agent_id, label)
VALUES
(1, 'linux'),
(1, 'python'),
(1, 'container'),
(2, 'linux'),
(2, 'java'),
(3, 'linux'),
(3, 'python');

INSERT INTO jobs (
    controller_id,
    job_name,
    job_type,
    state,
    description
)
VALUES
(
    1,
    'python-service',
    'pipeline',
    'enabled',
    'Build and validate a Python service'
),
(
    1,
    'java-service',
    'freestyle',
    'enabled',
    'Build and validate a Java service'
),
(
    1,
    'disabled-maintenance-job',
    'freestyle',
    'disabled',
    'Example of a disabled job'
);

INSERT INTO job_required_labels (job_id, label)
VALUES
(1, 'linux'),
(1, 'python'),
(2, 'linux'),
(2, 'java');

INSERT INTO commits (
    sha,
    message,
    author_name,
    committed_at
)
VALUES
(
    'a1b2c3d4e5f60123456789012345678901234567',
    'Validate Python service configuration',
    'Atul',
    CURRENT_TIMESTAMP - INTERVAL '3 hours'
),
(
    '11223344556677889900aabbccddeeff00112233',
    'Improve Java service validation',
    'Riya',
    CURRENT_TIMESTAMP - INTERVAL '2 hours'
),
(
    'e5f6a7b8c9d00123456789012345678901234567',
    '[FAIL] exercise deterministic failure handling',
    'DevOps',
    CURRENT_TIMESTAMP - INTERVAL '1 hour'
);

BEGIN;

SELECT enqueue_build(1, 1, 200);
SELECT enqueue_build(2, 2, 150);
SELECT enqueue_build(1, 3, 100);

COMMIT;

-- A compatible online agent can receive a queued build.
SELECT create_build_from_queue(1, 1);

UPDATE builds
SET
    status = 'success',
    finished_at = CURRENT_TIMESTAMP
WHERE build_id = 1;

INSERT INTO build_events (
    build_id,
    event_type,
    event_message
)
VALUES
(1, 'queued', 'Build entered the Jenkins queue'),
(1, 'started', 'Build started on linux-python-01'),
(1, 'checkout', 'Source checkout validated'),
(1, 'validation', 'Build validation completed'),
(1, 'completed', 'Build finished successfully');

-- The second queue item is assigned to the Java-compatible agent.
SELECT create_build_from_queue(2, 2);

UPDATE builds
SET
    status = 'success',
    finished_at = CURRENT_TIMESTAMP
WHERE build_id = 2;

INSERT INTO build_events (
    build_id,
    event_type,
    event_message
)
VALUES
(2, 'queued', 'Build entered the Jenkins queue'),
(2, 'started', 'Build started on linux-java-01'),
(2, 'checkout', 'Source checkout validated'),
(2, 'validation', 'Java build validation completed'),
(2, 'completed', 'Build finished successfully');

-- The third queued build is deliberately failed after assignment.
SELECT create_build_from_queue(3, 1);

UPDATE builds
SET
    status = 'failure',
    finished_at = CURRENT_TIMESTAMP,
    failure_reason = 'Validation failed for the requested failure scenario'
WHERE build_id = 3;

INSERT INTO build_events (
    build_id,
    event_type,
    event_message
)
VALUES
(3, 'queued', 'Build entered the Jenkins queue'),
(3, 'started', 'Build started on linux-python-01'),
(3, 'checkout', 'Source checkout completed'),
(3, 'failed', 'Build validation failed');

-- Retrieval: current build execution state.
SELECT *
FROM build_execution_report
ORDER BY job_name, build_number;

-- Aggregation: success/failure distribution by job.
SELECT
    job_name,
    COUNT(*) AS total_builds,
    COUNT(*) FILTER (WHERE status = 'success') AS successful_builds,
    COUNT(*) FILTER (WHERE status = 'failure') AS failed_builds,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'success')
        / NULLIF(COUNT(*), 0),
        2
    ) AS success_rate_percent
FROM build_execution_report
GROUP BY job_name
ORDER BY job_name;

-- Validation: identify jobs whose required labels are not completely
-- represented by any currently online agent.
WITH required AS (
    SELECT
        j.job_id,
        j.job_name,
        COUNT(*) AS required_count
    FROM jobs j
    JOIN job_required_labels r
      ON r.job_id = j.job_id
    WHERE j.state = 'enabled'
    GROUP BY j.job_id, j.job_name
),
compatible AS (
    SELECT
        j.job_id,
        COUNT(*) AS online_compatible_agents
    FROM jobs j
    JOIN agents a
      ON a.status = 'online'
    WHERE NOT EXISTS (
        SELECT 1
        FROM job_required_labels r
        WHERE r.job_id = j.job_id
          AND NOT EXISTS (
              SELECT 1
              FROM agent_labels al
              WHERE al.agent_id = a.agent_id
                AND al.label = r.label
          )
    )
    GROUP BY j.job_id
)
SELECT
    required.job_name,
    required.required_count,
    COALESCE(compatible.online_compatible_agents, 0)
        AS online_compatible_agents
FROM required
LEFT JOIN compatible
  ON compatible.job_id = required.job_id
ORDER BY required.job_name;

-- Workflow state: queued work and its priority.
SELECT
    q.queue_id,
    j.job_name,
    c.sha,
    q.priority,
    q.queued_at
FROM build_queue q
JOIN jobs j
  ON j.job_id = q.job_id
JOIN commits c
  ON c.commit_id = q.commit_id
ORDER BY q.priority DESC, q.queued_at;

-- Reporting: average execution duration for completed builds.
SELECT
    j.job_name,
    COUNT(*) AS completed_builds,
    ROUND(
        AVG(
            EXTRACT(EPOCH FROM (b.finished_at - b.started_at))
        )::numeric,
        3
    ) AS average_execution_seconds
FROM builds b
JOIN jobs j
  ON j.job_id = b.job_id
WHERE b.finished_at IS NOT NULL
GROUP BY j.job_name
ORDER BY j.job_name;

-- Operational state: executor capacity versus current assignment.
SELECT
    a.agent_name,
    a.status,
    a.executor_count,
    COUNT(b.build_id) FILTER (
        WHERE b.status = 'running'
    ) AS running_builds,
    a.executor_count
        - COUNT(b.build_id) FILTER (
            WHERE b.status = 'running'
        ) AS available_executor_slots
FROM agents a
LEFT JOIN builds b
  ON b.agent_id = a.agent_id
GROUP BY
    a.agent_id,
    a.agent_name,
    a.status,
    a.executor_count
ORDER BY a.agent_name;

-- CTE-based build failure report.
WITH failures AS (
    SELECT
        b.build_id,
        j.job_name,
        b.build_number,
        b.failure_reason
    FROM builds b
    JOIN jobs j
      ON j.job_id = b.job_id
    WHERE b.status = 'failure'
)
SELECT
    job_name,
    build_number,
    failure_reason
FROM failures
ORDER BY job_name, build_number;

-- Transactional demonstration:
-- a disabled job cannot enter the queue.
BEGIN;

DO $$
BEGIN
    IF (
        SELECT state
        FROM jobs
        WHERE job_id = 3
    ) <> 'disabled' THEN
        RAISE EXCEPTION 'Expected maintenance job to be disabled';
    END IF;
END
$$;

ROLLBACK;

-- The final report is intentionally based on database-enforced state,
-- rather than trusting application-only validation.
SELECT
    controller_name,
    version,
    created_at
FROM controllers;

SELECT
    j.job_name,
    j.job_type,
    j.state,
    COUNT(r.label) AS required_labels
FROM jobs j
LEFT JOIN job_required_labels r
  ON r.job_id = j.job_id
GROUP BY
    j.job_id,
    j.job_name,
    j.job_type,
    j.state
ORDER BY j.job_name;

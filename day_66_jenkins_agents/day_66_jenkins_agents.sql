/*
    JENKINS AGENTS
    PostgreSQL 15+

    Relational model for:
    - Jenkins controllers
    - Static and dynamic agents
    - Agent labels and executors
    - Distributed build requests
    - Build queue
    - Agent assignments
    - Execution attempts
    - Provisioning events
    - Agent lifecycle
    - Scheduling policies
    - Capacity and utilization reporting

    All timestamps use TIMESTAMPTZ.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS jenkins_lab;

SET search_path TO jenkins_lab, public;

-- =========================================================
-- 1. ENUMERATIONS
-- =========================================================

CREATE TYPE agent_type AS ENUM (
    'STATIC',
    'DYNAMIC'
);

CREATE TYPE agent_status AS ENUM (
    'ONLINE',
    'BUSY',
    'OFFLINE',
    'TERMINATED'
);

CREATE TYPE build_status AS ENUM (
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE build_priority AS ENUM (
    'LOW',
    'NORMAL',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE attempt_status AS ENUM (
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'TIMED_OUT',
    'CANCELLED'
);

-- =========================================================
-- 2. CONTROLLERS
-- =========================================================

CREATE TABLE controllers (
    controller_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    controller_name VARCHAR(120) NOT NULL UNIQUE,

    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'STAGING',
                'PRODUCTION'
            )
        ),

    endpoint TEXT NOT NULL,

    max_dynamic_agents INTEGER NOT NULL DEFAULT 5
        CHECK (max_dynamic_agents >= 0),

    status VARCHAR(20) NOT NULL DEFAULT 'ONLINE'
        CHECK (
            status IN ('ONLINE', 'OFFLINE', 'MAINTENANCE')
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 3. AGENTS
-- =========================================================

CREATE TABLE agents (
    agent_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    controller_id BIGINT NOT NULL
        REFERENCES controllers(controller_id),

    agent_name VARCHAR(120) NOT NULL,

    agent_type agent_type NOT NULL,

    status agent_status NOT NULL DEFAULT 'ONLINE',

    executors INTEGER NOT NULL DEFAULT 1
        CHECK (executors > 0),

    max_builds INTEGER,

    completed_builds INTEGER NOT NULL DEFAULT 0
        CHECK (completed_builds >= 0),

    connection_secret_hash TEXT,

    cloud_instance_id VARCHAR(200),

    provisioned_at TIMESTAMPTZ,

    last_seen_at TIMESTAMPTZ,

    last_used_at TIMESTAMPTZ,

    terminated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(controller_id, agent_name),

    CHECK (
        max_builds IS NULL OR max_builds > 0
    ),

    CHECK (
        agent_type <> 'DYNAMIC'
        OR max_builds IS NOT NULL
    ),

    CHECK (
        agent_type <> 'STATIC'
        OR cloud_instance_id IS NULL
    ),

    CHECK (
        status <> 'TERMINATED'
        OR terminated_at IS NOT NULL
    )
);

CREATE INDEX idx_agents_controller_status
    ON agents(controller_id, status);

CREATE INDEX idx_agents_type_status
    ON agents(agent_type, status);

-- =========================================================
-- 4. AGENT LABELS
-- =========================================================

CREATE TABLE agent_labels (
    agent_id BIGINT NOT NULL
        REFERENCES agents(agent_id) ON DELETE CASCADE,

    label VARCHAR(80) NOT NULL
        CHECK (label ~ '^[a-zA-Z0-9_.-]+$'),

    PRIMARY KEY(agent_id, label)
);

CREATE INDEX idx_agent_labels_label
    ON agent_labels(label, agent_id);

-- =========================================================
-- 5. BUILD REQUESTS
-- =========================================================

CREATE TABLE builds (
    build_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    controller_id BIGINT NOT NULL
        REFERENCES controllers(controller_id),

    job_name VARCHAR(200) NOT NULL,

    status build_status NOT NULL DEFAULT 'QUEUED',

    priority build_priority NOT NULL DEFAULT 'NORMAL',

    estimated_seconds INTEGER NOT NULL
        CHECK (estimated_seconds > 0),

    max_retries INTEGER NOT NULL DEFAULT 0
        CHECK (max_retries >= 0),

    retry_count INTEGER NOT NULL DEFAULT 0
        CHECK (retry_count >= 0),

    submitted_by VARCHAR(120) NOT NULL,

    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    assigned_agent_id BIGINT
        REFERENCES agents(agent_id),

    error_message TEXT,

    CHECK (retry_count <= max_retries),

    CHECK (
        status <> 'RUNNING'
        OR (
            assigned_agent_id IS NOT NULL
            AND started_at IS NOT NULL
        )
    ),

    CHECK (
        status NOT IN ('SUCCESS', 'FAILED', 'CANCELLED')
        OR completed_at IS NOT NULL
    )
);

CREATE INDEX idx_builds_queue
    ON builds(
        controller_id,
        priority DESC,
        queued_at ASC
    )
    WHERE status = 'QUEUED';

CREATE INDEX idx_builds_agent_status
    ON builds(assigned_agent_id, status);

CREATE INDEX idx_builds_job_history
    ON builds(job_name, queued_at DESC);

-- =========================================================
-- 6. BUILD LABEL REQUIREMENTS
-- =========================================================

CREATE TABLE build_required_labels (
    build_id BIGINT NOT NULL
        REFERENCES builds(build_id) ON DELETE CASCADE,

    label VARCHAR(80) NOT NULL
        CHECK (label ~ '^[a-zA-Z0-9_.-]+$'),

    PRIMARY KEY(build_id, label)
);

CREATE INDEX idx_build_required_labels_label
    ON build_required_labels(label, build_id);

-- =========================================================
-- 7. BUILD EXECUTION ATTEMPTS
-- =========================================================

CREATE TABLE build_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    build_id BIGINT NOT NULL
        REFERENCES builds(build_id),

    agent_id BIGINT NOT NULL
        REFERENCES agents(agent_id),

    attempt_number INTEGER NOT NULL
        CHECK (attempt_number > 0),

    status attempt_status NOT NULL DEFAULT 'RUNNING',

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    execution_seconds NUMERIC(12, 2)
        CHECK (
            execution_seconds IS NULL
            OR execution_seconds >= 0
        ),

    error_message TEXT,

    UNIQUE(build_id, attempt_number),

    CHECK (
        status = 'RUNNING'
        OR completed_at IS NOT NULL
    )
);

CREATE UNIQUE INDEX idx_one_running_attempt_per_build
    ON build_attempts(build_id)
    WHERE status = 'RUNNING';

CREATE INDEX idx_attempts_agent_history
    ON build_attempts(agent_id, started_at DESC);

-- =========================================================
-- 8. PROVISIONING EVENTS
-- =========================================================

CREATE TABLE provisioning_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    controller_id BIGINT NOT NULL
        REFERENCES controllers(controller_id),

    agent_id BIGINT
        REFERENCES agents(agent_id),

    event_type VARCHAR(30) NOT NULL
        CHECK (
            event_type IN (
                'PROVISION_REQUESTED',
                'PROVISIONED',
                'PROVISION_FAILED',
                'TERMINATED',
                'CLEANUP_FAILED'
            )
        ),

    cloud_instance_id VARCHAR(200),

    event_message TEXT,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_provisioning_controller_time
    ON provisioning_events(controller_id, occurred_at DESC);

-- =========================================================
-- 9. SCHEDULING POLICIES
-- =========================================================

CREATE TABLE scheduling_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    controller_id BIGINT NOT NULL
        REFERENCES controllers(controller_id),

    policy_name VARCHAR(120) NOT NULL,

    prefer_static_agents BOOLEAN NOT NULL DEFAULT TRUE,

    allow_dynamic_agents BOOLEAN NOT NULL DEFAULT TRUE,

    max_concurrent_builds INTEGER NOT NULL DEFAULT 20
        CHECK (max_concurrent_builds > 0),

    idle_timeout_seconds INTEGER NOT NULL DEFAULT 300
        CHECK (idle_timeout_seconds >= 0),

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE(controller_id, policy_name)
);

-- =========================================================
-- 10. TRIGGER: AGENT LIFECYCLE VALIDATION
-- =========================================================

CREATE OR REPLACE FUNCTION validate_agent_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'TERMINATED'
       AND NEW.status <> 'TERMINATED' THEN
        RAISE EXCEPTION
            'Terminated agents cannot be reactivated';
    END IF;

    IF NEW.status = 'TERMINATED'
       AND NEW.terminated_at IS NULL THEN
        NEW.terminated_at := CURRENT_TIMESTAMP;
    END IF;

    IF NEW.status = 'ONLINE'
       AND NEW.terminated_at IS NOT NULL THEN
        RAISE EXCEPTION
            'Terminated agent cannot become online';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_agent_lifecycle
BEFORE UPDATE ON agents
FOR EACH ROW
EXECUTE FUNCTION validate_agent_lifecycle();

-- =========================================================
-- 11. TRIGGER: BUILD STATE VALIDATION
-- =========================================================

CREATE OR REPLACE FUNCTION validate_build_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('SUCCESS', 'FAILED', 'CANCELLED')
       AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION
            'A completed build cannot be reopened directly';
    END IF;

    IF OLD.status = 'QUEUED'
       AND NEW.status NOT IN ('QUEUED', 'RUNNING', 'CANCELLED') THEN
        RAISE EXCEPTION
            'Invalid transition from QUEUED to %', NEW.status;
    END IF;

    IF OLD.status = 'RUNNING'
       AND NEW.status NOT IN (
           'RUNNING',
           'QUEUED',
           'SUCCESS',
           'FAILED',
           'CANCELLED'
       ) THEN
        RAISE EXCEPTION
            'Invalid transition from RUNNING to %', NEW.status;
    END IF;

    IF NEW.status = 'RUNNING' THEN
        IF NEW.assigned_agent_id IS NULL THEN
            RAISE EXCEPTION
                'Running build requires an assigned agent';
        END IF;

        IF NEW.started_at IS NULL THEN
            NEW.started_at := CURRENT_TIMESTAMP;
        END IF;
    END IF;

    IF NEW.status IN ('SUCCESS', 'FAILED', 'CANCELLED') THEN
        NEW.completed_at := COALESCE(
            NEW.completed_at,
            CURRENT_TIMESTAMP
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_build_transition
BEFORE UPDATE ON builds
FOR EACH ROW
EXECUTE FUNCTION validate_build_transition();

-- =========================================================
-- 12. FUNCTION: CHECK AGENT ELIGIBILITY
-- =========================================================

CREATE OR REPLACE FUNCTION is_agent_eligible(
    p_build_id BIGINT,
    p_agent_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT
        a.status = 'ONLINE'
        AND a.completed_builds < COALESCE(a.max_builds, 2147483647)
        AND (
            SELECT COUNT(*)
            FROM build_attempts ba
            WHERE ba.agent_id = a.agent_id
              AND ba.status = 'RUNNING'
        ) < a.executors
        AND NOT EXISTS (
            SELECT 1
            FROM build_required_labels required
            WHERE required.build_id = p_build_id
              AND NOT EXISTS (
                  SELECT 1
                  FROM agent_labels available
                  WHERE available.agent_id = a.agent_id
                    AND available.label = required.label
              )
        )
    FROM agents a
    WHERE a.agent_id = p_agent_id;
$$;

-- =========================================================
-- 13. FUNCTION: FIND ELIGIBLE AGENTS
-- =========================================================

CREATE OR REPLACE FUNCTION find_eligible_agents(
    p_build_id BIGINT
)
RETURNS TABLE (
    agent_id BIGINT,
    agent_name VARCHAR,
    agent_type agent_type,
    available_executors BIGINT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        a.agent_id,
        a.agent_name::VARCHAR,
        a.agent_type,
        a.executors - COUNT(ba.attempt_id) AS available_executors
    FROM agents a
    LEFT JOIN build_attempts ba
        ON ba.agent_id = a.agent_id
       AND ba.status = 'RUNNING'
    WHERE a.status = 'ONLINE'
      AND a.completed_builds < COALESCE(a.max_builds, 2147483647)
      AND EXISTS (
          SELECT 1
          FROM controllers c
          WHERE c.controller_id = a.controller_id
            AND c.controller_id = (
                SELECT controller_id
                FROM builds
                WHERE builds.build_id = p_build_id
            )
      )
      AND NOT EXISTS (
          SELECT 1
          FROM build_required_labels required
          WHERE required.build_id = p_build_id
            AND NOT EXISTS (
                SELECT 1
                FROM agent_labels available
                WHERE available.agent_id = a.agent_id
                  AND available.label = required.label
            )
      )
    GROUP BY a.agent_id
    HAVING COUNT(ba.attempt_id) < a.executors
    ORDER BY
        CASE WHEN a.agent_type = 'STATIC' THEN 0 ELSE 1 END,
        COUNT(ba.attempt_id),
        a.agent_id;
$$;

-- =========================================================
-- 14. PROCEDURE: ASSIGN A BUILD
-- =========================================================

CREATE OR REPLACE PROCEDURE assign_build(
    p_build_id BIGINT,
    p_agent_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_build builds%ROWTYPE;
    v_attempt_number INTEGER;
BEGIN
    -- Lock the build to prevent concurrent assignment.
    SELECT *
    INTO v_build
    FROM builds
    WHERE build_id = p_build_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Build % does not exist', p_build_id;
    END IF;

    IF v_build.status <> 'QUEUED' THEN
        RAISE EXCEPTION 'Build is not queued';
    END IF;

    -- Lock the agent to serialize executor allocation.
    PERFORM 1
    FROM agents
    WHERE agent_id = p_agent_id
      AND controller_id = v_build.controller_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Agent does not belong to the build controller';
    END IF;

    IF NOT is_agent_eligible(p_build_id, p_agent_id) THEN
        RAISE EXCEPTION
            'Agent is not eligible for build %', p_build_id;
    END IF;

    SELECT COALESCE(MAX(attempt_number), 0) + 1
    INTO v_attempt_number
    FROM build_attempts
    WHERE build_id = p_build_id;

    IF v_attempt_number > v_build.max_retries + 1 THEN
        RAISE EXCEPTION 'Build retry limit exceeded';
    END IF;

    INSERT INTO build_attempts (
        build_id,
        agent_id,
        attempt_number,
        status
    )
    VALUES (
        p_build_id,
        p_agent_id,
        v_attempt_number,
        'RUNNING'
    );

    UPDATE builds
    SET
        status = 'RUNNING',
        assigned_agent_id = p_agent_id,
        started_at = CURRENT_TIMESTAMP,
        retry_count = v_attempt_number - 1
    WHERE build_id = p_build_id;

    UPDATE agents
    SET
        status = 'BUSY',
        last_used_at = CURRENT_TIMESTAMP
    WHERE agent_id = p_agent_id;

END;
$$;

-- =========================================================
-- 15. PROCEDURE: COMPLETE A BUILD ATTEMPT
-- =========================================================

CREATE OR REPLACE PROCEDURE complete_build(
    p_build_id BIGINT,
    p_success BOOLEAN,
    p_error TEXT DEFAULT NULL,
    p_execution_seconds NUMERIC DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_build builds%ROWTYPE;
    v_attempt build_attempts%ROWTYPE;
    v_new_status build_status;
    v_attempt_status attempt_status;
BEGIN
    IF p_execution_seconds IS NOT NULL
       AND p_execution_seconds < 0 THEN
        RAISE EXCEPTION
            'Execution duration cannot be negative';
    END IF;

    SELECT *
    INTO v_build
    FROM builds
    WHERE build_id = p_build_id
    FOR UPDATE;

    IF NOT FOUND OR v_build.status <> 'RUNNING' THEN
        RAISE EXCEPTION
            'Build must exist and be running';
    END IF;

    SELECT *
    INTO v_attempt
    FROM build_attempts
    WHERE build_id = p_build_id
      AND status = 'RUNNING'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Running attempt does not exist';
    END IF;

    IF p_success THEN
        v_new_status := 'SUCCESS';
        v_attempt_status := 'SUCCESS';
    ELSIF v_build.retry_count < v_build.max_retries THEN
        v_new_status := 'QUEUED';
        v_attempt_status := 'FAILED';
    ELSE
        v_new_status := 'FAILED';
        v_attempt_status := 'FAILED';
    END IF;

    UPDATE build_attempts
    SET
        status = v_attempt_status,
        completed_at = CURRENT_TIMESTAMP,
        execution_seconds = p_execution_seconds,
        error_message = CASE
            WHEN p_success THEN NULL
            ELSE COALESCE(p_error, 'Build failed')
        END
    WHERE attempt_id = v_attempt.attempt_id;

    UPDATE builds
    SET
        status = v_new_status,
        assigned_agent_id = NULL,
        completed_at = CASE
            WHEN v_new_status IN ('SUCCESS', 'FAILED')
                THEN CURRENT_TIMESTAMP
            ELSE NULL
        END,
        error_message = CASE
            WHEN p_success THEN NULL
            ELSE COALESCE(p_error, 'Build failed')
        END
    WHERE build_id = p_build_id;

    UPDATE agents
    SET
        completed_builds = completed_builds + 1,
        status = CASE
            WHEN (
                SELECT COUNT(*)
                FROM build_attempts
                WHERE agent_id = v_attempt.agent_id
                  AND status = 'RUNNING'
            ) = 0
            THEN 'ONLINE'::agent_status
            ELSE 'BUSY'::agent_status
        END,
        last_used_at = CURRENT_TIMESTAMP
    WHERE agent_id = v_attempt.agent_id;

END;
$$;

-- =========================================================
-- 16. VIEW: AGENT CAPACITY
-- =========================================================

CREATE VIEW agent_capacity AS
SELECT
    a.agent_id,
    a.agent_name,
    a.agent_type,
    a.status,
    a.executors,

    COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'RUNNING'
    ) AS active_builds,

    a.executors - COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'RUNNING'
    ) AS available_executors,

    a.completed_builds,
    a.max_builds

FROM agents a

LEFT JOIN build_attempts ba
    ON ba.agent_id = a.agent_id

GROUP BY a.agent_id;

-- =========================================================
-- 17. VIEW: BUILD QUEUE
-- =========================================================

CREATE VIEW queued_build_details AS
SELECT
    b.build_id,
    b.job_name,
    b.priority,
    b.estimated_seconds,
    b.queued_at,

    ARRAY(
        SELECT label
        FROM build_required_labels brl
        WHERE brl.build_id = b.build_id
        ORDER BY label
    ) AS required_labels,

    EXTRACT(
        EPOCH FROM CURRENT_TIMESTAMP - b.queued_at
    )::NUMERIC(12, 2) AS waiting_seconds

FROM builds b
WHERE b.status = 'QUEUED';

-- =========================================================
-- 18. SAMPLE DATA: CONTROLLERS
-- =========================================================

INSERT INTO controllers (
    controller_name,
    environment,
    endpoint,
    max_dynamic_agents
)
VALUES
(
    'jenkins-production',
    'PRODUCTION',
    'https://jenkins.example.internal',
    5
),
(
    'jenkins-staging',
    'STAGING',
    'https://staging-jenkins.example.internal',
    3
);

-- =========================================================
-- 19. SAMPLE DATA: STATIC AND DYNAMIC AGENTS
-- =========================================================

INSERT INTO agents (
    controller_id,
    agent_name,
    agent_type,
    status,
    executors,
    max_builds,
    last_seen_at
)
VALUES
(
    1,
    'linux-static-01',
    'STATIC',
    'ONLINE',
    2,
    NULL,
    CURRENT_TIMESTAMP
),
(
    1,
    'windows-static-01',
    'STATIC',
    'ONLINE',
    2,
    NULL,
    CURRENT_TIMESTAMP
),
(
    1,
    'cloud-linux-01',
    'DYNAMIC',
    'ONLINE',
    1,
    1,
    CURRENT_TIMESTAMP
),
(
    1,
    'cloud-linux-terminated',
    'DYNAMIC',
    'TERMINATED',
    1,
    1,
    CURRENT_TIMESTAMP
);

UPDATE agents
SET
    cloud_instance_id = 'i-cloud-terminated-001',
    provisioned_at = CURRENT_TIMESTAMP,
    terminated_at = CURRENT_TIMESTAMP
WHERE agent_name = 'cloud-linux-terminated';

-- =========================================================
-- 20. SAMPLE DATA: LABELS
-- =========================================================

INSERT INTO agent_labels(agent_id, label)
SELECT a.agent_id, labels.label
FROM agents a
CROSS JOIN LATERAL (
    SELECT unnest(
        CASE a.agent_name
            WHEN 'linux-static-01'
                THEN ARRAY[
                    'linux',
                    'python',
                    'docker'
                ]
            WHEN 'windows-static-01'
                THEN ARRAY[
                    'windows',
                    'dotnet'
                ]
            WHEN 'cloud-linux-01'
                THEN ARRAY[
                    'linux',
                    'security',
                    'ephemeral'
                ]
            WHEN 'cloud-linux-terminated'
                THEN ARRAY[
                    'linux',
                    'ephemeral'
                ]
        END
    ) AS label
) labels;

-- =========================================================
-- 21. SCHEDULING POLICIES
-- =========================================================

INSERT INTO scheduling_policies (
    controller_id,
    policy_name,
    prefer_static_agents,
    allow_dynamic_agents,
    max_concurrent_builds,
    idle_timeout_seconds
)
VALUES
(
    1,
    'production-default',
    TRUE,
    TRUE,
    20,
    300
),
(
    2,
    'staging-restricted',
    TRUE,
    FALSE,
    5,
    600
);

-- =========================================================
-- 22. SAMPLE BUILD REQUESTS
-- =========================================================

INSERT INTO builds (
    controller_id,
    job_name,
    status,
    priority,
    estimated_seconds,
    max_retries,
    submitted_by
)
VALUES
(
    1,
    'Python Unit Tests',
    'QUEUED',
    'HIGH',
    60,
    1,
    'developer-01'
),
(
    1,
    'Docker Image Build',
    'QUEUED',
    'NORMAL',
    120,
    1,
    'developer-02'
),
(
    1,
    'Windows Integration Tests',
    'QUEUED',
    'HIGH',
    180,
    0,
    'developer-03'
),
(
    1,
    'Security Scan',
    'QUEUED',
    'CRITICAL',
    90,
    2,
    'security-team'
),
(
    1,
    'Completed Historical Build',
    'SUCCESS',
    'NORMAL',
    30,
    0,
    'developer-01'
),
(
    1,
    'Cancelled Build',
    'CANCELLED',
    'LOW',
    30,
    0,
    'developer-04'
);

-- Add terminal timestamps for sample terminal states.
UPDATE builds
SET completed_at = CURRENT_TIMESTAMP
WHERE status IN ('SUCCESS', 'CANCELLED');

-- =========================================================
-- 23. SAMPLE BUILD LABEL REQUIREMENTS
-- =========================================================

INSERT INTO build_required_labels(build_id, label)
SELECT b.build_id, requirements.label
FROM builds b
JOIN (
    VALUES
        ('Python Unit Tests', 'linux'),
        ('Python Unit Tests', 'python'),
        ('Docker Image Build', 'linux'),
        ('Docker Image Build', 'docker'),
        ('Windows Integration Tests', 'windows'),
        ('Windows Integration Tests', 'dotnet'),
        ('Security Scan', 'linux'),
        ('Security Scan', 'security'),
        ('Completed Historical Build', 'linux'),
        ('Cancelled Build', 'linux')
) AS requirements(job_name, label)
ON b.job_name = requirements.job_name;

-- =========================================================
-- 24. SAMPLE HISTORICAL ATTEMPT
-- =========================================================

INSERT INTO build_attempts (
    build_id,
    agent_id,
    attempt_number,
    status,
    completed_at,
    execution_seconds
)
SELECT
    b.build_id,
    a.agent_id,
    1,
    'SUCCESS',
    CURRENT_TIMESTAMP,
    27.50
FROM builds b
CROSS JOIN agents a
WHERE b.job_name = 'Completed Historical Build'
  AND a.agent_name = 'linux-static-01';

UPDATE agents
SET completed_builds = completed_builds + 1
WHERE agent_name = 'linux-static-01';

-- =========================================================
-- 25. SAMPLE PROVISIONING EVENTS
-- =========================================================

INSERT INTO provisioning_events (
    controller_id,
    agent_id,
    event_type,
    cloud_instance_id,
    event_message
)
SELECT
    controller_id,
    agent_id,
    'PROVISIONED',
    cloud_instance_id,
    'Dynamic Linux agent successfully provisioned'
FROM agents
WHERE agent_name = 'cloud-linux-01';

INSERT INTO provisioning_events (
    controller_id,
    event_type,
    event_message
)
VALUES
(
    1,
    'PROVISION_FAILED',
    'Cloud capacity temporarily unavailable'
);

-- =========================================================
-- 26. RETRIEVAL: AGENT INVENTORY
-- =========================================================

SELECT
    a.agent_name,
    a.agent_type,
    a.status,
    a.executors,
    a.completed_builds,
    ARRAY_AGG(al.label ORDER BY al.label) AS labels
FROM agents a
LEFT JOIN agent_labels al
    ON al.agent_id = a.agent_id
GROUP BY a.agent_id
ORDER BY a.agent_type, a.agent_name;

-- =========================================================
-- 27. RETRIEVAL: QUEUED BUILDS
-- =========================================================

SELECT *
FROM queued_build_details
ORDER BY
    CASE priority
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'NORMAL' THEN 3
        WHEN 'LOW' THEN 4
    END,
    queued_at;

-- =========================================================
-- 28. VALIDATION: LABEL COMPATIBILITY
-- =========================================================

SELECT
    b.build_id,
    b.job_name,
    a.agent_name,
    is_agent_eligible(b.build_id, a.agent_id) AS eligible
FROM builds b
CROSS JOIN agents a
WHERE b.status = 'QUEUED'
  AND a.status <> 'TERMINATED'
ORDER BY b.build_id, a.agent_id;

-- =========================================================
-- 29. EVALUATION: ELIGIBLE AGENTS FOR ONE BUILD
-- =========================================================

SELECT *
FROM find_eligible_agents(
    (
        SELECT build_id
        FROM builds
        WHERE job_name = 'Python Unit Tests'
        LIMIT 1
    )
);

-- =========================================================
-- 30. REPORTING: AGENT UTILIZATION
-- =========================================================

SELECT
    a.agent_name,
    a.agent_type,
    a.executors,
    COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'RUNNING'
    ) AS running_builds,

    COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'SUCCESS'
    ) AS successful_attempts,

    COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'FAILED'
    ) AS failed_attempts,

    COALESCE(
        ROUND(
            AVG(ba.execution_seconds),
            2
        ),
        0
    ) AS average_execution_seconds

FROM agents a
LEFT JOIN build_attempts ba
    ON ba.agent_id = a.agent_id
GROUP BY a.agent_id
ORDER BY a.agent_name;

-- =========================================================
-- 31. REPORTING: BUILD PERFORMANCE
-- =========================================================

SELECT
    b.job_name,
    COUNT(ba.attempt_id) AS total_attempts,

    COUNT(*) FILTER (
        WHERE ba.status = 'SUCCESS'
    ) AS successful_attempts,

    COUNT(*) FILTER (
        WHERE ba.status = 'FAILED'
    ) AS failed_attempts,

    ROUND(
        AVG(ba.execution_seconds),
        2
    ) AS average_execution_seconds

FROM builds b
LEFT JOIN build_attempts ba
    ON ba.build_id = b.build_id
GROUP BY b.build_id
ORDER BY total_attempts DESC;

-- =========================================================
-- 32. AGGREGATION: STATIC VS DYNAMIC BUILDS
-- =========================================================

SELECT
    a.agent_type,
    COUNT(ba.attempt_id) AS total_attempts,
    COUNT(*) FILTER (
        WHERE ba.status = 'SUCCESS'
    ) AS successful_attempts,
    COUNT(*) FILTER (
        WHERE ba.status = 'FAILED'
    ) AS failed_attempts,
    ROUND(
        AVG(ba.execution_seconds),
        2
    ) AS mean_execution_seconds
FROM agents a
LEFT JOIN build_attempts ba
    ON ba.agent_id = a.agent_id
GROUP BY a.agent_type;

-- =========================================================
-- 33. WORKFLOW: ASSIGN A BUILD
-- =========================================================

-- The procedure locks the build and agent and validates
-- executor capacity and labels before making an assignment.

DO $$
DECLARE
    v_build_id BIGINT;
    v_agent_id BIGINT;
BEGIN
    SELECT build_id
    INTO v_build_id
    FROM builds
    WHERE job_name = 'Python Unit Tests'
      AND status = 'QUEUED'
    LIMIT 1;

    SELECT agent_id
    INTO v_agent_id
    FROM find_eligible_agents(v_build_id)
    LIMIT 1;

    IF v_build_id IS NOT NULL AND v_agent_id IS NOT NULL THEN
        CALL assign_build(v_build_id, v_agent_id);
    END IF;
END;
$$;

-- =========================================================
-- 34. WORKFLOW: COMPLETE THE ASSIGNED BUILD
-- =========================================================

DO $$
DECLARE
    v_build_id BIGINT;
BEGIN
    SELECT build_id
    INTO v_build_id
    FROM builds
    WHERE job_name = 'Python Unit Tests'
      AND status = 'RUNNING'
    LIMIT 1;

    IF v_build_id IS NOT NULL THEN
        CALL complete_build(
            v_build_id,
            TRUE,
            NULL,
            42.75
        );
    END IF;
END;
$$;

-- =========================================================
-- 35. VALIDATION: QUEUE AND EXECUTOR CAPACITY
-- =========================================================

SELECT
    a.agent_name,
    a.executors,
    COUNT(ba.attempt_id) FILTER (
        WHERE ba.status = 'RUNNING'
    ) AS active_executions,
    (
        a.executors -
        COUNT(ba.attempt_id) FILTER (
            WHERE ba.status = 'RUNNING'
        )
    ) AS remaining_capacity
FROM agents a
LEFT JOIN build_attempts ba
    ON ba.agent_id = a.agent_id
GROUP BY a.agent_id
ORDER BY a.agent_name;

-- =========================================================
-- 36. VALIDATION: DYNAMIC AGENT CAPACITY
-- =========================================================

SELECT
    c.controller_name,
    c.max_dynamic_agents,
    COUNT(a.agent_id) FILTER (
        WHERE a.agent_type = 'DYNAMIC'
          AND a.status <> 'TERMINATED'
    ) AS active_dynamic_agents,

    c.max_dynamic_agents -
    COUNT(a.agent_id) FILTER (
        WHERE a.agent_type = 'DYNAMIC'
          AND a.status <> 'TERMINATED'
    ) AS remaining_dynamic_capacity

FROM controllers c
LEFT JOIN agents a
    ON a.controller_id = c.controller_id
GROUP BY c.controller_id;

-- =========================================================
-- 37. CTE: BUILD QUEUE AGE AND PRIORITY
-- =========================================================

WITH queue_analysis AS (
    SELECT
        build_id,
        job_name,
        priority,
        queued_at,
        CURRENT_TIMESTAMP - queued_at AS waiting_duration,
        estimated_seconds
    FROM builds
    WHERE status = 'QUEUED'
)
SELECT
    build_id,
    job_name,
    priority,
    waiting_duration,
    estimated_seconds,
    CASE
        WHEN waiting_duration > INTERVAL '15 minutes'
            THEN 'LONG_WAIT'
        WHEN priority = 'CRITICAL'
            THEN 'EXPEDITE'
        ELSE 'NORMAL'
    END AS scheduling_recommendation
FROM queue_analysis
ORDER BY
    CASE priority
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'NORMAL' THEN 3
        WHEN 'LOW' THEN 4
    END,
    queued_at;

-- =========================================================
-- 38. TRANSACTION: CONTROLLED AGENT OFFLINE OPERATION
-- =========================================================

-- This transaction demonstrates safe agent maintenance.
-- It fails if the selected agent still has running builds.

DO $$
DECLARE
    v_agent_id BIGINT;
BEGIN
    SELECT agent_id
    INTO v_agent_id
    FROM agents
    WHERE agent_name = 'windows-static-01'
    FOR UPDATE;

    IF EXISTS (
        SELECT 1
        FROM build_attempts
        WHERE agent_id = v_agent_id
          AND status = 'RUNNING'
    ) THEN
        RAISE EXCEPTION
            'Agent cannot enter maintenance with active builds';
    END IF;

    UPDATE agents
    SET status = 'OFFLINE'
    WHERE agent_id = v_agent_id;
END;
$$;

-- Return the demonstration agent to service.
UPDATE agents
SET status = 'ONLINE'
WHERE agent_name = 'windows-static-01'
  AND status = 'OFFLINE';

-- =========================================================
-- 39. REPORTING: PROVISIONING FAILURES
-- =========================================================

SELECT
    c.controller_name,
    pe.event_type,
    pe.event_message,
    pe.occurred_at
FROM provisioning_events pe
JOIN controllers c
    ON c.controller_id = pe.controller_id
WHERE pe.event_type IN (
    'PROVISION_FAILED',
    'CLEANUP_FAILED'
)
ORDER BY pe.occurred_at DESC;

-- =========================================================
-- 40. REPORTING: DYNAMIC AGENT LIFECYCLE
-- =========================================================

SELECT
    agent_name,
    status,
    provisioned_at,
    last_used_at,
    terminated_at,
    CASE
        WHEN status = 'TERMINATED'
            THEN 'TERMINATED'
        WHEN last_used_at IS NULL
            THEN 'NEVER_USED'
        WHEN last_used_at <
            CURRENT_TIMESTAMP - INTERVAL '5 minutes'
            THEN 'POTENTIALLY_IDLE'
        ELSE 'RECENTLY_USED'
    END AS lifecycle_assessment
FROM agents
WHERE agent_type = 'DYNAMIC'
ORDER BY created_at DESC;

COMMIT;

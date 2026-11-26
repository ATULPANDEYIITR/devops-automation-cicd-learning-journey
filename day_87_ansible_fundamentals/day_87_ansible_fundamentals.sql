-- ============================================================
-- Ansible Fundamentals
-- Inventory, Modules, Playbooks, and Execution Tracking
-- PostgreSQL 14+
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ansible_lab;

SET search_path TO ansible_lab, public;

-- ------------------------------------------------------------
-- 1. Enumerated domain types
-- ------------------------------------------------------------

CREATE TYPE host_status AS ENUM (
    'active',
    'unreachable',
    'disabled'
);

CREATE TYPE task_status AS ENUM (
    'pending',
    'running',
    'ok',
    'changed',
    'failed',
    'skipped'
);

CREATE TYPE run_status AS ENUM (
    'pending',
    'running',
    'successful',
    'failed',
    'check_mode'
);

CREATE TYPE module_state AS ENUM (
    'present',
    'absent',
    'started',
    'stopped'
);

-- ------------------------------------------------------------
-- 2. Repository of managed infrastructure
-- ------------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    repository_name VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE inventory_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    group_name VARCHAR(100) NOT NULL,
    description TEXT,
    variables JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, group_name),

    CHECK (jsonb_typeof(variables) = 'object')
);

CREATE TABLE inventory_hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    hostname VARCHAR(120) NOT NULL,
    ansible_host INET NOT NULL,
    ansible_port INTEGER NOT NULL DEFAULT 22,
    ansible_user VARCHAR(100) NOT NULL DEFAULT 'ansible',
    host_status host_status NOT NULL DEFAULT 'active',
    variables JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, hostname),

    CHECK (ansible_port BETWEEN 1 AND 65535),
    CHECK (jsonb_typeof(variables) = 'object')
);

CREATE TABLE host_group_memberships (
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id)
        ON DELETE CASCADE,
    group_id BIGINT NOT NULL
        REFERENCES inventory_groups(group_id)
        ON DELETE CASCADE,

    PRIMARY KEY(host_id, group_id)
);

CREATE INDEX idx_hosts_repository_status
    ON inventory_hosts(repository_id, host_status);

CREATE INDEX idx_group_memberships_group
    ON host_group_memberships(group_id, host_id);

CREATE INDEX idx_hosts_variables
    ON inventory_hosts USING GIN(variables);

-- ------------------------------------------------------------
-- 3. Module registry
-- ------------------------------------------------------------

CREATE TABLE configuration_modules (
    module_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_name VARCHAR(80) NOT NULL UNIQUE,
    module_category VARCHAR(80) NOT NULL,
    description TEXT NOT NULL,
    supports_check_mode BOOLEAN NOT NULL DEFAULT TRUE,
    idempotent BOOLEAN NOT NULL DEFAULT TRUE,
    argument_schema JSONB NOT NULL DEFAULT '{}'::JSONB,

    CHECK (jsonb_typeof(argument_schema) = 'object')
);

INSERT INTO configuration_modules
    (module_name, module_category, description)
VALUES
    (
        'package',
        'software',
        'Manage installed software packages'
    ),
    (
        'service',
        'service_management',
        'Manage service state and startup configuration'
    ),
    (
        'file',
        'filesystem',
        'Manage files, directories, and permissions'
    ),
    (
        'command',
        'execution',
        'Execute controlled validation commands'
    );

-- ------------------------------------------------------------
-- 4. Playbooks and ordered tasks
-- ------------------------------------------------------------

CREATE TABLE playbooks (
    playbook_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    playbook_name VARCHAR(150) NOT NULL,
    description TEXT,
    target_pattern VARCHAR(120) NOT NULL DEFAULT 'all',
    variables JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, playbook_name),

    CHECK (jsonb_typeof(variables) = 'object')
);

CREATE TABLE playbook_tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id)
        ON DELETE CASCADE,
    module_id BIGINT NOT NULL
        REFERENCES configuration_modules(module_id),
    task_name VARCHAR(150) NOT NULL,
    task_order INTEGER NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::JSONB,
    condition_expression TEXT,
    ignore_errors BOOLEAN NOT NULL DEFAULT FALSE,
    notify_handler VARCHAR(150),

    UNIQUE(playbook_id, task_order),
    UNIQUE(playbook_id, task_name),

    CHECK (task_order > 0),
    CHECK (jsonb_typeof(arguments) = 'object')
);

CREATE INDEX idx_playbook_tasks_order
    ON playbook_tasks(playbook_id, task_order);

-- ------------------------------------------------------------
-- 5. Handlers
-- ------------------------------------------------------------

CREATE TABLE playbook_handlers (
    handler_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id)
        ON DELETE CASCADE,
    module_id BIGINT NOT NULL
        REFERENCES configuration_modules(module_id),
    handler_name VARCHAR(150) NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::JSONB,

    UNIQUE(playbook_id, handler_name),

    CHECK (jsonb_typeof(arguments) = 'object')
);

-- ------------------------------------------------------------
-- 6. Execution runs
-- ------------------------------------------------------------

CREATE TABLE playbook_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id),
    initiated_by VARCHAR(120) NOT NULL,
    execution_status run_status NOT NULL DEFAULT 'pending',
    check_mode BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,

    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    )
);

CREATE INDEX idx_runs_playbook_date
    ON playbook_runs(playbook_id, started_at DESC);

CREATE INDEX idx_runs_status
    ON playbook_runs(execution_status);

-- ------------------------------------------------------------
-- 7. Host-level task execution results
-- ------------------------------------------------------------

CREATE TABLE task_execution_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    run_id BIGINT NOT NULL
        REFERENCES playbook_runs(run_id)
        ON DELETE CASCADE,
    task_id BIGINT NOT NULL
        REFERENCES playbook_tasks(task_id),
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id),
    execution_status task_status NOT NULL DEFAULT 'pending',
    changed BOOLEAN NOT NULL DEFAULT FALSE,
    execution_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    UNIQUE(run_id, task_id, host_id),

    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    ),

    CHECK (
        changed = (execution_status = 'changed')
        OR execution_status <> 'changed'
    )
);

CREATE INDEX idx_results_run_status
    ON task_execution_results(run_id, execution_status);

CREATE INDEX idx_results_host
    ON task_execution_results(host_id, run_id);

-- ------------------------------------------------------------
-- 8. Host execution state
-- ------------------------------------------------------------

CREATE TABLE managed_packages (
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id)
        ON DELETE CASCADE,
    package_name VARCHAR(150) NOT NULL,
    installed BOOLEAN NOT NULL DEFAULT TRUE,
    version VARCHAR(80),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY(host_id, package_name)
);

CREATE TABLE managed_services (
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id)
        ON DELETE CASCADE,
    service_name VARCHAR(150) NOT NULL,
    desired_state module_state NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY(host_id, service_name),

    CHECK (
        desired_state IN ('started', 'stopped')
    )
);

CREATE TABLE managed_files (
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    permission_mode VARCHAR(4) NOT NULL DEFAULT '0644',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY(host_id, file_path),

    CHECK (file_path LIKE '/%'),
    CHECK (file_path NOT LIKE '%/../%'),
    CHECK (file_type IN ('file', 'directory')),
    CHECK (permission_mode ~ '^[0-7]{3,4}$')
);

-- ------------------------------------------------------------
-- 9. Execution trigger
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_task_result()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_run BIGINT;
    actual_playbook BIGINT;
BEGIN
    SELECT r.playbook_id
    INTO actual_playbook
    FROM playbook_runs r
    WHERE r.run_id = NEW.run_id;

    SELECT t.playbook_id
    INTO actual_run
    FROM playbook_tasks t
    WHERE t.task_id = NEW.task_id;

    IF actual_playbook IS NULL OR actual_run IS NULL THEN
        RAISE EXCEPTION 'Invalid run or task reference';
    END IF;

    IF actual_playbook <> actual_run THEN
        RAISE EXCEPTION
            'Task does not belong to the selected playbook';
    END IF;

    IF NEW.execution_status = 'changed' THEN
        NEW.changed := TRUE;
    ELSE
        NEW.changed := FALSE;
    END IF;

    IF NEW.execution_status IN (
        'ok', 'changed', 'failed', 'skipped'
    ) AND NEW.completed_at IS NULL THEN
        NEW.completed_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_task_result
BEFORE INSERT OR UPDATE
ON task_execution_results
FOR EACH ROW
EXECUTE FUNCTION validate_task_result();

-- ------------------------------------------------------------
-- 10. Inventory resolution view
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW v_inventory_overview AS
SELECT
    h.host_id,
    h.repository_id,
    h.hostname,
    h.ansible_host,
    h.ansible_port,
    h.ansible_user,
    h.host_status,
    COALESCE(
        jsonb_agg(
            DISTINCT g.group_name
        ) FILTER (WHERE g.group_id IS NOT NULL),
        '[]'::JSONB
    ) AS groups,
    h.variables AS host_variables
FROM inventory_hosts h
LEFT JOIN host_group_memberships m
    ON m.host_id = h.host_id
LEFT JOIN inventory_groups g
    ON g.group_id = m.group_id
GROUP BY h.host_id;

-- ------------------------------------------------------------
-- 11. Effective variable resolution
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION effective_host_variables(
    p_host_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB := '{}'::JSONB;
    group_vars JSONB;
    host_vars JSONB;
BEGIN
    SELECT COALESCE(
        jsonb_object_agg(
            variable.key,
            variable.value
        ),
        '{}'::JSONB
    )
    INTO group_vars
    FROM host_group_memberships membership
    JOIN inventory_groups groups
        ON groups.group_id = membership.group_id
    CROSS JOIN LATERAL jsonb_each(
        groups.variables
    ) AS variable
    WHERE membership.host_id = p_host_id;

    SELECT variables
    INTO host_vars
    FROM inventory_hosts
    WHERE host_id = p_host_id;

    IF host_vars IS NULL THEN
        RAISE EXCEPTION 'Unknown host: %', p_host_id;
    END IF;

    result := COALESCE(group_vars, '{}'::JSONB)
        || host_vars;

    RETURN result;
END;
$$;

-- ------------------------------------------------------------
-- 12. Merge-independent execution eligibility
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION playbook_execution_eligibility(
    p_playbook_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    target_pattern TEXT;
    repository BIGINT;
    matching_hosts BIGINT;
    task_count BIGINT;
BEGIN
    SELECT repository_id, target_pattern
    INTO repository, target_pattern
    FROM playbooks
    WHERE playbook_id = p_playbook_id
      AND is_enabled = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Playbook does not exist or is disabled';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO task_count
    FROM playbook_tasks
    WHERE playbook_id = p_playbook_id;

    IF task_count = 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Playbook has no tasks';
        RETURN;
    END IF;

    IF target_pattern = 'all' THEN
        SELECT COUNT(*)
        INTO matching_hosts
        FROM inventory_hosts
        WHERE repository_id = repository
          AND host_status = 'active';
    ELSE
        SELECT COUNT(DISTINCT h.host_id)
        INTO matching_hosts
        FROM inventory_hosts h
        LEFT JOIN host_group_memberships m
            ON m.host_id = h.host_id
        LEFT JOIN inventory_groups g
            ON g.group_id = m.group_id
        WHERE h.repository_id = repository
          AND h.host_status = 'active'
          AND (
              h.hostname = target_pattern
              OR g.group_name = target_pattern
          );
    END IF;

    IF matching_hosts = 0 THEN
        RETURN QUERY
        SELECT FALSE, 'No active inventory hosts match target';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'Playbook configuration is eligible';
END;
$$;

-- ------------------------------------------------------------
-- 13. Start an execution transaction
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION start_playbook_run(
    p_playbook_id BIGINT,
    p_user VARCHAR(120),
    p_check_mode BOOLEAN DEFAULT FALSE
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    new_run_id BIGINT;
    eligibility RECORD;
BEGIN
    SELECT *
    INTO eligibility
    FROM playbook_execution_eligibility(p_playbook_id);

    IF NOT eligibility.eligible THEN
        RAISE EXCEPTION
            'Execution rejected: %',
            eligibility.reason;
    END IF;

    INSERT INTO playbook_runs (
        playbook_id,
        initiated_by,
        execution_status,
        check_mode,
        started_at
    )
    VALUES (
        p_playbook_id,
        p_user,
        CASE
            WHEN p_check_mode THEN 'check_mode'::run_status
            ELSE 'running'::run_status
        END,
        p_check_mode,
        NOW()
    )
    RETURNING run_id INTO new_run_id;

    RETURN new_run_id;
END;
$$;

-- ------------------------------------------------------------
-- 14. Execution report view
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW v_playbook_execution_report AS
SELECT
    r.run_id,
    p.playbook_name,
    r.initiated_by,
    r.execution_status AS run_status,
    r.check_mode,
    COUNT(e.result_id) AS total_tasks,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'ok'
    ) AS successful_tasks,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'changed'
    ) AS changed_tasks,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'failed'
    ) AS failed_tasks,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'skipped'
    ) AS skipped_tasks,
    r.started_at,
    r.completed_at
FROM playbook_runs r
JOIN playbooks p
    ON p.playbook_id = r.playbook_id
LEFT JOIN task_execution_results e
    ON e.run_id = r.run_id
GROUP BY
    r.run_id,
    p.playbook_name,
    r.initiated_by,
    r.execution_status,
    r.check_mode,
    r.started_at,
    r.completed_at;

-- ------------------------------------------------------------
-- 15. Sample repository and inventory
-- ------------------------------------------------------------

INSERT INTO repositories (
    repository_name,
    description
)
VALUES (
    'production-infrastructure',
    'Production web and database infrastructure'
);

INSERT INTO inventory_groups (
    repository_id,
    group_name,
    description,
    variables
)
SELECT
    repository_id,
    'web',
    'Production web servers',
    '{"package_name":"nginx","environment":"production"}'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO inventory_groups (
    repository_id,
    group_name,
    description,
    variables
)
SELECT
    repository_id,
    'database',
    'Production database servers',
    '{"package_name":"postgresql","environment":"production"}'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO inventory_hosts (
    repository_id,
    hostname,
    ansible_host,
    ansible_user,
    variables
)
SELECT
    repository_id,
    'web01',
    '192.168.10.11',
    'ansible',
    '{"environment":"production"}'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO inventory_hosts (
    repository_id,
    hostname,
    ansible_host,
    ansible_user
)
SELECT
    repository_id,
    'web02',
    '192.168.10.12',
    'ansible'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO inventory_hosts (
    repository_id,
    hostname,
    ansible_host,
    ansible_user
)
SELECT
    repository_id,
    'db01',
    '192.168.10.21',
    'ansible'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO inventory_hosts (
    repository_id,
    hostname,
    ansible_host,
    host_status
)
SELECT
    repository_id,
    'web03',
    '192.168.10.13',
    'unreachable'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO host_group_memberships (
    host_id,
    group_id
)
SELECT h.host_id, g.group_id
FROM inventory_hosts h
JOIN inventory_groups g
    ON g.repository_id = h.repository_id
WHERE
    (h.hostname IN ('web01', 'web02', 'web03')
        AND g.group_name = 'web')
    OR
    (h.hostname = 'db01'
        AND g.group_name = 'database');

-- ------------------------------------------------------------
-- 16. Sample playbooks
-- ------------------------------------------------------------

INSERT INTO playbooks (
    repository_id,
    playbook_name,
    description,
    target_pattern,
    variables
)
SELECT
    repository_id,
    'configure-web',
    'Install and configure production web services',
    'web',
    '{"service_enabled":true}'
FROM repositories
WHERE repository_name = 'production-infrastructure';

INSERT INTO playbooks (
    repository_id,
    playbook_name,
    description,
    target_pattern
)
SELECT
    repository_id,
    'configure-database',
    'Install and configure PostgreSQL services',
    'database'
FROM repositories
WHERE repository_name = 'production-infrastructure';

-- Web playbook tasks

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments,
    notify_handler
)
SELECT
    p.playbook_id,
    m.module_id,
    'Install nginx',
    1,
    '{"name":"{{ package_name }}","state":"present"}',
    NULL
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'package'
WHERE p.playbook_name = 'configure-web';

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments
)
SELECT
    p.playbook_id,
    m.module_id,
    'Create application directory',
    2,
    '{"path":"/srv/application","state":"directory","mode":"0755"}'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'file'
WHERE p.playbook_name = 'configure-web';

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments,
    notify_handler
)
SELECT
    p.playbook_id,
    m.module_id,
    'Start nginx',
    3,
    '{"name":"nginx","state":"started","enabled":true}',
    'reload_nginx'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'service'
WHERE p.playbook_name = 'configure-web';

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments
)
SELECT
    p.playbook_id,
    m.module_id,
    'Validate HTTP configuration',
    4,
    '{"command":"check_http"}'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'command'
WHERE p.playbook_name = 'configure-web';

-- Database playbook tasks

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments
)
SELECT
    p.playbook_id,
    m.module_id,
    'Install PostgreSQL',
    1,
    '{"name":"{{ package_name }}","state":"present"}'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'package'
WHERE p.playbook_name = 'configure-database';

INSERT INTO playbook_tasks (
    playbook_id,
    module_id,
    task_name,
    task_order,
    arguments
)
SELECT
    p.playbook_id,
    m.module_id,
    'Start PostgreSQL',
    2,
    '{"name":"postgresql","state":"started","enabled":true}'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'service'
WHERE p.playbook_name = 'configure-database';

-- Handler definition

INSERT INTO playbook_handlers (
    playbook_id,
    module_id,
    handler_name,
    arguments
)
SELECT
    p.playbook_id,
    m.module_id,
    'reload_nginx',
    '{"name":"nginx","state":"started","enabled":true}'
FROM playbooks p
JOIN configuration_modules m
    ON m.module_name = 'service'
WHERE p.playbook_name = 'configure-web';

-- ------------------------------------------------------------
-- 17. Sample execution records
-- ------------------------------------------------------------

INSERT INTO playbook_runs (
    playbook_id,
    initiated_by,
    execution_status,
    check_mode,
    started_at,
    completed_at
)
SELECT
    playbook_id,
    'automation-admin',
    'successful',
    FALSE,
    NOW() - INTERVAL '10 minutes',
    NOW()
FROM playbooks
WHERE playbook_name = 'configure-web';

-- Record successful and changed tasks.

INSERT INTO task_execution_results (
    run_id,
    task_id,
    host_id,
    execution_status,
    execution_message,
    started_at
)
SELECT
    r.run_id,
    t.task_id,
    h.host_id,
    CASE
        WHEN t.task_name = 'Install nginx'
            THEN 'changed'::task_status
        WHEN t.task_name = 'Create application directory'
            THEN 'changed'::task_status
        WHEN t.task_name = 'Start nginx'
            THEN 'changed'::task_status
        ELSE 'ok'::task_status
    END,
    'Sample execution completed',
    NOW() - INTERVAL '9 minutes'
FROM playbook_runs r
JOIN playbooks p
    ON p.playbook_id = r.playbook_id
JOIN playbook_tasks t
    ON t.playbook_id = p.playbook_id
JOIN inventory_hosts h
    ON h.repository_id = p.repository_id
WHERE
    p.playbook_name = 'configure-web'
    AND h.hostname IN ('web01', 'web02');

-- ------------------------------------------------------------
-- 18. Inventory retrieval
-- ------------------------------------------------------------

SELECT *
FROM v_inventory_overview
ORDER BY hostname;

-- ------------------------------------------------------------
-- 19. Variable precedence evaluation
-- ------------------------------------------------------------

SELECT
    h.hostname,
    effective_host_variables(h.host_id)
        AS effective_variables
FROM inventory_hosts h
ORDER BY h.hostname;

-- ------------------------------------------------------------
-- 20. Playbook eligibility evaluation
-- ------------------------------------------------------------

SELECT
    p.playbook_name,
    e.eligible,
    e.reason
FROM playbooks p
CROSS JOIN LATERAL
    playbook_execution_eligibility(p.playbook_id) e
ORDER BY p.playbook_name;

-- ------------------------------------------------------------
-- 21. Module and task retrieval
-- ------------------------------------------------------------

SELECT
    p.playbook_name,
    t.task_order,
    t.task_name,
    m.module_name,
    t.arguments,
    t.notify_handler
FROM playbooks p
JOIN playbook_tasks t
    ON t.playbook_id = p.playbook_id
JOIN configuration_modules m
    ON m.module_id = t.module_id
ORDER BY p.playbook_name, t.task_order;

-- ------------------------------------------------------------
-- 22. Start a check-mode execution
-- ------------------------------------------------------------

DO $$
DECLARE
    selected_playbook BIGINT;
    new_run BIGINT;
BEGIN
    SELECT playbook_id
    INTO selected_playbook
    FROM playbooks
    WHERE playbook_name = 'configure-database';

    new_run := start_playbook_run(
        selected_playbook,
        'automation-admin',
        TRUE
    );

    RAISE NOTICE 'Created check-mode run: %', new_run;
END;
$$;

-- ------------------------------------------------------------
-- 23. Demonstrate result validation and failure recording
-- ------------------------------------------------------------

DO $$
DECLARE
    selected_run BIGINT;
    selected_task BIGINT;
    selected_host BIGINT;
BEGIN
    SELECT r.run_id
    INTO selected_run
    FROM playbook_runs r
    JOIN playbooks p
        ON p.playbook_id = r.playbook_id
    WHERE p.playbook_name = 'configure-web'
    ORDER BY r.run_id
    LIMIT 1;

    SELECT task_id
    INTO selected_task
    FROM playbook_tasks
    WHERE task_name = 'Validate HTTP configuration'
      AND playbook_id = (
          SELECT playbook_id
          FROM playbooks
          WHERE playbook_name = 'configure-web'
      );

    SELECT host_id
    INTO selected_host
    FROM inventory_hosts
    WHERE hostname = 'web01';

    INSERT INTO task_execution_results (
        run_id,
        task_id,
        host_id,
        execution_status,
        execution_message,
        started_at
    )
    VALUES (
        selected_run,
        selected_task,
        selected_host,
        'ok',
        'HTTP configuration verified',
        NOW()
    )
    ON CONFLICT (run_id, task_id, host_id)
    DO UPDATE SET
        execution_status = EXCLUDED.execution_status,
        execution_message = EXCLUDED.execution_message,
        started_at = EXCLUDED.started_at;
END;
$$;

-- ------------------------------------------------------------
-- 24. Execution aggregation
-- ------------------------------------------------------------

SELECT
    h.hostname,
    COUNT(*) AS total_tasks,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'ok'
    ) AS successful,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'changed'
    ) AS changed,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'failed'
    ) AS failed,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'skipped'
    ) AS skipped
FROM task_execution_results e
JOIN inventory_hosts h
    ON h.host_id = e.host_id
GROUP BY h.hostname
ORDER BY h.hostname;

-- ------------------------------------------------------------
-- 25. CTE-based infrastructure compliance report
-- ------------------------------------------------------------

WITH host_packages AS (
    SELECT
        host_id,
        COUNT(*) FILTER (
            WHERE installed
        ) AS installed_packages
    FROM managed_packages
    GROUP BY host_id
),
host_services AS (
    SELECT
        host_id,
        COUNT(*) FILTER (
            WHERE desired_state = 'started'
        ) AS started_services
    FROM managed_services
    GROUP BY host_id
)
SELECT
    h.hostname,
    COALESCE(p.installed_packages, 0)
        AS installed_packages,
    COALESCE(s.started_services, 0)
        AS started_services,
    h.host_status
FROM inventory_hosts h
LEFT JOIN host_packages p
    ON p.host_id = h.host_id
LEFT JOIN host_services s
    ON s.host_id = h.host_id
ORDER BY h.hostname;

-- ------------------------------------------------------------
-- 26. Handler notification retrieval
-- ------------------------------------------------------------

SELECT
    p.playbook_name,
    t.task_name,
    t.notify_handler,
    h.handler_name,
    h.arguments AS handler_arguments
FROM playbook_tasks t
JOIN playbooks p
    ON p.playbook_id = t.playbook_id
LEFT JOIN playbook_handlers h
    ON h.playbook_id = p.playbook_id
   AND h.handler_name = t.notify_handler
WHERE t.notify_handler IS NOT NULL;

-- ------------------------------------------------------------
-- 27. Execution history
-- ------------------------------------------------------------

SELECT *
FROM v_playbook_execution_report
ORDER BY run_id DESC;

COMMIT;

-- ============================================================
-- ANSIBLE ROLES: REUSABLE CONFIGURATION-MANAGEMENT ARCHITECTURE
-- PostgreSQL 14+
--
-- Models:
-- Repositories of configuration roles
-- Role versions and dependencies
-- Inventory hosts and groups
-- Variables and precedence
-- Tasks, handlers and notifications
-- Playbooks and role assignments
-- Execution runs and task results
-- Configuration state
-- Idempotence
-- Check mode
-- Execution reporting
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ansible_lab;

SET search_path TO ansible_lab, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE task_status AS ENUM (
    'pending',
    'ok',
    'changed',
    'failed',
    'skipped'
);

CREATE TYPE execution_mode AS ENUM (
    'normal',
    'check'
);

CREATE TYPE execution_status AS ENUM (
    'running',
    'completed',
    'failed',
    'cancelled'
);

CREATE TYPE variable_scope AS ENUM (
    'role_default',
    'inventory',
    'role_variable',
    'play',
    'extra'
);

CREATE TYPE handler_status AS ENUM (
    'pending',
    'executed',
    'failed',
    'skipped'
);

-- ------------------------------------------------------------
-- ROLE CATALOG
-- ------------------------------------------------------------

CREATE TABLE roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL,
    version VARCHAR(30) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    author VARCHAR(150),
    minimum_ansible_version VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_role_version
        UNIQUE (role_name, version),

    CONSTRAINT chk_role_name
        CHECK (
            role_name ~ '^[a-zA-Z0-9_-]+$'
        )
);

CREATE INDEX idx_roles_active
    ON roles(role_name)
    WHERE is_active = TRUE;

-- ------------------------------------------------------------
-- ROLE DEPENDENCIES
-- ------------------------------------------------------------

CREATE TABLE role_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE CASCADE,

    depends_on_role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE RESTRICT,

    dependency_position INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT uq_role_dependency
        UNIQUE (role_id, depends_on_role_id),

    CONSTRAINT chk_no_direct_self_dependency
        CHECK (role_id <> depends_on_role_id),

    CONSTRAINT chk_dependency_position
        CHECK (dependency_position > 0)
);

CREATE INDEX idx_dependencies_role
    ON role_dependencies(role_id, dependency_position);

-- ------------------------------------------------------------
-- INVENTORY AND GROUPS
-- ------------------------------------------------------------

CREATE TABLE inventory_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE inventory_hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hostname VARCHAR(150) NOT NULL UNIQUE,
    management_address INET,
    environment VARCHAR(50) NOT NULL,
    operating_system VARCHAR(100),
    ansible_connection VARCHAR(50) NOT NULL DEFAULT 'ssh',
    become_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_connection_type
        CHECK (
            ansible_connection IN (
                'ssh',
                'local',
                'winrm'
            )
        )
);

CREATE INDEX idx_inventory_environment
    ON inventory_hosts(environment, is_active);

CREATE TABLE host_group_memberships (
    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id) ON DELETE CASCADE,

    group_id BIGINT NOT NULL
        REFERENCES inventory_groups(group_id) ON DELETE CASCADE,

    PRIMARY KEY (host_id, group_id)
);

-- ------------------------------------------------------------
-- VARIABLES
--
-- The scope and priority support a simplified precedence model.
-- Encrypted secrets should be stored in a dedicated secret
-- manager, not as plaintext database values.
-- ------------------------------------------------------------

CREATE TABLE configuration_variables (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    variable_name VARCHAR(150) NOT NULL,
    variable_value JSONB NOT NULL,

    scope variable_scope NOT NULL,

    role_id BIGINT REFERENCES roles(role_id)
        ON DELETE CASCADE,

    host_id BIGINT REFERENCES inventory_hosts(host_id)
        ON DELETE CASCADE,

    group_id BIGINT REFERENCES inventory_groups(group_id)
        ON DELETE CASCADE,

    playbook_id BIGINT,

    priority INTEGER NOT NULL DEFAULT 0,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_variable_name
        CHECK (
            variable_name ~ '^[a-zA-Z_][a-zA-Z0-9_]*$'
        ),

    CONSTRAINT chk_variable_scope_reference
        CHECK (
            (scope IN ('role_default', 'role_variable')
                AND role_id IS NOT NULL
                AND host_id IS NULL
                AND group_id IS NULL)
            OR
            (scope = 'inventory'
                AND (
                    host_id IS NOT NULL
                    OR group_id IS NOT NULL
                )
                AND role_id IS NULL)
            OR
            (scope IN ('play', 'extra')
                AND playbook_id IS NOT NULL
                AND role_id IS NULL
                AND host_id IS NULL
                AND group_id IS NULL)
        )
);

CREATE INDEX idx_variables_role
    ON configuration_variables(role_id, variable_name);

CREATE INDEX idx_variables_host
    ON configuration_variables(host_id, variable_name);

CREATE INDEX idx_variables_group
    ON configuration_variables(group_id, variable_name);

-- ------------------------------------------------------------
-- PLAYBOOKS
-- ------------------------------------------------------------

CREATE TABLE playbooks (
    playbook_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    playbook_name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    execution_strategy VARCHAR(30) NOT NULL DEFAULT 'linear',
    serial_limit INTEGER,
    max_fail_percentage NUMERIC(5,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_execution_strategy
        CHECK (
            execution_strategy IN (
                'linear',
                'free'
            )
        ),

    CONSTRAINT chk_serial_limit
        CHECK (serial_limit IS NULL OR serial_limit > 0),

    CONSTRAINT chk_failure_percentage
        CHECK (
            max_fail_percentage BETWEEN 0 AND 100
        )
);

ALTER TABLE configuration_variables
    ADD CONSTRAINT fk_variables_playbook
    FOREIGN KEY (playbook_id)
    REFERENCES playbooks(playbook_id)
    ON DELETE CASCADE;

-- ------------------------------------------------------------
-- PLAYBOOK ROLE ASSIGNMENTS
-- ------------------------------------------------------------

CREATE TABLE playbook_roles (
    assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id) ON DELETE CASCADE,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE RESTRICT,

    execution_position INTEGER NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

    CONSTRAINT uq_playbook_role_position
        UNIQUE (playbook_id, execution_position),

    CONSTRAINT chk_execution_position
        CHECK (execution_position > 0)
);

CREATE INDEX idx_playbook_roles_execution
    ON playbook_roles(playbook_id, execution_position)
    WHERE enabled = TRUE;

-- ------------------------------------------------------------
-- ROLE TASKS
-- ------------------------------------------------------------

CREATE TABLE role_tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE CASCADE,

    task_name VARCHAR(200) NOT NULL,
    module_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,

    arguments JSONB NOT NULL DEFAULT '{}'::JSONB,

    execution_position INTEGER NOT NULL,

    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

    condition_expression TEXT,

    become_required BOOLEAN NOT NULL DEFAULT FALSE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_role_task_position
        UNIQUE (role_id, execution_position),

    CONSTRAINT chk_task_position
        CHECK (execution_position > 0),

    CONSTRAINT chk_task_name
        CHECK (LENGTH(TRIM(task_name)) > 0)
);

CREATE INDEX idx_role_tasks_order
    ON role_tasks(role_id, execution_position)
    WHERE is_active = TRUE;

CREATE INDEX idx_role_tasks_tags
    ON role_tasks USING GIN(tags);

CREATE INDEX idx_role_tasks_arguments
    ON role_tasks USING GIN(arguments);

-- ------------------------------------------------------------
-- ROLE HANDLERS
-- ------------------------------------------------------------

CREATE TABLE role_handlers (
    handler_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE CASCADE,

    handler_name VARCHAR(200) NOT NULL,

    module_name VARCHAR(100) NOT NULL,

    arguments JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT uq_role_handler
        UNIQUE (role_id, handler_name)
);

CREATE TABLE task_notifications (
    task_id BIGINT NOT NULL
        REFERENCES role_tasks(task_id) ON DELETE CASCADE,

    handler_id BIGINT NOT NULL
        REFERENCES role_handlers(handler_id) ON DELETE CASCADE,

    PRIMARY KEY (task_id, handler_id)
);

-- ------------------------------------------------------------
-- EXECUTION RUNS
-- ------------------------------------------------------------

CREATE TABLE execution_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id) ON DELETE RESTRICT,

    mode execution_mode NOT NULL DEFAULT 'normal',

    status execution_status NOT NULL DEFAULT 'running',

    requested_by VARCHAR(150) NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    execution_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT chk_execution_timestamps
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE INDEX idx_execution_runs_status
    ON execution_runs(status, started_at DESC);

CREATE TABLE execution_run_hosts (
    run_id BIGINT NOT NULL
        REFERENCES execution_runs(run_id) ON DELETE CASCADE,

    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id) ON DELETE RESTRICT,

    status execution_status NOT NULL DEFAULT 'running',

    PRIMARY KEY (run_id, host_id)
);

-- ------------------------------------------------------------
-- TASK EXECUTION RESULTS
-- ------------------------------------------------------------

CREATE TABLE task_execution_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL,

    host_id BIGINT NOT NULL,

    task_id BIGINT NOT NULL
        REFERENCES role_tasks(task_id) ON DELETE RESTRICT,

    status task_status NOT NULL,

    changed BOOLEAN NOT NULL DEFAULT FALSE,

    message TEXT NOT NULL DEFAULT '',

    execution_duration_ms INTEGER,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_result_run_host
        FOREIGN KEY (run_id, host_id)
        REFERENCES execution_run_hosts(run_id, host_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_result_duration
        CHECK (
            execution_duration_ms IS NULL
            OR execution_duration_ms >= 0
        ),

    CONSTRAINT chk_result_status_change
        CHECK (
            (status = 'changed' AND changed = TRUE)
            OR
            (status <> 'changed' AND changed = FALSE)
        ),

    CONSTRAINT chk_result_timestamps
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE INDEX idx_results_run_status
    ON task_execution_results(run_id, status);

CREATE INDEX idx_results_host
    ON task_execution_results(host_id, started_at DESC);

CREATE INDEX idx_results_task
    ON task_execution_results(task_id, run_id);

-- ------------------------------------------------------------
-- HANDLER EXECUTION QUEUE
-- ------------------------------------------------------------

CREATE TABLE handler_execution_queue (
    queue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL,
    host_id BIGINT NOT NULL,

    handler_id BIGINT NOT NULL
        REFERENCES role_handlers(handler_id) ON DELETE RESTRICT,

    status handler_status NOT NULL DEFAULT 'pending',

    notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    executed_at TIMESTAMPTZ,

    message TEXT,

    CONSTRAINT fk_handler_run_host
        FOREIGN KEY (run_id, host_id)
        REFERENCES execution_run_hosts(run_id, host_id)
        ON DELETE CASCADE
);

-- Avoid duplicate pending notifications for the same handler
-- on the same host during one execution run.
CREATE UNIQUE INDEX uq_pending_handler_notification
    ON handler_execution_queue(run_id, host_id, handler_id)
    WHERE status = 'pending';

CREATE INDEX idx_handler_queue_pending
    ON handler_execution_queue(run_id, notified_at)
    WHERE status = 'pending';

-- ------------------------------------------------------------
-- CONFIGURATION STATE
--
-- Stores the last successfully applied desired resource state.
-- This is an application-level state model, not a replacement
-- for the actual remote host filesystem or service manager.
-- ------------------------------------------------------------

CREATE TABLE managed_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    host_id BIGINT NOT NULL
        REFERENCES inventory_hosts(host_id) ON DELETE CASCADE,

    resource_type VARCHAR(50) NOT NULL,

    resource_identifier VARCHAR(255) NOT NULL,

    desired_state JSONB NOT NULL,

    last_applied_run_id BIGINT
        REFERENCES execution_runs(run_id) ON DELETE SET NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_host_managed_resource
        UNIQUE (
            host_id,
            resource_type,
            resource_identifier
        )
);

CREATE INDEX idx_managed_resources_type
    ON managed_resources(resource_type, host_id);

-- ------------------------------------------------------------
-- TRIGGER: VALIDATE TASK NOTIFICATION ROLE OWNERSHIP
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_task_handler_role()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    task_role BIGINT;
    handler_role BIGINT;
BEGIN
    SELECT role_id
    INTO task_role
    FROM role_tasks
    WHERE task_id = NEW.task_id;

    SELECT role_id
    INTO handler_role
    FROM role_handlers
    WHERE handler_id = NEW.handler_id;

    IF task_role IS NULL OR handler_role IS NULL THEN
        RAISE EXCEPTION
            'Task or handler does not exist.';
    END IF;

    IF task_role <> handler_role THEN
        RAISE EXCEPTION
            'Task and handler must belong to the same role.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_task_handler
BEFORE INSERT OR UPDATE ON task_notifications
FOR EACH ROW
EXECUTE FUNCTION validate_task_handler_role();

-- ------------------------------------------------------------
-- FUNCTION: DETECT TRANSITIVE ROLE DEPENDENCY CYCLES
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_role_dependency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    cycle_found BOOLEAN;
BEGIN
    IF NEW.role_id = NEW.depends_on_role_id THEN
        RAISE EXCEPTION
            'A role cannot depend on itself.';
    END IF;

    WITH RECURSIVE dependency_path(role_id) AS (
        SELECT NEW.depends_on_role_id

        UNION

        SELECT rd.depends_on_role_id
        FROM role_dependencies rd
        JOIN dependency_path dp
            ON rd.role_id = dp.role_id
    )
    SELECT EXISTS (
        SELECT 1
        FROM dependency_path
        WHERE role_id = NEW.role_id
    )
    INTO cycle_found;

    IF cycle_found THEN
        RAISE EXCEPTION
            'Circular role dependency detected.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_role_dependency
BEFORE INSERT OR UPDATE ON role_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_role_dependency();

-- ------------------------------------------------------------
-- FUNCTION: SIMPLIFIED VARIABLE RESOLUTION
--
-- Higher priority wins.
-- Ties are resolved by variable_id for deterministic results.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION resolve_host_variable(
    p_host_id BIGINT,
    p_role_id BIGINT,
    p_playbook_id BIGINT,
    p_variable_name VARCHAR
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    resolved_value JSONB;
BEGIN
    SELECT variable_value
    INTO resolved_value
    FROM configuration_variables
    WHERE variable_name = p_variable_name
      AND (
          (
              scope = 'role_default'
              AND role_id = p_role_id
          )
          OR
          (
              scope = 'inventory'
              AND host_id = p_host_id
          )
          OR
          (
              scope = 'role_variable'
              AND role_id = p_role_id
          )
          OR
          (
              scope IN ('play', 'extra')
              AND playbook_id = p_playbook_id
          )
      )
    ORDER BY priority DESC, variable_id DESC
    LIMIT 1;

    RETURN resolved_value;
END;
$$;

-- ------------------------------------------------------------
-- FUNCTION: DETERMINE WHETHER A TASK WOULD CHANGE STATE
--
-- This function compares the desired state with the database
-- representation of the last applied state.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_resource_change(
    p_host_id BIGINT,
    p_resource_type VARCHAR,
    p_identifier VARCHAR,
    p_desired_state JSONB
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    current_state JSONB;
BEGIN
    SELECT desired_state
    INTO current_state
    FROM managed_resources
    WHERE host_id = p_host_id
      AND resource_type = p_resource_type
      AND resource_identifier = p_identifier;

    IF NOT FOUND THEN
        RETURN TRUE;
    END IF;

    RETURN current_state IS DISTINCT FROM p_desired_state;
END;
$$;

-- ------------------------------------------------------------
-- PROCEDURE: APPLY A RESOURCE STATE
--
-- Check mode reports the required change without mutation.
-- Normal mode updates the desired-state ledger atomically.
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE apply_resource_state(
    p_run_id BIGINT,
    p_host_id BIGINT,
    p_resource_type VARCHAR,
    p_identifier VARCHAR,
    p_desired_state JSONB
)
LANGUAGE plpgsql
AS $$
DECLARE
    run_mode execution_mode;
    current_run_status execution_status;
BEGIN
    SELECT mode, status
    INTO run_mode, current_run_status
    FROM execution_runs
    WHERE run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Execution run % does not exist.', p_run_id;
    END IF;

    IF current_run_status <> 'running' THEN
        RAISE EXCEPTION
            'Cannot modify a completed execution run.';
    END IF;

    PERFORM 1
    FROM execution_run_hosts
    WHERE run_id = p_run_id
      AND host_id = p_host_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Host is not assigned to this execution run.';
    END IF;

    IF run_mode = 'check' THEN
        RAISE NOTICE
            'Check mode: resource % inspected without mutation.',
            p_identifier;

        RETURN;
    END IF;

    INSERT INTO managed_resources (
        host_id,
        resource_type,
        resource_identifier,
        desired_state,
        last_applied_run_id
    )
    VALUES (
        p_host_id,
        p_resource_type,
        p_identifier,
        p_desired_state,
        p_run_id
    )
    ON CONFLICT (
        host_id,
        resource_type,
        resource_identifier
    )
    DO UPDATE SET
        desired_state = EXCLUDED.desired_state,
        last_applied_run_id = EXCLUDED.last_applied_run_id,
        updated_at = NOW()
    WHERE managed_resources.desired_state
        IS DISTINCT FROM EXCLUDED.desired_state;
END;
$$;

-- ------------------------------------------------------------
-- VIEW: ROLE DEPENDENCY REPORT
-- ------------------------------------------------------------

CREATE VIEW role_dependency_report AS
SELECT
    r.role_name,
    r.version,
    COALESCE(
        STRING_AGG(
            dependency.role_name,
            ', ' ORDER BY rd.dependency_position
        ),
        ''
    ) AS dependencies
FROM roles r
LEFT JOIN role_dependencies rd
    ON rd.role_id = r.role_id
LEFT JOIN roles dependency
    ON dependency.role_id = rd.depends_on_role_id
GROUP BY r.role_id, r.role_name, r.version;

-- ------------------------------------------------------------
-- VIEW: EXECUTION REPORT
-- ------------------------------------------------------------

CREATE VIEW execution_report AS
SELECT
    er.run_id,
    p.playbook_name,
    er.mode,
    er.status,
    er.requested_by,
    er.started_at,
    er.completed_at,

    COUNT(tr.result_id) AS total_tasks,

    COUNT(*) FILTER (
        WHERE tr.status = 'changed'
    ) AS changed_tasks,

    COUNT(*) FILTER (
        WHERE tr.status = 'ok'
    ) AS successful_unchanged_tasks,

    COUNT(*) FILTER (
        WHERE tr.status = 'failed'
    ) AS failed_tasks,

    COUNT(*) FILTER (
        WHERE tr.status = 'skipped'
    ) AS skipped_tasks

FROM execution_runs er
JOIN playbooks p
    ON p.playbook_id = er.playbook_id
LEFT JOIN task_execution_results tr
    ON tr.run_id = er.run_id
GROUP BY
    er.run_id,
    p.playbook_name,
    er.mode,
    er.status,
    er.requested_by,
    er.started_at,
    er.completed_at;

-- ------------------------------------------------------------
-- SAMPLE DATA
-- ------------------------------------------------------------

INSERT INTO roles (
    role_name,
    version,
    description,
    author,
    minimum_ansible_version
)
VALUES
(
    'base',
    '1.0.0',
    'Common operating-system configuration',
    'Infrastructure Engineering',
    '2.14'
),
(
    'webserver',
    '2.0.0',
    'Reusable nginx configuration',
    'Infrastructure Engineering',
    '2.14'
),
(
    'monitoring',
    '1.0.0',
    'Monitoring agent configuration',
    'Infrastructure Engineering',
    '2.14'
);

INSERT INTO role_dependencies (
    role_id,
    depends_on_role_id,
    dependency_position
)
SELECT
    web.role_id,
    base.role_id,
    1
FROM roles web
CROSS JOIN roles base
WHERE web.role_name = 'webserver'
  AND base.role_name = 'base';

INSERT INTO inventory_groups (
    group_name,
    description
)
VALUES
('web_servers', 'Application web servers'),
('monitoring_servers', 'Monitoring-enabled servers'),
('production', 'Production environment');

INSERT INTO inventory_hosts (
    hostname,
    management_address,
    environment,
    operating_system,
    become_allowed
)
VALUES
(
    'web-01',
    '192.168.10.11',
    'production',
    'Ubuntu 24.04',
    TRUE
),
(
    'web-02',
    '192.168.10.12',
    'staging',
    'Ubuntu 24.04',
    TRUE
),
(
    'monitor-01',
    '192.168.10.20',
    'production',
    'Debian 12',
    TRUE
);

INSERT INTO host_group_memberships (
    host_id,
    group_id
)
SELECT h.host_id, g.group_id
FROM inventory_hosts h
CROSS JOIN inventory_groups g
WHERE
    (h.hostname IN ('web-01', 'web-02')
        AND g.group_name = 'web_servers')
    OR
    (h.hostname = 'monitor-01'
        AND g.group_name = 'monitoring_servers')
    OR
    (h.hostname IN ('web-01', 'monitor-01')
        AND g.group_name = 'production');

INSERT INTO playbooks (
    playbook_name,
    description,
    execution_strategy,
    serial_limit,
    max_fail_percentage
)
VALUES
(
    'configure_web_infrastructure',
    'Deploy and configure reusable web infrastructure roles',
    'linear',
    2,
    20
);

INSERT INTO playbook_roles (
    playbook_id,
    role_id,
    execution_position,
    tags
)
SELECT
    p.playbook_id,
    r.role_id,
    CASE r.role_name
        WHEN 'base' THEN 1
        WHEN 'webserver' THEN 2
        WHEN 'monitoring' THEN 3
    END,
    CASE r.role_name
        WHEN 'base' THEN ARRAY['base', 'packages']
        WHEN 'webserver' THEN ARRAY['web', 'configuration']
        ELSE ARRAY['monitoring']
    END
FROM playbooks p
CROSS JOIN roles r
WHERE p.playbook_name = 'configure_web_infrastructure';

-- Role defaults.

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    role_id,
    priority
)
SELECT
    'timezone',
    '"UTC"'::JSONB,
    'role_default',
    role_id,
    10
FROM roles
WHERE role_name = 'base';

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    role_id,
    priority
)
SELECT
    'nginx_port',
    '8080'::JSONB,
    'role_default',
    role_id,
    10
FROM roles
WHERE role_name = 'webserver';

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    role_id,
    priority
)
SELECT
    'monitoring_enabled',
    'true'::JSONB,
    'role_default',
    role_id,
    10
FROM roles
WHERE role_name = 'monitoring';

-- Inventory-level overrides.

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    host_id,
    priority
)
SELECT
    'monitoring_enabled',
    'false'::JSONB,
    'inventory',
    host_id,
    30
FROM inventory_hosts
WHERE hostname = 'web-02';

-- Playbook-level configuration.

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    playbook_id,
    priority
)
SELECT
    'nginx_port',
    '8080'::JSONB,
    'play',
    playbook_id,
    40
FROM playbooks
WHERE playbook_name = 'configure_web_infrastructure';

-- Extra-variable override.

INSERT INTO configuration_variables (
    variable_name,
    variable_value,
    scope,
    playbook_id,
    priority
)
SELECT
    'nginx_port',
    '8443'::JSONB,
    'extra',
    playbook_id,
    100
FROM playbooks
WHERE playbook_name = 'configure_web_infrastructure';

-- Role tasks.

INSERT INTO role_tasks (
    role_id,
    task_name,
    module_name,
    action_type,
    arguments,
    execution_position,
    tags,
    become_required
)
SELECT
    role_id,
    'Install curl',
    'package',
    'present',
    '{"name":"curl","state":"present"}'::JSONB,
    1,
    ARRAY['base', 'packages'],
    TRUE
FROM roles
WHERE role_name = 'base';

INSERT INTO role_tasks (
    role_id,
    task_name,
    module_name,
    action_type,
    arguments,
    execution_position,
    tags,
    become_required
)
SELECT
    role_id,
    'Install nginx',
    'package',
    'present',
    '{"name":"nginx","state":"present"}'::JSONB,
    1,
    ARRAY['web', 'packages'],
    TRUE
FROM roles
WHERE role_name = 'webserver';

INSERT INTO role_tasks (
    role_id,
    task_name,
    module_name,
    action_type,
    arguments,
    execution_position,
    tags,
    become_required
)
SELECT
    role_id,
    'Deploy nginx configuration',
    'template',
    'deploy',
    '{"src":"nginx.conf.j2","dest":"/etc/nginx/nginx.conf"}'::JSONB,
    2,
    ARRAY['web', 'configuration'],
    TRUE
FROM roles
WHERE role_name = 'webserver';

INSERT INTO role_tasks (
    role_id,
    task_name,
    module_name,
    action_type,
    arguments,
    execution_position,
    tags,
    become_required
)
SELECT
    role_id,
    'Start nginx',
    'service',
    'started',
    '{"name":"nginx","state":"started","enabled":true}'::JSONB,
    3,
    ARRAY['web', 'services'],
    TRUE
FROM roles
WHERE role_name = 'webserver';

INSERT INTO role_tasks (
    role_id,
    task_name,
    module_name,
    action_type,
    arguments,
    execution_position,
    tags,
    become_required
)
SELECT
    role_id,
    'Install node exporter',
    'package',
    'present',
    '{"name":"node-exporter","state":"present"}'::JSONB,
    1,
    ARRAY['monitoring'],
    TRUE
FROM roles
WHERE role_name = 'monitoring';

-- Handler definitions.

INSERT INTO role_handlers (
    role_id,
    handler_name,
    module_name,
    arguments
)
SELECT
    role_id,
    'restart nginx',
    'service',
    '{"name":"nginx","state":"restarted"}'::JSONB
FROM roles
WHERE role_name = 'webserver';

-- Configuration deployment notifies the restart handler.

INSERT INTO task_notifications (
    task_id,
    handler_id
)
SELECT
    t.task_id,
    h.handler_id
FROM role_tasks t
JOIN roles r
    ON r.role_id = t.role_id
JOIN role_handlers h
    ON h.role_id = r.role_id
WHERE r.role_name = 'webserver'
  AND t.task_name = 'Deploy nginx configuration'
  AND h.handler_name = 'restart nginx';

-- ------------------------------------------------------------
-- SAMPLE EXECUTION
-- ------------------------------------------------------------

INSERT INTO execution_runs (
    playbook_id,
    mode,
    status,
    requested_by,
    execution_metadata
)
SELECT
    playbook_id,
    'normal',
    'running',
    'infrastructure-admin',
    '{"change_ticket":"CHG-2026-001","source":"deployment"}'::JSONB
FROM playbooks
WHERE playbook_name = 'configure_web_infrastructure';

INSERT INTO execution_run_hosts (
    run_id,
    host_id,
    status
)
SELECT
    er.run_id,
    h.host_id,
    'running'
FROM execution_runs er
JOIN inventory_hosts h
    ON h.hostname IN ('web-01', 'web-02')
WHERE er.requested_by = 'infrastructure-admin'
  AND er.status = 'running';

-- ------------------------------------------------------------
-- SAMPLE RESOURCE EVALUATION AND IDEMPOTENCE
-- ------------------------------------------------------------

SELECT
    hostname,
    evaluate_resource_change(
        host_id,
        'package',
        'nginx',
        '{"state":"present","version":"1.24"}'::JSONB
    ) AS requires_change
FROM inventory_hosts
WHERE hostname IN ('web-01', 'web-02');

-- First application creates the desired-state record.

CALL apply_resource_state(
    (
        SELECT MAX(run_id)
        FROM execution_runs
        WHERE status = 'running'
    ),
    (
        SELECT host_id
        FROM inventory_hosts
        WHERE hostname = 'web-01'
    ),
    'package',
    'nginx',
    '{"state":"present","version":"1.24"}'::JSONB
);

-- Second evaluation should report no change.

SELECT evaluate_resource_change(
    (
        SELECT host_id
        FROM inventory_hosts
        WHERE hostname = 'web-01'
    ),
    'package',
    'nginx',
    '{"state":"present","version":"1.24"}'::JSONB
) AS idempotent_result;

-- ------------------------------------------------------------
-- SAMPLE TASK RESULTS
-- ------------------------------------------------------------

INSERT INTO task_execution_results (
    run_id,
    host_id,
    task_id,
    status,
    changed,
    message,
    execution_duration_ms,
    completed_at
)
SELECT
    er.run_id,
    h.host_id,
    t.task_id,
    'changed',
    TRUE,
    'Package installed successfully.',
    1250,
    NOW()
FROM execution_runs er
JOIN execution_run_hosts erh
    ON erh.run_id = er.run_id
JOIN inventory_hosts h
    ON h.host_id = erh.host_id
JOIN role_tasks t
    ON t.task_name = 'Install nginx'
JOIN roles r
    ON r.role_id = t.role_id
WHERE er.status = 'running'
  AND h.hostname = 'web-01'
  AND r.role_name = 'webserver';

INSERT INTO task_execution_results (
    run_id,
    host_id,
    task_id,
    status,
    changed,
    message,
    execution_duration_ms,
    completed_at
)
SELECT
    er.run_id,
    h.host_id,
    t.task_id,
    'ok',
    FALSE,
    'Package already installed.',
    90,
    NOW()
FROM execution_runs er
JOIN execution_run_hosts erh
    ON erh.run_id = er.run_id
JOIN inventory_hosts h
    ON h.host_id = erh.host_id
JOIN role_tasks t
    ON t.task_name = 'Install nginx'
JOIN roles r
    ON r.role_id = t.role_id
WHERE er.status = 'running'
  AND h.hostname = 'web-02'
  AND r.role_name = 'webserver';

-- ------------------------------------------------------------
-- HANDLER NOTIFICATION
-- ------------------------------------------------------------

INSERT INTO handler_execution_queue (
    run_id,
    host_id,
    handler_id,
    status
)
SELECT
    er.run_id,
    h.host_id,
    rh.handler_id,
    'pending'
FROM execution_runs er
JOIN inventory_hosts h
    ON h.hostname = 'web-01'
JOIN roles r
    ON r.role_name = 'webserver'
JOIN role_handlers rh
    ON rh.role_id = r.role_id
WHERE er.status = 'running'
  AND rh.handler_name = 'restart nginx'
ON CONFLICT (
    run_id,
    host_id,
    handler_id
)
WHERE status = 'pending'
DO NOTHING;

-- Process pending handlers once.
UPDATE handler_execution_queue
SET
    status = 'executed',
    executed_at = NOW(),
    message = 'Service restart completed.'
WHERE status = 'pending'
  AND run_id = (
      SELECT MAX(run_id)
      FROM execution_runs
      WHERE status = 'running'
  );

-- ------------------------------------------------------------
-- COMPLETE THE EXECUTION RUN
-- ------------------------------------------------------------

UPDATE execution_run_hosts
SET status = 'completed'
WHERE run_id = (
    SELECT MAX(run_id)
    FROM execution_runs
    WHERE status = 'running'
);

UPDATE execution_runs
SET
    status = 'completed',
    completed_at = NOW()
WHERE status = 'running';

-- ------------------------------------------------------------
-- REPORTING AND VALIDATION QUERIES
-- ------------------------------------------------------------

-- 1. Registered role catalogue.

SELECT
    role_name,
    version,
    description,
    minimum_ansible_version,
    is_active
FROM roles
ORDER BY role_name, version;

-- 2. Dependency relationships.

SELECT *
FROM role_dependency_report
ORDER BY role_name;

-- 3. Inventory grouped by environment.

SELECT
    environment,
    COUNT(*) AS host_count,
    COUNT(*) FILTER (
        WHERE is_active
    ) AS active_hosts
FROM inventory_hosts
GROUP BY environment
ORDER BY environment;

-- 4. Role execution order.

SELECT
    p.playbook_name,
    pr.execution_position,
    r.role_name,
    pr.tags
FROM playbook_roles pr
JOIN playbooks p
    ON p.playbook_id = pr.playbook_id
JOIN roles r
    ON r.role_id = pr.role_id
WHERE pr.enabled
ORDER BY p.playbook_name, pr.execution_position;

-- 5. Effective variable resolution.

SELECT
    h.hostname,
    resolve_host_variable(
        h.host_id,
        r.role_id,
        p.playbook_id,
        'nginx_port'
    ) AS effective_nginx_port
FROM inventory_hosts h
CROSS JOIN roles r
CROSS JOIN playbooks p
WHERE h.hostname = 'web-01'
  AND r.role_name = 'webserver'
  AND p.playbook_name = 'configure_web_infrastructure';

-- 6. Task execution details.

SELECT
    h.hostname,
    r.role_name,
    t.task_name,
    tr.status,
    tr.changed,
    tr.execution_duration_ms,
    tr.message
FROM task_execution_results tr
JOIN inventory_hosts h
    ON h.host_id = tr.host_id
JOIN role_tasks t
    ON t.task_id = tr.task_id
JOIN roles r
    ON r.role_id = t.role_id
ORDER BY tr.started_at DESC;

-- 7. Execution summary.

SELECT *
FROM execution_report
ORDER BY started_at DESC;

-- 8. Resource state.

SELECT
    h.hostname,
    mr.resource_type,
    mr.resource_identifier,
    mr.desired_state,
    mr.updated_at
FROM managed_resources mr
JOIN inventory_hosts h
    ON h.host_id = mr.host_id
ORDER BY h.hostname, mr.resource_type;

-- 9. Handler processing status.

SELECT
    h.hostname,
    rh.handler_name,
    q.status,
    q.notified_at,
    q.executed_at,
    q.message
FROM handler_execution_queue q
JOIN inventory_hosts h
    ON h.host_id = q.host_id
JOIN role_handlers rh
    ON rh.handler_id = q.handler_id
ORDER BY q.notified_at DESC;

-- 10. Detect roles with no tasks.

SELECT
    r.role_name
FROM roles r
LEFT JOIN role_tasks t
    ON t.role_id = r.role_id
WHERE t.task_id IS NULL;

COMMIT;

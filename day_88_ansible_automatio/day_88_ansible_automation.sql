-- ================================================================
-- ANSIBLE AUTOMATION
-- Variables, Handlers, Templates, and Conditionals
-- PostgreSQL 14+
--
-- Relational configuration-management execution model.
--
-- Covers:
--   Inventories, groups, hosts, variables, variable precedence,
--   playbooks, tasks, templates, handlers, notifications,
--   conditional evaluation, execution results, and reporting.
--
-- The database models automation execution. It does not replace
-- Ansible's YAML parser, Jinja2 renderer, or execution engine.
-- ================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ansible_lab;

SET search_path TO ansible_lab, public;

-- ------------------------------------------------
-- 1. Domain enumerations
-- ------------------------------------------------

CREATE TYPE environment_type AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE variable_scope AS ENUM (
    'role_defaults',
    'inventory',
    'group_vars',
    'host_vars',
    'play_vars',
    'task_vars',
    'extra_vars'
);

CREATE TYPE task_status AS ENUM (
    'pending',
    'ok',
    'changed',
    'skipped',
    'failed'
);

CREATE TYPE execution_status AS ENUM (
    'running',
    'successful',
    'failed',
    'partially_failed'
);

CREATE TYPE handler_status AS ENUM (
    'registered',
    'pending',
    'executed',
    'failed'
);

-- ------------------------------------------------
-- 2. Inventory and infrastructure
-- ------------------------------------------------

CREATE TABLE inventories (
    inventory_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    inventory_name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    inventory_id BIGINT NOT NULL
        REFERENCES inventories(inventory_id)
        ON DELETE CASCADE,
    group_name VARCHAR(150) NOT NULL,
    description TEXT,
    UNIQUE (inventory_id, group_name),
    UNIQUE (inventory_id, group_id)
);

CREATE TABLE hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    inventory_id BIGINT NOT NULL
        REFERENCES inventories(inventory_id)
        ON DELETE CASCADE,
    hostname VARCHAR(255) NOT NULL,
    management_ip INET,
    environment environment_type NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (inventory_id, hostname),
    UNIQUE (inventory_id, host_id)
);

CREATE TABLE host_group_memberships (
    inventory_id BIGINT NOT NULL,
    host_id BIGINT NOT NULL,
    group_id BIGINT NOT NULL,
    PRIMARY KEY (host_id, group_id),
    FOREIGN KEY (inventory_id, host_id)
        REFERENCES hosts(inventory_id, host_id)
        ON DELETE CASCADE,
    FOREIGN KEY (inventory_id, group_id)
        REFERENCES inventory_groups(inventory_id, group_id)
        ON DELETE CASCADE
);

-- ------------------------------------------------
-- 3. Variable definitions and precedence
-- ------------------------------------------------

CREATE TABLE variable_definitions (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    inventory_id BIGINT NOT NULL
        REFERENCES inventories(inventory_id)
        ON DELETE CASCADE,
    scope variable_scope NOT NULL,
    group_id BIGINT,
    host_id BIGINT,
    variable_name VARCHAR(150) NOT NULL,
    variable_value JSONB NOT NULL,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (inventory_id, group_id)
        REFERENCES inventory_groups(inventory_id, group_id),

    FOREIGN KEY (inventory_id, host_id)
        REFERENCES hosts(inventory_id, host_id),

    CHECK (
        (scope = 'group_vars' AND group_id IS NOT NULL
            AND host_id IS NULL)
        OR
        (scope = 'host_vars' AND host_id IS NOT NULL
            AND group_id IS NULL)
        OR
        (scope NOT IN ('group_vars', 'host_vars')
            AND group_id IS NULL AND host_id IS NULL)
    ),

    CHECK (
        variable_name ~ '^[a-zA-Z_][a-zA-Z0-9_]*$'
    )
);

CREATE INDEX idx_variable_resolution
ON variable_definitions (
    inventory_id,
    variable_name,
    scope
);

CREATE INDEX idx_group_membership_host
ON host_group_memberships(group_id, host_id);

-- ------------------------------------------------
-- 4. Playbooks and task definitions
-- ------------------------------------------------

CREATE TABLE playbooks (
    playbook_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    inventory_id BIGINT NOT NULL
        REFERENCES inventories(inventory_id),
    playbook_name VARCHAR(150) NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (inventory_id, playbook_name)
);

CREATE TABLE automation_tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id)
        ON DELETE CASCADE,
    task_name VARCHAR(200) NOT NULL,
    task_order INTEGER NOT NULL CHECK (task_order > 0),
    module_name VARCHAR(100) NOT NULL,
    action_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    conditional_expression TEXT,
    notification_name VARCHAR(150),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (playbook_id, task_order),
    UNIQUE (playbook_id, task_id)
);

CREATE INDEX idx_tasks_execution_order
ON automation_tasks(playbook_id, task_order)
WHERE enabled = TRUE;

-- ------------------------------------------------
-- 5. Templates
-- ------------------------------------------------

CREATE TABLE configuration_templates (
    template_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id)
        ON DELETE CASCADE,
    template_name VARCHAR(200) NOT NULL,
    destination_path TEXT NOT NULL,
    template_content TEXT NOT NULL,
    file_owner VARCHAR(100) NOT NULL DEFAULT 'root',
    file_group VARCHAR(100) NOT NULL DEFAULT 'root',
    file_mode VARCHAR(4) NOT NULL DEFAULT '0644',
    version_number INTEGER NOT NULL DEFAULT 1
        CHECK (version_number > 0),
    UNIQUE (playbook_id, template_name),
    CHECK (destination_path LIKE '/%'),
    CHECK (file_mode ~ '^[0-7]{3,4}$')
);

-- ------------------------------------------------
-- 6. Handlers and event relationships
-- ------------------------------------------------

CREATE TABLE handlers (
    handler_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id)
        ON DELETE CASCADE,
    handler_name VARCHAR(150) NOT NULL,
    module_name VARCHAR(100) NOT NULL,
    action_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    execution_order INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (playbook_id, handler_name),
    UNIQUE (playbook_id, handler_id)
);

CREATE TABLE handler_listeners (
    listener_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    handler_id BIGINT NOT NULL
        REFERENCES handlers(handler_id)
        ON DELETE CASCADE,
    notification_name VARCHAR(150) NOT NULL,
    UNIQUE (handler_id, notification_name)
);

CREATE TABLE task_handler_notifications (
    task_id BIGINT NOT NULL
        REFERENCES automation_tasks(task_id)
        ON DELETE CASCADE,
    handler_id BIGINT NOT NULL
        REFERENCES handlers(handler_id)
        ON DELETE CASCADE,
    PRIMARY KEY (task_id, handler_id)
);

-- ------------------------------------------------
-- 7. Execution records
-- ------------------------------------------------

CREATE TABLE automation_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    playbook_id BIGINT NOT NULL
        REFERENCES playbooks(playbook_id),
    execution_status execution_status NOT NULL DEFAULT 'running',
    initiated_by VARCHAR(150) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    failure_message TEXT,
    CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX idx_runs_playbook_started
ON automation_runs(playbook_id, started_at DESC);

CREATE TABLE host_run_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    run_id BIGINT NOT NULL
        REFERENCES automation_runs(run_id)
        ON DELETE CASCADE,
    host_id BIGINT NOT NULL
        REFERENCES hosts(host_id),
    final_status task_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (run_id, host_id),
    CHECK (
        completed_at IS NULL OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE task_execution_results (
    task_result_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    result_id BIGINT NOT NULL
        REFERENCES host_run_results(result_id)
        ON DELETE CASCADE,
    task_id BIGINT NOT NULL
        REFERENCES automation_tasks(task_id),
    execution_status task_status NOT NULL DEFAULT 'pending',
    changed BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_condition BOOLEAN,
    execution_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (result_id, task_id),
    CHECK (
        completed_at IS NULL OR completed_at >= started_at
    ),
    CHECK (
        (execution_status = 'changed' AND changed = TRUE)
        OR
        (execution_status <> 'changed' AND changed = FALSE)
    )
);

CREATE INDEX idx_task_results_status
ON task_execution_results(execution_status, result_id);

-- ------------------------------------------------
-- 8. Handler execution and notifications
-- ------------------------------------------------

CREATE TABLE handler_execution_results (
    handler_result_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    result_id BIGINT NOT NULL
        REFERENCES host_run_results(result_id)
        ON DELETE CASCADE,
    handler_id BIGINT NOT NULL
        REFERENCES handlers(handler_id),
    status handler_status NOT NULL DEFAULT 'registered',
    notification_count INTEGER NOT NULL DEFAULT 0,
    executed_at TIMESTAMPTZ,
    execution_message TEXT,
    UNIQUE (result_id, handler_id),
    CHECK (notification_count >= 0)
);

CREATE TABLE handler_notification_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    task_result_id BIGINT NOT NULL
        REFERENCES task_execution_results(task_result_id)
        ON DELETE CASCADE,
    handler_id BIGINT NOT NULL
        REFERENCES handlers(handler_id),
    notification_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_handler_pending
ON handler_execution_results(result_id, status);

-- ------------------------------------------------
-- 9. Resolve effective variables
-- ------------------------------------------------

CREATE OR REPLACE FUNCTION resolve_host_variables(
    p_inventory_id BIGINT,
    p_host_id BIGINT
)
RETURNS TABLE (
    variable_name VARCHAR,
    variable_value JSONB,
    winning_scope variable_scope,
    is_secret BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT DISTINCT ON (vd.variable_name)
        vd.variable_name,
        vd.variable_value,
        vd.scope,
        vd.is_secret
    FROM variable_definitions vd
    WHERE vd.inventory_id = p_inventory_id
      AND (
          (vd.scope NOT IN ('group_vars', 'host_vars'))
          OR
          (vd.scope = 'host_vars' AND vd.host_id = p_host_id)
          OR
          (
              vd.scope = 'group_vars'
              AND EXISTS (
                  SELECT 1
                  FROM host_group_memberships hgm
                  WHERE hgm.inventory_id = p_inventory_id
                    AND hgm.host_id = p_host_id
                    AND hgm.group_id = vd.group_id
              )
          )
      )
    ORDER BY
        vd.variable_name,
        CASE vd.scope
            WHEN 'role_defaults' THEN 10
            WHEN 'inventory' THEN 20
            WHEN 'group_vars' THEN 30
            WHEN 'host_vars' THEN 40
            WHEN 'play_vars' THEN 50
            WHEN 'task_vars' THEN 60
            WHEN 'extra_vars' THEN 70
        END DESC,
        vd.variable_id DESC;
$$;

-- ------------------------------------------------
-- 10. Validate effective application variables
-- ------------------------------------------------

CREATE OR REPLACE FUNCTION validate_application_variables(
    p_inventory_id BIGINT,
    p_host_id BIGINT
)
RETURNS TABLE (
    valid BOOLEAN,
    validation_message TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_variables JSONB;
    v_port INTEGER;
    v_name TEXT;
    v_directory TEXT;
    v_version TEXT;
BEGIN
    SELECT jsonb_object_agg(
        variable_name,
        variable_value
    )
    INTO v_variables
    FROM resolve_host_variables(
        p_inventory_id,
        p_host_id
    );

    IF v_variables IS NULL THEN
        RETURN QUERY
        SELECT FALSE, 'No variables resolved';
        RETURN;
    END IF;

    v_name := v_variables ->> 'application_name';
    v_directory := v_variables ->> 'application_directory';
    v_version := v_variables ->> 'application_version';

    IF v_name IS NULL OR v_name = '' THEN
        RETURN QUERY
        SELECT FALSE, 'Missing application_name';
        RETURN;
    END IF;

    IF v_directory IS NULL
       OR v_directory NOT LIKE '/%' THEN
        RETURN QUERY
        SELECT FALSE, 'Invalid application_directory';
        RETURN;
    END IF;

    IF v_version IS NULL OR v_version = '' THEN
        RETURN QUERY
        SELECT FALSE, 'Missing application_version';
        RETURN;
    END IF;

    BEGIN
        v_port := (v_variables ->> 'application_port')::INTEGER;
    EXCEPTION
        WHEN OTHERS THEN
            RETURN QUERY
            SELECT FALSE, 'Application port is not an integer';
            RETURN;
    END;

    IF v_port < 1 OR v_port > 65535 THEN
        RETURN QUERY
        SELECT FALSE, 'Application port outside valid range';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'All application variables are valid';
END;
$$;

-- ------------------------------------------------
-- 11. Trigger: maintain task result consistency
-- ------------------------------------------------

CREATE OR REPLACE FUNCTION enforce_task_result_consistency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.execution_status = 'changed' THEN
        NEW.changed := TRUE;
    ELSE
        NEW.changed := FALSE;
    END IF;

    IF NEW.execution_status IN ('ok', 'changed', 'skipped', 'failed')
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_task_result_consistency
BEFORE INSERT OR UPDATE
ON task_execution_results
FOR EACH ROW
EXECUTE FUNCTION enforce_task_result_consistency();

-- ------------------------------------------------
-- 12. Procedure: create an automation run
-- ------------------------------------------------

CREATE OR REPLACE PROCEDURE start_automation_run(
    IN p_playbook_id BIGINT,
    IN p_initiated_by VARCHAR,
    INOUT p_run_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM playbooks
        WHERE playbook_id = p_playbook_id
          AND enabled = TRUE
    ) THEN
        RAISE EXCEPTION
            'Playbook % does not exist or is disabled',
            p_playbook_id;
    END IF;

    IF p_initiated_by IS NULL
       OR btrim(p_initiated_by) = '' THEN
        RAISE EXCEPTION 'Initiator is required';
    END IF;

    INSERT INTO automation_runs (
        playbook_id,
        execution_status,
        initiated_by
    )
    VALUES (
        p_playbook_id,
        'running',
        p_initiated_by
    )
    RETURNING run_id INTO p_run_id;

    INSERT INTO host_run_results (
        run_id,
        host_id,
        final_status,
        started_at
    )
    SELECT
        p_run_id,
        h.host_id,
        'pending',
        CURRENT_TIMESTAMP
    FROM hosts h
    JOIN inventories i
        ON i.inventory_id = h.inventory_id
    JOIN playbooks p
        ON p.inventory_id = i.inventory_id
    WHERE p.playbook_id = p_playbook_id
      AND h.enabled = TRUE;
END;
$$;

-- ------------------------------------------------
-- 13. Procedure: record a task execution
-- ------------------------------------------------

CREATE OR REPLACE PROCEDURE record_task_execution(
    IN p_result_id BIGINT,
    IN p_task_id BIGINT,
    IN p_status task_status,
    IN p_condition BOOLEAN,
    IN p_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_status execution_status;
BEGIN
    SELECT ar.execution_status
    INTO v_run_status
    FROM host_run_results hrr
    JOIN automation_runs ar
        ON ar.run_id = hrr.run_id
    WHERE hrr.result_id = p_result_id
    FOR UPDATE OF hrr, ar;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Host execution result not found';
    END IF;

    IF v_run_status <> 'running' THEN
        RAISE EXCEPTION
            'Cannot add task results to a completed run';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM task_execution_results
        WHERE result_id = p_result_id
          AND task_id = p_task_id
    ) THEN
        INSERT INTO task_execution_results (
            result_id,
            task_id,
            execution_status,
            evaluated_condition,
            execution_message
        )
        VALUES (
            p_result_id,
            p_task_id,
            p_status,
            p_condition,
            p_message
        );
    ELSE
        RAISE EXCEPTION
            'Task already recorded for this host execution';
    END IF;

    UPDATE host_run_results
    SET final_status = CASE
        WHEN p_status = 'failed' THEN 'failed'::task_status
        WHEN p_status = 'changed' THEN 'changed'::task_status
        WHEN p_status = 'ok' THEN 'ok'::task_status
        ELSE final_status
    END
    WHERE result_id = p_result_id;
END;
$$;

-- ------------------------------------------------
-- 14. Procedure: notify a handler
-- ------------------------------------------------

CREATE OR REPLACE PROCEDURE notify_handler(
    IN p_task_result_id BIGINT,
    IN p_handler_id BIGINT,
    IN p_notification_name VARCHAR
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_changed BOOLEAN;
    v_playbook_id BIGINT;
BEGIN
    SELECT ter.changed, at.playbook_id
    INTO v_changed, v_playbook_id
    FROM task_execution_results ter
    JOIN host_run_results hrr
        ON hrr.result_id = ter.result_id
    JOIN automation_runs ar
        ON ar.run_id = hrr.run_id
    JOIN automation_tasks at
        ON at.task_id = ter.task_id
    WHERE ter.task_result_id = p_task_result_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Task execution result not found';
    END IF;

    IF NOT v_changed THEN
        RAISE EXCEPTION
            'Unchanged or skipped tasks cannot notify handlers';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM handlers h
        JOIN handler_listeners hl
            ON hl.handler_id = h.handler_id
        WHERE h.handler_id = p_handler_id
          AND h.playbook_id = v_playbook_id
          AND hl.notification_name = p_notification_name
          AND h.enabled = TRUE
    ) THEN
        RAISE EXCEPTION
            'Handler does not subscribe to this notification';
    END IF;

    INSERT INTO handler_notification_events (
        task_result_id,
        handler_id,
        notification_name
    )
    VALUES (
        p_task_result_id,
        p_handler_id,
        p_notification_name
    );

    -- The unique result/handler pair represents a deduplicated
    -- pending handler for one host execution.
    INSERT INTO handler_execution_results (
        result_id,
        handler_id,
        status,
        notification_count
    )
    SELECT
        ter.result_id,
        p_handler_id,
        'pending',
        1
    FROM task_execution_results ter
    WHERE ter.task_result_id = p_task_result_id
    ON CONFLICT (result_id, handler_id)
    DO UPDATE SET
        notification_count =
            handler_execution_results.notification_count + 1,
        status = CASE
            WHEN handler_execution_results.status = 'executed'
                THEN 'executed'::handler_status
            ELSE 'pending'::handler_status
        END;
END;
$$;

-- ------------------------------------------------
-- 15. Procedure: execute pending handler records
-- ------------------------------------------------

CREATE OR REPLACE PROCEDURE mark_handler_executed(
    IN p_result_id BIGINT,
    IN p_handler_id BIGINT,
    IN p_success BOOLEAN,
    IN p_message TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE handler_execution_results
    SET
        status = CASE
            WHEN p_success THEN 'executed'::handler_status
            ELSE 'failed'::handler_status
        END,
        executed_at = CURRENT_TIMESTAMP,
        execution_message = p_message
    WHERE result_id = p_result_id
      AND handler_id = p_handler_id
      AND status = 'pending';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Pending handler record not found';
    END IF;
END;
$$;

-- ------------------------------------------------
-- 16. Procedure: finalize automation run
-- ------------------------------------------------

CREATE OR REPLACE PROCEDURE finalize_automation_run(
    IN p_run_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_failed INTEGER;
    v_total INTEGER;
    v_unfinished INTEGER;
BEGIN
    SELECT
        COUNT(*) FILTER (
            WHERE final_status = 'failed'
        ),
        COUNT(*),
        COUNT(*) FILTER (
            WHERE final_status = 'pending'
        )
    INTO v_failed, v_total, v_unfinished
    FROM host_run_results
    WHERE run_id = p_run_id;

    IF NOT EXISTS (
        SELECT 1
        FROM automation_runs
        WHERE run_id = p_run_id
          AND execution_status = 'running'
    ) THEN
        RAISE EXCEPTION
            'Run does not exist or is already finalized';
    END IF;

    IF v_unfinished > 0 THEN
        RAISE EXCEPTION
            'Cannot finalize: % hosts remain unfinished',
            v_unfinished;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM handler_execution_results her
        JOIN host_run_results hrr
            ON hrr.result_id = her.result_id
        WHERE hrr.run_id = p_run_id
          AND her.status IN ('pending', 'failed')
    ) THEN
        RAISE EXCEPTION
            'Cannot finalize: pending or failed handlers exist';
    END IF;

    UPDATE automation_runs
    SET
        execution_status = CASE
            WHEN v_failed = 0 THEN 'successful'::execution_status
            WHEN v_failed = v_total THEN 'failed'::execution_status
            ELSE 'partially_failed'::execution_status
        END,
        completed_at = CURRENT_TIMESTAMP
    WHERE run_id = p_run_id;
END;
$$;

-- ------------------------------------------------
-- 17. Reporting view
-- ------------------------------------------------

CREATE OR REPLACE VIEW automation_execution_report AS
SELECT
    ar.run_id,
    p.playbook_name,
    ar.initiated_by,
    ar.execution_status AS run_status,
    ar.started_at,
    ar.completed_at,
    h.hostname,
    h.environment,
    hrr.final_status AS host_status,
    COUNT(ter.task_result_id) AS tasks_executed,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'changed'
    ) AS changed_tasks,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'ok'
    ) AS successful_tasks,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'skipped'
    ) AS skipped_tasks,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'failed'
    ) AS failed_tasks
FROM automation_runs ar
JOIN playbooks p
    ON p.playbook_id = ar.playbook_id
JOIN host_run_results hrr
    ON hrr.run_id = ar.run_id
JOIN hosts h
    ON h.host_id = hrr.host_id
LEFT JOIN task_execution_results ter
    ON ter.result_id = hrr.result_id
GROUP BY
    ar.run_id,
    p.playbook_name,
    ar.initiated_by,
    ar.execution_status,
    ar.started_at,
    ar.completed_at,
    h.hostname,
    h.environment,
    hrr.final_status;

-- ------------------------------------------------
-- 18. Reporting view for pending handlers
-- ------------------------------------------------

CREATE OR REPLACE VIEW pending_handler_report AS
SELECT
    her.result_id,
    h.hostname,
    hd.handler_name,
    her.notification_count,
    her.status,
    her.execution_message
FROM handler_execution_results her
JOIN host_run_results hrr
    ON hrr.result_id = her.result_id
JOIN hosts h
    ON h.host_id = hrr.host_id
JOIN handlers hd
    ON hd.handler_id = her.handler_id
WHERE her.status = 'pending';

-- ------------------------------------------------
-- 19. Sample inventory
-- ------------------------------------------------

INSERT INTO inventories (
    inventory_name,
    description
)
VALUES (
    'production-inventory',
    'Production web application infrastructure'
);

INSERT INTO inventory_groups (
    inventory_id,
    group_name,
    description
)
SELECT
    inventory_id,
    'web',
    'Web application servers'
FROM inventories
WHERE inventory_name = 'production-inventory';

INSERT INTO inventory_groups (
    inventory_id,
    group_name,
    description
)
SELECT
    inventory_id,
    'canary',
    'Canary deployment servers'
FROM inventories
WHERE inventory_name = 'production-inventory';

INSERT INTO hosts (
    inventory_id,
    hostname,
    management_ip,
    environment
)
SELECT
    inventory_id,
    'web01.example.internal',
    '192.0.2.11',
    'production'
FROM inventories
WHERE inventory_name = 'production-inventory';

INSERT INTO hosts (
    inventory_id,
    hostname,
    management_ip,
    environment
)
SELECT
    inventory_id,
    'web02.example.internal',
    '192.0.2.12',
    'production'
FROM inventories
WHERE inventory_name = 'production-inventory';

INSERT INTO host_group_memberships (
    inventory_id,
    host_id,
    group_id
)
SELECT
    h.inventory_id,
    h.host_id,
    g.group_id
FROM hosts h
JOIN inventory_groups g
    ON g.inventory_id = h.inventory_id
WHERE g.group_name = 'web';

INSERT INTO host_group_memberships (
    inventory_id,
    host_id,
    group_id
)
SELECT
    h.inventory_id,
    h.host_id,
    g.group_id
FROM hosts h
JOIN inventory_groups g
    ON g.inventory_id = h.inventory_id
WHERE h.hostname = 'web02.example.internal'
  AND g.group_name = 'canary';

-- ------------------------------------------------
-- 20. Sample variables
-- ------------------------------------------------

INSERT INTO variable_definitions (
    inventory_id,
    scope,
    variable_name,
    variable_value
)
SELECT
    inventory_id,
    'role_defaults',
    variable_name,
    variable_value
FROM inventories
CROSS JOIN (
    VALUES
        ('application_name', '"inventory-api"'::jsonb),
        ('application_version', '"1.0.0"'::jsonb),
        ('application_directory', '"/opt/inventory"'::jsonb),
        ('service_name', '"inventory-api"'::jsonb),
        ('application_port', '8080'::jsonb),
        ('environment', '"development"'::jsonb)
) AS defaults(variable_name, variable_value)
WHERE inventory_name = 'production-inventory';

INSERT INTO variable_definitions (
    inventory_id,
    scope,
    group_id,
    variable_name,
    variable_value
)
SELECT
    i.inventory_id,
    'group_vars',
    g.group_id,
    'environment',
    '"production"'::jsonb
FROM inventories i
JOIN inventory_groups g
    ON g.inventory_id = i.inventory_id
WHERE i.inventory_name = 'production-inventory'
  AND g.group_name = 'web';

INSERT INTO variable_definitions (
    inventory_id,
    scope,
    host_id,
    variable_name,
    variable_value
)
SELECT
    inventory_id,
    'host_vars',
    host_id,
    'application_port',
    '8081'::jsonb
FROM hosts
WHERE hostname = 'web02.example.internal';

INSERT INTO variable_definitions (
    inventory_id,
    scope,
    variable_name,
    variable_value
)
SELECT
    inventory_id,
    'extra_vars',
    'application_version',
    '"1.1.0"'::jsonb
FROM inventories
WHERE inventory_name = 'production-inventory';

-- ------------------------------------------------
-- 21. Sample playbook
-- ------------------------------------------------

INSERT INTO playbooks (
    inventory_id,
    playbook_name,
    description
)
SELECT
    inventory_id,
    'deploy-inventory-api',
    'Deploy application and render service configuration'
FROM inventories
WHERE inventory_name = 'production-inventory';

INSERT INTO automation_tasks (
    playbook_id,
    task_name,
    task_order,
    module_name,
    action_parameters,
    conditional_expression
)
SELECT
    playbook_id,
    task.task_name,
    task.task_order,
    task.module_name,
    task.parameters,
    task.condition
FROM playbooks
CROSS JOIN (
    VALUES
    (
        'Create application directory',
        1,
        'ansible.builtin.file',
        '{"state":"directory","mode":"0755"}'::jsonb,
        NULL::TEXT
    ),
    (
        'Deploy application package',
        2,
        'ansible.builtin.package',
        '{"name":"inventory-api","state":"present"}'::jsonb,
        NULL::TEXT
    ),
    (
        'Render application configuration',
        3,
        'ansible.builtin.template',
        '{"src":"application.conf.j2","dest":"/opt/inventory/application.conf"}'::jsonb,
        'environment == production'
    ),
    (
        'Verify service',
        4,
        'ansible.builtin.service',
        '{"name":"inventory-api","state":"started"}'::jsonb,
        'inventory group contains web'
    )
) AS task(
    task_name,
    task_order,
    module_name,
    parameters,
    condition
)
WHERE playbook_name = 'deploy-inventory-api';

-- ------------------------------------------------
-- 22. Configuration template
-- ------------------------------------------------

INSERT INTO configuration_templates (
    playbook_id,
    template_name,
    destination_path,
    template_content,
    file_owner,
    file_group,
    file_mode
)
SELECT
    playbook_id,
    'application.conf.j2',
    '/opt/inventory/application.conf',
    E'server {\n    listen {{ application_port }};\n    server_name {{ application_name }};\n    environment {{ environment }};\n}',
    'root',
    'root',
    '0644'
FROM playbooks
WHERE playbook_name = 'deploy-inventory-api';

-- ------------------------------------------------
-- 23. Register handlers
-- ------------------------------------------------

INSERT INTO handlers (
    playbook_id,
    handler_name,
    module_name,
    action_parameters,
    execution_order
)
SELECT
    playbook_id,
    'restart application',
    'ansible.builtin.service',
    '{"name":"inventory-api","state":"restarted"}'::jsonb,
    1
FROM playbooks
WHERE playbook_name = 'deploy-inventory-api';

INSERT INTO handler_listeners (
    handler_id,
    notification_name
)
SELECT
    handler_id,
    'application configuration changed'
FROM handlers
WHERE handler_name = 'restart application';

INSERT INTO task_handler_notifications (
    task_id,
    handler_id
)
SELECT
    t.task_id,
    h.handler_id
FROM automation_tasks t
JOIN handlers h
    ON h.playbook_id = t.playbook_id
WHERE t.task_name IN (
    'Deploy application package',
    'Render application configuration'
)
AND h.handler_name = 'restart application';

-- ------------------------------------------------
-- 24. Variable retrieval
-- ------------------------------------------------

SELECT
    h.hostname,
    v.variable_name,
    CASE
        WHEN v.is_secret THEN '"[REDACTED]"'::jsonb
        ELSE v.variable_value
    END AS effective_value,
    v.winning_scope
FROM hosts h
CROSS JOIN LATERAL resolve_host_variables(
    h.inventory_id,
    h.host_id
) v
ORDER BY h.hostname, v.variable_name;

-- ------------------------------------------------
-- 25. Variable validation
-- ------------------------------------------------

SELECT
    h.hostname,
    validation.valid,
    validation.validation_message
FROM hosts h
CROSS JOIN LATERAL validate_application_variables(
    h.inventory_id,
    h.host_id
) validation
ORDER BY h.hostname;

-- ------------------------------------------------
-- 26. Conditional eligibility evaluation
-- ------------------------------------------------

SELECT
    h.hostname,
    h.environment,
    g.group_name,
    CASE
        WHEN h.environment = 'production'
             AND g.group_name = 'web'
        THEN 'ELIGIBLE'
        ELSE 'SKIPPED'
    END AS task_eligibility
FROM hosts h
JOIN host_group_memberships hgm
    ON hgm.host_id = h.host_id
JOIN inventory_groups g
    ON g.group_id = hgm.group_id
WHERE g.group_name IN ('web', 'canary')
ORDER BY h.hostname;

-- ------------------------------------------------
-- 27. Demonstrate an automation run
-- ------------------------------------------------

DO $$
DECLARE
    v_playbook_id BIGINT;
    v_run_id BIGINT;
    v_result_id BIGINT;
    v_task_id BIGINT;
    v_handler_id BIGINT;
    v_task_result_id BIGINT;
BEGIN
    SELECT playbook_id
    INTO v_playbook_id
    FROM playbooks
    WHERE playbook_name = 'deploy-inventory-api';

    CALL start_automation_run(
        v_playbook_id,
        'automation-operator',
        v_run_id
    );

    SELECT handler_id
    INTO v_handler_id
    FROM handlers
    WHERE playbook_id = v_playbook_id
      AND handler_name = 'restart application';

    -- Demonstrate changed deployment and handler notification.
    SELECT hrr.result_id
    INTO v_result_id
    FROM host_run_results hrr
    JOIN hosts h
        ON h.host_id = hrr.host_id
    WHERE hrr.run_id = v_run_id
      AND h.hostname = 'web01.example.internal';

    SELECT task_id
    INTO v_task_id
    FROM automation_tasks
    WHERE playbook_id = v_playbook_id
      AND task_name = 'Deploy application package';

    CALL record_task_execution(
        v_result_id,
        v_task_id,
        'changed',
        TRUE,
        'Application package updated'
    );

    SELECT task_result_id
    INTO v_task_result_id
    FROM task_execution_results
    WHERE result_id = v_result_id
      AND task_id = v_task_id;

    CALL notify_handler(
        v_task_result_id,
        v_handler_id,
        'application configuration changed'
    );

    CALL mark_handler_executed(
        v_result_id,
        v_handler_id,
        TRUE,
        'Application service restarted successfully'
    );

    -- Record a skipped conditional task.
    SELECT task_id
    INTO v_task_id
    FROM automation_tasks
    WHERE playbook_id = v_playbook_id
      AND task_name = 'Render application configuration';

    CALL record_task_execution(
        v_result_id,
        v_task_id,
        'skipped',
        FALSE,
        'Condition was not satisfied'
    );

    -- Record remaining tasks as successful for this demonstration.
    SELECT task_id
    INTO v_task_id
    FROM automation_tasks
    WHERE playbook_id = v_playbook_id
      AND task_name = 'Create application directory';

    CALL record_task_execution(
        v_result_id,
        v_task_id,
        'ok',
        TRUE,
        'Directory already exists'
    );

    SELECT task_id
    INTO v_task_id
    FROM automation_tasks
    WHERE playbook_id = v_playbook_id
      AND task_name = 'Verify service';

    CALL record_task_execution(
        v_result_id,
        v_task_id,
        'ok',
        TRUE,
        'Service verification passed'
    );

    UPDATE host_run_results
    SET
        final_status = 'changed',
        completed_at = CURRENT_TIMESTAMP
    WHERE result_id = v_result_id;

    -- Complete the second host with a simulated task failure.
    SELECT hrr.result_id
    INTO v_result_id
    FROM host_run_results hrr
    JOIN hosts h
        ON h.host_id = hrr.host_id
    WHERE hrr.run_id = v_run_id
      AND h.hostname = 'web02.example.internal';

    SELECT task_id
    INTO v_task_id
    FROM automation_tasks
    WHERE playbook_id = v_playbook_id
      AND task_name = 'Deploy application package';

    CALL record_task_execution(
        v_result_id,
        v_task_id,
        'failed',
        TRUE,
        'Simulated package repository connection failure'
    );

    UPDATE host_run_results
    SET
        final_status = 'failed',
        completed_at = CURRENT_TIMESTAMP
    WHERE result_id = v_result_id;

    CALL finalize_automation_run(v_run_id);
END;
$$;

-- ------------------------------------------------
-- 28. Execution reporting
-- ------------------------------------------------

SELECT *
FROM automation_execution_report
ORDER BY run_id, hostname;

-- ------------------------------------------------
-- 29. Handler reporting
-- ------------------------------------------------

SELECT *
FROM pending_handler_report;

-- ------------------------------------------------
-- 30. Aggregated task statistics
-- ------------------------------------------------

SELECT
    p.playbook_name,
    at.task_name,
    COUNT(ter.task_result_id) AS executions,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'changed'
    ) AS changed_count,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'ok'
    ) AS ok_count,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'skipped'
    ) AS skipped_count,
    COUNT(*) FILTER (
        WHERE ter.execution_status = 'failed'
    ) AS failed_count
FROM automation_tasks at
JOIN playbooks p
    ON p.playbook_id = at.playbook_id
LEFT JOIN automation_runs ar
    ON ar.playbook_id = p.playbook_id
LEFT JOIN host_run_results hrr
    ON hrr.run_id = ar.run_id
LEFT JOIN task_execution_results ter
    ON ter.result_id = hrr.result_id
   AND ter.task_id = at.task_id
GROUP BY
    p.playbook_name,
    at.task_id,
    at.task_name
ORDER BY
    p.playbook_name,
    at.task_id;

-- ------------------------------------------------
-- 31. Failed execution investigation
-- ------------------------------------------------

SELECT
    ar.run_id,
    h.hostname,
    at.task_name,
    ter.execution_message,
    ter.started_at,
    ter.completed_at
FROM task_execution_results ter
JOIN host_run_results hrr
    ON hrr.result_id = ter.result_id
JOIN automation_runs ar
    ON ar.run_id = hrr.run_id
JOIN hosts h
    ON h.host_id = hrr.host_id
JOIN automation_tasks at
    ON at.task_id = ter.task_id
WHERE ter.execution_status = 'failed'
ORDER BY ter.started_at DESC;

-- ------------------------------------------------
-- 32. Transaction handling
-- ------------------------------------------------

-- The demonstration run above is committed as part of this script.
-- Production callers should wrap each run or logical execution unit
-- in an explicit transaction and roll back inconsistent records.
--
-- The following read-only validation confirms run integrity.

DO $$
DECLARE
    v_invalid_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_invalid_count
    FROM task_execution_results ter
    JOIN host_run_results hrr
        ON hrr.result_id = ter.result_id
    JOIN automation_runs ar
        ON ar.run_id = hrr.run_id
    JOIN automation_tasks at
        ON at.task_id = ter.task_id
    WHERE at.playbook_id <> ar.playbook_id;

    IF v_invalid_count > 0 THEN
        RAISE EXCEPTION
            'Detected task execution records linked to another playbook';
    END IF;
END;
$$;

COMMIT;

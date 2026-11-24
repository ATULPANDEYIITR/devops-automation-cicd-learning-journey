/*
===============================================================================
TERRAFORM WORKSPACES
Environment Separation and Workspace Strategies
PostgreSQL 15+

This database models:
- Infrastructure projects and repositories
- Terraform environments and workspaces
- Remote state metadata and state versions
- Resource inventory
- Workspace configuration
- Deployment plans and execution history
- Approval decisions
- Workspace access control
- Environment-specific governance policies

PostgreSQL stores metadata and audit information.
Terraform state remains in the actual Terraform backend.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS infrastructure;

SET search_path TO infrastructure, public;

-- ============================================================================
-- ENUMERATIONS
-- ============================================================================

CREATE TYPE environment_type AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE workspace_status AS ENUM (
    'active',
    'locked',
    'archived'
);

CREATE TYPE deployment_status AS ENUM (
    'planned',
    'approved',
    'applying',
    'applied',
    'failed',
    'rejected',
    'cancelled'
);

CREATE TYPE approval_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'revoked'
);

CREATE TYPE isolation_strategy AS ENUM (
    'cli_workspace',
    'separate_root_module',
    'separate_backend'
);

CREATE TYPE operation_type AS ENUM (
    'create',
    'update',
    'destroy',
    'no_change'
);

-- ============================================================================
-- PROJECTS
-- ============================================================================

CREATE TABLE projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_name VARCHAR(120) NOT NULL UNIQUE,
    repository_url TEXT NOT NULL,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    cloud_provider VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_project_name
        CHECK (project_name ~ '^[a-zA-Z][a-zA-Z0-9_-]{1,119}$'),

    CONSTRAINT valid_cloud_provider
        CHECK (cloud_provider IN ('aws', 'azure', 'gcp'))
);

-- ============================================================================
-- ENVIRONMENTS
-- ============================================================================

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    environment environment_type NOT NULL,
    cloud_region VARCHAR(80) NOT NULL,
    monthly_budget NUMERIC(14,2) NOT NULL,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    maximum_instances INTEGER NOT NULL DEFAULT 5,
    database_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_project_environment
        UNIQUE (project_id, environment),

    CONSTRAINT positive_budget
        CHECK (monthly_budget > 0),

    CONSTRAINT nonnegative_instance_limit
        CHECK (maximum_instances >= 0),

    CONSTRAINT production_approval
        CHECK (
            environment <> 'production'
            OR approval_required = TRUE
        )
);

-- ============================================================================
-- WORKSPACES
-- ============================================================================

CREATE TABLE workspaces (
    workspace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    environment_id BIGINT NOT NULL REFERENCES environments(environment_id),

    workspace_name VARCHAR(63) NOT NULL,
    isolation isolation_strategy NOT NULL DEFAULT 'cli_workspace',
    status workspace_status NOT NULL DEFAULT 'active',

    backend_type VARCHAR(50) NOT NULL,
    backend_identifier TEXT NOT NULL,
    state_key TEXT NOT NULL,

    state_lineage UUID NOT NULL DEFAULT gen_random_uuid(),
    current_state_serial BIGINT NOT NULL DEFAULT 0,

    terraform_version VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_workspace_name
        UNIQUE (project_id, workspace_name),

    CONSTRAINT unique_workspace_state_key
        UNIQUE (backend_identifier, state_key),

    CONSTRAINT valid_workspace_name
        CHECK (workspace_name ~ '^[a-z][a-z0-9_-]{0,62}$'),

    CONSTRAINT valid_state_serial
        CHECK (current_state_serial >= 0),

    CONSTRAINT valid_backend_type
        CHECK (
            backend_type IN (
                's3',
                'azurerm',
                'gcs',
                'local',
                'terraform_cloud'
            )
        )
);

CREATE INDEX idx_workspaces_project_environment
    ON workspaces(project_id, environment_id);

CREATE INDEX idx_workspaces_status
    ON workspaces(status);

CREATE INDEX idx_workspaces_state_lineage
    ON workspaces(state_lineage);

-- ============================================================================
-- USERS AND ACCESS CONTROL
-- ============================================================================

CREATE TABLE platform_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE workspace_memberships (
    membership_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),
    user_id BIGINT NOT NULL REFERENCES platform_users(user_id),

    role VARCHAR(30) NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_workspace_membership
        UNIQUE (workspace_id, user_id),

    CONSTRAINT valid_membership_role
        CHECK (
            role IN (
                'viewer',
                'developer',
                'operator',
                'approver',
                'administrator'
            )
        )
);

CREATE INDEX idx_membership_user
    ON workspace_memberships(user_id, workspace_id);

-- ============================================================================
-- WORKSPACE CONFIGURATION
-- ============================================================================

CREATE TABLE workspace_variables (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),

    variable_name VARCHAR(120) NOT NULL,
    variable_value JSONB,
    sensitive BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_workspace_variable
        UNIQUE (workspace_id, variable_name),

    CONSTRAINT valid_variable_name
        CHECK (variable_name ~ '^[a-zA-Z_][a-zA-Z0-9_]*$'),

    -- Sensitive values are represented by an external secret reference.
    CONSTRAINT sensitive_variable_reference
        CHECK (
            sensitive = FALSE
            OR (
                variable_value IS NULL
                OR variable_value ? 'secret_reference'
            )
        )
);

CREATE INDEX idx_workspace_variables
    ON workspace_variables(workspace_id, variable_name);

-- ============================================================================
-- TERRAFORM STATE VERSIONS
-- ============================================================================

CREATE TABLE state_versions (
    state_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),

    lineage UUID NOT NULL,
    serial BIGINT NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    object_location TEXT NOT NULL,

    terraform_version VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT REFERENCES platform_users(user_id),

    CONSTRAINT unique_workspace_state_serial
        UNIQUE (workspace_id, serial),

    CONSTRAINT valid_state_serial
        CHECK (serial >= 0),

    CONSTRAINT valid_content_hash
        CHECK (length(content_hash) >= 32)
);

CREATE INDEX idx_state_versions_latest
    ON state_versions(workspace_id, serial DESC);

-- ============================================================================
-- RESOURCE INVENTORY
-- ============================================================================

CREATE TABLE managed_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),

    resource_address TEXT NOT NULL,
    resource_type VARCHAR(120) NOT NULL,
    provider VARCHAR(80) NOT NULL,
    cloud_resource_id TEXT,

    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_workspace_resource
        UNIQUE (workspace_id, resource_address)
);

CREATE INDEX idx_managed_resources_workspace
    ON managed_resources(workspace_id);

CREATE INDEX idx_managed_resources_type
    ON managed_resources(resource_type);

CREATE INDEX idx_managed_resources_attributes
    ON managed_resources USING GIN(attributes);

-- ============================================================================
-- DEPLOYMENT PLANS
-- ============================================================================

CREATE TABLE deployment_plans (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),

    plan_reference UUID NOT NULL DEFAULT gen_random_uuid(),
    expected_state_serial BIGINT NOT NULL,

    status deployment_status NOT NULL DEFAULT 'planned',
    changeset JSONB NOT NULL,

    plan_hash VARCHAR(128) NOT NULL,
    created_by BIGINT NOT NULL REFERENCES platform_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT unique_plan_reference
        UNIQUE (plan_reference),

    CONSTRAINT valid_plan_expiration
        CHECK (expires_at > created_at),

    CONSTRAINT valid_plan_serial
        CHECK (expected_state_serial >= 0),

    CONSTRAINT valid_changeset
        CHECK (jsonb_typeof(changeset) = 'array')
);

CREATE INDEX idx_deployment_plans_workspace
    ON deployment_plans(workspace_id, created_at DESC);

CREATE INDEX idx_deployment_plans_status
    ON deployment_plans(status, expires_at);

-- ============================================================================
-- PLAN OPERATIONS
-- ============================================================================

CREATE TABLE plan_operations (
    operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES deployment_plans(plan_id)
        ON DELETE CASCADE,

    resource_address TEXT NOT NULL,
    operation operation_type NOT NULL,
    desired_configuration JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_plan_resource_operation
        UNIQUE (plan_id, resource_address)
);

-- ============================================================================
-- APPROVALS
-- ============================================================================

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES deployment_plans(plan_id),

    approver_id BIGINT NOT NULL REFERENCES platform_users(user_id),
    decision approval_status NOT NULL DEFAULT 'pending',

    comments TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_plan_approver
        UNIQUE (plan_id, approver_id),

    CONSTRAINT decision_timestamp_consistency
        CHECK (
            (decision = 'pending' AND decided_at IS NULL)
            OR
            (decision <> 'pending' AND decided_at IS NOT NULL)
        )
);

CREATE INDEX idx_approvals_plan_decision
    ON deployment_approvals(plan_id, decision);

-- ============================================================================
-- DEPLOYMENT EXECUTIONS
-- ============================================================================

CREATE TABLE deployment_executions (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES deployment_plans(plan_id),
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id),

    execution_status deployment_status NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    executed_by BIGINT NOT NULL REFERENCES platform_users(user_id),
    error_message TEXT,
    resulting_state_serial BIGINT,

    CONSTRAINT valid_execution_timestamps
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE INDEX idx_execution_workspace
    ON deployment_executions(workspace_id, started_at DESC);

-- ============================================================================
-- AUDIT EVENTS
-- ============================================================================

CREATE TABLE infrastructure_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT REFERENCES workspaces(workspace_id),
    user_id BIGINT REFERENCES platform_users(user_id),

    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_workspace_date
    ON infrastructure_audit(workspace_id, created_at DESC);

-- ============================================================================
-- TRIGGER: ENVIRONMENT AND PROJECT CONSISTENCY
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_workspace_environment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    environment_project_id BIGINT;
    environment_name environment_type;
BEGIN
    SELECT project_id, environment
    INTO environment_project_id, environment_name
    FROM environments
    WHERE environment_id = NEW.environment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Environment does not exist';
    END IF;

    IF environment_project_id <> NEW.project_id THEN
        RAISE EXCEPTION
            'Workspace project must match environment project';
    END IF;

    IF environment_name = 'production'
       AND NEW.isolation = 'cli_workspace' THEN
        RAISE EXCEPTION
            'Production must use a separately governed isolation strategy';
    END IF;

    NEW.updated_at = NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_workspace_environment
BEFORE INSERT OR UPDATE OF project_id, environment_id, isolation
ON workspaces
FOR EACH ROW
EXECUTE FUNCTION validate_workspace_environment();

-- ============================================================================
-- TRIGGER: STATE SERIAL INTEGRITY
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_state_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_lineage UUID;
    current_serial BIGINT;
BEGIN
    SELECT state_lineage, current_state_serial
    INTO current_lineage, current_serial
    FROM workspaces
    WHERE workspace_id = NEW.workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workspace does not exist';
    END IF;

    IF NEW.lineage <> current_lineage THEN
        RAISE EXCEPTION 'State lineage mismatch';
    END IF;

    IF NEW.serial <> current_serial + 1 THEN
        RAISE EXCEPTION
            'Expected state serial %, received %',
            current_serial + 1,
            NEW.serial;
    END IF;

    UPDATE workspaces
    SET current_state_serial = NEW.serial,
        updated_at = NOW()
    WHERE workspace_id = NEW.workspace_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_state_version
BEFORE INSERT ON state_versions
FOR EACH ROW
EXECUTE FUNCTION validate_state_version();

-- ============================================================================
-- TRIGGER: APPROVAL AUTHORIZATION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_deployment_approval()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    workspace_environment environment_type;
    membership_role VARCHAR(30);
    current_decision approval_status;
BEGIN
    SELECT e.environment
    INTO workspace_environment
    FROM deployment_plans p
    JOIN workspaces w ON w.workspace_id = p.workspace_id
    JOIN environments e ON e.environment_id = w.environment_id
    WHERE p.plan_id = NEW.plan_id;

    SELECT role
    INTO membership_role
    FROM workspace_memberships m
    JOIN deployment_plans p ON p.workspace_id = m.workspace_id
    WHERE p.plan_id = NEW.plan_id
      AND m.user_id = NEW.approver_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Approver does not belong to the workspace';
    END IF;

    IF membership_role NOT IN ('approver', 'administrator') THEN
        RAISE EXCEPTION
            'User does not have approval privileges';
    END IF;

    IF NEW.decision IN ('approved', 'rejected')
       AND workspace_environment = 'production'
       AND membership_role <> 'administrator'
       AND membership_role <> 'approver' THEN
        RAISE EXCEPTION
            'Production approval role required';
    END IF;

    IF NEW.decision <> 'pending' THEN
        NEW.decided_at = COALESCE(NEW.decided_at, NOW());
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_deployment_approval
BEFORE INSERT OR UPDATE ON deployment_approvals
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_approval();

-- ============================================================================
-- ENVIRONMENT ELIGIBILITY VIEW
-- ============================================================================

CREATE OR REPLACE VIEW workspace_environment_report AS
SELECT
    w.workspace_id,
    p.project_name,
    w.workspace_name,
    e.environment,
    w.isolation,
    w.status,
    w.backend_type,
    w.state_key,
    w.current_state_serial,
    e.cloud_region,
    e.approval_required,
    e.monthly_budget,
    COUNT(DISTINCT r.resource_id) FILTER (
        WHERE r.is_active
    ) AS active_resources,
    COUNT(DISTINCT dp.plan_id) FILTER (
        WHERE dp.status = 'planned'
    ) AS pending_plans
FROM workspaces w
JOIN projects p ON p.project_id = w.project_id
JOIN environments e ON e.environment_id = w.environment_id
LEFT JOIN managed_resources r
    ON r.workspace_id = w.workspace_id
LEFT JOIN deployment_plans dp
    ON dp.workspace_id = w.workspace_id
GROUP BY
    w.workspace_id,
    p.project_name,
    w.workspace_name,
    e.environment,
    w.isolation,
    w.status,
    w.backend_type,
    w.state_key,
    w.current_state_serial,
    e.cloud_region,
    e.approval_required,
    e.monthly_budget;

-- ============================================================================
-- FUNCTION: DEPLOYMENT ELIGIBILITY
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_deployment(
    p_plan_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT,
    workspace_name TEXT,
    environment_name TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_workspace workspaces%ROWTYPE;
    v_environment environments%ROWTYPE;
    v_plan deployment_plans%ROWTYPE;
    v_approved_count BIGINT;
    v_active_resources BIGINT;
BEGIN
    SELECT *
    INTO v_plan
    FROM deployment_plans
    WHERE plan_id = p_plan_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'Deployment plan not found',
            NULL::TEXT,
            NULL::TEXT;
        RETURN;
    END IF;

    SELECT *
    INTO v_workspace
    FROM workspaces
    WHERE workspace_id = v_plan.workspace_id;

    SELECT *
    INTO v_environment
    FROM environments
    WHERE environment_id = v_workspace.environment_id;

    IF v_workspace.status <> 'active' THEN
        RETURN QUERY SELECT
            FALSE,
            'Workspace is not active',
            v_workspace.workspace_name::TEXT,
            v_environment.environment::TEXT;
        RETURN;
    END IF;

    IF v_plan.expires_at <= NOW() THEN
        RETURN QUERY SELECT
            FALSE,
            'Deployment plan has expired',
            v_workspace.workspace_name::TEXT,
            v_environment.environment::TEXT;
        RETURN;
    END IF;

    IF v_plan.expected_state_serial <>
       v_workspace.current_state_serial THEN
        RETURN QUERY SELECT
            FALSE,
            'Plan references stale infrastructure state',
            v_workspace.workspace_name::TEXT,
            v_environment.environment::TEXT;
        RETURN;
    END IF;

    IF v_plan.status NOT IN ('planned', 'approved') THEN
        RETURN QUERY SELECT
            FALSE,
            'Plan is not in an executable state',
            v_workspace.workspace_name::TEXT,
            v_environment.environment::TEXT;
        RETURN;
    END IF;

    IF v_environment.approval_required THEN
        SELECT COUNT(*)
        INTO v_approved_count
        FROM deployment_approvals
        WHERE plan_id = p_plan_id
          AND decision = 'approved';

        IF v_approved_count = 0 THEN
            RETURN QUERY SELECT
                FALSE,
                'Required approval is missing',
                v_workspace.workspace_name::TEXT,
                v_environment.environment::TEXT;
            RETURN;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM deployment_approvals
            WHERE plan_id = p_plan_id
              AND decision = 'rejected'
        ) THEN
            RETURN QUERY SELECT
                FALSE,
                'Plan has a rejected approval',
                v_workspace.workspace_name::TEXT,
                v_environment.environment::TEXT;
            RETURN;
        END IF;
    END IF;

    SELECT COUNT(*)
    INTO v_active_resources
    FROM managed_resources
    WHERE workspace_id = v_workspace.workspace_id
      AND is_active;

    IF v_active_resources > 10000 THEN
        RETURN QUERY SELECT
            FALSE,
            'Resource inventory limit exceeded',
            v_workspace.workspace_name::TEXT,
            v_environment.environment::TEXT;
        RETURN;
    END IF;

    RETURN QUERY SELECT
        TRUE,
        'Deployment eligible',
        v_workspace.workspace_name::TEXT,
        v_environment.environment::TEXT;
END;
$$;

-- ============================================================================
-- FUNCTION: CONTROLLED DEPLOYMENT PROCESSING
-- ============================================================================

CREATE OR REPLACE FUNCTION process_deployment(
    p_plan_id BIGINT,
    p_executor_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_plan deployment_plans%ROWTYPE;
    v_workspace workspaces%ROWTYPE;
    v_execution_id BIGINT;
    v_eligible BOOLEAN;
    v_reason TEXT;
    v_approval_required BOOLEAN;
BEGIN
    SELECT *
    INTO v_plan
    FROM deployment_plans
    WHERE plan_id = p_plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Plan not found';
    END IF;

    SELECT *
    INTO v_workspace
    FROM workspaces
    WHERE workspace_id = v_plan.workspace_id
    FOR UPDATE;

    SELECT e.approval_required
    INTO v_approval_required
    FROM environments e
    WHERE e.environment_id = v_workspace.environment_id;

    -- Lock the plan and workspace to prevent concurrent metadata updates.
    SELECT eligible, reason
    INTO v_eligible, v_reason
    FROM evaluate_deployment(p_plan_id);

    IF NOT v_eligible THEN
        RAISE EXCEPTION 'Deployment rejected: %', v_reason;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM workspace_memberships
        WHERE workspace_id = v_workspace.workspace_id
          AND user_id = p_executor_id
          AND role IN ('operator', 'administrator')
    ) THEN
        RAISE EXCEPTION 'Executor lacks deployment permissions';
    END IF;

    IF v_approval_required AND NOT EXISTS (
        SELECT 1
        FROM deployment_approvals
        WHERE plan_id = p_plan_id
          AND decision = 'approved'
    ) THEN
        RAISE EXCEPTION 'Production approval is required';
    END IF;

    INSERT INTO deployment_executions (
        plan_id,
        workspace_id,
        execution_status,
        executed_by
    )
    VALUES (
        p_plan_id,
        v_workspace.workspace_id,
        'applying',
        p_executor_id
    )
    RETURNING execution_id INTO v_execution_id;

    UPDATE deployment_plans
    SET status = 'applying'
    WHERE plan_id = p_plan_id;

    INSERT INTO infrastructure_audit (
        workspace_id,
        user_id,
        event_type,
        event_data
    )
    VALUES (
        v_workspace.workspace_id,
        p_executor_id,
        'deployment_started',
        jsonb_build_object(
            'plan_id', p_plan_id,
            'execution_id', v_execution_id
        )
    );

    RETURN v_execution_id;
END;
$$;

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

INSERT INTO projects (
    project_name,
    repository_url,
    default_branch,
    cloud_provider
)
VALUES (
    'enterprise-platform',
    'https://github.com/example/enterprise-platform',
    'main',
    'aws'
);

INSERT INTO environments (
    project_id,
    environment,
    cloud_region,
    monthly_budget,
    approval_required,
    maximum_instances,
    database_enabled
)
SELECT
    project_id,
    'development',
    'ap-south-1',
    100,
    FALSE,
    2,
    FALSE
FROM projects
WHERE project_name = 'enterprise-platform';

INSERT INTO environments (
    project_id,
    environment,
    cloud_region,
    monthly_budget,
    approval_required,
    maximum_instances,
    database_enabled
)
SELECT
    project_id,
    'staging',
    'ap-south-1',
    500,
    FALSE,
    5,
    TRUE
FROM projects
WHERE project_name = 'enterprise-platform';

INSERT INTO environments (
    project_id,
    environment,
    cloud_region,
    monthly_budget,
    approval_required,
    maximum_instances,
    database_enabled
)
SELECT
    project_id,
    'production',
    'ap-south-1',
    2000,
    TRUE,
    10,
    TRUE
FROM projects
WHERE project_name = 'enterprise-platform';

INSERT INTO platform_users (username, email)
VALUES
    ('developer01', 'developer01@example.com'),
    ('operator01', 'operator01@example.com'),
    ('platformadmin', 'platformadmin@example.com');

-- Default workspace.
INSERT INTO workspaces (
    project_id,
    environment_id,
    workspace_name,
    isolation,
    backend_type,
    backend_identifier,
    state_key,
    terraform_version
)
SELECT
    p.project_id,
    e.environment_id,
    'default',
    'cli_workspace',
    's3',
    'company-terraform-state',
    'enterprise-platform/default',
    '1.9.0'
FROM projects p
JOIN environments e ON e.project_id = p.project_id
WHERE p.project_name = 'enterprise-platform'
  AND e.environment = 'development';

-- Development workspace.
INSERT INTO workspaces (
    project_id,
    environment_id,
    workspace_name,
    isolation,
    backend_type,
    backend_identifier,
    state_key,
    terraform_version
)
SELECT
    p.project_id,
    e.environment_id,
    'development',
    'cli_workspace',
    's3',
    'company-terraform-state',
    'enterprise-platform/development',
    '1.9.0'
FROM projects p
JOIN environments e ON e.project_id = p.project_id
WHERE p.project_name = 'enterprise-platform'
  AND e.environment = 'development';

-- Staging workspace.
INSERT INTO workspaces (
    project_id,
    environment_id,
    workspace_name,
    isolation,
    backend_type,
    backend_identifier,
    state_key,
    terraform_version
)
SELECT
    p.project_id,
    e.environment_id,
    'staging',
    'cli_workspace',
    's3',
    'company-terraform-state',
    'enterprise-platform/staging',
    '1.9.0'
FROM projects p
JOIN environments e ON e.project_id = p.project_id
WHERE p.project_name = 'enterprise-platform'
  AND e.environment = 'staging';

-- Production uses a separate backend strategy.
INSERT INTO workspaces (
    project_id,
    environment_id,
    workspace_name,
    isolation,
    backend_type,
    backend_identifier,
    state_key,
    terraform_version
)
SELECT
    p.project_id,
    e.environment_id,
    'production',
    'separate_backend',
    's3',
    'company-production-terraform-state',
    'production/enterprise-platform/terraform.tfstate',
    '1.9.0'
FROM projects p
JOIN environments e ON e.project_id = p.project_id
WHERE p.project_name = 'enterprise-platform'
  AND e.environment = 'production';

-- Membership assignments.
INSERT INTO workspace_memberships (
    workspace_id,
    user_id,
    role
)
SELECT
    w.workspace_id,
    u.user_id,
    CASE
        WHEN u.username = 'platformadmin'
            THEN 'administrator'
        WHEN u.username = 'operator01'
            THEN 'operator'
        ELSE 'developer'
    END
FROM workspaces w
CROSS JOIN platform_users u
WHERE w.workspace_name IN (
    'development',
    'staging',
    'production'
);

INSERT INTO workspace_memberships (
    workspace_id,
    user_id,
    role
)
SELECT
    w.workspace_id,
    u.user_id,
    'approver'
FROM workspaces w
CROSS JOIN platform_users u
WHERE w.workspace_name = 'production'
  AND u.username = 'platformadmin'
ON CONFLICT (workspace_id, user_id)
DO UPDATE SET role = 'administrator';

-- Workspace variables.
INSERT INTO workspace_variables (
    workspace_id,
    variable_name,
    variable_value,
    sensitive
)
SELECT
    workspace_id,
    'aws_region',
    '"ap-south-1"'::jsonb,
    FALSE
FROM workspaces
WHERE workspace_name IN (
    'development',
    'staging',
    'production'
);

INSERT INTO workspace_variables (
    workspace_id,
    variable_name,
    variable_value,
    sensitive
)
SELECT
    workspace_id,
    'database_password',
    '{"secret_reference":"vault://production/database"}'::jsonb,
    TRUE
FROM workspaces
WHERE workspace_name = 'production';

-- Sample resource inventory.
INSERT INTO managed_resources (
    workspace_id,
    resource_address,
    resource_type,
    provider,
    cloud_resource_id,
    attributes
)
SELECT
    workspace_id,
    'aws_instance.application',
    'aws_instance',
    'aws',
    'i-development-001',
    '{"instance_type":"t3.micro","count":1}'::jsonb
FROM workspaces
WHERE workspace_name = 'development';

INSERT INTO managed_resources (
    workspace_id,
    resource_address,
    resource_type,
    provider,
    cloud_resource_id,
    attributes
)
SELECT
    workspace_id,
    'aws_instance.application',
    'aws_instance',
    'aws',
    'i-staging-001',
    '{"instance_type":"t3.small","count":2}'::jsonb
FROM workspaces
WHERE workspace_name = 'staging';

INSERT INTO managed_resources (
    workspace_id,
    resource_address,
    resource_type,
    provider,
    cloud_resource_id,
    attributes
)
SELECT
    workspace_id,
    'aws_instance.application',
    'aws_instance',
    'aws',
    'i-production-001',
    '{"instance_type":"t3.medium","count":3}'::jsonb
FROM workspaces
WHERE workspace_name = 'production';

-- ============================================================================
-- DEPLOYMENT PLAN EXAMPLES
-- ============================================================================

INSERT INTO deployment_plans (
    workspace_id,
    expected_state_serial,
    status,
    changeset,
    plan_hash,
    created_by,
    expires_at
)
SELECT
    w.workspace_id,
    w.current_state_serial,
    'planned',
    '[{"action":"update","resource":"aws_instance.application"}]'::jsonb,
    repeat('a', 64),
    u.user_id,
    NOW() + INTERVAL '2 hours'
FROM workspaces w
CROSS JOIN platform_users u
WHERE w.workspace_name = 'development'
  AND u.username = 'developer01';

INSERT INTO deployment_plans (
    workspace_id,
    expected_state_serial,
    status,
    changeset,
    plan_hash,
    created_by,
    expires_at
)
SELECT
    w.workspace_id,
    w.current_state_serial,
    'planned',
    '[{"action":"update","resource":"aws_instance.application"}]'::jsonb,
    repeat('b', 64),
    u.user_id,
    NOW() + INTERVAL '2 hours'
FROM workspaces w
CROSS JOIN platform_users u
WHERE w.workspace_name = 'production'
  AND u.username = 'developer01';

-- A production approval decision.
INSERT INTO deployment_approvals (
    plan_id,
    approver_id,
    decision,
    comments,
    decided_at
)
SELECT
    dp.plan_id,
    u.user_id,
    'approved',
    'Reviewed production infrastructure change.',
    NOW()
FROM deployment_plans dp
JOIN workspaces w ON w.workspace_id = dp.workspace_id
CROSS JOIN platform_users u
WHERE w.workspace_name = 'production'
  AND u.username = 'platformadmin';

-- ============================================================================
-- RETRIEVAL QUERIES
-- ============================================================================

-- Complete workspace inventory.
SELECT *
FROM workspace_environment_report
ORDER BY project_name, environment;

-- Workspace-specific resource inventory.
SELECT
    w.workspace_name,
    r.resource_address,
    r.resource_type,
    r.cloud_resource_id,
    r.attributes
FROM workspaces w
JOIN managed_resources r
    ON r.workspace_id = w.workspace_id
WHERE w.workspace_name = 'staging';

-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- Find environments without a workspace.
SELECT
    e.environment,
    p.project_name
FROM environments e
JOIN projects p ON p.project_id = e.project_id
LEFT JOIN workspaces w
    ON w.environment_id = e.environment_id
WHERE w.workspace_id IS NULL;

-- Identify duplicate state lineage values across workspaces.
SELECT
    state_lineage,
    COUNT(*) AS workspace_count
FROM workspaces
GROUP BY state_lineage
HAVING COUNT(*) > 1;

-- Find production workspaces without separate backend isolation.
SELECT
    w.workspace_name,
    e.environment,
    w.isolation
FROM workspaces w
JOIN environments e ON e.environment_id = w.environment_id
WHERE e.environment = 'production'
  AND w.isolation = 'cli_workspace';

-- Find stale or expired deployment plans.
SELECT
    plan_id,
    workspace_id,
    expected_state_serial,
    expires_at
FROM deployment_plans
WHERE expires_at < NOW()
   OR status = 'planned';

-- ============================================================================
-- CTE: ENVIRONMENT RESOURCE AGGREGATION
-- ============================================================================

WITH resource_counts AS (
    SELECT
        workspace_id,
        COUNT(*) FILTER (WHERE is_active) AS active_resources,
        COUNT(*) FILTER (WHERE NOT is_active) AS inactive_resources
    FROM managed_resources
    GROUP BY workspace_id
)
SELECT
    w.workspace_name,
    e.environment,
    COALESCE(rc.active_resources, 0) AS active_resources,
    COALESCE(rc.inactive_resources, 0) AS inactive_resources,
    e.monthly_budget
FROM workspaces w
JOIN environments e ON e.environment_id = w.environment_id
LEFT JOIN resource_counts rc
    ON rc.workspace_id = w.workspace_id
ORDER BY e.environment;

-- ============================================================================
-- APPROVAL AND DEPLOYMENT EVALUATION
-- ============================================================================

SELECT
    dp.plan_id,
    w.workspace_name,
    e.environment,
    result.eligible,
    result.reason
FROM deployment_plans dp
JOIN workspaces w ON w.workspace_id = dp.workspace_id
JOIN environments e ON e.environment_id = w.environment_id
CROSS JOIN LATERAL evaluate_deployment(dp.plan_id) result
ORDER BY dp.plan_id;

-- ============================================================================
-- WORKFLOW PROCESSING
-- ============================================================================
-- The following transaction demonstrates a metadata deployment workflow.
-- Actual Terraform plan and apply execution must occur through the Terraform
-- execution system, not through PostgreSQL.

DO $$
DECLARE
    v_plan_id BIGINT;
    v_executor_id BIGINT;
    v_execution_id BIGINT;
BEGIN
    SELECT dp.plan_id
    INTO v_plan_id
    FROM deployment_plans dp
    JOIN workspaces w ON w.workspace_id = dp.workspace_id
    WHERE w.workspace_name = 'development'
      AND dp.status = 'planned'
    ORDER BY dp.plan_id
    LIMIT 1;

    SELECT user_id
    INTO v_executor_id
    FROM platform_users
    WHERE username = 'operator01';

    IF v_plan_id IS NOT NULL THEN
        v_execution_id := process_deployment(
            v_plan_id,
            v_executor_id
        );

        RAISE NOTICE
            'Deployment execution created: %',
            v_execution_id;
    END IF;
END;
$$;

-- ============================================================================
-- TRANSACTIONAL COMPLETION EXAMPLE
-- ============================================================================
-- This records the completion of a development deployment execution.
-- It does not claim that a cloud resource was created by PostgreSQL.

DO $$
DECLARE
    v_execution_id BIGINT;
    v_plan_id BIGINT;
    v_workspace_id BIGINT;
    v_serial BIGINT;
BEGIN
    SELECT
        de.execution_id,
        de.plan_id,
        de.workspace_id
    INTO
        v_execution_id,
        v_plan_id,
        v_workspace_id
    FROM deployment_executions de
    JOIN workspaces w ON w.workspace_id = de.workspace_id
    WHERE w.workspace_name = 'development'
      AND de.execution_status = 'applying'
    ORDER BY de.execution_id DESC
    LIMIT 1
    FOR UPDATE OF de;

    IF v_execution_id IS NOT NULL THEN
        SELECT current_state_serial
        INTO v_serial
        FROM workspaces
        WHERE workspace_id = v_workspace_id;

        UPDATE deployment_executions
        SET execution_status = 'applied',
            completed_at = NOW(),
            resulting_state_serial = v_serial
        WHERE execution_id = v_execution_id;

        UPDATE deployment_plans
        SET status = 'applied'
        WHERE plan_id = v_plan_id;

        INSERT INTO infrastructure_audit (
            workspace_id,
            event_type,
            event_data
        )
        VALUES (
            v_workspace_id,
            'deployment_completed',
            jsonb_build_object(
                'execution_id', v_execution_id,
                'plan_id', v_plan_id,
                'state_serial', v_serial
            )
        );
    END IF;
END;
$$;

-- ============================================================================
-- REPORTING
-- ============================================================================

-- Environment deployment history.
SELECT
    p.project_name,
    w.workspace_name,
    e.environment,
    dp.plan_id,
    dp.status AS plan_status,
    de.execution_status,
    de.started_at,
    de.completed_at,
    de.error_message
FROM deployment_plans dp
JOIN workspaces w ON w.workspace_id = dp.workspace_id
JOIN projects p ON p.project_id = w.project_id
JOIN environments e ON e.environment_id = w.environment_id
LEFT JOIN deployment_executions de
    ON de.plan_id = dp.plan_id
ORDER BY dp.created_at DESC;

-- Approval reporting.
SELECT
    w.workspace_name,
    dp.plan_id,
    u.username AS approver,
    da.decision,
    da.comments,
    da.decided_at
FROM deployment_approvals da
JOIN deployment_plans dp ON dp.plan_id = da.plan_id
JOIN workspaces w ON w.workspace_id = dp.workspace_id
JOIN platform_users u ON u.user_id = da.approver_id
ORDER BY da.created_at DESC;

-- Resource distribution by environment.
SELECT
    e.environment,
    COUNT(r.resource_id) AS total_resources,
    COUNT(DISTINCT w.workspace_id) AS workspace_count
FROM environments e
JOIN workspaces w ON w.environment_id = e.environment_id
LEFT JOIN managed_resources r
    ON r.workspace_id = w.workspace_id
   AND r.is_active
GROUP BY e.environment
ORDER BY e.environment;

COMMIT;

/*
===============================================================================
OPERATIONAL NOTES

1. The SQL database stores control-plane metadata, not Terraform state itself.

2. Actual Terraform state belongs in an appropriately secured backend.

3. PostgreSQL transaction locks do not replace Terraform backend locking.

4. State-version records must be created from verified Terraform state
   metadata. The state-version trigger enforces sequential serial numbers.

5. The workspace consistency trigger prevents production from using the
   CLI-workspace isolation strategy in this governance model.

6. Sensitive values should remain in a secret manager. The database stores
   references rather than plaintext credentials.

7. Deployment execution records represent orchestration metadata. Terraform
   must execute and verify the real infrastructure operations.

8. Database users should receive least-privilege schema permissions.
===============================================================================
*/

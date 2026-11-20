-- ============================================================
-- INFRASTRUCTURE AS CODE
-- Declarative Infrastructure Management and Governance
--
-- PostgreSQL 15+
--
-- Models:
--   Organizations
--   Repositories
--   Infrastructure environments
--   Resource specifications
--   Resource dependencies
--   Infrastructure state
--   Deployment plans
--   Deployment executions
--   Security policies
--   Policy evaluation
--   Drift detection
--   Deployment eligibility
--   Audit history
--
-- The schema distinguishes declared infrastructure from
-- recorded actual infrastructure state.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS iac;

SET search_path TO iac, public;

-- ============================================================
-- 1. ENUMERATIONS
-- ============================================================

CREATE TYPE resource_type AS ENUM (
    'network',
    'server',
    'storage',
    'firewall',
    'database',
    'load_balancer'
);

CREATE TYPE environment_type AS ENUM (
    'development',
    'testing',
    'staging',
    'production'
);

CREATE TYPE deployment_status AS ENUM (
    'planned',
    'approved',
    'running',
    'succeeded',
    'failed',
    'cancelled',
    'rolled_back'
);

CREATE TYPE deployment_action AS ENUM (
    'create',
    'update',
    'delete',
    'replace',
    'no_op'
);

CREATE TYPE policy_severity AS ENUM (
    'info',
    'warning',
    'error',
    'critical'
);

CREATE TYPE resource_status AS ENUM (
    'declared',
    'provisioning',
    'active',
    'failed',
    'deleting',
    'deleted'
);

-- ============================================================
-- 2. ORGANIZATIONS AND USERS
-- ============================================================

CREATE TABLE organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (
        role IN (
            'administrator',
            'infrastructure_engineer',
            'security_reviewer',
            'auditor',
            'operator'
        )
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, username),
    UNIQUE (organization_id, email),
    UNIQUE (organization_id, user_id)
);

-- ============================================================
-- 3. REPOSITORIES
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    repository_name VARCHAR(150) NOT NULL,
    description TEXT,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, repository_name),
    UNIQUE (organization_id, repository_id)
);

-- ============================================================
-- 4. INFRASTRUCTURE ENVIRONMENTS
-- ============================================================

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    environment_name VARCHAR(100) NOT NULL,
    environment environment_type NOT NULL,
    region VARCHAR(100) NOT NULL,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, environment_name),
    UNIQUE (organization_id, environment_id)
);

-- ============================================================
-- 5. INFRASTRUCTURE DECLARATIONS
--
-- These records represent desired state, not actual cloud state.
-- ============================================================

CREATE TABLE infrastructure_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL,
    repository_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,

    logical_id VARCHAR(150) NOT NULL,
    resource_type resource_type NOT NULL,

    provider VARCHAR(80) NOT NULL,
    region VARCHAR(100) NOT NULL,

    properties JSONB NOT NULL DEFAULT '{}'::JSONB,

    protected BOOLEAN NOT NULL DEFAULT FALSE,
    immutable_keys TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (organization_id, repository_id)
        REFERENCES repositories(organization_id, repository_id),

    FOREIGN KEY (organization_id, environment_id)
        REFERENCES environments(organization_id, environment_id),

    FOREIGN KEY (organization_id, created_by)
        REFERENCES users(organization_id, user_id),

    UNIQUE (
        repository_id,
        environment_id,
        logical_id
    ),

    UNIQUE (
        resource_id,
        repository_id,
        environment_id
    ),

    CHECK (jsonb_typeof(properties) = 'object'),

    CHECK (
        resource_type <> 'storage'
        OR properties ->> 'encrypted' = 'true'
    ),

    CHECK (
        resource_type <> 'server'
        OR (
            COALESCE(
                (properties ->> 'cpu')::INTEGER,
                0
            ) > 0
            AND
            COALESCE(
                (properties ->> 'memory_gb')::INTEGER,
                0
            ) > 0
        )
    ),

    CHECK (
        resource_type <> 'firewall'
        OR properties ->> 'default_action' = 'DENY'
    )
);

CREATE INDEX idx_resources_environment
    ON infrastructure_resources(environment_id, enabled);

CREATE INDEX idx_resources_type
    ON infrastructure_resources(resource_type);

CREATE INDEX idx_resources_properties
    ON infrastructure_resources
    USING GIN(properties);

-- ============================================================
-- 6. RESOURCE DEPENDENCIES
--
-- A dependent resource must not be provisioned before its
-- dependencies.
-- ============================================================

CREATE TABLE resource_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,

    resource_id BIGINT NOT NULL,
    depends_on_resource_id BIGINT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (
        resource_id,
        repository_id,
        environment_id
    )
        REFERENCES infrastructure_resources(
            resource_id,
            repository_id,
            environment_id
        ),

    FOREIGN KEY (
        depends_on_resource_id,
        repository_id,
        environment_id
    )
        REFERENCES infrastructure_resources(
            resource_id,
            repository_id,
            environment_id
        ),

    CHECK (resource_id <> depends_on_resource_id),

    UNIQUE (resource_id, depends_on_resource_id)
);

CREATE INDEX idx_dependencies_parent
    ON resource_dependencies(depends_on_resource_id);

-- ============================================================
-- 7. ACTUAL INFRASTRUCTURE STATE
--
-- This table records the latest observed provider state.
-- It is deliberately separate from desired configuration.
-- ============================================================

CREATE TABLE infrastructure_state (
    state_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    resource_id BIGINT NOT NULL UNIQUE
        REFERENCES infrastructure_resources(resource_id),

    provider_resource_id VARCHAR(255),
    actual_properties JSONB NOT NULL DEFAULT '{}'::JSONB,

    status resource_status NOT NULL DEFAULT 'declared',

    configuration_hash VARCHAR(64),

    observed_at TIMESTAMPTZ,
    last_deployed_at TIMESTAMPTZ,

    error_message TEXT,

    version BIGINT NOT NULL DEFAULT 0,

    CHECK (jsonb_typeof(actual_properties) = 'object'),
    CHECK (version >= 0)
);

CREATE INDEX idx_infrastructure_state_status
    ON infrastructure_state(status, observed_at);

-- ============================================================
-- 8. SECURITY AND GOVERNANCE POLICIES
-- ============================================================

CREATE TABLE infrastructure_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    policy_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,

    severity policy_severity NOT NULL DEFAULT 'error',

    resource_type resource_type,

    property_name VARCHAR(100) NOT NULL,
    expected_value JSONB,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, policy_name)
);

-- ============================================================
-- 9. DEPLOYMENT PLANS
-- ============================================================

CREATE TABLE deployment_plans (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL,
    repository_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,

    created_by BIGINT NOT NULL,

    plan_name VARCHAR(150) NOT NULL,
    plan_hash VARCHAR(64) NOT NULL,

    status deployment_status NOT NULL DEFAULT 'planned',

    state_revision BIGINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    FOREIGN KEY (organization_id, repository_id)
        REFERENCES repositories(organization_id, repository_id),

    FOREIGN KEY (organization_id, environment_id)
        REFERENCES environments(organization_id, environment_id),

    FOREIGN KEY (organization_id, created_by)
        REFERENCES users(organization_id, user_id),

    UNIQUE (
        plan_id,
        repository_id,
        environment_id
    ),

    CHECK (state_revision >= 0),
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE INDEX idx_deployment_plans_status
    ON deployment_plans(status, created_at DESC);

-- ============================================================
-- 10. PLAN RESOURCE ACTIONS
-- ============================================================

CREATE TABLE deployment_plan_items (
    plan_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    plan_id BIGINT NOT NULL,
    repository_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,

    resource_id BIGINT NOT NULL,

    action deployment_action NOT NULL,

    before_properties JSONB,
    after_properties JSONB,

    execution_order INTEGER NOT NULL,

    reason TEXT NOT NULL,

    FOREIGN KEY (
        plan_id,
        repository_id,
        environment_id
    )
        REFERENCES deployment_plans(
            plan_id,
            repository_id,
            environment_id
        ),

    FOREIGN KEY (
        resource_id,
        repository_id,
        environment_id
    )
        REFERENCES infrastructure_resources(
            resource_id,
            repository_id,
            environment_id
        ),

    UNIQUE (plan_id, resource_id),
    UNIQUE (plan_id, execution_order),

    CHECK (execution_order >= 0)
);

CREATE INDEX idx_plan_items_action
    ON deployment_plan_items(plan_id, action);

-- ============================================================
-- 11. DEPLOYMENT APPROVALS
-- ============================================================

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    plan_id BIGINT NOT NULL
        REFERENCES deployment_plans(plan_id),

    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id),

    decision VARCHAR(20) NOT NULL CHECK (
        decision IN ('approved', 'rejected')
    ),

    comments TEXT,

    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (plan_id, reviewer_id)
);

-- ============================================================
-- 12. DEPLOYMENT EXECUTIONS
-- ============================================================

CREATE TABLE deployment_executions (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    plan_id BIGINT NOT NULL
        REFERENCES deployment_plans(plan_id),

    executed_by BIGINT NOT NULL
        REFERENCES users(user_id),

    status deployment_status NOT NULL DEFAULT 'planned',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    error_message TEXT,

    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_executions_status
    ON deployment_executions(status, started_at DESC);

-- ============================================================
-- 13. AUDIT HISTORY
-- ============================================================

CREATE TABLE infrastructure_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    resource_id BIGINT
        REFERENCES infrastructure_resources(resource_id),

    user_id BIGINT
        REFERENCES users(user_id),

    event_type VARCHAR(100) NOT NULL,

    old_value JSONB,
    new_value JSONB,

    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    details JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX idx_audit_resource_time
    ON infrastructure_audit(resource_id, event_time DESC);

-- ============================================================
-- 14. UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_modified_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_resources_updated
BEFORE UPDATE ON infrastructure_resources
FOR EACH ROW
EXECUTE FUNCTION update_modified_timestamp();

-- ============================================================
-- 15. DEPENDENCY CYCLE VALIDATION
--
-- Recursive traversal detects whether inserting an edge creates
-- a path back to the original resource.
-- ============================================================

CREATE OR REPLACE FUNCTION validate_dependency_graph()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    cycle_exists BOOLEAN;
BEGIN
    IF NEW.resource_id = NEW.depends_on_resource_id THEN
        RAISE EXCEPTION 'Self-dependency is prohibited';
    END IF;

    WITH RECURSIVE reachable(resource_id) AS (
        SELECT NEW.depends_on_resource_id

        UNION

        SELECT dependency.depends_on_resource_id
        FROM resource_dependencies dependency
        JOIN reachable
            ON dependency.resource_id = reachable.resource_id
        WHERE dependency.repository_id = NEW.repository_id
          AND dependency.environment_id = NEW.environment_id
    )
    SELECT EXISTS (
        SELECT 1
        FROM reachable
        WHERE resource_id = NEW.resource_id
    )
    INTO cycle_exists;

    IF cycle_exists THEN
        RAISE EXCEPTION
            'Dependency cycle detected for resource %',
            NEW.resource_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_dependency
BEFORE INSERT OR UPDATE ON resource_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_dependency_graph();

-- ============================================================
-- 16. SECURITY POLICY EVALUATION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_resource_policies(
    p_resource_id BIGINT
)
RETURNS TABLE (
    policy_name VARCHAR(150),
    severity policy_severity,
    violation TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        policy.policy_name,
        policy.severity,
        format(
            'Property %s expected %s but received %s',
            policy.property_name,
            policy.expected_value::TEXT,
            resource.properties -> policy.property_name
        )
    FROM infrastructure_resources resource
    JOIN infrastructure_policies policy
        ON policy.organization_id = resource.organization_id
       AND (
            policy.resource_type IS NULL
            OR policy.resource_type = resource.resource_type
       )
    WHERE resource.resource_id = p_resource_id
      AND policy.enabled
      AND policy.expected_value IS NOT NULL
      AND resource.properties -> policy.property_name
          IS DISTINCT FROM policy.expected_value;
$$;

-- ============================================================
-- 17. DRIFT DETECTION VIEW
--
-- Desired state is compared with the latest recorded actual state.
-- ============================================================

CREATE OR REPLACE VIEW infrastructure_drift AS
SELECT
    resource.resource_id,
    resource.logical_id,
    resource.resource_type,
    resource.environment_id,

    state.status,

    resource.properties AS desired_properties,
    state.actual_properties,

    state.observed_at,

    CASE
        WHEN state.state_id IS NULL THEN 'MISSING_STATE'

        WHEN state.status = 'failed' THEN 'FAILED'

        WHEN state.actual_properties
             IS DISTINCT FROM resource.properties
            THEN 'DRIFTED'

        ELSE 'COMPLIANT'
    END AS drift_status

FROM infrastructure_resources resource
LEFT JOIN infrastructure_state state
    ON state.resource_id = resource.resource_id
WHERE resource.enabled;

-- ============================================================
-- 18. DEPLOYMENT ELIGIBILITY VIEW
--
-- A plan must be valid, have required approvals and contain no
-- blocking policy violations before execution.
-- ============================================================

CREATE OR REPLACE VIEW deployment_eligibility AS
SELECT
    plan.plan_id,
    plan.plan_name,
    plan.repository_id,
    plan.environment_id,
    plan.status,

    environment.environment,

    environment.approval_required,

    COUNT(DISTINCT approval.approval_id)
        FILTER (
            WHERE approval.decision = 'approved'
        ) AS approvals,

    COUNT(DISTINCT approval.approval_id)
        FILTER (
            WHERE approval.decision = 'rejected'
        ) AS rejections,

    CASE
        WHEN plan.status <> 'planned'
            THEN FALSE

        WHEN plan.expires_at IS NOT NULL
             AND plan.expires_at <= NOW()
            THEN FALSE

        WHEN environment.active = FALSE
            THEN FALSE

        WHEN environment.approval_required
             AND COUNT(DISTINCT approval.approval_id)
                 FILTER (
                     WHERE approval.decision = 'approved'
                 ) < 1
            THEN FALSE

        WHEN COUNT(DISTINCT approval.approval_id)
             FILTER (
                 WHERE approval.decision = 'rejected'
             ) > 0
            THEN FALSE

        ELSE TRUE
    END AS eligible

FROM deployment_plans plan

JOIN environments environment
    ON environment.environment_id = plan.environment_id

LEFT JOIN deployment_approvals approval
    ON approval.plan_id = plan.plan_id

GROUP BY
    plan.plan_id,
    plan.plan_name,
    plan.repository_id,
    plan.environment_id,
    plan.status,
    plan.expires_at,
    environment.environment,
    environment.approval_required,
    environment.active;

-- ============================================================
-- 19. DEPLOYMENT PROCESSING PROCEDURE
--
-- Uses row-level locking to prevent concurrent processing of
-- the same deployment plan.
-- ============================================================

CREATE OR REPLACE PROCEDURE execute_deployment_plan(
    p_plan_id BIGINT,
    p_user_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    selected_plan deployment_plans%ROWTYPE;
    selected_environment environments%ROWTYPE;
    selected_resource RECORD;
    selected_item RECORD;
    selected_state infrastructure_state%ROWTYPE;
    current_revision BIGINT;
BEGIN
    SELECT *
    INTO selected_plan
    FROM deployment_plans
    WHERE plan_id = p_plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment plan % does not exist', p_plan_id;
    END IF;

    IF selected_plan.status <> 'planned' THEN
        RAISE EXCEPTION 'Plan is not in planned status';
    END IF;

    IF selected_plan.expires_at IS NOT NULL
       AND selected_plan.expires_at <= NOW() THEN
        RAISE EXCEPTION 'Deployment plan has expired';
    END IF;

    SELECT *
    INTO selected_environment
    FROM environments
    WHERE environment_id = selected_plan.environment_id
    FOR UPDATE;

    IF NOT selected_environment.active THEN
        RAISE EXCEPTION 'Target environment is inactive';
    END IF;

    IF selected_environment.approval_required THEN
        IF NOT EXISTS (
            SELECT 1
            FROM deployment_approvals
            WHERE plan_id = p_plan_id
              AND decision = 'approved'
        ) THEN
            RAISE EXCEPTION 'Deployment approval is required';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM deployment_approvals
        WHERE plan_id = p_plan_id
          AND decision = 'rejected'
    ) THEN
        RAISE EXCEPTION 'Deployment has been rejected';
    END IF;

    SELECT revision
    INTO current_revision
    FROM (
        SELECT COALESCE(MAX(version), 0) AS revision
        FROM infrastructure_state
        JOIN infrastructure_resources
            USING (resource_id)
        WHERE repository_id = selected_plan.repository_id
          AND environment_id = selected_plan.environment_id
    ) revision_data;

    IF current_revision <> selected_plan.state_revision THEN
        RAISE EXCEPTION
            'Infrastructure state changed after planning';
    END IF;

    INSERT INTO deployment_executions (
        plan_id,
        executed_by,
        status,
        started_at
    )
    VALUES (
        p_plan_id,
        p_user_id,
        'running',
        NOW()
    );

    UPDATE deployment_plans
    SET status = 'running'
    WHERE plan_id = p_plan_id;

    -- Process resources in the order established by the planner.
    FOR selected_item IN
        SELECT *
        FROM deployment_plan_items
        WHERE plan_id = p_plan_id
        ORDER BY
            CASE
                WHEN action = 'delete' THEN 1
                ELSE 0
            END,
            CASE
                WHEN action = 'delete' THEN -execution_order
                ELSE execution_order
            END
    LOOP
        SELECT *
        INTO selected_resource
        FROM infrastructure_resources
        WHERE resource_id = selected_item.resource_id
        FOR UPDATE;

        IF selected_item.action IN ('create', 'update', 'replace') THEN

            INSERT INTO infrastructure_state (
                resource_id,
                actual_properties,
                status,
                observed_at,
                last_deployed_at,
                version
            )
            VALUES (
                selected_item.resource_id,
                selected_item.after_properties,
                'active',
                NOW(),
                NOW(),
                1
            )
            ON CONFLICT (resource_id)
            DO UPDATE SET
                actual_properties = EXCLUDED.actual_properties,
                status = 'active',
                observed_at = NOW(),
                last_deployed_at = NOW(),
                version = infrastructure_state.version + 1;

        ELSIF selected_item.action = 'delete' THEN

            IF selected_resource.protected THEN
                RAISE EXCEPTION
                    'Cannot delete protected resource %',
                    selected_resource.logical_id;
            END IF;

            UPDATE infrastructure_state
            SET
                status = 'deleted',
                observed_at = NOW(),
                version = version + 1
            WHERE resource_id = selected_item.resource_id;

        END IF;

        INSERT INTO infrastructure_audit (
            organization_id,
            resource_id,
            user_id,
            event_type,
            old_value,
            new_value
        )
        VALUES (
            selected_plan.organization_id,
            selected_item.resource_id,
            p_user_id,
            'RESOURCE_' || UPPER(selected_item.action::TEXT),
            selected_item.before_properties,
            selected_item.after_properties
        );
    END LOOP;

    UPDATE deployment_plans
    SET status = 'succeeded'
    WHERE plan_id = p_plan_id;

    UPDATE deployment_executions
    SET
        status = 'succeeded',
        completed_at = NOW()
    WHERE execution_id = (
        SELECT MAX(execution_id)
        FROM deployment_executions
        WHERE plan_id = p_plan_id
          AND status = 'running'
    );

EXCEPTION
    WHEN OTHERS THEN
        UPDATE deployment_plans
        SET status = 'failed'
        WHERE plan_id = p_plan_id
          AND status = 'running';

        UPDATE deployment_executions
        SET
            status = 'failed',
            completed_at = NOW(),
            error_message = SQLERRM
        WHERE execution_id = (
            SELECT MAX(execution_id)
            FROM deployment_executions
            WHERE plan_id = p_plan_id
              AND status = 'running'
        );

        RAISE;
END;
$$;

-- ============================================================
-- 20. SAMPLE ORGANIZATION
-- ============================================================

INSERT INTO organizations (organization_name)
VALUES ('Example Cloud Engineering');

INSERT INTO users (
    organization_id,
    username,
    email,
    role
)
VALUES
(
    1,
    'infra_admin',
    'infra.admin@example.com',
    'administrator'
),
(
    1,
    'cloud_engineer',
    'engineer@example.com',
    'infrastructure_engineer'
),
(
    1,
    'security_reviewer',
    'security@example.com',
    'security_reviewer'
),
(
    1,
    'cloud_auditor',
    'auditor@example.com',
    'auditor'
);

-- ============================================================
-- 21. SAMPLE REPOSITORY
-- ============================================================

INSERT INTO repositories (
    organization_id,
    repository_name,
    description
)
VALUES (
    1,
    'production-infrastructure',
    'Declarative production cloud infrastructure'
);

-- ============================================================
-- 22. SAMPLE ENVIRONMENTS
-- ============================================================

INSERT INTO environments (
    organization_id,
    environment_name,
    environment,
    region,
    approval_required
)
VALUES
(
    1,
    'development-ap-south',
    'development',
    'ap-south-1',
    FALSE
),
(
    1,
    'production-ap-south',
    'production',
    'ap-south-1',
    TRUE
);

-- ============================================================
-- 23. SAMPLE INFRASTRUCTURE DECLARATIONS
-- ============================================================

INSERT INTO infrastructure_resources (
    organization_id,
    repository_id,
    environment_id,
    logical_id,
    resource_type,
    provider,
    region,
    properties,
    protected,
    immutable_keys,
    created_by
)
VALUES
(
    1,
    1,
    2,
    'production-network',
    'network',
    'aws',
    'ap-south-1',
    '{
        "cidr": "10.20.0.0/16",
        "public": false
    }'::JSONB,
    TRUE,
    ARRAY['cidr'],
    1
),
(
    1,
    1,
    2,
    'application-server',
    'server',
    'aws',
    'ap-south-1',
    '{
        "cpu": 4,
        "memory_gb": 16,
        "image": "ubuntu-24.04",
        "public_ssh": false
    }'::JSONB,
    FALSE,
    ARRAY['image'],
    1
),
(
    1,
    1,
    2,
    'application-storage',
    'storage',
    'aws',
    'ap-south-1',
    '{
        "size_gb": 100,
        "encrypted": true,
        "versioning": true
    }'::JSONB,
    TRUE,
    ARRAY['encrypted'],
    1
),
(
    1,
    1,
    2,
    'application-firewall',
    'firewall',
    'aws',
    'ap-south-1',
    '{
        "default_action": "DENY",
        "allow_https": true,
        "allow_ssh": false
    }'::JSONB,
    FALSE,
    ARRAY[]::TEXT[],
    1
);

-- ============================================================
-- 24. RESOURCE DEPENDENCIES
-- ============================================================

INSERT INTO resource_dependencies (
    repository_id,
    environment_id,
    resource_id,
    depends_on_resource_id
)
VALUES
(
    1,
    2,
    2,
    1
),
(
    1,
    2,
    4,
    1
);

-- ============================================================
-- 25. SAMPLE ACTUAL INFRASTRUCTURE STATE
-- ============================================================

INSERT INTO infrastructure_state (
    resource_id,
    actual_properties,
    status,
    configuration_hash,
    observed_at,
    last_deployed_at,
    version
)
SELECT
    resource_id,
    CASE
        WHEN logical_id = 'application-server'
        THEN jsonb_set(
            properties,
            '{cpu}',
            '8'::JSONB
        )
        ELSE properties
    END,
    'active',
    MD5(properties::TEXT),
    NOW(),
    NOW(),
    1
FROM infrastructure_resources;

-- The application server has intentional drift:
-- desired CPU = 4, observed CPU = 8.

-- ============================================================
-- 26. SECURITY POLICIES
-- ============================================================

INSERT INTO infrastructure_policies (
    organization_id,
    policy_name,
    description,
    severity,
    resource_type,
    property_name,
    expected_value
)
VALUES
(
    1,
    'mandatory-storage-encryption',
    'All storage must use encryption',
    'critical',
    'storage',
    'encrypted',
    'true'::JSONB
),
(
    1,
    'firewall-default-deny',
    'Firewall must deny traffic by default',
    'critical',
    'firewall',
    'default_action',
    '"DENY"'::JSONB
),
(
    1,
    'server-ssh-restriction',
    'Public SSH must be disabled',
    'error',
    'server',
    'public_ssh',
    'false'::JSONB
);

-- ============================================================
-- 27. SAMPLE DEPLOYMENT PLAN
-- ============================================================

INSERT INTO deployment_plans (
    organization_id,
    repository_id,
    environment_id,
    created_by,
    plan_name,
    plan_hash,
    status,
    state_revision,
    expires_at
)
VALUES (
    1,
    1,
    2,
    2,
    'Production infrastructure reconciliation',
    MD5('production-infrastructure-plan-v1'),
    'planned',
    1,
    NOW() + INTERVAL '2 hours'
);

-- ============================================================
-- 28. SAMPLE PLAN ITEMS
--
-- CPU drift requires an update.
-- Other resources require no changes.
-- ============================================================

INSERT INTO deployment_plan_items (
    plan_id,
    repository_id,
    environment_id,
    resource_id,
    action,
    before_properties,
    after_properties,
    execution_order,
    reason
)
SELECT
    1,
    resource.repository_id,
    resource.environment_id,
    resource.resource_id,

    CASE
        WHEN state.state_id IS NULL THEN 'create'::deployment_action
        WHEN state.actual_properties
             IS DISTINCT FROM resource.properties
            THEN 'update'::deployment_action
        ELSE 'no_op'::deployment_action
    END,

    state.actual_properties,
    resource.properties,

    ROW_NUMBER() OVER (
        ORDER BY
            CASE resource.logical_id
                WHEN 'production-network' THEN 1
                WHEN 'application-storage' THEN 2
                WHEN 'application-server' THEN 3
                WHEN 'application-firewall' THEN 4
                ELSE 5
            END
    )::INTEGER,

    CASE
        WHEN state.state_id IS NULL
            THEN 'Missing actual infrastructure state'
        WHEN state.actual_properties
             IS DISTINCT FROM resource.properties
            THEN 'Drift detected between desired and actual state'
        ELSE 'Resource is already compliant'
    END

FROM infrastructure_resources resource

LEFT JOIN infrastructure_state state
    ON state.resource_id = resource.resource_id

WHERE resource.repository_id = 1
  AND resource.environment_id = 2;

-- ============================================================
-- 29. APPROVE PRODUCTION DEPLOYMENT
-- ============================================================

INSERT INTO deployment_approvals (
    plan_id,
    reviewer_id,
    decision,
    comments
)
VALUES (
    1,
    3,
    'approved',
    'Production security and infrastructure review completed'
);

COMMIT;

-- ============================================================
-- 30. RETRIEVAL QUERIES
-- ============================================================

-- Retrieve all declared infrastructure resources.

SELECT
    logical_id,
    resource_type,
    provider,
    region,
    properties,
    protected
FROM iac.infrastructure_resources
WHERE repository_id = 1
  AND environment_id = 2
ORDER BY logical_id;

-- Retrieve infrastructure dependencies.

SELECT
    resource.logical_id AS resource,
    dependency.logical_id AS depends_on
FROM iac.resource_dependencies relation

JOIN iac.infrastructure_resources resource
    ON resource.resource_id = relation.resource_id

JOIN iac.infrastructure_resources dependency
    ON dependency.resource_id = relation.depends_on_resource_id

ORDER BY resource.logical_id;

-- ============================================================
-- 31. VALIDATION QUERIES
-- ============================================================

-- Detect drift.

SELECT
    logical_id,
    drift_status,
    desired_properties,
    actual_properties
FROM iac.infrastructure_drift
WHERE environment_id = 2
ORDER BY logical_id;

-- Evaluate policy violations.

SELECT
    resource.logical_id,
    violations.policy_name,
    violations.severity,
    violations.violation
FROM iac.infrastructure_resources resource

CROSS JOIN LATERAL iac.evaluate_resource_policies(
    resource.resource_id
) violations

ORDER BY resource.logical_id;

-- ============================================================
-- 32. AGGREGATION AND REPORTING
-- ============================================================

-- Resource inventory by type and environment.

SELECT
    environment.environment_name,
    resource.resource_type,
    COUNT(*) AS resource_count,
    COUNT(*) FILTER (
        WHERE resource.protected
    ) AS protected_count
FROM iac.infrastructure_resources resource

JOIN iac.environments environment
    ON environment.environment_id = resource.environment_id

WHERE resource.enabled

GROUP BY
    environment.environment_name,
    resource.resource_type

ORDER BY
    environment.environment_name,
    resource.resource_type;

-- Deployment action statistics.

SELECT
    action,
    COUNT(*) AS total_actions
FROM iac.deployment_plan_items
WHERE plan_id = 1
GROUP BY action
ORDER BY action;

-- ============================================================
-- 33. CTE: RECURSIVE DEPENDENCY TRAVERSAL
-- ============================================================

WITH RECURSIVE dependency_tree AS (

    SELECT
        resource_id,
        depends_on_resource_id,
        1 AS depth
    FROM iac.resource_dependencies
    WHERE resource_id = 2

    UNION ALL

    SELECT
        dependency.resource_id,
        dependency.depends_on_resource_id,
        tree.depth + 1
    FROM iac.resource_dependencies dependency

    JOIN dependency_tree tree
        ON dependency.resource_id = tree.depends_on_resource_id
)

SELECT
    resource.logical_id,
    dependency.logical_id AS dependency,
    tree.depth
FROM dependency_tree tree

JOIN iac.infrastructure_resources resource
    ON resource.resource_id = tree.resource_id

JOIN iac.infrastructure_resources dependency
    ON dependency.resource_id = tree.depends_on_resource_id

ORDER BY tree.depth;

-- ============================================================
-- 34. DEPLOYMENT ELIGIBILITY
-- ============================================================

SELECT
    plan_id,
    plan_name,
    environment,
    approvals,
    rejections,
    eligible
FROM iac.deployment_eligibility
ORDER BY plan_id;

-- ============================================================
-- 35. WORKFLOW PROCESSING
--
-- The procedure runs within the caller's transaction.
-- The following call can be executed after checking eligibility.
--
-- Uncomment to execute the approved production plan:
--
-- CALL iac.execute_deployment_plan(1, 2);
--
-- For production use, invoke through an authorized service role
-- with restricted EXECUTE privileges and transaction handling.
-- ============================================================

-- ============================================================
-- 36. ADDITIONAL VALIDATION EXAMPLES
-- ============================================================

-- Find protected resources.

SELECT
    logical_id,
    resource_type,
    properties
FROM iac.infrastructure_resources
WHERE protected = TRUE;

-- Find failed infrastructure operations.

SELECT
    execution_id,
    plan_id,
    status,
    error_message,
    started_at,
    completed_at
FROM iac.deployment_executions
WHERE status = 'failed';

-- Infrastructure state version report.

SELECT
    resource.logical_id,
    state.version,
    state.status,
    state.observed_at,
    state.last_deployed_at
FROM iac.infrastructure_state state

JOIN iac.infrastructure_resources resource
    ON resource.resource_id = state.resource_id

ORDER BY state.version DESC;

-- Audit history.

SELECT
    audit.event_type,
    resource.logical_id,
    audit.user_id,
    audit.event_time,
    audit.old_value,
    audit.new_value
FROM iac.infrastructure_audit audit

LEFT JOIN iac.infrastructure_resources resource
    ON resource.resource_id = audit.resource_id

ORDER BY audit.event_time DESC;

-- ============================================================
-- 37. OPERATIONAL SECURITY
--
-- Suggested production permissions:
--
-- GRANT USAGE ON SCHEMA iac TO iac_operator;
--
-- GRANT SELECT ON ALL TABLES IN SCHEMA iac TO iac_auditor;
--
-- GRANT EXECUTE ON PROCEDURE
--     iac.execute_deployment_plan(BIGINT, BIGINT)
-- TO iac_operator;
--
-- Do not grant unrestricted UPDATE or DELETE permissions on
-- infrastructure declarations or audit history.
--
-- The application layer must also enforce authenticated user
-- identity, organization membership, and approval separation.
-- ============================================================

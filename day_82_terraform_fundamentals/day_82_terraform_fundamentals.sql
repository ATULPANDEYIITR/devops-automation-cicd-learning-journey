-- ============================================================
-- TERRAFORM FUNDAMENTALS
-- PostgreSQL Infrastructure Configuration and State Model
-- ============================================================
--
-- Demonstrates:
-- 1. Provider registration and configuration
-- 2. Typed input variables
-- 3. Resource declarations
-- 4. Resource dependencies
-- 5. Plans and planned changes
-- 6. Infrastructure state
-- 7. Outputs and resource references
-- 8. Apply operations and state transitions
-- 9. Validation and failure tracking
-- 10. Reporting and drift detection
--
-- Requires PostgreSQL 15 or later.
--
-- The database models a Terraform-like workflow. It does not
-- replace Terraform's provider protocol or actual infrastructure
-- provisioning engine.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS terraform_lab;

SET search_path TO terraform_lab, public;

-- ------------------------------------------------------------
-- 1. Enumerated domain types
-- ------------------------------------------------------------

CREATE TYPE provider_status AS ENUM (
    'active',
    'disabled',
    'error'
);

CREATE TYPE resource_status AS ENUM (
    'declared',
    'planned',
    'created',
    'updated',
    'destroyed',
    'failed'
);

CREATE TYPE plan_action AS ENUM (
    'create',
    'update',
    'no_change',
    'destroy'
);

CREATE TYPE apply_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'rolled_back'
);

CREATE TYPE variable_type AS ENUM (
    'string',
    'number',
    'boolean',
    'object',
    'list'
);

-- ------------------------------------------------------------
-- 2. Repositories and workspaces
-- ------------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_repository_name
        CHECK (repository_name ~ '^[a-zA-Z0-9_-]+$')
);

CREATE TABLE workspaces (
    workspace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    workspace_name VARCHAR(100) NOT NULL,
    environment VARCHAR(30) NOT NULL,
    state_revision BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, workspace_name),

    CHECK (environment IN (
        'development',
        'staging',
        'production'
    )),

    CHECK (state_revision >= 0)
);

CREATE INDEX idx_workspaces_environment
    ON workspaces(environment);

-- ------------------------------------------------------------
-- 3. Provider configurations
-- ------------------------------------------------------------

CREATE TABLE providers (
    provider_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    provider_name VARCHAR(80) NOT NULL,
    provider_version VARCHAR(30) NOT NULL,
    region VARCHAR(100) NOT NULL,
    authentication_method VARCHAR(40) NOT NULL,
    status provider_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (workspace_id, provider_name),

    CHECK (
        provider_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),

    CHECK (
        authentication_method IN (
            'environment',
            'workload_identity',
            'assume_role'
        )
    )
);

CREATE INDEX idx_providers_workspace_status
    ON providers(workspace_id, status);

-- Credentials are deliberately not stored in this table.
-- Use a secure external credential mechanism.

-- ------------------------------------------------------------
-- 4. Input variable definitions and values
-- ------------------------------------------------------------

CREATE TABLE variable_definitions (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    variable_name VARCHAR(100) NOT NULL,
    value_type variable_type NOT NULL,
    default_value JSONB,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    validation_rule TEXT,

    UNIQUE (workspace_id, variable_name),

    CHECK (
        NOT required OR default_value IS NULL OR
        jsonb_typeof(default_value) IS NOT NULL
    )
);

CREATE TABLE variable_values (
    variable_value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variable_id BIGINT NOT NULL
        REFERENCES variable_definitions(variable_id),
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    value JSONB NOT NULL,
    supplied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (variable_id, workspace_id),

    CHECK (jsonb_typeof(value) IS NOT NULL)
);

CREATE INDEX idx_variable_values_workspace
    ON variable_values(workspace_id);

-- ------------------------------------------------------------
-- 5. Resource declarations
-- ------------------------------------------------------------

CREATE TABLE resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    provider_id BIGINT NOT NULL
        REFERENCES providers(provider_id),
    resource_name VARCHAR(120) NOT NULL,
    resource_type VARCHAR(120) NOT NULL,
    desired_attributes JSONB NOT NULL,
    status resource_status NOT NULL DEFAULT 'declared',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (workspace_id, resource_type, resource_name),

    CHECK (
        resource_name ~ '^[a-z][a-z0-9_]*$'
    ),

    CHECK (
        resource_type ~ '^[a-z][a-z0-9_]*_[a-z][a-z0-9_]*$'
    ),

    CHECK (
        jsonb_typeof(desired_attributes) = 'object'
    )
);

CREATE INDEX idx_resources_workspace_status
    ON resources(workspace_id, status);

CREATE INDEX idx_resources_attributes
    ON resources USING GIN(desired_attributes);

-- ------------------------------------------------------------
-- 6. Explicit resource dependencies
-- ------------------------------------------------------------

CREATE TABLE resource_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id BIGINT NOT NULL
        REFERENCES resources(resource_id) ON DELETE CASCADE,
    depends_on_resource_id BIGINT NOT NULL
        REFERENCES resources(resource_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (resource_id, depends_on_resource_id),

    CHECK (resource_id <> depends_on_resource_id)
);

CREATE INDEX idx_dependencies_target
    ON resource_dependencies(depends_on_resource_id);

-- A resource dependency determines execution ordering.
-- The referenced resource must be available before its dependent.

-- ------------------------------------------------------------
-- 7. Infrastructure plans
-- ------------------------------------------------------------

CREATE TABLE infrastructure_plans (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    plan_number INTEGER NOT NULL,
    configuration_hash VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    UNIQUE (workspace_id, plan_number),

    CHECK (status IN (
        'created',
        'applied',
        'discarded',
        'failed'
    )),

    CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

CREATE INDEX idx_plans_workspace_created
    ON infrastructure_plans(workspace_id, created_at DESC);

CREATE TABLE plan_changes (
    plan_change_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL
        REFERENCES infrastructure_plans(plan_id) ON DELETE CASCADE,
    resource_id BIGINT NOT NULL
        REFERENCES resources(resource_id),
    action plan_action NOT NULL,
    before_attributes JSONB,
    after_attributes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (plan_id, resource_id),

    CHECK (
        action <> 'create' OR after_attributes IS NOT NULL
    ),

    CHECK (
        action <> 'update' OR
        (
            before_attributes IS NOT NULL AND
            after_attributes IS NOT NULL
        )
    ),

    CHECK (
        action <> 'destroy' OR before_attributes IS NOT NULL
    )
);

CREATE INDEX idx_plan_changes_action
    ON plan_changes(plan_id, action);

-- ------------------------------------------------------------
-- 8. Infrastructure state
-- ------------------------------------------------------------

CREATE TABLE infrastructure_state (
    state_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    resource_id BIGINT NOT NULL
        REFERENCES resources(resource_id),
    provider_resource_id VARCHAR(255) NOT NULL,
    actual_attributes JSONB NOT NULL,
    state_version BIGINT NOT NULL DEFAULT 1,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (workspace_id, resource_id),

    CHECK (state_version > 0),

    CHECK (jsonb_typeof(actual_attributes) = 'object')
);

CREATE INDEX idx_state_workspace
    ON infrastructure_state(workspace_id);

-- The state table records known infrastructure objects.
-- State is not the same as the desired resource configuration.

-- ------------------------------------------------------------
-- 9. Outputs
-- ------------------------------------------------------------

CREATE TABLE infrastructure_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(workspace_id),
    output_name VARCHAR(120) NOT NULL,
    resource_id BIGINT
        REFERENCES resources(resource_id),
    attribute_name VARCHAR(120) NOT NULL,
    sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,

    UNIQUE (workspace_id, output_name)
);

CREATE INDEX idx_outputs_workspace
    ON infrastructure_outputs(workspace_id);

-- ------------------------------------------------------------
-- 10. Apply execution history
-- ------------------------------------------------------------

CREATE TABLE apply_operations (
    apply_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL
        REFERENCES infrastructure_plans(plan_id),
    status apply_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,

    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    )
);

CREATE INDEX idx_apply_status
    ON apply_operations(status, started_at DESC);

-- ------------------------------------------------------------
-- 11. Provider and resource integrity triggers
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_resource_provider()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    provider_workspace BIGINT;
    provider_current_status provider_status;
BEGIN
    SELECT workspace_id, status
    INTO provider_workspace, provider_current_status
    FROM providers
    WHERE provider_id = NEW.provider_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Provider does not exist';
    END IF;

    IF provider_workspace <> NEW.workspace_id THEN
        RAISE EXCEPTION
            'Resource and provider must belong to the same workspace';
    END IF;

    IF provider_current_status <> 'active' THEN
        RAISE EXCEPTION 'Provider is not active';
    END IF;

    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_resource_provider
BEFORE INSERT OR UPDATE ON resources
FOR EACH ROW
EXECUTE FUNCTION validate_resource_provider();

-- ------------------------------------------------------------
-- 12. Variable validation function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_variable_value(
    p_variable_id BIGINT,
    p_value JSONB
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    definition variable_definitions%ROWTYPE;
    actual_type TEXT;
BEGIN
    SELECT *
    INTO definition
    FROM variable_definitions
    WHERE variable_id = p_variable_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown variable definition';
    END IF;

    actual_type := jsonb_typeof(p_value);

    IF actual_type IS NULL THEN
        RETURN FALSE;
    END IF;

    CASE definition.value_type
        WHEN 'string' THEN
            RETURN actual_type = 'string';

        WHEN 'number' THEN
            RETURN actual_type = 'number';

        WHEN 'boolean' THEN
            RETURN actual_type = 'boolean';

        WHEN 'object' THEN
            RETURN actual_type = 'object';

        WHEN 'list' THEN
            RETURN actual_type = 'array';

        ELSE
            RETURN FALSE;
    END CASE;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_variable_value()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT validate_variable_value(
        NEW.variable_id,
        NEW.value
    ) THEN
        RAISE EXCEPTION
            'Variable value does not match its declared type';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM variable_definitions vd
        WHERE vd.variable_id = NEW.variable_id
          AND vd.workspace_id = NEW.workspace_id
    ) THEN
        RAISE EXCEPTION
            'Variable definition belongs to another workspace';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_enforce_variable_value
BEFORE INSERT OR UPDATE ON variable_values
FOR EACH ROW
EXECUTE FUNCTION enforce_variable_value();

-- ------------------------------------------------------------
-- 13. Dependency validation
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_resource_dependency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_workspace BIGINT;
    target_workspace BIGINT;
BEGIN
    SELECT workspace_id
    INTO source_workspace
    FROM resources
    WHERE resource_id = NEW.resource_id;

    SELECT workspace_id
    INTO target_workspace
    FROM resources
    WHERE resource_id = NEW.depends_on_resource_id;

    IF source_workspace IS NULL OR target_workspace IS NULL THEN
        RAISE EXCEPTION 'Dependency references an unknown resource';
    END IF;

    IF source_workspace <> target_workspace THEN
        RAISE EXCEPTION
            'Cross-workspace resource dependencies are not permitted';
    END IF;

    IF EXISTS (
        WITH RECURSIVE dependency_tree(resource_id) AS (
            SELECT NEW.depends_on_resource_id

            UNION

            SELECT rd.depends_on_resource_id
            FROM resource_dependencies rd
            JOIN dependency_tree dt
              ON rd.resource_id = dt.resource_id
        )
        SELECT 1
        FROM dependency_tree
        WHERE resource_id = NEW.resource_id
    ) THEN
        RAISE EXCEPTION 'Circular resource dependency detected';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_resource_dependency
BEFORE INSERT OR UPDATE ON resource_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_resource_dependency();

-- ------------------------------------------------------------
-- 14. Eligibility evaluation
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_plan_change(
    p_plan_change_id BIGINT
)
RETURNS TABLE (
    resource_address TEXT,
    action plan_action,
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    change_record plan_changes%ROWTYPE;
    resource_record resources%ROWTYPE;
    current_provider_status provider_status;
BEGIN
    SELECT *
    INTO change_record
    FROM plan_changes
    WHERE plan_change_id = p_plan_change_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Plan change does not exist';
    END IF;

    SELECT *
    INTO resource_record
    FROM resources
    WHERE resource_id = change_record.resource_id;

    SELECT status
    INTO current_provider_status
    FROM providers
    WHERE provider_id = resource_record.provider_id;

    resource_address :=
        resource_record.resource_type || '.' ||
        resource_record.resource_name;

    action := change_record.action;

    IF current_provider_status <> 'active' THEN
        eligible := FALSE;
        reason := 'Provider is not active';
        RETURN NEXT;
        RETURN;
    END IF;

    IF change_record.action IN ('create', 'update') AND
       change_record.after_attributes IS NULL THEN
        eligible := FALSE;
        reason := 'Desired resource attributes are missing';
        RETURN NEXT;
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM resource_dependencies rd
        LEFT JOIN infrastructure_state s
          ON s.resource_id = rd.depends_on_resource_id
         AND s.workspace_id = resource_record.workspace_id
        WHERE rd.resource_id = resource_record.resource_id
          AND s.state_id IS NULL
    ) THEN
        eligible := FALSE;
        reason := 'One or more dependencies are not present in state';
        RETURN NEXT;
        RETURN;
    END IF;

    eligible := TRUE;
    reason := 'Provider and dependency conditions satisfied';

    RETURN NEXT;
END;
$$;

-- ------------------------------------------------------------
-- 15. Output resolution function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION resolve_output(
    p_workspace_id BIGINT,
    p_output_name VARCHAR
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    output_record infrastructure_outputs%ROWTYPE;
    result JSONB;
BEGIN
    SELECT *
    INTO output_record
    FROM infrastructure_outputs
    WHERE workspace_id = p_workspace_id
      AND output_name = p_output_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Output does not exist: %', p_output_name;
    END IF;

    SELECT s.actual_attributes -> output_record.attribute_name
    INTO result
    FROM infrastructure_state s
    WHERE s.workspace_id = p_workspace_id
      AND s.resource_id = output_record.resource_id;

    IF result IS NULL THEN
        RAISE EXCEPTION
            'Output resource or referenced attribute is unavailable';
    END IF;

    IF output_record.sensitive THEN
        RETURN '"[REDACTED]"'::JSONB;
    END IF;

    RETURN result;
END;
$$;

-- ------------------------------------------------------------
-- 16. Reporting views
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW workspace_resource_report AS
SELECT
    w.workspace_id,
    r.repository_name,
    w.workspace_name,
    w.environment,
    COUNT(DISTINCT res.resource_id) AS declared_resources,
    COUNT(DISTINCT s.state_id) AS resources_in_state,
    COUNT(DISTINCT CASE
        WHEN res.status = 'failed' THEN res.resource_id
    END) AS failed_resources
FROM workspaces w
JOIN repositories r
    ON r.repository_id = w.repository_id
LEFT JOIN resources res
    ON res.workspace_id = w.workspace_id
LEFT JOIN infrastructure_state s
    ON s.resource_id = res.resource_id
   AND s.workspace_id = w.workspace_id
GROUP BY
    w.workspace_id,
    r.repository_name,
    w.workspace_name,
    w.environment;

CREATE OR REPLACE VIEW infrastructure_drift_report AS
SELECT
    r.resource_id,
    r.workspace_id,
    r.resource_type || '.' || r.resource_name AS resource_address,
    r.desired_attributes,
    s.actual_attributes,
    CASE
        WHEN s.state_id IS NULL THEN 'missing_state'
        WHEN r.desired_attributes = s.actual_attributes THEN 'in_sync'
        ELSE 'configuration_difference'
    END AS drift_status
FROM resources r
LEFT JOIN infrastructure_state s
    ON s.resource_id = r.resource_id
   AND s.workspace_id = r.workspace_id;

-- ------------------------------------------------------------
-- 17. Sample repository and workspaces
-- ------------------------------------------------------------

INSERT INTO repositories (
    repository_name,
    description
)
VALUES (
    'cloud-platform-infrastructure',
    'Application networking and compute infrastructure'
);

INSERT INTO workspaces (
    repository_id,
    workspace_name,
    environment
)
SELECT repository_id, 'development', 'development'
FROM repositories
WHERE repository_name = 'cloud-platform-infrastructure';

INSERT INTO workspaces (
    repository_id,
    workspace_name,
    environment
)
SELECT repository_id, 'production', 'production'
FROM repositories
WHERE repository_name = 'cloud-platform-infrastructure';

-- ------------------------------------------------------------
-- 18. Provider records
-- ------------------------------------------------------------

INSERT INTO providers (
    workspace_id,
    provider_name,
    provider_version,
    region,
    authentication_method
)
SELECT
    workspace_id,
    'aws',
    '5.80.0',
    'ap-south-1',
    'workload_identity'
FROM workspaces
WHERE workspace_name IN ('development', 'production');

-- ------------------------------------------------------------
-- 19. Input variable definitions
-- ------------------------------------------------------------

INSERT INTO variable_definitions (
    workspace_id,
    variable_name,
    value_type,
    default_value,
    required,
    sensitive,
    validation_rule
)
SELECT
    workspace_id,
    'environment',
    'string',
    to_jsonb(environment),
    FALSE,
    FALSE,
    'development, staging, or production'
FROM workspaces;

INSERT INTO variable_definitions (
    workspace_id,
    variable_name,
    value_type,
    default_value,
    required,
    sensitive,
    validation_rule
)
SELECT
    workspace_id,
    'instance_count',
    'number',
    '2'::JSONB,
    FALSE,
    FALSE,
    'integer between 1 and 10'
FROM workspaces
WHERE workspace_name = 'development';

INSERT INTO variable_definitions (
    workspace_id,
    variable_name,
    value_type,
    default_value,
    required,
    sensitive,
    validation_rule
)
SELECT
    workspace_id,
    'instance_type',
    'string',
    '"t3.small"'::JSONB,
    FALSE,
    FALSE,
    'valid cloud instance type'
FROM workspaces
WHERE workspace_name = 'development';

INSERT INTO variable_definitions (
    workspace_id,
    variable_name,
    value_type,
    default_value,
    required,
    sensitive,
    validation_rule
)
SELECT
    workspace_id,
    'database_password',
    'string',
    NULL,
    TRUE,
    TRUE,
    'minimum 12 characters'
FROM workspaces
WHERE workspace_name = 'development';

-- ------------------------------------------------------------
-- 20. Resource declarations
-- ------------------------------------------------------------

INSERT INTO resources (
    workspace_id,
    provider_id,
    resource_name,
    resource_type,
    desired_attributes
)
SELECT
    w.workspace_id,
    p.provider_id,
    'network',
    'aws_vpc',
    '{
        "cidr_block": "10.0.0.0/16",
        "environment": "development"
    }'::JSONB
FROM workspaces w
JOIN providers p
    ON p.workspace_id = w.workspace_id
WHERE w.workspace_name = 'development';

INSERT INTO resources (
    workspace_id,
    provider_id,
    resource_name,
    resource_type,
    desired_attributes
)
SELECT
    w.workspace_id,
    p.provider_id,
    'application',
    'aws_instance',
    '{
        "instance_type": "t3.small",
        "instance_count": 2,
        "environment": "development"
    }'::JSONB
FROM workspaces w
JOIN providers p
    ON p.workspace_id = w.workspace_id
WHERE w.workspace_name = 'development';

INSERT INTO resources (
    workspace_id,
    provider_id,
    resource_name,
    resource_type,
    desired_attributes
)
SELECT
    w.workspace_id,
    p.provider_id,
    'database',
    'aws_db_instance',
    '{
        "engine": "postgres",
        "password_configured": true,
        "environment": "development"
    }'::JSONB
FROM workspaces w
JOIN providers p
    ON p.workspace_id = w.workspace_id
WHERE w.workspace_name = 'development';

-- ------------------------------------------------------------
-- 21. Resource dependency declarations
-- ------------------------------------------------------------

INSERT INTO resource_dependencies (
    resource_id,
    depends_on_resource_id
)
SELECT application.resource_id, network.resource_id
FROM resources application
JOIN resources network
    ON network.workspace_id = application.workspace_id
WHERE application.resource_name = 'application'
  AND network.resource_name = 'network';

INSERT INTO resource_dependencies (
    resource_id,
    depends_on_resource_id
)
SELECT database.resource_id, network.resource_id
FROM resources database
JOIN resources network
    ON network.workspace_id = database.workspace_id
WHERE database.resource_name = 'database'
  AND network.resource_name = 'network';

-- ------------------------------------------------------------
-- 22. Input values
-- ------------------------------------------------------------

INSERT INTO variable_values (
    variable_id,
    workspace_id,
    value
)
SELECT
    variable_id,
    workspace_id,
    '"development"'::JSONB
FROM variable_definitions
WHERE variable_name = 'environment'
  AND workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

INSERT INTO variable_values (
    variable_id,
    workspace_id,
    value
)
SELECT
    variable_id,
    workspace_id,
    '2'::JSONB
FROM variable_definitions
WHERE variable_name = 'instance_count'
  AND workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

INSERT INTO variable_values (
    variable_id,
    workspace_id,
    value
)
SELECT
    variable_id,
    workspace_id,
    '"t3.small"'::JSONB
FROM variable_definitions
WHERE variable_name = 'instance_type'
  AND workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

-- Sensitive values are not inserted into the demonstration database.

-- ------------------------------------------------------------
-- 23. Create a sample infrastructure plan
-- ------------------------------------------------------------

INSERT INTO infrastructure_plans (
    workspace_id,
    plan_number,
    configuration_hash,
    status
)
SELECT
    workspace_id,
    1,
    'sha256:development-configuration-001',
    'created'
FROM workspaces
WHERE workspace_name = 'development';

INSERT INTO plan_changes (
    plan_id,
    resource_id,
    action,
    before_attributes,
    after_attributes
)
SELECT
    p.plan_id,
    r.resource_id,
    'create',
    NULL,
    r.desired_attributes
FROM infrastructure_plans p
JOIN resources r
    ON r.workspace_id = p.workspace_id
WHERE p.plan_number = 1
  AND p.workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

-- ------------------------------------------------------------
-- 24. Apply simulation with transactional state updates
-- ------------------------------------------------------------

SAVEPOINT before_infrastructure_apply;

INSERT INTO apply_operations (
    plan_id,
    status,
    started_at
)
SELECT
    plan_id,
    'running',
    NOW()
FROM infrastructure_plans
WHERE plan_number = 1
  AND workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

INSERT INTO infrastructure_state (
    workspace_id,
    resource_id,
    provider_resource_id,
    actual_attributes
)
SELECT
    r.workspace_id,
    r.resource_id,
    'cloud-' || r.resource_type || '-' || r.resource_name,
    r.desired_attributes
FROM resources r
JOIN plan_changes pc
    ON pc.resource_id = r.resource_id
JOIN infrastructure_plans p
    ON p.plan_id = pc.plan_id
WHERE p.plan_number = 1
  AND p.workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  )
  AND pc.action = 'create'
ON CONFLICT (workspace_id, resource_id)
DO UPDATE SET
    actual_attributes = EXCLUDED.actual_attributes,
    state_version =
        infrastructure_state.state_version + 1,
    last_updated = NOW();

UPDATE resources
SET status = 'created',
    updated_at = NOW()
WHERE workspace_id = (
    SELECT workspace_id
    FROM workspaces
    WHERE workspace_name = 'development'
);

UPDATE infrastructure_plans
SET status = 'applied'
WHERE plan_number = 1
  AND workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

UPDATE apply_operations
SET status = 'succeeded',
    completed_at = NOW()
WHERE status = 'running'
  AND plan_id = (
      SELECT plan_id
      FROM infrastructure_plans
      WHERE plan_number = 1
        AND workspace_id = (
            SELECT workspace_id
            FROM workspaces
            WHERE workspace_name = 'development'
        )
  );

UPDATE workspaces
SET state_revision = state_revision + 1
WHERE workspace_name = 'development';

RELEASE SAVEPOINT before_infrastructure_apply;

-- ------------------------------------------------------------
-- 25. Define output references
-- ------------------------------------------------------------

INSERT INTO infrastructure_outputs (
    workspace_id,
    output_name,
    resource_id,
    attribute_name,
    sensitive,
    description
)
SELECT
    r.workspace_id,
    'network_cidr',
    r.resource_id,
    'cidr_block',
    FALSE,
    'VPC network address range'
FROM resources r
WHERE r.resource_name = 'network'
  AND r.workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

INSERT INTO infrastructure_outputs (
    workspace_id,
    output_name,
    resource_id,
    attribute_name,
    sensitive,
    description
)
SELECT
    r.workspace_id,
    'instance_type',
    r.resource_id,
    'instance_type',
    FALSE,
    'Application compute instance type'
FROM resources r
WHERE r.resource_name = 'application'
  AND r.workspace_id = (
      SELECT workspace_id
      FROM workspaces
      WHERE workspace_name = 'development'
  );

-- ------------------------------------------------------------
-- 26. Retrieval queries
-- ------------------------------------------------------------

-- Provider configuration for each workspace.
SELECT
    w.workspace_name,
    p.provider_name,
    p.provider_version,
    p.region,
    p.status
FROM workspaces w
JOIN providers p
    ON p.workspace_id = w.workspace_id
ORDER BY w.workspace_name;

-- Resource declarations and provider relationships.
SELECT
    r.resource_type || '.' || r.resource_name AS resource_address,
    p.provider_name,
    r.desired_attributes,
    r.status
FROM resources r
JOIN providers p
    ON p.provider_id = r.provider_id
ORDER BY r.resource_type, r.resource_name;

-- Resource dependency relationships.
SELECT
    dependent.resource_type || '.' || dependent.resource_name
        AS dependent_resource,
    dependency.resource_type || '.' || dependency.resource_name
        AS prerequisite_resource
FROM resource_dependencies rd
JOIN resources dependent
    ON dependent.resource_id = rd.resource_id
JOIN resources dependency
    ON dependency.resource_id = rd.depends_on_resource_id;

-- ------------------------------------------------------------
-- 27. Variable evaluation and validation query
-- ------------------------------------------------------------

SELECT
    vd.variable_name,
    vd.value_type,
    vd.required,
    vd.sensitive,
    COALESCE(
        vv.value,
        vd.default_value
    ) AS resolved_value,
    CASE
        WHEN vv.variable_value_id IS NULL
             AND vd.default_value IS NULL
             AND vd.required
        THEN 'missing_required_value'

        WHEN vv.variable_value_id IS NOT NULL
             AND NOT validate_variable_value(
                 vd.variable_id,
                 vv.value
             )
        THEN 'invalid_type'

        ELSE 'valid'
    END AS validation_status
FROM variable_definitions vd
LEFT JOIN variable_values vv
    ON vv.variable_id = vd.variable_id
   AND vv.workspace_id = vd.workspace_id
WHERE vd.workspace_id = (
    SELECT workspace_id
    FROM workspaces
    WHERE workspace_name = 'development'
)
ORDER BY vd.variable_name;

-- ------------------------------------------------------------
-- 28. Plan evaluation
-- ------------------------------------------------------------

SELECT
    pc.plan_change_id,
    r.resource_type || '.' || r.resource_name AS resource_address,
    pc.action,
    pc.before_attributes,
    pc.after_attributes,
    evaluation.eligible,
    evaluation.reason
FROM plan_changes pc
JOIN resources r
    ON r.resource_id = pc.resource_id
CROSS JOIN LATERAL evaluate_plan_change(
    pc.plan_change_id
) AS evaluation
ORDER BY pc.plan_change_id;

-- ------------------------------------------------------------
-- 29. Output retrieval
-- ------------------------------------------------------------

SELECT
    output_name,
    resolve_output(workspace_id, output_name) AS output_value
FROM infrastructure_outputs
WHERE workspace_id = (
    SELECT workspace_id
    FROM workspaces
    WHERE workspace_name = 'development'
)
ORDER BY output_name;

-- ------------------------------------------------------------
-- 30. Resource aggregation and reporting
-- ------------------------------------------------------------

SELECT *
FROM workspace_resource_report
ORDER BY workspace_name;

-- ------------------------------------------------------------
-- 31. Drift detection
-- ------------------------------------------------------------

SELECT
    resource_address,
    drift_status,
    desired_attributes,
    actual_attributes
FROM infrastructure_drift_report
WHERE workspace_id = (
    SELECT workspace_id
    FROM workspaces
    WHERE workspace_name = 'development'
)
ORDER BY resource_address;

-- ------------------------------------------------------------
-- 32. Resource eligibility and dependency readiness
-- ------------------------------------------------------------

SELECT
    r.resource_type || '.' || r.resource_name AS resource_address,
    CASE
        WHEN p.status <> 'active'
        THEN FALSE

        WHEN EXISTS (
            SELECT 1
            FROM resource_dependencies rd
            LEFT JOIN infrastructure_state s
                ON s.resource_id = rd.depends_on_resource_id
               AND s.workspace_id = r.workspace_id
            WHERE rd.resource_id = r.resource_id
              AND s.state_id IS NULL
        )
        THEN FALSE

        ELSE TRUE
    END AS execution_eligible
FROM resources r
JOIN providers p
    ON p.provider_id = r.provider_id
WHERE r.workspace_id = (
    SELECT workspace_id
    FROM workspaces
    WHERE workspace_name = 'development'
)
ORDER BY resource_address;

-- ------------------------------------------------------------
-- 33. Demonstrate rejected variable values
-- ------------------------------------------------------------

DO $$
DECLARE
    password_variable_id BIGINT;
    development_workspace_id BIGINT;
BEGIN
    SELECT workspace_id
    INTO development_workspace_id
    FROM workspaces
    WHERE workspace_name = 'development';

    SELECT variable_id
    INTO password_variable_id
    FROM variable_definitions
    WHERE workspace_id = development_workspace_id
      AND variable_name = 'database_password';

    IF validate_variable_value(
        password_variable_id,
        '12345'::JSONB
    ) THEN
        RAISE EXCEPTION 'Unexpected validation result';
    ELSE
        RAISE NOTICE
            'Expected: database_password has a valid JSON type, '
            'but its minimum-length policy requires separate validation';
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 34. Demonstrate dependency cycle rejection
-- ------------------------------------------------------------

-- A self-dependency is rejected by a CHECK constraint.
-- A multi-resource cycle is rejected by the dependency trigger.
--
-- The following block tests the rejection without terminating
-- the complete demonstration transaction.

DO $$
DECLARE
    application_id BIGINT;
    database_id BIGINT;
BEGIN
    SELECT resource_id
    INTO application_id
    FROM resources
    WHERE resource_name = 'application'
      AND workspace_id = (
          SELECT workspace_id
          FROM workspaces
          WHERE workspace_name = 'development'
      );

    SELECT resource_id
    INTO database_id
    FROM resources
    WHERE resource_name = 'database'
      AND workspace_id = (
          SELECT workspace_id
          FROM workspaces
          WHERE workspace_name = 'development'
      );

    BEGIN
        INSERT INTO resource_dependencies (
            resource_id,
            depends_on_resource_id
        )
        VALUES (
            database_id,
            application_id
        );

        INSERT INTO resource_dependencies (
            resource_id,
            depends_on_resource_id
        )
        VALUES (
            application_id,
            database_id
        );

    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE
            'Expected dependency-cycle rejection: %',
            SQLERRM;
    END;
END;
$$;

-- ------------------------------------------------------------
-- 35. Final operational report
-- ------------------------------------------------------------

SELECT
    w.workspace_name,
    w.environment,
    w.state_revision,
    COUNT(DISTINCT r.resource_id) AS declared_resources,
    COUNT(DISTINCT s.state_id) AS tracked_resources,
    COUNT(DISTINCT p.plan_id) AS plans,
    COUNT(DISTINCT ao.apply_id) AS apply_operations
FROM workspaces w
LEFT JOIN resources r
    ON r.workspace_id = w.workspace_id
LEFT JOIN infrastructure_state s
    ON s.workspace_id = w.workspace_id
LEFT JOIN infrastructure_plans p
    ON p.workspace_id = w.workspace_id
LEFT JOIN plan_changes pc
    ON pc.plan_id = p.plan_id
LEFT JOIN apply_operations ao
    ON ao.plan_id = p.plan_id
GROUP BY
    w.workspace_id,
    w.workspace_name,
    w.environment,
    w.state_revision
ORDER BY w.workspace_name;

COMMIT;

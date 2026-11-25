-- ============================================================
-- TERRAFORM AUTOMATION INTEGRATED WITH CI/CD
-- PostgreSQL 15+
--
-- Enterprise infrastructure delivery database.
--
-- Models:
-- Repositories
-- Branches
-- Commits
-- Infrastructure deployments
-- Terraform plans
-- Resource changes
-- Reviewers
-- Reviews
-- Approval requirements
-- Automated status checks
-- Security findings
-- Deployment locks
-- Pipeline executions
-- Audit events
-- Merge and deployment eligibility
--
-- Execute in a dedicated database.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS terraform_ci;

SET search_path TO terraform_ci, public;

-- ============================================================
-- 1. ENUMERATED DOMAIN TYPES
-- ============================================================

CREATE TYPE environment_type AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE pipeline_status AS ENUM (
    'created',
    'validating',
    'initializing',
    'planning',
    'security_scanning',
    'review_pending',
    'applying',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TYPE review_decision AS ENUM (
    'approved',
    'rejected',
    'commented'
);

CREATE TYPE check_status AS ENUM (
    'pending',
    'passed',
    'failed',
    'skipped'
);

CREATE TYPE change_action AS ENUM (
    'create',
    'update',
    'delete'
);

CREATE TYPE finding_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'rolled_back'
);

-- ============================================================
-- 2. REPOSITORY MANAGEMENT
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_name VARCHAR(150) NOT NULL UNIQUE,

    owner_name VARCHAR(150) NOT NULL,

    default_branch VARCHAR(150) NOT NULL DEFAULT 'main',

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT repository_name_valid
        CHECK (
            repository_name ~ '^[a-zA-Z0-9_.-]+$'
        )
);

-- ============================================================
-- 3. BRANCHES
-- ============================================================

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_name VARCHAR(200) NOT NULL,

    latest_commit_sha CHAR(40),

    is_protected BOOLEAN NOT NULL DEFAULT FALSE,

    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, branch_name),

    CONSTRAINT branch_name_not_empty
        CHECK (LENGTH(TRIM(branch_name)) > 0)
);

CREATE INDEX idx_branches_repository
    ON branches(repository_id);

CREATE INDEX idx_branches_protected
    ON branches(repository_id, is_protected)
    WHERE is_protected = TRUE;

-- ============================================================
-- 4. COMMITS
-- ============================================================

CREATE TABLE commits (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    commit_sha CHAR(40) NOT NULL,

    author_name VARCHAR(150) NOT NULL,

    commit_message TEXT NOT NULL,

    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, commit_sha),

    CONSTRAINT commit_sha_valid
        CHECK (commit_sha ~ '^[a-fA-F0-9]{40}$')
);

CREATE INDEX idx_commits_repository_date
    ON commits(repository_id, committed_at DESC);

-- ============================================================
-- 5. TERRAFORM PROJECTS
-- ============================================================

CREATE TABLE terraform_projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    project_name VARCHAR(150) NOT NULL,

    working_directory TEXT NOT NULL,

    terraform_version VARCHAR(30) NOT NULL,

    backend_type VARCHAR(50) NOT NULL,

    state_key TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, project_name),

    UNIQUE(backend_type, state_key),

    CHECK (LENGTH(TRIM(working_directory)) > 0)
);

-- ============================================================
-- 6. REVIEWERS
-- ============================================================

CREATE TABLE reviewers (
    reviewer_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    username VARCHAR(100) NOT NULL UNIQUE,

    full_name VARCHAR(150) NOT NULL,

    role_name VARCHAR(80) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    is_authorized BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 7. BRANCH PROTECTION POLICIES
-- ============================================================

CREATE TABLE branch_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id),

    require_pull_request BOOLEAN NOT NULL DEFAULT TRUE,

    require_approvals BOOLEAN NOT NULL DEFAULT TRUE,

    required_approvals INTEGER NOT NULL DEFAULT 1,

    dismiss_stale_approvals BOOLEAN NOT NULL DEFAULT TRUE,

    require_code_owner_review BOOLEAN NOT NULL DEFAULT FALSE,

    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,

    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,

    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,

    require_up_to_date_branch BOOLEAN NOT NULL DEFAULT TRUE,

    prohibit_direct_push BOOLEAN NOT NULL DEFAULT TRUE,

    prohibit_force_push BOOLEAN NOT NULL DEFAULT TRUE,

    prohibit_branch_deletion BOOLEAN NOT NULL DEFAULT TRUE,

    administrator_bypass_allowed BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (required_approvals >= 0)
);

-- ============================================================
-- 8. APPROVAL REQUIREMENTS
-- ============================================================

CREATE TABLE approval_requirements (
    requirement_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id),

    required_role VARCHAR(80) NOT NULL,

    required_count INTEGER NOT NULL DEFAULT 1,

    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE(policy_id, required_role),

    CHECK (required_count >= 0)
);

-- ============================================================
-- 9. PULL REQUESTS
-- ============================================================

CREATE TABLE pull_requests (
    pull_request_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    created_by BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),

    title VARCHAR(250) NOT NULL,

    description TEXT,

    is_draft BOOLEAN NOT NULL DEFAULT TRUE,

    is_open BOOLEAN NOT NULL DEFAULT TRUE,

    is_merged BOOLEAN NOT NULL DEFAULT FALSE,

    source_commit_sha CHAR(40),

    target_commit_sha CHAR(40),

    base_synchronized BOOLEAN NOT NULL DEFAULT FALSE,

    has_merge_conflicts BOOLEAN NOT NULL DEFAULT FALSE,

    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    merged_at TIMESTAMPTZ,

    CHECK (source_branch_id <> target_branch_id),

    CHECK (
        NOT is_merged OR
        (NOT is_open AND merged_at IS NOT NULL)
    )
);

CREATE INDEX idx_pull_requests_repository
    ON pull_requests(repository_id, created_at DESC);

CREATE INDEX idx_pull_requests_open
    ON pull_requests(repository_id, created_at DESC)
    WHERE is_open = TRUE;

CREATE INDEX idx_pull_requests_target
    ON pull_requests(target_branch_id, is_open);

-- ============================================================
-- 10. TERRAFORM PIPELINE RUNS
-- ============================================================

CREATE TABLE pipeline_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES terraform_projects(project_id),

    pull_request_id BIGINT
        REFERENCES pull_requests(pull_request_id),

    environment environment_type NOT NULL,

    status pipeline_status NOT NULL DEFAULT 'created',

    triggered_by BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),

    source_commit_sha CHAR(40) NOT NULL,

    configuration_hash CHAR(64),

    pipeline_started_at TIMESTAMPTZ,

    pipeline_completed_at TIMESTAMPTZ,

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        configuration_hash IS NULL OR
        configuration_hash ~ '^[a-fA-F0-9]{64}$'
    ),

    CHECK (
        pipeline_completed_at IS NULL OR
        pipeline_started_at IS NOT NULL
    )
);

CREATE INDEX idx_pipeline_project_status
    ON pipeline_runs(project_id, status);

CREATE INDEX idx_pipeline_environment
    ON pipeline_runs(environment, created_at DESC);

CREATE INDEX idx_pipeline_pull_request
    ON pipeline_runs(pull_request_id, created_at DESC);

-- ============================================================
-- 11. TERRAFORM PLANS
-- ============================================================

CREATE TABLE terraform_plans (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    run_id BIGINT NOT NULL UNIQUE
        REFERENCES pipeline_runs(run_id),

    artifact_path TEXT NOT NULL,

    artifact_checksum CHAR(64) NOT NULL,

    source_commit_sha CHAR(40) NOT NULL,

    additions INTEGER NOT NULL DEFAULT 0,

    modifications INTEGER NOT NULL DEFAULT 0,

    destructions INTEGER NOT NULL DEFAULT 0,

    is_approved BOOLEAN NOT NULL DEFAULT FALSE,

    is_applied BOOLEAN NOT NULL DEFAULT FALSE,

    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    applied_at TIMESTAMPTZ,

    CHECK (additions >= 0),

    CHECK (modifications >= 0),

    CHECK (destructions >= 0),

    CHECK (artifact_checksum ~ '^[a-fA-F0-9]{64}$'),

    CHECK (
        NOT is_applied OR
        (is_approved AND applied_at IS NOT NULL)
    )
);

-- ============================================================
-- 12. RESOURCE CHANGES
-- ============================================================

CREATE TABLE resource_changes (
    change_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    plan_id BIGINT NOT NULL
        REFERENCES terraform_plans(plan_id),

    resource_address TEXT NOT NULL,

    resource_type VARCHAR(150) NOT NULL,

    action change_action NOT NULL,

    encryption_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    public_ingress_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE(plan_id, resource_address)
);

CREATE INDEX idx_resource_changes_plan
    ON resource_changes(plan_id);

CREATE INDEX idx_resource_changes_action
    ON resource_changes(plan_id, action);

-- ============================================================
-- 13. REVIEWS AND APPROVAL DECISIONS
-- ============================================================

CREATE TABLE reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id),

    reviewer_id BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),

    decision review_decision NOT NULL,

    reviewed_commit_sha CHAR(40),

    is_dismissed BOOLEAN NOT NULL DEFAULT FALSE,

    dismissal_reason TEXT,

    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(pull_request_id, reviewer_id)
);

CREATE INDEX idx_reviews_pull_request
    ON reviews(pull_request_id, decision)
    WHERE is_dismissed = FALSE;

-- ============================================================
-- 14. REVIEW COMMENTS
-- ============================================================

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id),

    file_path TEXT NOT NULL,

    line_number INTEGER,

    comment_body TEXT NOT NULL,

    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    resolved_at TIMESTAMPTZ,

    CHECK (line_number IS NULL OR line_number > 0),

    CHECK (
        NOT is_resolved OR resolved_at IS NOT NULL
    )
);

CREATE INDEX idx_review_comments_unresolved
    ON review_comments(review_id)
    WHERE is_resolved = FALSE;

-- ============================================================
-- 15. STATUS CHECKS
-- ============================================================

CREATE TABLE status_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id),

    check_name VARCHAR(150) NOT NULL,

    status check_status NOT NULL DEFAULT 'pending',

    details TEXT,

    execution_time_ms BIGINT,

    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(run_id, check_name),

    CHECK (
        execution_time_ms IS NULL OR
        execution_time_ms >= 0
    )
);

CREATE INDEX idx_status_checks_run
    ON status_checks(run_id, status);

-- ============================================================
-- 16. SECURITY FINDINGS
-- ============================================================

CREATE TABLE security_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id),

    resource_address TEXT,

    scanner_name VARCHAR(100) NOT NULL,

    rule_id VARCHAR(100) NOT NULL,

    severity finding_severity NOT NULL,

    description TEXT NOT NULL,

    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_security_findings_severity
    ON security_findings(run_id, severity)
    WHERE is_resolved = FALSE;

-- ============================================================
-- 17. DEPLOYMENTS
-- ============================================================

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id),

    plan_id BIGINT NOT NULL
        REFERENCES terraform_plans(plan_id),

    environment environment_type NOT NULL,

    status deployment_status NOT NULL DEFAULT 'pending',

    initiated_by BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    UNIQUE(run_id),

    CHECK (
        completed_at IS NULL OR
        started_at IS NOT NULL
    )
);

CREATE INDEX idx_deployments_environment
    ON deployments(environment, status);

-- ============================================================
-- 18. STATE LOCKS
-- ============================================================

CREATE TABLE state_locks (
    lock_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES terraform_projects(project_id),

    environment environment_type NOT NULL,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id),

    lock_owner VARCHAR(150) NOT NULL,

    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, environment)
);

-- ============================================================
-- 19. AUDIT EVENTS
-- ============================================================

CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    run_id BIGINT
        REFERENCES pipeline_runs(run_id),

    actor_id BIGINT
        REFERENCES reviewers(reviewer_id),

    event_type VARCHAR(100) NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_run_date
    ON audit_events(run_id, created_at DESC);

CREATE INDEX idx_audit_event_type
    ON audit_events(event_type, created_at DESC);

-- ============================================================
-- 20. BRANCH PROTECTION INTEGRITY TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_branch_protection()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_protected AND NOT NEW.is_protected THEN
        RAISE EXCEPTION
            'Protected branch status cannot be removed through this operation';
    END IF;

    IF OLD.is_protected AND NEW.allow_force_push THEN
        RAISE EXCEPTION
            'Force push is prohibited for protected branches';
    END IF;

    IF OLD.is_protected AND NEW.allow_deletion THEN
        RAISE EXCEPTION
            'Deletion is prohibited for protected branches';
    END IF;

    IF OLD.is_protected AND NEW.allow_direct_push THEN
        RAISE EXCEPTION
            'Direct push is prohibited for protected branches';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_branch_protection
BEFORE UPDATE ON branches
FOR EACH ROW
EXECUTE FUNCTION enforce_branch_protection();

-- ============================================================
-- 21. REVIEWER ELIGIBILITY TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_review_submission()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    reviewer_record reviewers%ROWTYPE;
    requester_id BIGINT;
    current_source_commit CHAR(40);
BEGIN
    SELECT *
    INTO reviewer_record
    FROM reviewers
    WHERE reviewer_id = NEW.reviewer_id
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Reviewer does not exist';
    END IF;

    IF NOT reviewer_record.is_active OR
       NOT reviewer_record.is_authorized THEN
        RAISE EXCEPTION
            'Reviewer is inactive or unauthorized';
    END IF;

    SELECT created_by, source_commit_sha
    INTO requester_id, current_source_commit
    FROM pull_requests
    WHERE pull_request_id = NEW.pull_request_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pull Request does not exist';
    END IF;

    IF reviewer_record.reviewer_id = requester_id THEN
        RAISE EXCEPTION 'Self-approval is prohibited';
    END IF;

    IF NEW.decision = 'approved' AND
       NEW.reviewed_commit_sha IS DISTINCT FROM
       current_source_commit THEN

        RAISE EXCEPTION
            'Approval must reference the current source commit';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_review_eligibility
BEFORE INSERT OR UPDATE ON reviews
FOR EACH ROW
EXECUTE FUNCTION validate_review_submission();

-- ============================================================
-- 22. AUDIT TRIGGER FOR PIPELINE STATUS
-- ============================================================

CREATE OR REPLACE FUNCTION audit_pipeline_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO audit_events (
            run_id,
            event_type,
            event_details
        )
        VALUES (
            NEW.run_id,
            'pipeline_status_changed',
            jsonb_build_object(
                'previous_status', OLD.status,
                'new_status', NEW.status
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pipeline_status_audit
AFTER UPDATE OF status ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION audit_pipeline_status();

-- ============================================================
-- 23. PLAN RESOURCE COUNT VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_plan_resource_counts()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_additions INTEGER;
    actual_updates INTEGER;
    actual_deletions INTEGER;
BEGIN
    SELECT
        COUNT(*) FILTER (WHERE action = 'create'),
        COUNT(*) FILTER (WHERE action = 'update'),
        COUNT(*) FILTER (WHERE action = 'delete')
    INTO
        actual_additions,
        actual_updates,
        actual_deletions
    FROM resource_changes
    WHERE plan_id = NEW.plan_id;

    IF NEW.additions <> actual_additions OR
       NEW.modifications <> actual_updates OR
       NEW.destructions <> actual_deletions THEN

        RAISE EXCEPTION
            'Plan metrics do not match resource change records';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_plan_counts
BEFORE UPDATE ON terraform_plans
FOR EACH ROW
WHEN (
    OLD.is_applied IS DISTINCT FROM NEW.is_applied
)
EXECUTE FUNCTION validate_plan_resource_counts();

-- ============================================================
-- 24. MERGE AND DEPLOYMENT ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_deployment_eligibility(
    p_run_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    violation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    run_record pipeline_runs%ROWTYPE;
    plan_record terraform_plans%ROWTYPE;
    policy_record branch_protection_policies%ROWTYPE;

    approved_count INTEGER;
    required_count INTEGER;
    failed_checks INTEGER;
    unresolved_comments INTEGER;
    critical_findings INTEGER;
    deletion_count INTEGER;
BEGIN
    SELECT *
    INTO run_record
    FROM pipeline_runs
    WHERE run_id = p_run_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Pipeline run not found';
        RETURN;
    END IF;

    SELECT *
    INTO plan_record
    FROM terraform_plans
    WHERE run_id = p_run_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Terraform plan not found';
        RETURN;
    END IF;

    IF run_record.pull_request_id IS NULL THEN
        RETURN QUERY SELECT FALSE, 'Pull Request is required';
        RETURN;
    END IF;

    SELECT bp.*
    INTO policy_record
    FROM branch_protection_policies bp
    JOIN pull_requests pr
        ON pr.target_branch_id = bp.branch_id
    WHERE pr.pull_request_id = run_record.pull_request_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Branch protection policy missing';
        RETURN;
    END IF;

    IF run_record.status <> 'review_pending' THEN
        RETURN QUERY SELECT FALSE, 'Pipeline is not review-ready';
    END IF;

    IF plan_record.source_commit_sha <>
       run_record.source_commit_sha THEN

        RETURN QUERY SELECT FALSE, 'Plan source commit mismatch';
        RETURN;
    END IF;

    IF policy_record.require_up_to_date_branch THEN
        IF NOT EXISTS (
            SELECT 1
            FROM pull_requests pr
            WHERE pr.pull_request_id = run_record.pull_request_id
              AND pr.base_synchronized = TRUE
        ) THEN
            RETURN QUERY SELECT FALSE, 'Target branch is not synchronized';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pull_requests pr
        WHERE pr.pull_request_id = run_record.pull_request_id
          AND (
              pr.is_open = FALSE OR
              pr.is_draft = TRUE OR
              pr.has_merge_conflicts = TRUE
          )
    ) THEN
        RETURN QUERY SELECT FALSE, 'Pull Request is not merge-ready';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pull_requests pr
        WHERE pr.pull_request_id = run_record.pull_request_id
          AND pr.conversations_resolved = FALSE
          AND policy_record.require_conversation_resolution = TRUE
    ) THEN
        RETURN QUERY SELECT FALSE, 'Unresolved review conversations';
    END IF;

    SELECT COUNT(*)
    INTO approved_count
    FROM reviews r
    JOIN reviewers rv
        ON rv.reviewer_id = r.reviewer_id
    JOIN pull_requests pr
        ON pr.pull_request_id = r.pull_request_id
    WHERE r.pull_request_id = run_record.pull_request_id
      AND r.decision = 'approved'
      AND r.is_dismissed = FALSE
      AND rv.is_active = TRUE
      AND rv.is_authorized = TRUE
      AND rv.reviewer_id <> pr.created_by
      AND (
          NOT policy_record.dismiss_stale_approvals
          OR r.reviewed_commit_sha = pr.source_commit_sha
      );

    required_count := policy_record.required_approvals;

    IF policy_record.require_approvals AND
       approved_count < required_count THEN

        RETURN QUERY SELECT FALSE, 'Required approvals missing';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reviews
        WHERE pull_request_id = run_record.pull_request_id
          AND decision = 'rejected'
          AND is_dismissed = FALSE
    ) THEN
        RETURN QUERY SELECT FALSE, 'Review rejection exists';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO failed_checks
    FROM status_checks
    WHERE run_id = p_run_id
      AND status <> 'passed';

    IF policy_record.require_status_checks AND
       failed_checks > 0 THEN

        RETURN QUERY SELECT FALSE, 'Required status checks incomplete';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO critical_findings
    FROM security_findings
    WHERE run_id = p_run_id
      AND severity IN ('critical', 'high')
      AND is_resolved = FALSE;

    IF critical_findings > 0 THEN
        RETURN QUERY SELECT FALSE, 'Unresolved security findings';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO deletion_count
    FROM resource_changes
    WHERE plan_id = plan_record.plan_id
      AND action = 'delete';

    IF deletion_count > 0 THEN
        RETURN QUERY SELECT FALSE, 'Destructive plan requires separate authorization';
        RETURN;
    END IF;

    RETURN QUERY SELECT TRUE, 'All eligibility conditions satisfied';
END;
$$;

-- ============================================================
-- 25. PIPELINE START PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE start_pipeline(
    p_project_id BIGINT,
    p_pull_request_id BIGINT,
    p_environment environment_type,
    p_triggered_by BIGINT,
    p_source_commit_sha CHAR(40),
    INOUT p_created_run_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM terraform_projects
        WHERE project_id = p_project_id
          AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'Terraform project is not active';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM reviewers
        WHERE reviewer_id = p_triggered_by
          AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'Pipeline trigger identity is invalid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM commits
        WHERE commit_sha = p_source_commit_sha
          AND repository_id = (
              SELECT repository_id
              FROM terraform_projects
              WHERE project_id = p_project_id
          )
    ) THEN
        RAISE EXCEPTION 'Source commit does not exist in repository';
    END IF;

    IF p_pull_request_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM pull_requests
        WHERE pull_request_id = p_pull_request_id
          AND is_open = TRUE
          AND is_merged = FALSE
    ) THEN
        RAISE EXCEPTION 'Pull Request is not open';
    END IF;

    INSERT INTO pipeline_runs (
        project_id,
        pull_request_id,
        environment,
        status,
        triggered_by,
        source_commit_sha,
        pipeline_started_at
    )
    VALUES (
        p_project_id,
        p_pull_request_id,
        p_environment,
        'created',
        p_triggered_by,
        p_source_commit_sha,
        NOW()
    )
    RETURNING run_id INTO p_created_run_id;

    INSERT INTO audit_events (
        run_id,
        actor_id,
        event_type,
        event_details
    )
    VALUES (
        p_created_run_id,
        p_triggered_by,
        'pipeline_created',
        jsonb_build_object(
            'environment', p_environment,
            'project_id', p_project_id
        )
    );
END;
$$;

-- ============================================================
-- 26. DEPLOYMENT PROCESSING PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE process_deployment(
    p_run_id BIGINT,
    p_initiated_by BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    run_record pipeline_runs%ROWTYPE;
    plan_record terraform_plans%ROWTYPE;
    eligibility_record RECORD;
    lock_created BOOLEAN := FALSE;
BEGIN
    SELECT *
    INTO run_record
    FROM pipeline_runs
    WHERE run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline run not found';
    END IF;

    IF run_record.status <> 'review_pending' THEN
        RAISE EXCEPTION 'Pipeline is not ready for deployment';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM reviewers
        WHERE reviewer_id = p_initiated_by
          AND is_active = TRUE
          AND is_authorized = TRUE
    ) THEN
        RAISE EXCEPTION 'Deployment identity is unauthorized';
    END IF;

    SELECT *
    INTO plan_record
    FROM terraform_plans
    WHERE run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Terraform plan not found';
    END IF;

    SELECT *
    INTO eligibility_record
    FROM evaluate_deployment_eligibility(p_run_id);

    IF NOT eligibility_record.eligible THEN
        RAISE EXCEPTION
            'Deployment rejected: %',
            eligibility_record.violation;
    END IF;

    BEGIN
        INSERT INTO state_locks (
            project_id,
            environment,
            run_id,
            lock_owner
        )
        VALUES (
            run_record.project_id,
            run_record.environment,
            p_run_id,
            CURRENT_USER
        );

        lock_created := TRUE;

    EXCEPTION
        WHEN unique_violation THEN
            RAISE EXCEPTION
                'Terraform state is already locked';
    END;

    UPDATE pipeline_runs
    SET status = 'applying'
    WHERE run_id = p_run_id;

    INSERT INTO deployments (
        run_id,
        plan_id,
        environment,
        status,
        initiated_by,
        started_at
    )
    VALUES (
        p_run_id,
        plan_record.plan_id,
        run_record.environment,
        'running',
        p_initiated_by,
        NOW()
    );

    -- This transaction models deployment authorization and
    -- metadata state. Actual Terraform execution belongs to
    -- the CI/CD runner, not to a PostgreSQL transaction.

    UPDATE terraform_plans
    SET is_applied = TRUE,
        applied_at = NOW()
    WHERE plan_id = plan_record.plan_id
      AND is_approved = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Plan approval is missing';
    END IF;

    UPDATE deployments
    SET status = 'succeeded',
        completed_at = NOW()
    WHERE run_id = p_run_id;

    UPDATE pipeline_runs
    SET status = 'succeeded',
        pipeline_completed_at = NOW()
    WHERE run_id = p_run_id;

    DELETE FROM state_locks
    WHERE run_id = p_run_id;

    lock_created := FALSE;

EXCEPTION
    WHEN OTHERS THEN
        IF lock_created THEN
            DELETE FROM state_locks
            WHERE run_id = p_run_id;
        END IF;

        RAISE;
END;
$$;

-- ============================================================
-- 27. DEPLOYMENT ELIGIBILITY VIEW
-- ============================================================

CREATE OR REPLACE VIEW deployment_eligibility_report AS
SELECT
    pr.run_id,
    tp.project_name,
    pr.environment,
    pr.status,

    pl.plan_id,
    pl.additions,
    pl.modifications,
    pl.destructions,

    COALESCE(review_data.approval_count, 0)
        AS approval_count,

    COALESCE(check_data.passed_checks, 0)
        AS passed_checks,

    COALESCE(check_data.total_checks, 0)
        AS total_checks,

    COALESCE(security_data.open_findings, 0)
        AS open_security_findings,

    COALESCE(eligibility.eligible, FALSE)
        AS deployment_eligible,

    eligibility.violation

FROM pipeline_runs pr

JOIN terraform_projects tp
    ON tp.project_id = pr.project_id

LEFT JOIN terraform_plans pl
    ON pl.run_id = pr.run_id

LEFT JOIN LATERAL (
    SELECT COUNT(*) AS approval_count
    FROM reviews r
    JOIN reviewers rv
        ON rv.reviewer_id = r.reviewer_id
    JOIN pull_requests pull
        ON pull.pull_request_id = r.pull_request_id
    WHERE r.pull_request_id = pr.pull_request_id
      AND r.decision = 'approved'
      AND r.is_dismissed = FALSE
      AND rv.is_active = TRUE
      AND rv.is_authorized = TRUE
      AND rv.reviewer_id <> pull.created_by
      AND r.reviewed_commit_sha = pull.source_commit_sha
) review_data ON TRUE

LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (
            WHERE status = 'passed'
        ) AS passed_checks,

        COUNT(*) AS total_checks
    FROM status_checks
    WHERE run_id = pr.run_id
) check_data ON TRUE

LEFT JOIN LATERAL (
    SELECT COUNT(*) AS open_findings
    FROM security_findings
    WHERE run_id = pr.run_id
      AND is_resolved = FALSE
) security_data ON TRUE

LEFT JOIN LATERAL (
    SELECT COUNT(*) AS open_findings
    FROM security_findings
    WHERE run_id = pr.run_id
      AND is_resolved = FALSE
) unused_security_data ON TRUE

LEFT JOIN LATERAL (
    SELECT *
    FROM evaluate_deployment_eligibility(pr.run_id)
    LIMIT 1
) eligibility ON TRUE;

-- ============================================================
-- 28. SAMPLE REPOSITORY DATA
-- ============================================================

INSERT INTO repositories (
    repository_name,
    owner_name,
    default_branch
)
VALUES
    ('cloud-infrastructure', 'platform-team', 'main'),
    ('application-platform', 'engineering-team', 'main');

INSERT INTO branches (
    repository_id,
    branch_name,
    latest_commit_sha,
    is_protected,
    allow_direct_push,
    allow_force_push,
    allow_deletion
)
VALUES
    (
        1,
        'main',
        '1111111111111111111111111111111111111111',
        TRUE,
        FALSE,
        FALSE,
        FALSE
    ),
    (
        1,
        'feature/network-hardening',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        FALSE,
        TRUE,
        TRUE,
        TRUE
    ),
    (
        2,
        'main',
        '2222222222222222222222222222222222222222',
        TRUE,
        FALSE,
        FALSE,
        FALSE
    ),
    (
        2,
        'feature/application-storage',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        FALSE,
        TRUE,
        TRUE,
        TRUE
    );

INSERT INTO commits (
    repository_id,
    commit_sha,
    author_name,
    commit_message
)
VALUES
    (
        1,
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'developer-001',
        'Harden infrastructure network configuration'
    ),
    (
        2,
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        'developer-002',
        'Add encrypted application storage'
    );

INSERT INTO terraform_projects (
    repository_id,
    project_name,
    working_directory,
    terraform_version,
    backend_type,
    state_key
)
VALUES
    (
        1,
        'production-infrastructure',
        'infrastructure/production',
        '1.9.8',
        's3',
        'cloud-infrastructure/production.tfstate'
    ),
    (
        2,
        'application-storage',
        'infrastructure/storage',
        '1.9.8',
        's3',
        'application-platform/storage.tfstate'
    );

INSERT INTO reviewers (
    username,
    full_name,
    role_name
)
VALUES
    ('developer001', 'Infrastructure Developer', 'developer'),
    ('platformlead', 'Platform Lead', 'platform-lead'),
    ('securitylead', 'Security Lead', 'security-lead'),
    ('cloudarchitect', 'Cloud Architect', 'cloud-architect');

INSERT INTO branch_protection_policies (
    branch_id,
    require_pull_request,
    require_approvals,
    required_approvals,
    dismiss_stale_approvals,
    require_status_checks,
    require_conversation_resolution,
    require_linear_history,
    require_up_to_date_branch,
    prohibit_direct_push,
    prohibit_force_push,
    prohibit_branch_deletion
)
VALUES
    (1, TRUE, TRUE, 2, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, TRUE),
    (3, TRUE, TRUE, 1, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE);

INSERT INTO approval_requirements (
    policy_id,
    required_role,
    required_count
)
VALUES
    (1, 'platform-lead', 1),
    (1, 'security-lead', 1),
    (2, 'platform-lead', 1);

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    created_by,
    title,
    description,
    is_draft,
    source_commit_sha,
    target_commit_sha,
    base_synchronized,
    has_merge_conflicts,
    conversations_resolved
)
VALUES
    (
        1,
        2,
        1,
        1,
        'Harden production infrastructure',
        'Improve network security and storage configuration.',
        FALSE,
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        '1111111111111111111111111111111111111111',
        TRUE,
        FALSE,
        TRUE
    ),
    (
        2,
        4,
        3,
        1,
        'Add application storage',
        'Introduce encrypted storage infrastructure.',
        FALSE,
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        '2222222222222222222222222222222222222222',
        TRUE,
        FALSE,
        TRUE
    );

INSERT INTO pipeline_runs (
    project_id,
    pull_request_id,
    environment,
    status,
    triggered_by,
    source_commit_sha,
    configuration_hash,
    pipeline_started_at
)
VALUES
    (
        1,
        1,
        'production',
        'review_pending',
        1,
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'a1234567890123456789012345678901a1234567890123456789012345678901',
        NOW()
    ),
    (
        2,
        2,
        'staging',
        'review_pending',
        1,
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        'b1234567890123456789012345678901b1234567890123456789012345678901',
        NOW()
    );

INSERT INTO terraform_plans (
    run_id,
    artifact_path,
    artifact_checksum,
    source_commit_sha,
    additions,
    modifications,
    destructions,
    is_approved
)
VALUES
    (
        1,
        'artifacts/production-001.tfplan',
        'c1234567890123456789012345678901c1234567890123456789012345678901',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        1,
        2,
        0,
        TRUE
    ),
    (
        2,
        'artifacts/staging-002.tfplan',
        'd1234567890123456789012345678901d1234567890123456789012345678901',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        2,
        0,
        0,
        TRUE
    );

INSERT INTO resource_changes (
    plan_id,
    resource_address,
    resource_type,
    action,
    encryption_enabled,
    public_ingress_enabled,
    is_sensitive
)
VALUES
    (1, 'aws_s3_bucket.application', 'aws_s3_bucket', 'create', TRUE, FALSE, TRUE),
    (1, 'aws_security_group.application', 'aws_security_group', 'update', TRUE, FALSE, FALSE),
    (1, 'aws_db_instance.application', 'aws_db_instance', 'update', TRUE, FALSE, TRUE),
    (2, 'aws_s3_bucket.storage', 'aws_s3_bucket', 'create', TRUE, FALSE, TRUE),
    (2, 'aws_kms_key.storage', 'aws_kms_key', 'create', TRUE, FALSE, TRUE);

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    decision,
    reviewed_commit_sha
)
VALUES
    (
        1,
        2,
        'approved',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ),
    (
        1,
        3,
        'approved',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ),
    (
        2,
        2,
        'approved',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    );

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    comment_body,
    is_resolved,
    resolved_at
)
VALUES
    (
        1,
        'infrastructure/network.tf',
        24,
        'Network access restriction verified.',
        TRUE,
        NOW()
    ),
    (
        2,
        'infrastructure/storage.tf',
        18,
        'Encryption configuration reviewed.',
        TRUE,
        NOW()
    );

INSERT INTO status_checks (
    run_id,
    check_name,
    status,
    details,
    execution_time_ms
)
VALUES
    (1, 'terraform-fmt', 'passed', 'Formatting passed', 120),
    (1, 'terraform-validate', 'passed', 'Validation passed', 450),
    (1, 'terraform-security', 'passed', 'Security scan passed', 800),
    (1, 'terraform-policy', 'passed', 'Policy evaluation passed', 300),
    (2, 'terraform-fmt', 'passed', 'Formatting passed', 110),
    (2, 'terraform-validate', 'passed', 'Validation passed', 400),
    (2, 'terraform-security', 'passed', 'Security scan passed', 700),
    (2, 'terraform-policy', 'pending', 'Policy check pending', NULL);

INSERT INTO security_findings (
    run_id,
    resource_address,
    scanner_name,
    rule_id,
    severity,
    description,
    is_resolved
)
VALUES
    (
        1,
        'aws_security_group.application',
        'iac-security',
        'NET-001',
        'low',
        'Review network ingress configuration.',
        TRUE
    ),
    (
        2,
        'aws_s3_bucket.storage',
        'iac-security',
        'STORAGE-001',
        'high',
        'Storage access policy requires remediation.',
        FALSE
    );

INSERT INTO audit_events (
    run_id,
    actor_id,
    event_type,
    event_details
)
VALUES
    (
        1,
        1,
        'pipeline_created',
        '{"environment":"production","trigger":"pull_request"}'
    ),
    (
        1,
        2,
        'review_completed',
        '{"decision":"approved"}'
    );

-- ============================================================
-- 29. DATA RETRIEVAL
-- ============================================================

SELECT
    r.repository_name,
    pr.pull_request_id,
    pr.title,
    pr.is_draft,
    pr.is_open,
    pr.has_merge_conflicts,
    source.branch_name AS source_branch,
    target.branch_name AS target_branch
FROM pull_requests pr
JOIN repositories r
    ON r.repository_id = pr.repository_id
JOIN branches source
    ON source.branch_id = pr.source_branch_id
JOIN branches target
    ON target.branch_id = pr.target_branch_id
ORDER BY pr.created_at DESC;

-- ============================================================
-- 30. TERRAFORM PLAN AGGREGATION
-- ============================================================

SELECT
    tp.project_name,
    run.environment,
    SUM(plan.additions) AS total_additions,
    SUM(plan.modifications) AS total_modifications,
    SUM(plan.destructions) AS total_destructions,
    COUNT(plan.plan_id) AS total_plans
FROM pipeline_runs run
JOIN terraform_projects tp
    ON tp.project_id = run.project_id
JOIN terraform_plans plan
    ON plan.run_id = run.run_id
GROUP BY tp.project_name, run.environment;

-- ============================================================
-- 31. RESOURCE CHANGE VALIDATION
-- ============================================================

SELECT
    rc.resource_address,
    rc.action,
    rc.encryption_enabled,
    rc.public_ingress_enabled,
    CASE
        WHEN rc.encryption_enabled = FALSE
            THEN 'ENCRYPTION_FAILURE'
        WHEN rc.public_ingress_enabled = TRUE
            THEN 'PUBLIC_ACCESS_FAILURE'
        WHEN rc.action = 'delete'
            THEN 'DESTRUCTIVE_CHANGE'
        ELSE 'VALID'
    END AS validation_result
FROM resource_changes rc
ORDER BY rc.plan_id, rc.change_id;

-- ============================================================
-- 32. REVIEW APPROVAL AGGREGATION
-- ============================================================

SELECT
    pr.pull_request_id,
    pr.title,
    COUNT(*) FILTER (
        WHERE r.decision = 'approved'
          AND r.is_dismissed = FALSE
    ) AS approvals,
    COUNT(*) FILTER (
        WHERE r.decision = 'rejected'
          AND r.is_dismissed = FALSE
    ) AS rejections,
    COUNT(*) FILTER (
        WHERE r.decision = 'commented'
          AND r.is_dismissed = FALSE
    ) AS comments
FROM pull_requests pr
LEFT JOIN reviews r
    ON r.pull_request_id = pr.pull_request_id
GROUP BY pr.pull_request_id, pr.title;

-- ============================================================
-- 33. UNRESOLVED REVIEW CONVERSATIONS
-- ============================================================

SELECT
    pr.pull_request_id,
    pr.title,
    rc.file_path,
    rc.line_number,
    rc.comment_body
FROM pull_requests pr
JOIN reviews r
    ON r.pull_request_id = pr.pull_request_id
JOIN review_comments rc
    ON rc.review_id = r.review_id
WHERE rc.is_resolved = FALSE
ORDER BY pr.pull_request_id, rc.file_path, rc.line_number;

-- ============================================================
-- 34. SECURITY FINDINGS REPORT
-- ============================================================

SELECT
    run_id,
    severity,
    scanner_name,
    rule_id,
    resource_address,
    description
FROM security_findings
WHERE is_resolved = FALSE
ORDER BY
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END;

-- ============================================================
-- 35. STATUS CHECK REPORT
-- ============================================================

SELECT
    run_id,
    COUNT(*) AS total_checks,
    COUNT(*) FILTER (
        WHERE status = 'passed'
    ) AS passed_checks,
    COUNT(*) FILTER (
        WHERE status = 'failed'
    ) AS failed_checks,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_checks
FROM status_checks
GROUP BY run_id
ORDER BY run_id;

-- ============================================================
-- 36. CTE: RESOURCE CHANGE SUMMARY
-- ============================================================

WITH resource_summary AS (
    SELECT
        plan_id,
        COUNT(*) AS total_resources,
        COUNT(*) FILTER (
            WHERE action = 'create'
        ) AS additions,
        COUNT(*) FILTER (
            WHERE action = 'update'
        ) AS modifications,
        COUNT(*) FILTER (
            WHERE action = 'delete'
        ) AS deletions
    FROM resource_changes
    GROUP BY plan_id
)
SELECT
    plan_id,
    total_resources,
    additions,
    modifications,
    deletions
FROM resource_summary
ORDER BY plan_id;

-- ============================================================
-- 37. CTE: DEPLOYMENT RISK REPORT
-- ============================================================

WITH plan_risk AS (
    SELECT
        p.plan_id,
        p.run_id,
        p.destructions,
        COUNT(*) FILTER (
            WHERE f.severity IN ('critical', 'high')
              AND f.is_resolved = FALSE
        ) AS high_risk_findings
    FROM terraform_plans p
    LEFT JOIN security_findings f
        ON f.run_id = p.run_id
    GROUP BY p.plan_id, p.run_id, p.destructions
)
SELECT
    plan_id,
    run_id,
    destructions,
    high_risk_findings,
    CASE
        WHEN destructions > 0 OR high_risk_findings > 0
            THEN 'HIGH'
        WHEN destructions = 0
            THEN 'NORMAL'
        ELSE 'REVIEW'
    END AS risk_category
FROM plan_risk;

-- ============================================================
-- 38. EVALUATE DEPLOYMENT ELIGIBILITY
-- ============================================================

SELECT *
FROM evaluate_deployment_eligibility(1);

SELECT *
FROM evaluate_deployment_eligibility(2);

-- ============================================================
-- 39. DEPLOYMENT DASHBOARD
-- ============================================================

SELECT *
FROM deployment_eligibility_report
ORDER BY run_id;

-- ============================================================
-- 40. FAILED PIPELINE RETRIEVAL
-- ============================================================

SELECT
    run_id,
    project_id,
    environment,
    status,
    failure_reason,
    created_at
FROM pipeline_runs
WHERE status = 'failed'
ORDER BY created_at DESC;

-- ============================================================
-- 41. TRANSACTIONAL DEPLOYMENT EXAMPLE
--
-- Run the following call separately when an eligible pipeline
-- is ready. PostgreSQL controls metadata and authorization.
-- The external CI/CD runner must perform actual Terraform apply.
--
-- CALL process_deployment(1, 2);
--
-- ============================================================

COMMIT;

-- ============================================================
-- 42. OPERATIONAL QUERIES
-- ============================================================

-- Active Terraform state locks:
SELECT
    project_id,
    environment,
    run_id,
    lock_owner,
    acquired_at
FROM terraform_ci.state_locks;

-- Recent deployment history:
SELECT
    deployment_id,
    run_id,
    environment,
    status,
    started_at,
    completed_at
FROM terraform_ci.deployments
ORDER BY started_at DESC NULLS LAST;

-- Recent audit history:
SELECT
    event_id,
    run_id,
    event_type,
    event_details,
    created_at
FROM terraform_ci.audit_events
ORDER BY created_at DESC
LIMIT 50;

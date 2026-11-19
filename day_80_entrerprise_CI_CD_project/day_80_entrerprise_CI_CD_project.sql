-- ============================================================
-- ENTERPRISE MULTI-STAGE CI/CD PLATFORM
-- PostgreSQL 14+
--
-- Functional areas:
-- 1. Repository and branch management
-- 2. Commit and Pull Request lifecycle
-- 3. Code review and inline conversations
-- 4. Reviewer eligibility and approval policies
-- 5. Branch protection
-- 6. CI pipeline execution
-- 7. Build, test and security stages
-- 8. Artifact management
-- 9. Deployment approval and environment promotion
-- 10. Deployment health checks and rollback
-- 11. Merge eligibility
-- 12. Audit and operational reporting
--
-- Run using psql.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS enterprise_cicd;

SET search_path TO enterprise_cicd, public;


-- ============================================================
-- 1. ENUMERATIONS
-- ============================================================

CREATE TYPE pr_state AS ENUM (
    'draft',
    'open',
    'merged',
    'closed'
);

CREATE TYPE review_state AS ENUM (
    'approved',
    'changes_requested',
    'commented',
    'dismissed'
);

CREATE TYPE check_state AS ENUM (
    'pending',
    'success',
    'failure',
    'cancelled'
);

CREATE TYPE pipeline_state AS ENUM (
    'queued',
    'running',
    'success',
    'failure',
    'cancelled'
);

CREATE TYPE stage_state AS ENUM (
    'pending',
    'running',
    'success',
    'failure',
    'skipped'
);

CREATE TYPE deployment_environment AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE deployment_state AS ENUM (
    'pending',
    'approved',
    'deploying',
    'success',
    'failure',
    'rolled_back'
);

CREATE TYPE merge_strategy AS ENUM (
    'merge_commit',
    'squash',
    'rebase'
);


-- ============================================================
-- 2. REPOSITORIES
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    name VARCHAR(150) NOT NULL UNIQUE,

    description TEXT,

    default_branch VARCHAR(150) NOT NULL DEFAULT 'main',

    visibility VARCHAR(20) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'internal', 'public')),

    archived BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_repository_name
        CHECK (name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,149}$')
);


-- ============================================================
-- 3. USERS AND ROLES
-- ============================================================

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    username VARCHAR(100) NOT NULL UNIQUE,

    email VARCHAR(255) NOT NULL UNIQUE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    role_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL
        REFERENCES users(user_id),

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id),

    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_role
    ON user_roles(role_id, user_id);


-- ============================================================
-- 4. BRANCHES
-- ============================================================

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_name VARCHAR(150) NOT NULL,

    head_commit_id VARCHAR(100),

    is_protected BOOLEAN NOT NULL DEFAULT FALSE,

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, branch_name)
);

CREATE INDEX idx_branches_repository
    ON branches(repository_id, is_deleted);


-- ============================================================
-- 5. COMMITS
-- ============================================================

CREATE TABLE commits (
    commit_id VARCHAR(100) PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    parent_commit_id VARCHAR(100)
        REFERENCES commits(commit_id),

    author_id BIGINT NOT NULL
        REFERENCES users(user_id),

    commit_message TEXT NOT NULL,

    tree_hash VARCHAR(128),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (commit_id, repository_id),

    CHECK (LENGTH(TRIM(commit_message)) > 0)
);

CREATE INDEX idx_commits_branch_time
    ON commits(branch_id, created_at DESC);

CREATE INDEX idx_commits_repository_time
    ON commits(repository_id, created_at DESC);

ALTER TABLE branches
    ADD CONSTRAINT fk_branch_head_commit
    FOREIGN KEY (head_commit_id)
    REFERENCES commits(commit_id)
    DEFERRABLE INITIALLY DEFERRED;


CREATE TABLE commit_files (
    commit_id VARCHAR(100) NOT NULL
        REFERENCES commits(commit_id) ON DELETE CASCADE,

    file_path TEXT NOT NULL,

    change_type VARCHAR(20) NOT NULL
        CHECK (
            change_type IN (
                'added',
                'modified',
                'deleted',
                'renamed'
            )
        ),

    content_hash VARCHAR(128),

    PRIMARY KEY (commit_id, file_path),

    CHECK (
        file_path <> ''
        AND LEFT(file_path, 1) <> '/'
        AND POSITION('..' IN file_path) = 0
    )
);

CREATE INDEX idx_commit_files_path
    ON commit_files(file_path);


-- ============================================================
-- 6. PULL REQUESTS
-- ============================================================

CREATE TABLE pull_requests (
    pr_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    author_id BIGINT NOT NULL
        REFERENCES users(user_id),

    title VARCHAR(255) NOT NULL,

    description TEXT,

    state pr_state NOT NULL DEFAULT 'open',

    merge_strategy merge_strategy NOT NULL DEFAULT 'squash',

    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    merged_at TIMESTAMPTZ,

    closed_at TIMESTAMPTZ,

    CHECK (source_branch_id <> target_branch_id),

    CHECK (LENGTH(TRIM(title)) > 0)
);

CREATE INDEX idx_pr_repository_state
    ON pull_requests(repository_id, state, created_at DESC);

CREATE INDEX idx_pr_target_state
    ON pull_requests(target_branch_id, state);


CREATE TABLE pull_request_commits (
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,

    commit_id VARCHAR(100) NOT NULL
        REFERENCES commits(commit_id),

    position INTEGER NOT NULL CHECK (position > 0),

    PRIMARY KEY (pr_id, commit_id),

    UNIQUE (pr_id, position)
);


-- ============================================================
-- 7. CODE REVIEWS
-- ============================================================

CREATE TABLE reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,

    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id),

    reviewed_commit_id VARCHAR(100) NOT NULL
        REFERENCES commits(commit_id),

    state review_state NOT NULL,

    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    dismissed BOOLEAN NOT NULL DEFAULT FALSE,

    dismissal_reason TEXT
);

CREATE INDEX idx_reviews_pr_state
    ON reviews(pr_id, state, submitted_at DESC);

CREATE INDEX idx_reviews_reviewer
    ON reviews(reviewer_id, submitted_at DESC);

CREATE INDEX idx_reviews_commit
    ON reviews(reviewed_commit_id, state);


-- ============================================================
-- 8. REVIEW COMMENTS AND CONVERSATIONS
-- ============================================================

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,

    review_id BIGINT
        REFERENCES reviews(review_id),

    author_id BIGINT NOT NULL
        REFERENCES users(user_id),

    file_path TEXT NOT NULL,

    line_number INTEGER NOT NULL CHECK (line_number > 0),

    body TEXT NOT NULL,

    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    resolved_by BIGINT
        REFERENCES users(user_id),

    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (LENGTH(TRIM(body)) > 0)
);

CREATE INDEX idx_review_comments_pr_resolution
    ON review_comments(pr_id, is_resolved);


-- ============================================================
-- 9. REVIEW POLICIES AND APPROVAL REQUIREMENTS
-- ============================================================

CREATE TABLE approval_policies (
    approval_policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    required_approvals INTEGER NOT NULL DEFAULT 2
        CHECK (required_approvals >= 0),

    reject_author_approval BOOLEAN NOT NULL DEFAULT TRUE,

    dismiss_stale_approvals BOOLEAN NOT NULL DEFAULT TRUE,

    require_distinct_reviewers BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, branch_id)
);

CREATE TABLE approval_eligible_roles (
    approval_policy_id BIGINT NOT NULL
        REFERENCES approval_policies(approval_policy_id)
        ON DELETE CASCADE,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id),

    PRIMARY KEY (approval_policy_id, role_id)
);


-- ============================================================
-- 10. BRANCH PROTECTION
-- ============================================================

CREATE TABLE branch_protection (
    protection_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    approval_policy_id BIGINT NOT NULL
        REFERENCES approval_policies(approval_policy_id),

    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,

    require_linear_history BOOLEAN NOT NULL DEFAULT TRUE,

    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,

    allow_admin_bypass BOOLEAN NOT NULL DEFAULT FALSE,

    administrator_bypass_requires_audit BOOLEAN NOT NULL DEFAULT TRUE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, branch_id)
);

CREATE TABLE required_status_checks (
    protection_id BIGINT NOT NULL
        REFERENCES branch_protection(protection_id)
        ON DELETE CASCADE,

    check_name VARCHAR(150) NOT NULL,

    PRIMARY KEY (protection_id, check_name)
);


-- ============================================================
-- 11. CI PIPELINES
-- ============================================================

CREATE TABLE pipelines (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    commit_id VARCHAR(100) NOT NULL
        REFERENCES commits(commit_id),

    pr_id BIGINT
        REFERENCES pull_requests(pr_id),

    state pipeline_state NOT NULL DEFAULT 'queued',

    trigger_type VARCHAR(30) NOT NULL
        CHECK (
            trigger_type IN (
                'push',
                'pull_request',
                'schedule',
                'manual',
                'release'
            )
        ),

    attempt_number INTEGER NOT NULL DEFAULT 1
        CHECK (attempt_number > 0),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_pipelines_commit_state
    ON pipelines(commit_id, state);

CREATE INDEX idx_pipelines_repository_time
    ON pipelines(repository_id, created_at DESC);

CREATE INDEX idx_pipelines_pr
    ON pipelines(pr_id, created_at DESC)
    WHERE pr_id IS NOT NULL;


CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,

    stage_name VARCHAR(100) NOT NULL,

    stage_order INTEGER NOT NULL CHECK (stage_order > 0),

    state stage_state NOT NULL DEFAULT 'pending',

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    duration_ms NUMERIC(14, 3),

    output TEXT,

    error_message TEXT,

    UNIQUE (pipeline_id, stage_name),

    UNIQUE (pipeline_id, stage_order),

    CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX idx_pipeline_stages_state
    ON pipeline_stages(pipeline_id, state);


-- ============================================================
-- 12. STATUS CHECKS
-- ============================================================

CREATE TABLE status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,

    commit_id VARCHAR(100) NOT NULL
        REFERENCES commits(commit_id),

    check_name VARCHAR(150) NOT NULL,

    state check_state NOT NULL DEFAULT 'pending',

    details TEXT,

    completed_at TIMESTAMPTZ,

    UNIQUE (pipeline_id, check_name)
);

CREATE INDEX idx_status_checks_commit
    ON status_checks(commit_id, check_name, state);


-- ============================================================
-- 13. ARTIFACTS
-- ============================================================

CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),

    artifact_name VARCHAR(255) NOT NULL,

    artifact_version VARCHAR(100) NOT NULL,

    storage_uri TEXT NOT NULL,

    sha256_hash CHAR(64) NOT NULL,

    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),

    immutable BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (pipeline_id, artifact_name, artifact_version),

    CHECK (sha256_hash ~ '^[a-fA-F0-9]{64}$')
);

CREATE INDEX idx_artifacts_hash
    ON artifacts(sha256_hash);


-- ============================================================
-- 14. DEPLOYMENT ENVIRONMENTS
-- ============================================================

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    name deployment_environment NOT NULL UNIQUE,

    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    description TEXT
);

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),

    artifact_id BIGINT NOT NULL
        REFERENCES artifacts(artifact_id),

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    version VARCHAR(100) NOT NULL,

    previous_version VARCHAR(100),

    state deployment_state NOT NULL DEFAULT 'pending',

    requested_by BIGINT NOT NULL
        REFERENCES users(user_id),

    approved_by BIGINT
        REFERENCES users(user_id),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployments_environment
    ON deployments(environment_id, created_at DESC);

CREATE INDEX idx_deployments_state
    ON deployments(state, created_at DESC);


-- ============================================================
-- 15. DEPLOYMENT APPROVAL POLICIES
-- ============================================================

CREATE TABLE deployment_approval_policies (
    environment_id BIGINT PRIMARY KEY
        REFERENCES environments(environment_id),

    required_approvals INTEGER NOT NULL DEFAULT 0
        CHECK (required_approvals >= 0),

    prevent_requester_approval BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE deployment_eligible_roles (
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id),

    PRIMARY KEY (environment_id, role_id)
);


-- ============================================================
-- 16. DEPLOYMENT HEALTH AND ROLLBACK
-- ============================================================

CREATE TABLE deployment_health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,

    check_name VARCHAR(150) NOT NULL,

    passed BOOLEAN NOT NULL,

    response_time_ms NUMERIC(14, 3),

    details TEXT,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        response_time_ms IS NULL OR response_time_ms >= 0
    )
);

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,

    approver_id BIGINT NOT NULL
        REFERENCES users(user_id),

    approved BOOLEAN NOT NULL,

    comment TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (deployment_id, approver_id)
);


-- ============================================================
-- 17. AUDIT LOG
-- ============================================================

CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    actor_id BIGINT
        REFERENCES users(user_id),

    action VARCHAR(150) NOT NULL,

    resource_type VARCHAR(100) NOT NULL,

    resource_id VARCHAR(150) NOT NULL,

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_resource
    ON audit_events(resource_type, resource_id, created_at DESC);

CREATE INDEX idx_audit_actor
    ON audit_events(actor_id, created_at DESC);


-- ============================================================
-- 18. APPROVAL VALIDATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_review_submission()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_author BIGINT;
    v_reviewer_active BOOLEAN;
    v_pr_state pr_state;
BEGIN
    SELECT author_id, state
    INTO v_author, v_pr_state
    FROM pull_requests
    WHERE pr_id = NEW.pr_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pull Request does not exist';
    END IF;

    IF v_pr_state <> 'open' THEN
        RAISE EXCEPTION 'Reviews require an open Pull Request';
    END IF;

    IF v_author = NEW.reviewer_id THEN
        RAISE EXCEPTION 'Pull Request authors cannot review themselves';
    END IF;

    SELECT active
    INTO v_reviewer_active
    FROM users
    WHERE user_id = NEW.reviewer_id;

    IF NOT COALESCE(v_reviewer_active, FALSE) THEN
        RAISE EXCEPTION 'Reviewer is inactive or unavailable';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_review
BEFORE INSERT ON reviews
FOR EACH ROW
EXECUTE FUNCTION validate_review_submission();


-- ============================================================
-- 19. PROTECT AUDIT LOG FROM MODIFICATION
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Audit events cannot be modified or deleted';
END;
$$;

CREATE TRIGGER trg_audit_immutable_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_mutation();


-- ============================================================
-- 20. AUDIT HELPER
-- ============================================================

CREATE OR REPLACE FUNCTION record_audit(
    p_actor_id BIGINT,
    p_action VARCHAR,
    p_resource_type VARCHAR,
    p_resource_id VARCHAR,
    p_details JSONB DEFAULT '{}'::JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO audit_events (
        actor_id,
        action,
        resource_type,
        resource_id,
        details
    )
    VALUES (
        p_actor_id,
        p_action,
        p_resource_type,
        p_resource_id,
        COALESCE(p_details, '{}'::JSONB)
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;


-- ============================================================
-- 21. MERGE ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pr_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_target_branch BIGINT;
    v_source_branch BIGINT;
    v_head_commit VARCHAR(100);
    v_protection_id BIGINT;
    v_required_reviews INTEGER;
    v_actual_reviews INTEGER;
    v_require_conversations BOOLEAN;
    v_pr_author BIGINT;
    v_required_check TEXT;
BEGIN
    SELECT
        pr.target_branch_id,
        pr.source_branch_id,
        source.head_commit_id,
        pr.author_id
    INTO
        v_target_branch,
        v_source_branch,
        v_head_commit,
        v_pr_author
    FROM pull_requests pr
    JOIN branches source
        ON source.branch_id = pr.source_branch_id
    WHERE pr.pr_id = p_pr_id
      AND pr.state = 'open';

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is not open'::TEXT;
        RETURN;
    END IF;

    SELECT
        bp.protection_id,
        ap.required_approvals,
        bp.require_resolved_conversations
    INTO
        v_protection_id,
        v_required_reviews,
        v_require_conversations
    FROM branch_protection bp
    JOIN approval_policies ap
        ON ap.approval_policy_id = bp.approval_policy_id
    WHERE bp.branch_id = v_target_branch
      AND bp.enabled = TRUE;

    IF v_protection_id IS NULL THEN
        RETURN QUERY
        SELECT TRUE, 'No active branch protection policy'::TEXT;
        RETURN;
    END IF;

    -- Count distinct, eligible reviewers approving the current source head.
    SELECT COUNT(DISTINCT r.reviewer_id)
    INTO v_actual_reviews
    FROM reviews r
    JOIN approval_policies ap
        ON ap.approval_policy_id = (
            SELECT approval_policy_id
            FROM branch_protection
            WHERE protection_id = v_protection_id
        )
    WHERE r.pr_id = p_pr_id
      AND r.state = 'approved'
      AND r.dismissed = FALSE
      AND r.reviewed_commit_id = v_head_commit
      AND r.reviewer_id <> v_pr_author
      AND EXISTS (
          SELECT 1
          FROM approval_eligible_roles aer
          JOIN user_roles ur
              ON ur.role_id = aer.role_id
          JOIN users u
              ON u.user_id = ur.user_id
          WHERE aer.approval_policy_id =
                ap.approval_policy_id
            AND ur.user_id = r.reviewer_id
            AND u.active = TRUE
      );

    IF v_actual_reviews < v_required_reviews THEN
        RETURN QUERY
        SELECT
            FALSE,
            FORMAT(
                'Required approvals: %s; valid approvals: %s',
                v_required_reviews,
                v_actual_reviews
            );
    END IF;

    -- Every required check must pass against the current source head.
    FOR v_required_check IN
        SELECT check_name
        FROM required_status_checks
        WHERE protection_id = v_protection_id
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM status_checks sc
            JOIN pipelines p
                ON p.pipeline_id = sc.pipeline_id
            WHERE p.pr_id = p_pr_id
              AND sc.commit_id = v_head_commit
              AND sc.check_name = v_required_check
              AND sc.state = 'success'
              AND p.state = 'success'
        ) THEN
            RETURN QUERY
            SELECT
                FALSE,
                ('Required check incomplete: ' ||
                 v_required_check)::TEXT;
        END IF;
    END LOOP;

    IF v_require_conversations AND EXISTS (
        SELECT 1
        FROM review_comments rc
        WHERE rc.pr_id = p_pr_id
          AND rc.is_resolved = FALSE
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Unresolved review conversations'::TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pull_request_commits
        WHERE pr_id = p_pr_id
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request has no proposed commits'::TEXT;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'All merge requirements satisfied'::TEXT;
END;
$$;


-- ============================================================
-- 22. MERGE PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE merge_pull_request(
    p_pr_id BIGINT,
    p_actor_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_eligible BOOLEAN;
    v_reason TEXT;
    v_source BIGINT;
    v_target BIGINT;
    v_head VARCHAR(100);
BEGIN
    SELECT eligible, reason
    INTO v_eligible, v_reason
    FROM evaluate_merge_eligibility(p_pr_id)
    WHERE eligible = FALSE
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION 'Merge blocked: %', v_reason;
    END IF;

    SELECT
        source_branch_id,
        target_branch_id
    INTO v_source, v_target
    FROM pull_requests
    WHERE pr_id = p_pr_id
      AND state = 'open'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pull Request is not open';
    END IF;

    -- Lock target branch to serialize concurrent merges.
    PERFORM 1
    FROM branches
    WHERE branch_id = v_target
    FOR UPDATE;

    SELECT head_commit_id
    INTO v_head
    FROM branches
    WHERE branch_id = v_source;

    -- The source commits become part of the target history.
    -- Production deployments should create a merge commit or
    -- rewritten commit graph according to the selected strategy.
    UPDATE branches target
    SET head_commit_id = v_head
    WHERE target.branch_id = v_target;

    UPDATE pull_requests
    SET
        state = 'merged',
        merged_at = NOW(),
        updated_at = NOW()
    WHERE pr_id = p_pr_id;

    PERFORM record_audit(
        p_actor_id,
        'pull_request_merged',
        'pull_request',
        p_pr_id::TEXT,
        jsonb_build_object(
            'source_branch_id', v_source,
            'target_branch_id', v_target
        )
    );
END;
$$;


-- ============================================================
-- 23. PIPELINE COMPLETION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION finalize_pipeline(
    p_pipeline_id BIGINT
)
RETURNS pipeline_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_state pipeline_state;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pipeline_stages
        WHERE pipeline_id = p_pipeline_id
          AND state = 'failure'
    ) THEN
        v_state := 'failure';

    ELSIF EXISTS (
        SELECT 1
        FROM pipeline_stages
        WHERE pipeline_id = p_pipeline_id
          AND state IN ('pending', 'running')
    ) THEN
        v_state := 'running';

    ELSE
        v_state := 'success';
    END IF;

    UPDATE pipelines
    SET
        state = v_state,
        completed_at = CASE
            WHEN v_state IN ('success', 'failure')
            THEN NOW()
            ELSE NULL
        END
    WHERE pipeline_id = p_pipeline_id;

    RETURN v_state;
END;
$$;


-- ============================================================
-- 24. DEPLOYMENT APPROVAL VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_deployment_approval()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_requester BIGINT;
    v_environment BIGINT;
    v_user_active BOOLEAN;
BEGIN
    SELECT requested_by, environment_id
    INTO v_requester, v_environment
    FROM deployments
    WHERE deployment_id = NEW.deployment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    SELECT active
    INTO v_user_active
    FROM users
    WHERE user_id = NEW.approver_id;

    IF NOT COALESCE(v_user_active, FALSE) THEN
        RAISE EXCEPTION 'Approver is inactive';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM deployment_approval_policies
        WHERE environment_id = v_environment
          AND prevent_requester_approval = TRUE
    ) AND v_requester = NEW.approver_id THEN
        RAISE EXCEPTION 'Requester cannot approve own deployment';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_deployment_approval
BEFORE INSERT ON deployment_approvals
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_approval();


-- ============================================================
-- 25. DEPLOYMENT FINALIZATION AND ROLLBACK
-- ============================================================

CREATE OR REPLACE PROCEDURE finalize_deployment(
    p_deployment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_environment BIGINT;
    v_previous_version VARCHAR(100);
    v_health_failed BOOLEAN;
    v_state deployment_state;
BEGIN
    SELECT
        environment_id,
        previous_version,
        state
    INTO
        v_environment,
        v_previous_version,
        v_state
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    IF v_state <> 'deploying' THEN
        RAISE EXCEPTION 'Deployment must be deploying';
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM deployment_health_checks
        WHERE deployment_id = p_deployment_id
          AND passed = FALSE
    )
    INTO v_health_failed;

    IF v_health_failed THEN
        UPDATE deployments
        SET
            state = 'rolled_back',
            completed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        PERFORM record_audit(
            NULL,
            'deployment_rollback',
            'deployment',
            p_deployment_id::TEXT,
            jsonb_build_object(
                'previous_version', v_previous_version
            )
        );
    ELSE
        UPDATE deployments
        SET
            state = 'success',
            completed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        PERFORM record_audit(
            NULL,
            'deployment_success',
            'deployment',
            p_deployment_id::TEXT
        );
    END IF;
END;
$$;


-- ============================================================
-- 26. REPORTING VIEW: PULL REQUEST STATUS
-- ============================================================

CREATE VIEW v_pull_request_status AS
SELECT
    pr.pr_id,
    r.name AS repository,
    source.branch_name AS source_branch,
    target.branch_name AS target_branch,
    author.username AS author,
    pr.title,
    pr.state,
    COUNT(DISTINCT prc.commit_id) AS proposed_commits,

    COUNT(DISTINCT rv.review_id)
        FILTER (
            WHERE rv.state = 'approved'
              AND rv.dismissed = FALSE
        ) AS approval_records,

    COUNT(DISTINCT rc.comment_id)
        FILTER (
            WHERE rc.is_resolved = FALSE
        ) AS unresolved_conversations,

    pr.created_at,
    pr.merged_at

FROM pull_requests pr

JOIN repositories r
    ON r.repository_id = pr.repository_id

JOIN branches source
    ON source.branch_id = pr.source_branch_id

JOIN branches target
    ON target.branch_id = pr.target_branch_id

JOIN users author
    ON author.user_id = pr.author_id

LEFT JOIN pull_request_commits prc
    ON prc.pr_id = pr.pr_id

LEFT JOIN reviews rv
    ON rv.pr_id = pr.pr_id

LEFT JOIN review_comments rc
    ON rc.pr_id = pr.pr_id

GROUP BY
    pr.pr_id,
    r.name,
    source.branch_name,
    target.branch_name,
    author.username;


-- ============================================================
-- 27. REPORTING VIEW: PIPELINE PERFORMANCE
-- ============================================================

CREATE VIEW v_pipeline_performance AS
SELECT
    p.pipeline_id,
    r.name AS repository,
    p.commit_id,
    p.state,
    p.trigger_type,
    COUNT(ps.stage_id) AS total_stages,

    COUNT(ps.stage_id)
        FILTER (WHERE ps.state = 'success') AS successful_stages,

    COUNT(ps.stage_id)
        FILTER (WHERE ps.state = 'failure') AS failed_stages,

    SUM(ps.duration_ms) AS total_duration_ms,

    p.started_at,
    p.completed_at

FROM pipelines p

JOIN repositories r
    ON r.repository_id = p.repository_id

LEFT JOIN pipeline_stages ps
    ON ps.pipeline_id = p.pipeline_id

GROUP BY
    p.pipeline_id,
    r.name;


-- ============================================================
-- 28. REPORTING VIEW: DEPLOYMENT STATUS
-- ============================================================

CREATE VIEW v_deployment_status AS
SELECT
    d.deployment_id,
    r.name AS repository,
    e.name AS environment,
    d.version,
    d.previous_version,
    d.state,
    requester.username AS requested_by,
    approver.username AS approved_by,
    d.created_at,
    d.completed_at

FROM deployments d

JOIN pipelines p
    ON p.pipeline_id = d.pipeline_id

JOIN repositories r
    ON r.repository_id = p.repository_id

JOIN environments e
    ON e.environment_id = d.environment_id

JOIN users requester
    ON requester.user_id = d.requested_by

LEFT JOIN users approver
    ON approver.user_id = d.approved_by;


-- ============================================================
-- 29. SAMPLE DATA
-- ============================================================

INSERT INTO repositories (
    name,
    description,
    default_branch,
    visibility
)
VALUES (
    'enterprise-platform',
    'Enterprise multi-stage CI/CD application',
    'main',
    'private'
);

INSERT INTO users (username, email)
VALUES
    ('developer-01', 'developer01@example.com'),
    ('reviewer-01', 'reviewer01@example.com'),
    ('reviewer-02', 'reviewer02@example.com'),
    ('release-operator', 'release@example.com'),
    ('production-manager', 'production@example.com'),
    ('admin-01', 'admin@example.com');

INSERT INTO roles (role_name)
VALUES
    ('developer'),
    ('senior_engineer'),
    ('maintainer'),
    ('release_manager'),
    ('platform_admin');

INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM users u
JOIN roles r ON (
    (u.username = 'developer-01' AND r.role_name = 'developer')
    OR
    (u.username = 'reviewer-01' AND r.role_name = 'senior_engineer')
    OR
    (u.username = 'reviewer-02' AND r.role_name = 'maintainer')
    OR
    (u.username = 'release-operator' AND r.role_name = 'release_manager')
    OR
    (u.username = 'production-manager' AND r.role_name = 'release_manager')
    OR
    (u.username = 'admin-01' AND r.role_name = 'platform_admin')
);

INSERT INTO environments (
    name,
    requires_approval,
    description
)
VALUES
    ('development', FALSE, 'Development deployment environment'),
    ('staging', TRUE, 'Pre-production validation environment'),
    ('production', TRUE, 'Production environment');

INSERT INTO deployment_approval_policies (
    environment_id,
    required_approvals,
    prevent_requester_approval
)
SELECT
    environment_id,
    CASE
        WHEN name = 'development' THEN 0
        WHEN name = 'staging' THEN 1
        WHEN name = 'production' THEN 1
    END,
    TRUE
FROM environments;

INSERT INTO deployment_eligible_roles (
    environment_id,
    role_id
)
SELECT
    e.environment_id,
    r.role_id
FROM environments e
CROSS JOIN roles r
WHERE
    (
        e.name = 'staging'
        AND r.role_name IN (
            'release_manager',
            'platform_admin'
        )
    )
    OR
    (
        e.name = 'production'
        AND r.role_name = 'release_manager'
    );


-- ============================================================
-- 30. SAMPLE BRANCHES
-- ============================================================

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected
)
SELECT repository_id, 'main', TRUE
FROM repositories
WHERE name = 'enterprise-platform';

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected
)
SELECT repository_id, 'feature/payment-api', FALSE
FROM repositories
WHERE name = 'enterprise-platform';


-- ============================================================
-- 31. SAMPLE COMMITS
-- ============================================================

INSERT INTO commits (
    commit_id,
    repository_id,
    branch_id,
    author_id,
    commit_message,
    tree_hash
)
SELECT
    'commit-feature-001',
    r.repository_id,
    b.branch_id,
    u.user_id,
    'Implement payment API',
    REPEAT('a', 64)
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
JOIN users u
    ON u.username = 'developer-01'
WHERE
    r.name = 'enterprise-platform'
    AND b.branch_name = 'feature/payment-api';

INSERT INTO commit_files (
    commit_id,
    file_path,
    change_type,
    content_hash
)
VALUES
    (
        'commit-feature-001',
        'src/payment_service.py',
        'added',
        REPEAT('b', 64)
    ),
    (
        'commit-feature-001',
        'tests/test_payment.py',
        'added',
        REPEAT('c', 64)
    ),
    (
        'commit-feature-001',
        'requirements.txt',
        'modified',
        REPEAT('d', 64)
    );

UPDATE branches
SET head_commit_id = 'commit-feature-001'
WHERE branch_name = 'feature/payment-api';


-- ============================================================
-- 32. BRANCH PROTECTION CONFIGURATION
-- ============================================================

INSERT INTO approval_policies (
    repository_id,
    branch_id,
    required_approvals,
    reject_author_approval,
    dismiss_stale_approvals
)
SELECT
    r.repository_id,
    b.branch_id,
    2,
    TRUE,
    TRUE
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE
    r.name = 'enterprise-platform'
    AND b.branch_name = 'main';

INSERT INTO approval_eligible_roles (
    approval_policy_id,
    role_id
)
SELECT
    ap.approval_policy_id,
    roles.role_id
FROM approval_policies ap
CROSS JOIN roles
WHERE
    roles.role_name IN (
        'senior_engineer',
        'maintainer'
    );

INSERT INTO branch_protection (
    repository_id,
    branch_id,
    approval_policy_id,
    require_resolved_conversations,
    require_linear_history,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    allow_admin_bypass
)
SELECT
    ap.repository_id,
    ap.branch_id,
    ap.approval_policy_id,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    FALSE
FROM approval_policies ap;

INSERT INTO required_status_checks (
    protection_id,
    check_name
)
SELECT
    protection_id,
    check_name
FROM branch_protection
CROSS JOIN (
    VALUES
        ('build'),
        ('unit_tests'),
        ('security_scan')
) AS required(check_name);


-- ============================================================
-- 33. SAMPLE PULL REQUEST
-- ============================================================

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    description,
    state,
    merge_strategy
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    author.user_id,
    'Add payment API',
    'Introduce payment validation and test coverage.',
    'open',
    'squash'
FROM repositories r
JOIN branches source
    ON source.repository_id = r.repository_id
JOIN branches target
    ON target.repository_id = r.repository_id
JOIN users author
    ON author.username = 'developer-01'
WHERE
    r.name = 'enterprise-platform'
    AND source.branch_name = 'feature/payment-api'
    AND target.branch_name = 'main';

INSERT INTO pull_request_commits (
    pr_id,
    commit_id,
    position
)
SELECT
    pr.pr_id,
    'commit-feature-001',
    1
FROM pull_requests pr
WHERE pr.title = 'Add payment API';


-- ============================================================
-- 34. SAMPLE REVIEWS
-- ============================================================

INSERT INTO reviews (
    pr_id,
    reviewer_id,
    reviewed_commit_id,
    state
)
SELECT
    pr.pr_id,
    reviewer.user_id,
    'commit-feature-001',
    'approved'
FROM pull_requests pr
CROSS JOIN users reviewer
WHERE
    pr.title = 'Add payment API'
    AND reviewer.username IN (
        'reviewer-01',
        'reviewer-02'
    );


-- ============================================================
-- 35. SAMPLE REVIEW CONVERSATION
-- ============================================================

INSERT INTO review_comments (
    pr_id,
    author_id,
    file_path,
    line_number,
    body,
    is_resolved,
    resolved_by,
    resolved_at
)
SELECT
    pr.pr_id,
    reviewer.user_id,
    'src/payment_service.py',
    25,
    'Validate transaction amount before processing.',
    TRUE,
    reviewer.user_id,
    NOW()
FROM pull_requests pr
JOIN users reviewer
    ON reviewer.username = 'reviewer-01'
WHERE pr.title = 'Add payment API';


UPDATE pull_requests
SET conversations_resolved = TRUE
WHERE title = 'Add payment API';


-- ============================================================
-- 36. SAMPLE PIPELINE
-- ============================================================

INSERT INTO pipelines (
    repository_id,
    commit_id,
    pr_id,
    state,
    trigger_type,
    attempt_number,
    started_at,
    completed_at
)
SELECT
    pr.repository_id,
    'commit-feature-001',
    pr.pr_id,
    'success',
    'pull_request',
    1,
    NOW() - INTERVAL '5 minutes',
    NOW()
FROM pull_requests pr
WHERE pr.title = 'Add payment API';


INSERT INTO pipeline_stages (
    pipeline_id,
    stage_name,
    stage_order,
    state,
    duration_ms,
    output
)
SELECT
    p.pipeline_id,
    stage.stage_name,
    stage.stage_order,
    'success',
    stage.duration_ms,
    stage.output
FROM pipelines p
CROSS JOIN (
    VALUES
        ('checkout', 1, 120.0, 'Source checked out'),
        ('build', 2, 850.0, 'Build passed'),
        ('unit_tests', 3, 1300.0, '42 tests passed'),
        ('integration_tests', 4, 2200.0, '18 tests passed'),
        ('security_scan', 5, 760.0, 'Security checks passed'),
        ('package', 6, 340.0, 'Artifact packaged')
) AS stage(
    stage_name,
    stage_order,
    duration_ms,
    output
)
WHERE p.trigger_type = 'pull_request';


INSERT INTO status_checks (
    pipeline_id,
    commit_id,
    check_name,
    state,
    details,
    completed_at
)
SELECT
    p.pipeline_id,
    p.commit_id,
    stage.stage_name,
    'success',
    stage.output,
    NOW()
FROM pipelines p
JOIN pipeline_stages stage
    ON stage.pipeline_id = p.pipeline_id
WHERE p.trigger_type = 'pull_request'
  AND stage.stage_name IN (
      'build',
      'unit_tests',
      'security_scan'
  );


-- ============================================================
-- 37. SAMPLE ARTIFACT
-- ============================================================

INSERT INTO artifacts (
    pipeline_id,
    artifact_name,
    artifact_version,
    storage_uri,
    sha256_hash,
    size_bytes,
    immutable
)
SELECT
    pipeline_id,
    'payment-service',
    '1.0.0',
    'artifact://enterprise-platform/payment-service/1.0.0',
    REPEAT('e', 64),
    5242880,
    TRUE
FROM pipelines
WHERE trigger_type = 'pull_request';


-- ============================================================
-- 38. MERGE ELIGIBILITY REPORT
-- ============================================================

SELECT
    pr_id,
    eligible,
    reason
FROM pull_requests
CROSS JOIN LATERAL
    evaluate_merge_eligibility(pr_id)
WHERE state = 'open';


-- ============================================================
-- 39. EXAMPLE VALIDATION QUERIES
-- ============================================================

-- Detect approvals that have become stale.
SELECT
    pr.pr_id,
    rv.review_id,
    rv.reviewer_id,
    rv.reviewed_commit_id,
    source.head_commit_id AS current_head
FROM pull_requests pr
JOIN branches source
    ON source.branch_id = pr.source_branch_id
JOIN reviews rv
    ON rv.pr_id = pr.pr_id
WHERE
    rv.state = 'approved'
    AND rv.dismissed = FALSE
    AND rv.reviewed_commit_id <> source.head_commit_id;


-- Detect unresolved review conversations.
SELECT
    pr.pr_id,
    rc.comment_id,
    rc.file_path,
    rc.line_number,
    rc.body
FROM pull_requests pr
JOIN review_comments rc
    ON rc.pr_id = pr.pr_id
WHERE rc.is_resolved = FALSE;


-- Identify failed CI pipelines.
SELECT
    pipeline_id,
    commit_id,
    state,
    created_at
FROM pipelines
WHERE state = 'failure'
ORDER BY created_at DESC;


-- ============================================================
-- 40. AGGREGATION AND REPORTING
-- ============================================================

-- Pipeline success and failure counts.
SELECT
    repository_id,
    COUNT(*) AS total_pipelines,
    COUNT(*) FILTER (
        WHERE state = 'success'
    ) AS successful_pipelines,
    COUNT(*) FILTER (
        WHERE state = 'failure'
    ) AS failed_pipelines,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE state = 'success'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_percentage
FROM pipelines
GROUP BY repository_id;


-- Average stage execution duration.
SELECT
    stage_name,
    COUNT(*) AS executions,
    ROUND(AVG(duration_ms), 2) AS average_duration_ms,
    MAX(duration_ms) AS maximum_duration_ms
FROM pipeline_stages
WHERE state IN ('success', 'failure')
GROUP BY stage_name
ORDER BY average_duration_ms DESC;


-- Deployment success and rollback analysis.
SELECT
    e.name AS environment,
    COUNT(*) AS deployment_count,
    COUNT(*) FILTER (
        WHERE d.state = 'success'
    ) AS successful_deployments,
    COUNT(*) FILTER (
        WHERE d.state = 'rolled_back'
    ) AS rollback_count
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
GROUP BY e.name;


-- ============================================================
-- 41. COMPLETE WORKFLOW TRANSACTION
-- ============================================================

-- Merge only after all eligibility conditions pass.
-- If any condition fails, the transaction rolls back.

DO $$
DECLARE
    v_pr_id BIGINT;
    v_actor_id BIGINT;
BEGIN
    SELECT pr_id
    INTO v_pr_id
    FROM pull_requests
    WHERE title = 'Add payment API'
      AND state = 'open'
    LIMIT 1;

    SELECT user_id
    INTO v_actor_id
    FROM users
    WHERE username = 'admin-01';

    IF v_pr_id IS NOT NULL THEN
        CALL merge_pull_request(v_pr_id, v_actor_id);
    END IF;
END;
$$;


-- ============================================================
-- 42. SAMPLE DEPLOYMENT REQUEST
-- ============================================================

INSERT INTO deployments (
    pipeline_id,
    artifact_id,
    environment_id,
    version,
    previous_version,
    state,
    requested_by
)
SELECT
    p.pipeline_id,
    a.artifact_id,
    e.environment_id,
    '1.0.0',
    '0.9.0',
    'pending',
    requester.user_id
FROM pipelines p
JOIN artifacts a
    ON a.pipeline_id = p.pipeline_id
JOIN environments e
    ON e.name = 'staging'
JOIN users requester
    ON requester.username = 'developer-01'
WHERE p.state = 'success'
  AND p.trigger_type = 'pull_request';


-- ============================================================
-- 43. SAMPLE DEPLOYMENT APPROVAL
-- ============================================================

INSERT INTO deployment_approvals (
    deployment_id,
    approver_id,
    approved,
    comment
)
SELECT
    d.deployment_id,
    approver.user_id,
    TRUE,
    'Staging release approved'
FROM deployments d
JOIN users approver
    ON approver.username = 'release-operator'
JOIN user_roles ur
    ON ur.user_id = approver.user_id
JOIN roles role
    ON role.role_id = ur.role_id
WHERE
    d.version = '1.0.0'
    AND role.role_name = 'release_manager'
    AND d.state = 'pending'
    AND d.environment_id = (
        SELECT environment_id
        FROM environments
        WHERE name = 'staging'
    );


-- ============================================================
-- 44. DEPLOYMENT ELIGIBILITY QUERY
-- ============================================================

SELECT
    d.deployment_id,
    e.name,
    d.version,
    COUNT(DISTINCT da.approver_id)
        FILTER (WHERE da.approved = TRUE) AS approvals,
    policy.required_approvals,

    CASE
        WHEN p.state <> 'success' THEN FALSE

        WHEN COUNT(DISTINCT da.approver_id)
            FILTER (WHERE da.approved = TRUE)
            < policy.required_approvals THEN FALSE

        WHEN policy.required_approvals > 0
            AND NOT EXISTS (
                SELECT 1
                FROM deployment_approvals approved
                WHERE approved.deployment_id = d.deployment_id
                  AND approved.approved = TRUE
            ) THEN FALSE

        ELSE TRUE
    END AS eligible

FROM deployments d

JOIN pipelines p
    ON p.pipeline_id = d.pipeline_id

JOIN environments e
    ON e.environment_id = d.environment_id

JOIN deployment_approval_policies policy
    ON policy.environment_id = d.environment_id

LEFT JOIN deployment_approvals da
    ON da.deployment_id = d.deployment_id

GROUP BY
    d.deployment_id,
    e.name,
    d.version,
    p.state,
    policy.required_approvals;


-- ============================================================
-- 45. DEPLOYMENT HEALTH CHECK EXAMPLE
-- ============================================================

INSERT INTO deployment_health_checks (
    deployment_id,
    check_name,
    passed,
    response_time_ms,
    details
)
SELECT
    deployment_id,
    'http_health_endpoint',
    TRUE,
    85.5,
    'HTTP health endpoint returned success'
FROM deployments
WHERE version = '1.0.0'
  AND state = 'pending'
  AND environment_id = (
      SELECT environment_id
      FROM environments
      WHERE name = 'staging'
  );


-- ============================================================
-- 46. OPERATIONAL REPORTS
-- ============================================================

SELECT * FROM v_pull_request_status
ORDER BY created_at DESC;

SELECT * FROM v_pipeline_performance
ORDER BY pipeline_id DESC;

SELECT * FROM v_deployment_status
ORDER BY created_at DESC;


-- ============================================================
-- 47. AUDIT REPORT
-- ============================================================

SELECT
    event_id,
    actor_id,
    action,
    resource_type,
    resource_id,
    details,
    created_at
FROM audit_events
ORDER BY created_at DESC;


COMMIT;


-- ============================================================
-- 48. ADDITIONAL OPERATIONAL QUERIES
-- ============================================================

-- Repositories with protected branches.
SELECT
    r.name,
    b.branch_name,
    bp.allow_direct_push,
    bp.allow_force_push,
    bp.allow_deletion,
    bp.require_linear_history
FROM branch_protection bp
JOIN repositories r
    ON r.repository_id = bp.repository_id
JOIN branches b
    ON b.branch_id = bp.branch_id
WHERE bp.enabled = TRUE;


-- Latest pipeline execution for each repository.
SELECT DISTINCT ON (repository_id)
    repository_id,
    pipeline_id,
    commit_id,
    state,
    created_at
FROM pipelines
ORDER BY repository_id, created_at DESC;


-- Security scan failures.
SELECT
    p.pipeline_id,
    p.commit_id,
    sc.details
FROM status_checks sc
JOIN pipelines p
    ON p.pipeline_id = sc.pipeline_id
WHERE sc.check_name = 'security_scan'
  AND sc.state = 'failure';


-- Artifact inventory.
SELECT
    artifact_name,
    artifact_version,
    sha256_hash,
    size_bytes,
    immutable,
    created_at
FROM artifacts
ORDER BY created_at DESC;


-- Production deployment history.
SELECT
    d.deployment_id,
    d.version,
    d.previous_version,
    d.state,
    d.created_at,
    d.completed_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
WHERE e.name = 'production'
ORDER BY d.created_at DESC;

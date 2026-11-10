-- ============================================================
-- CI/CD ARCHITECTURE AND REPOSITORY GOVERNANCE
-- PostgreSQL 15+
--
-- Domain:
-- Repository -> Branches -> Commits -> Pull Requests
-- -> Reviews -> Comments -> Status Checks
-- -> Branch Protection -> Merge Eligibility
-- -> Pipeline -> Runners -> Jobs -> Artifacts
-- -> Environments -> Deployments
--
-- All merge and deployment decisions are recorded separately
-- from the underlying source branch and target branch state.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS cicd;

SET search_path TO cicd, public;

-- ============================================================
-- ENUM TYPES
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

CREATE TYPE job_state AS ENUM (
    'queued',
    'running',
    'success',
    'failure',
    'cancelled'
);

CREATE TYPE deployment_environment AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE merge_strategy AS ENUM (
    'merge_commit',
    'squash',
    'rebase'
);

CREATE TYPE runner_status AS ENUM (
    'online',
    'offline',
    'draining'
);

CREATE TYPE deployment_state AS ENUM (
    'pending',
    'deploying',
    'succeeded',
    'failed',
    'rolled_back'
);

-- ============================================================
-- IDENTITY AND REPOSITORY MODEL
-- ============================================================

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(user_id),
    default_branch VARCHAR(150) NOT NULL DEFAULT 'main',
    visibility VARCHAR(20) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'internal', 'public')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, name)
);

CREATE TABLE repository_members (
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    repository_role VARCHAR(30) NOT NULL
        CHECK (
            repository_role IN (
                'read',
                'developer',
                'reviewer',
                'maintainer',
                'admin'
            )
        ),
    can_bypass_protection BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (repository_id, user_id)
);

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    head_commit_sha VARCHAR(40),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository_id, name)
);

CREATE UNIQUE INDEX uq_default_branch
ON branches(repository_id)
WHERE is_default = TRUE AND deleted_at IS NULL;

-- ============================================================
-- COMMITS AND BRANCH HISTORY
-- ============================================================

CREATE TABLE commits (
    commit_sha VARCHAR(40) PRIMARY KEY
        CHECK (commit_sha ~ '^[0-9a-f]{7,40}$'),
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES users(user_id),
    message TEXT NOT NULL CHECK (LENGTH(TRIM(message)) > 0),
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE commit_parents (
    commit_sha VARCHAR(40) NOT NULL
        REFERENCES commits(commit_sha) ON DELETE CASCADE,
    parent_sha VARCHAR(40) NOT NULL
        REFERENCES commits(commit_sha),
    parent_order SMALLINT NOT NULL CHECK (parent_order > 0),
    PRIMARY KEY (commit_sha, parent_sha),
    UNIQUE (commit_sha, parent_order),
    CHECK (commit_sha <> parent_sha)
);

CREATE TABLE branch_commits (
    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id) ON DELETE CASCADE,
    commit_sha VARCHAR(40) NOT NULL
        REFERENCES commits(commit_sha),
    position BIGINT NOT NULL CHECK (position > 0),
    PRIMARY KEY (branch_id, commit_sha),
    UNIQUE (branch_id, position)
);

-- ============================================================
-- PULL REQUESTS
-- ============================================================

CREATE TABLE pull_requests (
    pr_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    author_id BIGINT NOT NULL REFERENCES users(user_id),
    title VARCHAR(250) NOT NULL
        CHECK (LENGTH(TRIM(title)) > 0),
    description TEXT NOT NULL DEFAULT '',
    state pr_state NOT NULL DEFAULT 'draft',
    base_commit_sha VARCHAR(40)
        REFERENCES commits(commit_sha),
    head_commit_sha VARCHAR(40)
        REFERENCES commits(commit_sha),
    merged_commit_sha VARCHAR(40)
        REFERENCES commits(commit_sha),
    merge_method merge_strategy,
    draft BOOLEAN NOT NULL DEFAULT TRUE,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    merged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_branch_id <> target_branch_id),
    CHECK (
        (state = 'merged' AND merged_at IS NOT NULL
            AND merged_commit_sha IS NOT NULL)
        OR
        (state <> 'merged' AND merged_at IS NULL)
    )
);

CREATE TABLE pull_request_commits (
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,
    commit_sha VARCHAR(40) NOT NULL
        REFERENCES commits(commit_sha),
    position INTEGER NOT NULL CHECK (position > 0),
    PRIMARY KEY (pr_id, commit_sha),
    UNIQUE (pr_id, position)
);

CREATE TABLE review_requests (
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES users(user_id),
    requested_by BIGINT NOT NULL REFERENCES users(user_id),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (pr_id, reviewer_id)
);

-- ============================================================
-- CODE REVIEW
-- ============================================================

CREATE TABLE reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES users(user_id),
    reviewed_commit_sha VARCHAR(40) NOT NULL
        REFERENCES commits(commit_sha),
    state review_state NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed_at TIMESTAMPTZ,
    dismissal_reason TEXT,
    UNIQUE (review_id, pr_id),
    CHECK (
        (state = 'dismissed' AND dismissed_at IS NOT NULL)
        OR
        (state <> 'dismissed' AND dismissed_at IS NULL)
    )
);

CREATE INDEX idx_reviews_pr_latest
ON reviews(pr_id, reviewer_id, submitted_at DESC);

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES reviews(review_id),
    pr_id BIGINT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number > 0),
    comment_body TEXT NOT NULL
        CHECK (LENGTH(TRIM(comment_body)) > 0),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by BIGINT REFERENCES users(user_id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (review_id, pr_id)
        REFERENCES reviews(review_id, pr_id) ON DELETE CASCADE,
    CHECK (
        (resolved = TRUE AND resolved_by IS NOT NULL
            AND resolved_at IS NOT NULL)
        OR
        (resolved = FALSE AND resolved_by IS NULL
            AND resolved_at IS NULL)
    )
);

CREATE INDEX idx_review_comments_unresolved
ON review_comments(pr_id)
WHERE resolved = FALSE;

-- ============================================================
-- STATUS CHECKS
-- ============================================================

CREATE TABLE status_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id) ON DELETE CASCADE,
    check_name VARCHAR(150) NOT NULL,
    commit_sha VARCHAR(40) NOT NULL REFERENCES commits(commit_sha),
    state check_state NOT NULL DEFAULT 'pending',
    details TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (state = 'pending' AND completed_at IS NULL)
        OR
        (state <> 'pending' AND completed_at IS NOT NULL)
    )
);

CREATE INDEX idx_status_checks_pr
ON status_checks(pr_id, check_name, created_at DESC);

CREATE INDEX idx_status_checks_commit
ON status_checks(commit_sha, state);

-- ============================================================
-- BRANCH PROTECTION AND APPROVAL POLICY
-- ============================================================

CREATE TABLE branch_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id) ON DELETE CASCADE,
    required_reviews INTEGER NOT NULL DEFAULT 2
        CHECK (required_reviews >= 0),
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    dismiss_stale_reviews BOOLEAN NOT NULL DEFAULT TRUE,
    enforce_admins BOOLEAN NOT NULL DEFAULT TRUE,
    allow_merge_commit BOOLEAN NOT NULL DEFAULT TRUE,
    allow_squash BOOLEAN NOT NULL DEFAULT TRUE,
    allow_rebase BOOLEAN NOT NULL DEFAULT FALSE,
    bypass_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (policy_id, check_name)
);

CREATE TABLE policy_bypass_audit (
    bypass_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id BIGINT NOT NULL REFERENCES pull_requests(pr_id),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id),
    reason TEXT NOT NULL CHECK (LENGTH(TRIM(reason)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MERGE DECISIONS
-- ============================================================

CREATE TABLE merge_decisions (
    decision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id BIGINT NOT NULL REFERENCES pull_requests(pr_id),
    eligible BOOLEAN NOT NULL,
    approval_count INTEGER NOT NULL DEFAULT 0,
    required_approval_count INTEGER NOT NULL DEFAULT 0,
    evaluated_head_sha VARCHAR(40) REFERENCES commits(commit_sha),
    evaluated_base_sha VARCHAR(40) REFERENCES commits(commit_sha),
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_merge_decisions_pr
ON merge_decisions(pr_id, evaluated_at DESC);

-- ============================================================
-- CI/CD PIPELINE ARCHITECTURE
-- ============================================================

CREATE TABLE pipeline_definitions (
    pipeline_definition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    configuration_version INTEGER NOT NULL DEFAULT 1
        CHECK (configuration_version > 0),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository_id, name)
);

CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_definition_id BIGINT NOT NULL
        REFERENCES pipeline_definitions(pipeline_definition_id)
        ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    stage_order INTEGER NOT NULL CHECK (stage_order > 0),
    parallel_execution BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (pipeline_definition_id, stage_order),
    UNIQUE (pipeline_definition_id, name)
);

CREATE TABLE pipeline_runs (
    pipeline_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_definition_id BIGINT NOT NULL
        REFERENCES pipeline_definitions(pipeline_definition_id),
    pr_id BIGINT REFERENCES pull_requests(pr_id),
    commit_sha VARCHAR(40) NOT NULL REFERENCES commits(commit_sha),
    state pipeline_state NOT NULL DEFAULT 'queued',
    trigger_type VARCHAR(30) NOT NULL
        CHECK (
            trigger_type IN (
                'push',
                'pull_request',
                'manual',
                'schedule',
                'release'
            )
        ),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (state IN ('queued', 'running') AND completed_at IS NULL)
        OR
        (state IN ('success', 'failure', 'cancelled')
            AND completed_at IS NOT NULL)
    )
);

CREATE INDEX idx_pipeline_runs_commit
ON pipeline_runs(commit_sha, created_at DESC);

CREATE INDEX idx_pipeline_runs_pr
ON pipeline_runs(pr_id, state);

CREATE TABLE runners (
    runner_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    runner_name VARCHAR(150) NOT NULL UNIQUE,
    status runner_status NOT NULL DEFAULT 'online',
    capacity INTEGER NOT NULL DEFAULT 1 CHECK (capacity > 0),
    current_jobs INTEGER NOT NULL DEFAULT 0
        CHECK (current_jobs >= 0 AND current_jobs <= capacity),
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE runner_labels (
    runner_id BIGINT NOT NULL
        REFERENCES runners(runner_id) ON DELETE CASCADE,
    label VARCHAR(100) NOT NULL,
    PRIMARY KEY (runner_id, label)
);

CREATE TABLE pipeline_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id) ON DELETE CASCADE,
    stage_id BIGINT NOT NULL REFERENCES pipeline_stages(stage_id),
    job_name VARCHAR(150) NOT NULL,
    state job_state NOT NULL DEFAULT 'queued',
    assigned_runner_id BIGINT REFERENCES runners(runner_id),
    required_labels TEXT[] NOT NULL DEFAULT '{}',
    attempt_number INTEGER NOT NULL DEFAULT 1
        CHECK (attempt_number > 0),
    duration_ms BIGINT CHECK (duration_ms >= 0),
    failure_reason TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pipeline_jobs_queue
ON pipeline_jobs(state, created_at)
WHERE state = 'queued';

CREATE INDEX idx_pipeline_jobs_runner
ON pipeline_jobs(assigned_runner_id, state);

CREATE TABLE pipeline_job_dependencies (
    job_id BIGINT NOT NULL
        REFERENCES pipeline_jobs(job_id) ON DELETE CASCADE,
    depends_on_job_id BIGINT NOT NULL
        REFERENCES pipeline_jobs(job_id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, depends_on_job_id),
    CHECK (job_id <> depends_on_job_id)
);

-- ============================================================
-- ARTIFACTS AND ENVIRONMENTS
-- ============================================================

CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id),
    commit_sha VARCHAR(40) NOT NULL REFERENCES commits(commit_sha),
    artifact_name VARCHAR(250) NOT NULL,
    storage_uri TEXT NOT NULL,
    sha256_digest VARCHAR(64) NOT NULL
        CHECK (sha256_digest ~ '^[0-9a-f]{64}$'),
    size_bytes BIGINT NOT NULL
        CHECK (size_bytes > 0),
    immutable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pipeline_run_id, artifact_name),
    UNIQUE (sha256_digest)
);

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    name deployment_environment NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository_id, name)
);

CREATE TABLE environment_approvals (
    environment_approval_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    decision VARCHAR(20) NOT NULL
        CHECK (decision IN ('approved', 'rejected')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    artifact_id BIGINT NOT NULL REFERENCES artifacts(artifact_id),
    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id),
    state deployment_state NOT NULL DEFAULT 'pending',
    initiated_by BIGINT NOT NULL REFERENCES users(user_id),
    previous_deployment_id BIGINT REFERENCES deployments(deployment_id),
    deployed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployments_environment
ON deployments(environment_id, created_at DESC);

-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT REFERENCES repositories(repository_id),
    actor_id BIGINT REFERENCES users(user_id),
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id BIGINT,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_events_repository
ON audit_events(repository_id, occurred_at DESC);

-- ============================================================
-- UPDATED TIMESTAMP TRIGGER
-- ============================================================

CREATE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pr_updated_at
BEFORE UPDATE ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- REVIEW ELIGIBILITY TRIGGER
-- ============================================================

CREATE FUNCTION validate_review_submission()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_author BIGINT;
    v_repository BIGINT;
    v_head VARCHAR(40);
    v_role VARCHAR(30);
    v_active BOOLEAN;
    v_is_member BOOLEAN;
BEGIN
    SELECT author_id, repository_id, head_commit_sha
    INTO v_author, v_repository, v_head
    FROM pull_requests
    WHERE pr_id = NEW.pr_id
      AND state = 'open';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Reviews require an open Pull Request';
            USING ERRCODE = '23514';
    END IF;

    IF NEW.reviewer_id = v_author THEN
        RAISE EXCEPTION 'Self-approval is prohibited';
            USING ERRCODE = '42501';
    END IF;

    IF NEW.reviewed_commit_sha <> v_head THEN
        RAISE EXCEPTION 'Review must reference current PR head';
            USING ERRCODE = '23514';
    END IF;

    SELECT repository_role, u.active
    INTO v_role, v_active
    FROM repository_members rm
    JOIN users u ON u.user_id = rm.user_id
    WHERE rm.repository_id = v_repository
      AND rm.user_id = NEW.reviewer_id;

    IF NOT FOUND OR NOT v_active THEN
        RAISE EXCEPTION 'Reviewer is not an active repository member';
            USING ERRCODE = '42501';
    END IF;

    IF v_role NOT IN ('reviewer', 'maintainer', 'admin') THEN
        RAISE EXCEPTION 'Repository role cannot review changes';
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_review
BEFORE INSERT ON reviews
FOR EACH ROW
EXECUTE FUNCTION validate_review_submission();

-- ============================================================
-- STALE APPROVAL INVALIDATION
-- ============================================================

CREATE FUNCTION dismiss_stale_approvals()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy BOOLEAN;
BEGIN
    SELECT bpp.dismiss_stale_reviews
    INTO v_policy
    FROM pull_requests pr
    JOIN branch_protection_policies bpp
      ON bpp.branch_id = pr.target_branch_id
    WHERE pr.pr_id = NEW.pr_id;

    IF COALESCE(v_policy, FALSE) THEN
        UPDATE reviews
        SET state = 'dismissed',
            dismissed_at = NOW(),
            dismissal_reason = 'New commit changed reviewed revision'
        WHERE pr_id = NEW.pr_id
          AND state = 'approved';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_dismiss_stale_approvals
AFTER INSERT ON pull_request_commits
FOR EACH ROW
EXECUTE FUNCTION dismiss_stale_approvals();

-- ============================================================
-- RUNNER CAPACITY ACCOUNTING
-- ============================================================

CREATE FUNCTION update_runner_job_capacity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.state = 'running'
           AND NEW.state <> 'running'
           AND OLD.assigned_runner_id IS NOT NULL THEN

            UPDATE runners
            SET current_jobs = GREATEST(current_jobs - 1, 0)
            WHERE runner_id = OLD.assigned_runner_id;

        ELSIF OLD.state <> 'running'
          AND NEW.state = 'running'
          AND NEW.assigned_runner_id IS NOT NULL THEN

            UPDATE runners
            SET current_jobs = current_jobs + 1
            WHERE runner_id = NEW.assigned_runner_id
              AND status = 'online'
              AND current_jobs < capacity;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Runner unavailable or at capacity';
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_runner_capacity
AFTER UPDATE OF state ON pipeline_jobs
FOR EACH ROW
EXECUTE FUNCTION update_runner_job_capacity();

-- ============================================================
-- MERGE ELIGIBILITY FUNCTION
-- ============================================================

CREATE FUNCTION evaluate_merge_eligibility(p_pr_id BIGINT)
RETURNS TABLE (
    eligible BOOLEAN,
    approval_count BIGINT,
    required_approvals INTEGER,
    reasons JSONB
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pr pull_requests%ROWTYPE;
    v_policy branch_protection_policies%ROWTYPE;
    v_source_head VARCHAR(40);
    v_target_head VARCHAR(40);
    v_approval_count BIGINT := 0;
    v_reasons JSONB := '[]'::jsonb;
    v_required TEXT;
    v_check_exists BOOLEAN;
BEGIN
    SELECT *
    INTO v_pr
    FROM pull_requests
    WHERE pr_id = p_pr_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pull Request % not found', p_pr_id;
    END IF;

    IF v_pr.state <> 'open' THEN
        RETURN QUERY SELECT
            FALSE,
            0::BIGINT,
            0,
            jsonb_build_array('Pull Request is not open');
        RETURN;
    END IF;

    SELECT *
    INTO v_policy
    FROM branch_protection_policies
    WHERE branch_id = v_pr.target_branch_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            0::BIGINT,
            0,
            jsonb_build_array('No branch protection policy');
        RETURN;
    END IF;

    SELECT head_commit_sha
    INTO v_source_head
    FROM branches
    WHERE branch_id = v_pr.source_branch_id;

    SELECT head_commit_sha
    INTO v_target_head
    FROM branches
    WHERE branch_id = v_pr.target_branch_id;

    IF v_source_head IS DISTINCT FROM v_pr.head_commit_sha THEN
        v_reasons := v_reasons ||
            jsonb_build_array('PR head does not match source branch head');
    END IF;

    IF v_target_head IS DISTINCT FROM v_pr.base_commit_sha THEN
        v_reasons := v_reasons ||
            jsonb_build_array('Target branch changed; synchronize PR');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pull_request_commits
        WHERE pr_id = p_pr_id
    ) THEN
        v_reasons := v_reasons ||
            jsonb_build_array('No proposed commits');
    END IF;

    -- Count only the latest review from each eligible reviewer.
    -- Approvals are tied to the current source head.
    WITH latest_reviews AS (
        SELECT DISTINCT ON (r.reviewer_id)
            r.reviewer_id,
            r.state,
            r.reviewed_commit_sha
        FROM reviews r
        WHERE r.pr_id = p_pr_id
        ORDER BY r.reviewer_id, r.submitted_at DESC, r.review_id DESC
    )
    SELECT COUNT(*)
    INTO v_approval_count
    FROM latest_reviews lr
    JOIN repository_members rm
      ON rm.user_id = lr.reviewer_id
     AND rm.repository_id = v_pr.repository_id
    JOIN users u ON u.user_id = lr.reviewer_id
    WHERE lr.state = 'approved'
      AND lr.reviewed_commit_sha = v_source_head
      AND u.active = TRUE
      AND rm.repository_role IN ('reviewer', 'maintainer', 'admin')
      AND lr.reviewer_id <> v_pr.author_id;

    IF v_approval_count < v_policy.required_reviews THEN
        v_reasons := v_reasons ||
            jsonb_build_array(
                format(
                    'Insufficient approvals: %s/%s',
                    v_approval_count,
                    v_policy.required_reviews
                )
            );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            SELECT DISTINCT ON (r.reviewer_id)
                r.reviewer_id,
                r.state,
                r.reviewed_commit_sha
            FROM reviews r
            WHERE r.pr_id = p_pr_id
            ORDER BY r.reviewer_id,
                     r.submitted_at DESC,
                     r.review_id DESC
        ) latest
        WHERE latest.state = 'changes_requested'
          AND latest.reviewed_commit_sha = v_source_head
    ) THEN
        v_reasons := v_reasons ||
            jsonb_build_array('Active changes-requested review exists');
    END IF;

    -- Every configured required check must succeed against
    -- the current source branch head.
    FOR v_required IN
        SELECT rsc.check_name
        FROM required_status_checks rsc
        WHERE rsc.policy_id = v_policy.policy_id
    LOOP
        SELECT EXISTS (
            SELECT 1
            FROM status_checks sc
            WHERE sc.pr_id = p_pr_id
              AND sc.check_name = v_required
              AND sc.commit_sha = v_source_head
              AND sc.state = 'success'
              AND sc.created_at = (
                  SELECT MAX(sc2.created_at)
                  FROM status_checks sc2
                  WHERE sc2.pr_id = p_pr_id
                    AND sc2.check_name = v_required
                    AND sc2.commit_sha = v_source_head
              )
        )
        INTO v_check_exists;

        IF NOT v_check_exists THEN
            v_reasons := v_reasons ||
                jsonb_build_array(
                    'Required status check missing or unsuccessful: '
                    || v_required
                );
        END IF;
    END LOOP;

    IF v_policy.require_conversation_resolution
       AND EXISTS (
           SELECT 1
           FROM review_comments rc
           WHERE rc.pr_id = p_pr_id
             AND rc.resolved = FALSE
       ) THEN
        v_reasons := v_reasons ||
            jsonb_build_array('Unresolved review conversations exist');
    END IF;

    RETURN QUERY SELECT
        jsonb_array_length(v_reasons) = 0,
        v_approval_count,
        v_policy.required_reviews,
        v_reasons;
END;
$$;

-- ============================================================
-- MERGE PROCEDURE
-- ============================================================

CREATE PROCEDURE merge_pull_request(
    p_pr_id BIGINT,
    p_user_id BIGINT,
    p_strategy merge_strategy
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pr pull_requests%ROWTYPE;
    v_policy branch_protection_policies%ROWTYPE;
    v_eligible BOOLEAN;
    v_reasons JSONB;
    v_new_sha VARCHAR(40);
    v_repository BIGINT;
    v_bypass BOOLEAN;
BEGIN
    SELECT *
    INTO v_pr
    FROM pull_requests
    WHERE pr_id = p_pr_id
    FOR UPDATE;

    IF NOT FOUND OR v_pr.state <> 'open' THEN
        RAISE EXCEPTION 'Pull Request is not open';
    END IF;

    SELECT *
    INTO v_policy
    FROM branch_protection_policies
    WHERE branch_id = v_pr.target_branch_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target branch has no protection policy';
    END IF;

    SELECT can_bypass_protection
    INTO v_bypass
    FROM repository_members
    WHERE repository_id = v_pr.repository_id
      AND user_id = p_user_id
      AND repository_role = 'admin';

    v_bypass := COALESCE(v_bypass, FALSE);

    IF p_strategy = 'squash' AND NOT v_policy.allow_squash THEN
        RAISE EXCEPTION 'Squash merging is disabled';
    END IF;

    IF p_strategy = 'merge_commit'
       AND NOT v_policy.allow_merge_commit THEN
        RAISE EXCEPTION 'Merge commits are disabled';
    END IF;

    IF p_strategy = 'rebase' AND NOT v_policy.allow_rebase THEN
        RAISE EXCEPTION 'Rebase merging is disabled';
    END IF;

    SELECT eligible, reasons
    INTO v_eligible, v_reasons
    FROM evaluate_merge_eligibility(p_pr_id);

    IF NOT v_eligible
       AND NOT (
           v_bypass
           AND v_policy.bypass_enabled
           AND (
               NOT v_policy.enforce_admins
           )
       ) THEN
        INSERT INTO merge_decisions (
            pr_id,
            eligible,
            reasons
        )
        VALUES (
            p_pr_id,
            FALSE,
            v_reasons
        );

        RAISE EXCEPTION 'Merge blocked: %', v_reasons;
    END IF;

    -- This identifier is an illustrative database-level merge record.
    -- Real Git object creation belongs to the repository hosting service.
    v_new_sha := encode(
        digest(
            v_pr.pr_id::TEXT ||
            v_pr.head_commit_sha ||
            v_pr.base_commit_sha ||
            p_strategy::TEXT ||
            clock_timestamp()::TEXT,
            'sha256'
        ),
        'hex'
    );

    INSERT INTO commits (
        commit_sha,
        repository_id,
        author_id,
        message
    )
    VALUES (
        v_new_sha,
        v_pr.repository_id,
        p_user_id,
        'Merge PR #' || p_pr_id || ': ' || v_pr.title
    );

    INSERT INTO branch_commits (
        branch_id,
        commit_sha,
        position
    )
    SELECT
        v_pr.target_branch_id,
        v_new_sha,
        COALESCE(MAX(position), 0) + 1
    FROM branch_commits
    WHERE branch_id = v_pr.target_branch_id;

    UPDATE branches
    SET head_commit_sha = v_new_sha
    WHERE branch_id = v_pr.target_branch_id;

    UPDATE pull_requests
    SET state = 'merged',
        merged_commit_sha = v_new_sha,
        merge_method = p_strategy,
        merged_at = NOW(),
        closed_at = NOW()
    WHERE pr_id = p_pr_id;

    INSERT INTO merge_decisions (
        pr_id,
        eligible,
        approval_count,
        required_approval_count,
        evaluated_head_sha,
        evaluated_base_sha,
        reasons
    )
    SELECT
        p_pr_id,
        TRUE,
        approval_count,
        required_approvals,
        v_pr.head_commit_sha,
        v_pr.base_commit_sha,
        reasons
    FROM evaluate_merge_eligibility(p_pr_id);

    INSERT INTO audit_events (
        repository_id,
        actor_id,
        event_type,
        entity_type,
        entity_id,
        event_data
    )
    VALUES (
        v_pr.repository_id,
        p_user_id,
        'pull_request_merged',
        'pull_request',
        p_pr_id,
        jsonb_build_object(
            'strategy', p_strategy,
            'merged_commit', v_new_sha
        )
    );
END;
$$;

-- ============================================================
-- PIPELINE JOB ASSIGNMENT FUNCTION
-- ============================================================

CREATE FUNCTION assign_pipeline_job(
    p_job_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_job pipeline_jobs%ROWTYPE;
    v_runner BIGINT;
BEGIN
    SELECT *
    INTO v_job
    FROM pipeline_jobs
    WHERE job_id = p_job_id
      AND state = 'queued'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job is not queued';
    END IF;

    SELECT r.runner_id
    INTO v_runner
    FROM runners r
    WHERE r.status = 'online'
      AND r.current_jobs < r.capacity
      AND NOT EXISTS (
          SELECT 1
          FROM unnest(v_job.required_labels) AS required(label)
          WHERE NOT EXISTS (
              SELECT 1
              FROM runner_labels rl
              WHERE rl.runner_id = r.runner_id
                AND rl.label = required.label
          )
      )
    ORDER BY r.current_jobs, r.runner_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    UPDATE pipeline_jobs
    SET state = 'running',
        assigned_runner_id = v_runner,
        started_at = NOW()
    WHERE job_id = p_job_id;

    RETURN v_runner;
END;
$$;

-- ============================================================
-- REPORTING VIEW: LATEST REVIEW STATE
-- ============================================================

CREATE VIEW latest_review_states AS
SELECT DISTINCT ON (r.pr_id, r.reviewer_id)
    r.pr_id,
    r.reviewer_id,
    u.username,
    r.state,
    r.reviewed_commit_sha,
    r.submitted_at
FROM reviews r
JOIN users u ON u.user_id = r.reviewer_id
ORDER BY
    r.pr_id,
    r.reviewer_id,
    r.submitted_at DESC,
    r.review_id DESC;

-- ============================================================
-- REPORTING VIEW: MERGE READINESS
-- ============================================================

CREATE VIEW pull_request_merge_report AS
SELECT
    pr.pr_id,
    repo.name AS repository,
    pr.title,
    pr.state,
    source.name AS source_branch,
    target.name AS target_branch,
    author.username AS author,
    pr.head_commit_sha,
    pr.base_commit_sha,
    COALESCE(approvals.approval_count, 0) AS approval_count,
    COALESCE(policy.required_reviews, 0) AS required_reviews,
    COALESCE(checks.successful_checks, 0) AS successful_checks,
    COALESCE(checks.required_checks, 0) AS required_checks,
    COALESCE(comments.unresolved_count, 0) AS unresolved_comments
FROM pull_requests pr
JOIN repositories repo
  ON repo.repository_id = pr.repository_id
JOIN branches source
  ON source.branch_id = pr.source_branch_id
JOIN branches target
  ON target.branch_id = pr.target_branch_id
JOIN users author
  ON author.user_id = pr.author_id
LEFT JOIN branch_protection_policies policy
  ON policy.branch_id = pr.target_branch_id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS approval_count
    FROM latest_review_states lr
    JOIN repository_members rm
      ON rm.repository_id = pr.repository_id
     AND rm.user_id = lr.reviewer_id
    WHERE lr.pr_id = pr.pr_id
      AND lr.state = 'approved'
      AND lr.reviewed_commit_sha = pr.head_commit_sha
      AND rm.repository_role IN ('reviewer', 'maintainer', 'admin')
      AND lr.reviewer_id <> pr.author_id
) approvals ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (
            WHERE sc.state = 'success'
              AND sc.commit_sha = pr.head_commit_sha
        ) AS successful_checks,
        COUNT(DISTINCT required.check_name) AS required_checks
    FROM branch_protection_policies bp
    LEFT JOIN required_status_checks required
      ON required.policy_id = bp.policy_id
    LEFT JOIN status_checks sc
      ON sc.pr_id = pr.pr_id
     AND sc.check_name = required.check_name
    WHERE bp.branch_id = pr.target_branch_id
) checks ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS unresolved_count
    FROM review_comments rc
    WHERE rc.pr_id = pr.pr_id
      AND rc.resolved = FALSE
) comments ON TRUE;

-- ============================================================
-- SAMPLE DATA
-- ============================================================

INSERT INTO users (username, email)
VALUES
    ('admin', 'admin@example.com'),
    ('developer', 'developer@example.com'),
    ('alice', 'alice@example.com'),
    ('bob', 'bob@example.com'),
    ('security-engineer', 'security@example.com'),
    ('release-manager', 'release@example.com');

INSERT INTO repositories (
    name,
    owner_id,
    default_branch,
    visibility
)
VALUES (
    'payment-platform',
    (SELECT user_id FROM users WHERE username = 'admin'),
    'main',
    'private'
);

INSERT INTO repository_members (
    repository_id,
    user_id,
    repository_role,
    can_bypass_protection
)
SELECT
    repo.repository_id,
    u.user_id,
    membership.role,
    membership.bypass
FROM repositories repo
CROSS JOIN (
    VALUES
        ('admin', 'admin', TRUE),
        ('developer', 'developer', FALSE),
        ('alice', 'reviewer', FALSE),
        ('bob', 'maintainer', FALSE),
        ('security-engineer', 'reviewer', FALSE),
        ('release-manager', 'maintainer', FALSE)
) AS membership(username, role, bypass)
JOIN users u ON u.username = membership.username;

INSERT INTO branches (
    repository_id,
    name,
    is_default,
    is_protected
)
SELECT repository_id, 'main', TRUE, TRUE
FROM repositories;

INSERT INTO branches (
    repository_id,
    name
)
SELECT repository_id, 'feature/payment-validation'
FROM repositories;

INSERT INTO branches (
    repository_id,
    name
)
SELECT repository_id, 'feature/observability'
FROM repositories;

INSERT INTO commits (
    commit_sha,
    repository_id,
    author_id,
    message
)
SELECT
    'aaaaaaa',
    repo.repository_id,
    u.user_id,
    'Initial payment platform release'
FROM repositories repo
JOIN users u ON u.username = 'admin';

INSERT INTO commits (
    commit_sha,
    repository_id,
    author_id,
    message
)
SELECT
    'bbbbbbb',
    repo.repository_id,
    u.user_id,
    'Implement payment validation'
FROM repositories repo
JOIN users u ON u.username = 'developer';

INSERT INTO commits (
    commit_sha,
    repository_id,
    author_id,
    message
)
SELECT
    'ccccccc',
    repo.repository_id,
    u.user_id,
    'Improve structured logging'
FROM repositories repo
JOIN users u ON u.username = 'developer';

INSERT INTO branch_commits (
    branch_id,
    commit_sha,
    position
)
SELECT
    b.branch_id,
    'aaaaaaa',
    1
FROM branches b
WHERE b.name = 'main';

UPDATE branches
SET head_commit_sha = 'aaaaaaa'
WHERE name = 'main';

INSERT INTO branch_commits (
    branch_id,
    commit_sha,
    position
)
SELECT
    b.branch_id,
    'aaaaaaa',
    1
FROM branches b
WHERE b.name = 'feature/payment-validation';

INSERT INTO branch_commits (
    branch_id,
    commit_sha,
    position
)
SELECT
    b.branch_id,
    'bbbbbbb',
    2
FROM branches b
WHERE b.name = 'feature/payment-validation';

UPDATE branches
SET head_commit_sha = 'bbbbbbb'
WHERE name = 'feature/payment-validation';

INSERT INTO branch_commits (
    branch_id,
    commit_sha,
    position
)
SELECT
    b.branch_id,
    'aaaaaaa',
    1
FROM branches b
WHERE b.name = 'feature/observability';

INSERT INTO branch_commits (
    branch_id,
    commit_sha,
    position
)
SELECT
    b.branch_id,
    'ccccccc',
    2
FROM branches b
WHERE b.name = 'feature/observability';

UPDATE branches
SET head_commit_sha = 'ccccccc'
WHERE name = 'feature/observability';

INSERT INTO branch_protection_policies (
    branch_id,
    required_reviews,
    require_conversation_resolution,
    require_linear_history,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    dismiss_stale_reviews,
    enforce_admins,
    allow_merge_commit,
    allow_squash,
    allow_rebase,
    bypass_enabled
)
SELECT
    branch_id,
    2,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    FALSE
FROM branches
WHERE name = 'main';

INSERT INTO required_status_checks (
    policy_id,
    check_name
)
SELECT policy_id, required.check_name
FROM branch_protection_policies
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('build')
) AS required(check_name);

-- A valid open Pull Request.

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    description,
    state,
    base_commit_sha,
    head_commit_sha,
    draft,
    opened_at
)
SELECT
    repo.repository_id,
    source.branch_id,
    target.branch_id,
    author.user_id,
    'Implement payment validation',
    'Adds input validation and transaction safeguards.',
    'open',
    'aaaaaaa',
    'bbbbbbb',
    FALSE,
    NOW()
FROM repositories repo
JOIN branches source
  ON source.repository_id = repo.repository_id
 AND source.name = 'feature/payment-validation'
JOIN branches target
  ON target.repository_id = repo.repository_id
 AND target.name = 'main'
JOIN users author
  ON author.username = 'developer';

INSERT INTO pull_request_commits (
    pr_id,
    commit_sha,
    position
)
SELECT pr_id, 'bbbbbbb', 1
FROM pull_requests
WHERE title = 'Implement payment validation';

INSERT INTO review_requests (
    pr_id,
    reviewer_id,
    requested_by
)
SELECT
    pr.pr_id,
    reviewer.user_id,
    author.user_id
FROM pull_requests pr
JOIN users author ON author.username = 'developer'
CROSS JOIN users reviewer
WHERE pr.title = 'Implement payment validation'
  AND reviewer.username IN ('alice', 'bob');

-- A second PR with an incomplete review workflow.

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    description,
    state,
    base_commit_sha,
    head_commit_sha,
    draft,
    opened_at
)
SELECT
    repo.repository_id,
    source.branch_id,
    target.branch_id,
    author.user_id,
    'Improve application observability',
    'Adds structured application logging.',
    'open',
    'aaaaaaa',
    'ccccccc',
    FALSE,
    NOW()
FROM repositories repo
JOIN branches source
  ON source.repository_id = repo.repository_id
 AND source.name = 'feature/observability'
JOIN branches target
  ON target.repository_id = repo.repository_id
 AND target.name = 'main'
JOIN users author ON author.username = 'developer';

INSERT INTO pull_request_commits (
    pr_id,
    commit_sha,
    position
)
SELECT pr_id, 'ccccccc', 1
FROM pull_requests
WHERE title = 'Improve application observability';

-- Valid review decisions for the payment PR.

INSERT INTO reviews (
    pr_id,
    reviewer_id,
    reviewed_commit_sha,
    state,
    body
)
SELECT
    pr.pr_id,
    u.user_id,
    'bbbbbbb',
    'approved',
    'Input validation and error handling are correct.'
FROM pull_requests pr
JOIN users u ON u.username = 'alice'
WHERE pr.title = 'Implement payment validation';

INSERT INTO reviews (
    pr_id,
    reviewer_id,
    reviewed_commit_sha,
    state,
    body
)
SELECT
    pr.pr_id,
    u.user_id,
    'bbbbbbb',
    'approved',
    'Security controls and data handling reviewed.'
FROM pull_requests pr
JOIN users u ON u.username = 'bob'
WHERE pr.title = 'Implement payment validation';

-- An inline review conversation.

INSERT INTO review_comments (
    review_id,
    pr_id,
    file_path,
    line_number,
    comment_body,
    resolved
)
SELECT
    r.review_id,
    r.pr_id,
    'src/payment.py',
    42,
    'Please confirm that the validation also rejects negative amounts.',
    FALSE
FROM reviews r
JOIN pull_requests pr ON pr.pr_id = r.pr_id
JOIN users u ON u.user_id = r.reviewer_id
WHERE pr.title = 'Implement payment validation'
  AND u.username = 'alice';

-- Resolve the conversation after the requested modification.

UPDATE review_comments
SET resolved = TRUE,
    resolved_by = (
        SELECT user_id FROM users WHERE username = 'developer'
    ),
    resolved_at = NOW()
WHERE pr_id = (
    SELECT pr_id
    FROM pull_requests
    WHERE title = 'Implement payment validation'
);

-- Required successful status checks against the current head.

INSERT INTO status_checks (
    pr_id,
    check_name,
    commit_sha,
    state,
    details,
    started_at,
    completed_at
)
SELECT
    pr.pr_id,
    required.check_name,
    'bbbbbbb',
    'success',
    'Completed successfully.',
    NOW() - INTERVAL '2 minutes',
    NOW()
FROM pull_requests pr
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('build')
) AS required(check_name)
WHERE pr.title = 'Implement payment validation';

-- Incomplete PR: pending check and insufficient approval.

INSERT INTO status_checks (
    pr_id,
    check_name,
    commit_sha,
    state,
    details
)
SELECT
    pr.pr_id,
    'unit-tests',
    'ccccccc',
    'pending',
    'Waiting for test execution.'
FROM pull_requests pr
WHERE pr.title = 'Improve application observability';

-- ============================================================
-- CI/CD PIPELINE SAMPLE
-- ============================================================

INSERT INTO pipeline_definitions (
    repository_id,
    name
)
SELECT repository_id, 'payment-platform-ci'
FROM repositories;

INSERT INTO pipeline_stages (
    pipeline_definition_id,
    name,
    stage_order,
    parallel_execution
)
SELECT
    pipeline_definition_id,
    stage.name,
    stage.stage_order,
    stage.parallel_execution
FROM pipeline_definitions
CROSS JOIN (
    VALUES
        ('validation', 1, TRUE),
        ('testing', 2, TRUE),
        ('build', 3, FALSE),
        ('security', 4, TRUE)
) AS stage(name, stage_order, parallel_execution);

INSERT INTO pipeline_runs (
    pipeline_definition_id,
    pr_id,
    commit_sha,
    state,
    trigger_type,
    started_at,
    completed_at
)
SELECT
    pd.pipeline_definition_id,
    pr.pr_id,
    'bbbbbbb',
    'success',
    'pull_request',
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '1 minute'
FROM pipeline_definitions pd
JOIN pull_requests pr
  ON pr.title = 'Implement payment validation';

INSERT INTO runners (
    runner_name,
    status,
    capacity,
    current_jobs
)
VALUES
    ('ubuntu-runner-01', 'online', 4, 0),
    ('docker-runner-01', 'online', 2, 0),
    ('offline-runner-01', 'offline', 2, 0);

INSERT INTO runner_labels (runner_id, label)
SELECT runner_id, label
FROM runners
CROSS JOIN (
    VALUES
        ('ubuntu-runner-01', 'linux'),
        ('ubuntu-runner-01', 'python'),
        ('ubuntu-runner-01', 'docker'),
        ('docker-runner-01', 'linux'),
        ('docker-runner-01', 'docker'),
        ('offline-runner-01', 'linux')
) AS labels(runner_name, label)
WHERE runners.runner_name = labels.runner_name;

INSERT INTO pipeline_jobs (
    pipeline_run_id,
    stage_id,
    job_name,
    state,
    required_labels,
    duration_ms,
    started_at,
    completed_at
)
SELECT
    run.pipeline_run_id,
    stage.stage_id,
    job.job_name,
    'success',
    job.labels,
    job.duration,
    NOW() - INTERVAL '5 minutes',
    NOW() - INTERVAL '1 minute'
FROM pipeline_runs run
JOIN pipeline_stages stage
  ON stage.pipeline_definition_id = run.pipeline_definition_id
CROSS JOIN (
    VALUES
        ('validation', 'lint', ARRAY['linux', 'python']::TEXT[], 12000),
        ('testing', 'unit-tests', ARRAY['linux', 'python']::TEXT[], 35000),
        ('build', 'container-build', ARRAY['linux', 'docker']::TEXT[], 50000),
        ('security', 'security-scan', ARRAY['linux', 'python']::TEXT[], 18000)
) AS job(stage_name, job_name, labels, duration)
WHERE stage.name = job.stage_name;

-- ============================================================
-- ARTIFACTS AND DEPLOYMENT CONFIGURATION
-- ============================================================

INSERT INTO artifacts (
    pipeline_run_id,
    commit_sha,
    artifact_name,
    storage_uri,
    sha256_digest,
    size_bytes,
    immutable
)
SELECT
    pipeline_run_id,
    'bbbbbbb',
    'payment-service.tar',
    's3://cicd-artifacts/payment-service.tar',
    encode(digest('payment-service-build-v1', 'sha256'), 'hex'),
    1048576,
    TRUE
FROM pipeline_runs
LIMIT 1;

INSERT INTO environments (
    repository_id,
    name,
    requires_approval,
    protected
)
SELECT
    repository_id,
    env.name::deployment_environment,
    env.requires_approval,
    env.protected
FROM repositories
CROSS JOIN (
    VALUES
        ('development', FALSE, FALSE),
        ('staging', FALSE, TRUE),
        ('production', TRUE, TRUE)
) AS env(name, requires_approval, protected);

INSERT INTO environment_approvals (
    environment_id,
    user_id,
    decision,
    reason
)
SELECT
    e.environment_id,
    u.user_id,
    'approved',
    'Production release approved by release management.'
FROM environments e
JOIN repositories repo
  ON repo.repository_id = e.repository_id
JOIN users u ON u.username = 'release-manager'
WHERE e.name = 'production';

INSERT INTO deployments (
    environment_id,
    artifact_id,
    pipeline_run_id,
    state,
    initiated_by,
    deployed_at,
    completed_at
)
SELECT
    e.environment_id,
    a.artifact_id,
    a.pipeline_run_id,
    'succeeded',
    u.user_id,
    NOW() - INTERVAL '30 minutes',
    NOW() - INTERVAL '29 minutes'
FROM environments e
JOIN artifacts a ON a.artifact_name = 'payment-service.tar'
JOIN users u ON u.username = 'release-manager'
WHERE e.name = 'staging';

COMMIT;

-- ============================================================
-- RETRIEVAL
-- ============================================================

SELECT
    pr_id,
    title,
    state,
    source_branch,
    target_branch,
    author
FROM pull_request_merge_report
ORDER BY pr_id;

-- ============================================================
-- REVIEW HISTORY
-- ============================================================

SELECT
    pr_id,
    username,
    state,
    reviewed_commit_sha,
    submitted_at
FROM latest_review_states
ORDER BY pr_id, username;

-- ============================================================
-- MERGE ELIGIBILITY EVALUATION
-- ============================================================

SELECT
    pr.pr_id,
    pr.title,
    evaluation.eligible,
    evaluation.approval_count,
    evaluation.required_approvals,
    evaluation.reasons
FROM pull_requests pr
CROSS JOIN LATERAL evaluate_merge_eligibility(pr.pr_id)
    AS evaluation
ORDER BY pr.pr_id;

-- ============================================================
-- AGGREGATION: PIPELINE PERFORMANCE
-- ============================================================

SELECT
    pd.name AS pipeline,
    COUNT(DISTINCT run.pipeline_run_id) AS pipeline_runs,
    COUNT(job.job_id) AS total_jobs,
    COUNT(job.job_id) FILTER (
        WHERE job.state = 'success'
    ) AS successful_jobs,
    COUNT(job.job_id) FILTER (
        WHERE job.state = 'failure'
    ) AS failed_jobs,
    ROUND(
        AVG(job.duration_ms)::NUMERIC,
        2
    ) AS average_job_duration_ms
FROM pipeline_definitions pd
LEFT JOIN pipeline_runs run
    ON run.pipeline_definition_id = pd.pipeline_definition_id
LEFT JOIN pipeline_jobs job
    ON job.pipeline_run_id = run.pipeline_run_id
GROUP BY pd.pipeline_definition_id, pd.name;

-- ============================================================
-- RUNNER CAPACITY REPORT
-- ============================================================

SELECT
    r.runner_name,
    r.status,
    r.capacity,
    r.current_jobs,
    r.capacity - r.current_jobs AS available_slots,
    ARRAY_AGG(rl.label ORDER BY rl.label)
        FILTER (WHERE rl.label IS NOT NULL) AS labels
FROM runners r
LEFT JOIN runner_labels rl
    ON rl.runner_id = r.runner_id
GROUP BY
    r.runner_id,
    r.runner_name,
    r.status,
    r.capacity,
    r.current_jobs
ORDER BY r.runner_name;

-- ============================================================
-- ARTIFACT INVENTORY
-- ============================================================

SELECT
    a.artifact_name,
    a.sha256_digest,
    a.commit_sha,
    a.size_bytes,
    a.immutable,
    a.created_at
FROM artifacts a
ORDER BY a.created_at DESC;

-- ============================================================
-- DEPLOYMENT REPORT
-- ============================================================

SELECT
    repo.name AS repository,
    e.name AS environment,
    d.deployment_id,
    d.state,
    a.artifact_name,
    a.sha256_digest,
    d.deployed_at,
    d.completed_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN artifacts a
    ON a.artifact_id = d.artifact_id
JOIN repositories repo
    ON repo.repository_id = e.repository_id
ORDER BY d.created_at DESC;

-- ============================================================
-- VALIDATION: STALE APPROVALS
-- ============================================================

SELECT
    pr.pr_id,
    pr.title,
    r.reviewer_id,
    r.reviewed_commit_sha,
    pr.head_commit_sha,
    r.state
FROM reviews r
JOIN pull_requests pr ON pr.pr_id = r.pr_id
WHERE r.state = 'approved'
  AND r.reviewed_commit_sha <> pr.head_commit_sha;

-- ============================================================
-- VALIDATION: FAILED OR MISSING CHECKS
-- ============================================================

SELECT
    pr.pr_id,
    pr.title,
    required.check_name,
    sc.state,
    sc.commit_sha
FROM pull_requests pr
JOIN branches b ON b.branch_id = pr.target_branch_id
JOIN branch_protection_policies bp ON bp.branch_id = b.branch_id
JOIN required_status_checks required
    ON required.policy_id = bp.policy_id
LEFT JOIN LATERAL (
    SELECT state, commit_sha
    FROM status_checks
    WHERE pr_id = pr.pr_id
      AND check_name = required.check_name
    ORDER BY created_at DESC
    LIMIT 1
) sc ON TRUE
WHERE sc.state IS DISTINCT FROM 'success'
   OR sc.commit_sha IS DISTINCT FROM pr.head_commit_sha;

-- ============================================================
-- VALIDATION: UNRESOLVED CONVERSATIONS
-- ============================================================

SELECT
    pr.pr_id,
    pr.title,
    rc.comment_id,
    rc.file_path,
    rc.line_number,
    rc.comment_body
FROM review_comments rc
JOIN pull_requests pr ON pr.pr_id = rc.pr_id
WHERE rc.resolved = FALSE;

-- ============================================================
-- WORKFLOW PROCESSING: CLAIM A RUNNER JOB
-- ============================================================

-- Returns NULL if no online compatible runner has capacity.
-- Execute inside a transaction when assigning several jobs.

SELECT assign_pipeline_job(
    (
        SELECT job_id
        FROM pipeline_jobs
        WHERE state = 'queued'
        ORDER BY created_at
        LIMIT 1
    )
);

-- ============================================================
-- WORKFLOW PROCESSING: COMPLETE A JOB
-- ============================================================

BEGIN;

UPDATE pipeline_jobs
SET state = 'success',
    duration_ms = 12500,
    completed_at = NOW()
WHERE job_id = (
    SELECT job_id
    FROM pipeline_jobs
    WHERE state = 'running'
    ORDER BY started_at
    LIMIT 1
);

COMMIT;

-- ============================================================
-- ELIGIBILITY: ENVIRONMENT DEPLOYMENT
-- ============================================================

SELECT
    e.name,
    e.requires_approval,
    e.protected,
    EXISTS (
        SELECT 1
        FROM environment_approvals ea
        WHERE ea.environment_id = e.environment_id
          AND ea.decision = 'approved'
    ) AS has_approval,
    CASE
        WHEN e.requires_approval AND NOT EXISTS (
            SELECT 1
            FROM environment_approvals ea
            WHERE ea.environment_id = e.environment_id
              AND ea.decision = 'approved'
        )
        THEN FALSE
        ELSE TRUE
    END AS approval_eligible
FROM environments e
ORDER BY e.environment_id;

-- ============================================================
-- CTE: PR REVIEW AND CHECK SUMMARY
-- ============================================================

WITH review_summary AS (
    SELECT
        pr_id,
        COUNT(*) FILTER (
            WHERE state = 'approved'
        ) AS approved_reviews,
        COUNT(*) FILTER (
            WHERE state = 'changes_requested'
        ) AS requested_changes
    FROM latest_review_states
    GROUP BY pr_id
),
check_summary AS (
    SELECT
        pr_id,
        COUNT(*) FILTER (
            WHERE state = 'success'
        ) AS successful_checks,
        COUNT(*) FILTER (
            WHERE state = 'failure'
        ) AS failed_checks,
        COUNT(*) FILTER (
            WHERE state = 'pending'
        ) AS pending_checks
    FROM status_checks
    GROUP BY pr_id
)
SELECT
    pr.pr_id,
    pr.title,
    COALESCE(rs.approved_reviews, 0) AS approvals,
    COALESCE(rs.requested_changes, 0) AS change_requests,
    COALESCE(cs.successful_checks, 0) AS successful_checks,
    COALESCE(cs.failed_checks, 0) AS failed_checks,
    COALESCE(cs.pending_checks, 0) AS pending_checks
FROM pull_requests pr
LEFT JOIN review_summary rs ON rs.pr_id = pr.pr_id
LEFT JOIN check_summary cs ON cs.pr_id = pr.pr_id
ORDER BY pr.pr_id;

-- ============================================================
-- DIRECT-PUSH AND FORCE-PUSH POLICY INSPECTION
-- ============================================================

SELECT
    b.name,
    bp.allow_direct_push,
    bp.allow_force_push,
    bp.allow_deletion,
    bp.enforce_admins,
    bp.bypass_enabled
FROM branches b
JOIN branch_protection_policies bp
    ON bp.branch_id = b.branch_id;

-- ============================================================
-- PIPELINE FAILURE REPORT
-- ============================================================

SELECT
    run.pipeline_run_id,
    pd.name,
    job.job_name,
    job.failure_reason,
    job.attempt_number,
    job.assigned_runner_id
FROM pipeline_runs run
JOIN pipeline_definitions pd
    ON pd.pipeline_definition_id = run.pipeline_definition_id
JOIN pipeline_jobs job
    ON job.pipeline_run_id = run.pipeline_run_id
WHERE job.state = 'failure'
   OR run.state = 'failure'
ORDER BY run.created_at DESC;

-- ============================================================
-- AUDIT REPORT
-- ============================================================

SELECT
    event_type,
    entity_type,
    entity_id,
    actor_id,
    event_data,
    occurred_at
FROM audit_events
ORDER BY occurred_at DESC;

-- ============================================================
-- TRANSACTIONAL EXAMPLE: EVALUATE WITHOUT MERGING
-- ============================================================

BEGIN;

SELECT *
FROM evaluate_merge_eligibility(
    (
        SELECT pr_id
        FROM pull_requests
        WHERE title = 'Improve application observability'
    )
);

ROLLBACK;

-- ============================================================
-- PRODUCTION NOTES
--
-- 1. The merge procedure models database-level governance.
--    Actual Git commit construction and reference updates must
--    be coordinated with the repository hosting service.
--
-- 2. Runner execution must occur in isolated processes or
--    containers with restricted credentials and networking.
--
-- 3. Artifact URIs must be backed by private object storage,
--    checksum verification, access control and retention rules.
--
-- 4. Status checks are tied to commit SHA. A successful result
--    for an older commit cannot authorize a newer revision.
--
-- 5. Database application roles should not receive unrestricted
--    UPDATE privileges on protected branch metadata.
--
-- 6. Production deployments require independent authorization,
--    environment-specific credentials and deployment auditing.
--
-- 7. Database transactions cannot atomically include external
--    Git hosting, runner execution and cloud deployment APIs.
--    Use idempotency keys and an outbox or reconciliation process.
--
-- 8. For large repositories, partition audit and pipeline
--    history by time and retain immutable event records.
-- ============================================================

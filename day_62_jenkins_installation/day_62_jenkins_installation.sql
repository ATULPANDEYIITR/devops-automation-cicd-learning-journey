BEGIN;

DROP SCHEMA IF EXISTS jenkins_lab CASCADE;
CREATE SCHEMA jenkins_lab;

SET search_path = jenkins_lab, public;

CREATE TYPE installation_state AS ENUM (
    'new',
    'validated',
    'installed',
    'failed'
);

CREATE TYPE pull_request_state AS ENUM (
    'draft',
    'open',
    'closed',
    'merged'
);

CREATE TYPE review_state AS ENUM (
    'approved',
    'changes_requested',
    'commented',
    'pending'
);

CREATE TYPE check_state AS ENUM (
    'passing',
    'failing',
    'pending'
);

CREATE TYPE merge_state AS ENUM (
    'eligible',
    'blocked'
);

CREATE TABLE controllers (
    controller_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    jenkins_version TEXT NOT NULL,
    java_major INTEGER NOT NULL CHECK (java_major >= 17),
    http_port INTEGER NOT NULL CHECK (
        http_port BETWEEN 1024 AND 65535
    ),
    executor_count INTEGER NOT NULL CHECK (
        executor_count BETWEEN 1 AND 32
    ),
    csrf_protection BOOLEAN NOT NULL DEFAULT TRUE,
    anonymous_read BOOLEAN NOT NULL DEFAULT FALSE,
    allow_signup BOOLEAN NOT NULL DEFAULT FALSE,
    base_url TEXT NOT NULL,
    state installation_state NOT NULL DEFAULT 'new',
    installed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_controller_url
        CHECK (base_url ~ '^https?://.+/$'),

    CONSTRAINT secure_controller_defaults
        CHECK (
            csrf_protection = TRUE
            AND anonymous_read = FALSE
            AND allow_signup = FALSE
        )
);

CREATE TABLE plugins (
    plugin_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    minimum_java INTEGER NOT NULL CHECK (minimum_java >= 17),
    security_approved BOOLEAN NOT NULL DEFAULT TRUE,
    state TEXT NOT NULL DEFAULT 'available'
        CHECK (state IN ('available', 'installed', 'rejected'))
);

CREATE TABLE plugin_dependencies (
    plugin_id BIGINT NOT NULL REFERENCES plugins(plugin_id)
        ON DELETE CASCADE,
    dependency_plugin_id BIGINT NOT NULL REFERENCES plugins(plugin_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (plugin_id, dependency_plugin_id),
    CONSTRAINT plugin_cannot_depend_on_itself
        CHECK (plugin_id <> dependency_plugin_id)
);

CREATE TABLE controller_plugins (
    controller_id BIGINT NOT NULL REFERENCES controllers(controller_id)
        ON DELETE CASCADE,
    plugin_id BIGINT NOT NULL REFERENCES plugins(plugin_id)
        ON DELETE RESTRICT,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (controller_id, plugin_id)
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    visibility TEXT NOT NULL CHECK (
        visibility IN ('private', 'internal', 'public')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    head_commit TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, name)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_id BIGINT NOT NULL REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    sha TEXT NOT NULL UNIQUE,
    message TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    title TEXT NOT NULL,
    head_commit_id BIGINT REFERENCES commits(commit_id),
    state pull_request_state NOT NULL DEFAULT 'open',
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    merge_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    opened_by TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    merged_at TIMESTAMPTZ
);

CREATE TABLE reviewers (
    reviewer_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    role_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE pull_request_reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id)
        ON DELETE RESTRICT,
    state review_state NOT NULL,
    eligible BOOLEAN NOT NULL DEFAULT TRUE,
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pull_request_id, reviewer_id)
);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES pull_request_reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number > 0),
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state check_state NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    required_approvals INTEGER NOT NULL CHECK (
        required_approvals BETWEEN 0 AND 50
    ),
    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_direct_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_force_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_branch_deletion BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    PRIMARY KEY (policy_id, check_name)
);

CREATE TABLE credentials (
    credential_id BIGSERIAL PRIMARY KEY,
    credential_key TEXT NOT NULL UNIQUE,
    credential_kind TEXT NOT NULL CHECK (
        credential_kind IN (
            'username-password',
            'ssh-key',
            'api-token'
        )
    ),
    owner TEXT NOT NULL,
    secret_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    job_id BIGSERIAL PRIMARY KEY,
    controller_id BIGINT NOT NULL REFERENCES controllers(controller_id)
        ON DELETE CASCADE,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE RESTRICT,
    credential_id BIGINT REFERENCES credentials(credential_id)
        ON DELETE RESTRICT,
    name TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (controller_id, name)
);

CREATE TABLE job_required_plugins (
    job_id BIGINT NOT NULL REFERENCES jobs(job_id)
        ON DELETE CASCADE,
    plugin_id BIGINT NOT NULL REFERENCES plugins(plugin_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (job_id, plugin_id)
);

CREATE TABLE merge_evaluations (
    evaluation_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE RESTRICT,
    state merge_state NOT NULL,
    reasons TEXT[] NOT NULL DEFAULT '{}',
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    audit_event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_branches_repository
    ON branches(repository_id);

CREATE INDEX idx_pr_repository_state
    ON pull_requests(repository_id, state);

CREATE INDEX idx_reviews_pr_state
    ON pull_request_reviews(pull_request_id, state);

CREATE INDEX idx_status_checks_pr_state
    ON status_checks(pull_request_id, state);

CREATE INDEX idx_audit_events_created
    ON audit_events(created_at DESC);

CREATE OR REPLACE FUNCTION validate_controller_installation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'installed' THEN
        IF NEW.java_major < 17 THEN
            RAISE EXCEPTION
                'Controller requires Java 17 or newer';
        END IF;

        IF NOT NEW.csrf_protection THEN
            RAISE EXCEPTION
                'CSRF protection must be enabled';
        END IF;

        IF NEW.anonymous_read OR NEW.allow_signup THEN
            RAISE EXCEPTION
                'Anonymous read and public signup are disabled';
        END IF;

        NEW.installed_at := COALESCE(
            NEW.installed_at,
            now()
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_controller_installation
BEFORE INSERT OR UPDATE ON controllers
FOR EACH ROW
EXECUTE FUNCTION validate_controller_installation();

CREATE OR REPLACE FUNCTION validate_plugin_installation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    plugin_record RECORD;
    dependency RECORD;
BEGIN
    SELECT *
    INTO plugin_record
    FROM plugins
    WHERE plugin_id = NEW.plugin_id;

    IF plugin_record IS NULL THEN
        RAISE EXCEPTION 'Plugin does not exist';
    END IF;

    IF plugin_record.security_approved = FALSE THEN
        RAISE EXCEPTION
            'Plugin % is not approved',
            plugin_record.name;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM controllers c
        WHERE c.controller_id = NEW.controller_id
          AND c.java_major >= plugin_record.minimum_java
          AND c.state = 'installed'
    ) THEN
        RAISE EXCEPTION
            'Controller is incompatible with plugin %',
            plugin_record.name;
    END IF;

    FOR dependency IN
        SELECT pd.dependency_plugin_id
        FROM plugin_dependencies pd
        WHERE pd.plugin_id = NEW.plugin_id
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM controller_plugins cp
            WHERE cp.controller_id = NEW.controller_id
              AND cp.plugin_id = dependency.dependency_plugin_id
        ) THEN
            RAISE EXCEPTION
                'Dependency % is not installed before plugin %',
                dependency.dependency_plugin_id,
                NEW.plugin_id;
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_plugin_installation
BEFORE INSERT ON controller_plugins
FOR EACH ROW
EXECUTE FUNCTION validate_plugin_installation();

CREATE OR REPLACE FUNCTION evaluate_pull_request(
    p_pull_request_id BIGINT,
    p_policy_id BIGINT
)
RETURNS TABLE (
    state merge_state,
    reasons TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    policy RECORD;
    valid_approvals INTEGER;
    failed_checks INTEGER;
    unresolved_comments INTEGER;
    reason_list TEXT[] := '{}';
BEGIN
    SELECT *
    INTO pr
    FROM pull_requests
    WHERE pull_request_id = p_pull_request_id;

    IF pr IS NULL THEN
        RAISE EXCEPTION 'Pull Request % not found', p_pull_request_id;
    END IF;

    SELECT bp.*, b.name AS branch_name
    INTO policy
    FROM branch_protection_policies bp
    JOIN branches b ON b.branch_id = bp.branch_id
    WHERE bp.policy_id = p_policy_id;

    IF policy IS NULL THEN
        RAISE EXCEPTION 'Branch protection policy not found';
    END IF;

    IF pr.state <> 'open' THEN
        reason_list := array_append(
            reason_list,
            'Pull Request is not open'
        );
    END IF;

    IF pr.target_branch_id <> policy.branch_id THEN
        reason_list := array_append(
            reason_list,
            'Pull Request targets an unprotected branch'
        );
    END IF;

    IF pr.draft THEN
        reason_list := array_append(
            reason_list,
            'Pull Request is a draft'
        );
    END IF;

    IF pr.merge_conflict THEN
        reason_list := array_append(
            reason_list,
            'Merge conflict must be resolved'
        );
    END IF;

    IF policy.require_resolved_conversations
       AND NOT pr.conversations_resolved THEN
        reason_list := array_append(
            reason_list,
            'Review conversations remain unresolved'
        );
    END IF;

    SELECT COUNT(DISTINCT reviewer_id)
    INTO valid_approvals
    FROM pull_request_reviews
    WHERE pull_request_id = p_pull_request_id
      AND state = 'approved'
      AND eligible
      AND NOT stale;

    IF valid_approvals < policy.required_approvals THEN
        reason_list := array_append(
            reason_list,
            format(
                'Required approvals: %s/%s',
                valid_approvals,
                policy.required_approvals
            )
        );
    END IF;

    SELECT COUNT(*)
    INTO failed_checks
    FROM required_status_checks rsc
    LEFT JOIN status_checks sc
      ON sc.pull_request_id = p_pull_request_id
     AND sc.check_name = rsc.check_name
    WHERE rsc.policy_id = p_policy_id
      AND (
          sc.status_check_id IS NULL
          OR sc.state <> 'passing'
      );

    IF failed_checks > 0 THEN
        reason_list := array_append(
            reason_list,
            'Required status checks are not all passing'
        );
    END IF;

    SELECT COUNT(*)
    INTO unresolved_comments
    FROM review_comments rc
    JOIN pull_request_reviews r
      ON r.review_id = rc.review_id
    WHERE r.pull_request_id = p_pull_request_id
      AND rc.resolved = FALSE;

    IF policy.require_resolved_conversations
       AND unresolved_comments > 0 THEN
        reason_list := array_append(
            reason_list,
            format(
                'Unresolved review comments: %s',
                unresolved_comments
            )
        );
    END IF;

    IF cardinality(reason_list) = 0 THEN
        state := 'eligible';
    ELSE
        state := 'blocked';
    END IF;

    reasons := reason_list;

    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION audit_controller_plugin()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit_events (
        event_type,
        entity_type,
        entity_id,
        details
    )
    VALUES (
        'plugin.installed',
        'controller_plugin',
        NEW.controller_id,
        jsonb_build_object(
            'plugin_id',
            NEW.plugin_id
        )
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_controller_plugin
AFTER INSERT ON controller_plugins
FOR EACH ROW
EXECUTE FUNCTION audit_controller_plugin();

INSERT INTO controllers (
    name,
    jenkins_version,
    java_major,
    http_port,
    executor_count,
    csrf_protection,
    anonymous_read,
    allow_signup,
    base_url,
    state
)
VALUES (
    'enterprise-controller',
    '2.5xx',
    21,
    8080,
    4,
    TRUE,
    FALSE,
    FALSE,
    'http://localhost:8080/',
    'installed'
);

INSERT INTO plugins (
    name,
    version,
    minimum_java,
    security_approved
)
VALUES
    ('git', '5.6.0', 17, TRUE),
    ('credentials', '1400.1', 17, TRUE),
    ('workflow-api', '1400.1', 17, TRUE),
    ('workflow-job', '1500.1', 17, TRUE),
    ('pipeline-model-definition', '2.22.0', 17, TRUE);

INSERT INTO plugin_dependencies (
    plugin_id,
    dependency_plugin_id
)
SELECT p.plugin_id, d.plugin_id
FROM plugins p
JOIN plugins d
  ON d.name = 'workflow-api'
WHERE p.name = 'workflow-job';

INSERT INTO plugin_dependencies (
    plugin_id,
    dependency_plugin_id
)
SELECT p.plugin_id, d.plugin_id
FROM plugins p
JOIN plugins d
  ON d.name = 'workflow-job'
WHERE p.name = 'pipeline-model-definition';

INSERT INTO plugin_dependencies (
    plugin_id,
    dependency_plugin_id
)
SELECT p.plugin_id, d.plugin_id
FROM plugins p
JOIN plugins d
  ON d.name = 'credentials'
WHERE p.name = 'pipeline-model-definition';

INSERT INTO controller_plugins (
    controller_id,
    plugin_id
)
SELECT c.controller_id, p.plugin_id
FROM controllers c
JOIN plugins p ON p.name = 'git'
WHERE c.name = 'enterprise-controller';

INSERT INTO controller_plugins (
    controller_id,
    plugin_id
)
SELECT c.controller_id, p.plugin_id
FROM controllers c
JOIN plugins p ON p.name = 'credentials'
WHERE c.name = 'enterprise-controller';

INSERT INTO controller_plugins (
    controller_id,
    plugin_id
)
SELECT c.controller_id, p.plugin_id
FROM controllers c
JOIN plugins p ON p.name = 'workflow-api'
WHERE c.name = 'enterprise-controller';

INSERT INTO controller_plugins (
    controller_id,
    plugin_id
)
SELECT c.controller_id, p.plugin_id
FROM controllers c
JOIN plugins p ON p.name = 'workflow-job'
WHERE c.name = 'enterprise-controller';

INSERT INTO controller_plugins (
    controller_id,
    plugin_id
)
SELECT c.controller_id, p.plugin_id
FROM controllers c
JOIN plugins p ON p.name = 'pipeline-model-definition'
WHERE c.name = 'enterprise-controller';

INSERT INTO repositories (
    name,
    default_branch,
    visibility
)
VALUES (
    'orders-service',
    'main',
    'internal'
);

INSERT INTO branches (
    repository_id,
    name,
    head_commit,
    protected
)
SELECT repository_id, 'main', 'a8e9d2', TRUE
FROM repositories
WHERE name = 'orders-service';

INSERT INTO branches (
    repository_id,
    name,
    head_commit,
    protected
)
SELECT repository_id, 'feature/auth-hardening', 'a8e9d2', FALSE
FROM repositories
WHERE name = 'orders-service';

INSERT INTO commits (
    repository_id,
    branch_id,
    sha,
    message,
    author
)
SELECT
    r.repository_id,
    b.branch_id,
    'a8e9d2',
    'Harden authentication pipeline',
    'alice'
FROM repositories r
JOIN branches b
  ON b.repository_id = r.repository_id
 AND b.name = 'feature/auth-hardening'
WHERE r.name = 'orders-service';

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    title,
    head_commit_id,
    state,
    draft,
    conversations_resolved,
    merge_conflict,
    opened_by
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    'Harden authentication pipeline',
    c.commit_id,
    'open',
    FALSE,
    TRUE,
    FALSE,
    'alice'
FROM repositories r
JOIN branches source
  ON source.repository_id = r.repository_id
 AND source.name = 'feature/auth-hardening'
JOIN branches target
  ON target.repository_id = r.repository_id
 AND target.name = 'main'
JOIN commits c
  ON c.sha = 'a8e9d2'
WHERE r.name = 'orders-service';

INSERT INTO reviewers (
    username,
    role_name
)
VALUES
    ('alice', 'senior-engineer'),
    ('bob', 'security-reviewer'),
    ('automation-account', 'service-account');

INSERT INTO pull_request_reviews (
    pull_request_id,
    reviewer_id,
    state,
    eligible,
    stale
)
SELECT
    pr.pull_request_id,
    r.reviewer_id,
    'approved',
    CASE
        WHEN r.username = 'automation-account'
            THEN FALSE
        ELSE TRUE
    END,
    FALSE
FROM pull_requests pr
CROSS JOIN reviewers r
WHERE pr.title = 'Harden authentication pipeline'
  AND r.username IN (
      'alice',
      'bob',
      'automation-account'
  );

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    check_name,
    'passing',
    now()
FROM pull_requests
CROSS JOIN (
    VALUES
        ('build'),
        ('unit-tests'),
        ('security-scan')
) AS required(check_name)
WHERE title = 'Harden authentication pipeline';

INSERT INTO branch_protection_policies (
    branch_id,
    required_approvals,
    require_resolved_conversations,
    prohibit_direct_push,
    prohibit_force_push,
    prohibit_branch_deletion,
    require_linear_history,
    allow_administrator_bypass
)
SELECT
    branch_id,
    2,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE
FROM branches
WHERE name = 'main';

INSERT INTO required_status_checks (
    policy_id,
    check_name
)
SELECT
    policy_id,
    required.check_name
FROM branch_protection_policies
CROSS JOIN (
    VALUES
        ('build'),
        ('unit-tests'),
        ('security-scan')
) AS required(check_name);

INSERT INTO credentials (
    credential_key,
    credential_kind,
    owner,
    secret_fingerprint
)
VALUES (
    'git-readonly',
    'username-password',
    'ci-service',
    'abcdef0123456789abcdef0123456789'
);

INSERT INTO jobs (
    controller_id,
    repository_id,
    credential_id,
    name,
    branch_name,
    repository_url
)
SELECT
    c.controller_id,
    r.repository_id,
    cr.credential_id,
    'orders-service-main',
    'main',
    'https://git.example.internal/orders-service.git'
FROM controllers c
JOIN repositories r
  ON r.name = 'orders-service'
JOIN credentials cr
  ON cr.credential_key = 'git-readonly'
WHERE c.name = 'enterprise-controller';

INSERT INTO job_required_plugins (
    job_id,
    plugin_id
)
SELECT
    j.job_id,
    p.plugin_id
FROM jobs j
JOIN plugins p
  ON p.name IN (
      'git',
      'credentials',
      'pipeline-model-definition'
  )
WHERE j.name = 'orders-service-main';

COMMIT;

-- Retrieve installed plugins and their versions.
SELECT
    c.name AS controller,
    p.name AS plugin,
    p.version,
    p.minimum_java
FROM controller_plugins cp
JOIN controllers c
  ON c.controller_id = cp.controller_id
JOIN plugins p
  ON p.plugin_id = cp.plugin_id
ORDER BY p.name;

-- Show Pull Request review decisions without exposing credentials.
SELECT
    pr.pull_request_id,
    pr.title,
    r.username AS reviewer,
    r.state AS review_state,
    r.eligible,
    r.stale
FROM pull_requests pr
JOIN pull_request_reviews r
  ON r.pull_request_id = pr.pull_request_id
ORDER BY pr.pull_request_id, r.username;

-- Evaluate merge eligibility under branch protection.
SELECT *
FROM evaluate_pull_request(
    (
        SELECT pull_request_id
        FROM pull_requests
        WHERE title = 'Harden authentication pipeline'
    ),
    (
        SELECT policy_id
        FROM branch_protection_policies bp
        JOIN branches b
          ON b.branch_id = bp.branch_id
        WHERE b.name = 'main'
    )
);

-- Record the current merge decision for audit/reporting.
INSERT INTO merge_evaluations (
    pull_request_id,
    policy_id,
    state,
    reasons
)
SELECT
    pr.pull_request_id,
    bp.policy_id,
    evaluation.state,
    evaluation.reasons
FROM pull_requests pr
JOIN branches b
  ON b.branch_id = pr.target_branch_id
JOIN branch_protection_policies bp
  ON bp.branch_id = b.branch_id
CROSS JOIN LATERAL evaluate_pull_request(
    pr.pull_request_id,
    bp.policy_id
) AS evaluation
WHERE pr.title = 'Harden authentication pipeline';

-- Report protected branches and their controls.
SELECT
    r.name AS repository,
    b.name AS branch,
    bp.required_approvals,
    bp.require_resolved_conversations,
    bp.prohibit_direct_push,
    bp.prohibit_force_push,
    bp.prohibit_branch_deletion,
    bp.require_linear_history,
    bp.allow_administrator_bypass
FROM branch_protection_policies bp
JOIN branches b
  ON b.branch_id = bp.branch_id
JOIN repositories r
  ON r.repository_id = b.repository_id;

-- Report Jenkins jobs and required plugins.
SELECT
    j.name AS job,
    j.branch_name,
    j.repository_url,
    p.name AS required_plugin,
    p.version
FROM jobs j
JOIN job_required_plugins jrp
  ON jrp.job_id = j.job_id
JOIN plugins p
  ON p.plugin_id = jrp.plugin_id
ORDER BY j.name, p.name;

-- Show audit events produced by plugin installation.
SELECT
    event_type,
    entity_type,
    entity_id,
    details,
    created_at
FROM audit_events
ORDER BY created_at DESC;

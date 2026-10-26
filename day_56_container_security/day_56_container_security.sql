DROP SCHEMA IF EXISTS container_governance CASCADE;
CREATE SCHEMA container_governance;

SET search_path = container_governance, public;

CREATE TYPE pull_request_state AS ENUM (
    'draft',
    'open',
    'closed',
    'merged'
);

CREATE TYPE review_state AS ENUM (
    'commented',
    'approved',
    'changes_requested',
    'dismissed'
);

CREATE TYPE check_state AS ENUM (
    'pending',
    'passed',
    'failed'
);

CREATE TYPE vulnerability_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE repository_members (
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,
    role_name TEXT NOT NULL
        CHECK (role_name IN ('developer', 'reviewer', 'security', 'admin')),
    PRIMARY KEY (repository_id, user_id)
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT false,
    head_sha TEXT,
    UNIQUE (repository_id, name)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    sha CHAR(12) NOT NULL,
    author_id BIGINT NOT NULL
        REFERENCES users(user_id),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, sha)
);

CREATE TABLE commit_files (
    commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    PRIMARY KEY (commit_id, file_path)
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    number INTEGER NOT NULL CHECK (number > 0),
    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    author_id BIGINT NOT NULL
        REFERENCES users(user_id),
    head_commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),
    state pull_request_state NOT NULL DEFAULT 'open',
    is_draft BOOLEAN NOT NULL DEFAULT false,
    merge_conflict BOOLEAN NOT NULL DEFAULT false,
    base_synced BOOLEAN NOT NULL DEFAULT true,
    approvals_stale BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, number),
    CHECK (source_branch_id <> target_branch_id)
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id),
    state review_state NOT NULL,
    commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE review_comments (
    review_comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT,
    line_number INTEGER CHECK (line_number IS NULL OR line_number > 0),
    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
    resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
    conversation_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    opened_by BIGINT NOT NULL
        REFERENCES users(user_id),
    topic TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state check_state NOT NULL,
    details TEXT,
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    require_pull_request BOOLEAN NOT NULL DEFAULT true,
    required_approvals INTEGER NOT NULL DEFAULT 2
        CHECK (required_approvals >= 0),
    restrict_direct_push BOOLEAN NOT NULL DEFAULT true,
    restrict_force_push BOOLEAN NOT NULL DEFAULT true,
    restrict_branch_deletion BOOLEAN NOT NULL DEFAULT true,
    require_resolved_conversations BOOLEAN NOT NULL DEFAULT true,
    require_linear_history BOOLEAN NOT NULL DEFAULT true,
    allow_admin_bypass BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    PRIMARY KEY (policy_id, check_name)
);

CREATE TABLE container_images (
    image_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    pull_request_id BIGINT
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    image_name TEXT NOT NULL,
    image_digest TEXT,
    container_user TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(image_name)) > 0),
    CHECK (length(trim(container_user)) > 0)
);

CREATE TABLE container_secrets (
    secret_id BIGSERIAL PRIMARY KEY,
    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id)
        ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    detection_source TEXT NOT NULL,
    UNIQUE (image_id, secret_name)
);

CREATE TABLE vulnerabilities (
    vulnerability_id BIGSERIAL PRIMARY KEY,
    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id)
        ON DELETE CASCADE,
    package_name TEXT NOT NULL,
    severity vulnerability_severity NOT NULL,
    fixed_version TEXT,
    UNIQUE (image_id, package_name)
);

CREATE INDEX idx_pull_requests_target_state
    ON pull_requests(target_branch_id, state);

CREATE INDEX idx_reviews_pr_state
    ON reviews(pull_request_id, state);

CREATE INDEX idx_status_checks_pr_name
    ON status_checks(pull_request_id, check_name);

CREATE INDEX idx_vulnerabilities_image_severity
    ON vulnerabilities(image_id, severity);

CREATE INDEX idx_conversations_pr_unresolved
    ON conversations(pull_request_id)
    WHERE resolved = false;

CREATE OR REPLACE FUNCTION validate_review_reviewer()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    pr_author BIGINT;
    repository_id_value BIGINT;
BEGIN
    SELECT author_id, repository_id
    INTO pr_author, repository_id_value
    FROM pull_requests
    WHERE pull_request_id = NEW.pull_request_id;

    IF NEW.reviewer_id = pr_author THEN
        RAISE EXCEPTION
            'pull request author cannot approve their own pull request';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM repository_members rm
        WHERE rm.repository_id = repository_id_value
          AND rm.user_id = NEW.reviewer_id
          AND rm.role_name IN ('reviewer', 'security', 'admin')
    ) THEN
        RAISE EXCEPTION
            'reviewer is not an eligible repository reviewer';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_review_reviewer
BEFORE INSERT OR UPDATE ON reviews
FOR EACH ROW
EXECUTE FUNCTION validate_review_reviewer();

CREATE OR REPLACE FUNCTION invalidate_approvals_after_head_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.head_commit_id <> OLD.head_commit_id THEN
        NEW.approvals_stale := true;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invalidate_approvals
BEFORE UPDATE OF head_commit_id ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION invalidate_approvals_after_head_change();

CREATE OR REPLACE FUNCTION prevent_protected_branch_removal()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.protected THEN
        RAISE EXCEPTION
            'protected branch % cannot be deleted', OLD.name;
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_prevent_protected_branch_removal
BEFORE DELETE ON branches
FOR EACH ROW
EXECUTE FUNCTION prevent_protected_branch_removal();

CREATE OR REPLACE FUNCTION merge_eligibility(
    requested_pull_request BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    policy RECORD;
    approval_count INTEGER;
    unresolved_count INTEGER;
    failed_checks INTEGER;
    missing_checks INTEGER;
    security_findings INTEGER;
BEGIN
    SELECT *
    INTO pr
    FROM pull_requests
    WHERE pull_request_id = requested_pull_request;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'pull request does not exist';
        RETURN;
    END IF;

    SELECT bpp.*
    INTO policy
    FROM branch_protection_policies bpp
    WHERE bpp.branch_id = pr.target_branch_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'target branch has no protection policy';
        RETURN;
    END IF;

    IF pr.state <> 'open' THEN
        RETURN QUERY SELECT false, 'pull request is not open';
    END IF;

    IF pr.is_draft THEN
        RETURN QUERY SELECT false, 'pull request is a draft';
    END IF;

    IF pr.merge_conflict THEN
        RETURN QUERY SELECT false, 'merge conflict must be resolved';
    END IF;

    IF NOT pr.base_synced THEN
        RETURN QUERY SELECT false, 'source branch is not synchronized';
    END IF;

    IF pr.approvals_stale THEN
        RETURN QUERY SELECT false, 'approvals are stale';
    END IF;

    SELECT count(DISTINCT r.reviewer_id)
    INTO approval_count
    FROM reviews r
    JOIN repository_members rm
      ON rm.user_id = r.reviewer_id
     AND rm.repository_id = pr.repository_id
    WHERE r.pull_request_id = pr.pull_request_id
      AND r.state = 'approved'
      AND r.reviewer_id <> pr.author_id
      AND r.commit_id = pr.head_commit_id
      AND rm.role_name IN ('reviewer', 'security', 'admin');

    IF approval_count < policy.required_approvals THEN
        RETURN QUERY
        SELECT false,
               format(
                   'required approvals: %s, eligible approvals: %s',
                   policy.required_approvals,
                   approval_count
               );
    END IF;

    SELECT count(*)
    INTO unresolved_count
    FROM conversations
    WHERE pull_request_id = pr.pull_request_id
      AND resolved = false;

    IF policy.require_resolved_conversations
       AND unresolved_count > 0 THEN
        RETURN QUERY
        SELECT false,
               format(
                   'unresolved review conversations: %s',
                   unresolved_count
               );
    END IF;

    SELECT count(*)
    INTO failed_checks
    FROM status_checks sc
    JOIN required_status_checks rsc
      ON rsc.policy_id = policy.policy_id
     AND rsc.check_name = sc.check_name
    WHERE sc.pull_request_id = pr.pull_request_id
      AND sc.state <> 'passed';

    IF failed_checks > 0 THEN
        RETURN QUERY
        SELECT false,
               'one or more required status checks did not pass';
    END IF;

    SELECT count(*)
    INTO missing_checks
    FROM required_status_checks rsc
    WHERE rsc.policy_id = policy.policy_id
      AND NOT EXISTS (
          SELECT 1
          FROM status_checks sc
          WHERE sc.pull_request_id = pr.pull_request_id
            AND sc.check_name = rsc.check_name
            AND sc.state = 'passed'
      );

    IF missing_checks > 0 THEN
        RETURN QUERY
        SELECT false,
               format(
                   'required status checks missing or not passed: %s',
                   missing_checks
               );
    END IF;

    SELECT count(*)
    INTO security_findings
    FROM container_images ci
    WHERE ci.pull_request_id = pr.pull_request_id
      AND (
          lower(ci.container_user) IN ('root', '0', '')
          OR EXISTS (
              SELECT 1
              FROM container_secrets cs
              WHERE cs.image_id = ci.image_id
          )
          OR EXISTS (
              SELECT 1
              FROM vulnerabilities v
              WHERE v.image_id = ci.image_id
                AND v.severity IN ('high', 'critical')
          )
      );

    IF security_findings > 0 THEN
        RETURN QUERY
        SELECT false,
               format(
                   'container security findings: %s image(s)',
                   security_findings
               );
    END IF;

    RETURN QUERY
    SELECT true, 'all merge and container-security requirements passed';
END;
$$;

CREATE OR REPLACE VIEW repository_security_posture AS
SELECT
    r.name AS repository,
    b.name AS target_branch,
    count(DISTINCT pr.pull_request_id) AS pull_requests,
    count(DISTINCT CASE
        WHEN pr.state = 'open' THEN pr.pull_request_id
    END) AS open_pull_requests,
    count(DISTINCT ci.image_id) AS scanned_images,
    count(DISTINCT cs.secret_id) AS secret_findings,
    count(DISTINCT v.vulnerability_id)
        FILTER (WHERE v.severity IN ('high', 'critical'))
        AS high_or_critical_vulnerabilities
FROM repositories r
JOIN branches b
  ON b.repository_id = r.repository_id
LEFT JOIN pull_requests pr
  ON pr.target_branch_id = b.branch_id
LEFT JOIN container_images ci
  ON ci.pull_request_id = pr.pull_request_id
LEFT JOIN container_secrets cs
  ON cs.image_id = ci.image_id
LEFT JOIN vulnerabilities v
  ON v.image_id = ci.image_id
GROUP BY r.name, b.name;

INSERT INTO repositories(name)
VALUES ('payments-service');

INSERT INTO users(username)
VALUES
    ('alice'),
    ('bob'),
    ('carol');

INSERT INTO repository_members(
    repository_id,
    user_id,
    role_name
)
SELECT
    r.repository_id,
    u.user_id,
    CASE u.username
        WHEN 'alice' THEN 'developer'
        WHEN 'bob' THEN 'security'
        WHEN 'carol' THEN 'reviewer'
    END
FROM repositories r
CROSS JOIN users u
WHERE r.name = 'payments-service';

INSERT INTO branches(
    repository_id,
    name,
    protected,
    head_sha
)
VALUES
(
    (SELECT repository_id FROM repositories WHERE name = 'payments-service'),
    'main',
    true,
    'base00000001'
),
(
    (SELECT repository_id FROM repositories WHERE name = 'payments-service'),
    'feature/container-hardening',
    false,
    'head00000001'
);

INSERT INTO commits(
    repository_id,
    sha,
    author_id,
    message
)
VALUES
(
    (SELECT repository_id FROM repositories WHERE name = 'payments-service'),
    'head00000001',
    (SELECT user_id FROM users WHERE username = 'alice'),
    'Harden production container'
);

INSERT INTO commit_files(commit_id, file_path)
VALUES
(
    (SELECT commit_id FROM commits WHERE sha = 'head00000001'),
    'Dockerfile'
),
(
    (SELECT commit_id FROM commits WHERE sha = 'head00000001'),
    'app.py'
);

INSERT INTO pull_requests(
    repository_id,
    number,
    source_branch_id,
    target_branch_id,
    author_id,
    head_commit_id
)
VALUES
(
    (SELECT repository_id FROM repositories WHERE name = 'payments-service'),
    101,
    (SELECT branch_id
     FROM branches
     WHERE name = 'feature/container-hardening'),
    (SELECT branch_id
     FROM branches
     WHERE name = 'main'),
    (SELECT user_id FROM users WHERE username = 'alice'),
    (SELECT commit_id FROM commits WHERE sha = 'head00000001')
);

INSERT INTO branch_protection_policies(
    branch_id,
    required_approvals,
    require_pull_request,
    restrict_direct_push,
    restrict_force_push,
    restrict_branch_deletion,
    require_resolved_conversations,
    require_linear_history,
    allow_admin_bypass
)
VALUES
(
    (SELECT branch_id FROM branches WHERE name = 'main'),
    2,
    true,
    true,
    true,
    true,
    true,
    true,
    false
);

INSERT INTO required_status_checks(policy_id, check_name)
SELECT
    policy_id,
    required_check
FROM branch_protection_policies,
LATERAL unnest(
    ARRAY[
        'container-build',
        'container-vulnerability-scan',
        'container-secret-scan'
    ]
) AS required_check;

INSERT INTO reviews(
    pull_request_id,
    reviewer_id,
    state,
    commit_id
)
VALUES
(
    (SELECT pull_request_id
     FROM pull_requests
     WHERE number = 101),
    (SELECT user_id FROM users WHERE username = 'bob'),
    'approved',
    (SELECT commit_id FROM commits WHERE sha = 'head00000001')
),
(
    (SELECT pull_request_id
     FROM pull_requests
     WHERE number = 101),
    (SELECT user_id FROM users WHERE username = 'carol'),
    'approved',
    (SELECT commit_id FROM commits WHERE sha = 'head00000001')
);

INSERT INTO status_checks(
    pull_request_id,
    check_name,
    state,
    details,
    completed_at
)
SELECT
    pr.pull_request_id,
    checks.check_name,
    'passed',
    'security pipeline completed successfully',
    now()
FROM pull_requests pr
CROSS JOIN (
    VALUES
        ('container-build'),
        ('container-vulnerability-scan'),
        ('container-secret-scan')
) AS checks(check_name)
WHERE pr.number = 101;

INSERT INTO container_images(
    repository_id,
    pull_request_id,
    image_name,
    image_digest,
    container_user
)
VALUES
(
    (SELECT repository_id
     FROM repositories
     WHERE name = 'payments-service'),
    (SELECT pull_request_id
     FROM pull_requests
     WHERE number = 101),
    'payments:101',
    'sha256:secure-image-digest',
    '10001'
);

INSERT INTO vulnerabilities(
    image_id,
    package_name,
    severity,
    fixed_version
)
VALUES
(
    (SELECT image_id
     FROM container_images
     WHERE image_name = 'payments:101'),
    'openssl',
    'medium',
    '3.2.1'
);

INSERT INTO conversations(
    pull_request_id,
    opened_by,
    topic,
    resolved
)
VALUES
(
    (SELECT pull_request_id
     FROM pull_requests
     WHERE number = 101),
    (SELECT user_id FROM users WHERE username = 'bob'),
    'Confirm non-root container UID',
    true
);

SELECT *
FROM merge_eligibility(
    (
        SELECT pull_request_id
        FROM pull_requests
        WHERE number = 101
    )
);

INSERT INTO container_images(
    repository_id,
    pull_request_id,
    image_name,
    image_digest,
    container_user
)
VALUES
(
    (SELECT repository_id
     FROM repositories
     WHERE name = 'payments-service'),
    (SELECT pull_request_id
     FROM pull_requests
     WHERE number = 101),
    'payments:101-insecure',
    'sha256:insecure-image-digest',
    'root'
);

INSERT INTO container_secrets(
    image_id,
    secret_name,
    detection_source
)
VALUES
(
    (SELECT image_id
     FROM container_images
     WHERE image_name = 'payments:101-insecure'),
    'DATABASE_PASSWORD',
    'repository-secret-scan'
);

INSERT INTO vulnerabilities(
    image_id,
    package_name,
    severity,
    fixed_version
)
VALUES
(
    (SELECT image_id
     FROM container_images
     WHERE image_name = 'payments:101-insecure'),
    'openssl',
    'critical',
    '3.2.1'
),
(
    (SELECT image_id
     FROM container_images
     WHERE image_name = 'payments:101-insecure'),
    'curl',
    'high',
    '8.10.0'
);

SELECT
    ci.image_name,
    ci.container_user,
    EXISTS (
        SELECT 1
        FROM container_secrets cs
        WHERE cs.image_id = ci.image_id
    ) AS contains_detected_secret,
    count(v.vulnerability_id)
        FILTER (WHERE v.severity IN ('high', 'critical'))
        AS high_or_critical_vulnerabilities
FROM container_images ci
LEFT JOIN vulnerabilities v
  ON v.image_id = ci.image_id
GROUP BY ci.image_id, ci.image_name, ci.container_user
ORDER BY ci.image_name;

SELECT *
FROM repository_security_posture;

-- Transactional example: updating the Pull Request head invalidates
-- approvals because approvals are tied to the reviewed commit.
BEGIN;

UPDATE pull_requests
SET head_commit_id = (
    SELECT commit_id
    FROM commits
    WHERE sha = 'head00000001'
),
approvals_stale = true
WHERE number = 101;

SELECT
    number,
    state,
    head_commit_id,
    approvals_stale
FROM pull_requests
WHERE number = 101;

ROLLBACK;

-- Final reporting query distinguishes proposal state, review state,
-- automated checks, and container-security enforcement.
WITH review_summary AS (
    SELECT
        pr.pull_request_id,
        count(*) FILTER (WHERE r.state = 'approved') AS approvals,
        count(*) FILTER (WHERE r.state = 'changes_requested')
            AS change_requests
    FROM pull_requests pr
    LEFT JOIN reviews r
      ON r.pull_request_id = pr.pull_request_id
    GROUP BY pr.pull_request_id
),
check_summary AS (
    SELECT
        pull_request_id,
        count(*) FILTER (WHERE state = 'passed') AS passed_checks,
        count(*) FILTER (WHERE state = 'failed') AS failed_checks
    FROM status_checks
    GROUP BY pull_request_id
)
SELECT
    pr.number,
    pr.state,
    pr.is_draft,
    rs.approvals,
    rs.change_requests,
    COALESCE(cs.passed_checks, 0) AS passed_checks,
    COALESCE(cs.failed_checks, 0) AS failed_checks,
    pr.approvals_stale,
    pr.merge_conflict,
    pr.base_synced
FROM pull_requests pr
JOIN review_summary rs
  ON rs.pull_request_id = pr.pull_request_id
LEFT JOIN check_summary cs
  ON cs.pull_request_id = pr.pull_request_id
ORDER BY pr.number;

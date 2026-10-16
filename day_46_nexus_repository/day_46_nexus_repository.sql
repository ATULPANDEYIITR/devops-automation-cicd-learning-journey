-- Nexus Repository learning model for PostgreSQL 15+
-- Covers repository types, artifact publishing and retrieval, checksums,
-- repository permissions, proxy caching, group resolution, and auditability.
--
-- The schema models repository metadata rather than implementing Nexus REST
-- endpoints or storing large binary blobs. Production binaries normally reside
-- in repository-managed blob storage; this model stores digest and size metadata.

BEGIN;

DROP VIEW IF EXISTS artifact_inventory CASCADE;
DROP VIEW IF EXISTS repository_cache_metrics CASCADE;
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS artifact_retrievals CASCADE;
DROP TABLE IF EXISTS status_checks CASCADE;
DROP TABLE IF EXISTS repository_members CASCADE;
DROP TABLE IF EXISTS artifacts CASCADE;
DROP TABLE IF EXISTS artifact_versions CASCADE;
DROP TABLE IF EXISTS repository_permissions CASCADE;
DROP TABLE IF EXISTS principals CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    repository_type TEXT NOT NULL
        CHECK (repository_type IN ('hosted', 'proxy', 'group')),
    format TEXT NOT NULL
        CHECK (format IN ('maven2', 'npm', 'pypi', 'docker', 'raw')),
    upstream_url TEXT,
    allow_redeploy BOOLEAN NOT NULL DEFAULT FALSE,
    allow_delete BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT repository_name_safe
        CHECK (repository_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'),
    CONSTRAINT proxy_requires_upstream
        CHECK (
            (repository_type = 'proxy' AND upstream_url IS NOT NULL)
            OR (repository_type <> 'proxy' AND upstream_url IS NULL)
        ),
    CONSTRAINT group_cannot_redeploy
        CHECK (repository_type = 'hosted' OR NOT allow_redeploy),
    CONSTRAINT upstream_requires_https
        CHECK (
            upstream_url IS NULL
            OR upstream_url ~ '^https://[^/@]+(/.*)?$'
        )
);

CREATE TABLE principals (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE repository_permissions (
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    principal_id BIGINT NOT NULL REFERENCES principals(principal_id)
        ON DELETE CASCADE,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    can_publish BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    can_admin BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (repository_id, principal_id),
    CONSTRAINT permission_requires_read_for_publish
        CHECK (NOT can_publish OR can_read OR can_admin),
    CONSTRAINT permission_requires_read_for_delete
        CHECK (NOT can_delete OR can_read OR can_admin)
);

CREATE TABLE artifact_versions (
    artifact_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    format TEXT NOT NULL
        CHECK (format IN ('maven2', 'npm', 'pypi', 'docker', 'raw')),
    package_name TEXT NOT NULL,
    version TEXT NOT NULL,
    extension TEXT NOT NULL DEFAULT '',
    classifier TEXT NOT NULL DEFAULT '',
    artifact_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT artifact_coordinate_unique
        UNIQUE (format, package_name, version, extension, classifier),
    CONSTRAINT artifact_path_unique UNIQUE (artifact_path),
    CONSTRAINT artifact_coordinate_not_empty
        CHECK (
            length(trim(package_name)) > 0
            AND length(trim(version)) > 0
            AND length(trim(artifact_path)) > 0
        ),
    CONSTRAINT artifact_path_relative
        CHECK (
            artifact_path !~ '^/'
            AND artifact_path !~ '(^|/)\.\.?(/|$)'
            AND artifact_path !~ E'\\\\'
        ),
    CONSTRAINT format_coordinate_rules
        CHECK (
            (format <> 'maven2'
                OR (
                    package_name ~ '^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+$'
                    AND extension ~ '^[A-Za-z0-9]+$'
                ))
            AND
            (format <> 'npm'
                OR package_name ~ '^( @[a-z0-9._-]+/)?[a-z0-9._~-]+$')
        )
);

-- The composite uniqueness constraint identifies one coordinate independently
-- of the repository in which its binary is stored.
CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    artifact_version_id BIGINT NOT NULL
        REFERENCES artifact_versions(artifact_version_id),
    sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    origin TEXT NOT NULL
        CHECK (origin IN ('published', 'upstream_cache', 'replicated')),
    publisher_id BIGINT REFERENCES principals(principal_id),
    upstream_source TEXT,
    published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMPTZ,
    UNIQUE (repository_id, artifact_version_id),
    CONSTRAINT sha256_hex
        CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT hosted_publication_origin
        CHECK (
            (origin = 'published' AND publisher_id IS NOT NULL
                AND upstream_source IS NULL)
            OR
            (origin = 'upstream_cache' AND upstream_source IS NOT NULL)
            OR origin = 'replicated'
        )
);

CREATE TABLE repository_members (
    group_repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    member_repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE RESTRICT,
    member_priority INTEGER NOT NULL DEFAULT 100
        CHECK (member_priority >= 0),
    PRIMARY KEY (group_repository_id, member_repository_id),
    CONSTRAINT no_self_membership
        CHECK (group_repository_id <> member_repository_id)
);

CREATE TABLE status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    artifact_version_id BIGINT NOT NULL
        REFERENCES artifact_versions(artifact_version_id),
    check_name TEXT NOT NULL,
    result TEXT NOT NULL
        CHECK (result IN ('passed', 'failed', 'pending', 'skipped')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE artifact_retrievals (
    retrieval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    artifact_version_id BIGINT NOT NULL
        REFERENCES artifact_versions(artifact_version_id),
    principal_id BIGINT REFERENCES principals(principal_id),
    outcome TEXT NOT NULL
        CHECK (outcome IN ('hit', 'cache_miss', 'not_found', 'denied', 'error')),
    source_repository_id BIGINT REFERENCES repositories(repository_id),
    response_bytes BIGINT NOT NULL DEFAULT 0 CHECK (response_bytes >= 0),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_events (
    audit_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_id BIGINT REFERENCES principals(principal_id),
    repository_id BIGINT REFERENCES repositories(repository_id),
    artifact_version_id BIGINT REFERENCES artifact_versions(artifact_version_id),
    action TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX artifacts_repository_path_idx
    ON artifacts(repository_id, artifact_version_id);

CREATE INDEX artifact_versions_path_idx
    ON artifact_versions(artifact_path);

CREATE INDEX retrieval_repository_time_idx
    ON artifact_retrievals(repository_id, occurred_at DESC);

CREATE INDEX retrieval_failures_idx
    ON artifact_retrievals(outcome, occurred_at DESC)
    WHERE outcome IN ('not_found', 'denied', 'error');

CREATE INDEX audit_repository_time_idx
    ON audit_events(repository_id, occurred_at DESC);

CREATE INDEX status_check_latest_idx
    ON status_checks(repository_id, artifact_version_id, checked_at DESC);

CREATE VIEW artifact_inventory AS
SELECT
    r.repository_name,
    r.repository_type,
    r.format,
    v.package_name,
    v.version,
    v.extension,
    v.artifact_path,
    a.sha256,
    a.size_bytes,
    a.origin,
    p.username AS publisher,
    a.published_at,
    a.last_verified_at
FROM artifacts a
JOIN repositories r USING (repository_id)
JOIN artifact_versions v USING (artifact_version_id)
LEFT JOIN principals p ON p.principal_id = a.publisher_id;

CREATE VIEW repository_cache_metrics AS
SELECT
    r.repository_name,
    r.repository_type,
    COUNT(ar.retrieval_id) AS total_requests,
    COUNT(*) FILTER (WHERE ar.outcome = 'hit') AS cache_hits,
    COUNT(*) FILTER (WHERE ar.outcome = 'cache_miss') AS cache_misses,
    COUNT(*) FILTER (WHERE ar.outcome = 'not_found') AS not_found_count,
    COUNT(*) FILTER (WHERE ar.outcome = 'denied') AS denied_count
FROM repositories r
LEFT JOIN artifact_retrievals ar USING (repository_id)
GROUP BY r.repository_id, r.repository_name, r.repository_type;

INSERT INTO repositories (
    repository_name, repository_type, format, upstream_url, allow_redeploy
)
VALUES
    ('maven-releases', 'hosted', 'maven2', NULL, FALSE),
    ('maven-central-cache', 'proxy', 'maven2',
        'https://repo1.maven.org/maven2', FALSE),
    ('maven-public', 'group', 'maven2', NULL, FALSE),
    ('npm-internal', 'hosted', 'npm', NULL, FALSE),
    ('pypi-internal', 'hosted', 'pypi', NULL, FALSE),
    ('docker-internal', 'hosted', 'docker', NULL, FALSE);

INSERT INTO principals (username)
VALUES ('release-engineer'), ('build-agent'), ('anonymous-test');

INSERT INTO repository_permissions (
    repository_id, principal_id, can_read, can_publish, can_delete, can_admin
)
SELECT
    r.repository_id,
    p.principal_id,
    CASE
        WHEN p.username = 'release-engineer' THEN TRUE
        WHEN p.username = 'build-agent' AND r.repository_type <> 'hosted' THEN TRUE
        WHEN p.username = 'build-agent' AND r.repository_name = 'maven-releases' THEN TRUE
        ELSE FALSE
    END,
    p.username = 'release-engineer'
        AND r.repository_type = 'hosted',
    FALSE,
    FALSE
FROM repositories r
CROSS JOIN principals p
WHERE p.username <> 'anonymous-test';

-- An explicit denial record remains useful for audit demonstrations even when
-- an actual authorization layer rejects the request before binary retrieval.
INSERT INTO artifact_versions (
    format, package_name, version, extension, artifact_path
)
VALUES
    ('maven2', 'com.example.billing:billing-client', '4.1.0', 'jar',
     'com/example/billing/billing-client/4.1.0/billing-client-4.1.0.jar'),
    ('maven2', 'org.example:metrics-core', '1.0.0', 'jar',
     'org/example/metrics-core/1.0.0/metrics-core-1.0.0.jar'),
    ('npm', '@example/payment-sdk', '2.0.0', 'tgz',
     '@example/payment-sdk/-/payment-sdk-2.0.0.tgz'),
    ('pypi', 'payment_utils', '0.8.2', 'whl',
     'payment-utils/0.8.2/payment_utils-0.8.2-py3-none-any.whl'),
    ('docker', 'payments/api', '4.1.0', 'manifest',
     'payments/api/manifests/4.1.0');

-- Membership priority controls which member is queried first by a group resolver.
INSERT INTO repository_members (
    group_repository_id, member_repository_id, member_priority
)
SELECT group_repo.repository_id, member.repository_id, member.priority
FROM (
    VALUES
        ('maven-public', 'maven-releases', 10),
        ('maven-public', 'maven-central-cache', 20)
) AS member_data(group_name, member_name, priority)
JOIN repositories group_repo
    ON group_repo.repository_name = member_data.group_name
JOIN repositories member
    ON member.repository_name = member_data.member_name
CROSS JOIN LATERAL (
    SELECT member_data.priority
) AS member;

-- Publish a release with digest metadata. The digest is a fixed, valid-looking
-- demonstration value; real publication must calculate SHA-256 from the bytes.
INSERT INTO artifacts (
    repository_id, artifact_version_id, sha256, size_bytes,
    origin, publisher_id, last_verified_at
)
SELECT
    r.repository_id,
    v.artifact_version_id,
    repeat('a', 64),
    245760,
    'published',
    p.principal_id,
    CURRENT_TIMESTAMP
FROM repositories r
JOIN artifact_versions v
    ON v.package_name = 'com.example.billing:billing-client'
   AND v.version = '4.1.0'
JOIN principals p ON p.username = 'release-engineer'
WHERE r.repository_name = 'maven-releases';

-- Model the first successful retrieval and a subsequent cache hit.
INSERT INTO artifact_retrievals (
    repository_id, artifact_version_id, principal_id,
    outcome, source_repository_id, response_bytes
)
SELECT
    group_repo.repository_id,
    v.artifact_version_id,
    p.principal_id,
    'hit',
    hosted.repository_id,
    245760
FROM repositories group_repo
JOIN repositories hosted ON hosted.repository_name = 'maven-releases'
JOIN artifact_versions v
    ON v.package_name = 'com.example.billing:billing-client'
   AND v.version = '4.1.0'
JOIN principals p ON p.username = 'build-agent'
WHERE group_repo.repository_name = 'maven-public';

INSERT INTO artifact_retrievals (
    repository_id, artifact_version_id, principal_id,
    outcome, source_repository_id, response_bytes
)
SELECT
    r.repository_id, v.artifact_version_id, p.principal_id,
    'cache_miss', NULL, 0
FROM repositories r
JOIN artifact_versions v
    ON v.package_name = 'org.example:metrics-core'
   AND v.version = '1.0.0'
JOIN principals p ON p.username = 'build-agent'
WHERE r.repository_name = 'maven-central-cache';

INSERT INTO artifact_retrievals (
    repository_id, artifact_version_id, principal_id,
    outcome, source_repository_id, response_bytes
)
SELECT
    r.repository_id, v.artifact_version_id, p.principal_id,
    'not_found', NULL, 0
FROM repositories r
JOIN artifact_versions v
    ON v.package_name = 'org.example:metrics-core'
   AND v.version = '1.0.0'
JOIN principals p ON p.username = 'build-agent'
WHERE r.repository_name = 'maven-public';

INSERT INTO artifact_retrievals (
    repository_id, artifact_version_id, principal_id,
    outcome, source_repository_id, response_bytes
)
SELECT
    r.repository_id, v.artifact_version_id, p.principal_id,
    'denied', NULL, 0
FROM repositories r
JOIN artifact_versions v
    ON v.package_name = '@example/payment-sdk'
   AND v.version = '2.0.0'
JOIN principals p ON p.username = 'anonymous-test'
WHERE r.repository_name = 'npm-internal';

INSERT INTO status_checks (
    repository_id, artifact_version_id, check_name, result, details
)
SELECT
    r.repository_id,
    v.artifact_version_id,
    checks.check_name,
    checks.result,
    checks.details::jsonb
FROM (
    VALUES
        ('maven-releases', 'com.example.billing:billing-client', '4.1.0',
         'checksum-verification', 'passed',
         '{"algorithm":"SHA-256","verified":true}'),
        ('maven-releases', 'com.example.billing:billing-client', '4.1.0',
         'release-policy', 'passed',
         '{"redeployment_allowed":false}'),
        ('maven-central-cache', 'org.example:metrics-core', '1.0.0',
         'upstream-availability', 'failed',
         '{"http_status":404}')
) AS checks(repository_name, package_name, version, check_name, result, details)
JOIN repositories r ON r.repository_name = checks.repository_name
JOIN artifact_versions v
    ON v.package_name = checks.package_name
   AND v.version = checks.version;

INSERT INTO audit_events (
    principal_id, repository_id, artifact_version_id,
    action, outcome, event_data
)
SELECT
    p.principal_id,
    r.repository_id,
    v.artifact_version_id,
    'ARTIFACT_PUBLISHED',
    'success',
    jsonb_build_object(
        'path', v.artifact_path,
        'digest_algorithm', 'SHA-256',
        'immutable_release', TRUE
    )
FROM principals p
JOIN repositories r ON r.repository_name = 'maven-releases'
JOIN artifact_versions v
    ON v.package_name = 'com.example.billing:billing-client'
   AND v.version = '4.1.0'
WHERE p.username = 'release-engineer';

COMMIT;

-- Inventory of binaries and metadata stored in repositories.
SELECT
    repository_name,
    repository_type,
    format,
    package_name,
    version,
    artifact_path,
    sha256,
    size_bytes,
    publisher
FROM artifact_inventory
ORDER BY repository_name, artifact_path;

-- Identify proxy and group resolution problems from observed requests.
SELECT
    repository_name,
    total_requests,
    cache_hits,
    cache_misses,
    not_found_count,
    denied_count
FROM repository_cache_metrics
WHERE total_requests > 0
ORDER BY repository_name;

-- Retrieve the most recent status result for each artifact and check name.
WITH ranked_checks AS (
    SELECT
        r.repository_name,
        v.artifact_path,
        s.check_name,
        s.result,
        s.details,
        s.checked_at,
        ROW_NUMBER() OVER (
            PARTITION BY s.repository_id, s.artifact_version_id, s.check_name
            ORDER BY s.checked_at DESC, s.status_check_id DESC
        ) AS position
    FROM status_checks s
    JOIN repositories r USING (repository_id)
    JOIN artifact_versions v USING (artifact_version_id)
)
SELECT repository_name, artifact_path, check_name, result, details
FROM ranked_checks
WHERE position = 1
ORDER BY repository_name, artifact_path, check_name;

-- A release coordinate must not be duplicated in the same repository.
-- The following query is safe to run repeatedly and returns existing conflicts.
SELECT
    repository_name,
    artifact_path,
    COUNT(*) AS stored_copies
FROM artifact_inventory
GROUP BY repository_name, artifact_path
HAVING COUNT(*) > 1;

-- Verify that group membership references groups and compatible formats.
SELECT
    group_repo.repository_name AS group_name,
    member_repo.repository_name AS member_name,
    group_repo.format AS group_format,
    member_repo.format AS member_format,
    rm.member_priority
FROM repository_members rm
JOIN repositories group_repo
    ON group_repo.repository_id = rm.group_repository_id
JOIN repositories member_repo
    ON member_repo.repository_id = rm.member_repository_id
WHERE group_repo.repository_type <> 'group'
   OR group_repo.format <> member_repo.format;

-- Show audit events for incident investigation.
SELECT
    ae.occurred_at,
    p.username,
    r.repository_name,
    ae.action,
    ae.outcome,
    ae.event_data
FROM audit_events ae
LEFT JOIN principals p USING (principal_id)
LEFT JOIN repositories r USING (repository_id)
ORDER BY ae.occurred_at DESC, ae.audit_event_id DESC;

-- Demonstrate transaction rollback for an invalid duplicate artifact insertion.
-- The uniqueness violation is caught by a savepoint so the script can continue.
BEGIN;
SAVEPOINT before_duplicate_test;

DO $$
BEGIN
    BEGIN
        INSERT INTO artifacts (
            repository_id, artifact_version_id, sha256, size_bytes,
            origin, publisher_id
        )
        SELECT
            r.repository_id,
            v.artifact_version_id,
            repeat('b', 64),
            245760,
            'published',
            p.principal_id
        FROM repositories r
        JOIN artifact_versions v
            ON v.package_name = 'com.example.billing:billing-client'
           AND v.version = '4.1.0'
        JOIN principals p ON p.username = 'release-engineer'
        WHERE r.repository_name = 'maven-releases';

        RAISE EXCEPTION 'Expected duplicate coordinate constraint violation';
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Duplicate artifact rejected by database constraint';
    END;
END;
$$;

ROLLBACK TO SAVEPOINT before_duplicate_test;
COMMIT;

-- Inspect permissions without exposing credentials or binary content.
SELECT
    r.repository_name,
    p.username,
    rp.can_read,
    rp.can_publish,
    rp.can_delete,
    rp.can_admin
FROM repository_permissions rp
JOIN repositories r USING (repository_id)
JOIN principals p USING (principal_id)
ORDER BY r.repository_name, p.username;

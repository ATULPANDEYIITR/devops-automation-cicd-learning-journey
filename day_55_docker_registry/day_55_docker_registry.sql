BEGIN;

CREATE SCHEMA IF NOT EXISTS registry_lab;
SET LOCAL search_path = registry_lab, public;

-- Registries represent Docker Hub namespaces or independently operated registries.
CREATE TABLE IF NOT EXISTS registries (
    registry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hostname text NOT NULL UNIQUE,
    provider text NOT NULL CHECK (
        provider IN ('docker_hub', 'private', 'cloud')
    ),
    visibility text NOT NULL CHECK (visibility IN ('public', 'private')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS principals (
    principal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS registry_memberships (
    registry_id bigint NOT NULL REFERENCES registries(registry_id),
    principal_id bigint NOT NULL REFERENCES principals(principal_id),
    role text NOT NULL CHECK (role IN ('reader', 'publisher', 'admin')),
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (registry_id, principal_id)
);

CREATE TABLE IF NOT EXISTS repositories (
    repository_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_id bigint NOT NULL REFERENCES registries(registry_id),
    repository_name text NOT NULL,
    owner_principal_id bigint REFERENCES principals(principal_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (registry_id, repository_name),
    CHECK (
        repository_name = lower(repository_name)
        AND length(repository_name) BETWEEN 1 AND 255
        AND repository_name !~ '(^/|/$|//|[^a-z0-9._/-])'
    )
);

CREATE TABLE IF NOT EXISTS image_manifests (
    manifest_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id bigint NOT NULL REFERENCES repositories(repository_id),
    digest text NOT NULL CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    media_type text NOT NULL CHECK (
        media_type IN (
            'application/vnd.oci.image.manifest.v1+json',
            'application/vnd.docker.distribution.manifest.v2+json',
            'application/vnd.oci.image.index.v1+json'
        )
    ),
    platform_os text NOT NULL,
    platform_architecture text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository_id, digest)
);

CREATE TABLE IF NOT EXISTS image_tags (
    tag_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id bigint NOT NULL REFERENCES repositories(repository_id),
    tag_name text NOT NULL CHECK (
        tag_name ~ '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'
    ),
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    immutable boolean NOT NULL DEFAULT false,
    published_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository_id, tag_name)
);

CREATE TABLE IF NOT EXISTS image_signatures (
    signature_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    signer text NOT NULL,
    verification_status text NOT NULL CHECK (
        verification_status IN ('verified', 'invalid', 'unknown')
    ),
    verified_at timestamptz,
    UNIQUE (manifest_id, signer),
    CHECK (
        (verification_status = 'verified' AND verified_at IS NOT NULL)
        OR verification_status <> 'verified'
    )
);

CREATE TABLE IF NOT EXISTS vulnerability_scans (
    scan_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    scanner text NOT NULL,
    scan_status text NOT NULL CHECK (
        scan_status IN ('pass', 'fail', 'unknown')
    ),
    critical_count integer NOT NULL DEFAULT 0 CHECK (critical_count >= 0),
    high_count integer NOT NULL DEFAULT 0 CHECK (high_count >= 0),
    scanned_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS publication_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id bigint NOT NULL REFERENCES repositories(repository_id),
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    principal_id bigint NOT NULL REFERENCES principals(principal_id),
    operation text NOT NULL CHECK (
        operation IN ('push', 'pull', 'tag', 'reject')
    ),
    outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failed')),
    details text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

-- Only successful publication events are eligible for operational reporting.
CREATE INDEX IF NOT EXISTS idx_publication_events_repository_time
    ON publication_events(repository_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_image_tags_manifest
    ON image_tags(manifest_id);

CREATE INDEX IF NOT EXISTS idx_vulnerability_scans_latest
    ON vulnerability_scans(manifest_id, scanned_at DESC);

CREATE TABLE IF NOT EXISTS registry_policies (
    policy_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_id bigint NOT NULL REFERENCES registries(registry_id),
    policy_name text NOT NULL,
    require_scan_pass boolean NOT NULL DEFAULT true,
    require_signature boolean NOT NULL DEFAULT true,
    require_provenance boolean NOT NULL DEFAULT true,
    maximum_size_bytes bigint NOT NULL DEFAULT 500000000
        CHECK (maximum_size_bytes > 0),
    immutable_release_tags boolean NOT NULL DEFAULT true,
    deny_critical_vulnerabilities boolean NOT NULL DEFAULT true,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (registry_id, policy_name)
);

CREATE TABLE IF NOT EXISTS build_provenance (
    provenance_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    source_repository text NOT NULL,
    source_revision text NOT NULL,
    builder_identity text NOT NULL,
    verified boolean NOT NULL DEFAULT false,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manifest_id, source_revision)
);

CREATE TABLE IF NOT EXISTS publication_decisions (
    decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id bigint NOT NULL REFERENCES repositories(repository_id),
    manifest_id bigint NOT NULL REFERENCES image_manifests(manifest_id),
    policy_id bigint NOT NULL REFERENCES registry_policies(policy_id),
    principal_id bigint NOT NULL REFERENCES principals(principal_id),
    eligible boolean NOT NULL,
    reasons text[] NOT NULL DEFAULT '{}',
    decided_at timestamptz NOT NULL DEFAULT now()
);

-- Prevent accidental reassignment of immutable release tags.
CREATE OR REPLACE FUNCTION enforce_immutable_release_tag()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_digest text;
    new_digest text;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.immutable THEN
        SELECT digest INTO old_digest
        FROM image_manifests
        WHERE manifest_id = OLD.manifest_id;

        SELECT digest INTO new_digest
        FROM image_manifests
        WHERE manifest_id = NEW.manifest_id;

        IF old_digest IS DISTINCT FROM new_digest THEN
            RAISE EXCEPTION
                'Immutable tag % cannot point to a different digest',
                OLD.tag_name;
        END IF;
    END IF;

    IF TG_OP = 'DELETE' AND OLD.immutable THEN
        RAISE EXCEPTION 'Immutable tag % cannot be deleted', OLD.tag_name;
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS image_tags_immutable_guard ON image_tags;
CREATE TRIGGER image_tags_immutable_guard
BEFORE UPDATE OR DELETE ON image_tags
FOR EACH ROW EXECUTE FUNCTION enforce_immutable_release_tag();

-- This function centralizes publication eligibility; a stored decision is
-- evidence of evaluation, not a substitute for access control at the registry.
CREATE OR REPLACE FUNCTION evaluate_publication(
    p_repository_id bigint,
    p_manifest_id bigint,
    p_policy_id bigint,
    p_principal_id bigint
)
RETURNS TABLE (
    eligible boolean,
    reasons text[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_registry_id bigint;
    v_policy registry_policies%ROWTYPE;
    v_size bigint;
    v_scan_status text;
    v_critical integer;
    v_signature_status text;
    v_provenance boolean;
    v_role text;
    v_reasons text[] := '{}';
BEGIN
    SELECT registry_id INTO v_registry_id
    FROM repositories
    WHERE repository_id = p_repository_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, ARRAY['Repository not found']::text[];
        RETURN;
    END IF;

    SELECT * INTO v_policy
    FROM registry_policies
    WHERE policy_id = p_policy_id
      AND registry_id = v_registry_id
      AND active;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, ARRAY['No active matching policy']::text[];
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM image_manifests
        WHERE manifest_id = p_manifest_id
          AND repository_id = p_repository_id
    ) THEN
        RETURN QUERY SELECT false, ARRAY['Manifest does not belong to repository']::text[];
        RETURN;
    END IF;

    SELECT role INTO v_role
    FROM registry_memberships
    WHERE registry_id = v_registry_id
      AND principal_id = p_principal_id;

    IF v_role IS NULL OR v_role NOT IN ('publisher', 'admin') THEN
        v_reasons := array_append(v_reasons, 'Publisher permission required');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM principals
        WHERE principal_id = p_principal_id AND enabled
    ) THEN
        v_reasons := array_append(v_reasons, 'Principal is disabled or missing');
    END IF;

    SELECT size_bytes INTO v_size
    FROM image_manifests WHERE manifest_id = p_manifest_id;

    IF v_size > v_policy.maximum_size_bytes THEN
        v_reasons := array_append(v_reasons, 'Image exceeds size limit');
    END IF;

    SELECT scan_status, critical_count
    INTO v_scan_status, v_critical
    FROM vulnerability_scans
    WHERE manifest_id = p_manifest_id
    ORDER BY scanned_at DESC, scan_id DESC
    LIMIT 1;

    IF v_policy.require_scan_pass AND
       (v_scan_status IS DISTINCT FROM 'pass') THEN
        v_reasons := array_append(v_reasons, 'Latest vulnerability scan must pass');
    END IF;

    IF v_policy.deny_critical_vulnerabilities AND
       COALESCE(v_critical, 0) > 0 THEN
        v_reasons := array_append(v_reasons, 'Critical vulnerabilities detected');
    END IF;

    IF v_policy.require_signature AND NOT EXISTS (
        SELECT 1 FROM image_signatures
        WHERE manifest_id = p_manifest_id
          AND verification_status = 'verified'
    ) THEN
        v_reasons := array_append(v_reasons, 'Verified signature required');
    END IF;

    SELECT bool_or(verified) INTO v_provenance
    FROM build_provenance
    WHERE manifest_id = p_manifest_id;

    IF v_policy.require_provenance AND COALESCE(v_provenance, false) = false THEN
        v_reasons := array_append(v_reasons, 'Verified build provenance required');
    END IF;

    RETURN QUERY SELECT cardinality(v_reasons) = 0, v_reasons;
END;
$$;

-- Sample data covers Docker Hub, a private registry, valid publication,
-- missing scan evidence, an unverified signature, and a reader without push rights.
INSERT INTO registries(hostname, provider, visibility)
VALUES
    ('docker.io', 'docker_hub', 'public'),
    ('registry.example.com', 'private', 'private')
ON CONFLICT (hostname) DO NOTHING;

INSERT INTO principals(username)
VALUES ('release-bot'), ('deployment-bot'), ('untrusted-user')
ON CONFLICT (username) DO NOTHING;

INSERT INTO registry_memberships(registry_id, principal_id, role)
SELECT r.registry_id, p.principal_id, x.role
FROM (VALUES
    ('registry.example.com', 'release-bot', 'publisher'),
    ('registry.example.com', 'deployment-bot', 'reader'),
    ('registry.example.com', 'untrusted-user', 'reader'),
    ('docker.io', 'release-bot', 'publisher')
) AS x(hostname, username, role)
JOIN registries r ON r.hostname = x.hostname
JOIN principals p ON p.username = x.username
ON CONFLICT (registry_id, principal_id)
DO UPDATE SET role = EXCLUDED.role;

INSERT INTO repositories(registry_id, repository_name, owner_principal_id)
SELECT r.registry_id, x.repository_name, p.principal_id
FROM (VALUES
    ('registry.example.com', 'commerce/orders-api', 'release-bot'),
    ('registry.example.com', 'commerce/payments-api', 'release-bot'),
    ('docker.io', 'learning/orders-api', 'release-bot')
) AS x(hostname, repository_name, owner)
JOIN registries r ON r.hostname = x.hostname
JOIN principals p ON p.username = x.owner
ON CONFLICT (registry_id, repository_name) DO NOTHING;

INSERT INTO registry_policies(
    registry_id, policy_name, require_scan_pass, require_signature,
    require_provenance, maximum_size_bytes, immutable_release_tags,
    deny_critical_vulnerabilities
)
SELECT registry_id, 'production-release', true, true, true, 500000000, true, true
FROM registries
WHERE hostname = 'registry.example.com'
ON CONFLICT (registry_id, policy_name) DO NOTHING;

INSERT INTO image_manifests(
    repository_id, digest, size_bytes, media_type,
    platform_os, platform_architecture
)
SELECT repository_id,
       'sha256:' || repeat('a', 64),
       125000,
       'application/vnd.oci.image.manifest.v1+json',
       'linux',
       'amd64'
FROM repositories
WHERE repository_name = 'commerce/orders-api'
ON CONFLICT (repository_id, digest) DO NOTHING;

INSERT INTO image_manifests(
    repository_id, digest, size_bytes, media_type,
    platform_os, platform_architecture
)
SELECT repository_id,
       'sha256:' || repeat('b', 64),
       130000,
       'application/vnd.oci.image.manifest.v1+json',
       'linux',
       'arm64'
FROM repositories
WHERE repository_name = 'commerce/orders-api'
ON CONFLICT (repository_id, digest) DO NOTHING;

INSERT INTO image_tags(repository_id, tag_name, manifest_id, immutable)
SELECT m.repository_id, 'v2.4.1', m.manifest_id, true
FROM image_manifests m
JOIN repositories r USING (repository_id)
WHERE r.repository_name = 'commerce/orders-api'
  AND m.digest = 'sha256:' || repeat('a', 64)
ON CONFLICT (repository_id, tag_name) DO NOTHING;

INSERT INTO vulnerability_scans(
    manifest_id, scanner, scan_status, critical_count, high_count
)
SELECT manifest_id, 'release-scanner', 'pass', 0, 1
FROM image_manifests
WHERE digest = 'sha256:' || repeat('a', 64)
ON CONFLICT DO NOTHING;

INSERT INTO vulnerability_scans(
    manifest_id, scanner, scan_status, critical_count, high_count
)
SELECT manifest_id, 'release-scanner', 'fail', 1, 4
FROM image_manifests
WHERE digest = 'sha256:' || repeat('b', 64)
ON CONFLICT DO NOTHING;

INSERT INTO image_signatures(manifest_id, signer, verification_status, verified_at)
SELECT manifest_id, 'release-signing-key', 'verified', now()
FROM image_manifests
WHERE digest = 'sha256:' || repeat('a', 64)
ON CONFLICT (manifest_id, signer) DO NOTHING;

INSERT INTO image_signatures(manifest_id, signer, verification_status)
SELECT manifest_id, 'untrusted-key', 'invalid'
FROM image_manifests
WHERE digest = 'sha256:' || repeat('b', 64)
ON CONFLICT (manifest_id, signer) DO NOTHING;

INSERT INTO build_provenance(
    manifest_id, source_repository, source_revision, builder_identity, verified
)
SELECT manifest_id, 'company/orders-api', repeat('c', 40), 'trusted-ci', true
FROM image_manifests
WHERE digest = 'sha256:' || repeat('a', 64)
ON CONFLICT (manifest_id, source_revision) DO NOTHING;

-- Evaluate both the compliant image and the image with failed security evidence.
INSERT INTO publication_decisions(
    repository_id, manifest_id, policy_id, principal_id, eligible, reasons
)
SELECT r.repository_id, m.manifest_id, p.policy_id, pr.principal_id,
       decision.eligible, decision.reasons
FROM repositories r
JOIN registries g USING (registry_id)
JOIN image_manifests m USING (repository_id)
JOIN registry_policies p ON p.registry_id = g.registry_id
JOIN principals pr ON pr.username = 'release-bot'
CROSS JOIN LATERAL evaluate_publication(
    r.repository_id, m.manifest_id, p.policy_id, pr.principal_id
) AS decision
WHERE r.repository_name = 'commerce/orders-api'
  AND g.hostname = 'registry.example.com'
ON CONFLICT DO NOTHING;

INSERT INTO publication_events(
    repository_id, manifest_id, principal_id, operation, outcome, details
)
SELECT r.repository_id, m.manifest_id, pr.principal_id,
       CASE WHEN d.eligible THEN 'push' ELSE 'reject' END,
       CASE WHEN d.eligible THEN 'success' ELSE 'denied' END,
       array_to_string(d.reasons, '; ')
FROM publication_decisions d
JOIN repositories r USING (repository_id)
JOIN image_manifests m USING (manifest_id)
JOIN principals pr USING (principal_id)
ON CONFLICT DO NOTHING;

-- Report image tags, digests, platform, and latest scan evidence.
CREATE OR REPLACE VIEW image_catalog AS
SELECT
    g.hostname,
    r.repository_name,
    t.tag_name,
    m.digest,
    m.size_bytes,
    m.platform_os || '/' || m.platform_architecture AS platform,
    scan.scan_status AS latest_scan_status,
    scan.critical_count,
    t.immutable
FROM image_tags t
JOIN repositories r USING (repository_id)
JOIN registries g USING (registry_id)
JOIN image_manifests m USING (manifest_id)
LEFT JOIN LATERAL (
    SELECT s.scan_status, s.critical_count
    FROM vulnerability_scans s
    WHERE s.manifest_id = m.manifest_id
    ORDER BY s.scanned_at DESC, s.scan_id DESC
    LIMIT 1
) scan ON true;

-- Demonstrate transactional evaluation before recording a publication decision.
DO $$
DECLARE
    v_repository_id bigint;
    v_manifest_id bigint;
    v_policy_id bigint;
    v_principal_id bigint;
    v_allowed boolean;
    v_reasons text[];
BEGIN
    SELECT r.repository_id, m.manifest_id, p.policy_id, pr.principal_id
    INTO v_repository_id, v_manifest_id, v_policy_id, v_principal_id
    FROM repositories r
    JOIN registries g USING (registry_id)
    JOIN image_manifests m USING (repository_id)
    JOIN registry_policies p ON p.registry_id = g.registry_id
    JOIN principals pr ON pr.username = 'release-bot'
    WHERE r.repository_name = 'commerce/orders-api'
      AND g.hostname = 'registry.example.com'
      AND m.digest = 'sha256:' || repeat('a', 64)
    LIMIT 1;

    SELECT e.eligible, e.reasons
    INTO v_allowed, v_reasons
    FROM evaluate_publication(
        v_repository_id, v_manifest_id, v_policy_id, v_principal_id
    ) e;

    IF NOT v_allowed THEN
        RAISE NOTICE 'Publication blocked: %', array_to_string(v_reasons, '; ');
    ELSE
        RAISE NOTICE 'Publication approved for manifest %', v_manifest_id;
    END IF;
END;
$$;

-- Retrieval: inspect the catalog.
SELECT * FROM image_catalog ORDER BY hostname, repository_name, tag_name;

-- Evaluation: show why each candidate is allowed or blocked.
SELECT
    r.repository_name,
    m.digest,
    d.eligible,
    d.reasons,
    d.decided_at
FROM publication_decisions d
JOIN repositories r USING (repository_id)
JOIN image_manifests m USING (manifest_id)
ORDER BY d.decided_at, m.digest;

-- Aggregation: publication outcomes and transferred manifest bytes.
SELECT
    g.hostname,
    e.operation,
    e.outcome,
    count(*) AS event_count,
    sum(m.size_bytes) AS manifest_bytes
FROM publication_events e
JOIN repositories r USING (repository_id)
JOIN registries g USING (registry_id)
JOIN image_manifests m USING (manifest_id)
GROUP BY g.hostname, e.operation, e.outcome
ORDER BY g.hostname, e.operation, e.outcome;

-- Workflow status: latest scan per manifest.
WITH ranked_scans AS (
    SELECT s.*,
           row_number() OVER (
               PARTITION BY manifest_id
               ORDER BY scanned_at DESC, scan_id DESC
           ) AS position
    FROM vulnerability_scans s
)
SELECT
    r.repository_name,
    m.digest,
    rs.scan_status,
    rs.critical_count,
    rs.high_count,
    rs.scanned_at
FROM ranked_scans rs
JOIN image_manifests m USING (manifest_id)
JOIN repositories r USING (repository_id)
WHERE rs.position = 1
ORDER BY r.repository_name, m.digest;

-- Failure case: a reader attempting publication is denied by the eligibility function.
SELECT
    pr.username,
    r.repository_name,
    result.eligible,
    result.reasons
FROM principals pr
JOIN repositories r ON r.repository_name = 'commerce/orders-api'
JOIN registries g USING (registry_id)
JOIN image_manifests m USING (repository_id)
JOIN registry_policies p ON p.registry_id = g.registry_id
CROSS JOIN LATERAL evaluate_publication(
    r.repository_id, m.manifest_id, p.policy_id, pr.principal_id
) AS result
WHERE pr.username = 'deployment-bot'
  AND g.hostname = 'registry.example.com'
ORDER BY m.digest;

COMMIT;

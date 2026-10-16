"use strict";

/*
 * Nexus Repository workflow laboratory.
 *
 * This Node.js program focuses on asynchronous publishing and retrieval,
 * repository-specific format rules, content-addressed integrity, upstream
 * caching, and concurrent publication conflicts.
 *
 * Run with Node.js 18 or later. No third-party packages are required.
 */

const crypto = require("node:crypto");
const assert = require("node:assert/strict");

class RepositoryError extends Error {}
class ValidationError extends RepositoryError {}
class AuthorizationError extends RepositoryError {}
class NotFoundError extends RepositoryError {}
class ConflictError extends RepositoryError {}
class UpstreamError extends RepositoryError {}

const RepositoryType = Object.freeze({
  HOSTED: "hosted",
  PROXY: "proxy",
  GROUP: "group",
});

const Format = Object.freeze({
  MAVEN: "maven",
  NPM: "npm",
  PYPI: "pypi",
  DOCKER: "docker",
  RAW: "raw",
});

const Permission = Object.freeze({
  READ: "read",
  PUBLISH: "publish",
  DELETE: "delete",
});

function sha256(content) {
  return crypto.createHash("sha256").update(content).digest("hex");
}

function validateCoordinate(coordinate) {
  const { format, name, version } = coordinate;

  if (!Object.values(Format).includes(format)) {
    throw new ValidationError(`Unsupported artifact format: ${format}`);
  }

  if (typeof name !== "string" || !name.trim()) {
    throw new ValidationError("Artifact name is required.");
  }

  if (typeof version !== "string" || !version.trim()) {
    throw new ValidationError("Artifact version is required.");
  }

  if (/[\0-\x1f\\]/.test(name) || /[\/\\\0-\x1f]/.test(version)) {
    throw new ValidationError("Unsafe coordinate characters.");
  }

  if (name.split("/").some((part) => part === "." || part === "..")) {
    throw new ValidationError("Path traversal is not allowed.");
  }

  if (format === Format.MAVEN) {
    if (!/^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+$/.test(name)) {
      throw new ValidationError("Maven coordinates require group:artifact.");
    }
    if (!/^[A-Za-z0-9]+$/.test(coordinate.extension || "")) {
      throw new ValidationError("A valid Maven extension is required.");
    }
  }

  if (format === Format.NPM &&
      !/^(?:@[a-z0-9._-]+\/)?[a-z0-9._~-]+$/.test(name)) {
    throw new ValidationError("Invalid npm package name.");
  }

  if (format === Format.PYPI && !/^[A-Za-z0-9._-]+$/.test(name)) {
    throw new ValidationError("Invalid PyPI project name.");
  }

  if (format === Format.DOCKER && !/^[a-z0-9]+(?:[._/-][a-z0-9]+)*$/.test(name)) {
    throw new ValidationError("Invalid Docker image name.");
  }

  if (format === Format.RAW) {
    const rawPath = coordinate.path || "";
    if (
      !rawPath ||
      rawPath.startsWith("/") ||
      rawPath.split("/").some((part) => !part || part === "." || part === "..")
    ) {
      throw new ValidationError("Raw artifacts require a safe relative path.");
    }
  }
}

function artifactKey(coordinate) {
  validateCoordinate(coordinate);

  if (coordinate.format === Format.MAVEN) {
    const [group, artifact] = coordinate.name.split(":");
    const classifier = coordinate.classifier ? `-${coordinate.classifier}` : "";
    const filename = `${artifact}-${coordinate.version}${classifier}.${coordinate.extension}`;
    return `${group.replaceAll(".", "/")}/${artifact}/${coordinate.version}/${filename}`;
  }

  if (coordinate.format === Format.NPM) {
    const packageName = coordinate.name.replace("/", "%2f");
    const unscopedName = packageName.split("%2f").at(-1);
    return `${packageName}/-/${unscopedName}-${coordinate.version}.tgz`;
  }

  if (coordinate.format === Format.PYPI) {
    const project = coordinate.name.replace(/[-_.]+/g, "-").toLowerCase();
    return `${project}/${coordinate.version}/${coordinate.filename || `${project}-${coordinate.version}.whl`}`;
  }

  if (coordinate.format === Format.DOCKER) {
    return `${coordinate.name}/manifests/${coordinate.version}`;
  }

  return coordinate.path;
}

class Principal {
  constructor(username, grants = {}) {
    this.username = username;
    this.grants = new Map(
      Object.entries(grants).map(([repository, permissions]) => [
        repository,
        new Set(permissions),
      ]),
    );
  }

  can(repository, permission) {
    return this.grants.get(repository)?.has(permission) ||
      this.grants.get("*")?.has(permission) ||
      false;
  }
}

class Repository {
  constructor({
    name,
    type,
    format,
    members = [],
    upstream = null,
    redeploy = false,
    fetcher = null,
  }) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) {
      throw new ValidationError("Invalid repository name.");
    }

    if (type === RepositoryType.PROXY && !upstream && !fetcher) {
      throw new ValidationError("A proxy requires an upstream or fetcher.");
    }

    if (type === RepositoryType.GROUP && (!members.length || upstream)) {
      throw new ValidationError("A group needs members and cannot have an upstream.");
    }

    if (type !== RepositoryType.HOSTED && redeploy) {
      throw new ValidationError("Redeployment policy is hosted-only.");
    }

    this.name = name;
    this.type = type;
    this.format = format;
    this.members = [...members];
    this.upstream = upstream;
    this.redeploy = redeploy;
    this.fetcher = fetcher;
    this.artifacts = new Map();
    this.metrics = { hits: 0, misses: 0 };
  }
}

class NexusService {
  constructor() {
    this.repositories = new Map();
    this.audit = [];
    this.inFlight = new Map();
  }

  addRepository(repository) {
    if (this.repositories.has(repository.name)) {
      throw new ConflictError(`Repository already exists: ${repository.name}`);
    }

    for (const member of repository.members) {
      if (!this.repositories.has(member)) {
        throw new ValidationError(`Group member does not exist: ${member}`);
      }
    }

    this.repositories.set(repository.name, repository);
    this.audit.push({
      action: "repository_created",
      repository: repository.name,
      at: new Date().toISOString(),
    });
  }

  getRepository(name) {
    const repository = this.repositories.get(name);
    if (!repository) throw new RepositoryError(`Unknown repository: ${name}`);
    return repository;
  }

  authorize(principal, repositoryName, permission) {
    if (!principal.can(repositoryName, permission)) {
      throw new AuthorizationError(
        `${principal.username} lacks ${permission} permission on ${repositoryName}`,
      );
    }
  }

  async publish(repositoryName, coordinate, content, principal) {
    const repository = this.getRepository(repositoryName);
    this.authorize(principal, repositoryName, Permission.PUBLISH);

    if (repository.type !== RepositoryType.HOSTED) {
      throw new RepositoryError("Only hosted repositories accept publishing.");
    }

    if (coordinate.format !== repository.format) {
      throw new ValidationError("Artifact and repository formats differ.");
    }

    if (!(content instanceof Uint8Array) || content.byteLength === 0) {
      throw new ValidationError("Content must be non-empty binary data.");
    }

    const key = artifactKey(coordinate);
    const lockKey = `${repositoryName}:${key}`;

    // JavaScript executes each synchronous section on the event loop, but
    // publication may still overlap across asynchronous validation or I/O.
    // A per-coordinate promise serializes competing writers.
    const previous = this.inFlight.get(lockKey) || Promise.resolve();
    let release;
    const current = new Promise((resolve) => { release = resolve; });
    this.inFlight.set(lockKey, current);

    await previous;

    try {
      const existing = repository.artifacts.get(key);
      if (existing && !repository.redeploy) {
        throw new ConflictError(`Immutable artifact already exists: ${key}`);
      }

      const bytes = Buffer.from(content);
      const artifact = Object.freeze({
        key,
        coordinate: Object.freeze({ ...coordinate }),
        content: bytes,
        sha256: sha256(bytes),
        publishedBy: principal.username,
        publishedAt: new Date().toISOString(),
      });

      repository.artifacts.set(key, artifact);
      this.audit.push({
        action: "artifact_published",
        repository: repositoryName,
        key,
        sha256: artifact.sha256,
        user: principal.username,
      });
      return artifact;
    } finally {
      release();
      if (this.inFlight.get(lockKey) === current) {
        this.inFlight.delete(lockKey);
      }
    }
  }

  async retrieve(repositoryName, coordinate, principal, visited = new Set()) {
    this.authorize(principal, repositoryName, Permission.READ);
    return this.resolve(repositoryName, coordinate, visited);
  }

  async resolve(repositoryName, coordinate, visited) {
    if (visited.has(repositoryName)) {
      throw new RepositoryError("Repository resolution cycle detected.");
    }

    const repository = this.getRepository(repositoryName);
    if (coordinate.format !== repository.format) {
      throw new ValidationError("Artifact format does not match repository format.");
    }

    const key = artifactKey(coordinate);
    const existing = repository.artifacts.get(key);

    if (existing) {
      repository.metrics.hits += 1;
      if (sha256(existing.content) !== existing.sha256) {
        throw new RepositoryError(`Cached artifact checksum mismatch: ${key}`);
      }
      return existing;
    }

    repository.metrics.misses += 1;
    visited.add(repositoryName);

    if (repository.type === RepositoryType.HOSTED) {
      throw new NotFoundError(`Artifact not found: ${repositoryName}/${key}`);
    }

    if (repository.type === RepositoryType.GROUP) {
      for (const member of repository.members) {
        try {
          return await this.resolve(member, coordinate, new Set(visited));
        } catch (error) {
          if (!(error instanceof NotFoundError) &&
              !(error instanceof UpstreamError)) {
            throw error;
          }
        }
      }
      throw new NotFoundError(`No group member contains ${key}`);
    }

    const fetched = await this.fetchUpstream(repository, coordinate, key);
    repository.artifacts.set(key, fetched);
    return fetched;
  }

  async fetchUpstream(repository, coordinate, key) {
    // An injected fetcher makes upstream behavior testable without network access.
    if (repository.fetcher) {
      try {
        const content = await repository.fetcher(key);
        if (!(content instanceof Uint8Array) || content.byteLength === 0) {
          throw new UpstreamError("Upstream returned invalid content.");
        }
        const bytes = Buffer.from(content);
        return Object.freeze({
          key,
          coordinate: Object.freeze({ ...coordinate }),
          content: bytes,
          sha256: sha256(bytes),
          publishedBy: `upstream:${repository.name}`,
          publishedAt: new Date().toISOString(),
        });
      } catch (error) {
        if (error instanceof NotFoundError || error instanceof UpstreamError) {
          throw error;
        }
        throw new UpstreamError(`Upstream fetch failed: ${error.message}`);
      }
    }

    const base = new URL(repository.upstream);
    if (base.protocol !== "https:") {
      throw new UpstreamError("Configured upstream must use HTTPS.");
    }
    if (base.username || base.password) {
      throw new UpstreamError("Do not embed credentials in upstream URLs.");
    }

    const encodedPath = key.split("/").map(encodeURIComponent).join("/");
    const target = new URL(encodedPath, base.href.endsWith("/") ? base : `${base.href}/`);

    // Prevent a configured path or URL parser from changing the upstream host.
    if (target.origin !== base.origin) {
      throw new UpstreamError("Resolved upstream origin changed unexpectedly.");
    }

    const response = await fetch(target, { signal: AbortSignal.timeout(10000) });
    if (response.status === 404) {
      throw new NotFoundError(`Upstream artifact not found: ${key}`);
    }
    if (!response.ok) {
      throw new UpstreamError(`Upstream returned HTTP ${response.status}`);
    }

    const content = new Uint8Array(await response.arrayBuffer());
    if (content.byteLength === 0 || content.byteLength > 20 * 1024 * 1024) {
      throw new UpstreamError("Artifact size is outside the permitted demo range.");
    }

    return Object.freeze({
      key,
      coordinate: Object.freeze({ ...coordinate }),
      content: Buffer.from(content),
      sha256: sha256(content),
      publishedBy: `upstream:${repository.name}`,
      publishedAt: new Date().toISOString(),
    });
  }

  list(repositoryName, principal, { prefix = "", offset = 0, limit = 50 } = {}) {
    this.authorize(principal, repositoryName, Permission.READ);

    if (!Number.isInteger(offset) || offset < 0 ||
        !Number.isInteger(limit) || limit < 1 || limit > 200) {
      throw new ValidationError("Invalid pagination parameters.");
    }

    const repository = this.getRepository(repositoryName);
    return [...repository.artifacts.values()]
      .filter((artifact) => artifact.key.startsWith(prefix))
      .sort((a, b) => a.key.localeCompare(b.key))
      .slice(offset, offset + limit)
      .map(({ key, sha256: digest, content, publishedBy }) => ({
        key,
        sha256: digest,
        size: content.byteLength,
        publishedBy,
      }));
  }
}

async function main() {
  const service = new NexusService();

  service.addRepository(new Repository({
    name: "maven-releases",
    type: RepositoryType.HOSTED,
    format: Format.MAVEN,
  }));

  service.addRepository(new Repository({
    name: "maven-central-cache",
    type: RepositoryType.PROXY,
    format: Format.MAVEN,
    upstream: "https://repo1.maven.org/maven2/",
    fetcher: async (key) => {
      if (!key.endsWith("demo-library-1.0.0.jar")) {
        throw new NotFoundError(`No simulated upstream artifact at ${key}`);
      }
      return Buffer.from("simulated public dependency");
    },
  }));

  service.addRepository(new Repository({
    name: "maven-public",
    type: RepositoryType.GROUP,
    format: Format.MAVEN,
    members: ["maven-releases", "maven-central-cache"],
  }));

  service.addRepository(new Repository({
    name: "npm-private",
    type: RepositoryType.HOSTED,
    format: Format.NPM,
  }));

  const releaseEngineer = new Principal("release-engineer", {
    "maven-releases": [Permission.READ, Permission.PUBLISH],
    "maven-public": [Permission.READ],
    "maven-central-cache": [Permission.READ],
    "npm-private": [Permission.READ, Permission.PUBLISH],
  });

  const buildAgent = new Principal("build-agent", {
    "maven-releases": [Permission.READ],
    "maven-public": [Permission.READ],
    "maven-central-cache": [Permission.READ],
    "npm-private": [Permission.READ],
  });

  const release = {
    format: Format.MAVEN,
    name: "com.example.platform:platform-core",
    version: "3.2.1",
    extension: "jar",
  };

  const published = await service.publish(
    "maven-releases",
    release,
    Buffer.from("internal release binary"),
    releaseEngineer,
  );

  const resolved = await service.retrieve("maven-public", release, buildAgent);
  assert.equal(resolved.sha256, published.sha256);

  const dependency = {
    format: Format.MAVEN,
    name: "org.example:demo-library",
    version: "1.0.0",
    extension: "jar",
  };

  const firstFetch = await service.retrieve("maven-public", dependency, buildAgent);
  const secondFetch = await service.retrieve("maven-public", dependency, buildAgent);
  assert.equal(firstFetch.sha256, secondFetch.sha256);
  assert.equal(service.getRepository("maven-central-cache").artifacts.size, 1);

  const npmPackage = {
    format: Format.NPM,
    name: "@example/payment-sdk",
    version: "1.2.0",
  };

  await service.publish(
    "npm-private",
    npmPackage,
    Buffer.from("npm tarball bytes"),
    releaseEngineer,
  );

  const concurrentCoordinate = {
    format: Format.MAVEN,
    name: "com.example.platform:concurrent-module",
    version: "1.0.0",
    extension: "jar",
  };

  const concurrentResults = await Promise.allSettled([
    service.publish(
      "maven-releases",
      concurrentCoordinate,
      Buffer.from("writer A"),
      releaseEngineer,
    ),
    service.publish(
      "maven-releases",
      concurrentCoordinate,
      Buffer.from("writer B"),
      releaseEngineer,
    ),
  ]);

  assert.equal(
    concurrentResults.filter((result) => result.status === "fulfilled").length,
    1,
  );
  assert.equal(
    concurrentResults.filter((result) => result.status === "rejected").length,
    1,
  );

  await assert.rejects(
    service.publish(
      "maven-public",
      release,
      Buffer.from("wrong destination"),
      releaseEngineer,
    ),
    RepositoryError,
  );

  await assert.rejects(
    service.retrieve("npm-private", npmPackage, new Principal("guest")),
    AuthorizationError,
  );

  console.log(JSON.stringify({
    publishedArtifact: {
      path: published.key,
      sha256: published.sha256,
    },
    groupResolution: resolved.key,
    upstreamCache: service.getRepository("maven-central-cache").metrics,
    concurrentPublish: concurrentResults.map((result) => result.status),
    inventory: service.list("maven-releases", buildAgent),
    auditEvents: service.audit.length,
  }, null, 2));

  console.log("All repository workflow assertions passed.");
}

main().catch((error) => {
  console.error(`${error.name}: ${error.message}`);
  process.exitCode = 1;
});

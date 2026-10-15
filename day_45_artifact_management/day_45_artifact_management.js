"use strict";

/*
 * Artifact lifecycle and repository governance model.
 * Run with Node.js 18 or later: node artifact_management.js
 *
 * This example focuses on asynchronous publication, release channels,
 * event-driven audit records, digest verification, and immutable versions.
 */

const { createHash } = require("node:crypto");

class ArtifactError extends Error {}
class ValidationError extends ArtifactError {}
class ImmutableVersionError extends ArtifactError {}
class IntegrityError extends ArtifactError {}
class NotFoundError extends ArtifactError {}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function validateName(name) {
  if (
    typeof name !== "string" ||
    !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$/.test(name)
  ) {
    throw new ValidationError("Invalid artifact name.");
  }
}

function parseVersion(version) {
  const match =
    /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$/.exec(
      version
    );

  if (!match) {
    throw new ValidationError(`Invalid semantic version: ${version}`);
  }

  const prerelease = match[4] || "";

  for (const identifier of prerelease.split(".").filter(Boolean)) {
    if (/^\d+$/.test(identifier) && identifier.length > 1 && identifier.startsWith("0")) {
      throw new ValidationError("Numeric prerelease identifiers cannot have leading zeroes.");
    }
  }

  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease,
    build: match[5] || "",
  };
}

function compareIdentifiers(left, right) {
  const leftNumeric = /^\d+$/.test(left);
  const rightNumeric = /^\d+$/.test(right);

  if (leftNumeric && rightNumeric) {
    const a = BigInt(left);
    const b = BigInt(right);
    return a < b ? -1 : a > b ? 1 : 0;
  }

  if (leftNumeric !== rightNumeric) {
    return leftNumeric ? -1 : 1;
  }

  return left < right ? -1 : left > right ? 1 : 0;
}

function compareVersions(leftText, rightText) {
  const left = parseVersion(leftText);
  const right = parseVersion(rightText);

  for (const field of ["major", "minor", "patch"]) {
    if (left[field] !== right[field]) {
      return left[field] < right[field] ? -1 : 1;
    }
  }

  if (!left.prerelease && !right.prerelease) return 0;
  if (!left.prerelease) return 1;
  if (!right.prerelease) return -1;

  const a = left.prerelease.split(".");
  const b = right.prerelease.split(".");

  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const result = compareIdentifiers(a[index], b[index]);
    if (result !== 0) return result;
  }

  return a.length < b.length ? -1 : a.length > b.length ? 1 : 0;
}

class ArtifactRepository {
  #versions = new Map();
  #blobs = new Map();
  #listeners = new Map();
  #audit = [];
  #releaseChannels = new Map();
  #publishQueue = Promise.resolve();

  on(eventName, listener) {
    if (typeof listener !== "function") {
      throw new ValidationError("Event listener must be a function.");
    }

    const listeners = this.#listeners.get(eventName) || new Set();
    listeners.add(listener);
    this.#listeners.set(eventName, listeners);

    return () => listeners.delete(listener);
  }

  #emit(eventName, payload) {
    for (const listener of this.#listeners.get(eventName) || []) {
      try {
        listener(Object.freeze({ ...payload }));
      } catch (error) {
        // A monitoring subscriber must not roll back a completed publication.
        this.#audit.push({
          event: "listener_failure",
          eventName,
          message: String(error.message || error),
          timestamp: new Date().toISOString(),
        });
      }
    }
  }

  publish(input) {
    // Serialize writes to protect version uniqueness in this in-memory model.
    const operation = this.#publishQueue.then(() => this.#publish(input));
    this.#publishQueue = operation.catch(() => {});
    return operation;
  }

  async #publish(input) {
    const {
      name,
      version,
      content,
      publisher,
      sourceRevision,
      mediaType = "application/octet-stream",
      metadata = {},
    } = input;

    validateName(name);
    parseVersion(version);

    if (!Buffer.isBuffer(content) && !(content instanceof Uint8Array)) {
      throw new ValidationError("Content must be a Buffer or Uint8Array.");
    }

    if (typeof publisher !== "string" || !publisher.trim()) {
      throw new ValidationError("Publisher identity is required.");
    }

    if (typeof sourceRevision !== "string" || !sourceRevision.trim()) {
      throw new ValidationError("Source revision is required.");
    }

    if (typeof mediaType !== "string" || !mediaType.includes("/")) {
      throw new ValidationError("A valid media type is required.");
    }

    if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
      throw new ValidationError("Metadata must be a plain object.");
    }

    // Copy caller-owned bytes so subsequent mutation cannot alter the published payload.
    const bytes = Buffer.from(content);
    const digest = sha256(bytes);
    const key = `${name}@${version}`;
    const canonicalMetadata = JSON.stringify(
      Object.fromEntries(
        Object.entries(metadata).sort(([left], [right]) => left.localeCompare(right))
      )
    );

    const existing = this.#versions.get(key);

    if (existing) {
      const identical =
        existing.digest === digest &&
        existing.publisher === publisher &&
        existing.sourceRevision === sourceRevision &&
        existing.mediaType === mediaType &&
        existing.canonicalMetadata === canonicalMetadata;

      if (identical) {
        return existing;
      }

      throw new ImmutableVersionError(
        `${key} already exists. Publish a new version instead.`
      );
    }

    // Identical payloads share one blob, while version records remain distinct.
    if (!this.#blobs.has(digest)) {
      this.#blobs.set(digest, bytes);
    } else if (sha256(this.#blobs.get(digest)) !== digest) {
      throw new IntegrityError("Existing content-addressed blob failed verification.");
    }

    const manifest = Object.freeze({
      name,
      version,
      digest,
      sizeBytes: bytes.length,
      mediaType,
      publisher,
      sourceRevision,
      metadata: Object.freeze({ ...metadata }),
      canonicalMetadata,
      createdAt: new Date().toISOString(),
    });

    this.#versions.set(key, manifest);
    const auditEntry = Object.freeze({
      event: "artifact_published",
      artifact: key,
      digest,
      publisher,
      timestamp: manifest.createdAt,
    });

    this.#audit.push(auditEntry);
    this.#emit("published", {
      name,
      version,
      digest,
      publisher,
    });

    return manifest;
  }

  getManifest(name, version) {
    const manifest = this.#versions.get(`${name}@${version}`);
    if (!manifest) throw new NotFoundError(`Unknown artifact ${name}@${version}`);
    return manifest;
  }

  async download(name, version) {
    const manifest = this.getManifest(name, version);
    const stored = this.#blobs.get(manifest.digest);

    if (!stored) throw new IntegrityError("Artifact blob is missing.");

    const copy = Buffer.from(stored);
    if (copy.length !== manifest.sizeBytes || sha256(copy) !== manifest.digest) {
      throw new IntegrityError("Artifact payload failed digest or size verification.");
    }

    return copy;
  }

  listVersions(name) {
    return [...this.#versions.values()]
      .filter((item) => item.name === name)
      .sort((left, right) => compareVersions(left.version, right.version));
  }

  promote(channel, name, version, actor) {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,49}$/.test(channel)) {
      throw new ValidationError("Invalid release channel.");
    }

    if (typeof actor !== "string" || !actor.trim()) {
      throw new ValidationError("Promotion actor is required.");
    }

    const manifest = this.getManifest(name, version);

    // A mutable channel is a pointer, not an immutable artifact version.
    const previous = this.#releaseChannels.get(channel);
    const entry = Object.freeze({
      artifact: `${name}@${version}`,
      digest: manifest.digest,
      actor,
      changedAt: new Date().toISOString(),
    });

    this.#releaseChannels.set(channel, entry);
    this.#audit.push({
      event: "channel_promoted",
      channel,
      previous: previous ? previous.artifact : null,
      current: entry.artifact,
      actor,
      timestamp: entry.changedAt,
    });

    this.#emit("promoted", { channel, previous, current: entry });
    return entry;
  }

  resolveChannel(channel) {
    const entry = this.#releaseChannels.get(channel);
    if (!entry) throw new NotFoundError(`Unknown release channel: ${channel}`);
    return entry;
  }

  auditLog() {
    return this.#audit.map((entry) => ({ ...entry }));
  }

  verifyAll() {
    const results = [];

    for (const manifest of this.#versions.values()) {
      const bytes = this.#blobs.get(manifest.digest);
      const valid =
        Boolean(bytes) &&
        bytes.length === manifest.sizeBytes &&
        sha256(bytes) === manifest.digest;

      results.push({
        artifact: `${manifest.name}@${manifest.version}`,
        digest: manifest.digest,
        valid,
      });
    }

    return results;
  }
}

async function runDemonstration() {
  const repository = new ArtifactRepository();

  repository.on("published", (event) => {
    console.log(`Published ${event.name}@${event.version}: ${event.digest.slice(0, 12)}`);
  });

  repository.on("promoted", ({ channel, current }) => {
    console.log(`Channel ${channel} now points to ${current.artifact}`);
  });

  const releaseCandidate = Buffer.from(
    "inspection-engine build 4.8.0-rc.1\nschema=7\n"
  );
  const stableRelease = Buffer.from(
    "inspection-engine build 4.8.0\nschema=7\n"
  );

  await repository.publish({
    name: "inspection-engine",
    version: "4.8.0-rc.1",
    content: releaseCandidate,
    publisher: "ci-release",
    sourceRevision: "a91b02c",
    mediaType: "text/plain",
    metadata: { pipeline: "release-candidate", platform: "linux-amd64" },
  });

  await repository.publish({
    name: "inspection-engine",
    version: "4.8.0",
    content: stableRelease,
    publisher: "ci-release",
    sourceRevision: "bd34c19",
    mediaType: "text/plain",
    metadata: { pipeline: "production-release", platform: "linux-amd64" },
  });

  repository.promote("production", "inspection-engine", "4.8.0", "release-manager");

  const resolved = repository.resolveChannel("production");
  const downloaded = await repository.download("inspection-engine", "4.8.0");

  console.log("Resolved production digest:", resolved.digest);
  console.log("Downloaded content:", downloaded.toString("utf8").trim());
  console.log("Integrity results:", repository.verifyAll());

  try {
    await repository.publish({
      name: "inspection-engine",
      version: "4.8.0",
      content: Buffer.from("different content"),
      publisher: "ci-release",
      sourceRevision: "new-commit",
    });
  } catch (error) {
    console.log("Expected immutability rejection:", error.message);
  }

  console.log("Version order:", repository.listVersions("inspection-engine").map(
    (manifest) => manifest.version
  ));
  console.log("Audit event count:", repository.auditLog().length);
}

runDemonstration().catch((error) => {
  console.error("Repository execution failed:", error);
  process.exitCode = 1;
});

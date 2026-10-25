"use strict";

/**
 * Event-driven Docker Registry publishing and deployment policy model.
 * Run with Node.js 18 or later: node registry-workflow.js
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

class RegistryError extends Error {}
class ValidationError extends RegistryError {}
class AuthenticationError extends RegistryError {}
class AuthorizationError extends RegistryError {}
class PolicyError extends RegistryError {}
class ConflictError extends RegistryError {}

const Role = Object.freeze({
  READER: "reader",
  PUBLISHER: "publisher",
  ADMIN: "admin",
});

const CheckState = Object.freeze({
  PASS: "pass",
  FAIL: "fail",
  UNKNOWN: "unknown",
});

function validateRepository(repository) {
  if (
    typeof repository !== "string" ||
    repository.length === 0 ||
    repository.length > 255 ||
    repository !== repository.toLowerCase()
  ) {
    throw new ValidationError("Invalid lowercase repository name.");
  }

  const validComponent = /^[a-z0-9]+(?:[._-][a-z0-9]+)*$/;
  if (!repository.split("/").every((part) => validComponent.test(part))) {
    throw new ValidationError("Invalid repository path.");
  }
}

function validateTag(tag) {
  if (
    typeof tag !== "string" ||
    !/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/.test(tag)
  ) {
    throw new ValidationError("Invalid image tag.");
  }
}

function validateDigest(digest) {
  if (!/^sha256:[a-f0-9]{64}$/.test(digest)) {
    throw new ValidationError("Invalid SHA-256 digest.");
  }
}

function createArtifact(repository, tag, manifest, platform = "linux/amd64") {
  validateRepository(repository);
  validateTag(tag);

  if (typeof manifest !== "string" || manifest.length === 0) {
    throw new ValidationError("Manifest content must not be empty.");
  }

  if (!["linux/amd64", "linux/arm64", "linux/arm/v7"].includes(platform)) {
    throw new ValidationError("Unsupported demonstration platform.");
  }

  const bytes = Buffer.from(manifest, "utf8");
  const digest = `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;

  return Object.freeze({
    repository,
    tag,
    digest,
    sizeBytes: bytes.length,
    platform,
    reference: `${repository}:${tag}`,
    createdAt: new Date().toISOString(),
  });
}

class RegistryPolicy {
  constructor({
    allowedRegistries,
    maximumSizeBytes = 500_000_000,
    requireScanPass = true,
    requireSignature = true,
    immutableReleaseTags = true,
  }) {
    if (!Array.isArray(allowedRegistries) || allowedRegistries.length === 0) {
      throw new ValidationError("At least one registry must be allowed.");
    }
    if (!Number.isSafeInteger(maximumSizeBytes) || maximumSizeBytes <= 0) {
      throw new ValidationError("Invalid image size limit.");
    }

    this.allowedRegistries = new Set(allowedRegistries);
    this.maximumSizeBytes = maximumSizeBytes;
    this.requireScanPass = requireScanPass;
    this.requireSignature = requireSignature;
    this.immutableReleaseTags = immutableReleaseTags;
    Object.freeze(this);
  }
}

class Registry extends EventEmitter {
  #users = new Map();
  #images = new Map();
  #audit = [];

  constructor(name, { privateRegistry = true } = {}) {
    super();
    if (typeof name !== "string" || name.length === 0) {
      throw new ValidationError("Registry name is required.");
    }
    this.name = name;
    this.privateRegistry = privateRegistry;
  }

  addPrincipal(principal) {
    if (
      !principal ||
      typeof principal.username !== "string" ||
      !principal.username ||
      !Object.values(Role).includes(principal.role) ||
      typeof principal.token !== "string" ||
      principal.token.length < 8
    ) {
      throw new ValidationError("Invalid principal configuration.");
    }

    this.#users.set(principal.username, Object.freeze({ ...principal }));
  }

  authenticate(username, token) {
    const principal = this.#users.get(username);
    const expected = principal?.token ?? crypto.randomBytes(32).toString("hex");
    const supplied = typeof token === "string" ? token : "";
    const a = Buffer.from(expected);
    const b = Buffer.from(supplied);

    // Timing-safe comparison is used only for equal-length buffers.
    const valid =
      a.length === b.length &&
      crypto.timingSafeEqual(a, b) &&
      principal !== undefined;

    if (!valid) {
      this.#record("authentication_failed", username || "unknown", "");
      throw new AuthenticationError("Invalid registry credentials.");
    }

    this.#record("authenticated", username, "");
    return principal;
  }

  async publish(principal, artifact, policy, checks) {
    // A Promise boundary allows the caller to coordinate independent CI checks.
    await Promise.resolve();

    if (!principal || ![Role.PUBLISHER, Role.ADMIN].includes(principal.role)) {
      throw new AuthorizationError("Publisher permission required.");
    }
    if (!(policy instanceof RegistryPolicy)) {
      throw new ValidationError("A registry policy is required.");
    }
    if (!policy.allowedRegistries.has(this.name)) {
      throw new PolicyError("Target registry is not allowed.");
    }

    validateRepository(artifact.repository);
    validateTag(artifact.tag);
    validateDigest(artifact.digest);

    if (!Number.isSafeInteger(artifact.sizeBytes) || artifact.sizeBytes <= 0) {
      throw new ValidationError("Invalid image size.");
    }
    if (artifact.sizeBytes > policy.maximumSizeBytes) {
      throw new PolicyError("Image exceeds the size limit.");
    }

    if (
      policy.requireScanPass &&
      checks.vulnerabilityScan !== CheckState.PASS
    ) {
      throw new PolicyError("Vulnerability scan must pass.");
    }
    if (policy.requireSignature && checks.signatureVerified !== true) {
      throw new PolicyError("Image signature verification is required.");
    }

    const previous = this.#images.get(artifact.reference);
    if (previous) {
      if (previous.digest === artifact.digest) {
        this.#record("publish_idempotent", principal.username, artifact.reference);
        return previous;
      }

      const releaseTag = /^v\d+\.\d+\.\d+$/.test(artifact.tag);
      if (policy.immutableReleaseTags && releaseTag) {
        throw new ConflictError("Published release tags are immutable.");
      }
    }

    const published = Object.freeze({
      ...artifact,
      state: "published",
      publishedBy: principal.username,
      publishedAt: new Date().toISOString(),
    });

    this.#images.set(artifact.reference, published);
    this.#record("publish", principal.username, artifact.reference);
    this.emit("published", published);
    return published;
  }

  pull(principal, reference) {
    if (
      this.privateRegistry &&
      (!principal || !Object.values(Role).includes(principal.role))
    ) {
      throw new AuthenticationError("Private registry authentication required.");
    }

    const artifact = this.#images.get(reference);
    if (!artifact) {
      throw new RegistryError("Image reference not found.");
    }

    this.#record("pull", principal?.username ?? "anonymous", reference);
    this.emit("pulled", { reference, user: principal?.username ?? "anonymous" });
    return artifact;
  }

  report() {
    const images = [...this.#images.values()];
    return Object.freeze({
      registry: this.name,
      privateRegistry: this.privateRegistry,
      imageCount: images.length,
      totalBytes: images.reduce((total, item) => total + item.sizeBytes, 0),
      images,
      auditEvents: this.#audit.length,
    });
  }

  auditEvents() {
    return this.#audit.map((event) => ({ ...event }));
  }

  #record(action, actor, reference) {
    const event = Object.freeze({
      time: new Date().toISOString(),
      action,
      actor,
      reference,
    });
    this.#audit.push(event);
    this.emit("audit", event);
  }
}

async function main() {
  const registry = new Registry("registry.example.com", {
    privateRegistry: true,
  });

  registry.addPrincipal({
    username: "release-bot",
    role: Role.PUBLISHER,
    token: "demo-publisher-token",
  });
  registry.addPrincipal({
    username: "deployment-bot",
    role: Role.READER,
    token: "demo-reader-token",
  });

  registry.on("published", (image) => {
    console.log(`Published ${image.reference} (${image.digest})`);
  });

  registry.on("audit", (event) => {
    if (event.action === "authentication_failed") {
      console.error(`Security event: failed login for ${event.actor}`);
    }
  });

  const publisher = registry.authenticate(
    "release-bot",
    "demo-publisher-token",
  );
  const deployer = registry.authenticate(
    "deployment-bot",
    "demo-reader-token",
  );

  const policy = new RegistryPolicy({
    allowedRegistries: ["registry.example.com"],
    maximumSizeBytes: 1_000_000,
    requireScanPass: true,
    requireSignature: true,
  });

  const artifact = createArtifact(
    "commerce/orders-api",
    "v2.4.1",
    JSON.stringify({
      schemaVersion: 2,
      mediaType: "application/vnd.oci.image.manifest.v1+json",
    }),
  );

  await registry.publish(publisher, artifact, policy, {
    vulnerabilityScan: CheckState.PASS,
    signatureVerified: true,
  });

  const pulled = registry.pull(deployer, artifact.reference);
  console.log("Deployment reference:", pulled.reference);
  console.log("Registry report:", JSON.stringify(registry.report(), null, 2));

  try {
    const untrusted = createArtifact(
      "commerce/orders-api",
      "v2.4.2",
      '{"schemaVersion":2}',
    );
    await registry.publish(publisher, untrusted, policy, {
      vulnerabilityScan: CheckState.FAIL,
      signatureVerified: true,
    });
  } catch (error) {
    if (!(error instanceof RegistryError)) throw error;
    console.log("Expected publication rejection:", error.message);
  }

  try {
    registry.authenticate("release-bot", "wrong-token");
  } catch (error) {
    if (!(error instanceof AuthenticationError)) throw error;
    console.log("Expected authentication rejection:", error.message);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});

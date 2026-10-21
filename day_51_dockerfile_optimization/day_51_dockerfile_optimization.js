"use strict";

/*
 * Dockerfile optimization model using Node.js standard-library features.
 *
 * The program evaluates:
 * - layer sizes
 * - cache-key stability
 * - build-context reduction
 * - multi-stage runtime separation
 * - cache hit behavior
 * - optimization recommendations
 *
 * It is a model rather than a replacement for `docker build` measurement.
 */

const assert = require("node:assert/strict");

class Layer {
    constructor(name, sizeMb, cacheKey, options = {}) {
        if (!name || typeof name !== "string") {
            throw new TypeError("Layer name must be a non-empty string");
        }
        if (!Number.isFinite(sizeMb) || sizeMb < 0) {
            throw new RangeError("Layer size must be a non-negative number");
        }
        if (!cacheKey || typeof cacheKey !== "string") {
            throw new TypeError("Layer cache key is required");
        }

        this.name = name;
        this.sizeMb = sizeMb;
        this.cacheKey = cacheKey;
        this.expensive = Boolean(options.expensive);
    }
}

class DockerImage {
    constructor(name, contextMb, ignoredContextMb, layers) {
        if (!name || contextMb < 0 || ignoredContextMb < 0) {
            throw new Error("Invalid image configuration");
        }
        if (ignoredContextMb > contextMb) {
            throw new Error("Ignored context cannot exceed total context");
        }
        if (!Array.isArray(layers) || layers.length === 0) {
            throw new Error("At least one layer is required");
        }

        this.name = name;
        this.contextMb = contextMb;
        this.ignoredContextMb = ignoredContextMb;
        this.layers = layers;
    }

    get imageSizeMb() {
        return this.layers.reduce((total, layer) => total + layer.sizeMb, 0);
    }

    get effectiveContextMb() {
        return this.contextMb - this.ignoredContextMb;
    }
}

class CacheSimulator {
    constructor(existingKeys) {
        this.keys = new Set(existingKeys);
    }

    evaluate(image) {
        const hits = image.layers.filter(
            (layer) => this.keys.has(layer.cacheKey)
        ).length;

        return {
            hits,
            total: image.layers.length,
            hitRate: hits / image.layers.length
        };
    }
}

function printImage(image) {
    console.log(`\n${image.name}`);
    console.log("-".repeat(72));

    image.layers.forEach((layer, index) => {
        const expensive = layer.expensive ? " [expensive]" : "";
        console.log(
            `${String(index + 1).padStart(2)}. ` +
            `${layer.name.padEnd(32)} ` +
            `${layer.sizeMb.toFixed(1).padStart(7)} MB` +
            ` cache=${layer.cacheKey}${expensive}`
        );
    });

    console.log(`Image size: ${image.imageSizeMb.toFixed(1)} MB`);
    console.log(`Build context: ${image.effectiveContextMb.toFixed(1)} MB`);
}

function compare(before, after) {
    const sizeReduction =
        ((before.imageSizeMb - after.imageSizeMb) / before.imageSizeMb) * 100;

    const contextReduction =
        ((before.effectiveContextMb - after.effectiveContextMb) /
            before.effectiveContextMb) *
        100;

    console.log("\nOPTIMIZATION RESULTS");
    console.log("-".repeat(72));
    console.log(`Image reduction:   ${sizeReduction.toFixed(1)}%`);
    console.log(`Context reduction: ${contextReduction.toFixed(1)}%`);

    assert(after.imageSizeMb < before.imageSizeMb);
    assert(after.effectiveContextMb < before.effectiveContextMb);
}

function validateCacheOrdering(layers) {
    const expensiveIndex = layers.findIndex((layer) => layer.expensive);
    const sourceIndex = layers.findIndex(
        (layer) => layer.cacheKey === "COPY:source"
    );

    if (expensiveIndex !== -1 && sourceIndex !== -1) {
        return expensiveIndex < sourceIndex;
    }

    return true;
}

async function evaluateBuildPolicy(image) {
    // Promise-based evaluation models asynchronous build-policy checks.
    return new Promise((resolve) => {
        setImmediate(() => {
            const checks = {
                smallContext: image.effectiveContextMb <= 150,
                runtimeOnlyLayers: image.layers.every(
                    (layer) => !layer.name.toLowerCase().includes("compiler")
                ),
                stableDependencyOrdering: validateCacheOrdering(image.layers)
            };

            resolve(checks);
        });
    });
}

async function main() {
    const naive = new DockerImage(
        "naive-node-service",
        360,
        0,
        [
            new Layer("node runtime", 125, "node:22-slim"),
            new Layer("copy complete repository", 75, "COPY:all"),
            new Layer("npm install", 105, "npm:package-lock", {
                expensive: true
            }),
            new Layer("application source", 45, "COPY:source"),
            new Layer("development tooling", 35, "dev-tools")
        ]
    );

    const optimized = new DockerImage(
        "optimized-node-service",
        360,
        245,
        [
            new Layer("node runtime", 125, "node:22-slim"),
            new Layer("npm production dependencies", 48, "npm:package-lock", {
                expensive: true
            }),
            new Layer("application source", 22, "COPY:source")
        ]
    );

    printImage(naive);
    printImage(optimized);

    const cache = new CacheSimulator([
        "node:22-slim",
        "npm:package-lock"
    ]);

    const beforeCache = cache.evaluate(naive);
    const afterCache = cache.evaluate(optimized);

    console.log("\nCACHE BEHAVIOR");
    console.log("-".repeat(72));
    console.log(
        `Naive:     ${beforeCache.hits}/${beforeCache.total} cache hits`
    );
    console.log(
        `Optimized: ${afterCache.hits}/${afterCache.total} cache hits`
    );

    compare(naive, optimized);

    const policy = await evaluateBuildPolicy(optimized);

    console.log("\nPOLICY VALIDATION");
    console.log("-".repeat(72));

    for (const [name, passed] of Object.entries(policy)) {
        console.log(`[${passed ? "PASS" : "FAIL"}] ${name}`);
    }

    console.log("\nEVENT-DRIVEN BUILD OBSERVATION");
    console.log("-".repeat(72));
    console.log(
        "Dependency installation is modeled as an expensive asynchronous stage."
    );
    console.log(
        "Keeping dependency inputs stable allows its cache key to survive source-only changes."
    );

    if (!Object.values(policy).every(Boolean)) {
        process.exitCode = 1;
    }
}

main().catch((error) => {
    console.error(`Build-policy evaluation failed: ${error.message}`);
    process.exitCode = 1;
});

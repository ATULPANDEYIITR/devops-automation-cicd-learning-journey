'use strict';

/*
 * SonarQube-inspired quality analysis workflow.
 *
 * Runtime: Node.js 18 or later.
 *
 * This educational model calculates quality metrics from supplied findings.
 * It does not run SonarQube analyzers or claim to reproduce every server rule.
 */

const assert = require('node:assert/strict');

const IssueType = Object.freeze({
  BUG: 'BUG',
  VULNERABILITY: 'VULNERABILITY',
  CODE_SMELL: 'CODE_SMELL',
  SECURITY_HOTSPOT: 'SECURITY_HOTSPOT',
});

const Severity = Object.freeze({
  BLOCKER: 'BLOCKER',
  CRITICAL: 'CRITICAL',
  MAJOR: 'MAJOR',
  MINOR: 'MINOR',
  INFO: 'INFO',
});

const GateStatus = Object.freeze({
  OK: 'OK',
  ERROR: 'ERROR',
  NO_ANALYSIS: 'NO_ANALYSIS',
});

class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ValidationError';
  }
}

class QualityIssue {
  constructor({
    key,
    component,
    rule,
    type,
    severity,
    message,
    effortMinutes,
    line,
    isNew = true,
    resolved = false,
    hotspotReviewed = true,
  }) {
    if (![key, component, rule, message].every(
      value => typeof value === 'string' && value.trim().length > 0
    )) {
      throw new ValidationError('Issue identifiers and message must be non-empty strings.');
    }
    if (!Object.values(IssueType).includes(type)) {
      throw new ValidationError(`Unknown issue type: ${type}`);
    }
    if (!Object.values(Severity).includes(severity)) {
      throw new ValidationError(`Unknown severity: ${severity}`);
    }
    if (!Number.isSafeInteger(effortMinutes) || effortMinutes < 0) {
      throw new ValidationError('Remediation effort must be a non-negative integer.');
    }
    if (!Number.isSafeInteger(line) || line < 1) {
      throw new ValidationError('Source line must be a positive integer.');
    }

    Object.assign(this, {
      key,
      component,
      rule,
      type,
      severity,
      message,
      effortMinutes,
      line,
      isNew,
      resolved,
      hotspotReviewed,
    });
    Object.freeze(this);
  }
}

class SourceSnapshot {
  constructor({
    projectKey,
    branch,
    commit,
    lines,
    coveredLines,
    duplicatedLines,
    newLines,
    newCoveredLines,
    newDuplicatedLines,
    issues,
  }) {
    if (![projectKey, branch, commit].every(
      value => typeof value === 'string' && value.trim()
    )) {
      throw new ValidationError('Project, branch, and commit are required.');
    }

    const counts = {
      lines,
      coveredLines,
      duplicatedLines,
      newLines,
      newCoveredLines,
      newDuplicatedLines,
    };
    for (const [name, value] of Object.entries(counts)) {
      if (!Number.isSafeInteger(value) || value < 0) {
        throw new ValidationError(`${name} must be a non-negative integer.`);
      }
    }

    if (coveredLines > lines || duplicatedLines > lines) {
      throw new ValidationError('Overall coverage and duplication counts exceed source lines.');
    }
    if (newCoveredLines > newLines || newDuplicatedLines > newLines) {
      throw new ValidationError('New-code counts exceed the new-code denominator.');
    }
    if (!Array.isArray(issues) || !issues.every(
      issue => issue instanceof QualityIssue
    )) {
      throw new ValidationError('Issues must be an array of validated QualityIssue objects.');
    }

    Object.assign(this, counts, { projectKey, branch, commit });
    this.issues = Object.freeze([...issues]);
    Object.freeze(this);
  }

  static percent(numerator, denominator) {
    return denominator === 0
      ? 0
      : Math.round((10000 * numerator) / denominator) / 100;
  }

  metrics() {
    const active = this.issues.filter(issue => !issue.resolved);
    const fresh = active.filter(issue => issue.isNew);

    const count = (items, predicate) => items.filter(predicate).length;
    const debt = items => items.reduce(
      (total, issue) => total + issue.effortMinutes, 0
    );

    // These ratings are deliberately simplified teaching indicators.
    const rating = count => count === 0 ? 1
      : count <= 2 ? 2
      : count <= 5 ? 3
      : count <= 10 ? 4
      : 5;

    const activeHotspots = active.filter(
      issue => issue.type === IssueType.SECURITY_HOTSPOT
    );

    return Object.freeze({
      coveragePercent: SourceSnapshot.percent(this.coveredLines, this.lines),
      newCoveragePercent: SourceSnapshot.percent(this.newCoveredLines, this.newLines),
      duplicatedLinesPercent: SourceSnapshot.percent(this.duplicatedLines, this.lines),
      newDuplicatedLinesPercent: SourceSnapshot.percent(
        this.newDuplicatedLines, this.newLines
      ),
      newBugs: count(fresh, issue => issue.type === IssueType.BUG),
      newVulnerabilities: count(
        fresh, issue => issue.type === IssueType.VULNERABILITY
      ),
      newBlockers: count(fresh, issue => issue.severity === Severity.BLOCKER),
      newCriticalIssues: count(
        fresh, issue => issue.severity === Severity.CRITICAL
      ),
      newCodeSmells: count(fresh, issue => issue.type === IssueType.CODE_SMELL),
      newDebtMinutes: debt(fresh),
      totalDebtMinutes: debt(active),
      reliabilityRating: rating(
        count(active, issue => issue.type === IssueType.BUG)
      ),
      securityRating: rating(
        count(active, issue => issue.type === IssueType.VULNERABILITY)
      ),
      maintainabilityRating: rating(
        count(active, issue => issue.type === IssueType.CODE_SMELL)
      ),
      hotspotsReviewedPercent: SourceSnapshot.percent(
        count(activeHotspots, issue => issue.hotspotReviewed),
        activeHotspots.length
      ),
      activeIssueCount: active.length,
      newIssueCount: fresh.length,
    });
  }
}

class QualityCondition {
  constructor(metric, operator, threshold, scope = 'new_code') {
    const supported = new Set([
      'newCoveragePercent',
      'newDuplicatedLinesPercent',
      'newBugs',
      'newVulnerabilities',
      'newBlockers',
      'newCriticalIssues',
      'newCodeSmells',
      'newDebtMinutes',
      'totalDebtMinutes',
      'reliabilityRating',
      'securityRating',
      'maintainabilityRating',
      'hotspotsReviewedPercent',
    ]);
    if (!supported.has(metric)) {
      throw new ValidationError(`Unsupported metric: ${metric}`);
    }
    if (!['>', '>=', '<', '<=', '=', '!='].includes(operator)) {
      throw new ValidationError(`Unsupported operator: ${operator}`);
    }
    if (typeof threshold !== 'number' || !Number.isFinite(threshold)) {
      throw new ValidationError('Threshold must be a finite number.');
    }
    if (!['new_code', 'overall'].includes(scope)) {
      throw new ValidationError('Scope must be new_code or overall.');
    }

    Object.assign(this, { metric, operator, threshold, scope });
    Object.freeze(this);
  }

  evaluate(metrics) {
    const actual = metrics[this.metric];
    const passed = {
      '>': actual > this.threshold,
      '>=': actual >= this.threshold,
      '<': actual < this.threshold,
      '<=': actual <= this.threshold,
      '=': actual === this.threshold,
      '!=': actual !== this.threshold,
    }[this.operator];

    return Object.freeze({
      metric: this.metric,
      actual,
      operator: this.operator,
      threshold: this.threshold,
      scope: this.scope,
      passed,
    });
  }
}

class QualityGate {
  constructor(name, conditions) {
    if (!name || !Array.isArray(conditions) ||
        !conditions.every(condition => condition instanceof QualityCondition)) {
      throw new ValidationError('A named gate requires validated conditions.');
    }
    this.name = name;
    this.conditions = Object.freeze([...conditions]);
    Object.freeze(this);
  }

  evaluate(snapshot) {
    if (!(snapshot instanceof SourceSnapshot)) {
      return Object.freeze({
        status: GateStatus.NO_ANALYSIS,
        metrics: {},
        conditions: [],
        failed: [],
      });
    }

    const metrics = snapshot.metrics();
    const conditions = this.conditions.map(condition => condition.evaluate(metrics));
    const failed = conditions.filter(condition => !condition.passed);

    return Object.freeze({
      status: failed.length ? GateStatus.ERROR : GateStatus.OK,
      metrics,
      conditions,
      failed,
    });
  }
}

class AnalysisEventBus {
  #listeners = new Map();

  on(eventName, listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('Event listener must be a function.');
    }
    const listeners = this.#listeners.get(eventName) ?? new Set();
    listeners.add(listener);
    this.#listeners.set(eventName, listeners);

    // Return an unsubscribe function to prevent listener leaks.
    return () => listeners.delete(listener);
  }

  async emit(eventName, event) {
    const listeners = [...(this.#listeners.get(eventName) ?? [])];
    // Await listeners in order so that audit records are deterministic.
    for (const listener of listeners) {
      await listener(event);
    }
  }
}

class PullRequestQualityService {
  constructor(gate, eventBus = new AnalysisEventBus()) {
    this.gate = gate;
    this.events = eventBus;
    this.requests = new Map();
  }

  async analyzePullRequest({ id, sourceBranch, targetBranch, snapshot }) {
    if (!id || !sourceBranch || !targetBranch || sourceBranch === targetBranch) {
      throw new ValidationError('A pull request needs distinct source and target branches.');
    }
    if (!(snapshot instanceof SourceSnapshot)) {
      throw new ValidationError('A validated source snapshot is required.');
    }
    if (snapshot.branch !== sourceBranch) {
      throw new ValidationError('Analysis branch does not match the pull request source.');
    }

    const previous = this.requests.get(id);
    const result = this.gate.evaluate(snapshot);
    const request = Object.freeze({
      id,
      sourceBranch,
      targetBranch,
      commit: snapshot.commit,
      status: result.status,
      result,
      analyzedAt: new Date().toISOString(),
      generation: (previous?.generation ?? 0) + 1,
    });

    this.requests.set(id, request);
    await this.events.emit('analysis.completed', request);
    return request;
  }

  async merge(id, repositoryPolicy) {
    const request = this.requests.get(id);
    if (!request) {
      throw new Error('Merge denied: no analysis exists for this pull request.');
    }
    if (request.status !== GateStatus.OK) {
      throw new Error(`Merge denied: quality gate is ${request.status}.`);
    }

    // A passing quality gate does not replace review approvals or branch rules.
    const decision = repositoryPolicy(request);
    if (!decision.allowed) {
      throw new Error(`Merge denied by repository policy: ${decision.reason}`);
    }

    const event = Object.freeze({
      id,
      commit: request.commit,
      mergedAt: new Date().toISOString(),
    });
    await this.events.emit('pull-request.merged', event);
    return event;
  }
}

function createDemoSnapshot() {
  const issues = [
    new QualityIssue({
      key: 'PAY-001',
      component: 'src/payment-service.js',
      rule: 'javascript:S3776',
      type: IssueType.CODE_SMELL,
      severity: Severity.MAJOR,
      message: 'Split complex payment authorization logic into smaller operations.',
      effortMinutes: 40,
      line: 91,
    }),
    new QualityIssue({
      key: 'PAY-002',
      component: 'src/payment-service.js',
      rule: 'javascript:S3649',
      type: IssueType.VULNERABILITY,
      severity: Severity.CRITICAL,
      message: 'Use parameterized database queries for untrusted input.',
      effortMinutes: 90,
      line: 143,
    }),
    new QualityIssue({
      key: 'PAY-003',
      component: 'src/legacy-adapter.js',
      rule: 'javascript:S1481',
      type: IssueType.CODE_SMELL,
      severity: Severity.MINOR,
      message: 'Remove the unused local variable.',
      effortMinutes: 10,
      line: 28,
      isNew: false,
    }),
    new QualityIssue({
      key: 'PAY-004',
      component: 'src/crypto-adapter.js',
      rule: 'javascript:S4787',
      type: IssueType.SECURITY_HOTSPOT,
      severity: Severity.MAJOR,
      message: 'Review the cryptographic algorithm and key-management assumptions.',
      effortMinutes: 30,
      line: 66,
      hotspotReviewed: false,
    }),
  ];

  return new SourceSnapshot({
    projectKey: 'payments-api',
    branch: 'feature/safe-payment-query',
    commit: 'c7f91ad',
    lines: 1800,
    coveredLines: 1450,
    duplicatedLines: 45,
    newLines: 80,
    newCoveredLines: 68,
    newDuplicatedLines: 1,
    issues,
  });
}

function createProductionGate() {
  return new QualityGate('Production Quality Gate', [
    new QualityCondition('newCoveragePercent', '>=', 80),
    new QualityCondition('newDuplicatedLinesPercent', '<=', 3),
    new QualityCondition('newBugs', '=', 0),
    new QualityCondition('newVulnerabilities', '=', 0),
    new QualityCondition('newBlockers', '=', 0),
    new QualityCondition('hotspotsReviewedPercent', '>=', 100, 'overall'),
  ]);
}

async function main() {
  const bus = new AnalysisEventBus();
  const auditLog = [];

  bus.on('analysis.completed', event => {
    auditLog.push({
      event: 'analysis.completed',
      requestId: event.id,
      commit: event.commit,
      gateStatus: event.status,
      generation: event.generation,
    });
  });

  bus.on('pull-request.merged', event => {
    auditLog.push({ event: 'pull-request.merged', ...event });
  });

  const service = new PullRequestQualityService(createProductionGate(), bus);
  const snapshot = createDemoSnapshot();

  const request = await service.analyzePullRequest({
    id: 'PR-284',
    sourceBranch: snapshot.branch,
    targetBranch: 'main',
    snapshot,
  });

  console.log(`Pull request: ${request.id}`);
  console.log(`Commit analyzed: ${request.commit}`);
  console.log(`Quality gate: ${request.status}`);
  console.log('\nMetrics:', JSON.stringify(request.result.metrics, null, 2));
  console.log('\nFailed conditions:');
  console.log(JSON.stringify(request.result.failed, null, 2));

  try {
    await service.merge(request.id, () => ({
      allowed: true,
      reason: 'All repository policies passed.',
    }));
  } catch (error) {
    console.log(`\nExpected merge rejection: ${error.message}`);
  }

  // A second snapshot proves that a fixed commit can be evaluated independently.
  const fixedSnapshot = new SourceSnapshot({
    projectKey: 'payments-api',
    branch: 'feature/safe-payment-query',
    commit: 'e218c50',
    lines: 1810,
    coveredLines: 1510,
    duplicatedLines: 45,
    newLines: 100,
    newCoveredLines: 92,
    newDuplicatedLines: 2,
    issues: [
      new QualityIssue({
        key: 'PAY-001',
        component: 'src/payment-service.js',
        rule: 'javascript:S3776',
        type: IssueType.CODE_SMELL,
        severity: Severity.MAJOR,
        message: 'Complexity finding in changed code.',
        effortMinutes: 20,
        line: 91,
        isNew: false,
      }),
      new QualityIssue({
        key: 'PAY-003',
        component: 'src/legacy-adapter.js',
        rule: 'javascript:S1481',
        type: IssueType.CODE_SMELL,
        severity: Severity.MINOR,
        message: 'Existing legacy finding.',
        effortMinutes: 10,
        line: 28,
        isNew: false,
      }),
      new QualityIssue({
        key: 'PAY-004',
        component: 'src/crypto-adapter.js',
        rule: 'javascript:S4787',
        type: IssueType.SECURITY_HOTSPOT,
        severity: Severity.MAJOR,
        message: 'Cryptographic design reviewed by the security team.',
        effortMinutes: 30,
        line: 66,
        isNew: false,
        hotspotReviewed: true,
      }),
    ],
  });

  const fixedRequest = await service.analyzePullRequest({
    id: 'PR-284',
    sourceBranch: fixedSnapshot.branch,
    targetBranch: 'main',
    snapshot: fixedSnapshot,
  });

  console.log(`\nRe-analysis generation: ${fixedRequest.generation}`);
  console.log(`Updated quality gate: ${fixedRequest.status}`);

  const mergeEvent = await service.merge('PR-284', requestForMerge => ({
    allowed: requestForMerge.targetBranch === 'main',
    reason: 'Required review and CI policies have been independently satisfied.',
  }));

  console.log('Merge event:', JSON.stringify(mergeEvent, null, 2));
  console.log('Audit events:', JSON.stringify(auditLog, null, 2));

  assert.equal(createProductionGate().evaluate(null).status, GateStatus.NO_ANALYSIS);
  assert.equal(fixedRequest.status, GateStatus.OK);

  const zeroLineSnapshot = new SourceSnapshot({
    projectKey: 'empty-generated-module',
    branch: 'feature/empty',
    commit: '001',
    lines: 0,
    coveredLines: 0,
    duplicatedLines: 0,
    newLines: 0,
    newCoveredLines: 0,
    newDuplicatedLines: 0,
    issues: [],
  });
  assert.equal(zeroLineSnapshot.metrics().newCoveragePercent, 0);

  console.log('\nAssertions passed.');
}

main().catch(error => {
  console.error(`Fatal workflow error: ${error.message}`);
  process.exitCode = 1;
});

# CI/CD Fundamentals

## Continuous Integration, Continuous Delivery and Continuous Deployment

## Introduction

CI/CD is one of the most important concepts in modern software engineering and DevOps.

CI/CD represents a set of engineering practices, automation techniques and delivery principles that help software teams build, test, validate, release and deploy software in a reliable, repeatable and efficient manner.

The term CI/CD commonly refers to:

- Continuous Integration
- Continuous Delivery
- Continuous Deployment

Although these terms are closely related, they represent different stages of software delivery maturity.

A simplified software delivery lifecycle can be represented as:

```text
Developer
   |
   v
Git Commit
   |
   v
Continuous Integration
   |
   +----> Build
   |
   +----> Test
   |
   +----> Code Quality
   |
   +----> Security
   |
   v
Deployable Artifact
   |
   v
Staging
   |
   v
Validation
   |
   +----------------------------+
   |                            |
   v                            v
Continuous Delivery       Continuous Deployment
   |                            |
Manual Approval             Automatic Release
   |                            |
   +-------------+--------------+
                 |
                 v
             Production
                 |
                 v
             Monitoring
```

---

# 1. What is software delivery?

Software delivery is the process of taking source code written by developers and making a usable version of that software available to users.

A simplified traditional process may look like:

```text
Write Code
   |
   v
Test Manually
   |
   v
Build Manually
   |
   v
Copy Files
   |
   v
Configure Server
   |
   v
Deploy
   |
   v
Monitor
```

This process can become slow and error-prone as applications and organizations grow.

Common problems include:

- Manual errors
- Slow deployments
- Inconsistent environments
- Large batches of changes
- Difficult debugging
- Poor release visibility
- Configuration mistakes
- Long feedback cycles
- Fear of deployment
- "Works on my machine" problems

CI/CD attempts to automate and standardize this process.

---

# 2. What is Continuous Integration?

Continuous Integration, commonly called CI, is the practice of frequently integrating code changes into a shared repository while automatically validating those changes.

A typical CI workflow is:

```text
Developer
   |
   v
Code Change
   |
   v
Git Commit
   |
   v
Git Push
   |
   v
CI Trigger
   |
   v
Checkout Code
   |
   v
Install Dependencies
   |
   v
Lint
   |
   v
Unit Tests
   |
   v
Build
   |
   v
Security Checks
   |
   v
CI Result
```

The fundamental question CI answers is:

> "Is this code change safe to integrate with the rest of the application?"

---

# 3. Why Continuous Integration matters

Without CI, developers may work independently for long periods and attempt to combine their work later.

This creates an integration problem.

For example:

```text
Developer A
     |
     |
Developer B
     |
     |
Developer C
     |
     v
Large Integration Event
```

If all three developers make conflicting changes, identifying the source of the problem can be difficult.

With CI:

```text
Developer A ---> Integration ---> Automated Validation

Developer B ---> Integration ---> Automated Validation

Developer C ---> Integration ---> Automated Validation
```

Problems are discovered earlier.

The smaller the change, the easier it generally is to understand and debug a failure.

---

# 4. What does "continuous" mean?

Continuous does not mean that code must be integrated every second.

It means integration happens frequently instead of waiting for large integration events.

The principle is:

```text
Small Change
    +
Frequent Integration
    +
Fast Feedback
    =
Lower Integration Risk
```

---

# 5. What happens during CI?

A CI pipeline commonly performs the following operations:

1. Checkout source code
2. Install dependencies
3. Validate formatting
4. Run linting
5. Run unit tests
6. Run integration tests
7. Perform static analysis
8. Run security checks
9. Build the application
10. Generate an artifact
11. Store test results
12. Store build artifacts

A typical CI pipeline is:

```text
Source
  |
  v
Checkout
  |
  v
Dependencies
  |
  v
Lint
  |
  v
Tests
  |
  v
Security
  |
  v
Build
  |
  v
Artifact
```

---

# 6. Continuous Delivery

Continuous Delivery extends Continuous Integration.

The objective of Continuous Delivery is:

> Software should always be in a releasable state.

A Continuous Delivery pipeline may look like:

```text
Code
 |
 v
Build
 |
 v
Test
 |
 v
Security
 |
 v
Package
 |
 v
Staging
 |
 v
Acceptance Tests
 |
 v
Production-Ready Artifact
 |
 v
Manual Approval
 |
 v
Production
```

The important characteristic is that the software is automatically prepared for production.

Production deployment may still require explicit human approval.

---

# 7. Continuous Deployment

Continuous Deployment takes the idea one step further.

In Continuous Deployment, changes that successfully pass the required automated checks can automatically be deployed to production.

The flow becomes:

```text
Code
 |
 v
Build
 |
 v
Test
 |
 v
Security
 |
 v
Package
 |
 v
Staging
 |
 v
Validation
 |
 v
Automatic Production Deployment
 |
 v
Monitoring
```

There is no mandatory manual production approval.

This requires strong confidence in:

- Automated testing
- Security checks
- Deployment automation
- Monitoring
- Rollback mechanisms
- Infrastructure
- Configuration
- Observability

---

# 8. CI vs Continuous Delivery vs Continuous Deployment

| Concept | Primary Objective | Production Deployment |
|---|---|---|
| Continuous Integration | Frequently integrate and validate code | Not necessarily |
| Continuous Delivery | Keep software ready for release | Usually requires approval/action |
| Continuous Deployment | Automatically release validated changes | Automatic |

A useful mental model is:

```text
Continuous Integration
        |
        v
Build + Test + Validate
        |
        v
Continuous Delivery
        |
        v
Release-Ready Software
        |
        v
Continuous Deployment
        |
        v
Automatic Production Deployment
```

---

# 9. Git and CI/CD

Git is one of the foundations of modern CI/CD.

A common workflow is:

```text
git clone
    |
    v
Edit Code
    |
    v
git add
    |
    v
git commit
    |
    v
git push
    |
    v
CI Pipeline
```

The Git repository becomes an important source of truth for:

- Source code
- Version history
- Branches
- Pipeline configuration
- Infrastructure definitions
- Deployment configuration

---

# 10. CI/CD triggers

A pipeline needs a trigger that tells it when to execute.

Common triggers include:

- Push
- Pull request
- Merge
- Tag creation
- Release creation
- Scheduled execution
- Manual execution
- Webhook
- API call
- Dependency update

For example:

```text
Push to main
     |
     v
CI Pipeline Starts
```

Another example:

```text
Pull Request
     |
     v
Validation Pipeline
     |
     +--> Tests
     +--> Lint
     +--> Security
     +--> Build
```

---

# 11. Pull requests and CI

Pull requests provide an important control point.

A typical workflow is:

```text
Developer
    |
    v
Feature Branch
    |
    v
Pull Request
    |
    v
CI
    |
    +--> Unit Tests
    +--> Integration Tests
    +--> Lint
    +--> Security
    +--> Build
    |
    v
Code Review
    |
    v
Merge
```

This prevents unvalidated changes from being merged into important branches.

---

# 12. Protected branches

Production branches such as `main` can be protected.

Typical rules include:

- Pull request required
- CI must pass
- Required reviewers
- No direct pushes
- Security checks required
- Status checks required

Example:

```text
Developer
    |
    v
Pull Request
    |
    v
Automated Checks
    |
    v
Code Review
    |
    v
Merge to main
```

---

# 13. Pipeline

A pipeline is an automated sequence of operations used to validate, build, release or deploy software.

Example:

```text
Checkout
   |
   v
Install
   |
   v
Lint
   |
   v
Test
   |
   v
Build
   |
   v
Security Scan
   |
   v
Package
   |
   v
Deploy
   |
   v
Verify
```

---

# 14. Pipeline stages

A pipeline can be divided into stages.

Example:

```text
Stage 1: Checkout
Stage 2: Install
Stage 3: Quality
Stage 4: Test
Stage 5: Security
Stage 6: Build
Stage 7: Package
Stage 8: Staging
Stage 9: Validation
Stage 10: Production
Stage 11: Monitoring
```

Stages make complex pipelines easier to understand.

---

# 15. Jobs and steps

A stage can contain multiple jobs.

For example:

```text
Test Stage
   |
   +----> Unit Tests
   |
   +----> Integration Tests
   |
   +----> Security Tests
```

A job can contain multiple steps:

```text
Unit Test Job
   |
   +--> Checkout
   +--> Install Dependencies
   +--> Execute pytest
   +--> Generate Report
```

---

# 16. Parallel execution

Pipeline stages do not always need to execute sequentially.

For example:

```text
             +--> Unit Tests
             |
Build Setup -+--> Lint
             |
             +--> Security Scan
```

Parallel execution can significantly reduce pipeline duration.

---

# 17. Build

A build converts source code into a form that can be executed, packaged or deployed.

Examples include:

- Python wheel
- Java JAR
- Docker image
- JavaScript bundle
- ZIP package
- Native binary

A simplified model is:

```text
Source Code
    +
Dependencies
    +
Build Configuration
    |
    v
Build
    |
    v
Artifact
```

---

# 18. Artifacts

An artifact is the output produced by a build.

Examples:

```text
Python:
application-1.0.0.whl

Java:
application-1.0.0.jar

Container:
application:1.0.0

Frontend:
frontend-build.zip
```

Artifacts should generally be:

- Versioned
- Traceable
- Reproducible
- Immutable
- Stored securely

---

# 19. Build once, deploy many

One of the most important CI/CD principles is:

> Build once, deploy many times.

Instead of rebuilding the application separately for each environment:

```text
Source
  |
  v
Build
  |
  v
Artifact v1.5
  |
  +----> Development
  |
  +----> Staging
  |
  +----> Production
```

The same artifact should ideally be promoted through environments.

This improves consistency.

---

# 20. Artifact repositories

Artifacts need reliable storage.

Artifact repositories may store:

- Docker images
- Python packages
- Java packages
- Binary files
- Build outputs

The conceptual flow is:

```text
CI
 |
 v
Build
 |
 v
Artifact
 |
 v
Artifact Repository
 |
 +----> Staging
 |
 +----> Production
```

---

# 21. Automated testing

Automated testing is one of the foundations of CI/CD.

Common test types include:

### Unit tests

Test individual functions or components.

### Integration tests

Test interactions between components.

### System tests

Test the complete application.

### End-to-end tests

Test realistic user workflows.

### Acceptance tests

Validate business requirements.

### Performance tests

Measure performance characteristics.

### Security tests

Identify security weaknesses.

---

# 22. Testing pyramid

A common testing model is the testing pyramid.

```text
             /\
            /  \
           / E2E\
          /------\
         /Integr. \
        /----------\
       / Unit Tests \
      /--------------\
```

The general idea is:

```text
Many unit tests
       |
Fewer integration tests
       |
Even fewer end-to-end tests
```

Unit tests are usually:

- Fast
- Cheap
- Easy to debug

End-to-end tests can be:

- Slow
- Expensive
- Fragile
- Difficult to debug

---

# 23. Code quality

CI pipelines can automatically perform:

- Formatting
- Linting
- Type checking
- Static analysis
- Complexity checks
- Code coverage

Python projects may use tools such as:

```text
pytest
ruff
black
mypy
```

The exact tooling depends on the project.

---

# 24. Code coverage

Code coverage measures how much of the code is executed by tests.

For example:

```text
100 executable lines
80 lines executed by tests

Coverage = 80%
```

Coverage is useful but should not be treated as a guarantee of software quality.

A project can have high coverage while still having weak tests.

The quality of assertions and test cases matters more than simply maximizing a percentage.

---

# 25. Deployment environments

Common environments include:

```text
Development
     |
     v
Testing / QA
     |
     v
Staging
     |
     v
Production
```

### Development

Used for active development.

### Testing / QA

Used for validation.

### Staging

Used as a production-like environment.

### Production

Used by real users.

---

# 26. Environment parity

The closer staging resembles production, the more useful staging validation becomes.

Important similarities can include:

- Runtime version
- Container image
- Configuration structure
- Database behavior
- Network architecture
- External dependencies

The goal is to minimize unexpected differences.

---

# 27. Configuration management

Application code should be separated from environment-specific configuration.

Bad approach:

```python
DATABASE_PASSWORD = "my-secret-password"
```

Better:

```python
import os

DATABASE_PASSWORD = os.environ["DATABASE_PASSWORD"]
```

Configuration can come from:

- Environment variables
- Configuration systems
- Secret managers
- Deployment platforms

---

# 28. Secrets management

Secrets include:

- Passwords
- API keys
- Access tokens
- Database credentials
- Private keys

Secrets should not be committed to Git.

Bad:

```python
API_KEY = "secret-value"
```

Better:

```python
API_KEY = os.environ["API_KEY"]
```

Production environments should use secure secret-management systems.

---

# 29. CI/CD security

CI/CD systems can have significant privileges.

A compromised pipeline could potentially:

- Modify software
- Publish malicious artifacts
- Access cloud infrastructure
- Steal credentials
- Deploy unauthorized code

Important security practices include:

- Least privilege
- Short-lived credentials
- Secret rotation
- Dependency scanning
- Static analysis
- Protected branches
- Isolated runners
- Artifact signing
- Audit logging

---

# 30. DevSecOps

DevSecOps integrates security into the software lifecycle.

Instead of treating security as a final step:

```text
Development
     |
Testing
     |
Security
     |
Operations
```

DevSecOps embeds security throughout the process:

```text
Code
 |
 +--> SAST
 |
 +--> Dependency Scan
 |
 +--> Secret Scan
 |
 +--> Unit Tests
 |
 +--> Container Scan
 |
 +--> Infrastructure Scan
 |
 v
Deployment
```

---

# 31. Branching strategies

Common Git branching strategies include:

- Git Flow
- GitHub Flow
- GitLab Flow
- Trunk-based development

Git Flow traditionally uses:

```text
main
develop
feature/*
release/*
hotfix/*
```

Trunk-based development emphasizes:

- Small changes
- Short-lived branches
- Frequent integration
- Strong automated testing

---

# 32. Trunk-based development

A simplified trunk-based workflow is:

```text
Developer A ---\
Developer B ----> main
Developer C ---/
Developer D ---/
```

The objective is frequent integration rather than long-lived feature branches.

This approach aligns naturally with Continuous Integration.

---

# 33. Deployment strategies

Important deployment strategies include:

1. Recreate deployment
2. Rolling deployment
3. Blue-green deployment
4. Canary deployment
5. A/B deployment
6. Shadow deployment

The appropriate strategy depends on:

- Availability requirements
- Risk tolerance
- Infrastructure
- Application architecture
- User impact

---

# 34. Recreate deployment

The old version is stopped before the new version starts.

```text
v1
 |
 v
STOP
 |
 v
START v2
```

Advantages:

- Simple
- Easy to understand

Disadvantages:

- Can cause downtime

---

# 35. Rolling deployment

Instances are updated gradually.

Initial state:

```text
v1 v1 v1 v1
```

Then:

```text
v2 v1 v1 v1
```

Then:

```text
v2 v2 v1 v1
```

Then:

```text
v2 v2 v2 v1
```

Finally:

```text
v2 v2 v2 v2
```

Advantages:

- Reduced downtime
- Gradual rollout

Risk:

- Multiple application versions may coexist temporarily

---

# 36. Blue-green deployment

Blue-green deployment uses two environments.

```text
Users
  |
  v
Load Balancer
  |
  +----> Blue v1
  |
  +----> Green v2
```

Initially, Blue receives traffic.

Green is deployed and tested.

If Green is healthy:

```text
Users
  |
  v
Load Balancer
  |
  +----> Green v2
```

If a problem occurs, traffic can be switched back to Blue.

---

# 37. Canary deployment

Canary deployment exposes a new version to a small percentage of users.

Example:

```text
v1 -> 95%
v2 -> 5%
```

If the new version is healthy:

```text
v1 -> 75%
v2 -> 25%
```

Then:

```text
v1 -> 50%
v2 -> 50%
```

Eventually:

```text
v2 -> 100%
```

---

# 38. Blast radius

Blast radius means the scope of impact caused by a failure.

A deployment affecting 100% of users immediately has a large blast radius.

A deployment affecting 1% of users initially has a much smaller blast radius.

Canary deployments help reduce blast radius.

---

# 39. Feature flags

Feature flags separate deployment from feature activation.

Example:

```python
if feature_enabled:
    use_new_algorithm()
else:
    use_old_algorithm()
```

This allows code to be deployed without immediately exposing the feature.

Feature flags support:

- Gradual releases
- Experiments
- A/B testing
- Emergency disablement
- Customer segmentation

---

# 40. Release vs deployment

Deployment and release are not exactly the same thing.

### Deployment

Putting software into an environment.

### Release

Making a capability available to users.

Feature flags make this distinction especially clear.

You can deploy code while keeping its feature disabled.

```text
Build
 |
 v
Deploy
 |
 v
Feature Disabled
 |
 v
Validate
 |
 v
Enable Feature
```

---

# 41. Containers and CI/CD

Containers make application packaging more consistent.

A typical container CI/CD process is:

```text
Source Code
    |
    v
Docker Build
    |
    v
Container Image
    |
    v
Container Registry
    |
    v
Deployment Platform
```

---

# 42. Immutable artifacts

An immutable artifact should not be modified after creation.

Instead of changing a running application manually:

```text
Build v1
   |
   v
Modify manually
   |
   ?
```

prefer:

```text
Build v1
   |
   v
Build v2
   |
   v
Deploy v2
```

Examples:

```text
application:1.0.0
application:1.1.0
application:1.2.0
```

---

# 43. Kubernetes and CI/CD

Kubernetes is frequently used to manage containerized workloads.

A conceptual workflow is:

```text
Git
 |
 v
CI
 |
 v
Container Build
 |
 v
Container Registry
 |
 v
Kubernetes
 |
 v
Service
 |
 v
Users
```

Kubernetes can support:

- Rolling deployments
- Health checks
- Scaling
- Service discovery
- Self-healing
- Deployment management

---

# 44. Health checks

A deployment should verify more than whether a process has started.

Important concepts include:

### Liveness

Is the application alive?

### Readiness

Can the application receive traffic?

### Startup

Has the application finished starting?

These checks help deployment systems avoid sending traffic to unhealthy instances.

---

# 45. Infrastructure as Code

Infrastructure as Code, commonly called IaC, represents infrastructure configuration as code.

Examples of IaC tools include:

- Terraform
- CloudFormation
- Pulumi
- Ansible

Conceptually:

```text
Infrastructure Code
       |
       v
Validation
       |
       v
Plan
       |
       v
Review
       |
       v
Apply
       |
       v
Infrastructure
```

---

# 46. CI/CD for infrastructure

Infrastructure can have its own CI/CD pipeline.

For example:

```text
Terraform Change
      |
      v
Pull Request
      |
      v
terraform fmt
      |
      v
terraform validate
      |
      v
terraform plan
      |
      v
Review
      |
      v
terraform apply
```

---

# 47. Database migrations

Database changes are among the most challenging parts of CI/CD.

Suppose version 1 has:

```text
name
```

and version 2 requires:

```text
first_name
last_name
```

A careless migration can break old application instances.

A safer approach is:

```text
Expand
  |
  v
Deploy Compatible Code
  |
  v
Migrate Data
  |
  v
Switch Application
  |
  v
Contract
```

---

# 48. Expand and contract pattern

### Expand

Add new database structures without immediately removing old ones.

### Contract

Remove obsolete structures after all application versions no longer depend on them.

This approach supports safer zero-downtime migrations.

---

# 49. Rollback

Rollback means returning to a previous known-good version.

Example:

```text
v1
 |
 v
v2
 |
 X
 |
 v
Rollback
 |
 v
v1
```

A good deployment system should make rollback:

- Fast
- Predictable
- Automated where appropriate
- Observable

---

# 50. Rollforward

Sometimes rollback is not the best solution.

Instead:

```text
v1
 |
 v
v2
 |
 X
 |
 v
v3
```

The team fixes the problem and releases a new version.

Rollforward may be preferable when:

- Database changes cannot be safely reversed
- The fix is small
- A corrective release is already available

---

# 51. Observability

Deployment success does not necessarily mean application success.

Modern CI/CD must connect deployment with observability.

The three traditional pillars are:

```text
Logs
Metrics
Traces
```

### Logs

What happened?

### Metrics

How much or how often?

### Traces

Where did the request travel?

---

# 52. Deployment verification

After deployment, the system should verify:

- Application health
- HTTP responses
- Error rates
- Latency
- Resource usage
- Business metrics
- Database connectivity

A conceptual process is:

```text
Deploy
 |
 v
Health Check
 |
 v
Smoke Test
 |
 v
Monitor
 |
 +----> Healthy -> Continue
 |
 +----> Unhealthy -> Rollback
```

---

# 53. Smoke tests

Smoke tests are quick tests that verify critical functionality.

Examples:

```text
GET /health
GET /api/products
POST /api/login
```

The purpose is to quickly answer:

> "Is the deployment basically working?"

---

# 54. DORA metrics

DORA metrics are widely used to understand software delivery performance.

The four commonly discussed metrics are:

1. Deployment Frequency
2. Lead Time for Changes
3. Change Failure Rate
4. Time to Restore Service

---

# 55. Deployment Frequency

Deployment Frequency measures how often an organization successfully deploys software.

Example:

```text
15 production deployments per week
```

Higher frequency can indicate a strong ability to deliver small changes frequently, although frequency should not be pursued without regard to quality.

---

# 56. Lead Time for Changes

Lead Time for Changes measures how long it takes for a code change to move from development toward deployment.

Example:

```text
Code Commit
     |
     v
Build
     |
     v
Test
     |
     v
Review
     |
     v
Production

Total = 4 hours
```

Shorter lead times generally enable faster feedback.

---

# 57. Change Failure Rate

Change Failure Rate measures how often deployments cause failures requiring remediation.

For example:

```text
100 deployments
5 caused production failures

Change Failure Rate = 5%
```

---

# 58. Time to Restore Service

This measures how quickly the organization can recover after a failure.

A mature CI/CD system should make recovery easier through:

- Rollback
- Automation
- Monitoring
- Alerting
- Versioned artifacts
- Infrastructure automation

---

# 59. Pipeline optimization

A slow CI pipeline can reduce developer productivity.

Optimization techniques include:

- Dependency caching
- Parallel jobs
- Test splitting
- Incremental builds
- Smaller container images
- Reusable build environments
- Efficient test architecture

---

# 60. Caching

Without caching:

```text
Download Dependencies
       |
       v
Install
       |
       v
Run Tests
```

With caching:

```text
Cache Hit
   |
   v
Use Dependencies
   |
   v
Run Tests
```

Caching can significantly reduce pipeline execution time.

---

# 61. Fail fast

Basic validation should ideally happen early.

For example:

```text
Syntax
  |
  v
Formatting
  |
  v
Lint
  |
  v
Unit Tests
  |
  v
Integration Tests
  |
  v
Build
  |
  v
Deploy
```

There is little value in spending significant time building or deploying software that already fails a basic test.

---

# 62. Quality gates

A quality gate is a condition that must be satisfied before the pipeline can continue.

Examples:

- Tests must pass
- No critical vulnerabilities
- Required code review exists
- Build succeeds
- Coverage meets policy
- Security checks pass

Conceptually:

```text
          +-------------+
          | Quality Gate|
          +-------------+
                 |
          +------+------+
          |             |
        PASS           FAIL
          |             |
          v             v
      Continue          STOP
```

---

# 63. Manual approval

Continuous Delivery often uses a production approval step.

```text
Code
 |
 v
CI
 |
 v
Staging
 |
 v
Automated Validation
 |
 v
Manual Approval
 |
 v
Production
```

This can provide additional governance and organizational control.

---

# 64. Continuous Deployment does not mean no controls

Continuous Deployment does not mean blindly deploying everything.

Controls can be automated through:

- Test gates
- Security gates
- Policy checks
- Canary analysis
- Health checks
- Automated rollback
- Risk policies
- Deployment safeguards

The important distinction is that production promotion does not necessarily require a human approval step.

---

# 65. GitHub Actions concepts

GitHub Actions commonly organizes automation as:

```text
Workflow
   |
   +--> Job
          |
          +--> Step
          +--> Step
          +--> Step
```

A conceptual workflow is:

```yaml
name: CI

on:
  push:
    branches:
      - main

jobs:
  test:
    steps:
      - checkout
      - install dependencies
      - run lint
      - run tests

  build:
    needs: test
    steps:
      - build artifact
      - publish artifact
```

---

# 66. Jenkins concepts

Jenkins is an automation server widely used for CI/CD.

Important concepts include:

- Controller
- Agent
- Pipeline
- Stage
- Step
- Plugin
- Credential
- Workspace

Conceptually:

```text
Pipeline
 |
 +--> Checkout
 |
 +--> Test
 |
 +--> Build
 |
 +--> Deploy
```

---

# 67. GitLab CI/CD concepts

GitLab CI/CD commonly uses a `.gitlab-ci.yml` configuration file.

A conceptual pipeline is:

```yaml
stages:
  - test
  - build
  - deploy

test:
  stage: test

build:
  stage: build

deploy:
  stage: deploy
```

The exact syntax depends on the CI/CD platform and project requirements.

---

# 68. Pipeline as Code

Pipeline configuration should ideally be version-controlled.

Instead of configuring everything manually in a UI:

```text
Pipeline Configuration
       |
       v
Git Repository
       |
       v
Pull Request
       |
       v
Review
       |
       v
Pipeline
```

Advantages include:

- Version history
- Code review
- Reproducibility
- Auditability
- Collaboration

---

# 69. Reproducibility

A good CI/CD system should produce predictable results.

Potential causes of non-reproducibility include:

- Floating dependencies
- Mutable base images
- Environment differences
- Undocumented configuration
- External service changes

Dependency lock files and controlled build environments improve reproducibility.

---

# 70. Dependency management

Dependencies should be controlled carefully.

Instead of relying on arbitrary versions:

```text
requests
```

a project may pin or lock versions:

```text
requests==specific-version
```

or use a dependency lock file.

The goal is reproducibility and controlled upgrades.

---

# 71. Software supply chain security

Modern CI/CD must consider the software supply chain.

Potential threats include:

- Malicious dependencies
- Compromised packages
- Compromised runners
- Tampered artifacts
- Malicious build scripts

Controls can include:

- Dependency scanning
- Lock files
- Trusted registries
- Artifact signing
- Provenance
- SBOM
- Least privilege

---

# 72. SBOM

SBOM means:

> Software Bill of Materials

It describes the components contained within software.

For example:

```text
Application
 |
 +--> Python
 +--> Framework
 +--> HTTP Library
 +--> OpenSSL
 +--> OS Packages
```

SBOMs help organizations understand:

- What components are present
- Which versions are being used
- Where vulnerabilities may exist

---

# 73. Artifact signing

Artifact signing helps verify that an artifact came from a trusted build process and has not been unexpectedly modified.

Conceptually:

```text
Build
 |
 v
Artifact
 |
 v
Sign
 |
 v
Registry
 |
 v
Verify
 |
 v
Deploy
```

---

# 74. Ephemeral CI runners

An ephemeral runner is created for a pipeline job and destroyed after the job completes.

```text
Create Runner
     |
     v
Execute Job
     |
     v
Destroy Runner
```

Benefits include:

- Better isolation
- Cleaner execution environment
- Reduced persistence
- Lower cross-job contamination risk

---

# 75. Monorepo CI/CD

A monorepo stores multiple projects or services in one repository.

Example:

```text
repository/
    frontend/
    backend/
    service-a/
    service-b/
    shared-library/
```

A challenge is avoiding unnecessary builds.

For example:

```text
frontend/** changed
      |
      v
Frontend Pipeline
```

while:

```text
backend/** changed
      |
      v
Backend Pipeline
```

Path-based execution can improve efficiency.

---

# 76. Polyrepo CI/CD

Polyrepo means different applications or services use different repositories.

Example:

```text
frontend-repository
backend-repository
authentication-repository
payments-repository
```

Advantages:

- Independent ownership
- Independent pipelines
- Smaller repositories
- Independent release cycles

Challenges include:

- Cross-repository dependencies
- API compatibility
- Coordinated changes

---

# 77. Microservices CI/CD

Microservices often use independent pipelines.

Example:

```text
Service A
   |
   v
Service A CI/CD

Service B
   |
   v
Service B CI/CD

Service C
   |
   v
Service C CI/CD
```

This allows services to be deployed independently.

The tradeoff is increased operational complexity.

---

# 78. Service compatibility

Suppose:

```text
Service A ---> Service B
```

If Service B changes its API unexpectedly, Service A can break.

Solutions include:

- Backward-compatible APIs
- Contract testing
- API versioning
- Consumer-driven contracts
- Coordinated releases

---

# 79. Contract testing

Contract testing verifies that services agree on an interface.

Suppose a consumer expects:

```json
{
  "id": 10,
  "name": "Alice"
}
```

If the provider suddenly changes:

```text
name
```

to:

```text
full_name
```

the consumer may fail.

Contract testing can detect such compatibility issues before production.

---

# 80. Zero-downtime deployment

Zero-downtime deployment attempts to keep an application available while a new version is being deployed.

Common techniques include:

- Rolling deployment
- Blue-green deployment
- Canary deployment
- Health checks
- Backward-compatible database changes
- Load balancer management

---

# 81. Automatic rollback

A sophisticated deployment pipeline can automatically rollback when predefined health thresholds are violated.

Example:

```text
Deploy v2
   |
   v
Monitor
   |
   v
Error Rate Increases
   |
   v
Threshold Exceeded
   |
   v
Automatic Rollback
   |
   v
v1 Restored
```

This reduces the time users are exposed to failed deployments.

---

# 82. Progressive delivery

Progressive delivery combines several modern deployment techniques:

- Canary deployments
- Feature flags
- Gradual traffic shifting
- Automated analysis
- Automated rollback

Example:

```text
Deploy v2
    |
    v
1% Traffic
    |
    v
Analyze
    |
    +----> Failure -> Rollback
    |
    v
10%
    |
    v
50%
    |
    v
100%
```

---

# 83. GitOps

GitOps treats Git as the source of truth for desired application and infrastructure state.

Conceptually:

```text
Git Repository
      |
      v
Desired State
      |
      v
GitOps Controller
      |
      v
Infrastructure / Cluster
```

The controller attempts to make the actual environment match the state defined in Git.

---

# 84. CI vs CD responsibilities

CI generally focuses on:

- Integration
- Build
- Testing
- Validation
- Artifact creation

CD generally focuses on:

- Release
- Environment promotion
- Deployment
- Verification
- Rollback

A useful separation is:

```text
CI = "Can we safely integrate this change?"

CD = "Can we safely release and deploy this change?"
```

---

# 85. CI/CD vs DevOps

DevOps is broader than CI/CD.

DevOps includes:

- Development
- Operations
- Automation
- Infrastructure
- Monitoring
- Security
- Reliability
- Collaboration
- Continuous improvement

CI/CD is one major component of DevOps.

```text
DevOps
 |
 +--> CI/CD
 +--> Infrastructure
 +--> Security
 +--> Monitoring
 +--> Collaboration
 +--> Reliability
```

---

# 86. CI/CD vs Agile

Agile and CI/CD solve related but different problems.

Agile focuses on:

- Iterative development
- Small increments
- Feedback
- Collaboration
- Adaptability

CI/CD focuses on:

- Automated validation
- Automated builds
- Release readiness
- Deployment
- Delivery automation

They complement each other.

---

# 87. Common CI/CD anti-patterns

Common problems include:

### 1. Huge batches of changes

Large changes are difficult to validate.

### 2. Manual deployments

Manual operations introduce inconsistency.

### 3. No automated testing

Failures are discovered too late.

### 4. Secrets in Git

This creates significant security risk.

### 5. Rebuilding per environment

This can create different artifacts in different environments.

### 6. No rollback strategy

Failed releases become harder to recover from.

### 7. No health checks

Deployment success can be mistaken for application success.

### 8. Ignoring dependency security

Vulnerable dependencies can enter production.

### 9. Long-lived branches

Integration becomes harder.

### 10. Manual pipeline configuration

The delivery process becomes difficult to reproduce and audit.

---

# 88. "Works on my machine"

This is a classic software engineering problem.

An application may work on one developer's machine but fail elsewhere because of:

- Python version
- Dependency versions
- Operating system
- Environment variables
- Database configuration
- System packages
- Network configuration

CI helps expose these differences earlier.

Containers and reproducible environments can reduce them further.

---

# 89. Immutable infrastructure

Instead of manually modifying servers:

```text
Server v1
   |
   v
Manual Changes
   |
   ?
```

a more predictable approach is:

```text
Infrastructure Definition
       |
       v
Build New Version
       |
       v
Deploy New Version
```

This makes infrastructure more reproducible.

---

# 90. Pipeline idempotency

An idempotent operation can safely be repeated without causing unintended side effects.

For example, a deployment should ideally be safe to retry.

A non-idempotent process might accidentally:

- Create duplicate resources
- Corrupt state
- Create conflicting configuration
- Trigger unintended operations

Idempotency is an important property of reliable automation.

---

# 91. Pipeline observability

The CI/CD pipeline itself should be measurable.

Useful pipeline metrics include:

- Pipeline duration
- Queue time
- Failure rate
- Flaky test rate
- Deployment frequency
- Rollback frequency
- Most common failure causes

The pipeline is itself a critical engineering system.

---

# 92. Flaky tests

A flaky test sometimes passes and sometimes fails without a meaningful code change.

Flaky tests are dangerous because developers may eventually stop trusting CI.

Teams should monitor:

- Failure frequency
- Test duration
- Flaky test rate
- Failure causes

Flaky tests should generally be investigated and fixed rather than permanently ignored.

---

# 93. Pipeline governance

Large organizations may require:

- Approval policies
- Audit trails
- Change controls
- Segregation of duties
- Protected environments
- Security checks
- Compliance evidence

CI/CD must balance automation with organizational requirements.

---

# 94. Policy as Code

Policies can be expressed as executable rules.

For example:

```python
if environment == "production":
    require_approval()
```

Another example:

```python
if vulnerability_severity == "critical":
    block_deployment()
```

Policy as Code makes rules:

- Consistent
- Repeatable
- Reviewable
- Automatable

---

# 95. Environment promotion

A common promotion model is:

```text
Artifact v5
    |
    v
Development
    |
    v
Testing
    |
    v
Staging
    |
    v
Production
```

The same artifact should ideally move through these environments.

---

# 96. Continuous release

Modern delivery systems increasingly separate:

```text
Build
Release
Deploy
Activate
```

For example:

```text
Build v10
   |
   v
Deploy v10
   |
   v
Feature Disabled
   |
   v
Internal Validation
   |
   v
Enable for 5%
   |
   v
Enable for 100%
```

This gives teams more control over risk.

---

# 97. Disaster recovery and CI/CD

CI/CD should support the ability to recreate software environments.

A mature system can define:

- Application
- Infrastructure
- Configuration
- Pipeline
- Deployment

as version-controlled resources.

This makes recovery more repeatable.

---

# 98. CI/CD maturity

A conceptual maturity progression is:

```text
Level 0
Manual Deployment

      |

Level 1
Automated Build

      |

Level 2
Automated Tests

      |

Level 3
Continuous Integration

      |

Level 4
Continuous Delivery

      |

Level 5
Continuous Deployment

      |

Level 6
Progressive Delivery
+
Automated Rollback
+
Observability
+
Security
```

These levels are conceptual rather than a universal industry standard.

---

# 99. Complete CI/CD architecture

A mature CI/CD architecture can look like:

```text
                    Developer
                        |
                        v
                  Git Repository
                        |
                        v
                   Pull Request
                        |
                        v
                        CI
                        |
        +---------------+----------------+
        |               |                |
        v               v                v
     Linting         Testing          Security
        |               |                |
        +---------------+----------------+
                        |
                        v
                      Build
                        |
                        v
                     Artifact
                        |
                        v
                Artifact Registry
                        |
                        v
                    Staging
                        |
        +---------------+----------------+
        |                                |
        v                                v
   Smoke Tests                    Integration Tests
        |                                |
        +---------------+----------------+
                        |
                        v
                 Production Gate
                        |
                        v
                     Canary
                        |
                        v
               Automated Analysis
                        |
             +----------+----------+
             |                     |
           Failure               Success
             |                     |
             v                     v
          Rollback            Full Release
                                   |
                                   v
                              Production
                                   |
                                   v
                              Monitoring
```

---

# 100. Key principles of good CI/CD

A reliable CI/CD system should aim for:

### Small changes

Small changes are easier to review, test and rollback.

### Fast feedback

Developers should know about failures quickly.

### Automated validation

Machines should perform repetitive checks.

### Reproducible builds

The same source should produce predictable artifacts.

### Immutable artifacts

Artifacts should not be changed after creation.

### Secure pipelines

CI/CD infrastructure should follow least-privilege principles.

### Safe deployment

Deployment should minimize blast radius.

### Observability

Production behavior should be measurable.

### Fast recovery

Rollback and recovery should be well understood.

### Version-controlled automation

Pipeline and infrastructure configuration should be treated as code.

---

# 101. A practical CI/CD pipeline for a Python application

A Python application might use:

```text
Developer
   |
   v
Git
   |
   v
Pull Request
   |
   v
CI
   |
   +--> Install Python
   |
   +--> Install Dependencies
   |
   +--> Ruff
   |
   +--> Pytest
   |
   +--> Mypy
   |
   +--> Security Scan
   |
   v
Build Wheel / Container
   |
   v
Publish Artifact
   |
   v
Deploy Staging
   |
   v
Smoke Tests
   |
   v
Production
   |
   v
Monitoring
```

---

# 102. Example Python CI commands

A conceptual Python CI process may execute:

```bash
python -m pip install -r requirements.txt
ruff check .
pytest
mypy .
python -m build
```

The exact commands depend on the project.

---

# 103. Example deployment lifecycle

A mature release might look like:

```text
Commit
  |
  v
Pull Request
  |
  v
Review
  |
  v
CI
  |
  +--> Tests
  +--> Security
  +--> Quality
  |
  v
Build
  |
  v
Artifact
  |
  v
Staging
  |
  v
Validation
  |
  v
Canary
  |
  v
Monitoring
  |
  +----> Failure -> Rollback
  |
  v
100% Production
```

---

# 104. What I learned

Through CI/CD fundamentals, I learned that software delivery is not simply about writing code and deploying it.

A modern delivery process creates an automated chain from source code to production.

I learned that:

- Continuous Integration focuses on frequent integration and automated validation.
- Continuous Delivery keeps software in a release-ready state.
- Continuous Deployment automatically deploys validated changes to production.
- CI and CD are related but represent different responsibilities.
- Git provides the foundation for version-controlled software delivery.
- Pull requests provide an important review and validation point.
- Pipelines automate repetitive delivery tasks.
- Automated tests are fundamental to reliable CI/CD.
- Artifacts should be versioned and traceable.
- Build once, deploy many improves consistency.
- Deployment environments include development, testing, staging and production.
- Secrets should never be hard-coded in source code.
- DevSecOps integrates security throughout the software lifecycle.
- Quality gates prevent unsafe changes from progressing.
- Feature flags separate deployment from feature release.
- Rolling deployments update instances gradually.
- Blue-green deployments maintain two environments and switch traffic between them.
- Canary deployments reduce deployment blast radius.
- Containers provide consistent application packaging.
- Kubernetes can manage containerized application deployments.
- Infrastructure as Code allows infrastructure to be version-controlled and automated.
- Database migrations require special consideration during continuous deployment.
- Expand-and-contract migrations help support zero-downtime deployments.
- Rollbacks provide a recovery mechanism after failed releases.
- Rollforward can sometimes be preferable to rollback.
- Observability connects deployment activity with actual production behavior.
- Logs, metrics and traces provide different perspectives on system behavior.
- Smoke tests provide quick post-deployment validation.
- DORA metrics help measure software delivery performance.
- Pipeline caching and parallelization can reduce CI execution time.
- Flaky tests reduce confidence in CI and should be addressed.
- Artifact signing and SBOMs strengthen software supply-chain security.
- GitOps treats Git as the desired-state source of truth.
- Progressive delivery combines gradual rollout, monitoring and automated decision-making.
- Pipeline as Code makes delivery automation version-controlled and reviewable.
- Idempotent automation makes pipelines safer to retry.
- CI/CD is a major component of DevOps, but DevOps is broader than CI/CD.

---

# 105. CI/CD mental model

The simplest mental model I learned is:

```text
CI
==
Integrate and validate code continuously.


Continuous Delivery
===================
Keep software continuously ready for release.


Continuous Deployment
=====================
Automatically deploy validated software to production.
```

A mature system then adds:

```text
Automated Testing
       +
Security
       +
Immutable Artifacts
       +
Infrastructure as Code
       +
Feature Flags
       +
Progressive Delivery
       +
Observability
       +
Automated Rollback
       +
Supply Chain Security
       +
Policy as Code
       =
Reliable Software Delivery
```

---

# 106. Final takeaway

CI/CD is not simply a collection of tools such as GitHub Actions, Jenkins or GitLab CI/CD.

The tools are implementations of broader engineering principles.

The real objective is to create a software delivery system that is:

- Fast
- Reliable
- Repeatable
- Secure
- Reproducible
- Observable
- Auditable
- Recoverable

The core progression is:

```text
Continuous Integration
        |
        v
Frequent Integration
+
Automated Validation
        |
        v
Continuous Delivery
        |
        v
Release-Ready Software
        |
        v
Continuous Deployment
        |
        v
Automatic Production Delivery
```

The deepest lesson is that modern CI/CD attempts to transform software delivery from a risky, manual event into a predictable engineering system.

The ultimate goal is not simply:

> "Deploy more often."

The goal is:

> "Make every software change easier to validate, safer to release, easier to observe and faster to recover when something goes wrong."

That is the foundation of modern CI/CD engineering.
````

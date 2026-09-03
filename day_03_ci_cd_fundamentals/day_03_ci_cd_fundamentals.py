"""
===============================================================================
CI/CD FUNDAMENTALS
Continuous Integration (CI)
Continuous Delivery (CD)
Continuous Deployment (CD)

A COMPLETE BEGINNER-TO-ADVANCED EXPLANATORY PYTHON SCRIPT
===============================================================================

Purpose
-------
This script is an educational reference for understanding CI/CD from the
absolute basics to advanced software delivery concepts.

It explains:

1. What software delivery means
2. Why CI/CD exists
3. Continuous Integration
4. Continuous Delivery
5. Continuous Deployment
6. CI vs Continuous Delivery vs Continuous Deployment
7. Source control and Git
8. Build pipelines
9. Automated testing
10. Code quality
11. Artifacts
12. Deployment environments
13. Pipeline stages
14. Triggers
15. Branching strategies
16. Pull requests
17. Build failures
18. Deployment strategies
19. Blue-green deployment
20. Rolling deployment
21. Canary deployment
22. Recreate deployment
23. Feature flags
24. Infrastructure as Code
25. Containers
26. Kubernetes and CI/CD
27. Secrets management
28. Security in CI/CD
29. DevSecOps
30. Database migrations
31. Rollbacks
32. Observability
33. DORA metrics
34. Pipeline optimization
35. Monorepos and polyrepos
36. Microservices CI/CD
37. Trunk-based development
38. GitHub Actions-style concepts
39. Jenkins-style concepts
40. GitLab CI/CD-style concepts
41. Advanced pipeline architecture
42. CI/CD failure scenarios
43. Best practices
44. A simulated CI/CD pipeline in Python
45. Final interview-level concepts

NOTE
----
This script demonstrates CI/CD concepts locally. It does NOT actually deploy
software to cloud infrastructure.

===============================================================================
"""


# =============================================================================
# 1. WHAT IS CI/CD?
# =============================================================================

"""
CI/CD is a collection of software engineering practices and automation
techniques used to build, test, validate, release, and deploy software
reliably and frequently.

CI/CD commonly stands for:

CI  = Continuous Integration
CD  = Continuous Delivery
CD  = Continuous Deployment

The two meanings of CD are different.

Continuous Delivery:
    Software is automatically built, tested, and prepared for release.
    Production deployment usually requires an explicit approval or action.

Continuous Deployment:
    Every change that successfully passes the automated pipeline can be
    automatically deployed to production.

A simplified flow:

Developer
    |
    v
Git Commit
    |
    v
Continuous Integration
    |
    +--> Build
    |
    +--> Test
    |
    +--> Quality Checks
    |
    v
Release Candidate
    |
    +--> Continuous Delivery
    |       |
    |       +--> Production approval
    |       |
    |       +--> Deploy
    |
    OR
    |
    +--> Continuous Deployment
            |
            +--> Automatic Production Deployment


===============================================================================
2. WHY CI/CD EXISTS
===============================================================================

Without CI/CD, a traditional development process may look like:

Developer writes code
        |
        v
Developer sends code to team
        |
        v
Someone manually builds application
        |
        v
Someone manually tests application
        |
        v
Someone manually copies files
        |
        v
Someone manually configures server
        |
        v
Production deployment
        |
        v
Something breaks

This creates several problems:

- Human error
- Slow releases
- Difficult testing
- Large batches of changes
- Difficult debugging
- Deployment inconsistency
- "Works on my machine" problems
- Fear of releasing
- Manual configuration mistakes

CI/CD attempts to turn software delivery into a repeatable,
automated engineering process.


===============================================================================
3. THE BASIC SOFTWARE DELIVERY PIPELINE
===============================================================================

A basic pipeline can be represented as:

SOURCE
  |
  v
BUILD
  |
  v
TEST
  |
  v
PACKAGE
  |
  v
RELEASE
  |
  v
DEPLOY
  |
  v
VERIFY
  |
  v
MONITOR

Each stage should answer a question.

SOURCE:
    What changed?

BUILD:
    Can the application be compiled/packaged?

TEST:
    Does the software behave correctly?

PACKAGE:
    Can we create a deployable artifact?

RELEASE:
    Is this artifact approved for release?

DEPLOY:
    Can we safely put it into an environment?

VERIFY:
    Did deployment work?

MONITOR:
    Is the application healthy?


===============================================================================
4. CONTINUOUS INTEGRATION
===============================================================================

Continuous Integration means developers frequently integrate their changes
into a shared codebase and automated checks validate those changes.

Typical CI process:

1. Developer changes code.
2. Developer commits code.
3. Developer pushes code.
4. CI system detects the change.
5. Dependencies are installed.
6. Application is built.
7. Automated tests execute.
8. Static analysis executes.
9. Security checks may execute.
10. Results are reported.

Example:

git push
   |
   v
CI Trigger
   |
   v
Checkout Repository
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
Security Scan
   |
   v
CI Result


===============================================================================
5. WHY "CONTINUOUS" IN CONTINUOUS INTEGRATION?
===============================================================================

"Continuous" does not mean that code is integrated every second.

It means integration happens frequently rather than waiting weeks or months.

Traditional model:

Developer A
    |
Developer B
    |
Developer C
    |
Developer D
    |
    v
Large integration event

CI model:

A -> integrate
B -> integrate
C -> integrate
D -> integrate

Frequent integration reduces integration risk.

The smaller the change, the easier it usually is to understand and debug
a failure.


===============================================================================
6. CONTINUOUS DELIVERY
===============================================================================

Continuous Delivery extends CI.

The objective is:

"The software should always be in a releasable state."

Typical flow:

Code
 |
 v
Build
 |
 v
Tests
 |
 v
Security
 |
 v
Package
 |
 v
Deploy to staging
 |
 v
Acceptance tests
 |
 v
Production-ready artifact
 |
 v
MANUAL APPROVAL
 |
 v
Production

The key characteristic:

Production deployment is possible at any time, but may require a human
decision.


===============================================================================
7. CONTINUOUS DEPLOYMENT
===============================================================================

Continuous Deployment goes one step further.

If the change passes the required automated checks:

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
Deploy staging
 |
 v
Validate
 |
 v
Production
 |
 v
Monitor

There is no mandatory manual production approval.

This requires a high degree of confidence in:

- Automated testing
- Deployment automation
- Monitoring
- Rollback mechanisms
- Security
- Infrastructure automation
- Release processes


===============================================================================
8. CI VS CONTINUOUS DELIVERY VS CONTINUOUS DEPLOYMENT
===============================================================================

CI:

Primary question:
    "Is this change safe to integrate?"

Continuous Delivery:

Primary question:
    "Is this software ready to release?"

Continuous Deployment:

Primary question:
    "Can this validated change automatically go to production?"

Conceptually:

CI
    -> Build + Test + Validate

Continuous Delivery
    -> CI + Release Readiness + Deployable Software

Continuous Deployment
    -> Continuous Delivery + Automatic Production Deployment


===============================================================================
9. IMPORTANT TERMINOLOGY
===============================================================================

Repository
----------
A repository stores source code and version history.

Commit
------
A recorded change in source code.

Branch
------
An independent line of development.

Pull Request / Merge Request
-----------------------------
A mechanism for reviewing and merging changes.

Build
-----
The process of converting source code into something executable,
installable, or deployable.

Artifact
--------
A versioned output produced by a build.

Examples:

- Python wheel
- Docker image
- Java JAR
- JavaScript bundle
- ZIP package

Pipeline
--------
An automated sequence of software delivery operations.

Runner / Agent
--------------
A machine or execution environment that runs pipeline jobs.

Environment
-----------
A deployment target such as:

- Development
- Testing
- QA
- Staging
- Production


===============================================================================
10. GIT AND CI/CD
===============================================================================

Git is extremely important in CI/CD because the repository is often the
primary source of truth.

Typical workflow:

git clone
    |
    v
Edit code
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
CI pipeline


===============================================================================
11. CI/CD TRIGGERS
===============================================================================

A pipeline needs a reason to start.

Common triggers:

1. Push
2. Pull request
3. Merge
4. Tag creation
5. Scheduled execution
6. Manual execution
7. Release creation
8. API/webhook
9. Dependency update
10. Infrastructure change

Example conceptual configuration:

on:
    push:
        branches:
            - main

This means:

"When code is pushed to main, start the pipeline."


===============================================================================
12. PIPELINE STAGES
===============================================================================

A pipeline is commonly divided into stages.

Example:

stage 1 -> checkout
stage 2 -> install
stage 3 -> lint
stage 4 -> unit tests
stage 5 -> build
stage 6 -> security scan
stage 7 -> package
stage 8 -> deploy staging
stage 9 -> integration tests
stage 10 -> production deployment
stage 11 -> monitoring

Some stages can execute in parallel.

Example:

                    +--> Unit Tests
                    |
Build Environment --+--> Lint
                    |
                    +--> Security Scan

This reduces pipeline duration.


===============================================================================
13. JOBS AND STEPS
===============================================================================

A stage may contain multiple jobs.

Example:

Stage: Test

    Job 1:
        Unit tests

    Job 2:
        Integration tests

    Job 3:
        Security tests

A job may contain multiple steps.

Example:

Job:
    Step 1 -> Checkout
    Step 2 -> Install dependencies
    Step 3 -> Run tests


===============================================================================
14. BUILD AUTOMATION
===============================================================================

A build should be reproducible.

For example:

Source code
    +
Dependency definitions
    +
Build configuration
    =
Predictable artifact

Python example:

requirements.txt

Then:

pip install -r requirements.txt

The same dependency definition can be used by:

- Developer machine
- CI runner
- Staging environment
- Production build system


===============================================================================
15. AUTOMATED TESTING
===============================================================================

Testing is one of the foundations of CI/CD.

Major categories include:

Unit tests
-----------
Test small pieces of functionality.

Integration tests
-----------------
Test interaction between components.

System tests
------------
Test the complete system.

End-to-end tests
----------------
Test realistic user workflows.

Acceptance tests
----------------
Verify business requirements.

Performance tests
-----------------
Measure speed, throughput, latency, etc.

Security tests
--------------
Identify security weaknesses.


===============================================================================
16. TESTING PYRAMID
===============================================================================

A useful conceptual model is the testing pyramid.

             /\
            /  \
           / E2E\
          /------\
         /Integr. \
        /----------\
       / Unit Tests \
      /--------------\

Usually:

Many unit tests
Fewer integration tests
Even fewer expensive end-to-end tests

Why?

Unit tests are generally:

- Fast
- Cheap
- Easy to debug

End-to-end tests can be:

- Slow
- Expensive
- Fragile
- Harder to debug


===============================================================================
17. CODE QUALITY
===============================================================================

CI pipelines frequently perform static checks.

Examples:

- Formatting
- Linting
- Type checking
- Static analysis
- Complexity checks
- Code coverage

Example tools in Python ecosystems:

pytest
ruff
black
mypy

The exact tools depend on the project.


===============================================================================
18. CODE COVERAGE
===============================================================================

Code coverage measures how much code is exercised by tests.

Example:

100 executable lines
80 lines executed by tests

Coverage = 80%

Important:

High coverage does NOT automatically mean high-quality tests.

This:

def add(a, b):
    return a + b

can have 100% line coverage while still lacking meaningful edge-case tests.


===============================================================================
19. ARTIFACTS
===============================================================================

An artifact is a build output that can be stored and deployed.

Examples:

Python:

    application.whl

Java:

    application.jar

Container:

    application:1.2.0

Frontend:

    frontend-build.zip

An important principle:

BUILD ONCE, DEPLOY MANY TIMES.

Example:

Build artifact:
    version 1.5.2

Deploy the SAME artifact to:

Development
    |
    v
Staging
    |
    v
Production

Do not rebuild different versions for each environment unless there is a
specific reason.


===============================================================================
20. ARTIFACT REPOSITORIES
===============================================================================

Artifacts need storage.

Examples of artifact repositories include:

- Container registries
- Package registries
- Binary repositories
- Cloud artifact repositories

Conceptually:

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
 +--> Staging
 |
 +--> Production


===============================================================================
21. ENVIRONMENTS
===============================================================================

Typical environments:

Development
------------
Used by developers.

Testing / QA
------------
Used for validation.

Staging
-------
Designed to resemble production.

Production
----------
Real users and real workloads.

A common promotion path:

Development
    ->
Testing
    ->
Staging
    ->
Production


===============================================================================
22. CONFIGURATION VS CODE
===============================================================================

A good deployment system separates code from environment configuration.

The application should not hard-code:

DATABASE_PASSWORD = "secret"

Instead configuration can come from:

- Environment variables
- Secret managers
- Configuration services
- Deployment systems

Example:

import os

DATABASE_URL = os.environ["DATABASE_URL"]


===============================================================================
23. SECRETS MANAGEMENT
===============================================================================

Secrets include:

- Passwords
- API keys
- Access tokens
- Private keys
- Database credentials

Never hard-code secrets in source code.

Bad:

API_KEY = "123456-secret-value"

Better:

API_KEY = os.environ["API_KEY"]

Best practice:

Store sensitive credentials in a dedicated secret-management system and
inject them into the pipeline/runtime securely.


===============================================================================
24. CI/CD SECURITY
===============================================================================

CI/CD pipelines are highly privileged systems.

A compromised pipeline can potentially:

- Modify software
- Publish malicious artifacts
- Access cloud resources
- Steal credentials
- Deploy unauthorized code

Therefore pipeline security is critical.

Important practices:

- Least privilege
- Short-lived credentials
- Secret rotation
- Dependency scanning
- Container scanning
- Static analysis
- Protected branches
- Required reviews
- Signed artifacts
- Audit logs
- Isolated runners


===============================================================================
25. DEVSECOPS
===============================================================================

DevSecOps integrates security into development and delivery.

Traditional:

Development -> Testing -> Security -> Operations

DevSecOps:

Security is considered throughout the lifecycle.

Example pipeline:

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


===============================================================================
26. BRANCHING STRATEGIES
===============================================================================

Common strategies:

1. Git Flow
2. GitHub Flow
3. GitLab Flow
4. Trunk-based development

Git Flow traditionally uses branches such as:

main
develop
feature/*
release/*
hotfix/*

Trunk-based development emphasizes short-lived branches and frequent
integration into the main branch.


===============================================================================
27. TRUNK-BASED DEVELOPMENT
===============================================================================

Trunk-based development usually encourages:

- Small changes
- Short-lived branches
- Frequent merges
- Strong automated tests
- Continuous integration

Conceptually:

Developer A ---\
Developer B ----> main
Developer C ---/
Developer D ---/

Instead of maintaining long-lived branches for weeks.


===============================================================================
28. PULL REQUEST CI
===============================================================================

A common workflow:

Developer creates branch
        |
        v
Developer pushes code
        |
        v
Pull Request
        |
        v
CI pipeline
        |
        +--> Tests
        +--> Lint
        +--> Security
        +--> Build
        |
        v
Review
        |
        v
Merge


===============================================================================
29. PROTECTED BRANCHES
===============================================================================

A production branch can be protected.

Rules might include:

- Pull request required
- Two reviewers required
- CI must pass
- No direct pushes
- Security checks required

This creates a controlled path into production.


===============================================================================
30. DEPLOYMENT STRATEGIES
===============================================================================

A deployment strategy determines how a new version reaches users.

Important strategies:

1. Recreate
2. Rolling
3. Blue-green
4. Canary
5. A/B deployment
6. Shadow deployment


===============================================================================
31. RECREATE DEPLOYMENT
===============================================================================

Old version is stopped.

New version starts.

Old:

[Application v1]

Deploy:

STOP v1
   |
   v
START v2

Advantages:

- Simple

Disadvantages:

- Downtime may occur


===============================================================================
32. ROLLING DEPLOYMENT
===============================================================================

Instances are updated gradually.

Initial:

v1 v1 v1 v1

Then:

v2 v1 v1 v1

Then:

v2 v2 v1 v1

Then:

v2 v2 v2 v1

Finally:

v2 v2 v2 v2

Advantages:

- Reduced downtime
- Gradual replacement

Risks:

- Multiple versions coexist


===============================================================================
33. BLUE-GREEN DEPLOYMENT
===============================================================================

Two environments exist.

Blue:
    Current production

Green:
    New version

Example:

Users
  |
  v
Load Balancer
  |
  +----> Blue v1
  |
  +----> Green v2

Initially traffic goes to Blue.

After validation:

Users
  |
  v
Load Balancer
  |
  +----> Green v2

Rollback:

Switch traffic back to Blue.


===============================================================================
34. CANARY DEPLOYMENT
===============================================================================

Only a small percentage of users initially receive the new version.

Example:

v1 -> 95%
v2 -> 5%

If healthy:

v1 -> 75%
v2 -> 25%

Then:

v1 -> 50%
v2 -> 50%

Eventually:

v2 -> 100%

Canary deployments reduce blast radius.


===============================================================================
35. BLAST RADIUS
===============================================================================

Blast radius means the amount of damage caused by a failure.

If a deployment immediately affects:

100% of users

then blast radius is high.

If it affects:

1% of users

then the blast radius is much smaller.

Canary releases are one method of reducing blast radius.


===============================================================================
36. FEATURE FLAGS
===============================================================================

Feature flags separate deployment from feature activation.

Example:

if feature_enabled:
    use_new_algorithm()
else:
    use_old_algorithm()

This means code can be deployed without immediately exposing the feature.

Feature flags can support:

- Gradual releases
- A/B testing
- Emergency disablement
- Customer segmentation
- Experimentation


===============================================================================
37. CI/CD AND CONTAINERS
===============================================================================

Containers make application packaging more consistent.

Typical flow:

Source Code
    |
    v
Docker Build
    |
    v
Container Image
    |
    v
Registry
    |
    v
Deployment Platform


===============================================================================
38. CONTAINER IMMUTABILITY
===============================================================================

A useful principle:

Build an immutable artifact.

Instead of changing a running container manually:

Build new version
    |
    v
Publish new image
    |
    v
Deploy new image

Example:

myapp:1.0.0
myapp:1.1.0
myapp:1.2.0


===============================================================================
39. KUBERNETES AND CI/CD
===============================================================================

Kubernetes commonly manages containerized workloads.

A conceptual pipeline:

Git
 |
 v
CI
 |
 v
Container Build
 |
 v
Registry
 |
 v
Kubernetes Deployment
 |
 v
Service
 |
 v
Users

Kubernetes can provide:

- Rolling deployments
- Health checks
- Scaling
- Service discovery
- Self-healing
- Deployment management


===============================================================================
40. HEALTH CHECKS
===============================================================================

A deployment should not simply ask:

"Did the process start?"

It should ask:

"Is the application actually healthy?"

Common checks:

Liveness:
    Is the application alive?

Readiness:
    Can the application receive traffic?

Startup:
    Has the application finished starting?


===============================================================================
41. INFRASTRUCTURE AS CODE
===============================================================================

Infrastructure as Code means infrastructure configuration is represented
as code.

Examples of IaC technologies:

- Terraform
- CloudFormation
- Pulumi
- Ansible

Conceptually:

Infrastructure Code
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


===============================================================================
42. CI/CD FOR INFRASTRUCTURE
===============================================================================

Infrastructure can also have CI/CD.

Example:

Developer modifies Terraform
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


===============================================================================
43. DATABASE MIGRATIONS
===============================================================================

Database changes are one of the most difficult CI/CD problems.

Example:

Version 1:
    name

Version 2:
    first_name
    last_name

A careless deployment can break old application instances.

Safer approach:

Expand
  |
  v
Deploy compatible code
  |
  v
Migrate data
  |
  v
Switch application
  |
  v
Contract


===============================================================================
44. EXPAND AND CONTRACT PATTERN
===============================================================================

Expand:

Add new schema without immediately removing old schema.

Contract:

Remove old schema after all dependent application versions no longer need it.

This supports zero-downtime deployments.


===============================================================================
45. ROLLBACK
===============================================================================

A rollback restores a previous known-good version.

Example:

Production:

v1 -> v2

If v2 fails:

v2
 |
 X
 |
 v
v1

Rollback should be fast and predictable.

Important:

A rollback is not always possible if database schema changes are irreversible.

Therefore:

Rollback planning must include:

- Application
- Database
- Configuration
- Infrastructure
- Dependencies


===============================================================================
46. ROLLFORWARD
===============================================================================

Instead of returning to v1, the team fixes the issue and deploys v3.

Example:

v1 -> v2 -> problem -> v3

Rollforward can be preferable when:

- The migration cannot safely be reversed
- The fix is small
- The new version is already prepared


===============================================================================
47. OBSERVABILITY
===============================================================================

A deployment pipeline should not stop at "deployment successful."

You need to know what happens after deployment.

Observability commonly includes:

Logs
Metrics
Traces

Three pillars:

Logs:
    What happened?

Metrics:
    How much / how often?

Traces:
    Where did the request travel?


===============================================================================
48. DEPLOYMENT VERIFICATION
===============================================================================

After deployment:

1. Check process health.
2. Check readiness.
3. Check HTTP status.
4. Check error rates.
5. Check latency.
6. Check resource usage.
7. Check business metrics.

Example:

Deployment
    |
    v
Health Check
    |
    v
Smoke Test
    |
    v
Monitor Metrics
    |
    v
Continue or Rollback


===============================================================================
49. SMOKE TESTS
===============================================================================

A smoke test is a quick verification that the most important functionality
works.

Example:

GET /health
GET /api/products
POST /api/login

Smoke tests should be fast enough to run immediately after deployment.


===============================================================================
50. DORA METRICS
===============================================================================

DORA research popularized four important software delivery metrics.

1. Deployment Frequency
2. Lead Time for Changes
3. Change Failure Rate
4. Time to Restore Service

These metrics help teams evaluate delivery performance.

Deployment Frequency:
    How often do deployments happen?

Lead Time for Changes:
    How long from code change to deployment?

Change Failure Rate:
    What percentage of deployments cause failures?

Time to Restore Service:
    How quickly can service be restored after a failure?


===============================================================================
51. PIPELINE SPEED
===============================================================================

A slow pipeline reduces developer productivity.

Suppose:

Checkout: 10 sec
Install: 60 sec
Lint: 20 sec
Tests: 300 sec
Build: 90 sec
Security: 120 sec

Total:

600 seconds

That is 10 minutes.

Optimization techniques:

- Dependency caching
- Parallel jobs
- Test splitting
- Incremental builds
- Smaller containers
- Reusable CI images
- Better test architecture


===============================================================================
52. PARALLELIZATION
===============================================================================

Instead of:

Lint -> Unit -> Security -> Build

you may run:

        +--> Lint
        |
Build --+--> Unit Tests
        |
        +--> Security

Then continue when required checks finish.


===============================================================================
53. CACHING
===============================================================================

Dependencies can often be cached.

Without cache:

Download dependencies
    |
    v
Install
    |
    v
Run tests

With cache:

Cache hit
    |
    v
Use dependencies
    |
    v
Run tests

Caching can significantly reduce pipeline duration.


===============================================================================
54. PIPELINE FAIL FAST
===============================================================================

Some checks should run early.

For example:

1. Syntax
2. Formatting
3. Lint
4. Unit tests
5. Integration tests
6. Build
7. Deployment

There is little value in spending 20 minutes on deployment if the code
fails a basic test.


===============================================================================
55. QUALITY GATES
===============================================================================

A quality gate is a condition that must be satisfied before proceeding.

Examples:

- Tests must pass
- Coverage must exceed threshold
- No critical vulnerabilities
- Build must succeed
- Required review must exist

Conceptually:

        PASS
         |
         v
    +---------+
    | Quality |
    |  Gate   |
    +---------+
         |
         v
     Deployment

If gate fails:

STOP.


===============================================================================
56. MANUAL APPROVAL
===============================================================================

Continuous Delivery often uses an approval step.

Example:

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

This provides governance and control.


===============================================================================
57. CONTINUOUS DEPLOYMENT DOES NOT MEAN "NO CONTROL"
===============================================================================

Continuous Deployment still needs controls.

Controls can be automated:

- Test gates
- Security gates
- Policy checks
- Canary monitoring
- Automatic rollback
- Approval policies
- Risk scoring
- Change windows

The difference is that the production promotion itself does not necessarily
require a human click.


===============================================================================
58. GITHUB ACTIONS CONCEPTS
===============================================================================

GitHub Actions commonly uses:

Workflow
    -> Job
        -> Step

Conceptually:

workflow
 |
 +--> job: test
 |       +--> checkout
 |       +--> install
 |       +--> pytest
 |
 +--> job: build
         +--> build artifact


===============================================================================
59. GENERIC GITHUB ACTIONS EXAMPLE
===============================================================================

A conceptual workflow looks like:

name: CI

on:
  push:
    branches:
      - main

jobs:

  test:
    runs-on: ubuntu-latest

    steps:
      - checkout repository
      - install dependencies
      - run lint
      - run tests

  build:
    needs: test

    steps:
      - build application
      - publish artifact


===============================================================================
60. JENKINS CONCEPTS
===============================================================================

Jenkins is a widely used automation server.

Common concepts include:

- Controller
- Agent
- Pipeline
- Stage
- Step
- Plugin
- Credential
- Workspace

Conceptual Jenkins pipeline:

pipeline {
    stages {
        checkout
        test
        build
        deploy
    }
}


===============================================================================
61. GITLAB CI/CD CONCEPTS
===============================================================================

GitLab CI/CD commonly uses:

.gitlab-ci.yml

Conceptual structure:

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


===============================================================================
62. CI/CD PIPELINE AS CODE
===============================================================================

Pipeline configuration should itself be version-controlled.

Benefits:

- Reviewability
- Reproducibility
- Auditability
- History
- Collaboration

Instead of configuring everything manually in a UI:

Pipeline configuration
        |
        v
Git repository
        |
        v
Pull request
        |
        v
Review
        |
        v
Pipeline


===============================================================================
63. REPRODUCIBILITY
===============================================================================

A strong CI/CD system should produce consistent results.

If:

Commit A

is built today and tomorrow under equivalent conditions, the output should
be predictable.

Sources of non-reproducibility include:

- Floating dependencies
- Mutable base images
- Environment differences
- Undocumented configuration
- External service changes


===============================================================================
64. DEPENDENCY PINNING
===============================================================================

Instead of:

requests

use a controlled version:

requests==2.x.x

The exact version should depend on project requirements.

Pinning improves reproducibility.

Dependency lock files are another common solution.


===============================================================================
65. SUPPLY CHAIN SECURITY
===============================================================================

Modern CI/CD must consider software supply chain security.

Potential risks:

- Malicious dependencies
- Compromised packages
- Compromised build runners
- Tampered artifacts
- Malicious build scripts

Controls can include:

- Dependency scanning
- Lock files
- Trusted registries
- Artifact signing
- Provenance
- SBOM
- Minimal permissions


===============================================================================
66. SBOM
===============================================================================

SBOM means:

Software Bill of Materials.

It describes components contained in software.

Example:

Application
 |
 +--> Python
 +--> FastAPI
 +--> Requests
 +--> OpenSSL
 +--> Operating system packages

An SBOM helps organizations understand software composition and vulnerability
exposure.


===============================================================================
67. ARTIFACT SIGNING
===============================================================================

Artifact signing allows consumers to verify that an artifact came from a
trusted source and was not modified unexpectedly.

Conceptually:

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


===============================================================================
68. EPHEMERAL CI RUNNERS
===============================================================================

An ephemeral runner is created for a job and then destroyed.

Advantages:

- Cleaner environment
- Reduced cross-job contamination
- Better isolation
- Lower persistence risk

Conceptually:

Create runner
    |
    v
Execute pipeline
    |
    v
Destroy runner


===============================================================================
69. MONOREPO CI/CD
===============================================================================

A monorepo stores multiple applications/services in one repository.

Example:

repository/
    frontend/
    backend/
    service-a/
    service-b/
    shared-library/


Challenge:

A change in one directory should not necessarily rebuild everything.

Path-based pipelines can optimize this.

Example:

frontend/** changed
    -> frontend pipeline

backend/** changed
    -> backend pipeline


===============================================================================
70. POLYREPO CI/CD
===============================================================================

Polyrepo means multiple repositories.

Example:

frontend-repository
backend-repository
authentication-repository
payments-repository

Advantages:

- Independent ownership
- Independent pipelines
- Smaller repositories

Challenges:

- Dependency coordination
- Cross-repository changes


===============================================================================
71. MICROSERVICES CI/CD
===============================================================================

A microservices architecture may have:

service-a
service-b
service-c
service-d

Each service can have an independent pipeline.

Example:

service-a code
    |
    v
service-a CI/CD

service-b code
    |
    v
service-b CI/CD

This enables independent releases.

But it also increases operational complexity.


===============================================================================
72. DEPENDENCY MANAGEMENT BETWEEN SERVICES
===============================================================================

Suppose:

Service A depends on Service B.

If B changes its API, A may break.

Solutions include:

- Contract testing
- Backward-compatible APIs
- API versioning
- Consumer-driven contracts
- Coordinated releases


===============================================================================
73. CONTRACT TESTING
===============================================================================

Contract tests verify that services agree on an interface.

Example:

Consumer expects:

GET /users/{id}

Response:

{
    "id": 10,
    "name": "Alice"
}

Provider changes:

"name" -> "full_name"

Contract testing can identify this compatibility problem before production.


===============================================================================
74. ZERO-DOWNTIME DEPLOYMENT
===============================================================================

Zero-downtime deployment attempts to keep service available while deploying
a new version.

Techniques include:

- Rolling deployments
- Blue-green deployments
- Canary deployments
- Backward-compatible database migrations
- Load balancer control
- Health checks


===============================================================================
75. AUTOMATIC ROLLBACK
===============================================================================

A sophisticated pipeline can automatically rollback.

Example:

Deploy v2
    |
    v
Error rate increases
    |
    v
Threshold exceeded
    |
    v
Automatic rollback
    |
    v
v1 restored

Example policy:

if error_rate > threshold:
    rollback()


===============================================================================
76. PROGRESSIVE DELIVERY
===============================================================================

Progressive delivery combines:

- Feature flags
- Canary releases
- Automated analysis
- Gradual traffic shifting
- Automated rollback

Example:

Deploy v2
 |
 v
1% traffic
 |
 v
Health analysis
 |
 +--> bad -> rollback
 |
 +--> good
       |
       v
10%
 |
 v
50%
 |
 v
100%


===============================================================================
77. GITOPS
===============================================================================

GitOps treats Git as the source of truth for desired infrastructure and
application state.

Conceptually:

Git Repository
      |
      v
Desired State
      |
      v
GitOps Controller
      |
      v
Cluster

The controller continuously attempts to make actual state match desired
state.


===============================================================================
78. CI VS CD RESPONSIBILITIES
===============================================================================

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


===============================================================================
79. CI/CD VS DEVOPS
===============================================================================

DevOps is broader than CI/CD.

DevOps includes:

- Development
- Operations
- Automation
- Monitoring
- Infrastructure
- Collaboration
- Security
- Reliability
- Continuous improvement

CI/CD is one important component of DevOps.


===============================================================================
80. CI/CD VS AGILE
===============================================================================

Agile is primarily a development methodology/philosophy.

CI/CD is an engineering automation and delivery practice.

They complement each other.

Agile:
    Small increments of work.

CI/CD:
    Rapidly integrate, validate, and deliver those increments.


===============================================================================
81. COMMON CI/CD ANTI-PATTERNS
===============================================================================

Anti-pattern 1:
    Huge batches of changes.

Anti-pattern 2:
    Manual deployments.

Anti-pattern 3:
    No automated tests.

Anti-pattern 4:
    Secrets stored in Git.

Anti-pattern 5:
    Rebuilding different artifacts per environment.

Anti-pattern 6:
    No rollback strategy.

Anti-pattern 7:
    Deploying without health checks.

Anti-pattern 8:
    Ignoring dependency security.

Anti-pattern 9:
    Extremely long-lived branches.

Anti-pattern 10:
    Pipeline configuration managed manually and undocumented.


===============================================================================
82. "WORKS ON MY MACHINE"
===============================================================================

This problem occurs when application behavior differs between environments.

Possible causes:

- Python version
- Dependency version
- OS differences
- Environment variables
- Database differences
- Missing system packages
- Configuration differences

CI helps detect environment problems earlier.


===============================================================================
83. IMMUTABLE INFRASTRUCTURE
===============================================================================

Instead of modifying servers manually:

Server v1
    |
    X modify manually
    |
    ?

prefer:

Image v1
    |
    v
Build image v2
    |
    v
Deploy v2

This makes environments more predictable.


===============================================================================
84. PIPELINE IDEMPOTENCY
===============================================================================

An idempotent operation can safely be repeated without producing unwanted
additional effects.

Example:

If deployment runs twice, it should not create duplicate resources or
corrupt the environment.

Idempotency is important for reliable automation.


===============================================================================
85. PIPELINE OBSERVABILITY
===============================================================================

The pipeline itself should be observable.

Track:

- Duration
- Failure rate
- Queue time
- Most common failure
- Flaky tests
- Deployment frequency
- Rollback frequency

A pipeline is itself a production-like system for engineering delivery.


===============================================================================
86. FLAKY TESTS
===============================================================================

A flaky test sometimes passes and sometimes fails without relevant code
changes.

Flaky tests are dangerous because developers stop trusting CI.

A mature organization tracks:

- Test failure frequency
- Flaky test rate
- Test duration
- Failure causes

Flaky tests should be fixed rather than permanently ignored.


===============================================================================
87. PIPELINE GOVERNANCE
===============================================================================

Large organizations may require:

- Approval policies
- Audit trails
- Segregation of duties
- Security checks
- Change management
- Protected production environments
- Compliance evidence


===============================================================================
88. POLICY AS CODE
===============================================================================

Policies can be represented as executable rules.

Example conceptual policy:

if environment == "production":
    require_approval()

or:

if vulnerability_severity == "critical":
    block_deployment()


===============================================================================
89. ENVIRONMENT PROMOTION
===============================================================================

A useful pattern:

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

The same artifact should ideally be promoted rather than rebuilt.


===============================================================================
90. RELEASE VS DEPLOYMENT
===============================================================================

These concepts are related but different.

Deployment:
    Putting software into an environment.

Release:
    Making a capability available to users.

Feature flags make this distinction especially clear.

You can deploy code without releasing the feature.


===============================================================================
91. CONTINUOUS RELEASE
===============================================================================

A mature delivery system separates:

Build
Release
Deploy
Activate

This provides greater control.

Example:

Build v10
   |
Deploy v10
   |
Feature disabled
   |
Test internally
   |
Enable for 5%
   |
Enable for 100%


===============================================================================
92. ENVIRONMENT PARITY
===============================================================================

The closer staging resembles production, the more meaningful staging
validation becomes.

Differences should be minimized where practical.

Examples:

- Same runtime version
- Same container image
- Similar configuration
- Similar network architecture
- Similar database behavior


===============================================================================
93. DISASTER RECOVERY AND CI/CD
===============================================================================

CI/CD should support recovery.

A mature system can recreate:

- Application
- Infrastructure
- Configuration
- Deployment

from version-controlled definitions.

This is why:

Infrastructure as Code
+
Configuration as Code
+
Pipeline as Code

is powerful.


===============================================================================
94. DISASTER RECOVERY PIPELINE
===============================================================================

Conceptually:

Git
 |
 +--> Application
 |
 +--> Infrastructure
 |
 +--> Configuration
 |
 v
Automated Build
 |
 v
Infrastructure Provisioning
 |
 v
Application Deployment
 |
 v
Validation


===============================================================================
95. MATURITY LEVELS
===============================================================================

Level 0:
    Manual deployments

Level 1:
    Automated builds

Level 2:
    Automated tests

Level 3:
    Continuous Integration

Level 4:
    Continuous Delivery

Level 5:
    Continuous Deployment

Level 6:
    Progressive delivery + automated rollback + observability

These levels are conceptual rather than universal industry standards.


===============================================================================
96. COMPLETE CI/CD ARCHITECTURE
===============================================================================

A sophisticated architecture might look like:

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
    +--> Lint
    +--> Unit Tests
    +--> Integration Tests
    +--> SAST
    +--> Dependency Scan
    +--> Secret Scan
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
    +--> Smoke Tests
    +--> Integration Tests
    +--> Security Tests
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
    +--> Failure -> Rollback
    |
    +--> Success
             |
             v
        Full Production
             |
             v
        Monitoring


===============================================================================
97. SIMULATING A CI/CD PIPELINE IN PYTHON
===============================================================================

The following section implements a simplified local CI/CD simulation.

It demonstrates:

- Pipeline stages
- Jobs
- Success/failure
- Artifacts
- Quality gates
- Deployment
- Rollback
- Monitoring

This does not connect to GitHub, GitLab, Jenkins, Kubernetes, or a cloud
provider.


===============================================================================
98. IMPORTS
===============================================================================
"""

from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any
import time
import random


# =============================================================================
# 99. DATA MODELS
# =============================================================================

@dataclass
class Artifact:
    """
    Represents a build artifact.

    In a real system this might be:
        - Docker image
        - Python wheel
        - JAR
        - ZIP
        - npm package
    """

    name: str
    version: str
    checksum: str = "example-checksum"


@dataclass
class PipelineContext:
    """
    Stores information shared across pipeline stages.
    """

    commit_id: str
    branch: str
    environment: str = "development"
    artifact: Artifact | None = None
    logs: List[str] = field(default_factory=list)
    deployment_version: str | None = None

    def log(self, message: str) -> None:
        self.logs.append(message)
        print(message)


@dataclass
class PipelineJob:
    """
    Represents an individual pipeline job.
    """

    name: str
    action: Callable[[PipelineContext], bool]


# =============================================================================
# 100. PIPELINE CLASS
# =============================================================================

class CICDPipeline:
    """
    Simplified CI/CD pipeline engine.

    The pipeline executes jobs sequentially.

    A production-grade CI/CD platform would provide considerably more
    functionality, such as:

        - Distributed runners
        - Dependency caching
        - Artifacts
        - Secrets
        - Permissions
        - Retry mechanisms
        - Parallel jobs
        - Approvals
        - Deployment strategies
        - Logs
        - Metrics
        - Webhooks
    """

    def __init__(self, context: PipelineContext):
        self.context = context
        self.jobs: List[PipelineJob] = []

    def add_job(self, job: PipelineJob) -> None:
        self.jobs.append(job)

    def run(self) -> bool:
        self.context.log("\n=== PIPELINE STARTED ===")

        for job in self.jobs:
            self.context.log(f"\nRunning job: {job.name}")

            success = job.action(self.context)

            if success:
                self.context.log(f"SUCCESS: {job.name}")
            else:
                self.context.log(f"FAILED: {job.name}")
                self.context.log("\n=== PIPELINE STOPPED ===")
                return False

        self.context.log("\n=== PIPELINE COMPLETED ===")
        return True


# =============================================================================
# 101. CI JOBS
# =============================================================================

def checkout_code(context: PipelineContext) -> bool:
    """
    Simulates checking out source code.
    """

    context.log(
        f"Checking out branch '{context.branch}' "
        f"at commit '{context.commit_id}'."
    )

    return True


def install_dependencies(context: PipelineContext) -> bool:
    """
    Simulates dependency installation.
    """

    context.log("Installing dependencies...")

    # In real CI:
    #
    # pip install -r requirements.txt
    #
    # or:
    #
    # npm ci
    #
    # or:
    #
    # mvn install

    return True


def run_lint(context: PipelineContext) -> bool:
    """
    Simulates static code quality analysis.
    """

    context.log("Running lint and formatting checks...")

    # Real examples might include:
    #
    # ruff check .
    # black --check .
    # eslint .
    # gofmt -check

    return True


def run_unit_tests(context: PipelineContext) -> bool:
    """
    Simulates unit testing.
    """

    context.log("Running unit tests...")

    # Example:
    #
    # pytest
    #
    # A real CI system would capture the test exit code.

    return True


def run_security_scan(context: PipelineContext) -> bool:
    """
    Simulates security scanning.
    """

    context.log("Running dependency and security scans...")

    # Real tools might include:
    #
    # pip-audit
    # Trivy
    # Semgrep
    # Snyk
    #
    # depending on organizational requirements.

    return True


def build_application(context: PipelineContext) -> bool:
    """
    Simulates application compilation/building.
    """

    context.log("Building application...")

    context.artifact = Artifact(
        name="example-application",
        version="1.0.0",
    )

    context.log(
        f"Created artifact: "
        f"{context.artifact.name}:{context.artifact.version}"
    )

    return True


# =============================================================================
# 102. DELIVERY JOBS
# =============================================================================

def publish_artifact(context: PipelineContext) -> bool:
    """
    Simulates publishing an artifact to an artifact registry.
    """

    if context.artifact is None:
        context.log("No artifact available.")
        return False

    context.log(
        f"Publishing artifact "
        f"{context.artifact.name}:{context.artifact.version}"
    )

    return True


def deploy_to_staging(context: PipelineContext) -> bool:
    """
    Simulates deployment to staging.
    """

    context.environment = "staging"

    if context.artifact is None:
        return False

    context.log(
        f"Deploying {context.artifact.version} to staging."
    )

    context.deployment_version = context.artifact.version

    return True


def run_smoke_tests(context: PipelineContext) -> bool:
    """
    Simulates post-deployment smoke testing.
    """

    context.log("Running staging smoke tests...")

    checks = [
        "Application starts",
        "Health endpoint works",
        "Database connection works",
        "Critical API responds",
    ]

    for check in checks:
        context.log(f"PASS: {check}")

    return True


# =============================================================================
# 103. CONTINUOUS DELIVERY APPROVAL
# =============================================================================

def manual_production_approval(context: PipelineContext) -> bool:
    """
    Simulates a manual approval.

    In a real CI/CD platform, this would usually be represented by an
    environment approval or protected deployment gate.

    For this educational simulation we automatically approve it.
    """

    context.log("Production approval requested.")
    context.log("Approval granted for simulation.")

    return True


# =============================================================================
# 104. PRODUCTION DEPLOYMENT
# =============================================================================

def deploy_to_production(context: PipelineContext) -> bool:
    """
    Simulates production deployment.
    """

    context.environment = "production"

    if context.artifact is None:
        return False

    context.log(
        f"Deploying version {context.artifact.version} to production."
    )

    context.deployment_version = context.artifact.version

    return True


# =============================================================================
# 105. POST-DEPLOYMENT MONITORING
# =============================================================================

def monitor_production(context: PipelineContext) -> bool:
    """
    Simulates monitoring after production deployment.
    """

    context.log("Monitoring production deployment...")

    metrics = {
        "error_rate": 0.2,
        "latency_ms": 120,
        "availability_percent": 99.95,
    }

    for name, value in metrics.items():
        context.log(f"{name}: {value}")

    if metrics["error_rate"] > 5:
        context.log("Error rate too high.")
        return False

    return True


# =============================================================================
# 106. ROLLBACK
# =============================================================================

def rollback(context: PipelineContext, previous_version: str) -> None:
    """
    Simulates rollback to a previous version.
    """

    context.log(
        f"Rolling back production from "
        f"{context.deployment_version} to {previous_version}."
    )

    context.deployment_version = previous_version

    context.log(
        f"Rollback complete. Running version: "
        f"{context.deployment_version}"
    )


# =============================================================================
# 107. BUILD A CONTINUOUS DELIVERY PIPELINE
# =============================================================================

def build_continuous_delivery_pipeline() -> CICDPipeline:
    """
    Creates a CI + Continuous Delivery pipeline.
    """

    context = PipelineContext(
        commit_id="abc123",
        branch="main",
    )

    pipeline = CICDPipeline(context)

    pipeline.add_job(
        PipelineJob("Checkout", checkout_code)
    )

    pipeline.add_job(
        PipelineJob("Install Dependencies", install_dependencies)
    )

    pipeline.add_job(
        PipelineJob("Lint", run_lint)
    )

    pipeline.add_job(
        PipelineJob("Unit Tests", run_unit_tests)
    )

    pipeline.add_job(
        PipelineJob("Security Scan", run_security_scan)
    )

    pipeline.add_job(
        PipelineJob("Build", build_application)
    )

    pipeline.add_job(
        PipelineJob("Publish Artifact", publish_artifact)
    )

    pipeline.add_job(
        PipelineJob("Deploy Staging", deploy_to_staging)
    )

    pipeline.add_job(
        PipelineJob("Smoke Tests", run_smoke_tests)
    )

    pipeline.add_job(
        PipelineJob(
            "Production Approval",
            manual_production_approval,
        )
    )

    pipeline.add_job(
        PipelineJob(
            "Production Deployment",
            deploy_to_production,
        )
    )

    pipeline.add_job(
        PipelineJob(
            "Production Monitoring",
            monitor_production,
        )
    )

    return pipeline


# =============================================================================
# 108. CONTINUOUS DEPLOYMENT
# =============================================================================

def build_continuous_deployment_pipeline() -> CICDPipeline:
    """
    Creates a conceptual Continuous Deployment pipeline.

    Notice that there is no mandatory manual approval stage.

    Once all automated gates pass, production deployment occurs.
    """

    context = PipelineContext(
        commit_id="xyz789",
        branch="main",
    )

    pipeline = CICDPipeline(context)

    pipeline.add_job(
        PipelineJob("Checkout", checkout_code)
    )

    pipeline.add_job(
        PipelineJob("Install Dependencies", install_dependencies)
    )

    pipeline.add_job(
        PipelineJob("Lint", run_lint)
    )

    pipeline.add_job(
        PipelineJob("Unit Tests", run_unit_tests)
    )

    pipeline.add_job(
        PipelineJob("Security Scan", run_security_scan)
    )

    pipeline.add_job(
        PipelineJob("Build", build_application)
    )

    pipeline.add_job(
        PipelineJob("Publish Artifact", publish_artifact)
    )

    pipeline.add_job(
        PipelineJob("Deploy Staging", deploy_to_staging)
    )

    pipeline.add_job(
        PipelineJob("Smoke Tests", run_smoke_tests)
    )

    # No manual production approval here.

    pipeline.add_job(
        PipelineJob(
            "Automatic Production Deployment",
            deploy_to_production,
        )
    )

    pipeline.add_job(
        PipelineJob(
            "Production Monitoring",
            monitor_production,
        )
    )

    return pipeline


# =============================================================================
# 109. CANARY DEPLOYMENT SIMULATION
# =============================================================================

def canary_deployment(
    version: str,
    traffic_steps: List[int] | None = None,
) -> None:
    """
    Demonstrates a simplified canary release.

    traffic_steps represents the percentage of traffic sent to the new
    version.

    Example:

        [5, 10, 25, 50, 100]

    """

    if traffic_steps is None:
        traffic_steps = [5, 10, 25, 50, 100]

    print("\n=== CANARY DEPLOYMENT ===")

    for percentage in traffic_steps:
        print(
            f"Sending {percentage}% traffic to version {version}."
        )

        # In a real deployment, automated analysis would inspect:
        #
        # - Error rate
        # - Latency
        # - Saturation
        # - Business KPIs
        #
        # Here we simply simulate success.

        health_ok = True

        if not health_ok:
            print("Canary unhealthy. Rolling back.")
            return

        print(
            f"Version {version} healthy at "
            f"{percentage}% traffic."
        )

    print(
        f"Version {version} is now serving 100% traffic."
    )


# =============================================================================
# 110. BLUE-GREEN DEPLOYMENT SIMULATION
# =============================================================================

def blue_green_deployment(
    current_version: str,
    new_version: str,
) -> None:
    """
    Demonstrates the concept of blue-green deployment.
    """

    print("\n=== BLUE-GREEN DEPLOYMENT ===")

    print(f"Blue environment:  {current_version}")
    print(f"Green environment: {new_version}")

    print("Deploying new version to Green.")
    print("Running health checks on Green.")

    healthy = True

    if not healthy:
        print("Green unhealthy. Keeping Blue active.")
        return

    print("Green is healthy.")
    print("Switching production traffic from Blue to Green.")
    print(f"Production now serves {new_version}.")

    print("Blue remains available for rapid rollback.")


# =============================================================================
# 111. ROLLING DEPLOYMENT SIMULATION
# =============================================================================

def rolling_deployment(
    total_instances: int,
    old_version: str,
    new_version: str,
) -> None:
    """
    Demonstrates a rolling deployment.
    """

    print("\n=== ROLLING DEPLOYMENT ===")

    instances = [old_version] * total_instances

    for index in range(total_instances):
        print(
            f"Updating instance {index + 1} "
            f"from {old_version} to {new_version}."
        )

        instances[index] = new_version

        print("Current fleet:", instances)

    print("Rolling deployment completed.")


# =============================================================================
# 112. FEATURE FLAG SIMULATION
# =============================================================================

class FeatureFlags:
    """
    Simplified feature flag manager.
    """

    def __init__(self):
        self.flags: Dict[str, bool] = {}

    def enable(self, name: str) -> None:
        self.flags[name] = True

    def disable(self, name: str) -> None:
        self.flags[name] = False

    def is_enabled(self, name: str) -> bool:
        return self.flags.get(name, False)


def demonstrate_feature_flags() -> None:
    """
    Shows deployment and release separation.
    """

    print("\n=== FEATURE FLAGS ===")

    flags = FeatureFlags()

    flags.disable("new_checkout")

    print(
        "New checkout enabled:",
        flags.is_enabled("new_checkout"),
    )

    print("Deploying code containing new checkout.")

    flags.enable("new_checkout")

    print(
        "New checkout enabled:",
        flags.is_enabled("new_checkout"),
    )


# =============================================================================
# 113. QUALITY GATE SIMULATION
# =============================================================================

def quality_gate(
    tests_passed: bool,
    security_passed: bool,
    lint_passed: bool,
) -> bool:
    """
    Represents a simplified deployment quality gate.
    """

    print("\n=== QUALITY GATE ===")

    results = {
        "tests": tests_passed,
        "security": security_passed,
        "lint": lint_passed,
    }

    for check, result in results.items():
        print(
            f"{check}: {'PASS' if result else 'FAIL'}"
        )

    return all(results.values())


# =============================================================================
# 114. DORA METRICS SIMULATION
# =============================================================================

@dataclass
class DeliveryMetrics:
    """
    Simplified representation of delivery metrics.
    """

    deployment_frequency_per_week: float
    lead_time_hours: float
    change_failure_rate_percent: float
    mean_time_to_restore_hours: float

    def print_report(self) -> None:
        print("\n=== DELIVERY METRICS ===")

        print(
            "Deployment frequency:",
            self.deployment_frequency_per_week,
            "per week",
        )

        print(
            "Lead time:",
            self.lead_time_hours,
            "hours",
        )

        print(
            "Change failure rate:",
            self.change_failure_rate_percent,
            "%",
        )

        print(
            "Mean time to restore:",
            self.mean_time_to_restore_hours,
            "hours",
        )


# =============================================================================
# 115. PIPELINE DESIGN PRINCIPLES
# =============================================================================

"""
When designing a CI/CD pipeline, ask:

1. Is every important change automatically validated?
2. Can a developer discover failures quickly?
3. Are tests reliable?
4. Is the artifact immutable?
5. Is the artifact traceable to a commit?
6. Are secrets protected?
7. Are production environments protected?
8. Can deployments be rolled back?
9. Are deployments observable?
10. Can infrastructure be recreated?
11. Are dependencies controlled?
12. Is the pipeline itself version-controlled?
13. Can the pipeline run repeatedly safely?
14. Is the blast radius controlled?
15. Can failures stop promotion automatically?
"""


# =============================================================================
# 116. COMPLETE PIPELINE EXAMPLE
# =============================================================================

def demonstrate_complete_ci_cd() -> None:
    """
    Runs the educational demonstrations.
    """

    print("=" * 79)
    print("CI/CD FUNDAMENTALS DEMONSTRATION")
    print("=" * 79)

    # -------------------------------------------------------------------------
    # Continuous Delivery
    # -------------------------------------------------------------------------

    print("\n\n### CONTINUOUS DELIVERY PIPELINE ###")

    delivery_pipeline = build_continuous_delivery_pipeline()

    delivery_pipeline.run()

    # -------------------------------------------------------------------------
    # Continuous Deployment
    # -------------------------------------------------------------------------

    print("\n\n### CONTINUOUS DEPLOYMENT PIPELINE ###")

    deployment_pipeline = build_continuous_deployment_pipeline()

    deployment_pipeline.run()

    # -------------------------------------------------------------------------
    # Canary
    # -------------------------------------------------------------------------

    canary_deployment(
        version="2.0.0",
        traffic_steps=[5, 10, 25, 50, 100],
    )

    # -------------------------------------------------------------------------
    # Blue-Green
    # -------------------------------------------------------------------------

    blue_green_deployment(
        current_version="1.0.0",
        new_version="2.0.0",
    )

    # -------------------------------------------------------------------------
    # Rolling
    # -------------------------------------------------------------------------

    rolling_deployment(
        total_instances=4,
        old_version="1.0.0",
        new_version="2.0.0",
    )

    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------

    demonstrate_feature_flags()

    # -------------------------------------------------------------------------
    # Quality Gate
    # -------------------------------------------------------------------------

    passed = quality_gate(
        tests_passed=True,
        security_passed=True,
        lint_passed=True,
    )

    print(
        "\nDeployment permitted:",
        passed,
    )

    # -------------------------------------------------------------------------
    # Metrics
    # -------------------------------------------------------------------------

    metrics = DeliveryMetrics(
        deployment_frequency_per_week=15,
        lead_time_hours=4,
        change_failure_rate_percent=5,
        mean_time_to_restore_hours=1,
    )

    metrics.print_report()


# =============================================================================
# 117. INTERVIEW QUESTIONS
# =============================================================================

"""
Important CI/CD interview questions:

1. What is CI?
2. What is Continuous Delivery?
3. What is Continuous Deployment?
4. What is the difference between Delivery and Deployment?
5. Why is automated testing important?
6. What is a CI/CD pipeline?
7. What is a build artifact?
8. What does "build once, deploy many" mean?
9. What is a deployment environment?
10. What is a quality gate?
11. What is a canary deployment?
12. What is blue-green deployment?
13. What is a rolling deployment?
14. What is a rollback?
15. What is a feature flag?
16. What is Infrastructure as Code?
17. What is GitOps?
18. What is DevSecOps?
19. What are DORA metrics?
20. What is a flaky test?
21. Why should secrets not be committed to Git?
22. What is artifact signing?
23. What is an SBOM?
24. What is trunk-based development?
25. How would you design a CI/CD pipeline for a Python application?
26. How would you safely deploy a database schema change?
27. How would you implement zero-downtime deployment?
28. How would you reduce CI pipeline duration?
29. How would you automatically rollback a failed deployment?
30. How would you secure CI/CD runners?
"""


# =============================================================================
# 118. FINAL MENTAL MODEL
# =============================================================================

"""
The simplest mental model is:

CI
==
"Integrate and validate code continuously."

Continuous Delivery
===================
"Keep software always ready for release."

Continuous Deployment
======================
"Automatically release validated software to production."

A mature pipeline looks like:

        CODE
          |
          v
        COMMIT
          |
          v
         CI
          |
          +--> LINT
          |
          +--> TEST
          |
          +--> SECURITY
          |
          v
        BUILD
          |
          v
       ARTIFACT
          |
          v
       STAGING
          |
          v
       VALIDATE
          |
          v
      PRODUCTION
          |
          v
       MONITOR
          |
          v
    CONTINUE / ROLLBACK

The fundamental philosophy is:

MAKE CHANGES SMALL
        +
AUTOMATE VALIDATION
        +
BUILD REPRODUCIBLY
        +
PROMOTE IMMUTABLE ARTIFACTS
        +
DEPLOY SAFELY
        +
OBSERVE EVERYTHING
        +
ROLL BACK QUICKLY
        =
RELIABLE SOFTWARE DELIVERY


===============================================================================
119. FINAL TAKEAWAY
===============================================================================

CI/CD is not merely a collection of tools.

GitHub Actions, GitLab CI/CD, Jenkins, Azure Pipelines, CircleCI and similar
systems are implementations of broader engineering principles.

The deeper goal is to create a software delivery system that is:

- Fast
- Reliable
- Repeatable
- Secure
- Observable
- Reproducible
- Auditable
- Recoverable

The progression is:

Continuous Integration
    ->
frequent integration and automated validation

Continuous Delivery
    ->
software is always ready for release

Continuous Deployment
    ->
validated software is automatically deployed

A mature organization then adds:

    +
Automated testing
    +
Security
    +
Infrastructure as Code
    +
Immutable artifacts
    +
Feature flags
    +
Progressive delivery
    +
Observability
    +
Automated rollback
    +
Policy as Code
    +
Supply-chain security

That is the deeper meaning of modern CI/CD.

===============================================================================
END OF CI/CD FUNDAMENTALS
===============================================================================
"""


if __name__ == "__main__":
    demonstrate_complete_ci_cd()

# ============================================================
# INTRODUCTION TO DEVOPS
# ============================================================
#
# Topics Covered:
# 1. What is DevOps?
# 2. Why DevOps was created
# 3. History and evolution of DevOps
# 4. Traditional Software Development
# 5. Development vs Operations
# 6. Problems with the Dev and Ops separation
# 7. DevOps culture
# 8. Collaboration and shared responsibility
# 9. CALMS framework
# 10. Culture
# 11. Automation
# 12. Lean
# 13. Measurement
# 14. Sharing
# 15. Automation mindset
# 16. Infrastructure and deployment examples
# 17. CI/CD concepts
# 18. DevOps lifecycle
# 19. Real-world DevOps example
# 20. Beginner exercises
#
# ============================================================


print("=" * 70)
print("INTRODUCTION TO DEVOPS")
print("=" * 70)


# ============================================================
# 1. WHAT IS DEVOPS?
# ============================================================

print("\n1. WHAT IS DEVOPS?")
print("-" * 70)

print("""
DevOps is a combination of:

    Development + Operations

Development is generally responsible for creating software.

Operations is generally responsible for running, deploying,
monitoring, and maintaining software.

DevOps brings these responsibilities closer together.

The goal of DevOps is not simply to install tools.

DevOps is primarily:

    A culture
    + A set of practices
    + Automation
    + Collaboration
    + Continuous improvement
    + Measurement
    + Shared responsibility

The ultimate objective is to help organizations deliver
reliable software faster and more consistently.
""")


# ============================================================
# 2. SIMPLE REAL-WORLD ANALOGY
# ============================================================

print("\n2. DEVOPS USING A SIMPLE ANALOGY")
print("-" * 70)

print("""
Imagine a restaurant.

The chef prepares food.

The waiter serves the food.

The manager coordinates the restaurant.

The delivery person delivers food to customers.

If everyone works independently without communication,
problems occur.

For example:

    Chef:
        "The food is ready."

    Waiter:
        "I don't know where the order goes."

    Delivery person:
        "Nobody told me the address."

The problem is not that people are incapable.

The problem is lack of coordination.

Software organizations can have a similar problem.

Developers create software.

Operations teams deploy and maintain it.

If these teams work in isolation, software delivery can become
slow and unreliable.

DevOps attempts to create a collaborative system where:

    Developers
        +
    Operations
        +
    Security
        +
    QA
        +
    Infrastructure
        +
    Business

work together toward a shared outcome.
""")


# ============================================================
# 3. WHY DOES DEVOPS EXIST?
# ============================================================

print("\n3. WHY DOES DEVOPS EXIST?")
print("-" * 70)

print("""
Before modern DevOps practices became common, organizations
often separated software development and operations.

A typical process looked like:

    Developer writes code
            |
            v
    Developer finishes project
            |
            v
    Code handed to Operations
            |
            v
    Operations deploys application
            |
            v
    Problems appear
            |
            v
    Developer investigates
            |
            v
    Operations investigates
            |
            v
    More meetings
            |
            v
    More delays

This creates friction.

DevOps attempts to reduce this friction.

Instead of thinking:

    "The developers finished their job."

and:

    "Operations has to deal with it."

DevOps encourages:

    "We are collectively responsible for delivering
     and operating reliable software."
""")


# ============================================================
# 4. TRADITIONAL SOFTWARE DEVELOPMENT
# ============================================================

print("\n4. TRADITIONAL SOFTWARE DEVELOPMENT")
print("-" * 70)

print("""
A simplified traditional workflow might look like:

    Requirements
        |
        v
    Design
        |
        v
    Development
        |
        v
    Testing
        |
        v
    Deployment
        |
        v
    Operations

The problem is that these stages can become isolated.

A developer might say:

    "It works on my machine."

Operations might respond:

    "It doesn't work in production."

This famous statement represents an important class of
software delivery problems.

The developer's environment may differ from production.

For example:

Developer machine:

    Python 3.13
    PostgreSQL 17
    Linux
    Package version X

Production:

    Python 3.11
    PostgreSQL 15
    Different Linux distribution
    Different package version

The application may behave differently.

DevOps tries to make environments, deployment processes,
testing, configuration, and monitoring more consistent.
""")


# ============================================================
# 5. DEVELOPMENT VS OPERATIONS
# ============================================================

print("\n5. DEVELOPMENT VS OPERATIONS")
print("-" * 70)

print("""
DEVELOPMENT

Developers generally focus on:

    - Writing application code
    - Designing features
    - Fixing bugs
    - Writing tests
    - Building APIs
    - Implementing business logic
    - Improving applications

OPERATIONS

Operations traditionally focuses on:

    - Servers
    - Networking
    - Deployment
    - Availability
    - Monitoring
    - Infrastructure
    - Backups
    - Reliability
    - Incident response

These responsibilities are different.

However, modern software delivery requires them to work
together.

DevOps does NOT mean:

    "Developers do everything."

It means:

    "Teams collaborate across the entire software lifecycle."
""")


# ============================================================
# 6. COMPARISON
# ============================================================

print("\n6. DEVELOPMENT VS OPERATIONS COMPARISON")
print("-" * 70)

development = {
    "Primary focus": "Building software",
    "Typical activities": "Coding, testing, debugging",
    "Main concern": "Features and application behavior",
    "Common tools": "IDEs, Git, programming languages",
}

operations = {
    "Primary focus": "Running software",
    "Typical activities": "Deployment, monitoring, infrastructure",
    "Main concern": "Availability and reliability",
    "Common tools": "Linux, cloud platforms, monitoring tools",
}

print("DEVELOPMENT")
for key, value in development.items():
    print(f"  {key}: {value}")

print("\nOPERATIONS")
for key, value in operations.items():
    print(f"  {key}: {value}")


# ============================================================
# 7. THE OLD WALL BETWEEN DEV AND OPS
# ============================================================

print("\n7. THE OLD WALL BETWEEN DEV AND OPS")
print("-" * 70)

print("""
Imagine two departments:

+-----------------------+
|     DEVELOPMENT       |
|                       |
|  Write code           |
|  Build features       |
|  Fix bugs             |
+-----------------------+

             ||
             ||
             \\/

+-----------------------+
|      OPERATIONS       |
|                       |
|  Deploy               |
|  Maintain             |
|  Monitor              |
+-----------------------+

This separation can create:

    - Communication problems
    - Slow releases
    - Blame
    - Manual processes
    - Deployment failures
    - Environment inconsistencies
    - Long feedback cycles

DevOps attempts to reduce this organizational wall.
""")


# ============================================================
# 8. DEVOPS CULTURE
# ============================================================

print("\n8. DEVOPS CULTURE")
print("-" * 70)

print("""
DevOps culture is more important than any individual tool.

A company can install:

    Docker
    Kubernetes
    Jenkins
    Terraform
    GitHub Actions

and still not practice DevOps effectively.

Why?

Because tools alone cannot solve organizational problems.

DevOps culture encourages:

    Collaboration
    Trust
    Transparency
    Shared ownership
    Fast feedback
    Continuous learning
    Continuous improvement
    Experimentation
    Responsibility

Instead of:

    "Whose fault is this?"

the team asks:

    "Why did the system allow this failure?"

Instead of:

    "This is not my responsibility."

the team asks:

    "How can we help solve the problem?"
""")


# ============================================================
# 9. SHARED RESPONSIBILITY
# ============================================================

print("\n9. SHARED RESPONSIBILITY")
print("-" * 70)

print("""
In a traditional environment:

    Developer:
        "I wrote the code."

    Tester:
        "I tested it."

    Operations:
        "I deployed it."

    Nobody:
        "I own the complete outcome."

DevOps encourages:

    TEAM OWNERSHIP

The team collectively cares about:

    Code quality
    Security
    Deployment
    Reliability
    Performance
    Availability
    Customer experience

This does not mean every person performs every task.

It means teams stop treating organizational boundaries
as excuses to avoid responsibility.
""")


# ============================================================
# 10. HISTORY OF DEVOPS
# ============================================================

print("\n10. HISTORY OF DEVOPS")
print("-" * 70)

print("""
DevOps did not suddenly appear as a single technology.

It evolved from several ideas.

Important influences include:

    Traditional software development
        |
        v
    Agile software development
        |
        v
    Continuous Integration
        |
        v
    Continuous Delivery
        |
        v
    Infrastructure automation
        |
        v
    Cloud computing
        |
        v
    DevOps practices
        |
        v
    Platform Engineering
    SRE
    GitOps
    DevSecOps

Agile methodologies emphasized:

    - Shorter development cycles
    - Customer feedback
    - Iterative development
    - Adaptability
    - Collaboration

DevOps extended these ideas toward deployment,
infrastructure, operations, and production feedback.
""")


# ============================================================
# 11. AGILE AND DEVOPS
# ============================================================

print("\n11. AGILE VS DEVOPS")
print("-" * 70)

print("""
AGILE asks:

    How can we build software iteratively
    and respond quickly to change?

DEVOPS asks:

    How can we build, test, deploy, operate,
    and improve software continuously and reliably?

They complement each other.

Example:

    Agile:
        Build feature in a short iteration.

    DevOps:
        Automatically test and deploy that feature.

Together:

    Plan
      |
      v
    Code
      |
      v
    Build
      |
      v
    Test
      |
      v
    Deploy
      |
      v
    Monitor
      |
      v
    Feedback
      |
      +---------> Plan again
""")


# ============================================================
# 12. DEVOPS LIFECYCLE
# ============================================================

print("\n12. DEVOPS LIFECYCLE")
print("-" * 70)

devops_lifecycle = [
    "Plan",
    "Code",
    "Build",
    "Test",
    "Release",
    "Deploy",
    "Operate",
    "Monitor",
    "Feedback"
]

for number, stage in enumerate(devops_lifecycle, start=1):
    print(f"{number:02d}. {stage}")


print("""
The lifecycle is continuous.

There is no permanent final step.

After monitoring:

    Monitoring
         |
         v
      Feedback
         |
         v
       Plan
         |
         v
       Code
         |
         v
       Build
         |
         v
       Test
         |
         v
      Deploy
         |
         v
      Monitor

This creates a continuous feedback loop.
""")


# ============================================================
# 13. WHAT IS CALMS?
# ============================================================

print("\n13. CALMS FRAMEWORK")
print("-" * 70)

print("""
CALMS is a framework commonly associated with DevOps culture.

CALMS stands for:

    C = Culture
    A = Automation
    L = Lean
    M = Measurement
    S = Sharing

Each represents an important DevOps principle.
""")


# ============================================================
# 14. C = CULTURE
# ============================================================

print("\n14. C = CULTURE")
print("-" * 70)

print("""
Culture is about how people work together.

A strong DevOps culture encourages:

    - Collaboration
    - Trust
    - Shared responsibility
    - Learning
    - Transparency
    - Respect
    - Experimentation
    - Continuous improvement

Example:

Bad culture:

    Developer:
        "Operations broke my application."

    Operations:
        "Development gave us bad code."

    Management:
        "Find someone to blame."

Better culture:

    Developer + Operations:
        "The deployment failed."

    Team:
        "Let's understand why."

    Team:
        "Let's automate a test so this failure
         is detected earlier next time."

This is a DevOps mindset.
""")


# ============================================================
# 15. A = AUTOMATION
# ============================================================

print("\n15. A = AUTOMATION")
print("-" * 70)

print("""
Automation means using technology to perform repetitive
and predictable tasks consistently.

Examples:

    Manual:
        Developer builds application manually.

    Automated:
        CI system builds application automatically.

Manual:

    Someone logs into server.

Automated:

    Deployment pipeline deploys application.

Manual:

    Someone checks whether service is running.

Automated:

    Monitoring system checks continuously.

Automation reduces:

    - Human error
    - Repetitive work
    - Deployment time
    - Operational overhead
    - Inconsistency
""")


# ============================================================
# 16. SIMPLE AUTOMATION EXAMPLE
# ============================================================

print("\n16. SIMPLE PYTHON AUTOMATION EXAMPLE")
print("-" * 70)

servers = [
    "web-server-01",
    "web-server-02",
    "database-server-01",
    "cache-server-01"
]

print("Checking servers manually would be repetitive.")

for server in servers:
    print(f"Checking {server} ...")
    print(f"{server}: CHECK COMPLETED")

print("""
Instead of repeatedly performing the same task manually,
we wrote a program that performs the operation consistently.

This is the basic idea behind automation.

Real DevOps automation can be much more sophisticated,
including:

    CI/CD pipelines
    Infrastructure as Code
    Configuration management
    Automated testing
    Container orchestration
    Cloud provisioning
    Monitoring
    Alerting
""")


# ============================================================
# 17. L = LEAN
# ============================================================

print("\n17. L = LEAN")
print("-" * 70)

print("""
Lean focuses on reducing waste.

In software delivery, waste can include:

    - Waiting
    - Unnecessary approvals
    - Repetitive manual work
    - Large batches
    - Rework
    - Unused features
    - Slow feedback
    - Excessive handoffs

Example:

Traditional process:

    Developer
        |
        v
    Manager approval
        |
        v
    Testing team
        |
        v
    Operations approval
        |
        v
    Deployment

If every step requires long waiting periods,
delivery becomes slow.

A lean approach attempts to reduce unnecessary waiting
while maintaining appropriate controls.

The goal is:

    Smaller changes
    +
    Faster feedback
    +
    Less waste
    +
    Continuous improvement
""")


# ============================================================
# 18. M = MEASUREMENT
# ============================================================

print("\n18. M = MEASUREMENT")
print("-" * 70)

print("""
DevOps teams should measure what is happening.

Without measurement, improvement becomes guesswork.

Useful categories include:

    Deployment frequency
    Lead time for changes
    Change failure rate
    Recovery time
    Application performance
    Availability
    Error rates
    Infrastructure utilization
    Build duration
    Test success rate

For example:

If a deployment takes:

    2 hours

and automation reduces it to:

    10 minutes

the team can measure that improvement.

Measurement helps answer:

    Are we getting faster?

    Are we becoming more reliable?

    Are failures increasing?

    Are deployments becoming safer?

    Is automation actually helping?
""")


# ============================================================
# 19. SIMPLE METRICS EXAMPLE
# ============================================================

print("\n19. SIMPLE DEVOPS METRICS EXAMPLE")
print("-" * 70)

deployment_times = [120, 90, 75, 60, 45, 30, 20, 15]

average_time = sum(deployment_times) / len(deployment_times)

print("Historical deployment times in minutes:")
print(deployment_times)

print(f"\nAverage deployment time: {average_time:.2f} minutes")

print("""
This is a very simple example of measurement.

In a real organization, metrics can be collected automatically
from CI/CD systems, cloud infrastructure, monitoring systems,
version-control systems, and incident-management platforms.
""")


# ============================================================
# 20. S = SHARING
# ============================================================

print("\n20. S = SHARING")
print("-" * 70)

print("""
Sharing means sharing:

    Knowledge
    Information
    Responsibility
    Feedback
    Documentation
    Metrics
    Lessons learned

DevOps encourages transparency.

For example:

    Developers should understand production behavior.

    Operations should understand application requirements.

    Security should participate early.

    Teams should share monitoring information.

    Incident lessons should be documented.

A culture of sharing prevents knowledge from becoming trapped
inside individual teams.
""")


# ============================================================
# 21. CALMS SUMMARY
# ============================================================

print("\n21. CALMS SUMMARY")
print("-" * 70)

calms = {
    "C": "Culture - collaboration, trust and shared responsibility",
    "A": "Automation - automate repetitive and reliable processes",
    "L": "Lean - eliminate waste and improve flow",
    "M": "Measurement - measure performance and outcomes",
    "S": "Sharing - share knowledge, information and feedback"
}

for letter, meaning in calms.items():
    print(f"{letter} -> {meaning}")


# ============================================================
# 22. AUTOMATION MINDSET
# ============================================================

print("\n22. AUTOMATION MINDSET")
print("-" * 70)

print("""
Automation mindset means continuously asking:

    "Do we need to perform this manually?"

If the answer is:

    "We do this repeatedly."

Then ask:

    "Can it be automated?"

If the answer is yes:

    "How can we automate it safely?"

For example:

    Manual code formatting
            |
            v
    Automated formatter

    Manual testing
            |
            v
    Automated tests

    Manual build
            |
            v
    Automated build

    Manual deployment
            |
            v
    Automated deployment

    Manual infrastructure setup
            |
            v
    Infrastructure as Code

    Manual monitoring
            |
            v
    Automated monitoring and alerting
""")


# ============================================================
# 23. AUTOMATION DECISION MODEL
# ============================================================

print("\n23. AUTOMATION DECISION MODEL")
print("-" * 70)


def should_automate(task_frequency, human_error_risk, predictability):
    """
    A simplified educational model for deciding
    whether a task is a good candidate for automation.
    """

    score = 0

    if task_frequency >= 7:
        score += 1

    if human_error_risk >= 7:
        score += 1

    if predictability >= 7:
        score += 1

    if score >= 2:
        return "Strong candidate for automation"

    elif score == 1:
        return "Consider automation"

    else:
        return "Manual process may be acceptable"


print(
    should_automate(
        task_frequency=9,
        human_error_risk=8,
        predictability=9
    )
)

print(
    should_automate(
        task_frequency=2,
        human_error_risk=2,
        predictability=4
    )
)


# ============================================================
# 24. CI/CD
# ============================================================

print("\n24. CI/CD")
print("-" * 70)

print("""
DevOps is strongly associated with CI/CD.

CI means:

    Continuous Integration

CD can mean:

    Continuous Delivery

or:

    Continuous Deployment

Continuous Integration means developers frequently integrate
changes into a shared codebase and automated systems can
build and test those changes.

A simplified pipeline:

    Developer
        |
        v
    Git commit
        |
        v
    Build
        |
        v
    Automated tests
        |
        v
    Security checks
        |
        v
    Package
        |
        v
    Deploy

This dramatically reduces manual intervention.
""")


# ============================================================
# 25. SIMULATE A CI PIPELINE
# ============================================================

print("\n25. SIMULATING A CI PIPELINE")
print("-" * 70)


def run_build():
    print("[BUILD] Building application...")
    return True


def run_tests():
    print("[TEST] Running automated tests...")
    return True


def run_security_scan():
    print("[SECURITY] Running security checks...")
    return True


def deploy_application():
    print("[DEPLOY] Deploying application...")
    return True


print("Starting pipeline...\n")

pipeline_steps = [
    run_build,
    run_tests,
    run_security_scan,
    deploy_application
]

pipeline_success = True

for step in pipeline_steps:
    result = step()

    if not result:
        pipeline_success = False
        print("Pipeline stopped because a step failed.")
        break

if pipeline_success:
    print("\nPipeline completed successfully.")


# ============================================================
# 26. CONTINUOUS FEEDBACK
# ============================================================

print("\n26. CONTINUOUS FEEDBACK")
print("-" * 70)

print("""
One of the most important DevOps concepts is feedback.

Consider:

    Code
      |
      v
    Test
      |
      v
    Deploy
      |
      v
    Monitor
      |
      v
    User feedback
      |
      v
    Improve
      |
      v
    Code again

The shorter the feedback loop,
the faster a team can identify and fix problems.
""")


# ============================================================
# 27. DEVOPS AND CLOUD
# ============================================================

print("\n27. DEVOPS AND CLOUD COMPUTING")
print("-" * 70)

print("""
Cloud computing made DevOps practices even more powerful.

Traditional infrastructure might require:

    Buy server
    |
    v
    Install hardware
    |
    v
    Configure operating system
    |
    v
    Configure network
    |
    v
    Deploy application

This could take significant time.

Cloud platforms allow infrastructure to be provisioned
programmatically.

For example:

    Code
      |
      v
    Infrastructure definition
      |
      v
    Cloud API
      |
      v
    Infrastructure created

This concept leads to:

    Infrastructure as Code
""")


# ============================================================
# 28. INFRASTRUCTURE AS CODE
# ============================================================

print("\n28. INFRASTRUCTURE AS CODE")
print("-" * 70)

print("""
Infrastructure as Code means describing infrastructure
using machine-readable definitions.

Instead of saying:

    "Create a server manually."

you define:

    Server
    CPU
    Memory
    Network
    Storage
    Security rules

in code or configuration.

Common technologies include:

    Terraform
    OpenTofu
    CloudFormation
    Ansible
    Pulumi

The major advantage is repeatability.

If infrastructure is defined as code,
the same configuration can potentially be used
to recreate environments consistently.
""")


# ============================================================
# 29. CONTAINERS
# ============================================================

print("\n29. CONTAINERS AND DEVOPS")
print("-" * 70)

print("""
Containers help package applications together with
their required runtime components.

A simplified concept:

    Application
        +
    Dependencies
        +
    Runtime configuration
        |
        v
      Container

This can reduce environment inconsistencies.

Docker is one of the best-known container technologies.

Containers are especially useful in modern DevOps workflows
because they can be built, tested, distributed, and deployed
through automated pipelines.
""")


# ============================================================
# 30. KUBERNETES
# ============================================================

print("\n30. KUBERNETES AND DEVOPS")
print("-" * 70)

print("""
When organizations operate many containers,
managing them manually becomes difficult.

Kubernetes is a container orchestration platform.

It can help manage:

    - Container workloads
    - Scaling
    - Service discovery
    - Networking
    - Rolling deployments
    - Health checks
    - Desired state

A simplified model:

    Developer
        |
        v
    Container image
        |
        v
    Kubernetes
        |
        +------ Application instance 1
        |
        +------ Application instance 2
        |
        +------ Application instance 3
""")


# ============================================================
# 31. MONITORING
# ============================================================

print("\n31. MONITORING")
print("-" * 70)

print("""
DevOps does not end after deployment.

Once software reaches production,
teams need to understand how it behaves.

Monitoring can observe:

    CPU
    Memory
    Disk
    Network
    Request rate
    Error rate
    Latency
    Application health

Example:

    Application receives 10,000 requests.

    9,900 succeed.

    100 fail.

The team needs visibility into that behavior.

Without monitoring:

    Problem occurs
        |
        v
    Nobody knows

With monitoring:

    Problem occurs
        |
        v
    Metric changes
        |
        v
    Alert
        |
        v
    Engineer investigates
""")


# ============================================================
# 32. LOGGING
# ============================================================

print("\n32. LOGGING")
print("-" * 70)

print("""
Logs are records of events generated by software systems.

For example:

    User login successful
    Payment initiated
    Database connection failed
    API request received
    Service restarted

A simple Python example:
""")


def application_log(event, status):
    print(f"[LOG] event={event} status={status}")


application_log("user_login", "success")
application_log("database_connection", "success")
application_log("payment_request", "failed")


# ============================================================
# 33. OBSERVABILITY
# ============================================================

print("\n33. OBSERVABILITY")
print("-" * 70)

print("""
Modern DevOps environments often discuss observability.

Three classic observability signals are:

    Metrics
    Logs
    Traces

Metrics answer:

    "How much?"

Logs answer:

    "What happened?"

Traces answer:

    "Where did the request travel?"

Example:

A user clicks:

    BUY

The request might travel through:

    Browser
       |
       v
    API Gateway
       |
       v
    Application
       |
       v
    Payment Service
       |
       v
    Database

Tracing can help identify where latency or failure occurred.
""")


# ============================================================
# 34. DEVOPS SECURITY
# ============================================================

print("\n34. SECURITY IN DEVOPS")
print("-" * 70)

print("""
Modern DevOps increasingly integrates security throughout
the software lifecycle.

This idea is often called:

    DevSecOps

Instead of:

    Development
        |
        v
    Operations
        |
        v
    Security at the end

Security can be integrated into:

    Code
    Build
    Testing
    Dependencies
    Containers
    Infrastructure
    Deployment
    Monitoring

Examples include:

    Dependency scanning
    Secret detection
    Static analysis
    Container scanning
    Infrastructure security checks
""")


# ============================================================
# 35. FAILURE IS INFORMATION
# ============================================================

print("\n35. FAILURE IS INFORMATION")
print("-" * 70)

print("""
DevOps does not mean:

    "Nothing ever fails."

Modern distributed systems can fail.

The goal is to:

    Detect failures quickly
    Understand failures
    Recover quickly
    Learn from failures
    Prevent repeated failures

For example:

    Deployment fails.

Bad response:

    "Who caused this?"

Better response:

    "What condition caused this?"

Best response:

    "How can we modify the system so this failure
     becomes less likely or is detected earlier?"
""")


# ============================================================
# 36. POST-INCIDENT LEARNING
# ============================================================

print("\n36. POST-INCIDENT LEARNING")
print("-" * 70)

incident = {
    "Incident": "Application unavailable",
    "Detection": "Monitoring alert",
    "Impact": "Users unable to access application",
    "Cause": "Deployment configuration error",
    "Immediate_Action": "Rollback",
    "Long_Term_Action": "Automated configuration validation"
}

for key, value in incident.items():
    print(f"{key}: {value}")

print("""
This approach converts an incident into learning.

The objective is not merely:

    Fix today's problem.

The objective is also:

    Improve the system so tomorrow's problem
    becomes less likely.
""")


# ============================================================
# 37. DEVOPS TOOLCHAIN
# ============================================================

print("\n37. DEVOPS TOOLCHAIN")
print("-" * 70)

print("""
A modern DevOps environment can contain many categories
of tools.

Version Control:
    Git
    GitHub
    GitLab
    Bitbucket

CI/CD:
    GitHub Actions
    GitLab CI/CD
    Jenkins
    Azure Pipelines

Containers:
    Docker
    Podman

Orchestration:
    Kubernetes

Infrastructure as Code:
    Terraform
    OpenTofu
    CloudFormation
    Pulumi

Configuration Management:
    Ansible

Cloud:
    AWS
    Microsoft Azure
    Google Cloud

Monitoring:
    Prometheus
    Grafana

Logging:
    Elasticsearch
    Logstash
    OpenSearch

Security:
    Trivy
    Snyk
    SonarQube
    Dependency scanners

The important lesson:

    Learn the concepts first.

    Learn the tools second.
""")


# ============================================================
# 38. TOOL VS CONCEPT
# ============================================================

print("\n38. CONCEPT VS TOOL")
print("-" * 70)

print("""
Do not think:

    "DevOps = Jenkins."

Jenkins is a tool.

Do not think:

    "DevOps = Docker."

Docker is a tool.

Do not think:

    "DevOps = Kubernetes."

Kubernetes is a technology used in many DevOps environments.

Instead understand:

    Version control
    CI
    CD
    Automation
    Infrastructure as Code
    Containers
    Orchestration
    Monitoring
    Observability
    Security
    Collaboration
    Reliability

Once the concepts are understood,
individual tools become much easier to learn.
""")


# ============================================================
# 39. END-TO-END DEVOPS EXAMPLE
# ============================================================

print("\n39. END-TO-END DEVOPS EXAMPLE")
print("-" * 70)

print("""
Imagine an e-commerce company.

A developer adds a new discount feature.

STEP 1:
    Developer writes code.

STEP 2:
    Developer commits code to Git.

STEP 3:
    CI pipeline starts automatically.

STEP 4:
    Application is built.

STEP 5:
    Automated tests execute.

STEP 6:
    Security checks execute.

STEP 7:
    Container image is created.

STEP 8:
    Image is stored in a registry.

STEP 9:
    Deployment system deploys application.

STEP 10:
    Monitoring begins.

STEP 11:
    Metrics and logs are collected.

STEP 12:
    Users interact with the application.

STEP 13:
    Production feedback is collected.

STEP 14:
    Team analyzes the results.

STEP 15:
    Next improvement begins.

This is the DevOps feedback loop.
""")


# ============================================================
# 40. SIMULATE END-TO-END WORKFLOW
# ============================================================

print("\n40. SIMULATING END-TO-END DEVOPS WORKFLOW")
print("-" * 70)


def plan():
    print("1. PLAN")
    return True


def code():
    print("2. CODE")
    return True


def build():
    print("3. BUILD")
    return True


def test():
    print("4. TEST")
    return True


def release():
    print("5. RELEASE")
    return True


def deploy():
    print("6. DEPLOY")
    return True


def operate():
    print("7. OPERATE")
    return True


def monitor():
    print("8. MONITOR")
    return True


workflow = [
    plan,
    code,
    build,
    test,
    release,
    deploy,
    operate,
    monitor
]

for stage in workflow:
    stage()

print("\nWorkflow completed.")


# ============================================================
# 41. AUTOMATION MATURITY
# ============================================================

print("\n41. AUTOMATION MATURITY")
print("-" * 70)

print("""
Organizations can gradually improve automation.

LEVEL 1:

    Completely manual

LEVEL 2:

    Scripts automate individual tasks

LEVEL 3:

    CI automates builds and tests

LEVEL 4:

    CD automates deployment

LEVEL 5:

    Infrastructure is automated

LEVEL 6:

    Monitoring and alerting are automated

LEVEL 7:

    Security is integrated into pipelines

LEVEL 8:

    Highly automated platform with continuous feedback

The goal is not to automate everything blindly.

The goal is to automate valuable, repeatable,
safe, and measurable processes.
""")


# ============================================================
# 42. AUTOMATION IS NOT JUST SAVING TIME
# ============================================================

print("\n42. AUTOMATION IS NOT JUST ABOUT SAVING TIME")
print("-" * 70)

print("""
Automation provides several benefits.

1. CONSISTENCY

The same process executes in the same way.

2. REPEATABILITY

The process can be repeated many times.

3. SPEED

Machines can execute repetitive operations quickly.

4. REDUCED HUMAN ERROR

Fewer manual steps can reduce certain classes of mistakes.

5. TRACEABILITY

Automated systems can record what happened.

6. SCALABILITY

Automation allows organizations to handle more workloads.

7. STANDARDIZATION

Processes can become consistent across environments.
""")


# ============================================================
# 43. DEVOPS MINDSET QUESTIONS
# ============================================================

print("\n43. DEVOPS MINDSET QUESTIONS")
print("-" * 70)

questions = [
    "Can this process be automated?",
    "How quickly do we receive feedback?",
    "How frequently can we safely deploy?",
    "What happens when deployment fails?",
    "Can we reproduce the environment?",
    "Can we measure the result?",
    "How do developers and operations collaborate?",
    "How do we detect production problems?",
    "How quickly can we recover?",
    "What did we learn from the last incident?"
]

for number, question in enumerate(questions, start=1):
    print(f"{number}. {question}")


# ============================================================
# 44. DEVOPS IN ONE MODEL
# ============================================================

print("\n44. DEVOPS IN ONE MODEL")
print("-" * 70)

print("""
                     DEVOPS
                        |
        +---------------+---------------+
        |               |               |
      PEOPLE          PROCESS        TECHNOLOGY
        |               |               |
        |               |               |
   Collaboration     CI/CD          Automation
   Trust             Lean           Cloud
   Ownership         Feedback       Containers
   Sharing           Measurement    Monitoring
                                    Infrastructure
                                    as Code

All three dimensions matter.

Technology without culture:

    Tools exist but teams still work in silos.

Culture without process:

    People collaborate but delivery may remain inefficient.

Process without automation:

    Processes may remain slow and manual.

DevOps combines all three.
""")


# ============================================================
# 45. BEGINNER EXERCISE
# ============================================================

print("\n45. BEGINNER EXERCISE")
print("-" * 70)

print("""
Exercise:

Create a Python program that:

    1. Stores five software deployment tasks.
    2. Prints each task.
    3. Counts the number of tasks.
    4. Simulates task completion.
    5. Prints a final deployment report.

Example tasks:

    Build application
    Run tests
    Security scan
    Create container
    Deploy application
""")


tasks = [
    "Build application",
    "Run automated tests",
    "Run security scan",
    "Create container",
    "Deploy application"
]

completed = 0

for task in tasks:
    print(f"Executing: {task}")
    completed += 1

print("\nDeployment Report")
print("-" * 30)
print("Total tasks:", len(tasks))
print("Completed:", completed)
print("Failed:", len(tasks) - completed)


# ============================================================
# 46. INTERMEDIATE EXERCISE
# ============================================================

print("\n46. INTERMEDIATE EXERCISE")
print("-" * 70)

print("""
Create a deployment system that accepts:

    application name
    version
    environment

Then simulate:

    Build
    Test
    Security scan
    Deployment
    Monitoring
""")


def deploy_application_version(application, version, environment):

    print("\n----------------------------------------")
    print("DEPLOYMENT STARTED")
    print("----------------------------------------")

    print("Application:", application)
    print("Version:", version)
    print("Environment:", environment)

    print("\nBuilding...")
    print("Build successful.")

    print("Testing...")
    print("Tests successful.")

    print("Security scanning...")
    print("Security scan successful.")

    print("Deploying...")
    print("Deployment successful.")

    print("Starting monitoring...")
    print("Monitoring active.")

    print("\nDEPLOYMENT COMPLETED")


deploy_application_version(
    "ecommerce-api",
    "2.4.1",
    "production"
)


# ============================================================
# 47. ADVANCED THINKING EXERCISE
# ============================================================

print("\n47. ADVANCED THINKING EXERCISE")
print("-" * 70)

print("""
Imagine your organization deploys software manually.

Current process:

    1. Developer sends ZIP file.
    2. Operations downloads it.
    3. Operations logs into server.
    4. Existing application is stopped.
    5. New files are copied.
    6. Application is started.
    7. Someone manually checks the application.

Problems:

    - Slow
    - Error-prone
    - Difficult to reproduce
    - Difficult to audit
    - Difficult to scale

Design a DevOps solution.

Possible improvements:

    Git
      |
      v
    CI
      |
      v
    Automated tests
      |
      v
    Security scanning
      |
      v
    Container build
      |
      v
    Registry
      |
      v
    Automated deployment
      |
      v
    Monitoring
      |
      v
    Feedback

This is the type of transformation DevOps engineers
are expected to understand.
""")


# ============================================================
# 48. COMMON MISCONCEPTIONS
# ============================================================

print("\n48. COMMON DEVOPS MISCONCEPTIONS")
print("-" * 70)

misconceptions = {
    "DevOps is a tool": "Incorrect. DevOps is primarily a culture and set of practices.",
    "DevOps means developers do operations": "Oversimplified. DevOps emphasizes shared responsibility.",
    "DevOps means automation only": "Incorrect. Automation is one component.",
    "DevOps eliminates failures": "Incorrect. It aims to detect, recover and learn from failures.",
    "DevOps is only for large companies": "Incorrect. Small teams can use DevOps principles too.",
    "DevOps means deploying constantly": "Incorrect. Safe and reliable delivery matters more than raw frequency.",
    "Kubernetes is DevOps": "Incorrect. Kubernetes is one technology used in some DevOps environments."
}

for misconception, explanation in misconceptions.items():
    print("\nMISCONCEPTION:")
    print(misconception)
    print("REALITY:")
    print(explanation)


# ============================================================
# 49. DEVOPS KEY PRINCIPLES
# ============================================================

print("\n49. KEY DEVOPS PRINCIPLES")
print("-" * 70)

principles = [
    "Collaborate across organizational boundaries",
    "Automate repetitive processes",
    "Integrate and test code frequently",
    "Deliver smaller changes when appropriate",
    "Create fast feedback loops",
    "Measure performance and reliability",
    "Monitor production systems",
    "Treat infrastructure as code where appropriate",
    "Integrate security throughout the lifecycle",
    "Learn from failures",
    "Continuously improve"
]

for number, principle in enumerate(principles, start=1):
    print(f"{number:02d}. {principle}")


# ============================================================
# 50. FINAL SUMMARY
# ============================================================

print("\n50. FINAL SUMMARY")
print("=" * 70)

print("""
DEVOPS = DEVELOPMENT + OPERATIONS

But DevOps is much more than combining two job titles.

DevOps represents a way of designing software delivery
around collaboration, automation, feedback, measurement,
and continuous improvement.

The major concepts are:

    1. Development
    2. Operations
    3. Collaboration
    4. Automation
    5. Continuous Integration
    6. Continuous Delivery
    7. Continuous Deployment
    8. Infrastructure as Code
    9. Containers
    10. Cloud
    11. Monitoring
    12. Observability
    13. Security
    14. Measurement
    15. Continuous improvement

The CALMS framework provides another useful way to remember
the cultural and operational foundation:

    C = Culture
    A = Automation
    L = Lean
    M = Measurement
    S = Sharing

The most important mindset is:

    BUILD IT
       |
       v
    TEST IT
       |
       v
    DEPLOY IT
       |
       v
    OPERATE IT
       |
       v
    MONITOR IT
       |
       v
    LEARN FROM IT
       |
       v
    IMPROVE IT
       |
       +--------------------+
                            |
                            v
                         BUILD IT

This continuous loop is at the heart of modern DevOps.

Remember:

    DevOps is not just Jenkins.
    DevOps is not just Docker.
    DevOps is not just Kubernetes.
    DevOps is not just cloud computing.

DevOps is the combination of:

    PEOPLE
    +
    CULTURE
    +
    PROCESS
    +
    AUTOMATION
    +
    MEASUREMENT
    +
    SHARING
    +
    CONTINUOUS IMPROVEMENT
    +
    TECHNOLOGY

That is the foundation on which advanced DevOps,
Cloud Engineering, SRE, Platform Engineering,
DevSecOps, CI/CD, and MLOps practices are built.
""")


print("=" * 70)
print("END OF INTRODUCTION TO DEVOPS")
print("=" * 70)
